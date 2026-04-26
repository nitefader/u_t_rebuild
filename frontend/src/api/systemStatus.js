const API_PREFIX = "/api/v1/system";

export function createSystemStatusApi({ fetchImpl = globalThis.fetch } = {}) {
  return {
    async status() {
      if (typeof fetchImpl !== "function") {
        throw new Error("System status API unavailable: fetch is not configured");
      }
      const response = await fetchImpl(`${API_PREFIX}/status`, {
        headers: { Accept: "application/json" }
      });
      if (!response.ok) {
        throw new Error(`System status failed (${response.status}): ${response.statusText}`);
      }
      return response.json();
    }
  };
}
