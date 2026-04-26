/**
 * Providers page — replaces the deprecated Services Center per plan_review §J
 * ("Mounted under Providers → Market Data Pipelines, not as a separate Services
 * Center page").
 *
 * Hosts three tabs:
 *   - Market Data Pipelines (default; carries the Resolver Result Panel)
 *   - Market Data Services (provider credentials catalog)
 *   - AI Providers
 *
 * The Resolver Result Panel reads only from `resolution.per_symbol_rows` —
 * top-level mirrors are forbidden (see resolver determinism contract).
 */

import { createPipelinesApi } from "./api/pipelines.js";
import { createServicesApi } from "./api/services.js";

const MASKED = "********";

const RESOLVER_STRATEGIES = {
  auto: "Auto (Recommended)",
  default_preferred: "Default",
  manual_override: "Manual Override"
};

const STRATEGY_COPY = {
  auto: "System selects the best compatible service based on the request.",
  default_preferred: "Use the configured default service only. If incompatible, fail clearly.",
  manual_override: "Use the selected service only. If incompatible, fail clearly."
};

const TRADING_MODE_OPTIONS = [
  ["", "None (vendor-only)"],
  ["BROKER_PAPER", "BROKER_PAPER"],
  ["BROKER_LIVE", "BROKER_LIVE"]
];

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

function capabilityList(capabilities = {}) {
  return Object.entries(capabilities)
    .filter(([, enabled]) => enabled === true)
    .map(([key]) => key.replace("supports_", "").replaceAll("_", " "));
}

function capabilityChips(capabilities = {}) {
  const items = capabilityList(capabilities);
  return items.length
    ? items.map((item) => `<span class="status">${escapeHtml(item)}</span>`).join("")
    : `<span class="empty">No capabilities reported.</span>`;
}

// ---------------------------------------------------------------------------
// Tab: Market Data Pipelines (the canonical Phase 1 surface)
// ---------------------------------------------------------------------------

function renderPipelineRow(pipeline) {
  const status = pipeline.status || "unknown";
  return `<article class="summary-card service-card ${pipeline.is_default_for_provider ? "service-default" : ""} ${status === "disabled" ? "service-disabled" : ""}">
    <header>
      <div class="service-header">
        <span class="service-icon service-icon-pipeline">P</span>
        <h3>${escapeHtml(pipeline.display_name)}</h3>
      </div>
      <span class="status status-${status}">${escapeHtml(status)}</span>
    </header>
    <dl class="detail-grid">
      <div><dt>Provider</dt><dd>${escapeHtml(pipeline.provider || "unknown")}</dd></div>
      <div><dt>Service</dt><dd>${pipeline.service_id ? `<code>${escapeHtml(pipeline.service_id)}</code>` : "<em>not bound</em>"}</dd></div>
      <div><dt>Data Feed</dt><dd>${escapeHtml(pipeline.data_feed || "iex")}</dd></div>
      <div><dt>Trading Mode</dt><dd>${escapeHtml(pipeline.trading_mode || "(vendor-only)")}</dd></div>
      <div><dt>Default for provider</dt><dd>${pipeline.is_default_for_provider ? "yes" : "no"}</dd></div>
      <div><dt>Pipeline ID</dt><dd><code>${escapeHtml(pipeline.id)}</code></dd></div>
      <div><dt>Created</dt><dd>${formatDate(pipeline.created_at)}</dd></div>
      <div><dt>Updated</dt><dd>${formatDate(pipeline.updated_at)}</dd></div>
    </dl>
    <div class="chip-row" aria-label="Capability summary">${capabilityChips(pipeline.capabilities)}</div>
    <div class="button-row">
      <button type="button" data-action="default-pipeline" data-id="${escapeHtml(pipeline.id)}">Set Default</button>
      <button type="button" data-action="disable-pipeline" data-id="${escapeHtml(pipeline.id)}">Disable</button>
    </div>
  </article>`;
}

const DATA_FEED_OPTIONS = [
  ["iex", "IEX (real-time, free)"],
  ["sip", "SIP (real-time, premium)"],
  ["delayed_sip", "Delayed SIP (15-min delay)"],
  ["boats", "BOATS (overnight)"],
  ["overnight", "Overnight derived"],
  ["otc", "OTC"]
];

