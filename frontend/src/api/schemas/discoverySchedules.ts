import { z } from "zod";

export const DiscoveryScheduleTargetKindSchema = z.enum(["screener_run", "watchlist_refresh"]);
export type DiscoveryScheduleTargetKind = z.infer<typeof DiscoveryScheduleTargetKindSchema>;

export const DiscoveryScheduleCadenceSchema = z.enum(["every_n_minutes", "daily", "weekly"]);
export type DiscoveryScheduleCadence = z.infer<typeof DiscoveryScheduleCadenceSchema>;

export const DiscoveryScheduleStatusSchema = z.enum(["active", "paused", "archived"]);
export type DiscoveryScheduleStatus = z.infer<typeof DiscoveryScheduleStatusSchema>;

export const DiscoveryScheduleExecutionStatusSchema = z.enum([
  "running",
  "completed",
  "failed",
  "blocked",
]);
export type DiscoveryScheduleExecutionStatus = z.infer<typeof DiscoveryScheduleExecutionStatusSchema>;

export const DiscoveryScheduleTriggerSchema = z.enum(["due", "run_now"]);
export const DiscoveryScheduleApprovalPolicySchema = z.enum(["operator_review", "auto_snapshot"]);
export type DiscoveryScheduleApprovalPolicy = z.infer<typeof DiscoveryScheduleApprovalPolicySchema>;

export const DiscoveryScheduleSchema = z
  .object({
    schedule_id: z.string(),
    name: z.string(),
    target_kind: DiscoveryScheduleTargetKindSchema,
    screener_id: z.string().nullable().optional(),
    screener_version_id: z.string().nullable().optional(),
    watchlist_id: z.string().nullable().optional(),
    cadence: DiscoveryScheduleCadenceSchema,
    interval_minutes: z.number().nullable().optional(),
    time_of_day: z.string().nullable().optional(),
    weekdays: z.array(z.number()).default([0, 1, 2, 3, 4]),
    timezone_name: z.string().default("America/New_York"),
    session_start: z.string().nullable().optional(),
    session_end: z.string().nullable().optional(),
    approval_policy: DiscoveryScheduleApprovalPolicySchema.default("operator_review"),
    enabled: z.boolean().default(true),
    status: DiscoveryScheduleStatusSchema.default("active"),
    created_at: z.string(),
    updated_at: z.string(),
    last_attempt_at: z.string().nullable().optional(),
    last_success_at: z.string().nullable().optional(),
    next_run_at: z.string().nullable().optional(),
    last_status: DiscoveryScheduleExecutionStatusSchema.nullable().optional(),
    last_error: z.string().nullable().optional(),
    last_screener_run_id: z.string().nullable().optional(),
    last_watchlist_snapshot_id: z.string().nullable().optional(),
    execution_count: z.number().int().default(0),
    audit_events: z.array(z.record(z.unknown())).default([]),
  })
  .passthrough();
export type DiscoverySchedule = z.infer<typeof DiscoveryScheduleSchema>;

export const DiscoveryScheduleExecutionSchema = z
  .object({
    execution_id: z.string(),
    schedule_id: z.string(),
    schedule_name: z.string(),
    target_kind: DiscoveryScheduleTargetKindSchema,
    trigger: DiscoveryScheduleTriggerSchema,
    started_at: z.string(),
    completed_at: z.string().nullable().optional(),
    status: DiscoveryScheduleExecutionStatusSchema,
    screener_run_id: z.string().nullable().optional(),
    watchlist_snapshot_id: z.string().nullable().optional(),
    added_symbols: z.array(z.string()).default([]),
    removed_symbols: z.array(z.string()).default([]),
    stayed_symbols: z.array(z.string()).default([]),
    error: z.string().nullable().optional(),
    audit_events: z.array(z.record(z.unknown())).default([]),
  })
  .passthrough();
export type DiscoveryScheduleExecution = z.infer<typeof DiscoveryScheduleExecutionSchema>;

export const DiscoveryScheduleListResponseSchema = z
  .object({
    schedules: z.array(DiscoveryScheduleSchema).default([]),
  })
  .passthrough();
export type DiscoveryScheduleListResponse = z.infer<typeof DiscoveryScheduleListResponseSchema>;

export const DiscoveryScheduleExecutionListResponseSchema = z
  .object({
    executions: z.array(DiscoveryScheduleExecutionSchema).default([]),
  })
  .passthrough();
export type DiscoveryScheduleExecutionListResponse = z.infer<typeof DiscoveryScheduleExecutionListResponseSchema>;

export const DiscoveryScheduleWriteRequestSchema = z.object({
  name: z.string().min(1).max(120),
  target_kind: DiscoveryScheduleTargetKindSchema,
  screener_id: z.string().nullable().optional(),
  screener_version_id: z.string().nullable().optional(),
  watchlist_id: z.string().nullable().optional(),
  cadence: DiscoveryScheduleCadenceSchema.default("daily"),
  interval_minutes: z.number().int().min(1).max(720).nullable().optional(),
  time_of_day: z.string().nullable().optional(),
  weekdays: z.array(z.number()).default([0, 1, 2, 3, 4]),
  timezone_name: z.string().default("America/New_York"),
  session_start: z.string().nullable().optional(),
  session_end: z.string().nullable().optional(),
  approval_policy: DiscoveryScheduleApprovalPolicySchema.default("operator_review"),
  enabled: z.boolean().default(true),
});
export type DiscoveryScheduleWriteRequest = z.infer<typeof DiscoveryScheduleWriteRequestSchema>;

export const DiscoverySchedulePatchRequestSchema = z
  .object({
    name: z.string().min(1).max(120).nullable().optional(),
    cadence: DiscoveryScheduleCadenceSchema.nullable().optional(),
    interval_minutes: z.number().int().min(1).max(720).nullable().optional(),
    time_of_day: z.string().nullable().optional(),
    weekdays: z.array(z.number()).nullable().optional(),
    timezone_name: z.string().nullable().optional(),
    session_start: z.string().nullable().optional(),
    session_end: z.string().nullable().optional(),
    approval_policy: DiscoveryScheduleApprovalPolicySchema.nullable().optional(),
    enabled: z.boolean().nullable().optional(),
  })
  .passthrough();
export type DiscoverySchedulePatchRequest = z.infer<typeof DiscoverySchedulePatchRequestSchema>;
