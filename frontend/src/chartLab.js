const MAX_BARS = 120;
const SVG_NS = "http://www.w3.org/2000/svg";

export function mountChartLab(root, api) {
  if (!root) return;

  const state = {
    socket: null,
    config: null,
    symbol: "",
    bars: [],
    status: "loading",
    statusMessage: "Loading streaming config…"
  };

  function setStatus(status, message) {
    state.status = status;
    state.statusMessage = message;
    render();
  }

  function appendBar(bar) {
    state.bars.push(bar);
    if (state.bars.length > MAX_BARS) {
      state.bars = state.bars.slice(-MAX_BARS);
    }
    render();
  }

  function disconnect() {
    if (state.socket && state.socket.readyState !== WebSocket.CLOSED) {
      state.socket.close(1000, "client disconnect");
    }
    state.socket = null;
  }

  function connect(symbol) {
    disconnect();
    state.bars = [];
    state.symbol = symbol;
    setStatus("connecting", `Connecting to ${symbol}…`);

    let socket;
    try {
      socket = api.openStream(symbol);
    } catch (err) {
      setStatus("error", `Could not open WebSocket: ${err.message}`);
      return;
    }
    state.socket = socket;

    socket.addEventListener("open", () => setStatus("connected", `Streaming ${symbol}`));
    socket.addEventListener("message", (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      if (payload.type === "bar") {
        appendBar(payload.data);
      } else if (payload.type === "ready") {
        state.symbol = payload.symbol || symbol;
        setStatus("connected", `Streaming ${state.symbol}${payload.test_stream ? " (FAKEPACA test stream)" : ""}`);
      } else if (payload.type === "error") {
        setStatus("error", `Stream error: ${payload.code}${payload.message ? ` — ${payload.message}` : ""}`);
      }
    });
    socket.addEventListener("close", (event) => {
      if (state.status !== "error") {
        setStatus("disconnected", `Stream closed${event.reason ? ` — ${event.reason}` : ""}`);
      }
    });
    socket.addEventListener("error", () => {
      setStatus("error", "Stream socket error");
    });
  }

  function buildChart() {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 600 240");
    svg.setAttribute("class", "chart-lab__svg");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", `Live price chart for ${state.symbol || "selected symbol"}`);

    if (state.bars.length === 0) {
      const text = document.createElementNS(SVG_NS, "text");
      text.setAttribute("x", "300");
      text.setAttribute("y", "120");
      text.setAttribute("text-anchor", "middle");
      text.setAttribute("class", "chart-lab__placeholder");
      text.textContent = "Waiting for first bar…";
      svg.appendChild(text);
      return svg;
    }

    if (state.bars.length === 1) {
      // Single bar: draw an OHLC candle stub at the center so the chart
      // isn't empty while we wait for the second bar.
      const bar = state.bars[0];
      const padding = 24;
      const span = Math.max(bar.high - bar.low, 0.0001);
      const hi = padding;
      const lo = 240 - padding;
      const yFor = (price) => lo - ((price - bar.low) / span) * (lo - hi);
      const cx = 300;
      const wickTop = yFor(bar.high);
      const wickBottom = yFor(bar.low);
      const openY = yFor(bar.open);
      const closeY = yFor(bar.close);
      const isUp = bar.close >= bar.open;
      const color = isUp ? "#1f5a35" : "#8c1d1d";

      const wick = document.createElementNS(SVG_NS, "line");
      wick.setAttribute("x1", String(cx));
      wick.setAttribute("x2", String(cx));
      wick.setAttribute("y1", wickTop.toFixed(2));
      wick.setAttribute("y2", wickBottom.toFixed(2));
      wick.setAttribute("stroke", color);
      wick.setAttribute("stroke-width", "1.2");
      svg.appendChild(wick);

      const body = document.createElementNS(SVG_NS, "rect");
      const bodyTop = Math.min(openY, closeY);
      const bodyHeight = Math.max(Math.abs(closeY - openY), 1.5);
      body.setAttribute("x", String(cx - 10));
      body.setAttribute("y", bodyTop.toFixed(2));
      body.setAttribute("width", "20");
      body.setAttribute("height", bodyHeight.toFixed(2));
      body.setAttribute("fill", color);
      svg.appendChild(body);

      const note = document.createElementNS(SVG_NS, "text");
      note.setAttribute("x", "300");
      note.setAttribute("y", "230");
      note.setAttribute("text-anchor", "middle");
      note.setAttribute("class", "chart-lab__placeholder");
      note.textContent = "Waiting for next bar — line draws once we have 2 minutes of data";
      svg.appendChild(note);
      return svg;
    }

    const closes = state.bars.map((bar) => bar.close);
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const range = max - min;
    const xStep = 600 / (state.bars.length - 1);
    const points = closes
      .map((close, index) => {
        // When all closes are identical (FAKEPACA test stream emits a
        // canned bar) the line draws horizontally at chart center
        // instead of pinning to the bottom of the y-axis.
        const y = range > 0 ? 220 - ((close - min) / range) * 200 : 120;
        const x = index * xStep;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");

    const polyline = document.createElementNS(SVG_NS, "polyline");
    polyline.setAttribute("points", points);
    polyline.setAttribute("fill", "none");
    polyline.setAttribute("stroke", "#316b83");
    polyline.setAttribute("stroke-width", "1.5");
    svg.appendChild(polyline);

    const lastClose = closes[closes.length - 1];
    const dot = document.createElementNS(SVG_NS, "circle");
    const lastY = range > 0 ? 220 - ((lastClose - min) / range) * 200 : 120;
    dot.setAttribute("cx", "600");
    dot.setAttribute("cy", lastY.toFixed(2));
    dot.setAttribute("r", "3");
    dot.setAttribute("fill", "#316b83");
    svg.appendChild(dot);

    return svg;
  }

  function buildBarsTable() {
    const table = document.createElement("table");
    table.className = "chart-lab__table";
    const thead = document.createElement("thead");
    thead.innerHTML = "<tr><th>Time</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th></tr>";
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    const recent = state.bars.slice(-8).reverse();
    for (const bar of recent) {
      const row = document.createElement("tr");
      const cells = [
        formatTime(bar.timestamp),
        formatPrice(bar.open),
        formatPrice(bar.high),
        formatPrice(bar.low),
        formatPrice(bar.close),
        bar.volume.toLocaleString()
      ];
      for (const value of cells) {
        const td = document.createElement("td");
        td.textContent = value;
        row.appendChild(td);
      }
      tbody.appendChild(row);
    }
    table.appendChild(tbody);
    return table;
  }

  function buildLastPrice() {
    if (state.bars.length === 0) return null;
    const latest = state.bars[state.bars.length - 1];
    const wrap = document.createElement("div");
    wrap.className = "chart-lab__last-price";
    const value = document.createElement("span");
    value.className = "chart-lab__last-price-value";
    value.textContent = formatPrice(latest.close);
    const meta = document.createElement("span");
    meta.className = "chart-lab__last-price-meta";
    meta.textContent = `${latest.symbol} · ${latest.timeframe} · ${formatTime(latest.timestamp)}`;
    wrap.appendChild(value);
    wrap.appendChild(meta);
    return wrap;
  }

  function render() {
    root.innerHTML = "";

    const wrapper = document.createElement("section");
    wrapper.className = "chart-lab__shell";

    const header = document.createElement("header");
    header.className = "chart-lab__header";

    const title = document.createElement("h1");
    title.textContent = "Chart Lab";
    header.appendChild(title);

    const subtitle = document.createElement("p");
    subtitle.className = "chart-lab__subtitle";
    if (state.config) {
      subtitle.textContent = state.config.test_stream
        ? "Source: Alpaca FAKEPACA test stream (24/7 synthetic data)"
        : `Source: Alpaca live data feed · default symbol ${state.config.default_symbol}`;
    } else {
      subtitle.textContent = "Live bar stream from the configured Alpaca account.";
    }
    header.appendChild(subtitle);
    wrapper.appendChild(header);

    const panel = document.createElement("section");
    panel.className = "chart-lab__panel";

    const controls = document.createElement("form");
    controls.className = "chart-lab__controls";
    controls.addEventListener("submit", (event) => {
      event.preventDefault();
      const formData = new FormData(controls);
      const symbol = String(formData.get("symbol") || "").trim().toUpperCase();
      if (!symbol) return;
      connect(symbol);
    });

    const symbolField = document.createElement("input");
    symbolField.name = "symbol";
    symbolField.type = "text";
    symbolField.placeholder = "Symbol (e.g. SPY)";
    symbolField.value = state.symbol || (state.config && state.config.default_symbol) || "";
    symbolField.disabled = !(state.config && state.config.streaming_enabled);
    symbolField.className = "chart-lab__symbol-input";
    if (state.config && state.config.test_stream) {
      symbolField.value = state.config.default_symbol;
      symbolField.readOnly = true;
      symbolField.title = "FAKEPACA test stream — symbol is fixed";
    }
    controls.appendChild(symbolField);

    const connectButton = document.createElement("button");
    connectButton.type = "submit";
    connectButton.textContent = state.status === "connected" ? "Reconnect" : "Connect";
    connectButton.disabled = !(state.config && state.config.streaming_enabled);
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

    panel.appendChild(controls);

    const status = document.createElement("p");
    status.className = `chart-lab__status chart-lab__status--${state.status}`;
    status.textContent = state.statusMessage;
    panel.appendChild(status);

    if (!state.config || !state.config.streaming_enabled) {
      const help = document.createElement("p");
      help.className = "chart-lab__help";
      help.textContent =
        "Streaming is disabled. Set ALPACA_API_KEY and ALPACA_SECRET_KEY (and optionally ALPACA_USE_TEST_STREAM=1 for the 24/7 FAKEPACA feed) before starting the API server.";
      panel.appendChild(help);
    } else {
      const lastPrice = buildLastPrice();
      if (lastPrice) panel.appendChild(lastPrice);
      panel.appendChild(buildChart());
      if (state.bars.length > 0) {
        panel.appendChild(buildBarsTable());
      }
    }

    wrapper.appendChild(panel);
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
      setStatus("idle", `Ready. Default symbol: ${config.default_symbol}.`);
    } catch (err) {
      setStatus("error", `Could not load Chart Lab config: ${err.message}`);
    }
  }

  render();
  init();

  return {
    connect,
    disconnect,
    state
  };
}

function formatPrice(value) {
  if (typeof value !== "number") return "—";
  return value.toFixed(2);
}

function formatTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
