import { api } from "./client";
import {
  AccountSignalPlanEvaluationListResponseSchema,
  GovernorDecisionListResponseSchema,
  SignalPlanListResponseSchema,
  type AccountSignalPlanEvaluationListResponse,
  type GovernorDecisionListResponse,
  type SignalPlanListResponse,
} from "./schemas/timelines";

export const TimelinesApi = {
  signalPlans: (filters?: {
    deployment_id?: string;
    account_id?: string;
    symbol?: string;
    limit?: number;
  }): Promise<SignalPlanListResponse> => {
    const params = new URLSearchParams();
    if (filters?.deployment_id) params.set("deployment_id", filters.deployment_id);
    if (filters?.account_id) params.set("account_id", filters.account_id);
    if (filters?.symbol) params.set("symbol", filters.symbol.toUpperCase());
    if (filters?.limit != null) params.set("limit", String(filters.limit));
    const qs = params.toString();
    return api.get(SignalPlanListResponseSchema, `/api/v1/operations/signal-plans${qs ? `?${qs}` : ""}`);
  },

  evaluations: (filters?: {
    account_id?: string;
    deployment_id?: string;
    signal_plan_id?: string;
    limit?: number;
  }): Promise<AccountSignalPlanEvaluationListResponse> => {
    const params = new URLSearchParams();
    if (filters?.account_id) params.set("account_id", filters.account_id);
    if (filters?.deployment_id) params.set("deployment_id", filters.deployment_id);
    if (filters?.signal_plan_id) params.set("signal_plan_id", filters.signal_plan_id);
    if (filters?.limit != null) params.set("limit", String(filters.limit));
    const qs = params.toString();
    return api.get(
      AccountSignalPlanEvaluationListResponseSchema,
      `/api/v1/operations/evaluations${qs ? `?${qs}` : ""}`,
    );
  },

  governorDecisions: (filters?: {
    account_id?: string;
    deployment_id?: string;
    signal_plan_id?: string;
    limit?: number;
  }): Promise<GovernorDecisionListResponse> => {
    const params = new URLSearchParams();
    if (filters?.account_id) params.set("account_id", filters.account_id);
    if (filters?.deployment_id) params.set("deployment_id", filters.deployment_id);
    if (filters?.signal_plan_id) params.set("signal_plan_id", filters.signal_plan_id);
    if (filters?.limit != null) params.set("limit", String(filters.limit));
    const qs = params.toString();
    return api.get(
      GovernorDecisionListResponseSchema,
      `/api/v1/operations/governor-decisions${qs ? `?${qs}` : ""}`,
    );
  },
};