function renderPipelineForm(formState = {}, services = []) {
  const tradingMode = formState.trading_mode || "";
  const dataFeed = formState.data_feed || "iex";
  const serviceId = formState.service_id || "";
  const alpacaServices = services.filter((svc) => svc.provider === "alpaca" && svc.status !== "disabled");
  return `<form class="account-form service-form" data-form="pipeline">
    <div class="form-intro">
      <h3>Activate Market Data Stream (Pipeline)</h3>
      <p class="helper">Picks one of your registered Market Data Services and turns it into a live stream identity. Only one ACTIVE pipeline per (Service · trading mode · data feed) is allowed — duplicates are rejected at create time.</p>
    </div>
    <label><span>Service</span><select name="service_id" required>
      <option value="" disabled${serviceId ? "" : " selected"}>— pick a Service —</option>
      ${alpacaServices.map((svc) => `<option value="${escapeHtml(svc.id)}"${serviceId === svc.id ? " selected" : ""}>${escapeHtml(svc.name)} (${escapeHtml(svc.provider)})</option>`).join("")}
    </select><small class="helper">Only Alpaca services with a credentialed account are listed. Add the service first if you don't see one.</small></label>
    <label><span>Display Name</span><input name="display_name" placeholder="auto from service · feed" value="${escapeHtml(formState.display_name || "")}"></label>
    <label><span>Data Feed</span><select name="data_feed">${renderSelectOptions(DATA_FEED_OPTIONS, dataFeed)}</select></label>
    <label><span>Trading Mode</span><select name="trading_mode">${renderSelectOptions(TRADING_MODE_OPTIONS, tradingMode)}</select><small class="helper">BROKER_PAPER for paper-credentialed streams, BROKER_LIVE for live; leave None for vendor-data-only feeds.</small></label>
    <div class="button-row form-actions">
      <button type="button" data-action="cancel-pipeline-form">Cancel</button>
      <button type="submit">Activate</button>
    </div>
  </form>`;
}

function renderPipelinesTab(state) {
  const pipelines = state.pipelines?.pipelines || [];
  const formVisible = Boolean(state.pipelineFormState?.visible);
  return `<section class="service-workspace">
    <div class="service-toolbar">
      <h2>Market Data Pipelines</h2>
      <button type="button" data-action="show-pipeline-form">+ Add Pipeline</button>
    </div>
    ${formVisible ? renderPipelineForm(state.pipelineFormState, state.marketData?.services || []) : ""}
    <div class="service-table">${pipelines.length ? pipelines.map(renderPipelineRow).join("") : `<p class="empty">No pipelines configured. Add a pipeline so resolver results carry a real pipeline_id.</p>`}</div>
  </section>
  ${DataIntentPanel(state)}
  ${ResolverResultPanel(state.resolution || {}, state.activeResolverStrategy || "auto", pipelines)}`;
}

// ---------------------------------------------------------------------------
// Tab: Market Data Services (credentials catalog)
// ---------------------------------------------------------------------------

function serviceStatusClass(status) {
  if (status === "disabled") return "status-danger";
  if (status === "invalid") return "status-blocked";
  if (status === "valid") return "status-running";
  return "";
}

function renderServiceFlags(service) {
  const status = service.status || "unknown";
  const credentialed = service.has_api_key || service.has_api_secret ? "keyed" : "no credentials";
  return `<div class="service-flags">
    <span class="service-flag flag-market">${escapeHtml(service.provider || "unknown")}</span>
    <span class="service-flag flag-${status}">${escapeHtml(status)}</span>
    <span class="service-flag flag-credentials">${escapeHtml(credentialed)}</span>
  </div>`;
}

function renderMarketDataRow(service) {
  const status = service.status || "unknown";
  return `<article class="summary-card service-card ${status === "disabled" ? "service-disabled" : ""}">
    <header>
      <div class="service-header">
        <span class="service-icon service-icon-market">M</span>
        <h3>${escapeHtml(service.name)}</h3>
      </div>
      <span class="status ${serviceStatusClass(status)}">${escapeHtml(status)}</span>
    </header>
    ${renderServiceFlags(service)}
    <dl class="detail-grid">
      <div><dt>Provider</dt><dd>${escapeHtml(service.provider || "unknown")}</dd></div>
      <div><dt>Credentials</dt><dd>${service.has_api_key || service.has_api_secret ? MASKED : "not required"}</dd></div>
      <div><dt>Validation</dt><dd>${escapeHtml(service.validation_status || "not validated")} - ${escapeHtml(service.validation_message || "pending verification")}</dd></div>
      <div><dt>Last validated</dt><dd>${formatDate(service.last_validated_at)}</dd></div>
    </dl>
    <div class="chip-row" aria-label="Capability summary">${capabilityChips(service.capabilities)}</div>
    <div class="button-row">
      <button type="button" data-action="validate-market-data" data-id="${escapeHtml(service.id)}">Validate</button>
      <button type="button" data-action="activate-as-stream" data-id="${escapeHtml(service.id)}" title="Open the Pipeline form pre-filled with this service">Activate as Stream…</button>
      <button type="button" data-action="disable-market-data" data-id="${escapeHtml(service.id)}">Disable</button>
    </div>
  </article>`;
}

