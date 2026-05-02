import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { ApiError } from "@/api/client";
import { RiskPlansApi } from "@/api/riskPlans";
import type {
  CreateRiskPlanRequest,
  RiskPlanDetail,
  RiskPlanSource,
  RiskPlanSummary,
} from "@/api/schemas/riskPlans";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/Drawer";
import { TextField } from "@/components/ui/TextField";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { RiskPlanFormFields } from "./RiskPlanFormFields";
import {
  EMPTY_FORM,
  configFromFormState,
  formStateFromConfig,
  validateForm,
  type RiskPlanFormState,
} from "./riskPlanForm";

/**
 * RiskPlanDrawer — Create + Edit drawer for Risk Plans.
 *
 * Per RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §9.4 (form fields +
 * validation feedback) and §10 (AI draft).
 *
 * Modes:
 *   - mode="create": creates a new RiskPlan + initial RiskPlanVersion.
 *   - mode="edit":   posts a new RiskPlanVersion against an existing plan.
 *   - prefill:       optional form state (used by Save-as-Risk-Plan flow
 *                    + by AI draft accept).
 *
 * AI-draft section: when the operator provides a plain-English prompt,
 * we POST `/api/v1/risk-plans/ai-draft` and load the returned config into
 * the form. The operator MUST save explicitly (per §13 non-negotiable: AI
 * must never silently change RiskPlan settings).
 */
export type RiskPlanDrawerMode = "create" | "edit";

export interface RiskPlanDrawerProps {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  mode: RiskPlanDrawerMode;
  /** Required when mode === "edit". */
  plan?: RiskPlanDetail | null;
  /** Form prefill (used by Save-as-Risk-Plan flow + AI accept). */
  prefill?: Partial<RiskPlanFormState>;
  /** Default source for create flow ('manual' unless overridden). */
  defaultSource?: RiskPlanSource;
  /**
   * Optional human-readable AI summary to attach on save (set when prefill
   * came from AI draft / WF / Optimization). Persisted as `ai_summary` per
   * RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §4.1.
   */
  defaultAiSummary?: string | null;
  /** Required for research-derived Risk Plans. */
  defaultSourceRunId?: string | null;
  defaultSourceEvidenceType?: string | null;
  defaultEvidenceLineage?: Record<string, unknown>;
  /**
   * Optional ephemeral warnings shown in the drawer for operator review.
   * Not persisted — operator must read and decide before saving.
   */
  defaultAiWarnings?: readonly string[];
  onSaved?: (plan: RiskPlanSummary) => void;
}

