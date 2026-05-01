/**
 * StrategyComposeV4 — the v4 IDE shell page at /strategies/compose.
 *
 * Layout:
 *   Top bar   : Back, title, name, description, DirectionToggle, HorizonPicker,
 *               CoverageChips, validation pill, Save button, slide-out toggle
 *   Left rail : FeaturePalette (Features tab + Exit blocks tab)
 *   Center    : LongShortTabs + VariablesStrip + MonacoExpressionEditor
 *               + StopsSection + LegsSection + ExitsSection + ExecutionPreview
 *   Right rail: StarterStrategyPanel (collapsible)
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Loader2, PanelRightClose, PanelRightOpen, Save } from "lucide-react";
import { ROUTE_STRATEGIES, ROUTE_STRATEGIES_COMPOSE } from "@/strategy_ide_v4/routes";
import { FeaturePalette } from "@/strategy_ide_v4/FeaturePalette";
import { VariablesStrip } from "@/strategy_ide_v4/VariablesStrip";
import { LongShortTabs, type TradeSide } from "@/strategy_ide_v4/LongShortTabs";
import {
  MonacoExpressionEditor,
  type MonacoExpressionEditorHandle,
} from "@/strategy_ide_v4/MonacoExpressionEditor";
import type { ExpressionValidateResult } from "@/strategy_ide_v4/MonacoExpressionEditor";
import { BrowseFeaturesOverlay } from "@/strategy_ide_v4/BrowseFeaturesOverlay";
import { StopsSection } from "@/strategy_ide_v4/StopsSection";
import { LegsSection } from "@/strategy_ide_v4/LegsSection";
import { ExitsSection } from "@/strategy_ide_v4/ExitsSection";
import type { ExitsSectionValue } from "@/strategy_ide_v4/ExitsSection";
import { DirectionToggle } from "@/strategy_ide_v4/DirectionToggle";
import type { Direction } from "@/strategy_ide_v4/DirectionToggle";
import { HorizonPicker } from "@/strategy_ide_v4/HorizonPicker";
import type { Horizon, BaseTimeframe } from "@/strategy_ide_v4/HorizonPicker";
import { CoverageChips } from "@/strategy_ide_v4/CoverageChips";
import { StarterStrategyPanel } from "@/strategy_ide_v4/StarterStrategyPanel";
import { ExecutionPreview } from "@/strategy_ide_v4/ExecutionPreview";
import { buildPlaceholderLegs, buildPlaceholderStops } from "@/strategy_ide_v4/draftDefaults";
import { validateLegs, validateStops } from "@/strategy_ide_v4/legAutoBalance";
import { ApiError } from "@/api/client";
import { saveDraft, loadVersion } from "@/api/strategiesV4";
import type {
  StrategyVariableV4Draft,
  StrategyStopV4Draft,
  StrategyLegV4Draft,
  StrategyVersionV4Draft,
} from "@/api/schemas/strategiesV4";
import { Button } from "@/components/ui/Button";
import { Banner } from "@/components/ui/Banner";
import { TextField } from "@/components/ui/TextField";

/** FastAPI/Pydantic 422 body `detail`: array of `{ loc, msg }`. */
function messagesFromFastApiValidationDetail(detail: unknown): string[] {
  if (!Array.isArray(detail)) return [];
  const out: string[] = [];
  for (const raw of detail) {
    if (!raw || typeof raw !== "object") continue;
    const item = raw as { loc?: unknown; msg?: unknown };
    const msg = typeof item.msg === "string" ? item.msg.trim() : "";
    if (!msg) continue;

    const locRaw = Array.isArray(item.loc) ? item.loc : [];
    while (
      locRaw.length > 0 &&
      (locRaw[0] === "body" || locRaw[0] === "query" || locRaw[0] === "path")
    ) {
      locRaw.splice(0, 1);
    }

    let path = "";
    for (const segment of locRaw) {
      if (typeof segment === "number") path += `[${segment}]`;
      else path += path === "" ? String(segment) : `.${segment}`;
    }
    out.push(path ? `${path}: ${msg}` : msg);
  }
  return out;
}

interface LastSaved {
  version: number;
  saved_at: string;
  id: string;
}

// ---------------------------------------------------------------------------
// ValidationPill — inline status chip in the top bar
// ---------------------------------------------------------------------------

