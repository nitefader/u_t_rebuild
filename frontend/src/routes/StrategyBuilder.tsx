import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Lock, Save, Sparkles } from "lucide-react";
import { ApiError } from "@/api/client";
import { StrategiesApi } from "@/api/strategies";
import { StrategyComposerApi } from "@/api/strategyComposer";
import {
  StrategyVersionPayloadSchema,
  type StrategyVersionPayload,
  type StrategyVersionRecord,
} from "@/api/schemas/strategies";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import {
  BuilderPane,
  builderFromVersionPayload,
  builderToVersionPayload,
  emptyBuilderFormValue,
  type BuilderFormValue,
} from "@/components/strategy_builder/BuilderPane";
import { logicalExitToPayload } from "@/components/strategy_builder/conditionUtils";
import { PageHeader } from "./PageHeader";

/**
 * StrategyBuilder — full-page route for authoring a Strategy version.
 *
 * Routes:
 *   /strategies/:strategyId/builder/new          → draft a new version
 *   /strategies/:strategyId/builder/:versionId   → edit the current draft
 *
 * Layout:
 *   - PageHeader: strategy name + "Save draft" + "Save & Freeze"
 *   - Left column: section nav (Identity / Features / Entry / Exit)
 *   - Center column: BuilderPane (typed form, big breathing room)
 *   - Right column: live Validation, Feature Plan Preview
 *
 * Drives the same /api/v1/strategies endpoints as the AI Composer's edit
 * pane, so anything authored here is interchangeable with composer drafts.
 */
