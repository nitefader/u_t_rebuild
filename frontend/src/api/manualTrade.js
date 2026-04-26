const API_PREFIX = "/api/v1/broker-accounts";
const SESSION_STORAGE_KEY = "utos.operatorSessionId";

function operatorSessionId() {
  try {
    const existing = globalThis.localStorage && globalThis.localStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) return existing;
    const generated = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `operator-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e9).toString(36)}`;
    if (globalThis.localStorage) globalThis.localStorage.setItem(SESSION_STORAGE_KEY, generated);
    return generated;
  } catch {
    return `operator-${Date.now().toString(36)}`;
  }
}

async function requestJson(path, options = {}, fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") {
    throw new Error("Manual Trade API unavailable: fetch is not configured");
  }
  const response = await fetchImpl(`${API_PREFIX}${path}`, {
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      "X-Operator-Session-Id": operatorSessionId(),
      ...(options.headers || {})
    },
    ...options
  });
  let payload = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    const detail = payload && payload.detail && typeof payload.detail === "object" ? payload.detail : null;
    const message = detail ? detail.message : (payload && typeof payload.detail === "string" ? payload.detail : response.statusText);
    const error = new Error(message || `Manual Trade request failed (${response.status})`);
    error.status = response.status;
    error.detail = detail;
    error.code = detail && detail.code;
    error.recoveryHint = detail && detail.recovery_hint;
    error.fields = detail && detail.fields;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function makeIdempotencyKey() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `key-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e9).toString(36)}`;
}

export function createManualTradeApi({ fetchImpl = globalThis.fetch } = {}) {
  return {
    submit: (accountId, payload) =>
      requestJson(
        `/${accountId}/orders`,
        {
          method: "POST",
          body: JSON.stringify({
            idempotency_key: payload.idempotency_key || makeIdempotencyKey(),
            ...payload
          })
        },
        fetchImpl
      ),
    cancel: (accountId, orderId) =>
      requestJson(
        `/${accountId}/orders/${orderId}/cancel`,
        { method: "POST" },
        fetchImpl
      ),
    list: (accountId) => requestJson(`/${accountId}/orders`, { method: "GET" }, fetchImpl),
    makeIdempotencyKey
  };
}
