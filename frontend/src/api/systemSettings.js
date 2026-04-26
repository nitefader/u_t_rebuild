const API_PREFIX = "/api/v1/system";

async function requestJson(path, options = {}, fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") {
    throw new Error("System settings API unavailable: fetch is not configured");
  }
  const response = await fetchImpl(`${API_PREFIX}${path}`, {
    headers: { "Content-Type": "application/json", Accept: "application/json", ...(options.headers || {}) },
    ...options
  });
  let payload = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : response.statusText;
    throw new Error(`System settings request failed (${response.status}): ${detail}`);
  }
  return payload;
}

export function createSystemSettingsApi({ fetchImpl = globalThis.fetch } = {}) {
  return {
    get() {
      return requestJson("/settings", { method: "GET" }, fetchImpl);
    },
    update(changes) {
      return requestJson("/settings", { method: "PUT", body: JSON.stringify(changes) }, fetchImpl);
    },
    status() {
      return requestJson("/status", { method: "GET" }, fetchImpl);
    }
  };
}
