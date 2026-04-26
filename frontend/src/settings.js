const DATA_FEEDS = [
  { value: "iex", label: "IEX (real-time, free, IEX exchange only)" },
  { value: "sip", label: "SIP (real-time, full consolidated tape — premium)" },
  { value: "delayed_sip", label: "Delayed SIP (15-min delayed, free)" },
  { value: "boats", label: "BOATS (overnight equity feed)" },
  { value: "overnight", label: "Overnight derived feed" },
  { value: "otc", label: "OTC" }
];

export function mountSettings(root, api) {
  if (!root) return;
  const state = {
    settings: null,
    status: null,
    loading: true,
    saving: false,
    error: null,
    notice: null
  };

  function setState(partial) {
    Object.assign(state, partial);
    render();
  }

  async function refresh() {
    try {
      setState({ loading: true, error: null });
      const [settings, status] = await Promise.all([api.get(), api.status()]);
      setState({ settings, status, loading: false });
    } catch (err) {
      setState({ loading: false, error: err.message || String(err) });
    }
  }

  async function save(form) {
    const data = new FormData(form);
    const changes = {
      alpaca_use_test_stream: data.get("alpaca_use_test_stream") === "on",
      alpaca_data_feed: String(data.get("alpaca_data_feed") || "iex"),
      chart_lab_default_symbol: String(data.get("chart_lab_default_symbol") || "SPY").trim().toUpperCase()
    };
    try {
      setState({ saving: true, error: null, notice: null });
      const updated = await api.update(changes);
      const status = await api.status();
      setState({ settings: updated, status, saving: false, notice: "Saved. Restart any active streams to pick up the new feed." });
    } catch (err) {
      setState({ saving: false, error: err.message || String(err) });
    }
  }

  function render() {
    root.innerHTML = "";
    const wrapper = document.createElement("section");
    wrapper.className = "settings-shell";

    const heading = document.createElement("header");
    heading.className = "settings-shell__header";
    const title = document.createElement("h1");
    title.textContent = "Settings";
    heading.appendChild(title);
    const subtitle = document.createElement("p");
    subtitle.className = "settings-shell__subtitle";
    subtitle.textContent = "Operator-editable runtime knobs. Changes persist to data/system_settings.json and override the equivalent ALPACA_* env vars.";
    heading.appendChild(subtitle);
    wrapper.appendChild(heading);

    if (state.loading) {
      wrapper.appendChild(buildLoadingShell());
      root.appendChild(wrapper);
      return;
    }
    if (state.error) {
      wrapper.appendChild(buildErrorShell(state.error));
      root.appendChild(wrapper);
      return;
    }

    wrapper.appendChild(buildStreamingPanel());
    wrapper.appendChild(buildSecretsPanel());
    root.appendChild(wrapper);
  }

  function buildLoadingShell() {
    const el = document.createElement("section");
    el.className = "loading-shell";
    el.innerHTML = `<div class="loading-shell__spinner" aria-hidden="true"></div><div><h1>Loading…</h1><p>Fetching runtime settings.</p></div>`;
    return el;
  }

  function buildErrorShell(message) {
    const el = document.createElement("section");
    el.className = "loading-shell loading-shell--error";
    el.setAttribute("role", "alert");
    el.innerHTML = `<div><h1>Could not load settings</h1><p>${escapeHtml(message)}</p><p class="loading-shell__hint">Verify the backend is running and /api/v1/system/settings is reachable.</p></div>`;
    return el;
  }

  function buildStreamingPanel() {
    const panel = document.createElement("section");
    panel.className = "panel settings-panel";

    const header = document.createElement("header");
    header.innerHTML = "<h2>Streaming</h2>";
    panel.appendChild(header);

    const form = document.createElement("form");
    form.className = "settings-form";
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      save(form);
    });

    // Test stream toggle
    const testWrap = document.createElement("label");
    testWrap.className = "settings-toggle";
    const testInput = document.createElement("input");
    testInput.type = "checkbox";
    testInput.name = "alpaca_use_test_stream";
    testInput.checked = !!state.settings.alpaca_use_test_stream;
    const testText = document.createElement("span");
    testText.innerHTML = `<strong>Test stream (FAKEPACA)</strong><span class="settings-help">24/7 synthetic bars for off-hours testing. Overrides the data-feed selection below.</span>`;
    testWrap.appendChild(testInput);
    testWrap.appendChild(testText);
    form.appendChild(testWrap);

    // Data feed dropdown
    const feedWrap = document.createElement("label");
    feedWrap.className = "settings-field";
    feedWrap.innerHTML = `<span><strong>Data feed</strong><span class="settings-help">Picks the Alpaca StockDataStream feed when the test stream is off.</span></span>`;
    const feedSelect = document.createElement("select");
    feedSelect.name = "alpaca_data_feed";
    for (const feed of DATA_FEEDS) {
      const opt = document.createElement("option");
      opt.value = feed.value;
      opt.textContent = feed.label;
      if (feed.value === state.settings.alpaca_data_feed) opt.selected = true;
      feedSelect.appendChild(opt);
    }
    feedWrap.appendChild(feedSelect);
    form.appendChild(feedWrap);

    // Default symbol
    const symbolWrap = document.createElement("label");
    symbolWrap.className = "settings-field";
    symbolWrap.innerHTML = `<span><strong>Default symbol</strong><span class="settings-help">Pre-fills Chart Lab when no symbol has been typed.</span></span>`;
    const symbolInput = document.createElement("input");
    symbolInput.type = "text";
    symbolInput.name = "chart_lab_default_symbol";
    symbolInput.maxLength = 12;
    symbolInput.value = state.settings.chart_lab_default_symbol || "SPY";
    symbolWrap.appendChild(symbolInput);
    form.appendChild(symbolWrap);

    const actions = document.createElement("div");
    actions.className = "settings-form__actions";
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.textContent = state.saving ? "Saving…" : "Save settings";
    submit.disabled = state.saving;
    actions.appendChild(submit);
    if (state.notice) {
      const note = document.createElement("span");
      note.className = "settings-form__notice";
      note.textContent = state.notice;
      actions.appendChild(note);
    }
    form.appendChild(actions);

    panel.appendChild(form);

    if (state.status) {
      const live = document.createElement("p");
      live.className = "settings-form__live";
      const feed = (state.status.alpaca_data_feed || "iex").toUpperCase();
      live.textContent = `Live: ${state.status.alpaca_test_stream ? "FAKEPACA test stream" : `${feed} feed`} · endpoint ${state.status.alpaca_endpoint}`;
      panel.appendChild(live);

      const note = document.createElement("p");
      note.className = "settings-help";
      note.style.marginTop = "6px";
      note.textContent = "Precedence: .env always wins; the values above only take effect for knobs not set in .env. To override .env, comment the line out and restart uvicorn.";
      panel.appendChild(note);
    }

    return panel;
  }

  function buildSecretsPanel() {
    const panel = document.createElement("section");
    panel.className = "panel settings-panel settings-panel--secrets";
    panel.innerHTML = `
      <header><h2>Credentials</h2></header>
      <p>Alpaca API credentials live in <code>.env</code> (not in this UI) so they never end up in the runtime settings JSON or HTTP responses.</p>
      <dl class="settings-credentials">
        <div><dt>ALPACA_API_KEY</dt><dd>${state.status?.alpaca_credentials_present ? "Configured" : "Missing"}</dd></div>
        <div><dt>ALPACA_BASE_URL</dt><dd>${escapeHtml(state.status?.alpaca_endpoint || "default")}</dd></div>
        <div><dt>Environment</dt><dd>${escapeHtml(state.status?.operator_environment || "unknown")}</dd></div>
      </dl>
      <p class="settings-help">To rotate credentials or switch paper ⇄ live, edit <code>.env</code> and restart the backend.</p>
    `;
    return panel;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  render();
  refresh();

  return { state, refresh };
}
