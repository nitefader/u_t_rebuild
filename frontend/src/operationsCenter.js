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

function renderAccounts(accounts = []) {
  if (!accounts.length) {
    return `<p class="empty">No broker accounts are registered in the Operations API.</p>`;
  }

  return `<div class="summary-grid">${accounts
    .map((account) => {
      const sync = account.sync_state;
      const stale = sync?.is_stale;
      return `<article class="summary-card ${stale ? "danger-card" : ""}">
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

function renderDeployments(deployments = []) {
  if (!deployments.length) {
    return `<p class="empty">No deployments are registered in the Operations API.</p>`;
  }

  const active = deployments.filter((deployment) => deployment.is_running);
  const blocked = deployments.filter((deployment) => deployment.status === BLOCKED);
  const recovered = deployments.filter((deployment) => deployment.status === RECOVERED_READY);

  return `<div class="deployment-columns">
    ${renderDeploymentGroup("Active deployments", active, "No active deployments.")}
    ${renderDeploymentGroup("Blocked recovery", blocked, "No blocked recovery deployments.")}
    ${renderDeploymentGroup("Recovered ready", recovered, "No recovered-ready deployments.")}
  </div>`;
}

function renderDeploymentGroup(title, deployments, emptyText) {
  return `<section class="deployment-group">
    <h3>${title}</h3>
    ${
      deployments.length
        ? deployments.map(renderDeploymentCard).join("")
        : `<p class="empty">${emptyText}</p>`
    }
  </section>`;
}

function renderDeploymentCard(deployment) {
  return `<article class="summary-card ${deployment.status === BLOCKED ? "danger-card" : ""}">
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

export function renderOperationsCenterOverview(overview, detailHtml = "") {
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
  <section class="panel">
    <header><h2>Broker Accounts</h2></header>
    ${renderAccounts(overview.broker_accounts || [])}
  </section>
  <section class="panel">
    <header><h2>Deployments</h2></header>
    ${renderDeployments(overview.deployments || [])}
  </section>
  <section class="panel">
    <header><h2>Latest Governor Decisions</h2></header>
    ${renderGovernorDecisions(overview.latest_governor_decisions || [])}
  </section>
  <section class="detail-panel" id="operations-detail">${detailHtml || `<p class="empty">Select an account or deployment for detail.</p>`}</section>`;
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
  const flattenState = flattenResult
    ? `<p class="${flattenResult.accepted ? "notice" : "warning"}">Flatten ${escapeHtml(flattenResult.status)}: ${escapeHtml(flattenResult.reason)}</p>`
    : `<p class="notice">Flatten availability is determined by the Operations API. Unsupported or not_ready responses are shown here without retrying.</p>`;
  return `<article>
    <header><h2>Account Detail</h2><span class="status">${escapeHtml(account.account_id)}</span></header>
    <dl class="detail-grid">
      <div><dt>Paused</dt><dd>${escapeHtml(boolLabel(account.is_paused, "yes", "no"))}</dd></div>
      <div><dt>Killed</dt><dd>${escapeHtml(boolLabel(account.is_killed, "yes", "no"))}</dd></div>
      <div><dt>Open broker orders</dt><dd>${account.open_broker_orders?.length ?? 0}</dd></div>
      <div><dt>Positions</dt><dd>${account.positions?.length ?? 0}</dd></div>
      <div><dt>Latest broker sync</dt><dd>${escapeHtml(formatTimestamp(account.broker_sync_freshness?.last_sync_at))}</dd></div>
      <div><dt>Internal open orders</dt><dd>${account.internal_order_ledger_summary?.open_count ?? 0}</dd></div>
    </dl>
    ${account.broker_sync_freshness?.is_stale ? `<p class="warning">Stale broker sync: ${escapeHtml(account.broker_sync_freshness.stale_reason || "freshness check failed")}</p>` : ""}
    ${flattenState}
  </article>`;
}

export function renderDeploymentDetail(deployment, flattenResult = null) {
  const flattenState = flattenResult
    ? `<p class="${flattenResult.accepted ? "notice" : "warning"}">Flatten ${escapeHtml(flattenResult.status)}: ${escapeHtml(flattenResult.reason)}</p>`
    : `<p class="notice">Flatten availability is determined by the Operations API. Unsupported or not_ready responses are shown here without retrying.</p>`;
  return `<article>
    <header><h2>Deployment Detail</h2><span class="${statusClass(deployment.runtime_status)}">${escapeHtml(statusLabel(deployment.runtime_status))}</span></header>
    <dl class="detail-grid">
      <div><dt>Deployment</dt><dd>${escapeHtml(deployment.deployment_id)}</dd></div>
      <div><dt>Account</dt><dd>${escapeHtml(deployment.broker_account_id || "unassigned")}</dd></div>
      <div><dt>Governor</dt><dd>${escapeHtml(deployment.governor_id || "unknown")}</dd></div>
      <div><dt>Open orders</dt><dd>${deployment.open_orders?.length ?? 0}</dd></div>
      <div><dt>Trades</dt><dd>${deployment.trades?.length ?? 0}</dd></div>
      <div><dt>Fills</dt><dd>${deployment.fills?.length ?? 0}</dd></div>
      <div><dt>Last broker sync</dt><dd>${escapeHtml(formatTimestamp(deployment.last_broker_sync_timestamp))}</dd></div>
      <div><dt>Last decision</dt><dd>${escapeHtml(formatTimestamp(deployment.last_decision_timestamp))}</dd></div>
    </dl>
    ${renderGovernorDecisions(deployment.latest_governor_decisions || [])}
    ${flattenState}
  </article>`;
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

  async function refresh(detailHtml = "") {
    const overview = await client.getOverview();
    root.innerHTML = renderOperationsCenterOverview(overview, detailHtml);
  }

  root.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    const id = button.dataset.id;
    button.disabled = true;
    try {
      if (action === "account-detail") {
        const account = await client.getAccount(id);
        await refresh(renderAccountDetail(account));
        return;
      }
      if (action === "deployment-detail") {
        const deployment = await client.getDeployment(id);
        await refresh(renderDeploymentDetail(deployment));
        return;
      }
      const result = await executeOperationAction(action, id, client);
      if (result?.scope === "account" && action === "flatten-account") {
        const account = await client.getAccount(id);
        await refresh(renderAccountDetail(account, result));
        return;
      }
      if (result?.scope === "deployment" && action === "flatten-deployment") {
        const deployment = await client.getDeployment(id);
        await refresh(renderDeploymentDetail(deployment, result));
        return;
      }
      await refresh();
    } catch (error) {
      root.innerHTML = renderError(error);
    }
  });

  try {
    await refresh();
  } catch (error) {
    root.innerHTML = renderError(error);
  }
}
