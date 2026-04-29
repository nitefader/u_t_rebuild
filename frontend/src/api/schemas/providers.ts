import { z } from "zod";

// ---------- Market Data Providers ----------

export const ServicePurposeSchema = z.enum([
  "live_streaming",
  "test_streaming",
  "batch_historical",
  "signal_preview",
  "runtime_trading",
]);
export type ServicePurpose = z.infer<typeof ServicePurposeSchema>;

export const MarketDataValidationStatusSchema = z.enum([
  "valid",
  "invalid",
  "missing_credentials",
  "provider_unreachable",
  "unsupported_provider",
  "disabled",
]);

export const MarketDataServiceRecordSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    provider: z.string(),
    service_type: z.string(),
    status: z.string(),
    is_default: z.boolean(),
    default_for: z.array(ServicePurposeSchema).default([]),
    credentials_ref: z.string().nullable().optional(),
    has_api_key: z.boolean().default(false),
    has_api_secret: z.boolean().default(false),
    validation_status: MarketDataValidationStatusSchema.nullable().optional(),
    validation_message: z.string().nullable().optional(),
    last_validated_at: z.string().nullable().optional(),
    capabilities: z.record(z.unknown()).optional(),
    capability_notes: z.array(z.string()).default([]),
    created_at: z.string(),
    updated_at: z.string(),
    disabled_at: z.string().nullable().optional(),
  })
  .passthrough();
export type MarketDataServiceRecord = z.infer<typeof MarketDataServiceRecordSchema>;

export const MarketDataServiceListSchema = z.object({
  services: z.array(MarketDataServiceRecordSchema),
});
export type MarketDataServiceList = z.infer<typeof MarketDataServiceListSchema>;

export const MarketDataServiceDeletionResponseSchema = z.object({
  service_id: z.string(),
  message: z.string(),
});
export type MarketDataServiceDeletionResponse = z.infer<typeof MarketDataServiceDeletionResponseSchema>;

export const MarketDataProviderSchema = z.enum(["alpaca", "yahoo"]);
export type MarketDataProvider = z.infer<typeof MarketDataProviderSchema>;

export const MarketDataServiceWriteSchema = z.object({
  name: z.string().min(1),
  provider: MarketDataProviderSchema,
  api_key: z.string().nullable().optional(),
  api_secret: z.string().nullable().optional(),
});
export type MarketDataServiceWrite = z.infer<typeof MarketDataServiceWriteSchema>;

// ---------- AI Providers ----------

export const AIProviderSchema = z.enum(["groq", "claude", "openai", "codex", "future"]);
export type AIProvider = z.infer<typeof AIProviderSchema>;

export const AIProviderStatusSchema = z.enum(["draft", "valid", "invalid", "disabled"]);
export const AIValidationStatusSchema = z.enum([
  "valid",
  "invalid",
  "missing_credentials",
  "unsupported_provider",
  "disabled",
]);
export const AICapabilityLabelSchema = z.enum(["fast", "reasoning", "coding", "general", "unknown"]);

export const AIServiceRecordSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    provider: AIProviderSchema,
    service_type: z.string(),
    status: AIProviderStatusSchema,
    is_default: z.boolean(),
    credentials_ref: z.string().nullable().optional(),
    has_api_key: z.boolean(),
    capability_label: AICapabilityLabelSchema,
    validation_status: AIValidationStatusSchema.nullable().optional(),
    validation_message: z.string().nullable().optional(),
    last_validated_at: z.string().nullable().optional(),
    created_at: z.string(),
    updated_at: z.string(),
    disabled_at: z.string().nullable().optional(),
  })
  .passthrough();
export type AIServiceRecord = z.infer<typeof AIServiceRecordSchema>;

export const AIServiceListSchema = z.object({
  services: z.array(AIServiceRecordSchema),
});
export type AIServiceList = z.infer<typeof AIServiceListSchema>;

export const AIServiceDeletionResponseSchema = z.object({
  service_id: z.string(),
  message: z.string(),
});

export const AIServiceWriteSchema = z.object({
  name: z.string().min(1),
  provider: AIProviderSchema,
  api_key: z.string().nullable().optional(),
  capability_label: AICapabilityLabelSchema.default("unknown"),
});
export type AIServiceWrite = z.infer<typeof AIServiceWriteSchema>;
