import { createServicesApi } from "./api/services.js";
import { renderDataSourceResolverPanel } from "./operationsCenter.js";

const MASKED = "********";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function serviceDefault(services = []) {
  return services.find((service) => service.is_default);
}

function health(services = []) {
  const invalid = services.filter((service) => service.status === "invalid").length;
  const disabled = services.filter((service) => service.status === "disabled").length;
  return `${services.length} configured · ${invalid} invalid · ${disabled} disabled`;
}

function chips(capabilities = {}) {
  return Object.entries(capabilities)
    .filter(([, enabled]) => enabled === true)
    .map(([key]) => `<span class="status">${escapeHtml(key.replace("supports_", ""))}</span>`)
    .join("");
}

export function renderServicesCenter(state = {}) {
  const marketData = state.marketData?.services || [];
  const ai = state.ai?.services || [];
  const activeTab = state.activeTab || "market-data";
  const resolver = state.resolution
    ? renderDataSourceResolverPanel({
        selection_mode: state.resolution.selection_mode,
        intent: state.resolution.intent,
        selected_service: {
          service_name: state.resolution.selected_service_name,
          provider: state.resolution.provider,
          explanation: state.resolution.explanation
        },
        rejected_candidates: state.resolution.rejected_candidates || []
      })
    : "";

  return `<section class="page-heading">
    <div>
      <p class="eyebrow">External capabilities</p>
      <h1>Services Center</h1>
    </div>
  </section>
  <section class="state-strip">
    <article><span>Default Market Data Service</span><strong>${escapeHtml(serviceDefault(marketData)?.name || "None configured")}</strong></article>
    <article><span>Default AI Service</span><strong>${escapeHtml(serviceDefault(ai)?.name || "None configured")}</strong></article>
    <article><span>Service Health</span><strong>${escapeHtml(health([...marketData, ...ai]))}</strong></article>
  </section>
  <section class="panel">
    <header>
      <h2>Services</h2>
      <div class="segmented-control" role="tablist">
        <button type="button" data-tab="market-data" class="${activeTab === "market-data" ? "active" : ""}">Market Data Services</button>
        <button type="button" data-tab="ai" class="${activeTab === "ai" ? "active" : ""}">AI Services</button>
        <button type="button" data-tab="logs" class="${activeTab === "logs" ? "active" : ""}">Service Logs</button>
      </div>
    </header>
    ${activeTab === "ai" ? renderAiSection(ai) : activeTab === "logs" ? renderLogs(marketData, ai) : renderMarketDataSection(marketData)}
  </section>
  ${resolver}`;
}

function renderMarketDataSection(services) {
  return `<div class="button-row"><button type="button" data-action="show-market-data-form">Add Market Data Service</button><button type="button" data-action="resolve-sample">Resolve Sample Intent</button></div>
  ${renderMarketDataForm()}
  <div class="service-table">${services.map(renderMarketDataRow).join("") || `<p class="empty">No Market Data Services configured.</p>`}</div>`;
}

function renderMarketDataRow(service) {
  return `<article class="record-card service-row">
    <header><h3>${escapeHtml(service.name)}</h3><span class="status">${escapeHtml(service.status)}</span></header>
    <dl class="detail-grid">
      <div><dt>Provider</dt><dd>${escapeHtml(service.provider)}</dd></div>
      <div><dt>Mode</dt><dd>${escapeHtml(service.mode)}</dd></div>
      <div><dt>Default</dt><dd>${service.is_default ? "yes" : "no"}</dd></div>
      <div><dt>Credentials</dt><dd>${service.has_api_key || service.has_api_secret ? MASKED : "none required"}</dd></div>
      <div><dt>Validation</dt><dd>${escapeHtml(service.validation_status || "not validated")} ${escapeHtml(service.validation_message || "")}</dd></div>
    </dl>
    <div class="chip-row">${chips(service.capabilities)}</div>
    <div class="button-row">
      <button type="button" data-action="edit-market-data" data-id="${escapeHtml(service.id)}">Edit</button>
      <button type="button" data-action="validate-market-data" data-id="${escapeHtml(service.id)}">Validate</button>
      <button type="button" data-action="default-market-data" data-id="${escapeHtml(service.id)}">Set default</button>
      <button type="button" data-action="disable-market-data" data-id="${escapeHtml(service.id)}">Disable</button>
    </div>
  </article>`;
}

function renderMarketDataForm() {
  return `<form class="account-form service-form" data-form="market-data">
    <label><span>Name</span><input name="name" required></label>
    <label><span>Provider</span><select name="provider" data-provider-select="market-data"><option value="alpaca">Alpaca</option><option value="yahoo">Yahoo</option><option value="future">Future</option></select></label>
    <label data-field="alpaca"><span>Mode</span><select name="mode"><option value="paper">paper</option><option value="live">live</option></select></label>
    <label data-field="alpaca"><span>API key</span><input name="api_key" autocomplete="off" placeholder="${MASKED}"></label>
    <label data-field="alpaca"><span>API secret</span><input name="api_secret" type="password" autocomplete="off" placeholder="${MASKED}"></label>
    <button type="submit">Save Market Data Service</button>
  </form>`;
}

