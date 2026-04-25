import { createServicesApi } from "./api/services.js";

const MASKED = "********";

const RESOLVER_MODES = {
  auto: "Auto (Recommended)",
  default: "Default (system default)",
  explicit: "Manual (explicit selection)"
};

const SERVICE_ICONS = {
  alpaca: "A",
  yahoo: "Y",
  future: "F",
  groq: "G",
  claude: "C",
  openai: "O",
  codex: "X",
  unknown: "S"
};

const TIMEFRAME_OPTIONS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"];
const CONSUMER_OPTIONS = ["chart_lab", "sim_lab", "backtest", "broker_runtime", "operations_preview"];
const SERVICE_PURPOSES = ["warmup", "signal_preview", "simulation_replay", "backtest", "runtime_trading", "long_horizon_analysis"];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function sanitizePayloadEntry(value) {
  if (value === null || value === undefined || value === "") {
    return undefined;
  }
  if (value === MASKED) {
    return undefined;
  }
  const normalized = String(value).trim();
  return normalized.length ? normalized : undefined;
}

function compactPayload(payload) {
  return Object.fromEntries(
    Object.entries(payload)
      .map(([key, value]) => [key, sanitizePayloadEntry(value)])
      .filter(([, value]) => value !== undefined)
  );
}

function renderSelectOptions(values, currentValue) {
  return values
    .map(
      ([value, label]) => `<option value="${escapeHtml(value)}" ${value === currentValue ? "selected" : ""}>${escapeHtml(label)}</option>`
    )
    .join("");
}

function boolLabel(value) {
  return value ? "yes" : "no";
}