export function StrategyBuilder(): JSX.Element {
  const params = useParams();
  const strategyId = params.strategyId ?? "";
  const versionParam = params.versionId ?? "new";
  const navigate = useNavigate();
  const qc = useQueryClient();

  const detail = useQuery({
    queryKey: ["strategies", "detail", strategyId],
    queryFn: () => StrategiesApi.get(strategyId),
    enabled: Boolean(strategyId),
  });

  const editingVersion: StrategyVersionRecord | null = useMemo(() => {
    if (!detail.data || versionParam === "new") return null;
    return detail.data.versions.find((v) => v.strategy_version_id === versionParam) ?? null;
  }, [detail.data, versionParam]);

  const isFrozen = editingVersion?.status === "frozen";
  const versionNumber = useMemo(() => {
    if (editingVersion) return editingVersion.version;
    const last = detail.data?.versions.at(-1)?.version ?? 0;
    return last + 1;
  }, [editingVersion, detail.data]);

  const [form, setForm] = useState<BuilderFormValue>(() => emptyBuilderFormValue());
  const [error, setError] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (hydrated) return;
    if (versionParam === "new") {
      setHydrated(true);
      return;
    }
    if (editingVersion) {
      setForm(builderFromVersionPayload(editingVersion.payload));
      setHydrated(true);
    }
  }, [editingVersion, versionParam, hydrated]);

  // Live validation + plan preview snapshots driven off the current form.
  const editFeatureRefs = useMemo(
    () => Array.from(new Set(form.feature_refs.filter(Boolean))),
    [form.feature_refs],
  );
  const validation = useQuery({
    queryKey: ["strategy-builder-page", "validate", editFeatureRefs.join("\n")],
    queryFn: () =>
      StrategyComposerApi.validateFeatures({ feature_refs: editFeatureRefs, consumer: "backtest" }),
    enabled: editFeatureRefs.length > 0,
    staleTime: 30_000,
  });
  const planPreview = useQuery({
    queryKey: ["strategy-builder-page", "plan-preview", editFeatureRefs.join("\n")],
    queryFn: () =>
      StrategyComposerApi.planPreview({ feature_refs: editFeatureRefs, consumer: "backtest" }),
    enabled: editFeatureRefs.length > 0,
    staleTime: 30_000,
  });

  function buildPayload(): StrategyVersionPayload {
    const versionId = editingVersion?.strategy_version_id ?? crypto.randomUUID();
    const createdAt = editingVersion?.created_at ?? new Date().toISOString();
    const raw = builderToVersionPayload({
      form,
      strategyId,
      versionId,
      versionNumber,
      createdAt,
    });
    raw.exit_rules = raw.exit_rules.map((r) => ({
      ...r,
      logical_exit_rule: r.logical_exit_rule
        ? logicalExitToPayload(r.logical_exit_rule) ?? undefined
        : undefined,
    }));
    if (raw.entry_rules.length === 0 && raw.exit_rules.length === 0) {
      throw new Error("Strategy version requires at least one entry or exit rule.");
    }
    for (const [i, r] of raw.exit_rules.entries()) {
      if (!r.condition && !r.logical_exit_rule) {
        throw new Error(
          `Exit rule ${i + 1} (${r.name || "unnamed"}) needs a condition or a logical_exit_rule.`,
        );
      }
    }
    for (const [i, r] of raw.entry_rules.entries()) {
      if (!r.condition) {
        throw new Error(`Entry rule ${i + 1} (${r.name || "unnamed"}) needs a feature condition.`);
      }
    }
    const parsed = StrategyVersionPayloadSchema.safeParse(raw);
    if (!parsed.success) {
      throw new Error(
        parsed.error.issues
          .slice(0, 5)
          .map((i) => `${i.path.join(".")}: ${i.message}`)
          .join("; "),
      );
    }
    return parsed.data;
  }

  const save = useMutation({
    mutationFn: async () => {
      const payload = buildPayload();
      if (editingVersion) {
        return StrategiesApi.editDraftVersion(strategyId, editingVersion.strategy_version_id, payload);
      }
      return StrategiesApi.addVersion(strategyId, payload);
    },
    onSuccess: (record) => {
      void qc.invalidateQueries({ queryKey: ["strategies"] });
      // Land on the strategy detail page after a successful add. For draft
      // edits, stay put with refreshed data.
      if (!editingVersion) {
        navigate(`/strategies/${strategyId}`);
      } else {
        // Keep the editor in sync so subsequent edits don't carry stale state.
        setForm(builderFromVersionPayload(record.payload));
      }
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  const freeze = useMutation({
    mutationFn: async () => {
      // Save first to capture the latest edits, then freeze.
      let versionId = editingVersion?.strategy_version_id;
      if (editingVersion) {
        await StrategiesApi.editDraftVersion(
          strategyId,
          editingVersion.strategy_version_id,
          buildPayload(),
        );
      } else {
        const record = await StrategiesApi.addVersion(strategyId, buildPayload());
        versionId = record.strategy_version_id;
      }
      if (!versionId) throw new Error("missing strategy_version_id");
      return StrategiesApi.freezeVersion(strategyId, versionId);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["strategies"] });
      navigate(`/strategies/${strategyId}`);
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  function handleSave(): void {
    setError(null);
    try {
      buildPayload();
    } catch (e) {
      setError((e as Error).message);
      return;
    }
    save.mutate();
  }

  function handleFreeze(): void {
    setError(null);
    try {
      buildPayload();
    } catch (e) {
      setError((e as Error).message);
      return;
    }
    freeze.mutate();
  }

  if (detail.isLoading) {
    return (
      <div className="space-y-4">
        <PageHeader title="Strategy Builder" />
        <LoadingState title="Loading strategy" />
      </div>
    );
  }
  if (detail.isError || !detail.data) {
    return (
      <div className="space-y-4">
        <PageHeader title="Strategy Builder" />
        <ErrorState
          title="Could not load strategy"
          detail={(detail.error as Error)?.message}
          onRetry={() => detail.refetch()}
        />
      </div>
    );
  }

  const strategy = detail.data.strategy;

  return (
    <div className="space-y-4">
      <PageHeader
        title={`${strategy.name} · v${versionNumber}`}
        subtitle="Visual builder · pick features from the registry · time / bars / session / feature / hybrid exits all live under one logical_exit picker. Past frozen versions are immutable."
        explainSlug="strategy-builder"
        actions={
          <div className="flex items-center gap-2">
            <Link to={`/strategies/${strategyId}`}>
              <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />}>
                Back to {strategy.name}
              </Button>
            </Link>
            <Link to="/strategies/compose">
              <Button
                size="sm"
                variant="secondary"
                leftIcon={<Sparkles className="h-3.5 w-3.5" aria-hidden="true" />}
              >
                AI Composer
              </Button>
            </Link>
            <Button
              size="sm"
              variant="secondary"
              onClick={handleSave}
              disabled={isFrozen || !form.name.trim() || save.isPending}
              loading={save.isPending}
              leftIcon={<Save className="h-3.5 w-3.5" aria-hidden="true" />}
            >
              {editingVersion ? "Save draft" : "Save as draft"}
            </Button>
            <Button
              size="sm"
              variant="primary"
              onClick={handleFreeze}
              disabled={isFrozen || !form.name.trim() || freeze.isPending}
              loading={freeze.isPending}
              leftIcon={<Lock className="h-3.5 w-3.5" aria-hidden="true" />}
            >
              Save &amp; Freeze
            </Button>
          </div>
        }
      />

      {isFrozen ? (
        <Banner
          severity="warning"
          title="Frozen version"
          message="Frozen versions are immutable lineage. Open StrategyDetail and add a new version to introduce changes."
        />
      ) : null}

      {error ? <Banner severity="danger" title="Cannot save version" message={error} /> : null}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[16rem_minmax(0,1fr)_22rem]">
        <SectionNav />
        <div className="space-y-4">
          <BuilderPane value={form} onChange={setForm} consumer="backtest" />
        </div>
        <div className="space-y-3">
          <Card>
            <CardHeader>
              <CardTitle>Validation</CardTitle>
              {validation.data ? (
                validation.data.valid ? (
                  <StatusBadge tone="ok">valid</StatusBadge>
                ) : (
                  <StatusBadge tone="danger">invalid</StatusBadge>
                )
              ) : (
                <StatusBadge tone="muted">—</StatusBadge>
              )}
            </CardHeader>
            <CardBody className="text-xs">
              {validation.data && validation.data.items.length > 0 ? (
                <ul className="space-y-1">
                  {validation.data.items.map((item) => (
                    <li key={item.input} className="flex items-start gap-2">
                      <StatusBadge tone={item.valid ? "ok" : "danger"}>
                        {item.valid ? "✓" : "✗"}
                      </StatusBadge>
                      <span className="min-w-0 flex-1">
                        <span className="font-mono text-[11px]">{item.input}</span>
                        {item.normalized_ref && item.normalized_ref !== item.input ? (
                          <span className="ml-1 text-fg-subtle">→ {item.normalized_ref}</span>
                        ) : null}
                        {item.message ? (
                          <span className="block text-[10px] text-danger">{item.message}</span>
                        ) : null}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="text-fg-muted">Pick features to see live validation.</span>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Feature plan preview</CardTitle>
              {planPreview.data ? (
                planPreview.data.valid ? (
                  <StatusBadge tone="ok">{planPreview.data.feature_keys.length} keys</StatusBadge>
                ) : (
                  <StatusBadge tone="danger">invalid</StatusBadge>
                )
              ) : (
                <StatusBadge tone="muted">—</StatusBadge>
              )}
            </CardHeader>
            <CardBody className="text-xs">
              {planPreview.data ? (
                <>
                  {planPreview.data.feature_keys.length > 0 ? (
                    <ul className="space-y-0.5 font-mono text-[11px]">
                      {planPreview.data.feature_keys.map((k) => (
                        <li key={k}>{k}</li>
                      ))}
                    </ul>
                  ) : null}
                  {!planPreview.data.valid && planPreview.data.errors.length > 0 ? (
                    <div className="mt-2 rounded border border-danger/40 bg-danger-subtle/40 px-2 py-1 text-[11px] text-danger">
                      {planPreview.data.errors.slice(0, 3).join(" · ")}
                    </div>
                  ) : null}
                  {Object.keys(planPreview.data.warmup_by_timeframe ?? {}).length > 0 ? (
                    <div className="mt-2">
                      <div className="text-[10px] uppercase tracking-wide text-fg-muted">Warmup</div>
                      <ul className="mt-0.5 space-y-0.5 text-[11px]">
                        {Object.entries(planPreview.data.warmup_by_timeframe).map(([tf, n]) => (
                          <li key={tf}>
                            <span className="font-mono">{tf}</span>
                            <span className="ml-1 text-fg-muted">{n} bars</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </>
              ) : (
                <span className="text-fg-muted">Pick features to see plan preview.</span>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>What happens on save?</CardTitle>
            </CardHeader>
            <CardBody className="space-y-1 text-xs text-fg-muted">
              <p>
                <strong>Save draft</strong> stores the version as an editable draft. You can return
                and tweak it, then freeze it later.
              </p>
              <p>
                <strong>Save &amp; Freeze</strong> publishes the version. Frozen versions are
                immutable lineage and Deployments can only point at frozen versions.
              </p>
              <p>Saving never deploys, attaches an Account, or submits a broker order.</p>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

const SECTIONS: { id: string; label: string }[] = [
  { id: "identity", label: "Identity" },
  { id: "features", label: "Feature plan" },
  { id: "entries", label: "Entry rules" },
  { id: "exits", label: "Exit rules" },
];

function SectionNav(): JSX.Element {
  return (
    <Card className="hidden xl:block">
      <CardHeader>
        <CardTitle>Sections</CardTitle>
      </CardHeader>
      <CardBody className="space-y-1 text-xs">
        {SECTIONS.map((s) => (
          <a
            key={s.id}
            href={`#${s.id}`}
            className="block rounded px-2 py-1 text-fg-muted hover:bg-bg-subtle hover:text-fg"
          >
            {s.label}
          </a>
        ))}
        <div className="mt-2 border-t border-border/70 pt-2 text-[11px] text-fg-subtle">
          Tip: pick features from the live catalog — the picker emits canonical
          syntax so backend validators stay in sync.
        </div>
      </CardBody>
    </Card>
  );
}
