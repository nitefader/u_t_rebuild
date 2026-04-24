import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { createOperationsApi } from "../src/api/operations.js";
import {
  executeOperationAction,
  renderAccountDetail,
  renderDeploymentDetail,
  renderDetailPanel,
  renderOrderDetail,
  renderOperationsCenterOverview
} from "../src/operationsCenter.js";

const accountId = "11111111-2222-3333-4444-555555555555";
const deploymentId = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";

function overview(overrides = {}) {
  return {
    system_recovery_active: true,
    global_kill_active: false,
    control_state: {},
    broker_accounts: [
      {
        account_id: accountId,
        sync_state: {
          account_id: accountId,
          last_sync_at: "2026-04-24T15:00:00Z",
          is_stale: false
        },
        open_orders_count: 2,
        positions_count: 3,
        is_paused: false,
        is_killed: false
      }
    ],
    deployments: [
      {
        deployment_id: deploymentId,
        status: "running",
        is_running: true,
        account_id: accountId,
        program_id: "program-a",
        program_version: 1
      }
    ],
    stale_sync_accounts: [],
    blocked_deployments: [],
    open_orders_count: 2,
    open_positions_count: 3,
    latest_governor_decisions: [{ approved: true, reason: "within limits", symbol: "SPY" }],
    latest_broker_sync_timestamp: "2026-04-24T15:00:00Z",
    latest_runtime_event_timestamp: "2026-04-24T15:01:00Z",
    ...overrides
  };
}

test("overview renders recovery, kill, sync, deployment, order, and position state", () => {
  const html = renderOperationsCenterOverview(overview());

  assert.match(html, /Recovery/);
  assert.match(html, /Global kill/);
  assert.match(html, /Open orders/);
  assert.match(html, /Open positions/);
  assert.match(html, /Latest broker sync/);
  assert.match(html, /Latest runtime event/);
  assert.match(html, /Active deployments/);
  assert.match(html, /Latest Governor Decisions/);
  assert.match(html, /SPY/);
});

test("stale broker sync warning renders visibly", () => {
  const html = renderOperationsCenterOverview(overview({
    broker_accounts: [
      {
        account_id: accountId,
        sync_state: {
          account_id: accountId,
          last_sync_at: "2026-04-24T14:00:00Z",
          is_stale: true,
          stale_reason: "no sync for 10 minutes"
        },
        open_orders_count: 0,
        positions_count: 0
      }
    ],
    stale_sync_accounts: [
      {
        account_id: accountId,
        last_sync_at: "2026-04-24T14:00:00Z",
        is_stale: true,
        stale_reason: "no sync for 10 minutes"
      }
    ]
  }));

  assert.match(html, /Stale Broker Sync/);
  assert.match(html, /danger-card/);
  assert.match(html, /no sync for 10 minutes/);
});

test("blocked_recovery renders as blocked", () => {
  const html = renderOperationsCenterOverview(overview({
    deployments: [
      {
        deployment_id: deploymentId,
        status: "blocked_recovery",
        is_running: false,
        account_id: accountId
      }
    ]
  }));

  assert.match(html, /Blocked recovery/);
  assert.match(html, /blocked recovery/);
  assert.match(html, /status-blocked/);
});

test("recovered_ready renders as ready but not running", () => {
  const html = renderOperationsCenterOverview(overview({
    deployments: [
      {
        deployment_id: deploymentId,
        status: "recovered_ready",
        is_running: false,
        account_id: accountId
      }
    ]
  }));

  assert.match(html, /Recovered ready/);
  assert.match(html, /recovered ready, not running/);
  assert.doesNotMatch(html, /status-running/);
});

test("pause and resume deployment call correct API routes", async () => {
  const calls = [];
  const api = createOperationsApi(async (url, options = {}) => {
    calls.push([url, options.method, options.body]);
    return { ok: true, json: async () => ({ accepted: true }) };
  });

  await api.pauseDeployment(deploymentId, "maintenance");
  await api.resumeDeployment(deploymentId, "ready");

  assert.equal(calls[0][0], `/api/v1/operations/deployments/${deploymentId}/pause`);
  assert.equal(calls[0][1], "POST");
  assert.equal(calls[1][0], `/api/v1/operations/deployments/${deploymentId}/resume`);
  assert.equal(calls[1][1], "POST");
});

