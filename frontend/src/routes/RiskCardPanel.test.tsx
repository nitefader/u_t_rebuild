import { afterEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { RiskCardPanel } from "./RiskCardPanel";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

const ACCOUNT_ID = "11111111-1111-1111-1111-111111111111";

const RISK_CONFIG = {
  account_id: ACCOUNT_ID,
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
};

const RESTRICTIONS = {
  account_id: ACCOUNT_ID,
  version: 1,
  symbol_blocklist: ["TSLA", "GME"],
  asset_class_blocklist: [],
  long_only: true,
  short_only: false,
  extended_hours_allowed: false,
  time_of_day_windows: [],
  notes: "Operator blocklist",
  updated_at: "2026-04-29T12:00:00-04:00",
};

const RISK_PLAN_MAP_EMPTY = {
  account_id: ACCOUNT_ID,
  entries: [],
};

const RISK_PLANS_EMPTY = { risk_plans: [] };

const RISK_PLANS_WITH_DATA = {
  risk_plans: [
    {
      risk_plan_id: "plan-aaa",
      name: "Swing Conservative",
      description: null,
      status: "active",
      risk_score: 2,
      risk_tier: "conservative",
      source: "manual",
      ai_generated: false,
      ai_summary: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      created_by: null,
      active_version_id: "ver-aaa-1",
      active_version: {
        risk_plan_version_id: "ver-aaa-1",
        risk_plan_id: "plan-aaa",
        version: 1,
        status: "active",
        config_fingerprint: "fp1",
        config: { sizing_method: "risk_percent" },
        created_at: "2026-01-01T00:00:00Z",
      },
      linked_account_count: 1,
      last_used_at: null,
    },
  ],
};

const RISK_PLAN_MAP_WITH_SWING = {
  account_id: ACCOUNT_ID,
  entries: [
    {
      account_id: ACCOUNT_ID,
      horizon: "swing",
      risk_plan_version_id: "ver-aaa-1",
      updated_at: "2026-04-29T12:00:00Z",
    },
  ],
};

describe("<RiskCardPanel />", () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders account risk config and restrictions from live routes", async () => {
    restore = installFetchMock([
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/risk-config`,
        body: RISK_CONFIG,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/restrictions`,
        body: RESTRICTIONS,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/risk-plan-map`,
        body: RISK_PLAN_MAP_EMPTY,
      },
      { url: "/api/v1/risk-plans", body: RISK_PLANS_EMPTY },
    ]);

    renderRoute(<RiskCardPanel accountId={ACCOUNT_ID} />);

    await waitFor(() => expect(screen.getByText(/Sizing & exposure/i)).toBeInTheDocument());
    expect(screen.getByText("fixed_shares")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText(/Long only/i)).toBeInTheDocument();
    expect(screen.getByText("TSLA")).toBeInTheDocument();
    expect(screen.queryByText(/Operation Turtle Shell's queue/i)).not.toBeInTheDocument();
  });

  it("renders all 5 horizon dropdowns in the RiskPlan by Horizon section", async () => {
    restore = installFetchMock([
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/risk-config`,
        body: RISK_CONFIG,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/restrictions`,
        body: RESTRICTIONS,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/risk-plan-map`,
        body: RISK_PLAN_MAP_EMPTY,
      },
      { url: "/api/v1/risk-plans", body: RISK_PLANS_WITH_DATA },
    ]);

    renderRoute(<RiskCardPanel accountId={ACCOUNT_ID} />);

    // Wait until the dropdowns themselves render (the section heading
    // appears earlier than the dropdowns because the map + plans queries
    // are still resolving — wait on the dropdowns directly).
    await waitFor(() =>
      expect(screen.getByLabelText(/Scalping risk plan/i)).toBeInTheDocument(),
    );

    // Each of the 5 horizons must have an accessible select.
    expect(screen.getByLabelText(/Scalping risk plan/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Intraday risk plan/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Swing risk plan/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Position risk plan/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Other risk plan/i)).toBeInTheDocument();
  });

  it("pre-fills the swing dropdown when the map has an entry for swing", async () => {
    restore = installFetchMock([
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/risk-config`,
        body: RISK_CONFIG,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/restrictions`,
        body: RESTRICTIONS,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/risk-plan-map`,
        body: RISK_PLAN_MAP_WITH_SWING,
      },
      { url: "/api/v1/risk-plans", body: RISK_PLANS_WITH_DATA },
    ]);

    renderRoute(<RiskCardPanel accountId={ACCOUNT_ID} />);

    await waitFor(() =>
      expect(screen.getByLabelText(/Swing risk plan/i)).toBeInTheDocument(),
    );

    const swingSelect = screen.getByLabelText(/Swing risk plan/i) as HTMLSelectElement;
    expect(swingSelect.value).toBe("ver-aaa-1");

    // The other 4 horizons should be blank (None).
    const scalping = screen.getByLabelText(/Scalping risk plan/i) as HTMLSelectElement;
    expect(scalping.value).toBe("");
  });

  it("calls PUT on change-and-save round-trip", async () => {
    const putResponse = {
      account_id: ACCOUNT_ID,
      entries: [
        {
          account_id: ACCOUNT_ID,
          horizon: "intraday",
          risk_plan_version_id: "ver-aaa-1",
          updated_at: "2026-04-29T13:00:00Z",
        },
      ],
    };

    restore = installFetchMock([
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/risk-config`,
        body: RISK_CONFIG,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/restrictions`,
        body: RESTRICTIONS,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/risk-plan-map`,
        method: "GET",
        body: RISK_PLAN_MAP_EMPTY,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/risk-plan-map`,
        method: "PUT",
        body: putResponse,
      },
      { url: "/api/v1/risk-plans", body: RISK_PLANS_WITH_DATA },
    ]);

    renderRoute(<RiskCardPanel accountId={ACCOUNT_ID} />);

    await waitFor(() =>
      expect(screen.getByLabelText(/Intraday risk plan/i)).toBeInTheDocument(),
    );

    const intradaySelect = screen.getByLabelText(/Intraday risk plan/i);
    fireEvent.change(intradaySelect, { target: { value: "ver-aaa-1" } });

    // After the change the PUT should have fired and the intraday select should
    // reflect the newly returned map state.
    await waitFor(() => {
      const sel = screen.getByLabelText(/Intraday risk plan/i) as HTMLSelectElement;
      expect(sel.value).toBe("ver-aaa-1");
    });
  });

  it("shows an error banner when the risk-plan-map endpoint is unavailable", async () => {
    restore = installFetchMock([
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/risk-config`,
        body: RISK_CONFIG,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/restrictions`,
        body: RESTRICTIONS,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/risk-plan-map`,
        body: { detail: "Not found" },
        status: 404,
      },
      { url: "/api/v1/risk-plans", body: RISK_PLANS_EMPTY },
    ]);

    renderRoute(<RiskCardPanel accountId={ACCOUNT_ID} />);

    await waitFor(() =>
      expect(screen.getByText(/RiskPlan map/i)).toBeInTheDocument(),
    );
  });

  it("shows the info banner explaining the Governor rejection rule", async () => {
    restore = installFetchMock([
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/risk-config`,
        body: RISK_CONFIG,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/restrictions`,
        body: RESTRICTIONS,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/risk-plan-map`,
        body: RISK_PLAN_MAP_EMPTY,
      },
      { url: "/api/v1/risk-plans", body: RISK_PLANS_EMPTY },
    ]);

    renderRoute(<RiskCardPanel accountId={ACCOUNT_ID} />);

    await waitFor(() =>
      // Slice B fix F-RISK-1: when zero horizons are mapped the explicit
      // danger banner appears. Match that specifically — the older info
      // banner was reworded as part of F-NIT-2 to name the actual rule_id.
      expect(screen.getByText(/Governor will reject every SignalPlan/i)).toBeInTheDocument(),
    );
  });
});