function formatDate(value) {
  if (!value) return "not validated";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function formatDateRange(intent = {}) {
  const start = intent.start_at || "";
  const end = intent.end_at || "";
  if (!start && !end) {
    return "live or latest available";
  }
  return `${start || "open start"} to ${end || "open end"}`;
}

function serviceDefault(services = []) {
  return services.find((service) => service.is_default);
}

function serviceIcon(provider) {
  const code = (provider || "unknown").toLowerCase();
  return SERVICE_ICONS[code] || SERVICE_ICONS.unknown;
}

function serviceModeLabel(service, type) {
  if (type === "market") {
    if (service.provider === "yahoo" || service.provider === "future") return "historical";
    return service.mode || "paper";
  }
  if (service.provider === "future") return "none";
  return "keyed";
}

function serviceStatusClass(status) {
  if (status === "disabled") return "status-danger";
  if (status === "invalid") return "status-blocked";
  if (status === "valid") return "status-running";
  return "";
}

function capabilityChips(capabilities = {}) {
  return Object.entries(capabilities)
    .filter(([, enabled]) => enabled === true)
    .map(([key]) => `<span class="status">${escapeHtml(key.replace("supports_", "").replaceAll("_", " "))}</span>`)
    .join("");
}

function renderServiceFlags(service, type) {
  const status = service.status || "unknown";
  return `<div class="service-flags">
    <span class="service-flag flag-${type === "market" ? "market" : "ai"}">${escapeHtml(service.provider || "unknown")}</span>
    <span class="service-flag flag-${status}">${escapeHtml(status)}</span>
    <span class="service-flag flag-mode">${escapeHtml(serviceModeLabel(service, type))}</span>
    ${service.is_default ? `<span class="service-flag flag-default">default</span>` : ""}
  </div>`;
}

function renderSummaryCards({ marketData = [], ai = [] }) {
  const allServices = [...marketData, ...ai];
  const invalid = allServices.filter((service) => service.status === "invalid").length;
  const disabled = allServices.filter((service) => service.status === "disabled").length;
  const draft = allServices.filter((service) => service.status === "draft").length;
  return `<section class="state-strip">
    <article><span>Default Market Data Service</span><strong>${escapeHtml(serviceDefault(marketData)?.name || "None configured")}</strong></article>
    <article><span>Default AI Service</span><strong>${escapeHtml(serviceDefault(ai)?.name || "None configured")}</strong></article>
    <article><span>Service Health</span><strong>${marketData.length + ai.length} configured · ${invalid} invalid · ${disabled} disabled · ${draft} draft</strong></article>
  </section>`;
}

function ServiceFormModal(state, listType) {
  if (listType === "market") {
    return renderMarketDataForm(state.marketDataFormState || {});
  }
  return renderAiForm(state.aiFormState || {});
}

function ServiceDetailPanel(service, type) {
  return type === "market" ? renderMarketDataRow(service) : renderAiRow(service);
}

function ServiceTable(services, listType, formState = {}) {
  const noDataText = listType === "market" ? "No Market Data Services configured." : "No AI Services configured.";
  const rows = services.map((service) => ServiceDetailPanel(service, listType)).join("");
  return `<section class="service-workspace">
    <div class="service-toolbar">
      <h2>${listType === "market" ? "Market Data Services" : "AI Services"}</h2>
      <button type="button" data-action="show-${listType === "market" ? "market-data-form" : "ai-form"}">Add ${listType === "market" ? "Market Data Service" : "AI Service"}</button>
    </div>
    ${ServiceFormModal({ marketDataFormState: formState, aiFormState: formState }, listType)}
    <div class="service-table">${rows || `<p class=\"empty\">${noDataText}</p>`}</div>
  </section>`;
}

function renderMarketDataRow(service) {
  const status = service.status || "unknown";
  return `<article class="summary-card service-card ${service.is_default ? "service-default" : ""} ${status === "disabled" ? "service-disabled" : ""}">
    <header>
      <div class="service-header">
        <span class="service-icon service-icon-market">${escapeHtml(serviceIcon(service.provider))}</span>
        <h3>${escapeHtml(service.name)}</h3>
      </div>
      <span class="status ${serviceStatusClass(status)}">${escapeHtml(status)}</span>
    </header>
    ${renderServiceFlags(service, "market")}
    <dl class="detail-grid">
      <div><dt>Provider</dt><dd>${escapeHtml(service.provider || "unknown")}</dd></div>
      <div><dt>Mode</dt><dd>${escapeHtml(service.mode || "none")}</dd></div>
      <div><dt>Default</dt><dd>${service.is_default ? "yes" : "no"}</dd></div>
      <div><dt>Credentials</dt><dd>${(service.has_api_key || service.has_api_secret) ? MASKED : "not required"}</dd></div>
      <div><dt>Validation</dt><dd>${escapeHtml(service.validation_status || "not validated")} · ${escapeHtml(service.validation_message || "pending verification")}</dd></div>
      <div><dt>Last validated</dt><dd>${formatDate(service.last_validated_at)}</dd></div>
    </dl>
    <div class="chip-row" aria-label="Capability summary">${capabilityChips(service.capabilities)}</div>
    <div class="button-row">
      <button type="button" data-action="edit-market-data" data-id="${escapeHtml(service.id)}">Edit</button>
      <button type="button" data-action="validate-market-data" data-id="${escapeHtml(service.id)}">Validate</button>
      <button type="button" data-action="default-market-data" data-id="${escapeHtml(service.id)}">Set default</button>
      <button type="button" data-action="disable-market-data" data-id="${escapeHtml(service.id)}">Disable</button>
    </div>
  </article>`;
}

function renderAiRow(service) {
  const status = service.status || "unknown";
  return `<article class="summary-card service-card ${service.is_default ? "service-default" : ""} ${status === "disabled" ? "service-disabled" : ""}">
    <header>
      <div class="service-header">
        <span class="service-icon service-icon-ai">${escapeHtml(serviceIcon(service.provider))}</span>
        <h3>${escapeHtml(service.name)}</h3>
      </div>
      <span class="status ${serviceStatusClass(status)}">${escapeHtml(status)}</span>
    </header>
    ${renderServiceFlags(service, "ai")}
    <dl class="detail-grid">
      <div><dt>Provider</dt><dd>${escapeHtml(service.provider || "unknown")}</dd></div>
      <div><dt>Default</dt><dd>${service.is_default ? "yes" : "no"}</dd></div>
      <div><dt>Capability</dt><dd>${escapeHtml(service.capability_label || "unknown")}</dd></div>
      <div><dt>Credentials</dt><dd>${service.has_api_key ? MASKED : "not saved"}</dd></div>
      <div><dt>Validation</dt><dd>${escapeHtml(service.validation_status || "not validated")} · ${escapeHtml(service.validation_message || "pending verification")}</dd></div>
      <div><dt>Last validated</dt><dd>${formatDate(service.last_validated_at)}</dd></div>
    </dl>
    <div class="button-row">
      <button type="button" data-action="edit-ai" data-id="${escapeHtml(service.id)}">Edit</button>
      <button type="button" data-action="validate-ai" data-id="${escapeHtml(service.id)}">Validate</button>
      <button type="button" data-action="default-ai" data-id="${escapeHtml(service.id)}">Set default</button>
      <button type="button" data-action="disable-ai" data-id="${escapeHtml(service.id)}">Disable</button>
    </div>
  </article>`;
}

function renderMarketDataForm(formState = {}, canUseProvider = "alpaca") {
  const provider = (formState.provider || canUseProvider || "alpaca").toLowerCase();
  const mode = formState.mode || "paper";
  const isEditing = Boolean(formState.id);
  const actionText = isEditing ? "Update Market Data Service" : "Save Market Data Service";
  return `<form class=\"account-form service-form\" data-form=\"market-data\">
    <input type=\"hidden\" name=\"service_id\" value=\"${escapeHtml(formState.id || "")}\">
    <label><span>Name</span><input name=\"name\" required value=\"${escapeHtml(formState.name || "")}\"></label>
    <label><span>Provider</span><select name=\"provider\" data-provider-select=\"market-data\">${renderSelectOptions([["alpaca", "Alpaca"], ["yahoo", "Yahoo"], ["future", "Future"]], provider)}</select></label>
    <div data-provider-body=\"alpaca\" class=\"provider-body\" style=\"display:${provider === "alpaca" ? "grid" : "none"}\">
      <label><span>Mode</span><select name=\"mode\">${renderSelectOptions([["paper", "paper"], ["live", "live"]], mode)}</select></label>
      <label><span>API key</span><input name=\"api_key\" autocomplete=\"off\" placeholder=\"${MASKED}\" type=\"password\"><small class=\"helper\">${formState.id ? "Leave blank to keep existing key." : "Enter API key."}</small></label>
      <label><span>API secret</span><input name=\"api_secret\" type=\"password\" autocomplete=\"off\" placeholder=\"${MASKED}\"><small class=\"helper\">${formState.id ? "Leave blank to keep existing secret." : "Enter API secret."}</small></label>
    </div>
    <div data-provider-body=\"yahoo\" class=\"provider-body\" style=\"display:${provider === "yahoo" ? "grid" : "none"}\">
      <label><span>Source note</span><p class=\"helper\">Yahoo provides historical data only (no streaming).</p></label>
    </div>
    <div data-provider-body=\"future\" class=\"provider-body\" style=\"display:${provider === "future" ? "grid" : "none"}\">
      <label><span>Source note</span><p class=\"helper\">Reserved provider for future market-data integration.</p></label>
    </div>
    <button type=\"submit\">${actionText}</button>
    ${isEditing ? `<button type=\"button\" data-action=\"cancel-market-data-edit\">Cancel</button>` : ""}
  </form>`;
}

function renderAiForm(formState = {}) {
  const provider = (formState.provider || "groq").toLowerCase();
  const capability = formState.capability_label || "fast";
  const isEditing = Boolean(formState.id);
  const actionText = isEditing ? "Update AI Service" : "Save AI Service";
  const showKey = provider !== "future";
  return `<form class=\"account-form service-form\" data-form=\"ai\">
    <input type=\"hidden\" name=\"service_id\" value=\"${escapeHtml(formState.id || "")}\">
    <label><span>Name</span><input name=\"name\" required value=\"${escapeHtml(formState.name || "")}\"></label>
    <label><span>Provider</span><select name=\"provider\" data-provider-select=\"ai\">${renderSelectOptions([["groq", "Groq"], ["claude", "Claude"], ["openai", "OpenAI"], ["codex", "Codex"], ["future", "Future"]], provider)}</select></label>
    <div data-provider-body=\"ai-key\" style=\"display:${showKey ? "grid" : "none"}\">
      <label><span>API key</span><input name=\"api_key\" type=\"password\" autocomplete=\"off\" placeholder=\"${MASKED}\"><small class=\"helper\">${formState.id ? "Leave blank to keep existing key." : "Enter API key."}</small></label>
    </div>
    <label><span>Capability label</span><select name=\"capability_label\">${renderSelectOptions([["fast", "fast"], ["reasoning", "reasoning"], ["coding", "coding"], ["general", "general"], ["unknown", "unknown"]], capability)}</select></label>
    <button type=\"submit\">${actionText}</button>
    ${isEditing ? `<button type=\"button\" data-action=\"cancel-ai-edit\">Cancel</button>` : ""}
  </form>`;
}

function DataIntentPanel(state) {
  const resolver = state.resolutionPayload || {};
  const intent = resolver.intent || {};
  const selected = state.activeResolverMode || "auto";
  const modeLabel = RESOLVER_MODES[selected];
  const candidateServices = state.marketData.services || [];
  const selectedServiceId = resolver.selected_service_id || "";
  return `<section class="panel">
    <header>
      <h2>Data Source Resolver</h2>
      <div class=\"segmented-control\" role=\"group\" aria-label=\"Data Source Mode\">
        ${Object.entries(RESOLVER_MODES)
          .map(
            ([mode, label]) => `<button type="button" data-action="set-resolver-mode" data-mode="${mode}" class="${selected === mode ? "active" : ""}" aria-pressed="${selected === mode ? "true" : "false"}">${label}</button>`
          )
          .join("")}
      </div>
    </header>
    <p class=\"helper\">Auto means system chooses the best configured service, Default means only the default service, Manual means you explicitly choose a service.</p>
    <form class="account-form service-form" data-form="resolver-intent">
      <label><span>Consumer</span><select name="consumer">${renderSelectOptions(CONSUMER_OPTIONS.map((value) => [value, value]), intent.consumer || "backtest")}</select></label>
      <label><span>Timeframe</span><select name="timeframe">${renderSelectOptions(TIMEFRAME_OPTIONS.map((value) => [value, value]), intent.timeframe || "1d")}</select></label>
      <label><span>Purpose</span><select name="purpose">${renderSelectOptions(SERVICE_PURPOSES.map((value) => [value, value]), intent.purpose || "backtest")}</select></label>
      <label><span>Mode</span><select name="mode">${renderSelectOptions([["batch", "batch"], ["replay", "replay"], ["live_preview", "live_preview"], ["live_runtime", "live_runtime"]], intent.mode || "replay")}</select></label>
      <label><span>Symbols (comma-separated)</span><input name=\"symbols\" value=\"${escapeHtml((intent.symbols || ["SPY"]).join(", "))}\"></label>
      <label><span>Start date/time (ISO optional)</span><input name=\"start_at\" value=\"${escapeHtml(intent.start_at || "")}\" placeholder=\"2025-01-01T00:00:00Z\"></label>
      <label><span>End date/time (ISO optional)</span><input name=\"end_at\" value=\"${escapeHtml(intent.end_at || "")}\" placeholder=\"2026-01-01T00:00:00Z\"></label>
      <label class=\"checkbox-label\"><input type=\"checkbox\" name=\"requires_streaming\" ${intent.requires_streaming ? "checked" : ""}><span>Streaming required</span></label>
      <label class=\"checkbox-label\"><input type=\"checkbox\" name=\"requires_intraday\" ${intent.requires_intraday ? "checked" : ""}><span>Intraday required</span></label>
      <div class=\"service-mode-indicator\"><strong>Mode:</strong> ${escapeHtml(modeLabel)}</div>
    </form>
    <div class="button-row">
      <button type="button" data-action="run-resolution">Resolve Service</button>
    </div>
    <div class="service-guard-text" style="${selected === "explicit" ? "display:grid" : "display:none"}">
      <p><strong>Manual mode:</strong> choose a specific service from the current list.</p>
      <label class="manual-service-select">
        <span>Explicitly selected service</span>
        <select name=\"selected_service_id\">
          ${candidateServices
            .map((service) => `<option value="${escapeHtml(service.id)}" ${selectedServiceId === service.id ? "selected" : ""}>${escapeHtml(service.name)} · ${escapeHtml(service.provider || "market")}</option>`)
            .join("")}
        </select>
      </label>
    </div>
  </section>`;
}

function ResolverResultPanel(result, selectedMode, services = []) {
  const resolution = result || {};
  const intent = resolution.intent || {};
  const selected = {
    service_name: resolution.selected_service_name || "No compatible service",
    provider: resolution.provider || "none",
    explanation: resolution.explanation || ""
  };
  const rejected = resolution.rejected_candidates || [];
  const explicitNotice = resolution.selection_mode === "explicit" ? "Manual selection is enforced and only the selected candidate is considered." : "";
  return `<section class="panel data-intent-panel">
    <h3>Detected Intent</h3>
    <div class=\"resolver-grid\">
      <section class=\"resolver-block\">
        <dl>
          <div><dt>Consumer</dt><dd>${escapeHtml(intent.consumer || "not set")}</dd></div>
          <div><dt>Timeframe</dt><dd>${escapeHtml(intent.timeframe || "not set")}</dd></div>
          <div><dt>Date range</dt><dd>${escapeHtml(formatDateRange(intent))}</dd></div>
          <div><dt>Streaming required</dt><dd>${escapeHtml(boolLabel(Boolean(intent.requires_streaming)))}</dd></div>
          <div><dt>Intraday required</dt><dd>${escapeHtml(boolLabel(Boolean(intent.requires_intraday)))}</dd></div>
          <div><dt>Decision mode</dt><dd>${escapeHtml(RESOLVER_MODES[selectedMode || "auto"] || selectedMode || "auto")}</dd></div>
        </dl>
      </section>
      <section class=\"resolver-block\">
        <h4>Selected Service</h4>
        <dl>
          <div><dt>Service</dt><dd>${escapeHtml(selected.service_name || "No compatible service")}</dd></div>
          <div><dt>Provider</dt><dd>${escapeHtml(selected.provider || "none")}</dd></div>
          <div><dt>Reason code</dt><dd>${escapeHtml(resolution.reason_code || "not provided")}</dd></div>
          <div><dt>Why selected</dt><dd>${escapeHtml(selected.explanation || resolution.explanation || "No resolver explanation reported.")}</dd></div>
          <div><dt>Decision</dt><dd>${escapeHtml(resolution.decision || "unknown")}</dd></div>
        </dl>
      </section>
    </div>
    <p class=\"helper\">${escapeHtml(explicitNotice)}</p>
    <details class="rejected-services">
      <summary>Rejected candidates (${rejected.length})</summary>
      ${
        rejected.length
          ? `<ul>${rejected.map((candidate) => `<li><strong>${escapeHtml(candidate.service_id)}</strong><span>${escapeHtml(candidate.explanation || candidate.reason_code || "not selected")}</span></li>`).join("")}</ul>`
          : `<p class="empty">No rejected services.</p>`
      }
    </details>
  </section>`;
}

function renderLogs(marketData, ai) {
  const rows = [...marketData, ...ai].filter((service) => service.last_validated_at || service.validation_status);
  return `<section class="panel"><h3>Validation History</h3><div class=\"record-list\">${rows
    .map(
      (service) =>
        `<article class="record-card">
          <h4>${escapeHtml(service.name)}</h4>
          <p>${escapeHtml(service.validation_status || "not validated")}: ${escapeHtml(service.validation_message || "")}</p>
          <p class="empty">Last validated: ${formatDate(service.last_validated_at)}</p>
        </article>`
    )
    .join("") || `<p class="empty">No validation history yet.</p>`}</div></section>`;
}

function normalizeMarketDataForSubmit(data) {
  const provider = (data.get("provider") || "").toLowerCase();
  const mode = provider === "alpaca" ? data.get("mode") || "paper" : "none";
  if (provider === "alpaca") {
    return compactPayload({
      name: data.get("name"),
      provider,
      mode,
      api_key: data.get("api_key"),
      api_secret: data.get("api_secret")
    });
  }
  return compactPayload({
    name: data.get("name"),
    provider,
    mode
  });
}

function normalizeAiForSubmit(data) {
  return compactPayload({
    name: data.get("name"),
    provider: data.get("provider"),
    api_key: data.get("api_key"),
    capability_label: data.get("capability_label")
  });
}

function normalizeResolverPayload(formData, mode, services) {
  const symbols = String(formData.get("symbols") || "SPY")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const payload = {
    selection_mode: mode === "default" ? "default" : mode === "explicit" ? "explicit" : "auto",
    intent: {
      consumer: formData.get("consumer") || "backtest",
      mode: formData.get("mode") || "replay",
      symbols: symbols.length ? symbols : ["SPY"],
      timeframe: formData.get("timeframe") || "1d",
      purpose: formData.get("purpose") || "backtest",
      start_at: sanitizePayloadEntry(formData.get("start_at")),
      end_at: sanitizePayloadEntry(formData.get("end_at")),
      requires_streaming: formData.has("requires_streaming"),
      requires_intraday: formData.has("requires_intraday"),
      tolerance: "normal",
      requires_historical: true,
      requires_realtime: false
    }
  };
  if (mode === "explicit") {
    payload.selected_service_id = formData.get("selected_service_id") || (services[0] ? services[0].id : undefined);
  }
  return payload;
}

function applyMarketDataFields(form) {
  if (!form) return;
  const provider = form.querySelector("select[name='provider']")?.value || "alpaca";
  const alpacaFields = form.querySelectorAll("[data-provider-body='alpaca']");
  const yahooFields = form.querySelectorAll("[data-provider-body='yahoo']");
  const futureFields = form.querySelectorAll("[data-provider-body='future']");
  const isAlpaca = provider === "alpaca";
  const isYahoo = provider === "yahoo";
  const isFuture = provider === "future";
  alpacaFields.forEach((node) => {
    node.style.display = isAlpaca ? "grid" : "none";
  });
  yahooFields.forEach((node) => {
    node.style.display = isYahoo ? "grid" : "none";
  });
  futureFields.forEach((node) => {
    node.style.display = isFuture ? "grid" : "none";
  });
}

function applyAiFields(form) {
  if (!form) return;
  const provider = form.querySelector("select[name='provider']")?.value || "";
  const keyRow = form.querySelector("[data-provider-body='ai-key']");
  if (keyRow) {
    keyRow.style.display = provider === "future" ? "none" : "grid";
  }
}

export function renderServicesCenter(state = {}) {
  const marketData = state.marketData?.services || [];
  const ai = state.ai?.services || [];
  const activeTab = state.activeTab || "market-data";
  const marketDataFormState = state.marketDataFormState || {};
  const aiFormState = state.aiFormState || {};
  return `<section class="page-heading">
    <div>
      <p class=\"eyebrow\">External capabilities</p>
      <h1>Services Center</h1>
      <p class=\"helper\">Market data and AI services are configured here. Decisions are shown through the resolver, not by guesswork.</p>
    </div>
  </section>
  ${renderSummaryCards({ marketData, ai })}
  <section class=\"panel\">
    <header>
      <h2>Service Controls</h2>
      <div class=\"segmented-control\" role=\"tablist\">
        <button type=\"button\" data-tab=\"market-data\" class=\"${activeTab === "market-data" ? "active" : ""}\">Market Data Services</button>
        <button type=\"button\" data-tab=\"ai\" class=\"${activeTab === "ai" ? "active" : ""}\">AI Services</button>
        <button type=\"button\" data-tab=\"logs\" class=\"${activeTab === "logs" ? "active" : ""}\">Service Logs</button>
      </div>
    </header>
    ${activeTab === "ai" ? ServiceTable(ai, "ai", aiFormState) : activeTab === "logs" ? renderLogs(marketData, ai) : ServiceTable(marketData, "market", marketDataFormState)}
  </section>
  ${DataIntentPanel(state)}
  ${ResolverResultPanel(state.resolution || {}, state.activeResolverMode || "auto", marketData)}`;
}

export async function mountServicesCenter(root, client = createServicesApi()) {
  const state = {
    marketData: { services: [] },
    ai: { services: [] },
    activeTab: "market-data",
    marketDataFormState: { provider: "alpaca", mode: "paper", name: "", id: null },
    aiFormState: { provider: "groq", capability_label: "fast", name: "", id: null },
    activeResolverMode: "auto",
    resolutionPayload: {
      intent: {
        consumer: "backtest",
        mode: "replay",
        symbols: ["SPY"],
        timeframe: "1d",
        purpose: "backtest",
        start_at: "2024-01-01T00:00:00Z",
        end_at: "2025-01-01T00:00:00Z",
        requires_streaming: false,
        requires_intraday: false,
        tolerance: "normal",
        requires_historical: true,
        requires_realtime: false
      },
      selected_service_id: null
    }
  };

  function syncEditStateFromServices(listType, serviceId) {
    if (!serviceId) return;
    if (listType === "market") {
      const service = state.marketData.services.find((item) => item.id === serviceId);
      if (service) {
        state.marketDataFormState = {
          id: service.id,
          name: service.name || "",
          provider: service.provider || "alpaca",
          mode: service.mode || "paper",
          has_api_key: service.has_api_key || false,
          has_api_secret: service.has_api_secret || false
        };
      }
      return;
    }
    const service = state.ai.services.find((item) => item.id === serviceId);
    if (service) {
      state.aiFormState = {
        id: service.id,
        name: service.name || "",
        provider: service.provider || "groq",
        has_api_key: service.has_api_key || false,
        capability_label: service.capability_label || "fast"
      };
    }
  }

  async function refresh() {
    state.marketData = await client.listMarketData();
    state.ai = await client.listAi();
    root.innerHTML = renderServicesCenter(state);
    applyMarketDataFields(root.querySelector("form[data-form='market-data']"));
    applyAiFields(root.querySelector("form[data-form='ai']"));
    const resolverForm = root.querySelector("form[data-form='resolver-intent']");
    if (resolverForm) {
      const mode = state.activeResolverMode || "auto";
      resolverForm.dataset.explicitSelected = mode === "explicit" ? "yes" : "no";
    }
  }

  function getActiveDefault(listType) {
    const list = listType === "market" ? state.marketData.services : state.ai.services;
    return list.find((service) => service.is_default) || null;
  }

  async function resolveFromForm() {
    const form = root.querySelector("form[data-form='resolver-intent']");
    if (!form) return;
    const data = new FormData(form);
    const payload = normalizeResolverPayload(data, state.activeResolverMode || "auto", state.marketData.services);
    const selectedServiceId = data.get("selected_service_id");
    if (state.activeResolverMode === "explicit" && selectedServiceId) {
      payload.selected_service_id = selectedServiceId;
    }
    state.resolution = await client.resolveMarketData(payload);
    await refresh();
  }

  root.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-tab], button[data-action]");
    if (!button) return;
    const id = button.dataset.id;
    const action = button.dataset.action;

    if (button.dataset.tab) {
      state.activeTab = button.dataset.tab;
      root.innerHTML = renderServicesCenter(state);
      applyMarketDataFields(root.querySelector("form[data-form='market-data']"));
      applyAiFields(root.querySelector("form[data-form='ai']"));
      return;
    }

    if (action === "set-resolver-mode") {
      state.activeResolverMode = button.dataset.mode || "auto";
      root.innerHTML = renderServicesCenter(state);
      return;
    }

    if (action === "resolve-sample" || action === "run-resolution") {
      await resolveFromForm();
      return;
    }

    if (action === "validate-market-data") await client.validateMarketData(id);
    if (action === "disable-market-data") {
      const service = state.marketData.services.find((svc) => svc.id === id);
      if (service?.is_default) {
        const ok = window.confirm("This is the default Market Data service. Disabling it will remove the default. Continue?");
        if (!ok) return;
      }
      await client.disableMarketData(id);
    }
    if (action === "default-market-data") {
      const candidate = state.marketData.services.find((svc) => svc.id === id);
      const existingDefault = getActiveDefault("market");
      if (candidate && existingDefault && existingDefault.id !== candidate.id) {
        const ok = window.confirm(`Replace default "${existingDefault.name}" with "${candidate.name}"?`);
        if (!ok) return;
      }
      await client.setDefaultMarketData(id);
    }
    if (action === "validate-ai") await client.validateAi(id);
    if (action === "disable-ai") {
      const service = state.ai.services.find((svc) => svc.id === id);
      if (service?.is_default) {
        const ok = window.confirm("This is the default AI service. Disabling it will remove the default. Continue?");
        if (!ok) return;
      }
      await client.disableAi(id);
    }
    if (action === "default-ai") {
      const candidate = state.ai.services.find((svc) => svc.id === id);
      const existingDefault = getActiveDefault("ai");
      if (candidate && existingDefault && existingDefault.id !== candidate.id) {
        const ok = window.confirm(`Replace default "${existingDefault.name}" with "${candidate.name}"?`);
        if (!ok) return;
      }
      await client.setDefaultAi(id);
    }
    if (action === "edit-market-data") syncEditStateFromServices("market", id);
    if (action === "edit-ai") syncEditStateFromServices("ai", id);
    if (action === "cancel-market-data-edit") state.marketDataFormState = { provider: "alpaca", mode: "paper", name: "", id: null };
    if (action === "cancel-ai-edit") state.aiFormState = { provider: "groq", capability_label: "fast", name: "", id: null };

    if (action === "show-market-data-form") state.marketDataFormState = { provider: "alpaca", mode: "paper", name: "", id: null };
    if (action === "show-ai-form") state.aiFormState = { provider: "groq", capability_label: "fast", name: "", id: null };

    if (action === "default-market-data" || action === "disable-market-data" || action === "validate-market-data" || action === "default-ai" || action === "disable-ai" || action === "validate-ai" || action.startsWith("edit") || action.startsWith("cancel") || action.startsWith("show")) {
      await refresh();
    }
  });

  root.addEventListener("change", (event) => {
    const form = event.target.closest("form");
    if (!form) return;

    if (event.target.matches("select[data-provider-select='market-data']")) {
      state.marketDataFormState = { ...state.marketDataFormState, provider: event.target.value };
      applyMarketDataFields(form);
      return;
    }
    if (event.target.matches("select[data-provider-select='ai']")) {
      state.aiFormState = { ...state.aiFormState, provider: event.target.value };
      applyAiFields(form);
      return;
    }
  });

  root.addEventListener("submit", async (event) => {
    const form = event.target.closest("form[data-form='market-data'], form[data-form='ai']");
    if (!form) return;
    event.preventDefault();
    const data = new FormData(form);
    if (form.dataset.form === "market-data") {
      const payload = normalizeMarketDataForSubmit(data);
      const serviceId = sanitizePayloadEntry(data.get("service_id"));
      if (serviceId) await client.updateMarketData(serviceId, payload);
      else await client.createMarketData(payload);
      state.marketDataFormState = { provider: "alpaca", mode: "paper", name: "", id: null };
    } else {
      const payload = normalizeAiForSubmit(data);
      const serviceId = sanitizePayloadEntry(data.get("service_id"));
      if (serviceId) await client.updateAi(serviceId, payload);
      else await client.createAi(payload);
      state.aiFormState = { provider: "groq", capability_label: "fast", name: "", id: null };
    }
    await refresh();
  });

  await refresh();
}

