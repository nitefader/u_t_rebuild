const API_PREFIX = "/api/v1/operations";
const BROKER_ACCOUNTS_PREFIX = "/api/v1/broker-accounts";

async function requestJson(path, options = {}, fetchImpl = globalThis.fetch, prefix = API_PREFIX) {
  if (typeof fetchImpl !== "function") {
    throw new Error("Operations API unavailable: fetch is not configured");
  }

  const response = await fetchImpl(`${prefix}${path}`, {
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : response.statusText;
    throw new Error(`Operations API request failed (${response.status}): ${detail}`);
  }

  return payload;
}

function commandBody(reason) {
  return JSON.stringify({ reason: reason || "operator_request" });
}

export function createOperationsApi(fetchImpl = globalThis.fetch) {
  return {
    getOverview: () => requestJson("/overview", {}, fetchImpl),
    getAccount: (accountId) => requestJson(`/accounts/${accountId}`, {}, fetchImpl),
    getDeployment: (deploymentId) => requestJson(`/deployments/${deploymentId}`, {}, fetchImpl),
    getOrder: (orderId) => requestJson(`/orders/${orderId}`, {}, fetchImpl),
    createAlpacaPaperAccount: ({ displayName, apiKey, apiSecret }) =>
      requestJson(
        "/alpaca-paper",
        {
          method: "POST",
          body: JSON.stringify({
            display_name: displayName,
            api_key: apiKey,
            api_secret: apiSecret
          })
        },
        fetchImpl,
        BROKER_ACCOUNTS_PREFIX
      ),
    replaceAlpacaPaperCredentials: (accountId, { apiKey, apiSecret }) =>
      requestJson(
        `/${accountId}/alpaca-paper/credentials`,
        {
          method: "PUT",
          body: JSON.stringify({
            api_key: apiKey,
            api_secret: apiSecret
          })
        },
        fetchImpl,
        BROKER_ACCOUNTS_PREFIX
      ),
    deleteBrokerAccount: (accountId, { confirmDisplayName, confirmMode }) =>
      requestJson(
        `/${accountId}/delete`,
        {
          method: "POST",
          body: JSON.stringify({
            confirm_display_name: confirmDisplayName,
            confirm_mode: confirmMode
          })
        },
        fetchImpl,
        BROKER_ACCOUNTS_PREFIX
      ),
    pauseAccount: (accountId, reason) =>
      requestJson(`/accounts/${accountId}/pause`, { method: "POST", body: commandBody(reason) }, fetchImpl),
    resumeAccount: (accountId, reason) =>
      requestJson(`/accounts/${accountId}/resume`, { method: "POST", body: commandBody(reason) }, fetchImpl),
    pauseDeployment: (deploymentId, reason) =>
      requestJson(`/deployments/${deploymentId}/pause`, { method: "POST", body: commandBody(reason) }, fetchImpl),
    resumeDeployment: (deploymentId, reason) =>
      requestJson(`/deployments/${deploymentId}/resume`, { method: "POST", body: commandBody(reason) }, fetchImpl),
    globalKill: (reason) => requestJson("/global/kill", { method: "POST", body: commandBody(reason) }, fetchImpl),
    globalResume: (reason) => requestJson("/global/resume", { method: "POST", body: commandBody(reason) }, fetchImpl),
    flattenAccount: (accountId, reason) =>
      requestJson(`/accounts/${accountId}/flatten`, { method: "POST", body: commandBody(reason) }, fetchImpl),
    flattenDeployment: (deploymentId, reason) =>
      requestJson(`/deployments/${deploymentId}/flatten`, { method: "POST", body: commandBody(reason) }, fetchImpl)
  };
}
