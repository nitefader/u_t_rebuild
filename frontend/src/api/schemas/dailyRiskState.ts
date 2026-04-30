import { z } from "zod";

export const DailyAccountStateSchema = z.object({
  account_id: z.string(),
  market_day: z.string(),
  realized_pnl: z.number(),
  drawdown_pct: z.number(),
  last_loss_at: z.string().nullable(),
  total_loss_today: z.number(),
  updated_at: z.string(),
});

export const DailyRiskStateResponseSchema = z.object({
  account_id: z.string(),
  state: DailyAccountStateSchema.nullable(),
  cooldown_remaining_minutes: z.number().nullable(),
});

export type DailyAccountState = z.infer<typeof DailyAccountStateSchema>;
export type DailyRiskStateResponse = z.infer<typeof DailyRiskStateResponseSchema>;
