const MARKET_DATA_PREFIX = "/api/v1/market-data";
const AI_PREFIX = "/api/v1/ai";

async function requestJson(url, options = {}, fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") {
    throw new Error("Services API unavailable: fetch is not configured");
  }
  const response = await fetchImpl(url, {
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
    throw new Error(`Services API request failed (${response.status}): ${detail}`);
  }
  return payload;
}

export function createServicesApi(fetchImpl = globalThis.fetch) {
  const md = (path, options) => requestJson(`${MARKET_DATA_PREFIX}${path}`, options, fetchImpl);
  const ai = (path, options) => requestJson(`${AI_PREFIX}${path}`, options, fetchImpl);
  const mdPost = (path) => md(path, { method: "POST" });
  const aiPost = (path) => ai(path, { method: "POST" });
  return {
    listMarketData: () => md("/services"),
    createMarketData: (payload) => md("/services", { method: "POST", body: JSON.stringify(payload) }),
    updateMarketData: (id, payload) => md(`/services/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
    validateMarketData: (id) => mdPost(`/services/${id}/validate`),
    setDefaultMarketData: (id) => mdPost(`/services/${id}/set-default`),
    disableMarketData: (id) => mdPost(`/services/${id}/disable`),
    resolveMarketData: (payload) => md("/services/resolve", { method: "POST", body: JSON.stringify(payload) }),
    listAi: () => ai("/providers"),
    createAi: (payload) => ai("/providers", { method: "POST", body: JSON.stringify(payload) }),
    updateAi: (id, payload) => ai(`/providers/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
    validateAi: (id) => aiPost(`/providers/${id}/validate`),
    setDefaultAi: (id) => aiPost(`/providers/${id}/set-default`),
    disableAi: (id) => aiPost(`/providers/${id}/disable`)
  };
}
