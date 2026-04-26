import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { createOperationsApi } from "../src/api/operations.js";
import {
  executeOperationAction,
  renderDataSourceResolverPanel,
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

test("overview renders system runtime telemetry without broker account presence", () => {
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
  assert.doesNotMatch(html, /<h2>Broker Accounts<\/h2>/);
  assert.doesNotMatch(html, /data-action="account-detail"/);
  assert.doesNotMatch(html, /data-action="pause-account"/);
});

test("overview links operators to the Brokers page for account state", () => {
  const html = renderOperationsCenterOverview(overview());
  assert.match(html, /href="\.\/brokers\.html"/);
});

test("data source resolver panel displays detected intent, selection mode, selected service, and rejected services", () => {
  const html = renderDataSourceResolverPanel({
    selection_mode: "auto",
    intent: {
      consumer: "backtest",
      timeframe: "1d",
      start_at: "2023-01-01T00:00:00Z",
      end_at: "2026-01-01T00:00:00Z",
      requires_streaming: false,
      requires_intraday: false
    },
    selected_service: {
      service_name: "Yahoo Historical",
      provider: "yahoo",
      explanation: "Selected because request uses daily long-range historical data and does not require streaming."
    },
    rejected_candidates: [
      {
        service_id: "alpaca-main-data",
        reason_code: "selected_auto_best_fit",
        explanation: "Alpaca Main Data is compatible, but Yahoo Historical is a better fit for this intent."
      }
    ]
  });

  assert.match(html, /Data Source/);
  assert.match(html, /Auto Recommended/);
  assert.match(html, /Detected Intent/);
  assert.match(html, /backtest/);
  assert.match(html, /Streaming required/);
  assert.match(html, /Yahoo Historical/);
  assert.match(html, /Selected because request uses daily long-range historical data/);
  assert.match(html, /Rejected services \(1\)/);
  assert.match(html, /Alpaca Main Data is compatible/);
});

test("stale broker sync warning still surfaces as a runtime alert and links to Brokers", () => {
  const html = renderOperationsCenterOverview(overview({
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
  assert.match(html, /no sync for 10 minutes/);
  assert.match(html, /href="\.\/brokers\.html"/);
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

test("deployment and order detail calls use Operations API routes", async () => {
  const calls = [];
  const api = createOperationsApi(async (url, options = {}) => {
    calls.push([url, options.method || "GET"]);
    return { ok: true, json: async () => ({}) };
  });

  await api.getDeployment(deploymentId);
  await api.getOrder("order-1");

  assert.deepEqual(calls, [
    [`/api/v1/operations/deployments/${deploymentId}`, "GET"],
    ["/api/v1/operations/orders/order-1", "GET"]
  ]);
});

test("Operations Center exposes only deployment selection, not account selection", () => {
  const html = renderOperationsCenterOverview(overview(), {
    status: "loaded",
    selection: { type: "deployment", id: deploymentId },
    data: {
      deployment_id: deploymentId,
      runtime_status: "running",
      open_orders: [],
      trades: [],
      fills: [],
      latest_governor_decisions: []
    }
  });

  assert.match(html, new RegExp(`data-select-type="deployment" data-id="${deploymentId}"`));
  assert.doesNotMatch(html, /data-select-type="account"/);
  assert.match(html, /selected-card/);
  assert.match(html, /Deployment Detail/);
});

test("detail panel never shows previous data while loading or erroring", () => {
  const loading = renderDetailPanel({
    status: "loading",
    selection: { type: "deployment", id: deploymentId },
    data: { deployment_id: deploymentId }
  });
  const failed = renderDetailPanel({
    status: "error",
    selection: { type: "deployment", id: deploymentId },
    error: new Error("detail failed")
  });

  assert.match(loading, /Loading deployment detail/);
  assert.doesNotMatch(loading, new RegExp(deploymentId));
  assert.match(failed, /Detail unavailable/);
  assert.match(failed, /No previous detail data is shown/);
  assert.doesNotMatch(failed, /Deployment Detail/);
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

test("account-targeted actions are no longer dispatched from Operations Center", async () => {
  await assert.rejects(
    () => executeOperationAction("pause-account", accountId, {}),
    /Unknown operations action: pause-account/
  );
  await assert.rejects(
    () => executeOperationAction("flatten-account", accountId, {}),
    /Unknown operations action: flatten-account/
  );
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
  // Pattern aligns with scripts/check-frontend.mjs — requires a path
  // separator before the forbidden token so local UI modules like
  // ./brokers.js (frontend) don't false-positive.
  const forbiddenImportPattern = /from\s+["'][^"']*\/(backend|brokers?|alpaca|OrderManager|BrokerSync|FeatureEngine|SignalEngine)[\/'"]/;

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
