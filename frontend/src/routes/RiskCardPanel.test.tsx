import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { RiskCardPanel } from "./RiskCardPanel";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

describe("<RiskCardPanel />", () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders account risk config and restrictions from live routes", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/broker-accounts/11111111-1111-1111-1111-111111111111/risk-config",
        body: {
          account_id: "11111111-1111-1111-1111-111111111111",
          version: 1,
          sizing_method: "fixed_shares",
          fixed_shares: 5,
          fixed_notional: null,
          risk_per_trade_pct: null,
          max_position_notional: 10000,
          max_open_positions: 4,
          max_symbol_concentration_pct: 20,
          max_gross_exposure_pct: 100,
          max_net_exposure_pct: 80,
          max_daily_loss_pct: 3,
          max_drawdown_pct: 10,
          fractional_quantity_allowed: false,
          whole_share_rounding: "floor",
          updated_at: "2026-04-29T12:00:00-04:00",
        },
      },
      {
        url: "/api/v1/broker-accounts/11111111-1111-1111-1111-111111111111/restrictions",
        body: {
          account_id: "11111111-1111-1111-1111-111111111111",
          version: 1,
          symbol_blocklist: ["TSLA", "GME"],
          asset_class_blocklist: [],
          long_only: true,
          short_only: false,
          extended_hours_allowed: false,
          time_of_day_windows: [],
          notes: "Operator blocklist",
          updated_at: "2026-04-29T12:00:00-04:00",
        },
      },
    ]);

    renderRoute(<RiskCardPanel accountId="11111111-1111-1111-1111-111111111111" />);

    await waitFor(() => expect(screen.getByText(/Sizing & exposure/i)).toBeInTheDocument());
    expect(screen.getByText("fixed_shares")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText(/Long only/i)).toBeInTheDocument();
    expect(screen.getByText("TSLA")).toBeInTheDocument();
    expect(screen.queryByText(/Operation Turtle Shell's queue/i)).not.toBeInTheDocument();
  });
});
