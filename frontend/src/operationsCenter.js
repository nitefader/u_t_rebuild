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

function renderAccountSetupPanel(detailState = {}) {
  const status = detailState.accountSetup;
  return `<section class="panel">
    <header><h2>Add Alpaca Paper Account</h2></header>
    <form class="account-form" data-form="alpaca-paper-account">
      <label>
        <span>Display name</span>
        <input name="display_name" autocomplete="off" required>
      </label>
      <label>
        <span>API key</span>
        <input name="api_key" autocomplete="off" required>
      </label>
      <label>
        <span>API secret</span>
        <input name="api_secret" type="password" autocomplete="off" required>
      </label>
      <fieldset>
        <legend>Account Type</legend>
        <label class="checkbox-label">
          <input type="checkbox" checked disabled>
          <span>Paper (safe testing)</span>
        </label>
      </fieldset>
      <button type="submit">Validate and add account</button>
    </form>
    ${status === "loading" ? `<p class="notice">Validating Alpaca paper credentials and syncing broker truth.</p>` : ""}
    ${status === "error" ? `<p class="warning" role="alert">${escapeHtml(detailState.accountSetupError || "Account setup failed.")}</p>` : ""}
    ${status === "success" ? `<p class="notice">Alpaca paper account added and synced.</p>` : ""}
    ${status === "duplicate" ? `<p class="notice">This Alpaca paper account is already registered.</p>` : ""}
  </section>`;
}

