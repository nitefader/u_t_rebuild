const API_PREFIX = "/api/v1/broker-accounts";
const OPERATIONS_PREFIX = "/api/v1/operations";

async function requestJson(path, options = {}, fetchImpl = globalThis.fetch, prefix = API_PREFIX) {
  if (typeof fetchImpl !== "function") {
    throw new Error("Broker Accounts API unavailable: fetch is not configured");
  }
  const response = await fetchImpl(`${prefix}${path}`, {
    headers: { "Content-Type": "application/json", Accept: "application/json", ...(options.headers || {}) },
    ...options
  });
  let payload = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : response.statusText;
    throw new Error(`Broker Accounts request failed (${response.status}): ${detail}`);
  }
  return payload;
}

function commandBody(reason) {
  return JSON.stringify({ reason: reason || "operator_request" });
}

export function createBrokerAccountsApi({ fetchImpl = globalThis.fetch } = {}) {
  return {
    list: () => requestJson("", { method: "GET" }, fetchImpl),
    create: (payload) =>
      requestJson("", { method: "POST", body: JSON.stringify(payload) }, fetchImpl),
    replaceCredentials: (id, payload) =>
      requestJson(`/${id}/credentials`, { method: "PUT", body: JSON.stringify(payload) }, fetchImpl),
    deleteAccount: (id, payload) =>
      requestJson(`/${id}/delete`, { method: "POST", body: JSON.stringify(payload) }, fetchImpl),
    // Account-level operational controls live under /api/v1/operations but
    // logically belong to a broker account, so we expose them on this API
    // surface to keep the Brokers page self-sufficient.
    pauseAccount: (id, reason) =>
      requestJson(`/accounts/${id}/pause`, { method: "POST", body: commandBody(reason) }, fetchImpl, OPERATIONS_PREFIX),
    resumeAccount: (id, reason) =>
      requestJson(`/accounts/${id}/resume`, { method: "POST", body: commandBody(reason) }, fetchImpl, OPERATIONS_PREFIX),
    flattenAccount: (id, reason) =>
      requestJson(`/accounts/${id}/flatten`, { method: "POST", body: commandBody(reason) }, fetchImpl, OPERATIONS_PREFIX)
  };
}