function renderMarketDataForm(formState = {}) {
  const provider = (formState.provider || "alpaca").toLowerCase();
  const providerBody =
    provider === "alpaca"
      ? `<div data-provider-body="alpaca" class="provider-body">
          <label><span>API Key</span><input name="api_key" autocomplete="off" placeholder="${MASKED}" type="password"></label>
          <label><span>API Secret</span><input name="api_secret" autocomplete="off" placeholder="${MASKED}" type="password"></label>
          <p class="helper provider-note">Alpaca market data uses the same credentials regardless of broker mode. Trading mode lives on the Broker Account, not on the data feed.</p>
        </div>`
      : provider === "yahoo"
        ? `<div data-provider-body="yahoo" class="provider-body"><p class="helper provider-note">No credentials required. Yahoo is historical data only (no streaming).</p></div>`
        : `<div data-provider-body="future" class="provider-body"><p class="helper provider-note">Reserved provider for future market-data integration.</p></div>`;
  return `<form class="account-form service-form" data-form="market-data">
    <div class="form-intro">
      <h3>Create Market Data Service</h3>
      <p class="helper">Select a provider. Required fields update based on provider.</p>
    </div>
    <label><span>Service Name</span><input name="name" required value="${escapeHtml(formState.name || "")}"></label>
    <label><span>Provider</span><select name="provider" data-provider-select="market-data">${renderSelectOptions([["alpaca", "Alpaca"], ["yahoo", "Yahoo"], ["future", "Future"]], provider)}</select></label>
    ${providerBody}
    <div class="button-row form-actions">
      <button type="button" data-action="cancel-market-data-form">Cancel</button>
      <button type="submit">Save</button>
    </div>
  </form>`;
}

function renderMarketDataTab(state) {
  const services = state.marketData?.services || [];
  const formVisible = Boolean(state.marketDataFormState?.visible);
  return `<section class="service-workspace">
    <div class="service-toolbar">
      <h2>Market Data Services</h2>
      <button type="button" data-action="show-market-data-form">+ Add Market Data Service</button>
    </div>
    ${formVisible ? renderMarketDataForm(state.marketDataFormState) : ""}
    <div class="service-table">${services.length ? services.map(renderMarketDataRow).join("") : `<p class="empty">No Market Data Services configured.</p>`}</div>
  </section>`;
}

// ---------------------------------------------------------------------------
// Tab: AI Providers
// ---------------------------------------------------------------------------

function renderAiRow(service) {
  const status = service.status || "unknown";
  return `<article class="summary-card service-card ${service.is_default ? "service-default" : ""} ${status === "disabled" ? "service-disabled" : ""}">
    <header>
      <div class="service-header">
        <span class="service-icon service-icon-ai">AI</span>
        <h3>${escapeHtml(service.name)}</h3>
      </div>
      <span class="status ${serviceStatusClass(status)}">${escapeHtml(status)}</span>
    </header>
    <dl class="detail-grid">
      <div><dt>Provider</dt><dd>${escapeHtml(service.provider || "unknown")}</dd></div>
      <div><dt>Default</dt><dd>${service.is_default ? "yes" : "no"}</dd></div>
      <div><dt>Capability</dt><dd>${escapeHtml(service.capability_label || "unknown")}</dd></div>
      <div><dt>Credentials</dt><dd>${service.has_api_key ? MASKED : "not saved"}</dd></div>
      <div><dt>Validation</dt><dd>${escapeHtml(service.validation_status || "not validated")} - ${escapeHtml(service.validation_message || "pending verification")}</dd></div>
    </dl>
    <p class="helper">AI providers are advisory only. They cannot approve trades, override the Governor, or submit orders.</p>
    <div class="button-row">
      <button type="button" data-action="validate-ai" data-id="${escapeHtml(service.id)}">Validate</button>
      <button type="button" data-action="default-ai" data-id="${escapeHtml(service.id)}">Set Default</button>
      <button type="button" data-action="disable-ai" data-id="${escapeHtml(service.id)}">Disable</button>
    </div>
  </article>`;
}