function renderAccounts(accounts = [], selection = null) {
  if (!accounts.length) {
    return `<p class="empty">No broker accounts are registered in the Operations API.</p>`;
  }

  return `<div class="summary-grid">${accounts
    .map((account) => {
      const sync = account.sync_state;
      const stale = sync?.is_stale;
      const selected = isSelected(selection, "account", account.account_id);
      return `<article class="summary-card selectable-card ${stale ? "danger-card" : ""} ${selected ? "selected-card" : ""}" role="button" tabindex="0" data-select-type="account" data-id="${escapeHtml(account.account_id)}" aria-pressed="${selected ? "true" : "false"}">
        <header>
          <h3>${escapeHtml(account.account_id)}</h3>
          <span class="${stale ? "status status-danger" : "status"}">${stale ? "stale sync" : "sync current"}</span>
        </header>
        <dl>
          <div><dt>Open orders</dt><dd>${account.open_orders_count ?? 0}</dd></div>
          <div><dt>Open positions</dt><dd>${account.positions_count ?? 0}</dd></div>
          <div><dt>Latest broker sync</dt><dd>${escapeHtml(formatTimestamp(sync?.last_sync_at))}</dd></div>
          <div><dt>Pause state</dt><dd>${escapeHtml(boolLabel(account.is_paused, "paused", "active"))}</dd></div>
        </dl>
        ${stale ? `<p class="warning">Stale broker sync: ${escapeHtml(sync?.stale_reason || "freshness check failed")}</p>` : ""}
        <div class="button-row">
          <button type="button" data-action="account-detail" data-id="${escapeHtml(account.account_id)}">Account detail</button>
          <button type="button" data-action="pause-account" data-id="${escapeHtml(account.account_id)}">Pause</button>
          <button type="button" data-action="resume-account" data-id="${escapeHtml(account.account_id)}">Resume</button>
          <button type="button" class="danger" data-action="flatten-account" data-id="${escapeHtml(account.account_id)}">Flatten</button>
        </div>
      </article>`;
    })
    .join("")}</div>`;
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
  ${renderAccountSetupPanel(detailState)}
  <section class="panel">
    <header><h2>Broker Accounts</h2></header>
    ${renderAccounts(overview.broker_accounts || [], selection)}
  </section>
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
    ${staleAccounts
      .map((sync) => `<p><strong>${escapeHtml(sync.account_id)}</strong>: ${escapeHtml(sync.stale_reason || "sync is stale")} Last sync ${escapeHtml(formatTimestamp(sync.last_sync_at))}.</p>`)
      .join("")}
  </section>`;
}

export function renderAccountDetail(account, flattenResult = null) {
  const snapshot = account.broker_account_snapshot;
  const freshness = account.broker_sync_freshness;
  const flattenState = flattenResult
    ? `<p class="${flattenResult.accepted ? "notice" : "warning"}">Flatten ${escapeHtml(flattenResult.status)}: ${escapeHtml(flattenResult.reason)}</p>`
    : `<p class="notice">Flatten availability is determined by the Operations API. Unsupported or not_ready responses are shown here without retrying.</p>`;
  return `<article>
    <header>
      <h2>Account Detail</h2>
      <div class="button-row">
        <button type="button" data-action="clear-detail">Clear</button>
        <button type="button" data-action="pause-account" data-id="${escapeHtml(account.account_id)}">Pause</button>
        <button type="button" data-action="resume-account" data-id="${escapeHtml(account.account_id)}">Resume</button>
        <span class="status">${escapeHtml(account.account_id)}</span>
      </div>
    </header>
    <dl class="detail-grid">
      <div><dt>Paused</dt><dd>${escapeHtml(boolLabel(account.is_paused, "yes", "no"))}</dd></div>
      <div><dt>Killed</dt><dd>${escapeHtml(boolLabel(account.is_killed, "yes", "no"))}</dd></div>
      <div><dt>Provider</dt><dd>${escapeHtml(snapshot?.provider || "None reported")}</dd></div>
      <div><dt>Mode</dt><dd>${escapeHtml(snapshot?.mode || "None reported")}</dd></div>
      <div><dt>Equity</dt><dd>${renderJsonValue(snapshot?.equity)}</dd></div>
      <div><dt>Cash</dt><dd>${renderJsonValue(snapshot?.cash)}</dd></div>
      <div><dt>Buying power</dt><dd>${renderJsonValue(snapshot?.buying_power)}</dd></div>
      <div><dt>Open broker orders</dt><dd>${account.open_broker_orders?.length ?? 0}</dd></div>
      <div><dt>Positions</dt><dd>${account.positions?.length ?? 0}</dd></div>
      <div><dt>Latest broker sync</dt><dd>${escapeHtml(formatTimestamp(freshness?.last_sync_at))}</dd></div>
      <div><dt>Last poll sync</dt><dd>${escapeHtml(formatTimestamp(freshness?.last_poll_sync_at))}</dd></div>
      <div><dt>Last successful sync</dt><dd>${escapeHtml(formatTimestamp(freshness?.last_successful_sync_at))}</dd></div>
      <div><dt>Internal open orders</dt><dd>${account.internal_order_ledger_summary?.open_count ?? 0}</dd></div>
    </dl>
    ${freshness?.is_stale ? `<p class="warning">Stale broker sync: ${escapeHtml(freshness.stale_reason || "freshness check failed")}</p>` : `<p class="notice">Sync freshness is current according to the Operations API.</p>`}
    ${renderRecordList("Positions", account.positions || [], "No positions reported.", [
      { label: "Symbol", value: (position) => position.symbol },
      { label: "Side", value: (position) => position.side },
      { label: "Quantity", value: (position) => position.qty },
      { label: "Avg entry", value: (position) => position.avg_entry_price },
      { label: "Market value", value: (position) => position.market_value },
      { label: "Timestamp", value: (position) => formatTimestamp(position.timestamp) }
    ])}
    ${renderRecordList("Open Orders", account.open_broker_orders || [], "No open broker orders reported.", [
      { label: "Symbol", value: (order) => order.symbol },
      { label: "Side", value: (order) => order.side },
      { label: "Quantity", value: (order) => order.qty },
      { label: "Status", value: (order) => order.status },
      { label: "Type", value: (order) => order.order_type },
      { label: "Client order", value: (order) => order.client_order_id },
      { label: "Broker order", value: (order) => order.broker_order_id },
      { label: "Timestamp", value: (order) => formatTimestamp(order.timestamp) }
    ])}
    ${flattenState}
  </article>`;
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

export function renderDetailPanel(detailState = {}) {
  if (detailState.status === "custom") {
    return detailState.html;
  }
  if (detailState.status === "loading") {
    const label = detailState.selection?.type === "deployment" ? "deployment" : "account";
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
  if (detailState.status === "loaded" && detailState.selection?.type === "account") {
    return renderAccountDetail(detailState.data, detailState.flattenResult);
  }
  if (detailState.status === "loaded" && detailState.selection?.type === "deployment") {
    return renderDeploymentDetail(detailState.data, detailState.flattenResult);
  }
  return `<p class="empty">Select an account or deployment for detail.</p>`;
}

export async function executeOperationAction(action, id, client, confirmImpl = globalThis.confirm) {
  const destructiveActions = new Set(["global-kill", "flatten-account", "flatten-deployment"]);
  if (destructiveActions.has(action)) {
    const confirmed = typeof confirmImpl === "function" ? confirmImpl(`Confirm ${action.replaceAll("-", " ")}.`) : false;
    if (!confirmed) return { skipped: true };
  }

  const reason = "operator_request";
  switch (action) {
    case "pause-account":
      return client.pauseAccount(id, reason);
    case "resume-account":
      return client.resumeAccount(id, reason);
    case "pause-deployment":
      return client.pauseDeployment(id, reason);
    case "resume-deployment":
      return client.resumeDeployment(id, reason);
    case "global-kill":
      return client.globalKill(reason);
    case "global-resume":
      return client.globalResume(reason);
    case "flatten-account":
      return client.flattenAccount(id, reason);
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
      const data = type === "account" ? await client.getAccount(id) : await client.getDeployment(id);
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
        if (action === "account-detail") {
          await loadSelectedDetail("account", id);
          return;
        }
        if (action === "deployment-detail") {
          await loadSelectedDetail("deployment", id);
          return;
        }
        const result = await executeOperationAction(action, id, client);
        if (result?.skipped) {
          button.disabled = false;
          return;
        }
        if (result?.scope === "account" && action === "flatten-account") {
          state.detail = { status: "loading", selection: { type: "account", id: String(id) } };
          render();
          await refreshOverview();
          await loadSelectedDetail("account", id, result);
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

  root.addEventListener("submit", async (event) => {
    const form = event.target.closest("form[data-form='alpaca-paper-account']");
    if (!form) return;
    event.preventDefault();
    const data = new FormData(form);
    state.detail = { ...state.detail, accountSetup: "loading" };
    render();
    try {
      const result = await client.createAlpacaPaperAccount({
        displayName: data.get("display_name"),
        apiKey: data.get("api_key"),
        apiSecret: data.get("api_secret")
      });
      const accountId = result?.account?.id;
      const accountSetup = result?.already_exists ? "duplicate" : "success";
      state.detail = { status: "empty", accountSetup };
      await refreshOverview();
      if (accountId) {
        await loadSelectedDetail("account", accountId);
        state.detail = { ...state.detail, accountSetup };
        render();
      }
    } catch (error) {
      state.detail = {
        ...state.detail,
        accountSetup: "error",
        accountSetupError: error.message || String(error)
      };
      render();
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
