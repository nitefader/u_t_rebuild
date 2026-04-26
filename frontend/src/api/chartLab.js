const API_PREFIX = "/api/v1/chart-lab";

export function createChartLabApi({ fetchImpl = globalThis.fetch, websocketImpl = globalThis.WebSocket } = {}) {
  return {
    async health() {
      if (typeof fetchImpl !== "function") {
        throw new Error("Chart Lab API unavailable: fetch is not configured");
      }
      const response = await fetchImpl(`${API_PREFIX}/health`, {
        headers: { Accept: "application/json" }
      });
      if (!response.ok) {
        throw new Error(`Chart Lab health failed (${response.status}): ${response.statusText}`);
      }
      return response.json();
    },

    streamUrl(symbol) {
      const protocol = globalThis.location && globalThis.location.protocol === "https:" ? "wss:" : "ws:";
      const host = globalThis.location ? globalThis.location.host : "localhost";
      const query = symbol ? `?symbol=${encodeURIComponent(symbol)}` : "";
      return `${protocol}//${host}${API_PREFIX}/stream${query}`;
    },

    openStream(symbol) {
      if (typeof websocketImpl !== "function") {
        throw new Error("Chart Lab stream unavailable: WebSocket is not configured");
      }
      return new websocketImpl(this.streamUrl(symbol));
    }
  };
}