function renderAiForm(formState = {}) {
  const provider = (formState.provider || "groq").toLowerCase();
  const showKey = provider !== "future";
  return `<form class="account-form service-form" data-form="ai">
    <div class="form-intro">
      <h3>Create AI Provider</h3>
      <p class="helper">AI is advisory only and cannot approve trades, override Governor, or submit orders.</p>
    </div>
    <label><span>Display Name</span><input name="name" required value="${escapeHtml(formState.name || "")}"></label>
    <label><span>Provider</span><select name="provider" data-provider-select="ai">${renderSelectOptions([["groq", "Groq"], ["claude", "Claude"], ["openai", "OpenAI"], ["codex", "Codex"], ["future", "Future"]], provider)}</select></label>
    ${showKey ? `<label><span>API Key</span><input name="api_key" autocomplete="off" placeholder="${MASKED}" type="password"></label>` : ""}
    <label><span>Capability Label</span><select name="capability_label">${renderSelectOptions([["fast", "fast"], ["reasoning", "reasoning"], ["coding", "coding"], ["general", "general"], ["unknown", "unknown"]], formState.capability_label || "fast")}</select></label>
    <div class="button-row form-actions">
      <button type="button" data-action="cancel-ai-form">Cancel</button>
      <button type="submit">Save</button>
    </div>
  </form>`;
}

function renderAiTab(state) {
  const providers = state.ai?.services || [];
  const formVisible = Boolean(state.aiFormState?.visible);
  return `<section class="service-workspace">
    <div class="service-toolbar">
      <h2>AI Providers</h2>
      <button type="button" data-action="show-ai-form">+ Add AI Provider</button>
    </div>
    ${formVisible ? renderAiForm(state.aiFormState) : ""}
    <div class="service-table">${providers.length ? providers.map(renderAiRow).join("") : `<p class="empty">No AI providers configured.</p>`}</div>
  </section>`;
}

// ---------------------------------------------------------------------------
// Resolver Result Panel — reads only from per_symbol_rows
// ---------------------------------------------------------------------------

function renderRowRejections(row) {
  const rejected = Array.isArray(row.rejected_providers) ? row.rejected_providers : [];
  if (!rejected.length) return `<span class="empty">none</span>`;
  return `<details class="row-rejections"><summary>${rejected.length} rejected</summary><ul>${rejected
    .map((candidate) => `<li><strong>${escapeHtml(candidate.service_name || candidate.service_id || "candidate")}</strong> &mdash; ${escapeHtml(candidate.reason_code || "not provided")}: ${escapeHtml(candidate.explanation || "")}</li>`)
    .join("")}</ul></details>`;
}

function renderPerSymbolTable(rows) {
  if (!rows.length) return `<p class="empty">No per-symbol resolution rows.</p>`;
  const body = rows
    .map((row) => {
      const decisionClass = row.decision === "selected" ? "row-selected" : "row-rejected";
      return `<tr class="${decisionClass}">
        <td>${escapeHtml(row.symbol)}</td>
        <td>${escapeHtml(row.decision)}</td>
        <td>${escapeHtml(row.selected_service_name || "—")}</td>
        <td>${escapeHtml(row.selected_provider || "—")}</td>
        <td><code>${escapeHtml(row.pipeline_id || "—")}</code></td>
        <td><code>${escapeHtml(row.reason || "—")}</code></td>
        <td>${escapeHtml(row.explanation || "")}</td>
        <td>${renderRowRejections(row)}</td>
      </tr>`;
    })
    .join("");
  return `<table class="per-symbol-table">
    <thead><tr><th>Symbol</th><th>Decision</th><th>Service</th><th>Provider</th><th>Pipeline</th><th>Reason</th><th>Why</th><th>Rejected</th></tr></thead>
    <tbody>${body}</tbody>
  </table>`;
}