function renderAiSection(services) {
  return `<div class="button-row"><button type="button" data-action="show-ai-form">Add AI Service</button></div>
  ${renderAiForm()}
  <div class="service-table">${services.map(renderAiRow).join("") || `<p class="empty">No AI Services configured.</p>`}</div>`;
}

function renderAiRow(service) {
  return `<article class="record-card service-row">
    <header><h3>${escapeHtml(service.name)}</h3><span class="status">${escapeHtml(service.status)}</span></header>
    <dl class="detail-grid">
      <div><dt>Provider</dt><dd>${escapeHtml(service.provider)}</dd></div>
      <div><dt>Default</dt><dd>${service.is_default ? "yes" : "no"}</dd></div>
      <div><dt>Capability</dt><dd>${escapeHtml(service.capability_label)}</dd></div>
      <div><dt>API key</dt><dd>${service.has_api_key ? MASKED : "not saved"}</dd></div>
      <div><dt>Validation</dt><dd>${escapeHtml(service.validation_status || "not validated")} ${escapeHtml(service.validation_message || "")}</dd></div>
    </dl>
    <div class="button-row">
      <button type="button" data-action="edit-ai" data-id="${escapeHtml(service.id)}">Edit</button>
      <button type="button" data-action="validate-ai" data-id="${escapeHtml(service.id)}">Validate</button>
      <button type="button" data-action="default-ai" data-id="${escapeHtml(service.id)}">Set default</button>
      <button type="button" data-action="disable-ai" data-id="${escapeHtml(service.id)}">Disable</button>
    </div>
  </article>`;
}

function renderAiForm() {
  return `<form class="account-form service-form" data-form="ai">
    <label><span>Name</span><input name="name" required></label>
    <label><span>Provider</span><select name="provider" data-provider-select="ai"><option value="groq">Groq</option><option value="claude">Claude</option><option value="openai">OpenAI</option><option value="codex">Codex</option><option value="future">Future</option></select></label>
    <label><span>API key</span><input name="api_key" type="password" autocomplete="off" placeholder="${MASKED}"></label>
    <label><span>Capability</span><select name="capability_label"><option value="fast">fast</option><option value="reasoning">reasoning</option><option value="coding">coding</option><option value="general">general</option><option value="unknown">unknown</option></select></label>
    <button type="submit">Save AI Service</button>
  </form>`;
}

function renderLogs(marketData, ai) {
  const rows = [...marketData, ...ai].filter((service) => service.last_validated_at || service.validation_status);
  return `<div class="record-list">${rows.map((service) => `<article class="record-card"><h3>${escapeHtml(service.name)}</h3><p>${escapeHtml(service.validation_status || "not validated")}: ${escapeHtml(service.validation_message || "")}</p><p class="empty">${escapeHtml(service.last_validated_at || "No validation timestamp")}</p></article>`).join("") || `<p class="empty">No validation history yet.</p>`}</div>`;
}

export async function mountServicesCenter(root, client = createServicesApi()) {
  const state = { marketData: { services: [] }, ai: { services: [] }, activeTab: "market-data" };
  async function refresh() {
    state.marketData = await client.listMarketData();
    state.ai = await client.listAi();
    root.innerHTML = renderServicesCenter(state);
  }
  root.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-tab], button[data-action]");
    if (!button) return;
    if (button.dataset.tab) {
      state.activeTab = button.dataset.tab;
      root.innerHTML = renderServicesCenter(state);
      return;
    }
    const id = button.dataset.id;
    const action = button.dataset.action;
    if (action === "validate-market-data") await client.validateMarketData(id);
    if (action === "default-market-data") await client.setDefaultMarketData(id);
    if (action === "disable-market-data") await client.disableMarketData(id);
    if (action === "validate-ai") await client.validateAi(id);
    if (action === "default-ai") await client.setDefaultAi(id);
    if (action === "disable-ai") await client.disableAi(id);
    if (action === "resolve-sample") {
      state.resolution = await client.resolveMarketData({
        selection_mode: "auto",
        intent: { consumer: "backtest", mode: "replay", symbols: ["SPY"], timeframe: "1d", purpose: "backtest", start_at: "2023-01-01T00:00:00Z", end_at: "2026-01-01T00:00:00Z" }
      });
    }
    await refresh();
  });
  root.addEventListener("change", (event) => {
    const select = event.target.closest("[data-provider-select='market-data']");
    if (!select) return;
    const showAlpaca = select.value === "alpaca";
    root.querySelectorAll("[data-field='alpaca']").forEach((field) => {
      field.hidden = !showAlpaca;
    });
  });
  root.addEventListener("submit", async (event) => {
    const form = event.target.closest("form[data-form]");
    if (!form) return;
    event.preventDefault();
    const data = new FormData(form);
    if (form.dataset.form === "market-data") {
      await client.createMarketData(compactPayload({ name: data.get("name"), provider: data.get("provider"), mode: data.get("provider") === "yahoo" ? "none" : data.get("mode"), api_key: data.get("api_key"), api_secret: data.get("api_secret") }));
    } else {
      await client.createAi(compactPayload({ name: data.get("name"), provider: data.get("provider"), api_key: data.get("api_key"), capability_label: data.get("capability_label") }));
    }
    form.reset();
    await refresh();
  });
  await refresh();
}

function compactPayload(payload) {
  return Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== null && value !== undefined && value !== ""));
}
