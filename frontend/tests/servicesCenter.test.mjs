import assert from "node:assert/strict";
import test from "node:test";

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
  assert.match(html, /\*\*\*\*\*\*\*\*/);
  assert.doesNotMatch(html, /gsk_|new-secret|api-secret-value/);
});

test("Resolver panel shows decision modes and detected intent", () => {
  const html = renderServicesCenter(
    state({
      activeResolverMode: "auto",
      resolution: {
        selection_mode: "auto",
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
  assert.match(html, /Default \(system default\)/);
  assert.match(html, /Manual \(explicit selection\)/);
  assert.match(html, /Detected Intent/);
  assert.match(html, /consumer/i);
  assert.match(html, /timeframe/i);
  assert.match(html, /streaming required/i);
  assert.match(html, /Selected Service/);
  assert.match(html, /Yahoo Historical/);
  assert.match(html, /selected_auto_best_fit/);
  assert.match(html, /Rejected candidates \(1\)/);
});

test("Services Center renders AI table and provider-aware fields", () => {
  const html = renderServicesCenter(state({ activeTab: "ai" }));

  assert.match(html, /AI Services/);
  assert.match(html, /Groq Fast/);
  assert.match(html, /capability_label/);
  assert.match(html, /option value="groq"/);
  assert.match(html, /Set default/);
});

test("provider dropdown supports context-aware market fields", () => {
  const html = renderServicesCenter(state({ marketDataFormState: { provider: "yahoo", mode: "none", name: "", id: null } }));

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
      intent: { consumer: "backtest", timeframe: "1d", requires_streaming: false, requires_intraday: false },
      selected_service_name: "Yahoo Historical",
      provider: "yahoo",
      explanation: "Selected because long-range historical data does not require streaming.",
      rejected_candidates: [{ service_id: "alpaca-main", explanation: "compatible but not cheapest" }]
    }
  }));

  assert.match(html, /Selected Service/);
  assert.match(html, /Yahoo Historical/);
  assert.match(html, /Rejected candidates \(1\)/);
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