export function RiskPlanDrawer({
  open,
  onOpenChange,
  mode,
  plan,
  prefill,
  defaultSource,
  defaultAiSummary,
  defaultSourceRunId,
  defaultSourceEvidenceType,
  defaultEvidenceLineage,
  defaultAiWarnings,
  onSaved,
}: RiskPlanDrawerProps): JSX.Element {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<RiskPlanFormState>(EMPTY_FORM);
  const [aiPrompt, setAiPrompt] = useState<string>("");
  const [aiSummary, setAiSummary] = useState<string | null>(defaultAiSummary ?? null);
  const [aiWarnings, setAiWarnings] = useState<string[]>(
    defaultAiWarnings ? [...defaultAiWarnings] : [],
  );
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (mode === "edit" && plan && plan.active_version) {
      setForm(
        formStateFromConfig(
          plan.name,
          plan.description ?? "",
          plan.risk_score,
          plan.risk_tier,
          plan.active_version.config,
        ),
      );
      setAiSummary(plan.ai_summary ?? null);
      setAiWarnings([]);
    } else {
      setForm({ ...EMPTY_FORM, ...(prefill ?? {}) });
      setAiSummary(defaultAiSummary ?? null);
      setAiWarnings(defaultAiWarnings ? [...defaultAiWarnings] : []);
    }
    setSubmitError(null);
  }, [open, mode, plan, prefill, defaultAiSummary, defaultAiWarnings]);

  const validation = useMemo(() => validateForm(form), [form]);
  const errorMap = useMemo(() => {
    const m: Record<string, string> = {};
    for (const e of validation.errors) m[String(e.field)] = e.message;
    return m;
  }, [validation]);

  const aiDraft = useMutation({
    mutationFn: () => RiskPlansApi.aiDraft({ prompt: aiPrompt.trim() }),
    onSuccess: (resp) => {
      const next = formStateFromConfig(
        resp.risk_plan.name,
        resp.risk_plan.description ?? "",
        resp.risk_plan.risk_score,
        resp.risk_plan.risk_tier,
        resp.risk_plan_version.config,
      );
      setForm(next);
      setAiSummary(resp.risk_plan.ai_summary ?? null);
      setAiWarnings([...resp.warnings]);
      setSubmitError(null);
    },
    onError: (e) =>
      setSubmitError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  const create = useMutation({
    mutationFn: () => {
      const source = defaultSource ?? "manual";
      const aiAttached = source === "ai_generated";
      const body: CreateRiskPlanRequest = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        risk_score: form.risk_score,
        risk_tier: form.risk_tier,
        source,
        source_run_id: defaultSourceRunId ?? undefined,
        source_evidence_type: defaultSourceEvidenceType ?? undefined,
        evidence_lineage: defaultEvidenceLineage,
        ai_generated: aiAttached,
        ai_summary: aiSummary,
        config: configFromFormState(form),
      };
      return RiskPlansApi.create(body);
    },
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: ["risk-plans"] });
      onSaved?.(saved);
      onOpenChange(false);
    },
    onError: (e) =>
      setSubmitError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  const editVersion = useMutation({
    mutationFn: () => {
      if (!plan) throw new Error("missing plan in edit mode");
      // First patch identity fields so name/description/score/tier track edits,
      // then post the new RiskPlanVersion (activated by default).
      return RiskPlansApi.patch(plan.risk_plan_id, {
        name: form.name.trim(),
        description: form.description.trim() || null,
        risk_score: form.risk_score,
        risk_tier: form.risk_tier,
        ai_summary: aiSummary,
      }).then(() =>
        RiskPlansApi.newVersion(plan.risk_plan_id, {
          config: configFromFormState(form),
          activate: true,
        }).then(() => RiskPlansApi.get(plan.risk_plan_id)),
      );
    },
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: ["risk-plans"] });
      void queryClient.invalidateQueries({
        queryKey: ["risk-plans", "detail", plan?.risk_plan_id],
      });
      onSaved?.(saved);
      onOpenChange(false);
    },
    onError: (e) =>
      setSubmitError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  const isEdit = mode === "edit";
  const submitting = create.isPending || editVersion.isPending;
  const canSave = validation.errors.length === 0 && !submitting;

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-w-2xl">
        <DrawerHeader>
          <DrawerTitle>
            {isEdit ? `Edit Risk Plan — ${plan?.name ?? ""}` : "Create Risk Plan"}
          </DrawerTitle>
          <DrawerDescription>
            {isEdit
              ? "Saving creates a new RiskPlanVersion and activates it. Existing references to old versions stay frozen."
              : "Drafts a new RiskPlan with an initial active RiskPlanVersion. AI may help, but you must save explicitly — AI never silently assigns."}
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-5">
          {!isEdit ? (
            <fieldset className="space-y-2 rounded border border-ai/40 bg-ai-subtle/40 p-3">
              <legend className="px-1 text-[11px] font-semibold uppercase tracking-wider text-ai">
                AI draft
              </legend>
              <p className="text-xs text-fg-muted">
                Describe what you want, in plain English. AI fills in the form below — you
                still review every field and click Save.
              </p>
              <TextField
                label="Prompt"
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                placeholder="e.g. balanced intraday plan that risks 1% per trade with 5 concurrent positions max"
              />
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  loading={aiDraft.isPending}
                  disabled={aiPrompt.trim().length < 4 || aiDraft.isPending}
                  leftIcon={<Sparkles className="h-3.5 w-3.5" aria-hidden="true" />}
                  onClick={() => aiDraft.mutate()}
                >
                  Generate draft
                </Button>
                {aiSummary ? (
                  <StatusBadge size="sm" tone="ai">
                    AI draft loaded
                  </StatusBadge>
                ) : null}
              </div>
              {aiSummary ? (
                <Banner severity="info" title="AI summary" message={aiSummary} />
              ) : null}
              {aiWarnings.length > 0 ? (
                <Banner
                  severity="warning"
                  title="AI raised warnings"
                  message={
                    <ul className="list-disc pl-4">
                      {aiWarnings.map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                    </ul>
                  }
                />
              ) : null}
            </fieldset>
          ) : null}

          {validation.warnings.length > 0 ? (
            <Banner
              severity="warning"
              title="Aggressive settings warning"
              message={
                <ul className="list-disc pl-4">
                  {validation.warnings.map((w, i) => (
                    <li key={i}>{w.message}</li>
                  ))}
                </ul>
              }
            />
          ) : null}

          <RiskPlanFormFields form={form} setForm={setForm} errors={errorMap} />

          {submitError ? (
            <Banner severity="danger" title="Could not save" message={submitError} />
          ) : null}
          {validation.errors.length > 0 ? (
            <Banner
              severity="danger"
              title="Fix validation errors before saving"
              message={
                <ul className="list-disc pl-4">
                  {validation.errors.map((e, i) => (
                    <li key={i}>{e.message}</li>
                  ))}
                </ul>
              }
            />
          ) : null}
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!canSave}
            loading={submitting}
            onClick={() => (isEdit ? editVersion.mutate() : create.mutate())}
          >
            {isEdit ? "Save new version" : "Save Risk Plan"}
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}
