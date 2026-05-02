import { z } from "zod";
import { BrokerAccountSnapshotSchema, BrokerSyncStateSchema } from "./accounts";

/**
 * RuntimeStatus values from backend.app.runtime.models.RuntimeStatus.
 *
 * Permissive `z.string()` instead of `z.enum(...)` so the typed client
 * doesn't reject responses when the Coordinator adds new status
 * values backend-side. The UI matches on known strings and falls
 * through to a neutral tone for anything else.
 */
export const RuntimeStatusSchema = z.string();
export type RuntimeStatus = z.infer<typeof RuntimeStatusSchema>;

/** Same rationale as RuntimeStatusSchema — additive backend values must not break the drawer. */
export const InternalOrderStatusSchema = z.string();

export const ControlPlaneStateSchema = z
  .object({
    system_recovery_active: z.boolean(),
    global_kill_active: z.boolean(),
    paused_account_ids: z.array(z.string()).default([]),
    paused_deployment_ids: z.array(z.string()).default([]),
  })
  .passthrough();

export const AccountSummarySchema = z
  .object({
    account_id: z.string(),
    snapshot: BrokerAccountSnapshotSchema.nullable().optional(),
    sync_state: BrokerSyncStateSchema.nullable().optional(),
    open_orders_count: z.number().default(0),
    positions_count: z.number().default(0),
    is_paused: z.boolean().default(false),
    is_killed: z.boolean().default(false),
  })
  .passthrough();
export type AccountSummary = z.infer<typeof AccountSummarySchema>;

export const DeploymentSummarySchema = z
  .object({
    deployment_id: z.string(),
    status: RuntimeStatusSchema,
    is_running: z.boolean(),
    account_id: z.string().nullable().optional(),
    strategy_version_id: z.string().nullable().optional(),
    strategy_version: z.number().nullable().optional(),
  })
  .passthrough();
export type DeploymentSummary = z.infer<typeof DeploymentSummarySchema>;

export const GovernorDecisionSchema = z
  .object({
    approved: z.boolean(),
    reason: z.string().optional(),
    rule_id: z.string().nullable().optional(),
    decided_at: z.string().nullable().optional(),
    projected_state: z.record(z.unknown()).optional(),
  })
  .passthrough();
export type GovernorDecision = z.infer<typeof GovernorDecisionSchema>;

export const ResearchEvidenceSummarySchema = z
  .object({
    evidence_type: z.string(),
    count: z.number(),
    latest_created_at: z.string().nullable().optional(),
  })
  .passthrough();

export const RuntimeOverviewSchema = z
  .object({
    system_recovery_active: z.boolean(),
    global_kill_active: z.boolean(),
    control_state: ControlPlaneStateSchema,
    broker_accounts: z.array(AccountSummarySchema).default([]),
    deployments: z.array(DeploymentSummarySchema).default([]),
    stale_sync_accounts: z.array(BrokerSyncStateSchema).default([]),
    blocked_deployments: z.array(DeploymentSummarySchema).default([]),
    open_orders_count: z.number().default(0),
    open_positions_count: z.number().default(0),
    latest_governor_decisions: z.array(GovernorDecisionSchema).default([]),
    latest_broker_sync_timestamp: z.string().nullable().optional(),
    latest_runtime_event_timestamp: z.string().nullable().optional(),
    research_evidence_summary: z.array(ResearchEvidenceSummarySchema).default([]),
  })
  .passthrough();
export type RuntimeOverview = z.infer<typeof RuntimeOverviewSchema>;

export const InternalOrderSchema = z
  .object({
    order_id: z.string(),
    client_order_id: z.string(),
    account_id: z.string(),
    symbol: z.string(),
    side: z.string(),
    quantity: z.number(),
    filled_quantity: z.number().default(0),
    status: InternalOrderStatusSchema,
    intent: z.string().optional(),
    deployment_id: z.string().nullable().optional(),
    signal_plan_id: z.string().nullable().optional(),
    opening_signal_plan_id: z.string().nullable().optional(),
    position_lineage_id: z.string().nullable().optional(),
    created_at: z.string().nullable().optional(),
    updated_at: z.string().nullable().optional(),
    canceled_at: z.string().nullable().optional(),
    reason: z.string().nullable().optional(),
  })
  .passthrough();
export type InternalOrder = z.infer<typeof InternalOrderSchema>;

export const BrokerOrderMappingSchema = z
  .object({
    internal_order_id: z.string().optional(),
    broker_order_id: z.string().optional(),
    broker_account_id: z.string().optional(),
    submitted_at: z.string().nullable().optional(),
  })
  .passthrough();

export const BrokerFillUpdateEventSchema = z
  .object({
    broker_fill_id: z.string().optional(),
    broker_order_id: z.string().optional(),
    symbol: z.string().optional(),
    side: z.string().optional(),
    fill_quantity: z.number().optional(),
    fill_price: z.number().optional(),
    timestamp: z.string().optional(),
  })
  .passthrough();

export const OrderDetailSchema = z
  .object({
    internal_order: InternalOrderSchema,
    broker_mapping: BrokerOrderMappingSchema.nullable().optional(),
    broker_account_id: z.string(),
    deployment_id: z.string().nullable().optional(),
    strategy_version_id: z.string().nullable().optional(),
    broker_order_id: z.string().nullable().optional(),
    broker_status: z.string().default("unknown_stale"),
    broker_sync_timestamp: z.string().nullable().optional(),
    fills: z.array(BrokerFillUpdateEventSchema).default([]),
    trade_summary: z.record(z.unknown()).default({}),
  })
  .passthrough();