export function ResolverResultPanel(result, selectedStrategy, pipelines = []) {
  const resolution = result || {};
  const hasResolution = Object.keys(resolution).length > 0;
  const intent = normalizeIntent(resolution.intent || DEFAULT_INTENT);
  const rows = Array.isArray(resolution.per_symbol_rows) ? resolution.per_symbol_rows : [];
  const decision = resolution.decision || "unknown";
  const partialBanner = decision === "partial"
    ? `<div class="resolver-banner resolver-banner-partial"><strong>Mixed outcome:</strong> ${rows.filter((row) => row.decision === "selected").length} of ${rows.length} symbols resolved. Inspect each row.</div>`
    : "";
  const debugFields = hasResolution
    ? `<details class="resolver-debug">
        <summary>Resolver determinism (debug)</summary>
        <dl>
          <div><dt>Resolver Version</dt><dd>${escapeHtml(resolution.resolver_version || "unknown")}</dd></div>
          <div><dt>Input Hash</dt><dd><code>${escapeHtml(resolution.resolver_input_hash || "n/a")}</code></dd></div>
          <div><dt>Invocation Context</dt><dd>${escapeHtml(resolution.invocation_context || "n/a")}</dd></div>
          <div><dt>Decided At</dt><dd>${escapeHtml(resolution.decided_at || "n/a")}</dd></div>
          <div><dt>Selection Strategy</dt><dd>${escapeHtml(resolution.selection_strategy || selectedStrategy || "auto")}</dd></div>
          <div><dt>Aggregate Decision</dt><dd>${escapeHtml(decision)}</dd></div>
          <p class="helper">Compare two resolutions on <code>resolver_input_hash</code> only — <code>decided_at</code> is a wall-clock receipt and is non-deterministic by design.</p>
        </dl>
      </details>`
    : "";
  return `<section class="panel data-intent-panel">
    <h3>Resolver Result</h3>
    <div class="resolver-grid">
      <section class="resolver-block">
        <h4>Detected Intent</h4>
        <dl>
          <div><dt>Consumer</dt><dd>${escapeHtml(intent.consumer)}</dd></div>
          <div><dt>Timeframe</dt><dd>${escapeHtml(intent.timeframe)}</dd></div>
          <div><dt>Date Range</dt><dd>${escapeHtml(formatDateRange(intent))}</dd></div>
          <div><dt>Streaming Required</dt><dd>${escapeHtml(boolLabel(Boolean(intent.requires_streaming)))}</dd></div>
          <div><dt>Intraday Required</dt><dd>${escapeHtml(boolLabel(Boolean(intent.requires_intraday)))}</dd></div>
          <div><dt>Purpose</dt><dd>${escapeHtml(intent.purpose)}</dd></div>
        </dl>
      </section>
      <section class="resolver-block ${hasResolution && decision === "rejected" ? "resolver-error" : ""}">
        <h4>${!hasResolution ? "Decision Preview" : `Per-Symbol Resolution (${decision})`}</h4>
        ${
          !hasResolution
            ? `<p class="empty">${pipelines.length ? "Preview the resolver decision below." : "No pipelines configured. Resolver pipeline_id will remain null until at least one default pipeline exists."}</p>`
            : `${partialBanner}${renderPerSymbolTable(rows)}`
        }
      </section>
    </div>
    ${debugFields}
  </section>`;
}