function ValidationPill({
  result,
  savedVersion,
  savedVisible,
}: {
  result: ExpressionValidateResult | null;
  savedVersion: number | null;
  savedVisible: boolean;
}): JSX.Element | null {
  if (savedVisible && savedVersion !== null) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-ok-subtle px-2 py-0.5 text-xs font-medium text-ok">
        <span className="h-1.5 w-1.5 rounded-full bg-ok" />
        Saved v{savedVersion}
      </span>
    );
  }

  if (!result) return null;

  if (result.valid) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-ok-subtle px-2 py-0.5 text-xs font-medium text-ok">
        <span className="h-1.5 w-1.5 rounded-full bg-ok" />
        Valid
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-danger-subtle px-2 py-0.5 text-xs font-medium text-danger">
      <span className="h-1.5 w-1.5 rounded-full bg-danger" />
      {result.errors.length} error{result.errors.length !== 1 ? "s" : ""}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function StrategyComposeV4(): JSX.Element {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const loadId = searchParams.get("id");

  // Form state
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [direction, setDirection] = useState<Direction>("both");
  const [variables, setVariables] = useState<StrategyVariableV4Draft[]>([]);
  const [entryLong, setEntryLong] = useState("");
  const [entryShort, setEntryShort] = useState("");
  const [stops, setStops] = useState<StrategyStopV4Draft[]>(() => buildPlaceholderStops());
  const [legs, setLegs] = useState<StrategyLegV4Draft[]>(() => buildPlaceholderLegs());
  const [logicalExits, setLogicalExits] = useState<ExitsSectionValue>({ long: [], short: [] });
  const [activeSide, setActiveSide] = useState<TradeSide>("long");

  // Horizon / base-timeframe UX filters (do NOT touch draft domain)
  const [horizon, setHorizon] = useState<Horizon | null>(null);
  const [baseTimeframe, setBaseTimeframe] = useState<BaseTimeframe>("5m");

  // Right-rail state — closed by default when loading an existing strategy
  const [starterPanelOpen, setStarterPanelOpen] = useState(!loadId);

  // UI state
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveErrors, setSaveErrors] = useState<string[]>([]);
  const [lastSaved, setLastSaved] = useState<LastSaved | null>(null);
  const [saveBannerVisible, setSaveBannerVisible] = useState(false);
  const [savedPillVisible, setSavedPillVisible] = useState(false);
  const [browseOpen, setBrowseOpen] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [validationResult, setValidationResult] = useState<ExpressionValidateResult | null>(null);

  // Block double-save for 250ms after success — MUST be state-backed so cooldown expiry re-renders.
  const [saveCooldownUntil, setSaveCooldownUntil] = useState<number | null>(null);
  // Ref to clear the auto-dismiss timer on unmount
  const bannerTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const savedPillTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Track whether user has interacted with the banner (cancels auto-dismiss)
  const bannerInteractedRef = useRef(false);
  const saveCooldownClearRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const onBack = (): void => {
    if (window.history.length > 1) navigate(-1);
    else navigate(ROUTE_STRATEGIES);
  };

  // Handle for programmatic text insertion into the active editor
  const editorHandleRef = useRef<MonacoExpressionEditorHandle | null>(null);

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      if (bannerTimerRef.current) clearTimeout(bannerTimerRef.current);
      if (savedPillTimerRef.current) clearTimeout(savedPillTimerRef.current);
      if (saveCooldownClearRef.current) clearTimeout(saveCooldownClearRef.current);
    };
  }, []);

  // Load existing version if ?id= is set
  useEffect(() => {
    if (!loadId) return;
    loadVersion(loadId)
      .then((version) => {
        setName(version.name);
        setDescription(version.description ?? "");
        setDirection((version.identity?.direction as Direction) ?? "both");
        setVariables(
          (version.variables ?? []).map((v) => ({
            name: v.name,
            expression_text: v.expression_text,
            kind: v.kind ?? "expression",
          })),
        );
        setEntryLong(version.entries?.long?.expression_text ?? "");
        setEntryShort(version.entries?.short?.expression_text ?? "");
        if (version.stops && version.stops.length > 0) {
          setStops(version.stops as StrategyStopV4Draft[]);
        }
        if (version.legs && version.legs.length > 0) {
          setLegs(version.legs as StrategyLegV4Draft[]);
        }
        if (version.logical_exits) {
          setLogicalExits({
            long: (version.logical_exits.long ?? []) as ExitsSectionValue["long"],
            short: (version.logical_exits.short ?? []) as ExitsSectionValue["short"],
          });
        }
        // Collapse starter panel when loading an existing strategy
        setStarterPanelOpen(false);
      })
      .catch((err: unknown) => {
        setLoadError(err instanceof Error ? err.message : "Failed to load strategy");
      });
  }, [loadId]);

  // Keyboard shortcut: Ctrl+Space opens browse overlay
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent): void {
      if (e.ctrlKey && e.code === "Space") {
        e.preventDefault();
        setBrowseOpen(true);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  function handleTabChange(side: TradeSide, _text: string): void {
    setActiveSide(side);
  }

  function handleEditorChange(text: string): void {
    if (activeSide === "long") setEntryLong(text);
    else setEntryShort(text);
  }

  const handleMirror = useCallback(
    (mirroredText: string, targetSide: TradeSide): void => {
      if (targetSide === "long") setEntryLong(mirroredText);
      else setEntryShort(mirroredText);
    },
    [],
  );

  function handleInsertFromPalette(text: string): void {
    editorHandleRef.current?.insertAtCursor(text);
  }

  function handleInsertFromOverlay(text: string): void {
    editorHandleRef.current?.insertAtCursor(text);
    setBrowseOpen(false);
  }

  function handleApplyTemplate(draft: StrategyVersionV4Draft): void {
    setName(draft.name);
    setDescription(draft.description ?? "");
    setDirection((draft.identity?.direction ?? "both") as Direction);
    setVariables(draft.variables ?? []);
    setEntryLong(draft.entries?.long?.expression_text ?? "");
    setEntryShort(draft.entries?.short?.expression_text ?? "");
    setStops(draft.stops ?? buildPlaceholderStops());
    setLegs(draft.legs ?? buildPlaceholderLegs());
    setLogicalExits({
      long: (draft.logical_exits?.long ?? []) as ExitsSectionValue["long"],
      short: (draft.logical_exits?.short ?? []) as ExitsSectionValue["short"],
    });
  }

  function showSaveBanner(meta: LastSaved): void {
    // Cancel any existing auto-dismiss
    if (bannerTimerRef.current) clearTimeout(bannerTimerRef.current);
    if (savedPillTimerRef.current) clearTimeout(savedPillTimerRef.current);
    bannerInteractedRef.current = false;

    setLastSaved(meta);
    setSaveBannerVisible(true);
    setSavedPillVisible(true);

    // Auto-dismiss banner after 5s unless user interacted
    bannerTimerRef.current = setTimeout(() => {
      if (!bannerInteractedRef.current) {
        setSaveBannerVisible(false);
      }
    }, 5000);

    savedPillTimerRef.current = setTimeout(() => {
      setSavedPillVisible(false);
      savedPillTimerRef.current = null;
    }, 10000);
  }

  function dismissSaveBanner(): void {
    bannerInteractedRef.current = true;
    if (bannerTimerRef.current) clearTimeout(bannerTimerRef.current);
    setSaveBannerVisible(false);
  }

  function handleSaveBannerInteract(): void {
    bannerInteractedRef.current = true;
  }

  const isSaveDisabled =
    saving ||
    legsValidationResult().structureInvalid ||
    (saveCooldownUntil !== null && Date.now() < saveCooldownUntil);

  // eslint-disable-next-line @typescript-eslint/explicit-function-return-type
  function legsValidationResult() {
    const legsV = validateLegs(legs);
    const stopsV = validateStops(stops);
    return {
      structureInvalid: !legsV.valid || !stopsV.valid,
      structureErrors: [...stopsV.errors, ...legsV.errors],
    };
  }

  async function handleSave(): Promise<void> {
    if (saveCooldownUntil !== null && Date.now() < saveCooldownUntil) return;

    setSaveError(null);
    setSaveErrors([]);

    if (!name.trim()) {
      setSaveError("Strategy name is required");
      return;
    }
    if (!entryLong.trim() && !entryShort.trim()) {
      setSaveError("At least one entry expression (long or short) is required");
      return;
    }

    const { structureInvalid, structureErrors } = legsValidationResult();
    if (structureInvalid) {
      setSaveErrors(structureErrors);
      return;
    }

    const draft = {
      name: name.trim(),
      description: description.trim() || null,
      identity: { tags: [], direction },
      timeframe_aliases: {},
      variables,
      entries: {
        long: entryLong.trim() ? { expression_text: entryLong.trim() } : null,
        short: entryShort.trim() ? { expression_text: entryShort.trim() } : null,
      },
      stops,
      legs,
      logical_exits: logicalExits,
    };

    setSaving(true);
    try {
      const saved = await saveDraft(draft);
      const savedId = saved.id as string;
      const savedVersion = (saved.version as number) ?? 1;
      const savedAt = (saved.created_at as string) ?? new Date().toISOString();

      const until = Date.now() + 250;
      setSaveCooldownUntil(until);
      if (saveCooldownClearRef.current) clearTimeout(saveCooldownClearRef.current);
      saveCooldownClearRef.current = setTimeout(() => {
        saveCooldownClearRef.current = null;
        setSaveCooldownUntil((prev) => (prev === until ? null : prev));
      }, 250);

      void navigate(`${ROUTE_STRATEGIES_COMPOSE}?id=${savedId}`, { replace: true });
      showSaveBanner({ version: savedVersion, saved_at: savedAt, id: savedId });
    } catch (err: unknown) {
      let surfacedList = false;

      if (err instanceof ApiError && err.body !== null && typeof err.body === "object") {
        const detail = (err.body as { detail?: unknown }).detail;
        const fastApiMsgs = messagesFromFastApiValidationDetail(detail);
        if (fastApiMsgs.length > 0) {
          setSaveErrors(fastApiMsgs);
          surfacedList = true;
        } else if (detail !== undefined && typeof detail === "object" && !Array.isArray(detail)) {
          const errs = (detail as { validation_status?: { errors?: string[] } }).validation_status
            ?.errors;
          if (errs && errs.length > 0) {
            setSaveErrors(errs);
            surfacedList = true;
          }
        }
      }

      if (!surfacedList) {
        setSaveError(err instanceof Error ? err.message : "Save failed");
      }
    } finally {
      setSaving(false);
    }
  }

  const activeText = activeSide === "long" ? entryLong : entryShort;
  const exprVariableNames = variables
    .filter((v) => (v.kind ?? "expression") === "expression")
    .map((v) => v.name);
  const timeframeVariableNames = variables
    .filter((v) => v.kind === "timeframe")
    .map((v) => v.name);

  const { structureInvalid, structureErrors } = legsValidationResult();

  // Format the saved_at timestamp as a human-readable string
  function formatSavedAt(iso: string): string {
    try {
      return new Date(iso).toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return iso;
    }
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-bg text-fg">
      {/* Top bar */}
      <header className="flex shrink-0 items-center gap-2 border-b border-border bg-bg/80 px-4 py-2 backdrop-blur flex-wrap">
        <Button
          variant="ghost"
          size="sm"
          leftIcon={<ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />}
          onClick={onBack}
          aria-label="Back"
        >
          Back
        </Button>
        <span className="text-sm font-semibold text-fg-muted shrink-0">Compose v4</span>

        {/* Name + description */}
        <TextField
          label=""
          placeholder="Strategy name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-44 shrink-0"
          aria-label="Strategy name"
        />
        <TextField
          label=""
          placeholder="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="w-40 shrink-0"
          aria-label="Strategy description"
        />

        {/* Direction toggle */}
        <DirectionToggle value={direction} onChange={setDirection} />

        {/* Horizon + base timeframe */}
        <HorizonPicker
          horizon={horizon}
          onHorizonChange={setHorizon}
          timeframe={baseTimeframe}
          onTimeframeChange={setBaseTimeframe}
        />

        {/* Coverage chips */}
        <div className="flex-1 min-w-0 flex justify-end items-center gap-2">
          <CoverageChips
            entryLong={entryLong}
            entryShort={entryShort}
            stops={stops}
            legs={legs}
            logicalExits={logicalExits}
          />
          <ValidationPill
            result={validationResult}
            savedVersion={lastSaved?.version ?? null}
            savedVisible={savedPillVisible}
          />
          <Button
            variant="primary"
            size="sm"
            aria-label="Save strategy"
            leftIcon={
              saving ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <Save className="h-3.5 w-3.5" aria-hidden="true" />
              )
            }
            onClick={() => void handleSave()}
            disabled={isSaveDisabled}
          >
            {saving ? "Saving…" : "Save"}
          </Button>

          {/* Slide-out toggle */}
          <button
            type="button"
            className="shrink-0 rounded p-1 text-fg-subtle hover:bg-bg-raised hover:text-fg focus:outline-none transition-colors"
            onClick={() => setStarterPanelOpen((v) => !v)}
            aria-label={starterPanelOpen ? "Close starter strategies" : "Open starter strategies"}
            title={starterPanelOpen ? "Close starter strategies" : "Open starter strategies"}
          >
            {starterPanelOpen ? (
              <PanelRightClose className="h-4 w-4" aria-hidden="true" />
            ) : (
              <PanelRightOpen className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        </div>
      </header>

      {/* Load error */}
      {loadError ? (
        <div className="shrink-0 px-4 pt-3">
          <Banner severity="danger" title="Could not load strategy" message={loadError} />
        </div>
      ) : null}

      {/* Save success banner — rich, auto-dismissing */}
      {saveBannerVisible && lastSaved ? (
        <div
          className="shrink-0 px-4 pt-3"
          onMouseDown={handleSaveBannerInteract}
          onFocusCapture={handleSaveBannerInteract}
          role="presentation"
        >
          <Banner
            severity="success"
            title={`Saved as v${lastSaved.version} — ${formatSavedAt(lastSaved.saved_at)}`}
            action={
              <div className="flex items-center gap-2">
                <a
                  href={`${ROUTE_STRATEGIES_COMPOSE}?id=${lastSaved.id}`}
                  className="text-xs font-semibold underline decoration-ok/50 hover:no-underline"
                  onClick={(e) => {
                    e.preventDefault();
                    handleSaveBannerInteract();
                    void navigate(`${ROUTE_STRATEGIES_COMPOSE}?id=${lastSaved.id}`, { replace: true });
                  }}
                >
                  View version
                </a>
                <button
                  type="button"
                  onClick={dismissSaveBanner}
                  className="rounded px-2 py-0.5 text-xs font-medium text-ok hover:bg-ok/10 focus:outline-none"
                  aria-label="Dismiss confirmation banner"
                >
                  Dismiss
                </button>
              </div>
            }
          />
        </div>
      ) : null}

      {/* Save error (single message) */}
      {saveError ? (
        <div className="shrink-0 px-4 pt-3">
          <Banner severity="danger" title="Save failed" message={saveError} />
        </div>
      ) : null}

      {/* Validation errors from 422 */}
      {saveErrors.length > 0 ? (
        <div className="shrink-0 px-4 pt-3">
          <div className="rounded-lg border border-danger/40 bg-danger-subtle px-4 py-3">
            <p className="mb-1 text-sm font-semibold text-danger">
              Validation failed ({saveErrors.length} error{saveErrors.length !== 1 ? "s" : ""})
            </p>
            <ul className="list-disc pl-4 text-xs text-danger/80">
              {saveErrors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      {/* Main layout */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Left rail — Feature palette */}
        <aside className="w-[260px] shrink-0 border-r border-border bg-bg-subtle overflow-hidden">
          <FeaturePalette onInsert={handleInsertFromPalette} />
        </aside>

        {/* Center — Editor */}
        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {/* Long/Short tabs */}
          <LongShortTabs
            activeSide={activeSide}
            longText={entryLong}
            shortText={entryShort}
            onChange={handleTabChange}
            onMirror={handleMirror}
          />

          {/* Variables strip */}
          <VariablesStrip variables={variables} onChange={setVariables} />

          {/* Monaco editor */}
          <div className="flex-1 overflow-hidden">
            <MonacoExpressionEditor
              value={activeText}
              onChange={handleEditorChange}
              variableNames={exprVariableNames}
              timeframeVariableNames={timeframeVariableNames}
              onValidationChange={setValidationResult}
              height="100%"
              editorHandleRef={editorHandleRef}
            />
          </div>

          {/* Structure validation summary above Save (inline in editor area) */}
          {structureInvalid ? (
            <div className="shrink-0 border-t border-border px-4 py-2">
              <p className="text-xs text-danger">
                {structureErrors[0]}
                {structureErrors.length > 1 ? ` (+${structureErrors.length - 1} more)` : ""}
              </p>
            </div>
          ) : null}

          {/* Stops, legs, exits, and execution preview */}
          <div className="shrink-0 overflow-y-auto border-t border-border px-4 py-4 flex flex-col gap-6 max-h-[50vh]">
            <StopsSection
              stops={stops}
              legCount={legs.length}
              onChange={setStops}
              variableNames={exprVariableNames}
              timeframeVariableNames={timeframeVariableNames}
            />
            <LegsSection legs={legs} onChange={setLegs} />
            <ExecutionPreview legs={legs} stops={stops} />
            <ExitsSection value={logicalExits} onChange={setLogicalExits} />
          </div>
        </main>

        {/* Right rail — Starter strategy slide-out */}
        <StarterStrategyPanel
          open={starterPanelOpen}
          onOpenChange={setStarterPanelOpen}
          horizonFilter={horizon}
          directionFilter={null}
          onApply={handleApplyTemplate}
        />
      </div>

      {/* Browse features overlay (Ctrl+Space) */}
      <BrowseFeaturesOverlay
        open={browseOpen}
        onOpenChange={setBrowseOpen}
        onInsert={handleInsertFromOverlay}
      />
    </div>
  );
}
