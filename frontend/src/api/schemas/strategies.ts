import { z } from "zod";

export const StrategyStatusSchema = z.enum(["draft", "active", "deprecated"]);
export const StrategyVersionStatusSchema = z.enum(["draft", "frozen"]);

export const ConditionOperatorSchema = z.enum([
  "gt",
  "greater_than",
  "gte",
  "lt",
  "less_than",
  "lte",
  "eq",
  "cross_above",
  "cross_below",
]);

export const CandidateSideSchema = z.enum(["long", "short"]);
export const IntentTypeSchema = z.enum(["entry", "exit"]);

export const ConditionNodeSchema: z.ZodTypeAny = z
  .object({
    kind: z.literal("condition"),
    left_feature: z.string(),
    operator: ConditionOperatorSchema,
    right_feature: z.string().nullable().optional(),
    right_value: z.union([z.number(), z.string(), z.boolean()]).nullable().optional(),
    label: z.string().nullable().optional(),
  })
  .passthrough();

// Recursive — children can be ConditionNode or ConditionGroup.
const conditionExpression: z.ZodTypeAny = z.lazy(() =>
  z.union([ConditionNodeSchema, ConditionGroupSchema]),
);

export const ConditionGroupSchema: z.ZodTypeAny = z
  .object({
    kind: z.literal("group"),
    operator: z.enum(["all", "any", "and", "or"]),
    children: z.array(conditionExpression).min(1),
    label: z.string().nullable().optional(),
  })
  .passthrough();

export const SignalRuleSchema = z
  .object({
    name: z.string(),
    side: CandidateSideSchema,
    intent_type: IntentTypeSchema,
    // condition is optional now — exit rules may carry only a logical_exit_rule
    // (per the LogicalExitRule slice; doctrine: time/bars/session/feature/hybrid
    // exits all live under SignalPlan.intent=logical_exit, never as a sibling
    // top-level intent). Backend validates that at least one of (condition,
    // logical_exit_rule) is set per SignalRule.
    condition: conditionExpression.nullable().optional(),
    logical_exit_rule: z
      .object({ kind: z.string() })
      .passthrough()
      .nullable()
      .optional(),
    stop_candidate_feature: z.string().nullable().optional(),
    target_candidate_feature: z.string().nullable().optional(),
  })
  .passthrough();

export const StrategyVersionPayloadSchema = z
  .object({
    id: z.string(),
    strategy_id: z.string(),
    version: z.number(),
    name: z.string(),
    description: z.string().nullable().optional(),
    feature_refs: z.array(z.string()).default([]),
    entry_rules: z.array(SignalRuleSchema).default([]),
    exit_rules: z.array(SignalRuleSchema).default([]),
    tags: z.array(z.string()).default([]),
    created_at: z.string(),
  })
  .passthrough();
export type StrategyVersionPayload = z.infer<typeof StrategyVersionPayloadSchema>;

export const StrategyVersionRecordSchema = z
  .object({
    strategy_version_id: z.string(),
    strategy_id: z.string(),
    version: z.number(),
    status: z.string(),
    payload: StrategyVersionPayloadSchema,
    frozen_at: z.string().nullable().optional(),
    frozen_by: z.string().nullable().optional(),
    created_at: z.string(),
  })
  .passthrough();
export type StrategyVersionRecord = z.infer<typeof StrategyVersionRecordSchema>;

export const StrategySchema = z
  .object({
    strategy_id: z.string(),
    name: z.string(),
    description: z.string().nullable().optional(),
    tags: z.array(z.string()).default([]),
    status: z.string(),
    created_at: z.string(),
    latest_version_id: z.string().nullable().optional(),
    frozen_version_ids: z.array(z.string()).default([]),
    version_count: z.number().default(0),
  })
  .passthrough();
export type Strategy = z.infer<typeof StrategySchema>;

export const StrategyResponseSchema = z
  .object({
    strategy: StrategySchema,
    versions: z.array(StrategyVersionRecordSchema).default([]),
  })
  .passthrough();
export type StrategyResponse = z.infer<typeof StrategyResponseSchema>;

export const StrategyListResponseSchema = z
  .object({
    strategies: z.array(StrategySchema).default([]),
  })
  .passthrough();
export type StrategyListResponse = z.infer<typeof StrategyListResponseSchema>;

export const StrategyWriteRequestSchema = z.object({
  name: z.string().min(1).max(120),
  description: z.string().nullable().optional(),
  tags: z.array(z.string()).default([]),
});
export type StrategyWriteRequest = z.infer<typeof StrategyWriteRequestSchema>;
