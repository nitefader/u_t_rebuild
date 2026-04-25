import { createServicesApi } from "./api/services.js";

const MASKED = "********";

const RESOLVER_MODES = {
  auto: "Auto (Recommended)",
  default: "Default",
  explicit: "Manual Selection"
};

const MODE_COPY = {
  auto: "System selects the best compatible service based on the request.",
  default: "Use the configured default service only. If incompatible, fail clearly.",
  explicit: "Use the selected service only. If incompatible, fail clearly."
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
const DEFAULT_INTENT = {
  consumer: "backtest",
  mode: "replay",
  symbols: ["SPY"],
  timeframe: "1d",
  purpose: "backtest",
  start_at: "",
  end_at: "",
  requires_streaming: false,
  requires_intraday: false,
  requires_historical: true,
  requires_realtime: false,
  tolerance: "normal"
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function sanitizePayloadEntry(value) {
  if (value === null || value === undefined || value === "") return undefined;
  if (value === MASKED) return undefined;
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
    .map(([value, label]) => `<option value="${escapeHtml(value)}" ${value === currentValue ? "selected" : ""}>${escapeHtml(label)}</option>`)
    .join("");
}

function formatDate(value) {
  if (!value) return "not validated";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function formatDateRange(intent = {}) {
  if (!intent.start_at && !intent.end_at) return "live or latest available";
  return `${intent.start_at || "open start"} to ${intent.end_at || "open end"}`;
}

function boolLabel(value) {
  return value ? "Yes" : "No";
}

function normalizeIntent(intent = {}) {
  return {
    ...DEFAULT_INTENT,
    ...intent,
    symbols: Array.isArray(intent.symbols) && intent.symbols.length ? intent.symbols : DEFAULT_INTENT.symbols
  };
}

function serviceDefault(services = []) {
  return services.find((service) => service.is_default);
}

function serviceIcon(provider) {
  return SERVICE_ICONS[(provider || "unknown").toLowerCase()] || SERVICE_ICONS.unknown;
}

function serviceStatusClass(status) {
  if (status === "disabled") return "status-danger";
  if (status === "invalid") return "status-blocked";
  if (status === "valid") return "status-running";
  return "";
}

function serviceModeLabel(service, type) {
  if (type === "market") return service.mode || "none";
  return service.provider === "future" ? "none" : "keyed";
}

function capabilityList(capabilities = {}) {
  return Object.entries(capabilities)
    .filter(([, enabled]) => enabled === true)
    .map(([key]) => key.replace("supports_", "").replaceAll("_", " "));
}

function capabilityChips(capabilities = {}) {
  const capabilitiesFromBackend = capabilityList(capabilities);
  return capabilitiesFromBackend.length
    ? capabilitiesFromBackend.map((item) => `<span class="status">${escapeHtml(item)}</span>`).join("")
    : `<span class="empty">No capabilities reported.</span>`;
}

function capabilitySummary(capabilities = {}) {
  const capabilitiesFromBackend = capabilityList(capabilities);
  return capabilitiesFromBackend.length ? capabilitiesFromBackend.join(", ") : "No capabilities reported by backend";
}

function bestForItems(service, type) {
  if (type === "ai") {
    return [`${service.capability_label || "unknown"} advisory assistance`, "Generation and analysis only"];
  }
  const caps = service.capabilities || {};
  const items = [];
  if (caps.supports_streaming || caps.supports_realtime) items.push("Realtime or streaming-compatible requests");
  if (caps.supports_intraday) items.push("Intraday analysis and runtime data");
  if (caps.supports_historical) items.push("Historical bars and Feature Engine warmup");
  if (caps.supports_daily || caps.supports_weekly || caps.supports_monthly || caps.supports_long_range_history) {
    items.push("Daily, weekly, monthly, or long-range analysis");
  }
  return items.length ? items : ["No backend capabilities reported yet"];
}

function renderBestFor(service, type) {
  return `<section class="best-for">
    <h4>Best For</h4>
    <ul>${bestForItems(service, type).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
  </section>`;
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
  const marketDefault = serviceDefault(marketData);
  const aiDefault = serviceDefault(ai);
  const active = allServices.filter((service) => service.status !== "disabled").length;
  const invalid = allServices.filter((service) => service.status === "invalid").length;
  const disabled = allServices.filter((service) => service.status === "disabled").length;
  const draft = allServices.filter((service) => service.status === "draft").length;
  const issues = invalid + disabled + draft;
  const statusSummary = allServices.length ? `${invalid} invalid - ${disabled} disabled - ${draft} draft` : "No services configured yet.";
  return `<section class="state-strip">
    <article>
      <span>Default Market Data Service</span>
      <strong>${escapeHtml(marketDefault?.name || "Not configured")}</strong>
      <p class="helper">${marketDefault ? `Used for: ${escapeHtml(capabilitySummary(marketDefault.capabilities))}` : "Create or validate a Market Data Service before runtime data selection can use Default mode."}</p>
    </article>
    <article>
      <span>Default AI Service</span>
      <strong>${escapeHtml(aiDefault?.name || "Not configured")}</strong>
      <p class="helper">${aiDefault ? "AI is advisory only." : "AI is optional and does not control execution."}</p>
    </article>
    <article>
      <span>Service Health</span>
      <strong>${active} Active - ${issues} Issues</strong>
      <p class="helper">${escapeHtml(statusSummary)}</p>
    </article>
  </section>`;
}

function ServiceFormModal(state, listType) {
  return listType === "market" ? renderMarketDataForm(state.marketDataFormState || {}) : renderAiForm(state.aiFormState || {});
}

function ServiceDetailPanel(service, type) {
  return type === "market" ? renderMarketDataRow(service) : renderAiRow(service);
}

function ServiceTable(services, listType, formState = null) {
  const noDataText =
    listType === "market"
      ? "No Market Data Services configured. Add a Market Data Service to enable historical data, warmup, and future streaming."
      : "No AI Services configured. AI is optional. Add an AI Service when you are ready to use assisted generation or analysis.";
  const isOpen = Boolean(formState?.visible || formState?.id);
  return `<section class="service-workspace">
    <div class="service-toolbar">
      <h2>${listType === "market" ? "Market Data Services" : "AI Services"}</h2>
      <button type="button" data-action="show-${listType === "market" ? "market-data-form" : "ai-form"}">+ Add ${listType === "market" ? "Market Data Service" : "AI Service"}</button>
    </div>
    ${isOpen ? ServiceFormModal({ marketDataFormState: formState, aiFormState: formState }, listType) : ""}
    <div class="service-table">${services.map((service) => ServiceDetailPanel(service, listType)).join("") || `<p class="empty">${noDataText}</p>`}</div>
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
      <div><dt>Credentials</dt><dd>${service.has_api_key || service.has_api_secret ? MASKED : "not required"}</dd></div>
      <div><dt>Validation</dt><dd>${escapeHtml(service.validation_status || "not validated")} - ${escapeHtml(service.validation_message || "pending verification")}</dd></div>
      <div><dt>Last validated</dt><dd>${formatDate(service.last_validated_at)}</dd></div>
    </dl>
    <div class="chip-row" aria-label="Capability summary">${capabilityChips(service.capabilities)}</div>
    ${renderBestFor(service, "market")}
    <div class="button-row">
      <button type="button" data-action="edit-market-data" data-id="${escapeHtml(service.id)}">Edit</button>
      <button type="button" data-action="validate-market-data" data-id="${escapeHtml(service.id)}">Validate</button>
      <button type="button" data-action="default-market-data" data-id="${escapeHtml(service.id)}">Set Default</button>
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
      <div><dt>Validation</dt><dd>${escapeHtml(service.validation_status || "not validated")} - ${escapeHtml(service.validation_message || "pending verification")}</dd></div>
      <div><dt>Last validated</dt><dd>${formatDate(service.last_validated_at)}</dd></div>
    </dl>
    ${renderBestFor(service, "ai")}
    <p class="helper">AI services are advisory only. They cannot approve trades, override the Governor, or submit orders.</p>
    <div class="button-row">
      <button type="button" data-action="edit-ai" data-id="${escapeHtml(service.id)}">Edit</button>
      <button type="button" data-action="validate-ai" data-id="${escapeHtml(service.id)}">Validate</button>
      <button type="button" data-action="default-ai" data-id="${escapeHtml(service.id)}">Set Default</button>
      <button type="button" data-action="disable-ai" data-id="${escapeHtml(service.id)}">Disable</button>
    </div>
  </article>`;
}

function renderMarketDataForm(formState = {}) {
  const provider = (formState.provider || "alpaca").toLowerCase();
  const mode = formState.mode || "paper";
  const isEditing = Boolean(formState.id);
  const providerBody =
    provider === "alpaca"
      ? `<div data-provider-body="alpaca" class="provider-body">
          <label><span>Mode</span><select name="mode">${renderSelectOptions([["paper", "paper"], ["live", "live"]], mode)}</select></label>
          <label><span>API Key</span><input name="api_key" autocomplete="off" placeholder="${MASKED}" type="password"><small class="helper">${isEditing ? "Leave blank to keep existing key." : "Enter API key."}</small></label>
          <label><span>API Secret</span><input name="api_secret" autocomplete="off" placeholder="${MASKED}" type="password"><small class="helper">${isEditing ? "Leave blank to keep existing secret." : "Enter API secret."}</small></label>
          <p class="helper provider-note">Alpaca supports historical bars and streaming when credentials and entitlement allow it. Required for Broker Runtime intraday streaming.</p>
        </div>`
      : provider === "yahoo"
        ? `<div data-provider-body="yahoo" class="provider-body">
            <p class="helper provider-note">No credentials required. Yahoo is historical data only (no streaming) in this system. Best for daily, weekly, and monthly historical analysis when compatible.</p>
          </div>`
        : `<div data-provider-body="future" class="provider-body">
            <p class="helper provider-note">Reserved provider for future market-data integration.</p>
          </div>`;
  return `<form class="account-form service-form" data-form="market-data">
    <div class="form-intro">
      <h3>${isEditing ? "Edit Market Data Service" : "Create Market Data Service"}</h3>
      <p class="helper">Select a provider. Required fields update based on provider.</p>
    </div>
    <input type="hidden" name="service_id" value="${escapeHtml(formState.id || "")}">
    <label><span>Service Name</span><input name="name" required value="${escapeHtml(formState.name || "")}"></label>
    <label><span>Provider</span><select name="provider" data-provider-select="market-data">${renderSelectOptions([["alpaca", "Alpaca"], ["yahoo", "Yahoo"], ["future", "Future"]], provider)}</select></label>
    ${providerBody}
    <div class="button-row form-actions">
      <button type="button" data-action="cancel-market-data-edit">Cancel</button>
      <button type="button" data-action="validate-market-data" data-id="${escapeHtml(formState.id || "")}" ${formState.id ? "" : "disabled"}>Validate</button>
      <button type="submit">${isEditing ? "Save Changes" : "Save"}</button>
    </div>
  </form>`;
}

function renderAiForm(formState = {}) {
  const provider = (formState.provider || "groq").toLowerCase();
  const showKey = provider !== "future";
  const keyBody = showKey
    ? `<div data-provider-body="ai-key">
        <label><span>API Key</span><input name="api_key" autocomplete="off" placeholder="${MASKED}" type="password"><small class="helper">${formState.id ? "Leave blank to keep existing key." : "Enter API key."}</small></label>
      </div>`
    : "";
  return `<form class="account-form service-form" data-form="ai">
    <div class="form-intro">
      <h3>${formState.id ? "Edit AI Service" : "Create AI Service"}</h3>
      <p class="helper">AI is advisory only and cannot approve trades, override Governor, or submit orders.</p>
    </div>
    <input type="hidden" name="service_id" value="${escapeHtml(formState.id || "")}">
    <label><span>Service Name</span><input name="name" required value="${escapeHtml(formState.name || "")}"></label>
    <label><span>Provider</span><select name="provider" data-provider-select="ai">${renderSelectOptions([["groq", "Groq"], ["claude", "Claude"], ["openai", "OpenAI"], ["codex", "Codex"], ["future", "Future"]], provider)}</select></label>
    ${keyBody}
    <label><span>Capability Label</span><select name="capability_label">${renderSelectOptions([["fast", "fast"], ["reasoning", "reasoning"], ["coding", "coding"], ["general", "general"], ["unknown", "unknown"]], formState.capability_label || "fast")}</select></label>
    <div class="button-row form-actions">
      <button type="button" data-action="cancel-ai-edit">Cancel</button>
      <button type="button" data-action="validate-ai" data-id="${escapeHtml(formState.id || "")}" ${formState.id ? "" : "disabled"}>Validate</button>
      <button type="submit">${formState.id ? "Save Changes" : "Save"}</button>
    </div>
  </form>`;
}

function DataIntentPanel(state) {
  const resolverPayload = state.resolutionPayload || {};
  const intent = normalizeIntent(resolverPayload.intent || {});
  const selected = state.activeResolverMode || "auto";
  const candidateServices = state.marketData?.services || [];
  const selectedServiceId = resolverPayload.selected_service_id || "";
  return `<section class="panel">
    <header>
      <h2>Data Source Decision</h2>
      <div class="segmented-control" role="group" aria-label="Data Source Mode">
        ${Object.entries(RESOLVER_MODES)
          .map(([mode, label]) => `<button type="button" data-action="set-resolver-mode" data-mode="${mode}" class="${selected === mode ? "active" : ""}" aria-pressed="${selected === mode ? "true" : "false"}">${label}</button>`)
          .join("")}
      </div>
    </header>
    <p class="helper">${escapeHtml(MODE_COPY[selected] || MODE_COPY.auto)}</p>
    <form class="account-form service-form" data-form="resolver-intent">
      <label><span>Consumer</span><select name="consumer">${renderSelectOptions(CONSUMER_OPTIONS.map((value) => [value, value]), intent.consumer)}</select></label>
      <label><span>Timeframe</span><select name="timeframe">${renderSelectOptions(TIMEFRAME_OPTIONS.map((value) => [value, value]), intent.timeframe)}</select></label>
      <label><span>Purpose</span><select name="purpose">${renderSelectOptions(SERVICE_PURPOSES.map((value) => [value, value]), intent.purpose)}</select></label>
      <label><span>Mode</span><select name="mode">${renderSelectOptions([["batch", "batch"], ["replay", "replay"], ["live_preview", "live_preview"], ["live_runtime", "live_runtime"]], intent.mode)}</select></label>
      <label><span>Symbols</span><input name="symbols" value="${escapeHtml(intent.symbols.join(", "))}"></label>
      <label><span>Start Date/Time</span><input name="start_at" value="${escapeHtml(intent.start_at || "")}" placeholder="2025-01-01T00:00:00Z"></label>
      <label><span>End Date/Time</span><input name="end_at" value="${escapeHtml(intent.end_at || "")}" placeholder="2026-01-01T00:00:00Z"></label>
      <label class="checkbox-label"><input type="checkbox" name="requires_streaming" ${intent.requires_streaming ? "checked" : ""}><span>Streaming required</span></label>
      <label class="checkbox-label"><input type="checkbox" name="requires_intraday" ${intent.requires_intraday ? "checked" : ""}><span>Intraday required</span></label>
      <div class="service-mode-indicator"><strong>Mode:</strong> ${escapeHtml(RESOLVER_MODES[selected])}</div>
      <div class="service-guard-text" style="${selected === "explicit" ? "display:grid" : "display:none"}">
        <p><strong>Manual mode:</strong> choose a specific service from the current list.</p>
        ${
          candidateServices.length
            ? `<label class="manual-service-select">
                <span>Explicitly selected service</span>
                <select name="selected_service_id">${candidateServices.map((service) => `<option value="${escapeHtml(service.id)}" ${selectedServiceId === service.id ? "selected" : ""}>${escapeHtml(service.name)} - ${escapeHtml(service.provider || "market")}</option>`).join("")}</select>
              </label>`
            : `<p class="empty">No services available for selection. Create and validate a Market Data Service before using Auto, Default, or Manual selection.</p>`
        }
      </div>
    </form>
    <div class="button-row">
      <button type="button" data-action="run-resolution">Preview Service Decision</button>
    </div>
  </section>`;
}

function ResolverResultPanel(result, selectedMode, services = [], fallbackIntent = DEFAULT_INTENT) {
  const resolution = result || {};
  const hasResolution = Object.keys(resolution).length > 0;
  const intent = normalizeIntent(resolution.intent || fallbackIntent);
  const rejected = Array.isArray(resolution.rejected_candidates) ? resolution.rejected_candidates : [];
  const isSelected = hasResolution && resolution.decision === "selected";
  const explanation = resolution.explanation || "No resolver explanation returned. This is a backend contract issue.";
  return `<section class="panel data-intent-panel">
    <h3>Detected Intent</h3>
    <div class="resolver-grid">
      <section class="resolver-block">
        <dl>
          <div><dt>Consumer</dt><dd>${escapeHtml(intent.consumer)}</dd></div>
          <div><dt>Timeframe</dt><dd>${escapeHtml(intent.timeframe)}</dd></div>
          <div><dt>Date Range</dt><dd>${escapeHtml(formatDateRange(intent))}</dd></div>
          <div><dt>Streaming Required</dt><dd>${escapeHtml(boolLabel(Boolean(intent.requires_streaming)))}</dd></div>
          <div><dt>Intraday Required</dt><dd>${escapeHtml(boolLabel(Boolean(intent.requires_intraday)))}</dd></div>
          <div><dt>Purpose</dt><dd>${escapeHtml(intent.purpose)}</dd></div>
        </dl>
      </section>
      <section class="resolver-block ${hasResolution && !isSelected ? "resolver-error" : ""}">
        <h4>${!hasResolution ? "Service Decision Preview" : isSelected ? "Selected Service" : "No Compatible Service Found"}</h4>
        ${
          !hasResolution
            ? `<p class="empty">${services.length ? "Preview service selection to see the resolver decision." : "No services available for selection. Create and validate a Market Data Service before using Auto, Default, or Manual selection."}</p>`
            : isSelected
              ? `<dl>
                  <div><dt>Service</dt><dd>${escapeHtml(resolution.selected_service_name || "No service name returned")}</dd></div>
                  <div><dt>Provider</dt><dd>${escapeHtml(resolution.provider || "No provider returned")}</dd></div>
                  <div><dt>Selection Mode</dt><dd>${escapeHtml(resolution.selection_mode || selectedMode || "auto")}</dd></div>
                  <div><dt>Reason Code</dt><dd>${escapeHtml(resolution.reason_code || "not provided")}</dd></div>
                  <div><dt>Why Selected</dt><dd>${escapeHtml(explanation)}</dd></div>
                  <div><dt>Decision</dt><dd>${escapeHtml(resolution.decision || "unknown")}</dd></div>
                </dl>`
              : `<p><strong>Why:</strong> ${escapeHtml(explanation)}</p>
                <dl>
                  <div><dt>Reason Code</dt><dd>${escapeHtml(resolution.reason_code || "not provided")}</dd></div>
                  <div><dt>Decision</dt><dd>${escapeHtml(resolution.decision || "unknown")}</dd></div>
                </dl>
                <p class="helper"><strong>What to do:</strong> Adjust timeframe or request mode, validate or enable a compatible service, or use manual selection only if compatible.</p>`
        }
      </section>
    </div>
    <details class="rejected-services">
      <summary>Rejected Services (${rejected.length})</summary>
      ${
        rejected.length
          ? `<ul>${rejected.map((candidate) => `<li><strong>${escapeHtml(candidate.service_name || candidate.service_id || "candidate")}</strong><span>Reason: ${escapeHtml(candidate.reason_code || "not provided")}</span><span>${escapeHtml(candidate.explanation || "No resolver explanation returned. This is a backend contract issue.")}</span></li>`).join("")}</ul>`
          : `<p class="empty">No rejected candidates.</p>`
      }
    </details>
  </section>`;
}

function renderLogs(marketData, ai) {
  const rows = [...marketData, ...ai].filter((service) => service.last_validated_at || service.validation_status);
  return `<section class="panel"><h3>Validation History</h3><div class="record-list">${rows
    .map((service) => `<article class="record-card">
      <h4>${escapeHtml(service.name)}</h4>
      <p>${escapeHtml(service.validation_status || "not validated")}: ${escapeHtml(service.validation_message || "")}</p>
      <p class="empty">Last validated: ${formatDate(service.last_validated_at)}</p>
    </article>`)
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
  return compactPayload({ name: data.get("name"), provider, mode });
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
  const symbols = String(formData.get("symbols") || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const payload = {
    selection_mode: mode === "default" ? "default" : mode === "explicit" ? "explicit" : "auto",
    intent: {
      consumer: formData.get("consumer") || DEFAULT_INTENT.consumer,
      mode: formData.get("mode") || DEFAULT_INTENT.mode,
      symbols: symbols.length ? symbols : DEFAULT_INTENT.symbols,
      timeframe: formData.get("timeframe") || DEFAULT_INTENT.timeframe,
      purpose: formData.get("purpose") || DEFAULT_INTENT.purpose,
      start_at: sanitizePayloadEntry(formData.get("start_at")),
      end_at: sanitizePayloadEntry(formData.get("end_at")),
      requires_streaming: formData.has("requires_streaming"),
      requires_intraday: formData.has("requires_intraday"),
      tolerance: "normal",
      requires_historical: true,
      requires_realtime: formData.has("requires_streaming")
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
  form.querySelectorAll("[data-provider-body='alpaca']").forEach((node) => {
    node.style.display = provider === "alpaca" ? "grid" : "none";
  });
  form.querySelectorAll("[data-provider-body='yahoo']").forEach((node) => {
    node.style.display = provider === "yahoo" ? "grid" : "none";
  });
  form.querySelectorAll("[data-provider-body='future']").forEach((node) => {
    node.style.display = provider === "future" ? "grid" : "none";
  });
}

function applyAiFields(form) {
  if (!form) return;
  const provider = form.querySelector("select[name='provider']")?.value || "";
  const keyRow = form.querySelector("[data-provider-body='ai-key']");
  if (keyRow) keyRow.style.display = provider === "future" ? "none" : "grid";
}

export function renderServicesCenter(state = {}) {
  const marketData = state.marketData?.services || [];
  const ai = state.ai?.services || [];
  const activeTab = state.activeTab || "market-data";
  const resolverIntent = normalizeIntent(state.resolutionPayload?.intent || DEFAULT_INTENT);
  return `<section class="page-heading">
    <div>
      <p class="eyebrow">External capabilities</p>
      <h1>Services Center</h1>
      <p class="helper">Configure external providers. The system selects the correct service automatically based on Data Intent.</p>
    </div>
  </section>
  ${renderSummaryCards({ marketData, ai })}
  <section class="panel">
    <header>
      <h2>Service Controls</h2>
      <div class="segmented-control" role="tablist">
        <button type="button" data-tab="market-data" class="${activeTab === "market-data" ? "active" : ""}">Market Data Services</button>
        <button type="button" data-tab="ai" class="${activeTab === "ai" ? "active" : ""}">AI Services</button>
        <button type="button" data-tab="logs" class="${activeTab === "logs" ? "active" : ""}">Service Logs</button>
      </div>
    </header>
    ${activeTab === "ai" ? ServiceTable(ai, "ai", state.aiFormState || null) : activeTab === "logs" ? renderLogs(marketData, ai) : ServiceTable(marketData, "market", state.marketDataFormState || null)}
  </section>
  ${DataIntentPanel({ ...state, resolutionPayload: { ...(state.resolutionPayload || {}), intent: resolverIntent } })}
  ${ResolverResultPanel(state.resolution || {}, state.activeResolverMode || "auto", marketData, resolverIntent)}`;
}

export async function mountServicesCenter(root, client = createServicesApi()) {
  const state = {
    marketData: { services: [] },
    ai: { services: [] },
    activeTab: "market-data",
    marketDataFormState: null,
    aiFormState: null,
    activeResolverMode: "auto",
    resolutionPayload: { intent: DEFAULT_INTENT, selected_service_id: null },
    resolution: null
  };

  function syncEditStateFromServices(listType, serviceId) {
    if (!serviceId) return;
    if (listType === "market") {
      const service = state.marketData.services.find((item) => item.id === serviceId);
      if (service) {
        state.marketDataFormState = {
          id: service.id,
          visible: true,
          name: service.name || "",
          provider: service.provider || "alpaca",
          mode: service.mode || "paper"
        };
      }
      return;
    }
    const service = state.ai.services.find((item) => item.id === serviceId);
    if (service) {
      state.aiFormState = {
        id: service.id,
        visible: true,
        name: service.name || "",
        provider: service.provider || "groq",
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
    state.resolutionPayload = payload;
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

    if (action === "run-resolution") {
      await resolveFromForm();
      return;
    }

    if (action === "show-market-data-form") state.marketDataFormState = { visible: true, provider: "alpaca", mode: "paper", name: "", id: null };
    if (action === "show-ai-form") state.aiFormState = { visible: true, provider: "groq", capability_label: "fast", name: "", id: null };
    if (action === "edit-market-data") syncEditStateFromServices("market", id);
    if (action === "edit-ai") syncEditStateFromServices("ai", id);
    if (action === "cancel-market-data-edit") state.marketDataFormState = null;
    if (action === "cancel-ai-edit") state.aiFormState = null;

    if (action === "validate-market-data" && id) await client.validateMarketData(id);
    if (action === "disable-market-data") {
      const service = state.marketData.services.find((svc) => svc.id === id);
      if (service?.is_default && !window.confirm("This is the default Market Data service. Disabling it will remove the default. Continue?")) return;
      await client.disableMarketData(id);
    }
    if (action === "default-market-data") {
      const candidate = state.marketData.services.find((svc) => svc.id === id);
      const existingDefault = getActiveDefault("market");
      if (candidate && existingDefault && existingDefault.id !== candidate.id && !window.confirm(`Replace default "${existingDefault.name}" with "${candidate.name}"?`)) return;
      await client.setDefaultMarketData(id);
    }
    if (action === "validate-ai" && id) await client.validateAi(id);
    if (action === "disable-ai") {
      const service = state.ai.services.find((svc) => svc.id === id);
      if (service?.is_default && !window.confirm("This is the default AI service. Disabling it will remove the default. Continue?")) return;
      await client.disableAi(id);
    }
    if (action === "default-ai") {
      const candidate = state.ai.services.find((svc) => svc.id === id);
      const existingDefault = getActiveDefault("ai");
      if (candidate && existingDefault && existingDefault.id !== candidate.id && !window.confirm(`Replace default "${existingDefault.name}" with "${candidate.name}"?`)) return;
      await client.setDefaultAi(id);
    }

    if (action) await refresh();
  });

  root.addEventListener("change", (event) => {
    const form = event.target.closest("form");
    if (!form) return;
    if (event.target.matches("select[data-provider-select='market-data']")) {
      const data = new FormData(form);
      state.marketDataFormState = {
        ...(state.marketDataFormState || {}),
        visible: true,
        id: sanitizePayloadEntry(data.get("service_id")) || null,
        name: data.get("name") || "",
        mode: data.get("mode") || "paper",
        provider: event.target.value
      };
      root.innerHTML = renderServicesCenter(state);
    }
    if (event.target.matches("select[data-provider-select='ai']")) {
      const data = new FormData(form);
      state.aiFormState = {
        ...(state.aiFormState || {}),
        visible: true,
        id: sanitizePayloadEntry(data.get("service_id")) || null,
        name: data.get("name") || "",
        capability_label: data.get("capability_label") || "fast",
        provider: event.target.value
      };
      root.innerHTML = renderServicesCenter(state);
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
      state.marketDataFormState = null;
    } else {
      const payload = normalizeAiForSubmit(data);
      const serviceId = sanitizePayloadEntry(data.get("service_id"));
      if (serviceId) await client.updateAi(serviceId, payload);
      else await client.createAi(payload);
      state.aiFormState = null;
    }
    await refresh();
  });

  await refresh();
}
