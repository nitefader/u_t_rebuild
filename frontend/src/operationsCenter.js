import { createOperationsApi } from "./api/operations.js";

const BLOCKED = "blocked_recovery";
const RECOVERED_READY = "recovered_ready";
const RUNNING = "running";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatTimestamp(value) {
  if (!value) return "None reported";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function statusClass(status) {
  if (status === BLOCKED) return "status status-blocked";
  if (status === RECOVERED_READY) return "status status-ready";
  if (status === RUNNING) return "status status-running";
  return "status";
}

function statusLabel(status) {
  if (status === RECOVERED_READY) return "recovered ready, not running";
  if (status === BLOCKED) return "blocked recovery";
  return status || "unknown";
}

function boolLabel(value, trueText, falseText) {
  return value ? trueText : falseText;
}

function itemKey(type, id) {
  return `${type}:${id}`;
}

function isSelected(selection, type, id) {
  return selection?.type === type && selection?.id === String(id);
}

function renderJsonValue(value) {
  if (value === null || value === undefined || value === "") return "None reported";
  if (typeof value === "object") return escapeHtml(JSON.stringify(value, null, 2));
  return escapeHtml(value);
}

function formatDateRange(intent = {}) {
  const start = intent.start_at ? formatTimestamp(intent.start_at) : "open start";
  const end = intent.end_at ? formatTimestamp(intent.end_at) : "open end";
  if (!intent.start_at && !intent.end_at) return "live or latest available";
  return `${start} to ${end}`;
}

export function renderDataSourceResolverPanel(resolution = {}) {
  const intent = resolution.intent || {};
  const selected = resolution.selected_service || {
    service_name: resolution.selected_service_name,
    provider: resolution.provider,
    explanation: resolution.explanation
  };
  const rejected = resolution.rejected_candidates || [];
  const selectionMode = resolution.selection_mode || "auto";
  return `<section class="panel data-intent-panel">
    <header>
      <h2>Data Source</h2>
      <div class="segmented-control" role="group" aria-label="Data Source Mode">
        ${["auto", "default", "explicit"]
          .map((mode) => {
            const label = mode === "auto" ? "Auto Recommended" : mode === "default" ? "Use Default" : "Choose Manually";
            return `<button type="button" class="${selectionMode === mode ? "active" : ""}" aria-pressed="${selectionMode === mode ? "true" : "false"}">${label}</button>`;
          })
          .join("")}
      </div>
    </header>
    <div class="resolver-grid">
      <section class="resolver-block">
        <h3>Detected Intent</h3>
        <dl>
          <div><dt>Consumer</dt><dd>${escapeHtml(intent.consumer || "unknown")}</dd></div>
          <div><dt>Timeframe</dt><dd>${escapeHtml(intent.timeframe || "unknown")}</dd></div>
          <div><dt>Date range</dt><dd>${escapeHtml(formatDateRange(intent))}</dd></div>
          <div><dt>Streaming required</dt><dd>${escapeHtml(boolLabel(intent.requires_streaming, "yes", "no"))}</dd></div>
          <div><dt>Intraday required</dt><dd>${escapeHtml(boolLabel(intent.requires_intraday, "yes", "no"))}</dd></div>
        </dl>
      </section>
      <section class="resolver-block">
        <h3>Selected Service</h3>
        <dl>
          <div><dt>Service</dt><dd>${escapeHtml(selected.service_name || "No compatible service")}</dd></div>
          <div><dt>Provider</dt><dd>${escapeHtml(selected.provider || "none")}</dd></div>
          <div><dt>Why selected</dt><dd>${escapeHtml(selected.explanation || resolution.explanation || "No resolver explanation reported.")}</dd></div>
        </dl>
      </section>
    </div>
    <details class="rejected-services">
      <summary>Rejected services (${rejected.length})</summary>
      ${
        rejected.length
          ? `<ul>${rejected
              .map((candidate) => `<li><strong>${escapeHtml(candidate.service_id)}</strong><span>${escapeHtml(candidate.explanation || candidate.reason_code || "not selected")}</span></li>`)
              .join("")}</ul>`
          : `<p class="empty">No rejected services.</p>`
      }
    </details>
  </section>`;
}

function renderRecordList(title, records = [], emptyText, fields = []) {
  if (!records.length) {
    return `<section class="detail-section"><h3>${title}</h3><p class="empty">${emptyText}</p></section>`;
  }

  return `<section class="detail-section">
    <h3>${title}</h3>
    <div class="record-list">${records
      .map((record) => `<article class="record-card">
        <dl>${fields
          .map(({ label, value }) => `<div><dt>${label}</dt><dd>${renderJsonValue(value(record))}</dd></div>`)
          .join("")}</dl>
        ${record.order_id ? `<button type="button" data-action="order-detail" data-id="${escapeHtml(record.order_id)}">Order detail</button>` : ""}
      </article>`)
      .join("")}</div>
  </section>`;
}

function renderGovernorDecisions(decisions = []) {
  if (!decisions.length) {
    return `<p class="empty">No governor decisions reported.</p>`;
  }

  return `<ul class="event-list">${decisions
    .slice(0, 5)
    .map((decision) => {
      const approved = decision.approved ?? decision.allowed ?? decision.is_approved;
      const reason = decision.reason || decision.message || "no reason provided";
      const symbol = decision.symbol ? ` ${escapeHtml(decision.symbol)}` : "";
      return `<li><strong>${escapeHtml(boolLabel(approved, "approved", "blocked"))}${symbol}</strong><span>${escapeHtml(reason)}</span></li>`;
    })
    .join("")}</ul>`;
}

function renderDeployments(deployments = [], selection = null) {
  if (!deployments.length) {
    return `<p class="empty">No deployments are registered in the Operations API.</p>`;
  }

  const active = deployments.filter((deployment) => deployment.is_running);
  const blocked = deployments.filter((deployment) => deployment.status === BLOCKED);
  const recovered = deployments.filter((deployment) => deployment.status === RECOVERED_READY);

  return `<div class="deployment-columns">
    ${renderDeploymentGroup("Active deployments", active, "No active deployments.", selection)}
    ${renderDeploymentGroup("Blocked recovery", blocked, "No blocked recovery deployments.", selection)}
    ${renderDeploymentGroup("Recovered ready", recovered, "No recovered-ready deployments.", selection)}
  </div>`;
}

function renderDeploymentGroup(title, deployments, emptyText, selection) {
  return `<section class="deployment-group">
    <h3>${title}</h3>
    ${
      deployments.length
        ? deployments.map((deployment) => renderDeploymentCard(deployment, selection)).join("")
        : `<p class="empty">${emptyText}</p>`
    }
  </section>`;
}

function renderDeploymentCard(deployment, selection = null) {
  const selected = isSelected(selection, "deployment", deployment.deployment_id);
  return `<article class="summary-card selectable-card ${deployment.status === BLOCKED ? "danger-card" : ""} ${selected ? "selected-card" : ""}" role="button" tabindex="0" data-select-type="deployment" data-id="${escapeHtml(deployment.deployment_id)}" aria-pressed="${selected ? "true" : "false"}">
    <header>
      <h4>${escapeHtml(deployment.deployment_id)}</h4>
      <span class="${statusClass(deployment.status)}">${escapeHtml(statusLabel(deployment.status))}</span>
    </header>
    <dl>
      <div><dt>Account</dt><dd>${escapeHtml(deployment.account_id || "unassigned")}</dd></div>
      <div><dt>Program</dt><dd>${escapeHtml(deployment.program_id || "unknown")}</dd></div>
      <div><dt>Version</dt><dd>${escapeHtml(deployment.program_version ?? "unknown")}</dd></div>
    </dl>
    <div class="button-row">
      <button type="button" data-action="deployment-detail" data-id="${escapeHtml(deployment.deployment_id)}">Deployment detail</button>
      <button type="button" data-action="pause-deployment" data-id="${escapeHtml(deployment.deployment_id)}">Pause</button>
      <button type="button" data-action="resume-deployment" data-id="${escapeHtml(deployment.deployment_id)}">Resume</button>
      <button type="button" class="danger" data-action="flatten-deployment" data-id="${escapeHtml(deployment.deployment_id)}">Flatten</button>
    </div>
  </article>`;
}

export function renderOperationsCenterOverview(overview, detailState = {}) {
  if (typeof detailState === "string") {
    detailState = detailState ? { status: "custom", html: detailState } : {};
  }
  const selection = detailState.selection || null;
  return `<section class="page-heading">
    <div>
      <p class="eyebrow">Runtime visibility and operator controls</p>
      <h1>Operations Center</h1>
      <p class="helper">Deployments, orders, and system-wide runtime state. Broker accounts live on the <a href="./brokers.html">Brokers</a> page.</p>
    </div>
    <div class="global-controls">
      <button type="button" class="danger" data-action="global-kill">Global kill</button>
      <button type="button" data-action="global-resume">Global resume</button>
    </div>
  </section>
  <section class="state-strip" aria-label="Global runtime state">
    <article class="${overview.system_recovery_active ? "danger-card" : ""}">
      <span>Recovery</span>
      <strong>${escapeHtml(boolLabel(overview.system_recovery_active, "active", "inactive"))}</strong>
    </article>
    <article class="${overview.global_kill_active ? "danger-card" : ""}">
      <span>Global kill</span>
      <strong>${escapeHtml(boolLabel(overview.global_kill_active, "active", "inactive"))}</strong>
    </article>
    <article>
      <span>Open orders</span>
      <strong>${overview.open_orders_count ?? 0}</strong>
    </article>
    <article>
      <span>Open positions</span>
      <strong>${overview.open_positions_count ?? 0}</strong>
    </article>
    <article>
      <span>Latest broker sync</span>
      <strong>${escapeHtml(formatTimestamp(overview.latest_broker_sync_timestamp))}</strong>
    </article>
    <article>
      <span>Latest runtime event</span>
      <strong>${escapeHtml(formatTimestamp(overview.latest_runtime_event_timestamp))}</strong>
    </article>
  </section>
  ${renderStaleSyncWarnings(overview.stale_sync_accounts || [])}
  ${overview.market_data_resolution ? renderDataSourceResolverPanel(overview.market_data_resolution) : ""}
  <section class="panel">
    <header><h2>Deployments</h2></header>
    ${renderDeployments(overview.deployments || [], selection)}
  </section>
  <section class="panel">
    <header><h2>Latest Governor Decisions</h2></header>
    ${renderGovernorDecisions(overview.latest_governor_decisions || [])}
  </section>
  <section class="detail-panel" id="operations-detail">${renderDetailPanel(detailState)}</section>`;
}

function renderStaleSyncWarnings(staleAccounts) {
  if (!staleAccounts.length) return "";
  return `<section class="alert-panel" role="alert">
    <h2>Stale Broker Sync</h2>
    <p class="helper">Account-level staleness detected. Investigate from the <a href="./brokers.html">Brokers</a> page.</p>
    ${staleAccounts
      .map((sync) => `<p><strong>${escapeHtml(sync.account_id)}</strong>: ${escapeHtml(sync.stale_reason || "sync is stale")} Last sync ${escapeHtml(formatTimestamp(sync.last_sync_at))}.</p>`)
      .join("")}
  </section>`;
}

export function renderDeploymentDetail(deployment, flattenResult = null) {
  const flattenState = flattenResult
    ? `<p class="${flattenResult.accepted ? "notice" : "warning"}">Flatten ${escapeHtml(flattenResult.status)}: ${escapeHtml(flattenResult.reason)}</p>`
    : `<p class="notice">Flatten availability is determined by the Operations API. Unsupported or not_ready responses are shown here without retrying.</p>`;
  return `<article>
    <header>
      <h2>Deployment Detail</h2>
      <div class="button-row">
        <button type="button" data-action="clear-detail">Clear</button>
        <button type="button" data-action="pause-deployment" data-id="${escapeHtml(deployment.deployment_id)}">Pause</button>
        <button type="button" data-action="resume-deployment" data-id="${escapeHtml(deployment.deployment_id)}">Resume</button>
        <span class="${statusClass(deployment.runtime_status)}">${escapeHtml(statusLabel(deployment.runtime_status))}</span>
      </div>
    </header>
    <dl class="detail-grid">
      <div><dt>Deployment</dt><dd>${escapeHtml(deployment.deployment_id)}</dd></div>
      <div><dt>Account</dt><dd>${escapeHtml(deployment.broker_account_id || "unassigned")}</dd></div>
      <div><dt>Runtime status</dt><dd>${escapeHtml(statusLabel(deployment.runtime_status))}</dd></div>
      <div><dt>Program id</dt><dd>${escapeHtml(deployment.program_id || "unknown")}</dd></div>
      <div><dt>Program version</dt><dd>${escapeHtml(deployment.program_version ?? "unknown")}</dd></div>
      <div><dt>Governor</dt><dd>${escapeHtml(deployment.governor_id || "unknown")}</dd></div>
      <div><dt>Governor state</dt><dd><pre>${renderJsonValue(deployment.governor_state)}</pre></dd></div>
      <div><dt>Open orders</dt><dd>${deployment.open_orders?.length ?? 0}</dd></div>
      <div><dt>Trades</dt><dd>${deployment.trades?.length ?? 0}</dd></div>
      <div><dt>Fills</dt><dd>${deployment.fills?.length ?? 0}</dd></div>
      <div><dt>Last market data</dt><dd>${escapeHtml(formatTimestamp(deployment.last_market_data_timestamp))}</dd></div>
      <div><dt>Last broker sync</dt><dd>${escapeHtml(formatTimestamp(deployment.last_broker_sync_timestamp))}</dd></div>
      <div><dt>Last decision</dt><dd>${escapeHtml(formatTimestamp(deployment.last_decision_timestamp))}</dd></div>
    </dl>
    ${renderRecordList("Open Orders", deployment.open_orders || [], "No open internal orders reported.", [
      { label: "Symbol", value: (order) => order.symbol },
      { label: "Side", value: (order) => order.side },
      { label: "Quantity", value: (order) => order.quantity ?? order.qty },
      { label: "Status", value: (order) => order.status },
      { label: "Type", value: (order) => order.order_type },
      { label: "Client order", value: (order) => order.client_order_id },
      { label: "Created", value: (order) => formatTimestamp(order.created_at || order.timestamp) }
    ])}
    ${renderRecordList("Trades", deployment.trades || [], "No trades reported.", [
      { label: "Symbol", value: (trade) => trade.symbol },
      { label: "Side", value: (trade) => trade.side },
      { label: "Quantity", value: (trade) => trade.qty },
      { label: "Price", value: (trade) => trade.price },
      { label: "Broker order", value: (trade) => trade.broker_order_id },
      { label: "Event", value: (trade) => formatTimestamp(trade.event_at || trade.timestamp) }
    ])}
    ${renderRecordList("Fills", deployment.fills || [], "No fills reported.", [
      { label: "Symbol", value: (fill) => fill.symbol },
      { label: "Side", value: (fill) => fill.side },
      { label: "Quantity", value: (fill) => fill.qty },
      { label: "Price", value: (fill) => fill.price },
      { label: "Execution", value: (fill) => fill.broker_execution_id },
      { label: "Event", value: (fill) => formatTimestamp(fill.event_at || fill.timestamp) }
    ])}
    ${renderGovernorDecisions(deployment.latest_governor_decisions || [])}
    ${flattenState}
  </article>`;
}

export function renderOrderDetail(detail) {
  const order = detail.internal_order || {};
  const mapping = detail.broker_mapping;
  return `<article>
    <header>
      <h2>Order Detail</h2>
      <button type="button" data-action="clear-detail">Clear</button>
    </header>
    <section class="detail-section">
      <h3>Internal Order Truth</h3>
      <dl class="detail-grid">
        <div><dt>Internal order id</dt><dd>${escapeHtml(order.order_id)}</dd></div>
        <div><dt>Client order id</dt><dd>${escapeHtml(order.client_order_id)}</dd></div>
        <div><dt>Broker account</dt><dd>${escapeHtml(detail.broker_account_id)}</dd></div>
        <div><dt>Deployment</dt><dd>${escapeHtml(detail.deployment_id)}</dd></div>
        <div><dt>Program</dt><dd>${escapeHtml(detail.program_id)}</dd></div>
        <div><dt>Symbol</dt><dd>${escapeHtml(order.symbol)}</dd></div>
        <div><dt>Side</dt><dd>${escapeHtml(order.side)}</dd></div>
        <div><dt>Quantity</dt><dd>${renderJsonValue(order.quantity)}</dd></div>
        <div><dt>Filled quantity</dt><dd>${renderJsonValue(order.filled_quantity)}</dd></div>
        <div><dt>Order type</dt><dd>${escapeHtml(order.order_type)}</dd></div>
        <div><dt>Time in force</dt><dd>${escapeHtml(order.time_in_force)}</dd></div>
        <div><dt>Intent</dt><dd>${escapeHtml(order.intent)}</dd></div>
        <div><dt>Internal status</dt><dd>${escapeHtml(order.status)}</dd></div>
        <div><dt>Reason</dt><dd>${escapeHtml(order.reason || "None reported")}</dd></div>
        <div><dt>Created</dt><dd>${escapeHtml(formatTimestamp(order.created_at))}</dd></div>
        <div><dt>Submitted</dt><dd>${escapeHtml(formatTimestamp(order.submitted_at))}</dd></div>
        <div><dt>Updated</dt><dd>${escapeHtml(formatTimestamp(order.updated_at))}</dd></div>
        <div><dt>Filled</dt><dd>${escapeHtml(formatTimestamp(order.filled_at))}</dd></div>
      </dl>
    </section>
    <section class="detail-section">
      <h3>Broker Mapped Truth</h3>
      <dl class="detail-grid">
        <div><dt>Broker order id</dt><dd>${escapeHtml(detail.broker_order_id || "unknown")}</dd></div>
        <div><dt>Broker status</dt><dd>${escapeHtml(detail.broker_status || "unknown_stale")}</dd></div>
        <div><dt>Provider</dt><dd>${escapeHtml(mapping?.provider || "unknown")}</dd></div>
        <div><dt>Mapping synced</dt><dd>${escapeHtml(formatTimestamp(mapping?.last_synced_at))}</dd></div>
        <div><dt>Broker sync freshness</dt><dd>${escapeHtml(formatTimestamp(detail.broker_sync_timestamp))}</dd></div>
      </dl>
      ${!mapping ? `<p class="warning">Broker state is unknown/stale until BrokerSync maps this order.</p>` : ""}
    </section>
    <section class="detail-section">
      <h3>Trade/Fill Truth</h3>
      <pre>${renderJsonValue(detail.trade_summary)}</pre>
      ${renderRecordList("Fills", detail.fills || [], "No fills reported.", [
        { label: "Symbol", value: (fill) => fill.symbol },
        { label: "Quantity", value: (fill) => fill.qty },
        { label: "Price", value: (fill) => fill.price },
        { label: "Event", value: (fill) => formatTimestamp(fill.event_at) }
      ])}
    </section>
  </article>`;
}

export function renderDetailPanel(detailState = {}) {
  if (detailState.status === "custom") {
    return detailState.html;
  }
  if (detailState.status === "loading") {
    const label = detailState.selection?.type || "deployment";
    return `<div class="detail-loading" role="status"><span class="spinner" aria-hidden="true"></span><p>Loading ${label} detail from the Operations API.</p></div>`;
  }
  if (detailState.status === "error") {
    return `<article class="detail-error" role="alert">
      <header>
        <h2>Detail unavailable</h2>
        <button type="button" data-action="clear-detail">Clear</button>
      </header>
      <p>${escapeHtml(detailState.error?.message || detailState.error || "Operations API request failed.")}</p>
      <p class="warning">No previous detail data is shown because freshness could not be verified.</p>
    </article>`;
  }
  if (detailState.status === "loaded" && detailState.selection?.type === "deployment") {
    return renderDeploymentDetail(detailState.data, detailState.flattenResult);
  }
  if (detailState.status === "loaded" && detailState.selection?.type === "order") {
    return renderOrderDetail(detailState.data);
  }
  return `<p class="empty">Select a deployment for detail.</p>`;
}

export async function executeOperationAction(action, id, client, confirmImpl = globalThis.confirm) {
  const destructiveActions = new Set(["global-kill", "flatten-deployment"]);
  if (destructiveActions.has(action)) {
    const confirmed = typeof confirmImpl === "function" ? confirmImpl(`Confirm ${action.replaceAll("-", " ")}.`) : false;
    if (!confirmed) return { skipped: true };
  }

  const reason = "operator_request";
  switch (action) {
    case "pause-deployment":
      return client.pauseDeployment(id, reason);
    case "resume-deployment":
      return client.resumeDeployment(id, reason);
    case "global-kill":
      return client.globalKill(reason);
    case "global-resume":
      return client.globalResume(reason);
    case "flatten-deployment":
      return client.flattenDeployment(id, reason);
    default:
      throw new Error(`Unknown operations action: ${action}`);
  }
}

export function renderError(error) {
  return `<section class="alert-panel" role="alert"><h1>Operations Center unavailable</h1><p>${escapeHtml(error.message || error)}</p><p>Control state is unknown while this error is visible.</p></section>`;
}

export async function mountOperationsCenter(root, client = createOperationsApi()) {
  root.innerHTML = `<section class="loading-shell"><h1>Operations Center</h1><p>Loading runtime visibility. Controls are unavailable until Operations API state returns.</p></section>`;
  const state = {
    overview: null,
    detail: { status: "empty" }
  };

  function render() {
    if (!state.overview) return;
    root.innerHTML = renderOperationsCenterOverview(state.overview, state.detail);
  }

  async function refreshOverview() {
    state.overview = await client.getOverview();
    render();
  }

  async function loadSelectedDetail(type, id, flattenResult = null) {
    const selection = { type, id: String(id) };
    state.detail = { status: "loading", selection };
    render();
    try {
      const data = type === "deployment" ? await client.getDeployment(id) : await client.getOrder(id);
      if (itemKey(state.detail.selection?.type, state.detail.selection?.id) !== itemKey(type, id)) return;
      state.detail = { status: "loaded", selection, data, flattenResult };
      render();
    } catch (error) {
      if (itemKey(state.detail.selection?.type, state.detail.selection?.id) !== itemKey(type, id)) return;
      state.detail = { status: "error", selection, error };
      render();
    }
  }

  async function refreshSelection(flattenResult = null) {
    const selection = state.detail.selection;
    await refreshOverview();
    if (selection) {
      await loadSelectedDetail(selection.type, selection.id, flattenResult);
    }
  }

  root.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (button) {
      const action = button.dataset.action;
      const id = button.dataset.id;
      button.disabled = true;
      try {
        if (action === "clear-detail") {
          state.detail = { status: "empty" };
          render();
          return;
        }
        if (action === "deployment-detail") {
          await loadSelectedDetail("deployment", id);
          return;
        }
        if (action === "order-detail") {
          await loadSelectedDetail("order", id);
          return;
        }
        const result = await executeOperationAction(action, id, client);
        if (result?.skipped) {
          button.disabled = false;
          return;
        }
        if (result?.scope === "deployment" && action === "flatten-deployment") {
          state.detail = { status: "loading", selection: { type: "deployment", id: String(id) } };
          render();
          await refreshOverview();
          await loadSelectedDetail("deployment", id, result);
          return;
        }
        await refreshSelection();
      } catch (error) {
        state.detail = { status: "error", selection: state.detail.selection, error };
        if (state.overview) render();
        else root.innerHTML = renderError(error);
      }
      return;
    }

    const card = event.target.closest("[data-select-type][data-id]");
    if (card) {
      await loadSelectedDetail(card.dataset.selectType, card.dataset.id);
    }
  });

  root.addEventListener("keydown", async (event) => {
    if (!["Enter", " "].includes(event.key)) return;
    const card = event.target.closest("[data-select-type][data-id]");
    if (!card) return;
    event.preventDefault();
    await loadSelectedDetail(card.dataset.selectType, card.dataset.id);
  });

  try {
    await refreshOverview();
  } catch (error) {
    root.innerHTML = renderError(error);
  }
}
