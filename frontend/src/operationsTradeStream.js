const MAX_EVENTS = 50;

export function mountOperationsTradeStream(root, api) {
  if (!root) return;

  const state = {
    socket: null,
    config: null,
    status: "loading",
    statusMessage: "Loading trade-stream config…",
    events: []
  };

  function setStatus(status, message) {
    state.status = status;
    state.statusMessage = message;
    render();
  }

  function appendEvent(event) {
    state.events.unshift(event);
    if (state.events.length > MAX_EVENTS) {
      state.events = state.events.slice(0, MAX_EVENTS);
    }
    render();
  }

  function disconnect() {
    if (state.socket && state.socket.readyState !== WebSocket.CLOSED) {
      state.socket.close(1000, "client disconnect");
    }
    state.socket = null;
  }

  function connect() {
    disconnect();
    setStatus("connecting", "Connecting to paper account trade stream…");

    let socket;
    try {
      socket = api.openStream();
    } catch (err) {
      setStatus("error", `Could not open WebSocket: ${err.message}`);
      return;
    }
    state.socket = socket;

    socket.addEventListener("open", () => setStatus("connected", "Streaming Alpaca paper trade updates"));
    socket.addEventListener("message", (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      if (payload.type === "ready") {
        setStatus("connected", `Streaming ${payload.account_provider}`);
      } else if (payload.type === "error") {
        setStatus("error", `Stream error: ${payload.code}${payload.message ? ` — ${payload.message}` : ""}`);
      } else if (
        payload.type === "order_event" ||
        payload.type === "fill_event" ||
        payload.type === "account_snapshot" ||
        payload.type === "position_snapshot"
      ) {
        appendEvent({ type: payload.type, data: payload.data, received_at: new Date().toISOString() });
      }
    });
    socket.addEventListener("close", () => {
      if (state.status !== "error") {
        setStatus("disconnected", "Trade stream closed");
      }
    });
    socket.addEventListener("error", () => {
      setStatus("error", "Trade stream socket error");
    });
  }

  function describeEvent(event) {
    const data = event.data || {};
    if (event.type === "order_event") {
      const status = data.status || "?";
      const symbol = data.symbol || data.client_order_id || "?";
      const filled = data.filled_quantity ?? 0;
      return `Order ${status}: ${symbol} (filled ${filled})`;
    }
    if (event.type === "fill_event") {
      return `Fill: ${data.symbol} ${data.side} ${data.qty} @ ${data.price}`;
    }
    if (event.type === "account_snapshot") {
      return `Account: equity ${data.equity}, cash ${data.cash}, buying_power ${data.buying_power}`;
    }
    if (event.type === "position_snapshot") {
      return `Position: ${data.symbol} ${data.side} ${data.qty} @ ${data.avg_entry_price}`;
    }
    return event.type;
  }

  function render() {
    root.innerHTML = "";

    const wrapper = document.createElement("section");
    wrapper.className = "ops-trade-stream";

    const header = document.createElement("header");
    header.className = "ops-trade-stream__header";
    const title = document.createElement("h2");
    title.textContent = "Trade Stream — Alpaca Paper";
    header.appendChild(title);

    const controls = document.createElement("div");
    controls.className = "ops-trade-stream__controls";

    const connectButton = document.createElement("button");
    connectButton.type = "button";
    connectButton.textContent = state.socket && state.status === "connected" ? "Reconnect" : "Connect";
    connectButton.disabled = !(state.config && state.config.streaming_enabled);
    connectButton.addEventListener("click", () => connect());
    controls.appendChild(connectButton);

    if (state.socket && state.status === "connected") {
      const stopButton = document.createElement("button");
      stopButton.type = "button";
      stopButton.className = "danger";
      stopButton.textContent = "Disconnect";
      stopButton.addEventListener("click", () => {
        disconnect();
        setStatus("disconnected", "Disconnected by operator");
      });
      controls.appendChild(stopButton);
    }

    header.appendChild(controls);
    wrapper.appendChild(header);

    const status = document.createElement("p");
    status.className = `ops-trade-stream__status ops-trade-stream__status--${state.status}`;
    status.textContent = state.statusMessage;
    wrapper.appendChild(status);

    if (!state.config || !state.config.streaming_enabled) {
      const help = document.createElement("p");
      help.className = "ops-trade-stream__help";
      help.textContent =
        "Set ALPACA_API_KEY and ALPACA_SECRET_KEY before starting the API server. The stream emits 24/7 whenever the paper account has activity (submits, cancels, fills) — no equity market hours required.";
      wrapper.appendChild(help);
      root.appendChild(wrapper);
      return;
    }

    if (state.events.length === 0) {
      const placeholder = document.createElement("p");
      placeholder.className = "ops-trade-stream__placeholder";
      placeholder.textContent =
        state.status === "connected"
          ? "Waiting for trade events. Submit or cancel a paper order to see events arrive."
          : "Connect to start streaming.";
      wrapper.appendChild(placeholder);
    } else {
      const list = document.createElement("ul");
      list.className = "ops-trade-stream__events";
      for (const event of state.events) {
        const item = document.createElement("li");
        const meta = document.createElement("span");
        meta.className = "ops-trade-stream__event-meta";
        meta.textContent = formatTime(event.received_at);
        const desc = document.createElement("span");
        desc.className = `ops-trade-stream__event ops-trade-stream__event--${event.type}`;
        desc.textContent = describeEvent(event);
        item.appendChild(meta);
        item.appendChild(desc);
        list.appendChild(item);
      }
      wrapper.appendChild(list);
    }

    root.appendChild(wrapper);
  }

  async function init() {
    try {
      const config = await api.health();
      state.config = config;
      if (!config.streaming_enabled) {
        setStatus("disabled", "Streaming disabled — credentials are not configured.");
        return;
      }
      setStatus("idle", "Ready. Click Connect to subscribe to Alpaca paper trade updates.");
    } catch (err) {
      setStatus("error", `Could not load trade-stream config: ${err.message}`);
    }
  }

  render();
  init();

  return { connect, disconnect, state };
}

function formatTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