test("account and deployment detail calls use Operations API routes", async () => {
  const calls = [];
  const api = createOperationsApi(async (url, options = {}) => {
    calls.push([url, options.method || "GET"]);
    return { ok: true, json: async () => ({}) };
  });

  await api.getAccount(accountId);
  await api.getDeployment(deploymentId);
  await api.getOrder("order-1");

  assert.deepEqual(calls, [
    [`/api/v1/operations/accounts/${accountId}`, "GET"],
    [`/api/v1/operations/deployments/${deploymentId}`, "GET"],
    ["/api/v1/operations/orders/order-1", "GET"]
  ]);
});

test("alpaca paper account creation uses broker account API without URL input", async () => {
  const calls = [];
  const api = createOperationsApi(async (url, options = {}) => {
    calls.push([url, options.method || "GET", JSON.parse(options.body)]);
    return { ok: true, json: async () => ({ account: { id: accountId } }) };
  });

  await api.createAlpacaPaperAccount({
    displayName: "Paper",
    apiKey: "key",
    apiSecret: "secret"
  });

  assert.equal(calls[0][0], "/api/v1/broker-accounts/alpaca-paper");
  assert.equal(calls[0][1], "POST");
  assert.deepEqual(calls[0][2], {
    display_name: "Paper",
    api_key: "key",
    api_secret: "secret"
  });
  assert.ok(!("base_url" in calls[0][2]));
});

test("account setup UI is paper only and does not ask for API URLs", () => {
  const html = renderOperationsCenterOverview(overview());

  assert.match(html, /Add Alpaca Paper Account/);
  assert.match(html, /Paper \(safe testing\)/);
  assert.match(html, /name="api_key"/);
  assert.match(html, /name="api_secret"/);
  assert.doesNotMatch(html, /base_url|base url|endpoint|environment URL|api endpoint/i);
});

test("credential replacement and account deletion use broker account API without exposing secrets", async () => {
  const calls = [];
  const api = createOperationsApi(async (url, options = {}) => {
    calls.push([url, options.method || "GET", options.body ? JSON.parse(options.body) : null]);
    return { ok: true, json: async () => ({ validation_status: "valid", message: "ok" }) };
  });

  const replace = await api.replaceAlpacaPaperCredentials(accountId, { apiKey: "new-key", apiSecret: "new-secret" });
  await api.deleteBrokerAccount(accountId, { confirmDisplayName: "Paper", confirmMode: "BROKER_PAPER" });

  assert.equal(calls[0][0], `/api/v1/broker-accounts/${accountId}/alpaca-paper/credentials`);
  assert.equal(calls[0][1], "PUT");
  assert.deepEqual(calls[0][2], { api_key: "new-key", api_secret: "new-secret" });
  assert.doesNotMatch(JSON.stringify(replace), /new-secret/);
  assert.equal(calls[1][0], `/api/v1/broker-accounts/${accountId}/delete`);
  assert.deepEqual(calls[1][2], { confirm_display_name: "Paper", confirm_mode: "BROKER_PAPER" });
});

test("duplicate account setup message renders while existing account is selected", () => {
  const html = renderOperationsCenterOverview(overview(), {
    accountSetup: "duplicate",
    status: "loaded",
    selection: { type: "account", id: accountId },
    data: {
      account_id: accountId,
      is_paused: false,
      is_killed: false,
      broker_account_snapshot: null,
      broker_sync_freshness: null,
      open_broker_orders: [],
      positions: [],
      internal_order_ledger_summary: { open_count: 0 }
    }
  });

  assert.match(html, /This Alpaca paper account is already registered\./);
  assert.match(html, /selected-card/);
  assert.equal((html.match(/data-select-type="account"/g) || []).length, 1);
});

test("overview cards are clickable and selected account is highlighted", () => {
  const html = renderOperationsCenterOverview(overview(), {
    status: "loaded",
    selection: { type: "account", id: accountId },
    data: {
      account_id: accountId,
      is_paused: false,
      is_killed: false,
      broker_account_snapshot: null,
      broker_sync_freshness: null,
      open_broker_orders: [],
      positions: [],
      internal_order_ledger_summary: { open_count: 0 }
    }
  });

  assert.match(html, new RegExp(`data-select-type="account" data-id="${accountId}"`));
  assert.match(html, new RegExp(`data-select-type="deployment" data-id="${deploymentId}"`));
  assert.match(html, /selected-card/);
  assert.match(html, /Account Detail/);
});

