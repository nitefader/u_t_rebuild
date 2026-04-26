const API_PREFIX = "/api/v1/system";

export function createSystemStreamsApi({ fetchImpl = globalThis.fetch } = {}) {
  return {
    async streams() {
      if (typeof fetchImpl !== "function") {
        throw new Error("System streams API unavailable: fetch is not configured");
      }
      const response = await fetchImpl(`${API_PREFIX}/streams`, {
        headers: { Accept: "application/json" }
      });
      if (!response.ok) {
        throw new Error(`Streams snapshot failed (${response.status}): ${response.statusText}`);
      }
      return response.json();
    }
  };
}