function DataIntentPanel(state) {
  const intent = normalizeIntent(state.resolutionPayload?.intent || DEFAULT_INTENT);
  const selected = state.activeResolverStrategy || "auto";
  const candidatePipelines = state.pipelines?.pipelines || [];
  return `<section class="panel">
    <header>
      <h2>Data Source Decision</h2>
      <div class="segmented-control" role="group" aria-label="Selection Strategy">
        ${Object.entries(RESOLVER_STRATEGIES)
          .map(([strategy, label]) => `<button type="button" data-action="set-resolver-strategy" data-strategy="${strategy}" class="${selected === strategy ? "active" : ""}" aria-pressed="${selected === strategy ? "true" : "false"}">${label}</button>`)
          .join("")}
      </div>
    </header>
    <p class="helper">${escapeHtml(STRATEGY_COPY[selected] || STRATEGY_COPY.auto)}</p>
    <form class="account-form service-form" data-form="resolver-intent">
      <label><span>Consumer</span><select name="consumer">${renderSelectOptions(CONSUMER_OPTIONS.map((value) => [value, value]), intent.consumer)}</select></label>
      <label><span>Timeframe</span><select name="timeframe">${renderSelectOptions(TIMEFRAME_OPTIONS.map((value) => [value, value]), intent.timeframe)}</select></label>
      <label><span>Purpose</span><select name="purpose">${renderSelectOptions(SERVICE_PURPOSES.map((value) => [value, value]), intent.purpose)}</select></label>
      <label><span>Mode</span><select name="mode">${renderSelectOptions([["batch", "batch"], ["replay", "replay"], ["live_preview", "live_preview"], ["live_runtime", "live_runtime"]], intent.mode)}</select></label>
      <label><span>Symbols</span><input name="symbols" value="${escapeHtml(intent.symbols.join(", "))}"></label>
      <label class="checkbox-label"><input type="checkbox" name="requires_streaming" ${intent.requires_streaming ? "checked" : ""}><span>Streaming required</span></label>
      <label class="checkbox-label"><input type="checkbox" name="requires_intraday" ${intent.requires_intraday ? "checked" : ""}><span>Intraday required</span></label>
      <div class="service-strategy-indicator"><strong>Strategy:</strong> ${escapeHtml(RESOLVER_STRATEGIES[selected])}</div>
    </form>
    <div class="button-row">
      <button type="button" data-action="run-resolution" ${candidatePipelines.length ? "" : "disabled"}>Preview Resolution</button>
    </div>
  </section>`;
}

// ---------------------------------------------------------------------------
// Top-level renderer + mount
// ---------------------------------------------------------------------------

function renderSummaryCards(state) {
  const pipelines = state.pipelines?.pipelines || [];
  const services = state.marketData?.services || [];
  const ai = state.ai?.services || [];
  const defaultPipelinesByProvider = pipelines.filter((p) => p.is_default_for_provider);
  const issues = [...services, ...ai].filter((svc) => svc.status === "invalid" || svc.status === "disabled" || svc.status === "draft").length;
  return `<section class="state-strip">
    <article>
      <span>Pipelines</span>
      <strong>${pipelines.length} configured · ${defaultPipelinesByProvider.length} default</strong>
      <p class="helper">Shared market-data subscriptions. One pipeline can serve many Deployments.</p>
    </article>
    <article>
      <span>Market Data Services</span>
      <strong>${services.length} configured</strong>
      <p class="helper">Provider credentials catalog (separate from pipelines).</p>
    </article>
    <article>
      <span>AI Providers</span>
      <strong>${ai.length} configured</strong>
      <p class="helper">Advisory only — never approves trades or submits orders.</p>
    </article>
    <article>
      <span>Service Health</span>
      <strong>${issues} issues</strong>
      <p class="helper">Invalid / disabled / draft services across both market-data and AI.</p>
    </article>
  </section>`;
}

export function renderProviders(state = {}) {
  const activeTab = state.activeTab || "pipelines";
  return `<section class="page-heading">
    <div>
      <p class="eyebrow">Providers</p>
      <h1>Providers</h1>
      <p class="helper">Market Data Pipelines and AI Providers. Pipelines drive shared market-data fan-out; AI is advisory only.</p>
    </div>
  </section>
  ${renderBootstrapBanner(state)}
  ${renderSummaryCards(state)}
  <section class="panel">
    <header>
      <h2>Provider Surfaces</h2>
      <div class="segmented-control" role="tablist">
        <button type="button" data-tab="pipelines" class="${activeTab === "pipelines" ? "active" : ""}">Market Data Pipelines</button>
        <button type="button" data-tab="market-data" class="${activeTab === "market-data" ? "active" : ""}">Market Data Services</button>
        <button type="button" data-tab="ai" class="${activeTab === "ai" ? "active" : ""}">AI Providers</button>
      </div>
    </header>
    ${activeTab === "ai" ? renderAiTab(state) : activeTab === "market-data" ? renderMarketDataTab(state) : renderPipelinesTab(state)}
  </section>`;
}

