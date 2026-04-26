import assert from "node:assert/strict";
import test from "node:test";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { createPipelinesApi } from "../src/api/pipelines.js";
import { createServicesApi } from "../src/api/services.js";
import { renderProviders, ResolverResultPanel } from "../src/providers.js";

const FRONTEND_ROOT = fileURLToPath(new URL("../", import.meta.url));

const pipelineId = "11111111-2222-3333-4444-555555555555";
const marketServiceId = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const aiId = "cccccccc-cccc-cccc-cccc-cccccccccccc";

function state(overrides = {}) {
  return {
    activeTab: "market-data",
    pipelines: {
      pipelines: [
        {
          id: pipelineId,
          display_name: "Alpaca Premium",
          provider: "alpaca",
          service_id: marketServiceId,
          data_feed: "iex",
          trading_mode: "BROKER_PAPER",
          status: "active",
          is_default_for_provider: true,
          capabilities: { supports_streaming: true, supports_intraday: true },
          created_at: "2026-04-25T01:00:00Z",
          updated_at: "2026-04-25T01:00:00Z"
        }
      ]
    },
    marketData: {
      services: [
        {
          id: marketServiceId,
          name: "Alpaca Main",
          provider: "alpaca",
          status: "valid",
          is_default: true,
          has_api_key: true,
          has_api_secret: true,
          capabilities: { supports_streaming: true },
          validation_status: "valid",
          validation_message: "ok"
        }
      ]
    },
    ai: {
      services: [
        {
          id: aiId,
          name: "Groq Fast",
          provider: "groq",
          status: "valid",
          is_default: true,
          has_api_key: true,
          capability_label: "fast",
          validation_status: "valid",
          validation_message: "ok"
        }
      ]
    },
    activeResolverStrategy: "auto",
    resolutionPayload: { intent: { consumer: "backtest", timeframe: "1d" } },
    resolution: null,
    ...overrides
  };
}

// ---------------------------------------------------------------------------
// IA flip enforcement
// ---------------------------------------------------------------------------

test("Legacy Services Center surface is gone (services.html, servicesCenter.js, servicesCenter.test.mjs deleted)", () => {
  assert.equal(existsSync(join(FRONTEND_ROOT, "services.html")), false, "frontend/services.html must not exist");
  assert.equal(existsSync(join(FRONTEND_ROOT, "src", "servicesCenter.js")), false, "frontend/src/servicesCenter.js must not exist");
  assert.equal(existsSync(join(FRONTEND_ROOT, "tests", "servicesCenter.test.mjs")), false, "frontend/tests/servicesCenter.test.mjs must not exist");
});

test("Providers page surface exists (providers.html, providers.js)", () => {
  assert.equal(existsSync(join(FRONTEND_ROOT, "providers.html")), true);
  assert.equal(existsSync(join(FRONTEND_ROOT, "src", "providers.js")), true);
  assert.equal(existsSync(join(FRONTEND_ROOT, "src", "api", "pipelines.js")), true);
});

test("No frontend source imports the legacy servicesCenter module", () => {
  function walk(dir) {
    const out = [];
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (["dist", "node_modules", "tests"].includes(entry.name)) continue;
        out.push(...walk(join(dir, entry.name)));
      } else if (/\.(js|mjs|html)$/.test(entry.name)) {
        out.push(join(dir, entry.name));
      }
    }
    return out;
  }
  for (const file of walk(FRONTEND_ROOT)) {
    const source = readFileSync(file, "utf8");
    assert.equal(/servicesCenter/.test(source), false, `${file} still references the deleted servicesCenter module`);
  }
});

test("Resolver Result Panel is exported by providers.js, not the deleted servicesCenter.js", () => {
  assert.equal(typeof ResolverResultPanel, "function");
});

// ---------------------------------------------------------------------------
// Providers page rendering
// ---------------------------------------------------------------------------

test("Providers page renders integrated Market Data Providers + AI Providers tabs and stats", () => {
  const html = renderProviders(state());
  assert.match(html, /<h1>Providers<\/h1>/);
  assert.match(html, /Market Data Providers/);
  assert.match(html, /AI Providers/);
  assert.match(html, /market data providers/);
  assert.match(html, /streams/);
});

