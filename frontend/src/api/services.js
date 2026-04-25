const API_PREFIX = "/api/v1/services";

async function requestJson(path, options = {}, fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") {
    throw new Error("Services API unavailable: fetch is not configured");
  }
  const response = await fetchImpl(`${API_PREFIX}${path}`, {
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
  const post = (path) => requestJson(path, { method: "POST" }, fetchImpl);
  return {
    listMarketData: () => requestJson("/market-data", {}, fetchImpl),
    createMarketData: (payload) => requestJson("/market-data", { method: "POST", body: JSON.stringify(payload) }, fetchImpl),
    updateMarketData: (id, payload) => requestJson(`/market-data/${id}`, { method: "PUT", body: JSON.stringify(payload) }, fetchImpl),
    validateMarketData: (id) => post(`/market-data/${id}/validate`),
    setDefaultMarketData: (id) => post(`/market-data/${id}/set-default`),
    disableMarketData: (id) => post(`/market-data/${id}/disable`),
    resolveMarketData: (payload) => requestJson("/market-data/resolve", { method: "POST", body: JSON.stringify(payload) }, fetchImpl),
    listAi: () => requestJson("/ai", {}, fetchImpl),
    createAi: (payload) => requestJson("/ai", { method: "POST", body: JSON.stringify(payload) }, fetchImpl),
    updateAi: (id, payload) => requestJson(`/ai/${id}`, { method: "PUT", body: JSON.stringify(payload) }, fetchImpl),
    validateAi: (id) => post(`/ai/${id}/validate`),
    setDefaultAi: (id) => post(`/ai/${id}/set-default`),
    disableAi: (id) => post(`/ai/${id}/disable`)
  };
}
