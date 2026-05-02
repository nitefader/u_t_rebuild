import { z } from "zod";

/** TradingMode values per backend domain.trading_mode. Account-only metadata. */
export const TradingModeSchema = z.enum([
  "BROKER_PAPER",
  "BROKER_LIVE",
  "CHART_LAB_HISTORICAL",
  "CHART_LAB_LIVE_PREVIEW",
  "SIM_LAB_HISTORICAL",
  "SIM_LAB_LIVE_REPLAY",
]);
export type TradingMode = z.infer<typeof TradingModeSchema>;

export const BrokerAccountValidationStatusSchema = z.enum(["pending", "valid", "invalid"]);

export const BrokerAccountCredentialValidationStatusSchema = z.enum([
  "valid",
  "invalid",
  "mode_mismatch",
  "missing_credentials",
  "provider_unreachable",
]);

export const BrokerAccountDeletionStatusSchema = z.enum(["hard_deleted", "archived", "blocked"]);

/** Loose snapshot — operator UI surfaces only the fields it renders. */
export const BrokerAccountSnapshotSchema = z
  .object({
    account_id: z.string(),
    timestamp: z.string().nullable().optional(),
    equity: z.number().nullable().optional(),
    cash: z.number().nullable().optional(),
    buying_power: z.number().nullable().optional(),
    daytrading_buying_power: z.number().nullable().optional(),
    regt_buying_power: z.number().nullable().optional(),
    non_marginable_buying_power: z.number().nullable().optional(),
    multiplier: z.number().nullable().optional(),
    portfolio_value: z.number().nullable().optional(),
    long_market_value: z.number().nullable().optional(),
    short_market_value: z.number().nullable().optional(),
    initial_margin: z.number().nullable().optional(),
    maintenance_margin: z.number().nullable().optional(),
    last_maintenance_margin: z.number().nullable().optional(),
    last_equity: z.number().nullable().optional(),
    sma: z.number().nullable().optional(),
    daytrade_count: z.number().nullable().optional(),
    trade_suspended_by_user: z.boolean().nullable().optional(),
    transfers_blocked: z.boolean().nullable().optional(),
    crypto_status: z.string().nullable().optional(),
    currency: z.string().nullable().optional(),
    accrued_fees: z.number().nullable().optional(),
    pending_transfer_in: z.number().nullable().optional(),
    pending_transfer_out: z.number().nullable().optional(),
    pattern_day_trader: z.boolean().nullable().optional(),
    trading_blocked: z.boolean().nullable().optional(),
    account_blocked: z.boolean().nullable().optional(),
    status: z.string().nullable().optional(),
  })
  .passthrough();

export const BrokerSyncStateSchema = z
  .object({
    account_id: z.string(),
    is_stale: z.boolean(),
    stale_reason: z.string().nullable().optional(),
    last_sync_at: z.string().nullable().optional(),
    last_event_at: z.string().nullable().optional(),
    last_poll_sync_at: z.string().nullable().optional(),
    last_successful_sync_at: z.string().nullable().optional(),
  })
  .passthrough();
export type BrokerSyncState = z.infer<typeof BrokerSyncStateSchema>;

export const BrokerAccountSchema = z.object({
  id: z.string(),
  display_name: z.string(),
  provider: z.string(),
  mode: TradingModeSchema,
  external_account_id: z.string().nullable().optional(),
  credentials_ref: z.string(),
  needs_credentials: z.boolean(),
  validation_status: BrokerAccountValidationStatusSchema,
  last_account_snapshot: BrokerAccountSnapshotSchema.nullable().optional(),
  broker_sync_freshness: BrokerSyncStateSchema.nullable().optional(),
  // M11 Guardian Assignment — Account-scoped Deployment that pre-authorizes
  // adoption of orphaned / owner-down positions. Optional; backend ships
  // null when no Guardian set. `guardian_deployment_name` is the readable
  // label per the AGENTS.md "Human-Readable Frontend Data Rule".
  guardian_deployment_id: z.string().nullable().optional(),
  guardian_deployment_name: z.string().nullable().optional(),
  created_at: z.string(),
  is_archived: z.boolean(),
  archived_at: z.string().nullable().optional(),
});
export type BrokerAccount = z.infer<typeof BrokerAccountSchema>;

export const BrokerAccountListResponseSchema = z.object({
  accounts: z.array(BrokerAccountSchema),
});
export type BrokerAccountListResponse = z.infer<typeof BrokerAccountListResponseSchema>;

export const BrokerAccountResponseSchema = z.object({
  account: BrokerAccountSchema,
  already_exists: z.boolean().default(false),
});

export const BrokerAccountCredentialUpdateResponseSchema = z.object({
  account: BrokerAccountSchema.nullable(),
  validation_status: BrokerAccountCredentialValidationStatusSchema,
  message: z.string(),
});

export const BrokerAccountDeletionResponseSchema = z.object({
  account_id: z.string(),
  status: BrokerAccountDeletionStatusSchema,
  message: z.string(),
  blockers: z.array(z.string()).default([]),
  archived_account: BrokerAccountSchema.nullable().optional(),
});

export const CreateBrokerAccountRequestSchema = z.object({
  display_name: z.string().min(1),
  provider: z.string().min(1).default("alpaca"),
  mode: TradingModeSchema,
  api_key: z.string().min(1),
  api_secret: z.string().min(1),
});
export type CreateBrokerAccountRequest = z.infer<typeof CreateBrokerAccountRequestSchema>;

export const UpdateBrokerAccountDetailsRequestSchema = z.object({
  display_name: z.string().min(1),
});

export const ReplaceBrokerAccountCredentialsRequestSchema = z.object({
  api_key: z.string().min(1),
  api_secret: z.string().min(1),
});

export const DeleteBrokerAccountRequestSchema = z.object({
  confirm_display_name: z.string().min(1),
  confirm_mode: TradingModeSchema,
});
