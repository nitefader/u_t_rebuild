/**
 * Providers — unified Market Data + Resolver + AI (single integrated surface).
 * Services, purpose tags, and pipelines are one workflow; resolver preview sits above the catalog.
 *
 * Visual IA and tokens follow `docs/architecture/UI_VISUAL_DIRECTION.md` (tabs, badges,
 * dense tables, restrained accents, 6–8px radii, subtle borders).
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

// Operator-driven role tags on a Market Data Service. Replaces .env bootstrap.
// Backend: backend/app/market_data/models.py::ServicePurpose. Keep these
// in sync with the Python enum values.
const SERVICE_PURPOSE_TAGS = [
  ["live_streaming", "Live streaming", "Real-time streaming for production / live trading."],
  ["test_streaming", "Test streaming", "FAKEPACA / 24-7 synthetic stream for off-hours dev."],
  ["batch_historical", "Batch historical", "Bulk historical pulls for backtest / batch jobs."],
  ["signal_preview", "Signal preview", "Operations Center previews and signal-plan rehearsal."],
  ["runtime_trading", "Runtime trading", "Credentials the broker runtime picks up at boot."]
];
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
// Pipeline row (detached streams + cards)
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
      ${!pipeline.service_id ? `<button type="button" data-action="bind-pipeline-service" data-id="${escapeHtml(pipeline.id)}" title="Backfill service_id on this legacy pipeline">Bind to Service…</button>` : ""}
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

// ---------------------------------------------------------------------------
// Market data catalog + resolver (integrated)
// ---------------------------------------------------------------------------

function serviceStatusClass(status) {
  if (status === "disabled") return "status-danger";
  if (status === "invalid") return "status-blocked";
  if (status === "valid") return "status-running";
  return "";
}

function renderPurposeForm(service) {
  const current = new Set(service.default_for || []);
  return `<form class="account-form service-form" data-form="service-purposes" data-service-id="${escapeHtml(service.id)}">
    <div class="form-intro">
      <h4>Configure purposes for "${escapeHtml(service.name)}"</h4>
      <p class="helper">Each purpose can be assigned to at most one Service. Picking a tag here moves it off any other Service that holds it.</p>
    </div>
    ${SERVICE_PURPOSE_TAGS
      .map(([value, label, blurb]) => `<label class="checkbox-label"><input type="checkbox" name="purposes" value="${value}" ${current.has(value) ? "checked" : ""}><span><strong>${escapeHtml(label)}</strong> · <span class="helper">${escapeHtml(blurb)}</span></span></label>`)
      .join("")}
    <div class="button-row form-actions">
      <button type="button" data-action="cancel-purposes-form">Cancel</button>
      <button type="submit">Save purposes</button>
    </div>
  </form>`;
}

function renderMarketDataForm(formState = {}) {
  const provider = (formState.provider || "alpaca").toLowerCase();
  const initialPurposes = new Set(formState.default_for || []);
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
      <p class="helper">Register provider credentials and tag the role this Service plays — the runtime picks Services by purpose tag instead of reading .env.</p>
    </div>
    <label><span>Service Name</span><input name="name" required value="${escapeHtml(formState.name || "")}"></label>
    <label><span>Provider</span><select name="provider" data-provider-select="market-data">${renderSelectOptions([["alpaca", "Alpaca"], ["yahoo", "Yahoo"], ["future", "Future"]], provider)}</select></label>
    ${providerBody}
    <fieldset class="purpose-fieldset">
      <legend>Default for</legend>
      <p class="helper">Pick which contexts use this Service. Each tag is single-canonical: assigning it here moves it off any other Service that holds it. Optional — leave blank if you'll tag later.</p>
      ${SERVICE_PURPOSE_TAGS
        .map(([value, label, blurb]) => `<label class="checkbox-label"><input type="checkbox" name="default_for" value="${value}" ${initialPurposes.has(value) ? "checked" : ""}><span><strong>${escapeHtml(label)}</strong> · <span class="helper">${escapeHtml(blurb)}</span></span></label>`)
        .join("")}
    </fieldset>
    <div class="button-row form-actions">
      <button type="button" data-action="cancel-market-data-form">Cancel</button>
      <button type="submit">Save</button>
    </div>
  </form>`;
}

// ---------------------------------------------------------------------------
// Tab: AI Providers
// ---------------------------------------------------------------------------

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
  return renderIntegratedAi(state);
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
  return `<table class="per-symbol-table prov-per-symbol-table">
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
  return `<section class="panel data-intent-panel prov-resolver-result">
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
  return `<section class="panel prov-data-intent">
    <header>
      <h2>Resolver intent</h2>
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

function provCapabilityPills(capabilities = {}) {
  const items = capabilityList(capabilities);
  if (!items.length) return `<span class="prov-muted">—</span>`;
  return items.map((item) => `<span class="prov-pill prov-pill--cap">${escapeHtml(item)}</span>`).join(" ");
}

function purposeTagsHtml(service) {
  const tags = Array.isArray(service.default_for) ? service.default_for : [];
  if (!tags.length) return `<span class="prov-pill prov-pill--muted">no role tags</span>`;
  return tags
    .map((t) => {
      const meta = SERVICE_PURPOSE_TAGS.find(([v]) => v === t);
      const label = meta ? meta[1] : t;
      return `<span class="prov-pill prov-pill--role">${escapeHtml(label)}</span>`;
    })
    .join("");
}

function streamSummaryForService(service, pipelines) {
  const list = (pipelines || []).filter((p) => p.service_id === service.id && p.status !== "disabled");
  if (!list.length) return `<span class="prov-muted">No active stream</span>`;
  return list
    .map((p) => {
      const bits = [p.data_feed || "iex"];
      if (p.trading_mode) bits.push(p.trading_mode);
      if (p.is_default_for_provider) bits.push("stream default");
      return `<span class="prov-pill prov-pill--stream">${escapeHtml(bits.join(" · "))}</span>`;
    })
    .join(" ");
}

function healthBadgeForStatus(status) {
  const s = String(status || "unknown").toLowerCase();
  if (s === "valid") return `<span class="prov-health prov-health--ok">Healthy</span>`;
  if (s === "invalid") return `<span class="prov-health prov-health--bad">Invalid</span>`;
  if (s === "disabled") return `<span class="prov-health prov-health--off">Disabled</span>`;
  if (s === "draft") return `<span class="prov-health prov-health--warn">Draft</span>`;
  return `<span class="prov-health">${escapeHtml(status)}</span>`;
}

function renderCompactStats(state) {
  const pipelines = state.pipelines?.pipelines || [];
  const services = state.marketData?.services || [];
  const ai = state.ai?.services || [];
  const defect = [...services, ...ai].filter((svc) => svc.status === "invalid" || svc.status === "disabled" || svc.status === "draft").length;
  return `<div class="prov-stats" role="status">
    <span><strong>${services.length}</strong> market data providers</span>
    <span aria-hidden="true">·</span>
    <span><strong>${pipelines.length}</strong> streams</span>
    <span aria-hidden="true">·</span>
    <span><strong>${ai.length}</strong> AI providers</span>
    <span aria-hidden="true">·</span>
    <span class="${defect ? "prov-stats--warn" : ""}"><strong>${defect}</strong> need attention</span>
  </div>`;
}

function renderResolverLeadIn(state) {
  const resolution = state.resolution;
  const rows = Array.isArray(resolution?.per_symbol_rows) ? resolution.per_symbol_rows : [];
  const intent = normalizeIntent(resolution?.intent || state.resolutionPayload?.intent || DEFAULT_INTENT);
  if (!resolution || !rows.length) {
    return `<p class="prov-lead">Capability tags and streams drive Auto-pick. Set intent below, then <strong>Preview Resolution</strong>.</p>`;
  }
  const first = rows.find((r) => r.decision === "selected") || rows[0];
  const rejected =
    Array.isArray(first?.rejected_providers) && first.rejected_providers.length
      ? `<p class="prov-last-decision__meta"><strong>Rejected candidates</strong> — ${first.rejected_providers
          .map((c) => escapeHtml(c.service_name || c.service_id || "candidate"))
          .join(", ")}</p>`
      : "";
  return `<div class="prov-last-decision">
    <p class="prov-last-decision__line"><strong>Requested</strong> — ${escapeHtml(intent.symbols.join(", "))} · ${escapeHtml(intent.timeframe)} · ${escapeHtml(intent.purpose)}</p>
    <p class="prov-last-decision__line"><strong>Selected</strong> — ${escapeHtml(first?.selected_service_name || "—")} <span class="prov-muted">(${escapeHtml(first?.selected_provider || "—")})</span></p>
    <p class="prov-last-decision__line"><strong>Pipeline</strong> — <code>${escapeHtml(first?.pipeline_id || "—")}</code></p>
    <p class="prov-last-decision__line"><strong>Reason</strong> — ${escapeHtml(first?.reason || resolution.decision || "—")}: ${escapeHtml(first?.explanation || "")}</p>
    ${rejected}
  </div>`;
}

function renderMarketDataServiceRows(state) {
  const services = state.marketData?.services || [];
  const pipelines = state.pipelines?.pipelines || [];
  const expanded = state.expandedPurposesFor || null;
  if (!services.length) {
    return `<tr><td colspan="8" class="prov-table-empty">
      <p>No market data providers yet. Register a vendor, assign role tags, then activate a stream.</p>
      <button type="button" data-action="show-market-data-form">+ Add market data provider</button>
    </td></tr>`;
  }
  return services
    .map((service) => {
      const isOpen = expanded === service.id;
      const main = `<tr class="prov-md-row">
        <td><strong>${escapeHtml(service.name)}</strong></td>
        <td>${escapeHtml(service.provider || "—")}</td>
        <td class="prov-cell-stream">${streamSummaryForService(service, pipelines)}</td>
        <td><div class="prov-pill-stack">${provCapabilityPills(service.capabilities)}${purposeTagsHtml(service)}</div></td>
        <td class="prov-center">${service.is_default ? `<span class="prov-yes">Yes</span>` : `<span class="prov-no">No</span>`}
          ${service.is_default ? "" : `<button type="button" class="prov-inline-btn" data-action="set-default-market-data" data-id="${escapeHtml(service.id)}">Set default</button>`}</td>
        <td><div class="prov-valid">${formatDate(service.last_validated_at)}</div><div class="prov-muted prov-small">${escapeHtml(service.validation_status || "—")}</div></td>
        <td>${healthBadgeForStatus(service.status)}</td>
        <td class="prov-actions">
          <button type="button" data-action="validate-market-data" data-id="${escapeHtml(service.id)}">Validate</button>
          <button type="button" data-action="${isOpen ? "cancel-purposes-form" : "configure-purposes"}" data-id="${escapeHtml(service.id)}">${isOpen ? "Close" : "Roles"}</button>
          <button type="button" data-action="activate-as-stream" data-id="${escapeHtml(service.id)}">Stream</button>
          <button type="button" class="prov-btn-danger" data-action="disable-market-data" data-id="${escapeHtml(service.id)}">Disable</button>
        </td>
      </tr>`;
      const sub = isOpen ? `<tr class="prov-md-sub"><td colspan="8"><div class="prov-subcard">${renderPurposeForm(service)}</div></td></tr>` : "";
      return main + sub;
    })
    .join("");
}

function renderDetachedPipelines(state) {
  const pipelines = state.pipelines?.pipelines || [];
  const orphans = pipelines.filter((p) => !p.service_id);
  if (!orphans.length) return "";
  return `<section class="prov-detached" aria-labelledby="prov-detached-heading">
    <h3 id="prov-detached-heading">Detached streams</h3>
    <p class="prov-muted prov-small">Pipelines without a bound provider row.</p>
    <div class="prov-detached-grid">${orphans.map(renderPipelineRow).join("")}</div>
  </section>`;
}

function renderIntegratedMarketData(state) {
  const pipelines = state.pipelines?.pipelines || [];
  const services = state.marketData?.services || [];
  return `<div class="prov-md-integrated">
    ${renderCompactStats(state)}
    <section class="prov-panel prov-panel--resolver">
      <h2 class="prov-h2">Resolver — last preview</h2>
      ${renderResolverLeadIn(state)}
    </section>
    ${DataIntentPanel(state)}
    ${ResolverResultPanel(state.resolution || {}, state.activeResolverStrategy || "auto", pipelines)}
    <section class="prov-panel">
      <div class="prov-toolbar">
        <h2 class="prov-h2">Market Data Providers</h2>
        <div class="prov-toolbar-actions">
          <button type="button" data-action="show-market-data-form">+ Provider</button>
          <button type="button" data-action="show-pipeline-form">+ Stream</button>
        </div>
      </div>
      ${state.marketDataFormState?.visible ? renderMarketDataForm(state.marketDataFormState) : ""}
      ${state.pipelineFormState?.visible ? renderPipelineForm(state.pipelineFormState, services) : ""}
      <div class="prov-table-scroller">
        <table class="prov-table" aria-label="Market data providers">
          <thead>
            <tr>
              <th>Name</th>
              <th>Vendor</th>
              <th>Stream / feed</th>
              <th>Roles &amp; capabilities</th>
              <th>Catalog default</th>
              <th>Validated</th>
              <th>Health</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>${renderMarketDataServiceRows(state)}</tbody>
        </table>
      </div>
    </section>
    ${renderDetachedPipelines(state)}
  </div>`;
}

function renderAiServiceRows(providers) {
  if (!providers.length) {
    return `<tr><td colspan="8" class="prov-table-empty"><p>No AI providers configured.</p><button type="button" data-action="show-ai-form">+ Add AI provider</button></td></tr>`;
  }
  return providers
    .map(
      (svc) => `<tr class="prov-md-row">
      <td><strong>${escapeHtml(svc.name)}</strong></td>
      <td>${escapeHtml(svc.provider || "—")}</td>
      <td>${escapeHtml(svc.capability_label || "—")}</td>
      <td class="prov-center">${svc.is_default ? `<span class="prov-yes">Yes</span>` : `<span class="prov-no">No</span>`}</td>
      <td>${svc.has_api_key ? MASKED : "—"}</td>
      <td><div class="prov-valid">${formatDate(svc.last_validated_at)}</div><div class="prov-muted prov-small">${escapeHtml(svc.validation_status || "—")}</div></td>
      <td>${healthBadgeForStatus(svc.status)}</td>
      <td class="prov-actions">
        <button type="button" data-action="validate-ai" data-id="${escapeHtml(svc.id)}">Validate</button>
        <button type="button" data-action="default-ai" data-id="${escapeHtml(svc.id)}">Default</button>
        <button type="button" class="prov-btn-danger" data-action="disable-ai" data-id="${escapeHtml(svc.id)}">Disable</button>
      </td>
    </tr>`
    )
    .join("");
}

function renderIntegratedAi(state) {
  const providers = state.ai?.services || [];
  const formVisible = Boolean(state.aiFormState?.visible);
  return `<div class="prov-ai-integrated">
    <p class="prov-lead">AI cannot approve trades, override the Governor, or submit orders.</p>
    <div class="prov-toolbar">
      <div class="prov-toolbar-title">
        <h2 class="prov-h2">AI Providers</h2>
        <span class="prov-badge prov-badge--advisory" title="Advisory only — no trade authority">Advisory only</span>
      </div>
      <button type="button" data-action="show-ai-form">+ Add Provider</button>
    </div>
    ${formVisible ? renderAiForm(state.aiFormState) : ""}
    <div class="prov-table-scroller">
      <table class="prov-table" aria-label="AI providers">
        <thead>
          <tr>
            <th>Name</th>
            <th>Provider</th>
            <th>Capability</th>
            <th>Default</th>
            <th>Key</th>
            <th>Validated</th>
            <th>Health</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>${renderAiServiceRows(providers)}</tbody>
      </table>
    </div>
  </div>`;
}

// ---------------------------------------------------------------------------
// Top-level renderer + mount
// ---------------------------------------------------------------------------

export function renderProviders(state = {}) {
  const activeTab = state.activeTab || "market-data";
  const tabBtn = (id, tabKey, label) =>
    `<button type="button" role="tab" id="providers-tab-${id}" data-tab="${tabKey}" class="${activeTab === tabKey ? "active" : ""}" aria-selected="${activeTab === tabKey ? "true" : "false"}" aria-controls="providers-tabpanel-${id}" tabindex="${activeTab === tabKey ? "0" : "-1"}">${label}</button>`;
  return `<div class="prov-layout">
  <section class="page-heading prov-page-heading">
    <div>
      <p class="eyebrow">Admin</p>
      <h1>Providers</h1>
      <p class="helper">Market data and AI configuration in one place. Role tags and streams drive resolver Auto-pick; broker accounts stay on the Brokers page.</p>
    </div>
  </section>
  <section class="prov-main-panel">
    <header class="prov-main-tabs">
      <div class="segmented-control prov-tabs" role="tablist" aria-label="Provider domains">
        ${tabBtn("market-data", "market-data", "Market Data Providers")}
        ${tabBtn("ai", "ai", "AI Providers")}
      </div>
    </header>
    <div id="providers-tabpanel-market-data" role="tabpanel" aria-labelledby="providers-tab-market-data" ${activeTab === "market-data" ? "" : "hidden"}>
      ${renderIntegratedMarketData(state)}
    </div>
    <div id="providers-tabpanel-ai" role="tabpanel" aria-labelledby="providers-tab-ai" ${activeTab === "ai" ? "" : "hidden"}>
      ${renderAiTab(state)}
    </div>
  </section>
  </div>`;
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
  const purposes = data.getAll("default_for");
  const base = provider === "alpaca"
    ? compactPayload({
        name: data.get("name"),
        provider,
        api_key: data.get("api_key"),
        api_secret: data.get("api_secret")
      })
    : compactPayload({ name: data.get("name"), provider });
  if (purposes.length) {
    base.default_for = purposes;
  }
  return base;
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
    activeTab: "market-data",
    pipelines: { pipelines: [] },
    marketData: { services: [] },
    ai: { services: [] },
    pipelineFormState: null,
    marketDataFormState: null,
    aiFormState: null,
    expandedPurposesFor: null,
    activeResolverStrategy: "auto",
    resolutionPayload: { intent: DEFAULT_INTENT },
    resolution: null,
    systemStatus: null
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
          <p class="loading-shell__hint">Check that the API server is running, routes /api/v1/market-data and /api/v1/ai are reachable, and Settings documents VITE_API_BASE if the UI is not same-origin.</p>
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

    if (action === "configure-purposes" && id) {
      state.expandedPurposesFor = id;
      root.innerHTML = renderProviders(state);
      return;
    }
    if (action === "cancel-purposes-form") {
      state.expandedPurposesFor = null;
      root.innerHTML = renderProviders(state);
      return;
    }

    if (action === "show-pipeline-form") state.pipelineFormState = { visible: true, provider: "alpaca" };
    if (action === "cancel-pipeline-form") state.pipelineFormState = null;
    if (action === "default-pipeline" && id) await pipelinesApi.setDefaultPipeline(id);
    if (action === "disable-pipeline" && id) await pipelinesApi.disablePipeline(id);
    if (action === "bind-pipeline-service" && id) {
      const services = (state.marketData?.services || []).filter((svc) => svc.status !== "disabled");
      if (services.length === 0) {
        alert("No Market Data Services registered. Add one first.");
        return;
      }
      const choices = services.map((svc) => `${svc.id}  —  ${svc.name} (${svc.provider})`).join("\n");
      const picked = window.prompt(`Bind pipeline ${id} to which Service?\n\n${choices}\n\nPaste the service id (the UUID before the dash):`);
      if (!picked) return;
      const serviceId = picked.trim().split(/\s/)[0];
      try {
        await pipelinesApi.attachServiceToPipeline(id, serviceId);
      } catch (err) {
        alert(`Bind failed: ${err.message || err}`);
      }
    }

    if (action === "show-market-data-form") state.marketDataFormState = { visible: true, provider: "alpaca" };
    if (action === "cancel-market-data-form") state.marketDataFormState = null;
    if (action === "validate-market-data" && id) await servicesApi.validateMarketData(id);
    if (action === "disable-market-data" && id) await servicesApi.disableMarketData(id);
    if (action === "activate-as-stream" && id) {
      state.activeTab = "market-data";
      state.pipelineFormState = {
        visible: true,
        service_id: id,
        trading_mode: "BROKER_PAPER",
        data_feed: "iex"
      };
      root.innerHTML = renderProviders(state);
      return;
    }

    if (action === "set-default-market-data" && id) {
      await servicesApi.setDefaultMarketData(id);
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
    } else if (form.dataset.form === "service-purposes") {
      const serviceId = form.dataset.serviceId;
      const purposes = data.getAll("purposes");
      try {
        await pipelinesApi.setServicePurposeTags(serviceId, purposes);
        state.expandedPurposesFor = null;
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("Failed to update service purposes:", err);
        alert(`Could not save purposes: ${err.message || err}`);
        return;
      }
    } else if (form.dataset.form === "ai") {
      await servicesApi.createAi(normalizeAiPayload(data));
      state.aiFormState = null;
    }
    await refresh();
  });

  await refresh();
}
