import { z } from "zod";

// ------------------------------------------------------------------
// Enums
// ------------------------------------------------------------------

export const DirectionV4Schema = z.enum(["long", "short", "both"]);
export type DirectionV4 = z.infer<typeof DirectionV4Schema>;

export const StopModeV4Schema = z.enum(["simple", "expression"]);
export type StopModeV4 = z.infer<typeof StopModeV4Schema>;

export const StopSimpleTypeV4Schema = z.enum(["%", "ATR", "$", "R"]);
export type StopSimpleTypeV4 = z.infer<typeof StopSimpleTypeV4Schema>;

export const LegKindV4Schema = z.enum(["target", "runner"]);
export type LegKindV4 = z.infer<typeof LegKindV4Schema>;

export const LegTargetTypeV4Schema = z.enum([
  "%",
  "ATR",
  "$",
  "R",
  "feature",
  "trail-ATR",
  "trail-%",
  "trail-$",
]);
export type LegTargetTypeV4 = z.infer<typeof LegTargetTypeV4Schema>;

export const OnFillActionKindV4Schema = z.enum([
  "be_exact",
  "be_plus",
  "be_minus",
  "tighten_atr",
  "tighten_pct",
  "leave",
]);
export type OnFillActionKindV4 = z.infer<typeof OnFillActionKindV4Schema>;

export const LogicalExitTemplateV4Schema = z.enum([
  "no_progress",
  "opposite_cross",
  "session_end",
  "bars_since",
]);
export type LogicalExitTemplateV4 = z.infer<typeof LogicalExitTemplateV4Schema>;

// ------------------------------------------------------------------
// Identity
// ------------------------------------------------------------------

export const IdentityDraftSchema = z.object({
  tags: z.array(z.string()).default([]),
  direction: DirectionV4Schema.default("both"),
});
export type IdentityDraft = z.infer<typeof IdentityDraftSchema>;

// ------------------------------------------------------------------
// Draft models (write)
// ------------------------------------------------------------------

export const StrategyEntryV4DraftSchema = z.object({
  expression_text: z.string(),
});
export type StrategyEntryV4Draft = z.infer<typeof StrategyEntryV4DraftSchema>;

export const VariableKindV4Schema = z.enum(["expression", "timeframe"]);
export type VariableKindV4 = z.infer<typeof VariableKindV4Schema>;

export const StrategyVariableV4DraftSchema = z.object({
  name: z.string().regex(/^[a-z_][a-z0-9_]*$/),
  expression_text: z.string(),
  kind: VariableKindV4Schema.default("expression"),
});
export type StrategyVariableV4Draft = z.infer<typeof StrategyVariableV4DraftSchema>;

export const OnFillActionV4DraftSchema = z.object({
  kind: OnFillActionKindV4Schema,
  offset_value: z.number().nullable().optional(),
});
export type OnFillActionV4Draft = z.infer<typeof OnFillActionV4DraftSchema>;

export const StrategyStopV4DraftSchema = z.object({
  id: z.string(),
  mode: StopModeV4Schema,
  scope: z.string().default("all"),
  simple_type: StopSimpleTypeV4Schema.nullable().optional(),
  simple_value: z.number().nullable().optional(),
  expression_text: z.string().nullable().optional(),
  feature_requirements: z.array(z.string()).optional(),
});
export type StrategyStopV4Draft = z.infer<typeof StrategyStopV4DraftSchema>;

export const StrategyLegV4DraftSchema = z.object({
  id: z.string(),
  position: z.number().int().min(1),
  kind: LegKindV4Schema,
  size_pct: z.number().gt(0).lte(1),
  target_type: LegTargetTypeV4Schema,
  target_value: z.number().nullable().optional(),
  on_fill_action: OnFillActionV4DraftSchema,
});
export type StrategyLegV4Draft = z.infer<typeof StrategyLegV4DraftSchema>;

export const StrategyLogicalExitV4DraftSchema = z.object({
  id: z.string(),
  template_id: LogicalExitTemplateV4Schema,
  params: z.record(z.unknown()).default({}),
});
export type StrategyLogicalExitV4Draft = z.infer<typeof StrategyLogicalExitV4DraftSchema>;

export const StrategyVersionV4DraftSchema = z.object({
  name: z.string().min(1),
  description: z.string().nullable().optional(),
  identity: IdentityDraftSchema.default({}),
  default_strategy_controls_version_id: z.string().nullable().optional(),
  default_execution_plan_version_id: z.string().nullable().optional(),
  timeframe_aliases: z.record(z.string()).optional().default({}),
  variables: z.array(StrategyVariableV4DraftSchema).default([]),
  entries: z.object({
    long: StrategyEntryV4DraftSchema.nullable().optional(),
    short: StrategyEntryV4DraftSchema.nullable().optional(),
  }),
  stops: z.array(StrategyStopV4DraftSchema),
  legs: z.array(StrategyLegV4DraftSchema).default([]),
  logical_exits: z
    .object({
      long: z.array(StrategyLogicalExitV4DraftSchema).default([]),
      short: z.array(StrategyLogicalExitV4DraftSchema).default([]),
    })
    .default({ long: [], short: [] }),
});
export type StrategyVersionV4Draft = z.infer<typeof StrategyVersionV4DraftSchema>;