export type OrderDetail = z.infer<typeof OrderDetailSchema>;

export const BrokerOpenOrderSnapshotSchema = z
  .object({
    broker_order_id: z.string(),
    account_id: z.string(),
    client_order_id: z.string(),
    symbol: z.string(),
    side: z.string().nullable().optional(),
    qty: z.number().nullable().optional(),
    filled_qty: z.number().nullable().optional(),
    status: z.string(),
    order_type: z.string().nullable().optional(),
    limit_price: z.number().nullable().optional(),
    stop_price: z.number().nullable().optional(),
    timestamp: z.string().nullable().optional(),
  })
  .passthrough();
export type BrokerOpenOrderSnapshot = z.infer<typeof BrokerOpenOrderSnapshotSchema>;

/**
 * Real payload shipping today uses `qty` + `avg_entry_price`. Earlier
 * draft schemas keyed on `quantity` + `average_entry_price`. Both
 * spellings are accepted (optional) so the table renders whichever
 * the backend ships.
 */
export const BrokerPositionSnapshotSchema = z
  .object({
    account_id: z.string(),
    symbol: z.string(),
    qty: z.number().nullable().optional(),
    quantity: z.number().nullable().optional(),
    avg_entry_price: z.number().nullable().optional(),
    average_entry_price: z.number().nullable().optional(),
    side: z.string().nullable().optional(),
    market_value: z.number().nullable().optional(),
    unrealized_pl: z.number().nullable().optional(),
    status: z.string().nullable().optional(),
    timestamp: z.string().nullable().optional(),
    deployment_id: z.string().nullable().optional(),
    deployment_name: z.string().nullable().optional(),
    strategy_id: z.string().nullable().optional(),
    opening_signal_plan_id: z.string().nullable().optional(),
    position_lineage_id: z.string().nullable().optional(),
    // M2 (HARD.MD P0-2) — unmanaged-position classification flag (true when the
    // position has no matched lineage and is not Guardian-adopted).
    unmanaged_broker_position: z.boolean().nullable().optional(),
    // M11 Guardian lineage extension. All optional; backend may ship any
    // subset. The frontend surfaces badges only when the relevant fields
    // are present, so the row stays clean while M11 backend is in flight.
    adoption_status: z
      .enum(["managed", "unmanaged", "adopted_by_guardian"])
      .nullable()
      .optional(),
    adoption_reason: z
      .enum(["owner_unknown", "owner_deployment_down_unprotected"])
      .nullable()
      .optional(),
    original_owner_deployment_id: z.string().nullable().optional(),
    original_owner_deployment_name: z.string().nullable().optional(),
    owner_deployment_healthy: z.boolean().nullable().optional(),
    owner_self_protected: z.boolean().nullable().optional(),
  })
  .passthrough();
export type BrokerPositionSnapshot = z.infer<typeof BrokerPositionSnapshotSchema>;

export const InternalOrderLedgerSummarySchema = z
  .object({
    total_count: z.number().default(0),
    open_count: z.number().default(0),
    terminal_count: z.number().default(0),
    by_status: z.record(z.number()).default({}),
    by_intent: z.record(z.number()).default({}),
  })
  .passthrough();

/**
 * T-5 Bracket Program: operator-visible protection status on each open
 * position. ``z.string()`` instead of ``z.enum`` so additive backend
 * status values (e.g. future `protection_failing`) don't break the
 * UI — the table renders a neutral tone for unknown strings.
 */
export const OperatorPositionViewSchema = z
  .object({
    snapshot: BrokerPositionSnapshotSchema,
    protection_status: z.string().default("unknown"),
    protective_order_count: z.number().default(0),
  })
  .passthrough();
export type OperatorPositionView = z.infer<typeof OperatorPositionViewSchema>;

export const AccountOperationsSchema = z
  .object({
    account_id: z.string(),
    broker_account_snapshot: BrokerAccountSnapshotSchema.nullable().optional(),
    broker_sync_freshness: BrokerSyncStateSchema.nullable().optional(),
    open_broker_orders: z.array(BrokerOpenOrderSnapshotSchema).default([]),
    internal_order_ledger_summary: InternalOrderLedgerSummarySchema,
    positions: z.array(BrokerPositionSnapshotSchema).default([]),
    position_views: z.array(OperatorPositionViewSchema).default([]),
    deployments: z.array(DeploymentSummarySchema).default([]),
    is_paused: z.boolean().default(false),
    is_killed: z.boolean().default(false),
  })
  .passthrough();
export type AccountOperations = z.infer<typeof AccountOperationsSchema>;

export const FlattenRequestResponseSchema = z
  .object({
    accepted: z.boolean(),
    status: z.string(),
    reason: z.string(),
    scope: z.string(),
    target_id: z.string(),
    result: z.unknown().nullable().optional(),
  })
  .passthrough();
export type FlattenRequestResponse = z.infer<typeof FlattenRequestResponseSchema>;

export const ControlCommandResponseSchema = z
  .object({
    accepted: z.boolean().default(true),
    action: z.string(),
    scope: z.string(),
    target_id: z.string().nullable().optional(),
    message: z.string(),
  })
  .passthrough();
export type ControlCommandResponse = z.infer<typeof ControlCommandResponseSchema>;