test("Integrated Market Data catalog shows bound stream and provider row", () => {
  const html = renderProviders(state());
  assert.match(html, /Market Data Providers/);
  assert.match(html, /Alpaca Main/);
  assert.match(html, /BROKER_PAPER/);
  assert.match(html, /iex/);
});

test("Detached pipeline cards still expose pipeline id for unbound streams", () => {
  const fixture = state();
  fixture.pipelines.pipelines[0].service_id = null;
  const html = renderProviders(fixture);
  assert.match(html, /Detached streams/);
  assert.match(html, new RegExp(pipelineId));
});

test("Activate stream form does not let operator pick a banned standalone mode", () => {
  const html = renderProviders(state({ pipelineFormState: { visible: true, provider: "alpaca" } }));
  assert.match(html, /Activate Market Data Stream/);
  assert.match(html, /option value="BROKER_PAPER"/);
  assert.match(html, /option value="BROKER_LIVE"/);
  // Banned standalone "paper" / "live" must never appear as enum values.
  assert.doesNotMatch(html, /option value="paper"/);
  assert.doesNotMatch(html, /option value="live"/);
});

test("Activate stream form lists registered Alpaca services in the Service dropdown", () => {
  const html = renderProviders(state({ pipelineFormState: { visible: true } }));
  // The fixture state() seeds an "Alpaca Main" service.
  assert.match(html, /name="service_id"/);
  assert.match(html, /Alpaca Main/);
});

test("Stream column reflects pipeline data_feed when pipeline binds to service", () => {
  const fixture = state();
  fixture.pipelines.pipelines[0].service_id = marketServiceId;
  fixture.pipelines.pipelines[0].data_feed = "sip";
  const html = renderProviders(fixture);
  assert.match(html, /sip/);
  assert.match(html, /BROKER_PAPER/);
});

test("Market Data surface still renders catalog without a spurious Mode label on service rows", () => {
  const html = renderProviders(state({ activeTab: "market-data" }));
  assert.match(html, /Market Data Providers/);
  assert.match(html, /Alpaca Main/);
  assert.doesNotMatch(html, /<dt>Mode<\/dt>/);
});

test("AI Providers tab renders provider records, advisory badge, and copy", () => {
  const html = renderProviders(state({ activeTab: "ai" }));
  assert.match(html, /AI Providers/);
  assert.match(html, /Groq Fast/);
  assert.match(html, /Advisory only/);
});

// ---------------------------------------------------------------------------
// Resolver Result Panel
// ---------------------------------------------------------------------------

test("Resolver panel renders per-symbol table with pipeline_id from per_symbol_rows", () => {
  const html = renderProviders(state({
    resolution: {
      selection_strategy: "auto",
      decision: "selected",
      per_symbol_rows: [
        {
          symbol: "SPY",
          decision: "selected",
          selected_service_id: "yahoo-historical",
          selected_service_name: "Yahoo Historical",
          selected_provider: "yahoo",
          pipeline_id: "pipe-yahoo-default",
          reason: "SELECTED_AUTO_BEST_FIT",
          explanation: "ok",
          rejected_providers: []
        }
      ],
      resolver_version: "0.11.0",
      resolver_input_hash: "sha256:abc",
      invocation_context: "operations_preview",
      decided_at: "2026-04-25T03:30:00Z"
    }
  }));

  assert.match(html, /Per-Symbol Resolution \(selected\)/);
  assert.match(html, /per-symbol-table/);
  assert.match(html, /pipe-yahoo-default/);
  assert.match(html, /SELECTED_AUTO_BEST_FIT/);
  assert.match(html, /Resolver determinism/);
  assert.match(html, /sha256:abc/);
});