// ------------------------------------------------------------------
// Domain (read) models
// ------------------------------------------------------------------

export const ValidationStatusV4Schema = z.object({
  valid: z.boolean(),
  errors: z.array(z.string()).default([]),
  warnings: z.array(z.string()).default([]),
});
export type ValidationStatusV4 = z.infer<typeof ValidationStatusV4Schema>;

export const StrategyVersionV4Schema = z
  .object({
    id: z.string(),
    strategy_v4_id: z.string().optional(),
    version: z.number().int(),
    name: z.string(),
    description: z.string().nullable().optional(),
    identity: IdentityDraftSchema,
    default_strategy_controls_version_id: z.string().nullable().optional(),
    default_execution_plan_version_id: z.string().nullable().optional(),
    timeframe_aliases: z.record(z.string()).optional().default({}),
    variables: z.array(
      z.object({
        name: z.string(),
        expression_text: z.string(),
        kind: VariableKindV4Schema.default("expression"),
        feature_requirements: z.array(z.string()).default([]),
      }),
    ).default([]),
    entries: z.object({
      long: z
        .object({ expression_text: z.string(), feature_requirements: z.array(z.string()).default([]) })
        .nullable()
        .optional(),
      short: z
        .object({ expression_text: z.string(), feature_requirements: z.array(z.string()).default([]) })
        .nullable()
        .optional(),
    }),
    stops: z.array(StrategyStopV4DraftSchema).default([]),
    legs: z.array(StrategyLegV4DraftSchema).default([]),
    logical_exits: z
      .object({
        long: z.array(StrategyLogicalExitV4DraftSchema).default([]),
        short: z.array(StrategyLogicalExitV4DraftSchema).default([]),
      })
      .default({ long: [], short: [] }),
    feature_requirements: z.array(z.string()).default([]),
    validation_status: ValidationStatusV4Schema,
    created_at: z.string().optional(),
  })
  .passthrough();
export type StrategyVersionV4 = z.infer<typeof StrategyVersionV4Schema>;

// ------------------------------------------------------------------
// Validate draft response
// ------------------------------------------------------------------

export const ValidateDraftResponseSchema = z.object({
  validation_status: ValidationStatusV4Schema,
});
export type ValidateDraftResponse = z.infer<typeof ValidateDraftResponseSchema>;

// ------------------------------------------------------------------
// Expression API schemas
// ------------------------------------------------------------------

export const ExpressionValidateResultSchema = z.object({
  valid: z.boolean(),
  errors: z
    .array(
      z.object({
        level: z.string(),
        message: z.string(),
        line: z.number().nullable().optional(),
        col: z.number().nullable().optional(),
      }),
    )
    .default([]),
  warnings: z
    .array(
      z.object({
        level: z.string(),
        message: z.string(),
        line: z.number().nullable().optional(),
        col: z.number().nullable().optional(),
      }),
    )
    .default([]),
  feature_requirements: z
    .array(
      z.object({
        key: z.string(),
        name: z.string(),
        namespace: z.string().nullable().optional(),
        timeframe: z.string().nullable().optional(),
        args: z.array(z.number()).default([]),
      }),
    )
    .default([]),
  variables_used: z.array(z.string()).default([]),
});
export type ExpressionValidateResult = z.infer<typeof ExpressionValidateResultSchema>;

export const CatalogEntrySchema = z.object({
  key: z.string(),
  name: z.string(),
  namespace: z.string(),
  timeframe_bound: z.boolean(),
  arity: z.number().int(),
  arg_names: z.array(z.string()).default([]),
  arg_defaults: z.array(z.unknown()).default([]),
  return_type: z.string(),
  description: z.string(),
  category: z.string(),
});
export type CatalogEntry = z.infer<typeof CatalogEntrySchema>;

export const FeaturesResponseSchema = z.object({
  features: z.array(CatalogEntrySchema).default([]),
});

// ------------------------------------------------------------------
// AI provider enum (mirrors AIProvider StrEnum on backend)
// ------------------------------------------------------------------

export const AIProviderSchema = z.enum(["groq", "claude", "openai", "codex", "future"]);
export type AIProvider = z.infer<typeof AIProviderSchema>;

// ------------------------------------------------------------------
// AI seed-fill response
// ------------------------------------------------------------------

export const AISeedFillResponseSchema = z.object({
  draft: StrategyVersionV4DraftSchema,
  validation_status: ValidationStatusV4Schema,
  provider_used: AIProviderSchema,
  model_used: z.string(),
  raw_response_excerpt: z.string(),
  notes: z.array(z.string()).default([]),
});
export type AISeedFillResponse = z.infer<typeof AISeedFillResponseSchema>;
