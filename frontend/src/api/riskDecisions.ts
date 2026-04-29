import { api } from "./client";
import {
  RiskDecisionCardListSchema,
  RiskDecisionCardSchema,
  type RiskDecisionCard,
  type RiskDecisionCardList,
} from "./schemas/riskDecisions";

/**
 * Risk decision read API.
 *
 * RiskPlan belongs to the Account or selected research run. SignalPlan describes
 * the proposed lifecycle action. RiskResolver combines the SignalPlan, RiskPlan,
 * and current account or simulated account state to produce a RiskDecisionCard.
 * No simulated or real order may be created without that RiskDecisionCard.
 */
export const RiskDecisionsApi = {
  get: (riskDecisionId: string): Promise<RiskDecisionCard> =>
    api.get(RiskDecisionCardSchema, `/api/v1/risk-decisions/${riskDecisionId}`),

  listByRunId: (runId: string): Promise<RiskDecisionCardList> =>
    api.get(
      RiskDecisionCardListSchema,
      `/api/v1/risk-decisions?run_id=${encodeURIComponent(runId)}`,
    ),

  listBySignalPlanId: (signalPlanId: string): Promise<RiskDecisionCardList> =>
    api.get(
      RiskDecisionCardListSchema,
      `/api/v1/risk-decisions?signal_plan_id=${encodeURIComponent(signalPlanId)}`,
    ),
};
