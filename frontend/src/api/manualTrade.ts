import { apiJson } from "./client";
import {
  CancelOrderResponseSchema,
  ManualOrderListResponseSchema,
  ManualOrderResponseSchema,
  type CancelOrderResponse,
  type ManualOrderListResponse,
  type ManualOrderRequest,
  type ManualOrderResponse,
} from "./schemas/manualTrade";

/**
 * Manual trade boundary.
 *
 * The manual-trade backend route accepts an optional `X-Operator-Session-Id`
 * header (or `X-Request-Id`) so the audit trail can attribute the
 * action to a specific operator session. We generate a stable
 * session id once per browser tab and attach it to every mutating
 * call.
 */
const SESSION_HEADER = "X-Operator-Session-Id";

let cachedSessionId: string | null = null;

function operatorSessionId(): string {
  if (cachedSessionId) return cachedSessionId;
  if (typeof window !== "undefined") {
    const key = "ut.operator.session.v1";
    try {
      const existing = window.sessionStorage.getItem(key);
      if (existing) {
        cachedSessionId = existing;
        return existing;
      }
    } catch {
      /* sessionStorage unavailable — fall through */
    }
    const fresh = `op-${Date.now().toString(36)}-${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
    try {
      window.sessionStorage.setItem(key, fresh);
    } catch {
      /* ignore */
    }
    cachedSessionId = fresh;
    return fresh;
  }
  cachedSessionId = `op-server-${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
  return cachedSessionId;
}

function sessionHeaders(): Record<string, string> {
  return { [SESSION_HEADER]: operatorSessionId() };
}

export const ManualTradeApi = {
  list: (accountId: string): Promise<ManualOrderListResponse> =>
    apiJson(ManualOrderListResponseSchema, `/api/v1/broker-accounts/${accountId}/orders`),

  submit: (accountId: string, request: ManualOrderRequest): Promise<ManualOrderResponse> =>
    apiJson(ManualOrderResponseSchema, `/api/v1/broker-accounts/${accountId}/orders`, {
      method: "POST",
      body: request,
      headers: sessionHeaders(),
    }),

  cancel: (accountId: string, orderId: string): Promise<CancelOrderResponse> =>
    apiJson(
      CancelOrderResponseSchema,
      `/api/v1/broker-accounts/${accountId}/orders/${orderId}/cancel`,
      {
        method: "POST",
        body: {},
        headers: sessionHeaders(),
      },
    ),
};