test("detail panel never shows previous data while loading or erroring", () => {
  const loading = renderDetailPanel({
    status: "loading",
    selection: { type: "deployment", id: deploymentId },
    data: { deployment_id: deploymentId }
  });
  const failed = renderDetailPanel({
    status: "error",
    selection: { type: "account", id: accountId },
    error: new Error("detail failed")
  });

  assert.match(loading, /Loading deployment detail/);
  assert.doesNotMatch(loading, new RegExp(deploymentId));
  assert.match(failed, /Detail unavailable/);
  assert.match(failed, /No previous detail data is shown/);
  assert.doesNotMatch(failed, /Account Detail/);
});

test("pause and resume account call correct API routes", async () => {
  const calls = [];
  const api = createOperationsApi(async (url, options = {}) => {
    calls.push([url, options.method, options.body]);
    return { ok: true, json: async () => ({ accepted: true }) };
  });

  await api.pauseAccount(accountId, "risk");
  await api.resumeAccount(accountId, "clear");

  assert.equal(calls[0][0], `/api/v1/operations/accounts/${accountId}/pause`);
  assert.equal(calls[0][1], "POST");
  assert.equal(calls[1][0], `/api/v1/operations/accounts/${accountId}/resume`);
  assert.equal(calls[1][1], "POST");
});

test("global kill and resume call correct API routes", async () => {
  const calls = [];
  const api = createOperationsApi(async (url, options = {}) => {
    calls.push([url, options.method]);
    return { ok: true, json: async () => ({ accepted: true }) };
  });

  await api.globalKill("operator");
  await api.globalResume("operator");

  assert.deepEqual(calls, [
    ["/api/v1/operations/global/kill", "POST"],
    ["/api/v1/operations/global/resume", "POST"]
  ]);
});

test("destructive controls require confirmation", async () => {
  const client = {
    globalKill: async () => {
      throw new Error("should not call without confirmation");
    }
  };

  const result = await executeOperationAction("global-kill", null, client, () => false);

  assert.deepEqual(result, { skipped: true });
});

test("flatten unsupported/not_ready is displayed safely", () => {
  const html = renderAccountDetail(
    {
      account_id: accountId,
      is_paused: false,
      is_killed: false,
      open_broker_orders: [],
      positions: [],
      internal_order_ledger_summary: { open_count: 0 },
      broker_sync_freshness: null
    },
    {
      accepted: false,
      status: "unsupported_not_ready",
      reason: "flatten_not_implemented_in_control_plane",
      scope: "account",
      target_id: accountId
    }
  );

  assert.match(html, /unsupported_not_ready/);
  assert.match(html, /flatten_not_implemented_in_control_plane/);
  assert.match(html, /warning/);
});

test("account detail renders snapshot, positions, open orders, freshness, and controls", () => {
  const html = renderAccountDetail({
    account_id: accountId,
    is_paused: false,
    is_killed: false,
    broker_account_snapshot: {
      account_id: accountId,
      provider: "fake",
      mode: "broker_paper",
      equity: 100000,
      cash: 40000,
      buying_power: 80000,
      timestamp: "2026-04-24T15:00:00Z"
    },
    broker_sync_freshness: {
      account_id: accountId,
      last_sync_at: "2026-04-24T15:00:00Z",
      last_poll_sync_at: "2026-04-24T15:00:00Z",
      last_successful_sync_at: "2026-04-24T15:00:00Z",
      is_stale: false
    },
    open_broker_orders: [{ symbol: "SPY", side: "buy", qty: 10, status: "accepted" }],
    positions: [{ symbol: "SPY", side: "long", qty: 10, market_value: 4000 }],
    internal_order_ledger_summary: { open_count: 1 }
  });

  assert.match(html, /Provider/);
  assert.match(html, /Positions/);
  assert.match(html, /Open Orders/);
  assert.match(html, /Last successful sync/);
  assert.match(html, /data-action="pause-account"/);
  assert.match(html, /data-action="resume-account"/);
  assert.match(html, /Paper Credential Replacement/);
  assert.match(html, /data-action="delete-account"/);
  assert.doesNotMatch(html, /secret-value/);
});

