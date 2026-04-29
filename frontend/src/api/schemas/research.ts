import { z } from "zod";

/** All research evidence types share a small core; payload-specific fields stay under passthrough. */
const baseEvidence = z
  .object({
    evidence_id: z.string().optional(),
    evidence_type: z.string(),
    strategy_id: z.string().optional(),
    strategy_version_id: z.string().optional(),
    name: z.string().optional(),
    created_at: z.string().optional(),
    succeeded: z.boolean().optional(),
    summary: z.record(z.unknown()).optional(),
    metrics: z.record(z.unknown()).optional(),
  })
  .passthrough();

export const ResearchEvidenceSchema = baseEvidence;
export type ResearchEvidence = z.infer<typeof ResearchEvidenceSchema>;

export const ResearchEvidenceListSchema = z.object({
  evidence: z.array(ResearchEvidenceSchema).default([]),
});
export type ResearchEvidenceList = z.infer<typeof ResearchEvidenceListSchema>;

/**
 * Evidence types returned by the backend, matching
 * backend/app/persistence/runtime_store.py:_RESEARCH_EVIDENCE_TYPES.
 */
export const EVIDENCE_TYPES = {
  CHART_LAB: "chart_lab_preview",
  BACKTEST: "backtest_run",
  SIM_LAB: "simulation_run",
  OPTIMIZATION: "optimization_run",
  WALK_FORWARD: "walk_forward_run",
  PROMOTION: "promotion_bundle",
} as const;
export type EvidenceTypeKey = keyof typeof EVIDENCE_TYPES;
export type EvidenceTypeValue = (typeof EVIDENCE_TYPES)[EvidenceTypeKey];