test("Resolver panel surfaces PARTIAL banner when rows mix selected and rejected", () => {
  const html = renderProviders(state({
    resolution: {
      selection_strategy: "auto",
      decision: "partial",
      per_symbol_rows: [
        { symbol: "SPY", decision: "selected", selected_service_name: "X", selected_provider: "yahoo", pipeline_id: "p1", reason: "SELECTED_AUTO_BEST_FIT", explanation: "ok", rejected_providers: [] },
        { symbol: "AAPL", decision: "rejected", reason: "STREAM_NOT_AVAILABLE", explanation: "no stream", rejected_providers: [{ service_id: "s", reason_code: "STREAM_NOT_AVAILABLE", explanation: "no stream" }] }
      ],
      resolver_version: "0.11.0",
      resolver_input_hash: "sha256:partial",
      invocation_context: "operations_preview",
      decided_at: "2026-04-25T03:30:00Z"
    }
  }));

  assert.match(html, /resolver-banner-partial/);
  assert.match(html, /1 of 2 symbols resolved/);
  assert.match(html, /SPY/);
  assert.match(html, /AAPL/);
});

test("Providers source reads only from per_symbol_rows — no top-level resolver mirror reads", () => {
  const source = readFileSync(new URL("../src/providers.js", import.meta.url), "utf8");
  assert.doesNotMatch(source, /resolution\.selected_service_name/);
  assert.doesNotMatch(source, /resolution\.selected_provider/);
  assert.doesNotMatch(source, /resolution\.selected_service_id/);
  assert.doesNotMatch(source, /resolution\.pipeline_id/);
  assert.doesNotMatch(source, /resolution\.rejected_providers/);
  assert.doesNotMatch(source, /resolution\.reason\b/);
  assert.match(source, /resolution\.per_symbol_rows/);
});

test("Providers source uses selection_strategy contract — selection_mode is banned wording", () => {
  const source = readFileSync(new URL("../src/providers.js", import.meta.url), "utf8");
  assert.doesNotMatch(source, /\bselection_mode\b/);
  assert.doesNotMatch(source, /\bRESOLVER_MODES\b/);
  assert.doesNotMatch(source, /set-resolver-mode/);
  assert.match(source, /selection_strategy/);
  assert.match(source, /default_preferred/);
  assert.match(source, /manual_override/);
});

// ---------------------------------------------------------------------------
// Pipelines API client
// ---------------------------------------------------------------------------

test("Pipelines API hits /api/v1/market-data/pipelines endpoints", async () => {
  const calls = [];
  const api = createPipelinesApi(async (url, options = {}) => {
    calls.push([url, options.method || "GET", options.body ? JSON.parse(options.body) : null]);
    return { ok: true, json: async () => ({ pipelines: [] }) };
  });

  await api.listPipelines();
  await api.createPipeline({ display_name: "Alpaca", provider: "alpaca" });
  await api.updatePipeline(pipelineId, { display_name: "Alpaca Edited", provider: "alpaca" });
  await api.setDefaultPipeline(pipelineId);
  await api.disablePipeline(pipelineId);

  assert.deepEqual(calls.map((call) => [call[0], call[1]]), [
    ["/api/v1/market-data/pipelines", "GET"],
    ["/api/v1/market-data/pipelines", "POST"],
    [`/api/v1/market-data/pipelines/${pipelineId}`, "PUT"],
    [`/api/v1/market-data/pipelines/${pipelineId}/set-default`, "POST"],
    [`/api/v1/market-data/pipelines/${pipelineId}/disable`, "POST"]
  ]);
});

test("Services API still hits canonical market-data and ai/providers routes", async () => {
  const calls = [];
  const api = createServicesApi(async (url, options = {}) => {
    calls.push([url, options.method || "GET"]);
    return { ok: true, json: async () => ({ services: [] }) };
  });

  await api.listMarketData();
  await api.listAi();
  await api.resolveMarketData({ selection_strategy: "auto", invocation_context: "operations_preview", intent: { consumer: "backtest", mode: "replay", symbols: ["SPY"], timeframe: "1d", purpose: "backtest" } });

  assert.deepEqual(calls, [
    ["/api/v1/market-data/services", "GET"],
    ["/api/v1/ai/providers", "GET"],
    ["/api/v1/market-data/services/resolve", "POST"]
  ]);
});