test("deployment detail renders status, program, governor, orders, trades, fills, timestamps, and controls", () => {
  const html = renderDeploymentDetail({
    deployment_id: deploymentId,
    runtime_status: "running",
    program_id: "program-a",
    program_version: 4,
    broker_account_id: accountId,
    governor_id: "portfolio-governor",
    governor_state: { max_open_positions: 5 },
    last_market_data_timestamp: "2026-04-24T15:00:00Z",
    last_broker_sync_timestamp: "2026-04-24T15:01:00Z",
    last_decision_timestamp: "2026-04-24T15:02:00Z",
    open_orders: [{ symbol: "SPY", side: "long", quantity: 10, status: "accepted" }],
    trades: [{ symbol: "SPY", side: "buy", qty: 1, price: 401 }],
    fills: [{ symbol: "SPY", side: "buy", qty: 1, price: 401, broker_execution_id: "exec-1" }],
    latest_governor_decisions: [{ approved: true, reason: "within limits", symbol: "SPY" }]
  });

  assert.match(html, /Runtime status/);
  assert.match(html, /Program id/);
  assert.match(html, /Governor state/);
  assert.match(html, /Open Orders/);
  assert.match(html, /Trades/);
  assert.match(html, /Fills/);
  assert.match(html, /Last market data/);
  assert.match(html, /data-action="pause-deployment"/);
  assert.match(html, /data-action="resume-deployment"/);
});

test("order detail distinguishes internal broker and fill truth without raw payloads", () => {
  const html = renderOrderDetail({
    internal_order: {
      order_id: "order-1",
      client_order_id: "client-1",
      account_id: accountId,
      deployment_id: deploymentId,
      program_id: "program-a",
      symbol: "SPY",
      side: "long",
      quantity: 10,
      filled_quantity: 1,
      order_type: "market",
      time_in_force: "day",
      intent: "open",
      status: "accepted",
      created_at: "2026-04-24T15:00:00Z",
      updated_at: "2026-04-24T15:01:00Z"
    },
    broker_mapping: {
      broker_order_id: "broker-1",
      provider: "alpaca",
      last_synced_at: "2026-04-24T15:01:00Z"
    },
    broker_account_id: accountId,
    deployment_id: deploymentId,
    program_id: "program-a",
    broker_order_id: "broker-1",
    broker_status: "accepted",
    broker_sync_timestamp: "2026-04-24T15:02:00Z",
    trade_summary: { fill_count: 1, filled_quantity: 1 },
    fills: [{ symbol: "SPY", qty: 1, price: 401, event_at: "2026-04-24T15:02:00Z" }]
  });

  assert.match(html, /Internal Order Truth/);
  assert.match(html, /Broker Mapped Truth/);
  assert.match(html, /Trade\/Fill Truth/);
  assert.match(html, /broker-1/);
  assert.doesNotMatch(html, /raw_alpaca|credentials|api_secret/i);
});

test("unknown broker state renders as unknown stale", () => {
  const html = renderOrderDetail({
    internal_order: { order_id: "order-1", client_order_id: "client-1" },
    broker_account_id: accountId,
    deployment_id: deploymentId,
    program_id: "program-a",
    broker_status: "unknown_stale",
    trade_summary: {}
  });

  assert.match(html, /unknown_stale/);
  assert.match(html, /unknown\/stale/);
});

test("UI does not import broker, engine, or order internals", async () => {
  const root = fileURLToPath(new URL("../src", import.meta.url));
  const files = await collectSourceFiles(root);
  const forbiddenImportPattern = /from\s+["'][^"']*(backend|brokers?|alpaca|OrderManager|BrokerSync|FeatureEngine|SignalEngine)[^"']*["']/;

  for (const file of files) {
    const source = await readFile(file, "utf8");
    assert.doesNotMatch(source, forbiddenImportPattern, file);
  }
});

async function collectSourceFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...await collectSourceFiles(path));
    } else if (entry.name.endsWith(".js")) {
      files.push(path);
    }
  }
  return files;
}
