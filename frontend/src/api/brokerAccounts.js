const API_PREFIX = "/api/v1/broker-accounts";

async function requestJson(path, options = {}, fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") {
    throw new Error("Broker Accounts API unavailable: fetch is not configured");
  }
  const response = await fetchImpl(`${API_PREFIX}${path}`, {
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

export function createBrokerAccountsApi({ fetchImpl = globalThis.fetch } = {}) {
  return {
    list: () => requestJson("", { method: "GET" }, fetchImpl),
    createAlpacaPaper: (payload) =>
      requestJson("/alpaca-paper", { method: "POST", body: JSON.stringify(payload) }, fetchImpl),
    replaceAlpacaPaperCredentials: (id, payload) =>
      requestJson(`/${id}/alpaca-paper/credentials`, { method: "PUT", body: JSON.stringify(payload) }, fetchImpl),
    deleteAccount: (id, payload) =>
      requestJson(`/${id}/delete`, { method: "POST", body: JSON.stringify(payload) }, fetchImpl)
  };
}