function renderBootstrapBanner(state) {
  const status = state.systemStatus;
  const services = state.marketData?.services || [];
  const pipelines = state.pipelines?.pipelines || [];
  const hasAlpacaService = services.some((svc) => svc.provider === "alpaca");
  const hasAlpacaPipeline = pipelines.some((p) => p.provider === "alpaca");
  const credsPresent = !!(status && status.alpaca_credentials_present);

  if (!credsPresent || (hasAlpacaService && hasAlpacaPipeline)) {
    return state.bootstrapNotice
      ? `<section class="bootstrap-banner bootstrap-banner--success" role="status">${escapeHtml(state.bootstrapNotice)}</section>`
      : "";
  }

  const detail = [];
  if (!hasAlpacaService) detail.push("Market Data Service");
  if (!hasAlpacaPipeline) detail.push("Pipeline");
  return `<section class="bootstrap-banner" role="status">
    <div>
      <strong>Alpaca credentials detected in .env</strong>
      <p>No Alpaca ${detail.join(" or ")} registered in the catalog yet. Click below to register the env-based credentials as a default Alpaca Market Data Service and Pipeline.</p>
    </div>
    <div class="bootstrap-banner__actions">
      <button type="button" data-action="bootstrap-from-env"${state.bootstrapping ? " disabled" : ""}>
        ${state.bootstrapping ? "Bootstrapping…" : "Bootstrap from .env"}
      </button>
    </div>
    ${state.bootstrapError ? `<p class="warning" role="alert">${escapeHtml(state.bootstrapError)}</p>` : ""}
  </section>`;
}

function normalizePipelinePayload(data) {
  const trading_mode = data.get("trading_mode");
  const display_name = data.get("display_name");
  return compactPayload({
    service_id: data.get("service_id"),
    display_name: display_name || undefined,
    data_feed: data.get("data_feed") || "iex",
    trading_mode: trading_mode || undefined
  });
}

function normalizeMarketDataPayload(data) {
  const provider = (data.get("provider") || "").toLowerCase();
  if (provider === "alpaca") {
    return compactPayload({
      name: data.get("name"),
      provider,
      api_key: data.get("api_key"),
      api_secret: data.get("api_secret")
    });
  }
  return compactPayload({ name: data.get("name"), provider });
}

function normalizeAiPayload(data) {
  return compactPayload({
    name: data.get("name"),
    provider: data.get("provider"),
    api_key: data.get("api_key"),
    capability_label: data.get("capability_label")
  });
}

