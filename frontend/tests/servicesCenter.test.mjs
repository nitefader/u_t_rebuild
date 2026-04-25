import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import { createServicesApi } from "../src/api/services.js";
import { renderServicesCenter } from "../src/servicesCenter.js";

const marketId = "11111111-2222-3333-4444-555555555555";
const aiId = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";

function state(overrides = {}) {
  return {
    marketData: {
      services: [
        {
          id: marketId,
          name: "Alpaca Main",
          provider: "alpaca",
          status: "valid",
          is_default: true,
          has_api_key: true,
          has_api_secret: true,
          capabilities: { supports_streaming: true, supports_realtime: true, supports_intraday: true },
          capability_source: "validation:fixture",
          capability_notes: ["Fixture reports streaming and intraday support."],
          capability_updated_at: "2026-04-24T20:00:00Z",
          validation_status: "valid",
          validation_message: "ok"
        },
        {
          id: "22222222-2222-3333-4444-555555555555",
          name: "Yahoo Historical",
          provider: "yahoo",
          status: "valid",
          is_default: false,
          has_api_key: false,
          has_api_secret: false,
          capabilities: { supports_historical: true, supports_daily: true, supports_streaming: false },
          capability_source: "validation:fixture",
          capability_notes: ["Fixture reports historical daily support only."],
          capability_updated_at: "2026-04-24T20:00:00Z",
          validation_status: "valid",
          validation_message: "historical only"
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
    ...overrides
  };
}

test("Services Center renders summary cards, market data table, capabilities, and no raw secrets", () => {
  const html = renderServicesCenter(state());

  assert.match(html, /Default Market Data Service/);
  assert.match(html, /Default AI Service/);
  assert.match(html, /Service Health/);
  assert.match(html, /Market Data Services/);
  assert.match(html, /Alpaca Main/);
  assert.match(html, /Yahoo Historical/);
  assert.match(html, /streaming/);
  assert.match(html, /Provider limitations and notes/);
  assert.match(html, /validation:fixture/);
  assert.match(html, /\*\*\*\*\*\*\*\*/);
  assert.match(html, /\+ Add Market Data Service/);
  assert.doesNotMatch(html, /Create Market Data Service/);
  assert.doesNotMatch(html, /gsk_|new-secret|api-secret-value/);
});

test("Market data card no longer renders a Mode field — mode lives on Broker Account only", () => {
  const html = renderServicesCenter(state());

  assert.doesNotMatch(html, /<dt>Mode<\/dt>/);
});

test("Add Market Data Service panel is collapsed by default and expands without a Mode picker", () => {
  const collapsed = renderServicesCenter(state());
  const expanded = renderServicesCenter(state({ marketDataFormState: { visible: true, provider: "alpaca" } }));

  assert.doesNotMatch(collapsed, /Create Market Data Service/);
  assert.match(expanded, /Create Market Data Service/);
  assert.match(expanded, /API Key/);
  assert.match(expanded, /API Secret/);
  const formStart = expanded.indexOf('data-form="market-data"');
  const formEnd = expanded.indexOf("</form>", formStart);
  const formHtml = expanded.slice(formStart, formEnd);
  assert.doesNotMatch(formHtml, /<select name="mode">/);
  assert.doesNotMatch(formHtml, /option value="paper"/);
  assert.doesNotMatch(formHtml, /option value="live"/);
});

test("Yahoo provider hides credential fields in the expanded market form", () => {
  const html = renderServicesCenter(state({ marketDataFormState: { visible: true, provider: "yahoo", name: "" } }));
  const formStart = html.indexOf('data-form="market-data"');
  const formEnd = html.indexOf("</form>", formStart);
  const formHtml = html.slice(formStart, formEnd);

  assert.match(formHtml, /historical data only/i);
  assert.doesNotMatch(formHtml, /API Key/);
  assert.doesNotMatch(formHtml, /API Secret/);
});

test("Resolver panel renders per-symbol table and reads only from per_symbol_rows", () => {
  const html = renderServicesCenter(
    state({
      activeResolverStrategy: "auto",
      resolution: {
        selection_strategy: "auto",
        decision: "selected",
        intent: {
          consumer: "backtest",
          timeframe: "1d",
          start_at: "2024-01-01T00:00:00Z",
          end_at: "2025-01-01T00:00:00Z",
          requires_streaming: false,
          requires_intraday: false
        },
        per_symbol_rows: [
          {
            symbol: "SPY",
            decision: "selected",
            selected_service_id: "yahoo-historical",
            selected_service_name: "Yahoo Historical",
            selected_provider: "yahoo",
            pipeline_id: null,
            reason: "SELECTED_AUTO_BEST_FIT",
            explanation: "Selected because long-range historical data does not require streaming.",
            rejected_providers: [
              { service_id: "alpaca-main", reason_code: "STREAM_NOT_AVAILABLE", explanation: "compatible but not cheapest" }
            ]
          }
        ],
        resolver_version: "0.10.1",
        resolver_input_hash: "sha256:deadbeef",
        invocation_context: "operations_preview",
        decided_at: "2026-04-25T02:30:00Z"
      }
    })
  );

  assert.match(html, /Auto \(Recommended\)/);
  assert.match(html, />Default</);
  assert.match(html, /Manual Selection/);
  assert.match(html, /Detected Intent/);
  assert.match(html, /consumer/i);
  assert.match(html, /timeframe/i);
  assert.match(html, /streaming required/i);
  assert.match(html, /Per-Symbol Resolution/);
  assert.match(html, /per-symbol-table/);
  assert.match(html, /Yahoo Historical/);
  assert.match(html, /SELECTED_AUTO_BEST_FIT/);
  assert.match(html, /1 rejected/);
  assert.match(html, /STREAM_NOT_AVAILABLE/);
  assert.match(html, /Resolver determinism/);
  assert.match(html, /sha256:deadbeef/);
  assert.match(html, /operations_preview/);
  assert.match(html, /decided_at/);
});

test("Resolver panel renders PARTIAL banner when some symbols resolve and others reject", () => {
  const html = renderServicesCenter(
    state({
      resolution: {
        selection_strategy: "auto",
        decision: "partial",
        per_symbol_rows: [
          {
            symbol: "SPY",
            decision: "selected",
            selected_service_id: "yahoo-historical",
            selected_service_name: "Yahoo Historical",
            selected_provider: "yahoo",
            pipeline_id: null,
            reason: "SELECTED_AUTO_BEST_FIT",
            explanation: "ok",
            rejected_providers: []
          },
          {
            symbol: "AAPL",
            decision: "rejected",
            reason: "STREAM_NOT_AVAILABLE",
            explanation: "no stream",
            rejected_providers: [
              { service_id: "yahoo-historical", reason_code: "STREAM_NOT_AVAILABLE", explanation: "no stream" }
            ]
          }
        ],
        resolver_version: "0.10.1",
        resolver_input_hash: "sha256:abc",
        invocation_context: "operations_preview",
        decided_at: "2026-04-25T02:30:00Z"
      }
    })
  );

  assert.match(html, /resolver-banner-partial/);
  assert.match(html, /Mixed outcome/);
  assert.match(html, /1 of 2 symbols resolved/);
  assert.match(html, /SPY/);
  assert.match(html, /AAPL/);
});

test("Services Center renders AI table and provider-aware fields", () => {
  const html = renderServicesCenter(state({ activeTab: "ai", aiFormState: { visible: true, provider: "groq", capability_label: "fast" } }));

  assert.match(html, /AI Services/);
  assert.match(html, /Groq Fast/);
  assert.match(html, /Capability Label/);
  assert.match(html, /option value="groq"/);
  assert.match(html, /Set Default/);
});

test("provider dropdown supports context-aware market fields", () => {
  const html = renderServicesCenter(state({ marketDataFormState: { visible: true, provider: "yahoo", name: "", id: null } }));

  assert.match(html, /data-provider-select="market-data"/);
  assert.match(html, /option value="alpaca"/);
  assert.match(html, /option value="yahoo"/);
  assert.match(html, /historical data only \(no streaming\)/i);
  assert.match(html, /option value="future"/);
});

test("Data Source Resolver panel renders selected per-symbol row inside the table", () => {
  const html = renderServicesCenter(state({
    resolution: {
      selection_strategy: "auto",
      decision: "selected",
      intent: { consumer: "backtest", timeframe: "1d", requires_streaming: false, requires_intraday: false },
      per_symbol_rows: [
        {
          symbol: "SPY",
          decision: "selected",
          selected_service_id: "yahoo-historical",
          selected_service_name: "Yahoo Historical",
          selected_provider: "yahoo",
          pipeline_id: null,
          reason: "SELECTED_AUTO_BEST_FIT",
          explanation: "ok",
          rejected_providers: [
            { service_id: "alpaca-main", reason_code: "STREAM_NOT_AVAILABLE", explanation: "compatible but not cheapest" }
          ]
        }
      ]
    }
  }));

  assert.match(html, /Per-Symbol Resolution/);
  assert.match(html, /Yahoo Historical/);
  assert.match(html, /1 rejected/);
});

test("Resolver panel shows rejected aggregate decision when every row failed", () => {
  const html = renderServicesCenter(state({
    resolution: {
      selection_strategy: "auto",
      decision: "rejected",
      intent: { consumer: "broker_runtime", timeframe: "5m", requires_streaming: true, requires_intraday: true, purpose: "runtime_trading" },
      per_symbol_rows: [
        {
          symbol: "SPY",
          decision: "rejected",
          reason: "NO_COMPATIBLE_PROVIDER",
          explanation: "No enabled service supports the requested realtime streaming intent.",
          rejected_providers: [{ service_id: marketId, reason_code: "STREAM_NOT_AVAILABLE", explanation: "Streaming is required." }]
        }
      ]
    }
  }));

  assert.match(html, /Per-Symbol Resolution \(rejected\)/);
  assert.match(html, /No enabled service supports the requested realtime streaming intent/);
  assert.match(html, /NO_COMPATIBLE_PROVIDER/);
  assert.match(html, /1 rejected/);
});

test("Disabled services are marked as disabled", () => {
  const html = renderServicesCenter(
    state({
      marketData: {
        services: [
          {
            id: marketId,
            name: "Disabled Service",
            provider: "alpaca",
            status: "disabled",
            is_default: false,
            has_api_key: true,
            has_api_secret: true,
            capabilities: {},
            validation_status: "disabled",
            validation_message: "disabled by operator"
          }
        ]
      }
    })
  );

  assert.match(html, /service-disabled/);
  assert.match(html, /disabled/);
});

test("Services API calls canonical market-data and ai/providers backend routes", async () => {
  const calls = [];
  const api = createServicesApi(async (url, options = {}) => {
    calls.push([url, options.method || "GET", options.body ? JSON.parse(options.body) : null]);
    return { ok: true, json: async () => ({ services: [] }) };
  });

  await api.listMarketData();
  await api.createMarketData({ name: "Yahoo", provider: "yahoo" });
  await api.validateMarketData(marketId);
  await api.setDefaultMarketData(marketId);
  await api.disableMarketData(marketId);
  await api.listAi();
  await api.createAi({ name: "Groq", provider: "groq", api_key: "gsk_test", capability_label: "fast" });
  await api.validateAi(aiId);
  await api.setDefaultAi(aiId);
  await api.disableAi(aiId);
  await api.resolveMarketData({
    selection_strategy: "auto",
    invocation_context: "operations_preview",
    intent: { consumer: "backtest", mode: "replay", symbols: ["SPY"], timeframe: "1d", purpose: "backtest" }
  });

  assert.deepEqual(calls.map((call) => [call[0], call[1]]), [
    ["/api/v1/market-data/services", "GET"],
    ["/api/v1/market-data/services", "POST"],
    [`/api/v1/market-data/services/${marketId}/validate`, "POST"],
    [`/api/v1/market-data/services/${marketId}/set-default`, "POST"],
    [`/api/v1/market-data/services/${marketId}/disable`, "POST"],
    ["/api/v1/ai/providers", "GET"],
    ["/api/v1/ai/providers", "POST"],
    [`/api/v1/ai/providers/${aiId}/validate`, "POST"],
    [`/api/v1/ai/providers/${aiId}/set-default`, "POST"],
    [`/api/v1/ai/providers/${aiId}/disable`, "POST"],
    ["/api/v1/market-data/services/resolve", "POST"]
  ]);
});

test("Market data create payload no longer carries a banned mode field", async () => {
  const calls = [];
  const api = createServicesApi(async (url, options = {}) => {
    calls.push([url, options.method || "GET", options.body ? JSON.parse(options.body) : null]);
    return { ok: true, json: async () => ({ services: [] }) };
  });

  await api.createMarketData({ name: "Alpaca Main", provider: "alpaca", api_key: "abcdef", api_secret: "abcdefgh" });

  assert.equal(calls[0][0], "/api/v1/market-data/services");
  assert.equal(calls[0][1], "POST");
  assert.deepEqual(Object.keys(calls[0][2]).sort(), ["api_key", "api_secret", "name", "provider"]);
});

test("Resolver source uses selection_strategy contract — selection_mode is banned wording", () => {
  const source = readFileSync(new URL("../src/servicesCenter.js", import.meta.url), "utf8");

  assert.doesNotMatch(source, /\bselection_mode\b/);
  assert.doesNotMatch(source, /\bRESOLVER_MODES\b/);
  assert.doesNotMatch(source, /set-resolver-mode/);
  assert.match(source, /selection_strategy/);
  assert.match(source, /default_preferred/);
  assert.match(source, /manual_override/);
});

test("Resolver source reads only from per_symbol_rows — no top-level mirror reads", () => {
  const source = readFileSync(new URL("../src/servicesCenter.js", import.meta.url), "utf8");

  // Top-level mirror foot-guns: backend dropped these fields; frontend must not read them.
  assert.doesNotMatch(source, /resolution\.selected_service_name/);
  assert.doesNotMatch(source, /resolution\.selected_provider/);
  assert.doesNotMatch(source, /resolution\.selected_service_id/);
  assert.doesNotMatch(source, /resolution\.pipeline_id/);
  assert.doesNotMatch(source, /resolution\.rejected_providers/);
  assert.doesNotMatch(source, /resolution\.reason\b/);
  assert.doesNotMatch(source, /resolution\.explanation/);
  // Per-symbol contract is the only resolution shape the UI reads.
  assert.match(source, /resolution\.per_symbol_rows/);
});

test("Services UI source does not hardcode selected provider recommendations", () => {
  const source = readFileSync(new URL("../src/servicesCenter.js", import.meta.url), "utf8");

  assert.doesNotMatch(source, /Yahoo selected/i);
  assert.doesNotMatch(source, /Alpaca selected/i);
  assert.doesNotMatch(source, /selected_service_name:\s*["']Yahoo/i);
  assert.doesNotMatch(source, /selected_service_name:\s*["']Alpaca/i);
});
