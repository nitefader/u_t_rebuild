/**
 * Operations Center "Streams" panel.
 *
 * Per the runtime architecture spec, the Operations Center must show:
 *   - Market Data Pipeline status
 *   - Status of every Account's Broker Trade Update Stream
 *   - Connection issues / stale states
 *
 * This panel polls /api/v1/system/streams every few seconds and renders
 * a single-glance status board the operator can read at boot to confirm
 * "everything is connected and running."
 */

const POLL_INTERVAL_MS = 5000;

export function mountSystemStreams(root, api) {
  if (!root) return;

  const state = {
    snapshot: null,
    error: null,
    loading: true
  };
  let timer = null;

  async function refresh() {
    try {
      const snapshot = await api.streams();
      state.snapshot = snapshot;
      state.error = null;
      state.loading = false;
    } catch (err) {
      state.error = err.message || String(err);
      state.loading = false;
    }
    render();
  }

  function start() {
    refresh();
    timer = setInterval(refresh, POLL_INTERVAL_MS);
  }

  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
  }

  function render() {
    root.innerHTML = "";
    const wrap = document.createElement("section");
    wrap.className = "streams-panel";

    const header = document.createElement("header");
    header.className = "streams-panel__header";
    const title = document.createElement("h2");
    title.textContent = "Streams";
    header.appendChild(title);
    if (state.snapshot && state.snapshot.snapshot_at) {
      const meta = document.createElement("span");
      meta.className = "streams-panel__meta";
      meta.textContent = `last poll: ${formatTime(state.snapshot.snapshot_at)}`;
      header.appendChild(meta);
    }
    wrap.appendChild(header);

    if (state.loading) {
      const p = document.createElement("p");
      p.className = "empty";
      p.textContent = "Loading stream status…";
      wrap.appendChild(p);
      root.appendChild(wrap);
      return;
    }
    if (state.error) {
      const p = document.createElement("p");
      p.className = "warning";
      p.setAttribute("role", "alert");
      p.textContent = `Streams snapshot failed: ${state.error}`;
      wrap.appendChild(p);
      root.appendChild(wrap);
      return;
    }

    wrap.appendChild(buildPipelineSection(state.snapshot));
    wrap.appendChild(buildTradeStreamSection(state.snapshot));
    root.appendChild(wrap);
  }

  function buildPipelineSection(snapshot) {
    const section = document.createElement("section");
    section.className = "streams-panel__section";
    const heading = document.createElement("h3");
    heading.textContent = "Market Data Pipelines";
    section.appendChild(heading);

    const hubs = snapshot.market_data_hubs || [];
    if (hubs.length === 0) {
      const p = document.createElement("p");
      p.className = "empty";
      p.textContent = "No pipeline registered — starts on first consumer.";
      section.appendChild(p);
      return section;
    }
    const list = document.createElement("ul");
    list.className = "streams-list";
    for (const hub of hubs) {
      const li = document.createElement("li");
      li.className = `stream-item stream-item--${hub.is_running ? "ok" : "idle"}`;
      const dot = document.createElement("span");
      dot.className = "stream-dot";
      li.appendChild(dot);
      const meta = document.createElement("div");
      meta.className = "stream-meta";
      const primary = document.createElement("strong");
      primary.textContent = `${hub.provider} · ${hub.trading_mode} · ${hub.data_feed}`;
      meta.appendChild(primary);
      const detail = document.createElement("span");
      detail.className = "stream-detail";
      const sym = (hub.subscribed_symbols || []).join(", ") || "no symbols subscribed";
      detail.textContent = `${hub.is_running ? "running" : "idle"} · ${hub.consumer_count} consumer(s) · ${sym}`;
      meta.appendChild(detail);
      li.appendChild(meta);
      list.appendChild(li);
    }
    section.appendChild(list);
    return section;
  }

  function buildTradeStreamSection(snapshot) {
    const section = document.createElement("section");
    section.className = "streams-panel__section";
    const heading = document.createElement("h3");
    heading.textContent = "Broker Trade Update Streams (per Account)";
    section.appendChild(heading);

    const trades = snapshot.trade_streams || [];
    if (trades.length === 0) {
      const p = document.createElement("p");
      p.className = "empty";
      p.textContent = "No Broker Accounts configured. Add one from the Accounts panel and restart the backend to start its trade stream.";
      section.appendChild(p);
      return section;
    }
    const list = document.createElement("ul");
    list.className = "streams-list";
    for (const stream of trades) {
      const cls = stream.is_stale ? "warn" : (stream.is_running ? "ok" : "idle");
      const li = document.createElement("li");
      li.className = `stream-item stream-item--${cls}`;
      const dot = document.createElement("span");
      dot.className = "stream-dot";
      li.appendChild(dot);
      const meta = document.createElement("div");
      meta.className = "stream-meta";
      const primary = document.createElement("strong");
      primary.textContent = `Account ${shortId(stream.account_id)}`;
      meta.appendChild(primary);
      const detail = document.createElement("span");
      detail.className = "stream-detail";
      const lastEvent = stream.last_event_at ? formatTime(stream.last_event_at) : "no events yet";
      detail.textContent = `${stream.is_running ? "running" : "stopped"} · ${stream.subscriber_count} subscriber(s) · last event: ${lastEvent}`;
      meta.appendChild(detail);
      if (stream.is_stale && stream.stale_reason) {
        const stale = document.createElement("span");
        stale.className = "stream-stale";
        stale.textContent = `⚠ ${stream.stale_reason}`;
        meta.appendChild(stale);
      }
      if (stream.last_error) {
        const err = document.createElement("span");
        err.className = "stream-error";
        err.textContent = `Error: ${stream.last_error}`;
        meta.appendChild(err);
      }
      li.appendChild(meta);
      list.appendChild(li);
    }
    section.appendChild(list);
    return section;
  }

  start();
  return { stop, refresh, state };
}

function formatTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function shortId(id) {
  if (!id || typeof id !== "string") return "?";
  return id.slice(0, 8);
}
