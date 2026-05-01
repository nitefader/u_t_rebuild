import { z } from "zod";

export const OrderSideSchema = z.enum(["long", "short"]);
export type OrderSide = z.infer<typeof OrderSideSchema>;

export const OrderTypeSchema = z.enum(["market", "limit", "stop", "stop_limit"]);
export type OrderType = z.infer<typeof OrderTypeSchema>;

export const TimeInForceSchema = z.enum(["day", "gtc", "ioc", "fok", "opg", "cls"]);
export type TimeInForce = z.infer<typeof TimeInForceSchema>;

export const ManualOrderIntentSchema = z.enum(["open", "close", "reduce"]);
export type ManualOrderIntent = z.infer<typeof ManualOrderIntentSchema>;

/** Permissive — additive backend status values must not break the order ticket. */
export const InternalOrderStatusSchema = z.string();
export type InternalOrderStatus = z.infer<typeof InternalOrderStatusSchema>;

export const InternalOrderIntentSchema = z
  .enum([
    "open",
    "close",
    "reduce",
    "target",
    "stop",
    "trail",
    "breakeven",
    "runner",
    "logical_exit",
    "take_profit",
    "stop_loss",
    "scale",
  ])
  .or(z.string());

export const ManualOrderRequestSchema = z.object({
  symbol: z.string().min(1).max(20),
  side: OrderSideSchema,
  qty: z.number().positive(),
  order_type: OrderTypeSchema.default("market"),
  time_in_force: TimeInForceSchema.default("day"),
  intent: ManualOrderIntentSchema.default("open"),
  reason: z.string().min(1).max(200),
  idempotency_key: z.string().min(8).max(64),
  confirm_live: z.boolean().default(false),
  confirm_account_display_name: z.string().nullable().optional(),
});
export type ManualOrderRequest = z.infer<typeof ManualOrderRequestSchema>;

export const ManualOrderResponseSchema = z.object({
  order_id: z.string(),
  client_order_id: z.string(),
  account_id: z.string(),
  symbol: z.string(),
  side: OrderSideSchema,
  quantity: z.number(),
  filled_quantity: z.number(),
  status: InternalOrderStatusSchema,
  intent: InternalOrderIntentSchema,
  submitted_at: z.string(),
  origin: z.string().optional(),
  source: z.string().optional(),
  duplicate: z.boolean().default(false),
});
export type ManualOrderResponse = z.infer<typeof ManualOrderResponseSchema>;

export const ManualOrderListResponseSchema = z.object({
  orders: z.array(ManualOrderResponseSchema).default([]),
});
export type ManualOrderListResponse = z.infer<typeof ManualOrderListResponseSchema>;

export const CancelOrderResponseSchema = z.object({
  order_id: z.string(),
  status: InternalOrderStatusSchema,
  no_op: z.boolean().default(false),
  filled_quantity: z.number().default(0),
  message: z.string().nullable().optional(),
});
export type CancelOrderResponse = z.infer<typeof CancelOrderResponseSchema>;
