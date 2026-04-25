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
          mode: "paper",
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
          mode: "none",
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

test("Add Market Data Service panel is collapsed by default and expands with provider-aware form", () => {
  const collapsed = renderServicesCenter(state());
  const expanded = renderServicesCenter(state({ marketDataFormState: { visible: true, provider: "alpaca", mode: "paper" } }));

  assert.doesNotMatch(collapsed, /Create Market Data Service/);
  assert.match(expanded, /Create Market Data Service/);
  assert.match(expanded, /API Key/);
  assert.match(expanded, /API Secret/);
  assert.match(expanded, /<span>Mode<\/span>/);
});

test("Yahoo provider hides credential fields in the expanded market form", () => {
  const html = renderServicesCenter(state({ marketDataFormState: { visible: true, provider: "yahoo", mode: "none", name: "" } }));
  const formStart = html.indexOf('data-form="market-data"');
  const formEnd = html.indexOf("</form>", formStart);
  const formHtml = html.slice(formStart, formEnd);

  assert.match(formHtml, /No credentials required/);
  assert.doesNotMatch(formHtml, /API Key/);
  assert.doesNotMatch(formHtml, /API Secret/);
});

test("Resolver panel shows decision modes and detected intent", () => {
  const html = renderServicesCenter(
    state({
      activeResolverMode: "auto",
      resolution: {
        selection_mode: "auto",
        decision: "selected",
        intent: {
          consumer: "backtest",
          timeframe: "1d",
          start_at: "2024-01-01T00:00:00Z",
          end_at: "2025-01-01T00:00:00Z",
          requires_streaming: false,
          requires_intraday: false
        },
        selected_service_name: "Yahoo Historical",
        provider: "yahoo",
        reason_code: "selected_auto_best_fit",
        explanation: "Selected because long-range historical data does not require streaming.",
        rejected_candidates: [{ service_id: "alpaca-main", explanation: "compatible but not cheapest" }]
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
  assert.match(html, /Selected Service/);
  assert.match(html, /Yahoo Historical/);
  assert.match(html, /selected_auto_best_fit/);
  assert.match(html, /Rejected Services \(1\)/);
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
  const html = renderServicesCenter(state({ marketDataFormState: { visible: true, provider: "yahoo", mode: "none", name: "", id: null } }));

  assert.match(html, /data-provider-select="market-data"/);
  assert.match(html, /option value="alpaca"/);
  assert.match(html, /option value="yahoo"/);
  assert.match(html, /historical data only \(no streaming\)/i);
  assert.match(html, /option value="future"/);
});

test("Data Source Resolver panel displays selected service and rejected candidates", () => {
  const html = renderServicesCenter(state({
    resolution: {
      selection_mode: "auto",
      decision: "selected",
      intent: { consumer: "backtest", timeframe: "1d", requires_streaming: false, requires_intraday: false },
      selected_service_name: "Yahoo Historical",
      provider: "yahoo",
      explanation: "Selected because long-range historical data does not require streaming.",
      rejected_candidates: [{ service_id: "alpaca-main", explanation: "compatible but not cheapest" }]
    }
  }));

  assert.match(html, /Selected Service/);
  assert.match(html, /Yahoo Historical/);
  assert.match(html, /Rejected Services \(1\)/);
});

test("Resolver panel displays no-compatible-service state cleanly", () => {
  const html = renderServicesCenter(state({
    resolution: {
      selection_mode: "auto",
      decision: "rejected",
      reason_code: "rejected_no_compatible_service",
      explanation: "No enabled service supports the requested realtime streaming intent.",
      intent: { consumer: "broker_runtime", timeframe: "5m", requires_streaming: true, requires_intraday: true, purpose: "runtime_trading" },
      rejected_candidates: [{ service_id: marketId, reason_code: "rejected_no_streaming", explanation: "Streaming is required." }]
    }
  }));

  assert.match(html, /No Compatible Service Found/);
  assert.match(html, /No enabled service supports the requested realtime streaming intent/);
  assert.match(html, /rejected_no_compatible_service/);
  assert.match(html, /Rejected Services \(1\)/);
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
            mode: "paper",
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

test("Services API calls backend routes for validate, default, disable, and resolve", async () => {
  const calls = [];
  const api = createServicesApi(async (url, options = {}) => {
    calls.push([url, options.method || "GET", options.body ? JSON.parse(options.body) : null]);
    return { ok: true, json: async () => ({ services: [] }) };
  });

  await api.listMarketData();
  await api.createMarketData({ name: "Yahoo", provider: "yahoo", mode: "none" });
  await api.validateMarketData(marketId);
  await api.setDefaultMarketData(marketId);
  await api.disableMarketData(marketId);
  await api.listAi();
  await api.createAi({ name: "Groq", provider: "groq", api_key: "gsk_test", capability_label: "fast" });
  await api.validateAi(aiId);
  await api.setDefaultAi(aiId);
  await api.disableAi(aiId);
  await api.resolveMarketData({ selection_mode: "auto", intent: { consumer: "backtest", mode: "replay", symbols: ["SPY"], timeframe: "1d", purpose: "backtest" } });

  assert.deepEqual(calls.map((call) => [call[0], call[1]]), [
    ["/api/v1/services/market-data", "GET"],
    ["/api/v1/services/market-data", "POST"],
    [`/api/v1/services/market-data/${marketId}/validate`, "POST"],
    [`/api/v1/services/market-data/${marketId}/set-default`, "POST"],
    [`/api/v1/services/market-data/${marketId}/disable`, "POST"],
    ["/api/v1/services/ai", "GET"],
    ["/api/v1/services/ai", "POST"],
    [`/api/v1/services/ai/${aiId}/validate`, "POST"],
    [`/api/v1/services/ai/${aiId}/set-default`, "POST"],
    [`/api/v1/services/ai/${aiId}/disable`, "POST"],
    ["/api/v1/services/market-data/resolve", "POST"]
  ]);
});

test("Services UI source does not hardcode selected provider recommendations", () => {
  const source = readFileSync(new URL("../src/servicesCenter.js", import.meta.url), "utf8");

  assert.doesNotMatch(source, /Yahoo selected/i);
  assert.doesNotMatch(source, /Alpaca selected/i);
  assert.doesNotMatch(source, /selected_service_name:\s*["']Yahoo/i);
  assert.doesNotMatch(source, /selected_service_name:\s*["']Alpaca/i);
});