function normalizeResolverPayload(formData, strategy) {
  const symbols = String(formData.get("symbols") || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const normalizedStrategy =
    strategy === "default_preferred" ? "default_preferred" : strategy === "manual_override" ? "manual_override" : "auto";
  return {
    selection_strategy: normalizedStrategy,
    invocation_context: "operations_preview",
    intent: {
      consumer: formData.get("consumer") || DEFAULT_INTENT.consumer,
      mode: formData.get("mode") || DEFAULT_INTENT.mode,
      symbols: symbols.length ? symbols : DEFAULT_INTENT.symbols,
      timeframe: formData.get("timeframe") || DEFAULT_INTENT.timeframe,
      purpose: formData.get("purpose") || DEFAULT_INTENT.purpose,
      requires_streaming: formData.has("requires_streaming"),
      requires_intraday: formData.has("requires_intraday"),
      tolerance: "normal",
      requires_historical: true,
      requires_realtime: formData.has("requires_streaming")
    }
  };
}

export async function mountProviders(root, deps = {}) {
  const pipelinesApi = deps.pipelinesApi || createPipelinesApi();
  const servicesApi = deps.servicesApi || createServicesApi();
  const systemStatusApi = deps.systemStatusApi || null;
  const state = {
    activeTab: "pipelines",
    pipelines: { pipelines: [] },
    marketData: { services: [] },
    ai: { services: [] },
    pipelineFormState: null,
    marketDataFormState: null,
    aiFormState: null,
    activeResolverStrategy: "auto",
    resolutionPayload: { intent: DEFAULT_INTENT },
    resolution: null,
    systemStatus: null,
    bootstrapping: false,
    bootstrapError: null,
    bootstrapNotice: null
  };

  async function refresh() {
    try {
      state.pipelines = await pipelinesApi.listPipelines();
      state.marketData = await servicesApi.listMarketData();
      state.ai = await servicesApi.listAi();
      if (systemStatusApi) {
        try {
          state.systemStatus = await systemStatusApi.status();
        } catch {
          state.systemStatus = null;
        }
      }
      root.innerHTML = renderProviders(state);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("Providers refresh failed:", err);
      root.innerHTML = `<section class="loading-shell loading-shell--error" role="alert">
        <div>
          <h1>Providers</h1>
          <p>Could not load Providers data.</p>
          <p class="loading-shell__hint">${escapeHtml(err.message || String(err))}</p>
          <p class="loading-shell__hint">Check that the API server is running on port 8000 and the routes /api/v1/market-data and /api/v1/ai are reachable.</p>
        </div>
      </section>`;
    }
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  async function resolveFromForm() {
    const form = root.querySelector("form[data-form='resolver-intent']");
    if (!form) return;
    const data = new FormData(form);
    const payload = normalizeResolverPayload(data, state.activeResolverStrategy || "auto");
    state.resolutionPayload = payload;
    state.resolution = await servicesApi.resolveMarketData(payload);
    await refresh();
  }

  root.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-tab], button[data-action]");
    if (!button) return;
    const id = button.dataset.id;
    const action = button.dataset.action;

    if (button.dataset.tab) {
      state.activeTab = button.dataset.tab;
      root.innerHTML = renderProviders(state);
      return;
    }

    if (action === "set-resolver-strategy") {
      state.activeResolverStrategy = button.dataset.strategy || "auto";
      root.innerHTML = renderProviders(state);
      return;
    }

    if (action === "run-resolution") {
      await resolveFromForm();
      return;
    }

    if (action === "bootstrap-from-env") {
      state.bootstrapping = true;
      state.bootstrapError = null;
      state.bootstrapNotice = null;
      root.innerHTML = renderProviders(state);
      try {
        const result = await pipelinesApi.bootstrapFromEnv();
        if (result.skipped_reason === "missing_credentials") {
          state.bootstrapError = "Backend reports no Alpaca credentials in .env.";
        } else {
          const parts = [];
          if (result.created_service) parts.push("registered Alpaca Market Data Service");
          if (result.created_pipeline) parts.push("created default Pipeline");
          state.bootstrapNotice = parts.length
            ? `Bootstrap complete — ${parts.join(", ")}.`
            : "Bootstrap complete — Alpaca catalog entries already existed.";
        }
      } catch (err) {
        state.bootstrapError = err.message || String(err);
      } finally {
        state.bootstrapping = false;
      }
      await refresh();
      return;
    }

    if (action === "show-pipeline-form") state.pipelineFormState = { visible: true, provider: "alpaca" };
    if (action === "cancel-pipeline-form") state.pipelineFormState = null;
    if (action === "default-pipeline" && id) await pipelinesApi.setDefaultPipeline(id);
    if (action === "disable-pipeline" && id) await pipelinesApi.disablePipeline(id);

    if (action === "show-market-data-form") state.marketDataFormState = { visible: true, provider: "alpaca" };
    if (action === "cancel-market-data-form") state.marketDataFormState = null;
    if (action === "validate-market-data" && id) await servicesApi.validateMarketData(id);
    if (action === "disable-market-data" && id) await servicesApi.disableMarketData(id);
    if (action === "activate-as-stream" && id) {
      // Switch to the Pipelines tab and pre-fill the form with this service.
      state.activeTab = "pipelines";
      state.pipelineFormState = {
        visible: true,
        service_id: id,
        trading_mode: "BROKER_PAPER",
        data_feed: "iex"
      };
      root.innerHTML = renderProviders(state);
      return;
    }

    if (action === "show-ai-form") state.aiFormState = { visible: true, provider: "groq", capability_label: "fast" };
    if (action === "cancel-ai-form") state.aiFormState = null;
    if (action === "validate-ai" && id) await servicesApi.validateAi(id);
    if (action === "default-ai" && id) await servicesApi.setDefaultAi(id);
    if (action === "disable-ai" && id) await servicesApi.disableAi(id);

    if (action) await refresh();
  });

  root.addEventListener("submit", async (event) => {
    const form = event.target.closest("form[data-form]");
    if (!form) return;
    event.preventDefault();
    const data = new FormData(form);
    if (form.dataset.form === "pipeline") {
      await pipelinesApi.createPipelineFromService(normalizePipelinePayload(data));
      state.pipelineFormState = null;
    } else if (form.dataset.form === "market-data") {
      await servicesApi.createMarketData(normalizeMarketDataPayload(data));
      state.marketDataFormState = null;
    } else if (form.dataset.form === "ai") {
      await servicesApi.createAi(normalizeAiPayload(data));
      state.aiFormState = null;
    }
    await refresh();
  });

  await refresh();
}
