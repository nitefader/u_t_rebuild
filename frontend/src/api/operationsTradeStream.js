const API_PREFIX = "/api/v1/operations";

export function createOperationsTradeStreamApi({ fetchImpl = globalThis.fetch, websocketImpl = globalThis.WebSocket } = {}) {
  return {
    async health() {
      if (typeof fetchImpl !== "function") {
        throw new Error("Operations trade-stream API unavailable: fetch is not configured");
      }
      const response = await fetchImpl(`${API_PREFIX}/trade-stream/health`, {
        headers: { Accept: "application/json" }
      });
      if (!response.ok) {
        throw new Error(`Trade-stream health failed (${response.status}): ${response.statusText}`);
      }
      return response.json();
    },

    streamUrl(accountId) {
      const protocol = globalThis.location && globalThis.location.protocol === "https:" ? "wss:" : "ws:";
      const host = globalThis.location ? globalThis.location.host : "localhost";
      const query = accountId ? `?account_id=${encodeURIComponent(accountId)}` : "";
      return `${protocol}//${host}${API_PREFIX}/trade-stream${query}`;
    },

    openStream(accountId) {
      if (typeof websocketImpl !== "function") {
        throw new Error("Operations trade-stream unavailable: WebSocket is not configured");
      }
      return new websocketImpl(this.streamUrl(accountId));
    }
  };
}
