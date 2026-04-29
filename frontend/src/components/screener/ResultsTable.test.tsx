import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResultsTable } from "./ResultsTable";
import type { ScreenerFieldDefinition, ScreenerResultRow } from "@/api/schemas/screener";

const metrics: ScreenerFieldDefinition[] = [
  {
    key: "broker.tradable",
    label: "Tradable at Alpaca",
    value_type: "boolean",
    unit: null,
    sources: ["alpaca_assets"],
    cadence: "per run",
    unavailable_behavior: "fail closed",
    supported_operators: ["eq"],
  },
];

describe("<ResultsTable /> capability evidence", () => {
  it("does not report AAPL as not tradable when bar metrics fail but Alpaca capability is true", () => {
    const row: ScreenerResultRow = {
      symbol: "AAPL",
      matched: true,
      metrics: {
        "broker.name": "Apple Inc. Common Stock",
        "broker.tradable": true,
      },
      failed_criteria: [],
      passed_criteria: ["Tradable at Alpaca"],
      blocked_reasons: [],
      evidence: {
        error: "bar metrics unavailable: Data Center bars unavailable",
        asset_capability: { unavailable_reason: null },
      },
      score: null,
      sparkline: [],
    };

    render(<ResultsTable results={[row]} metrics={metrics} />);

    expect(screen.getByText(/Decision reason/i)).toBeInTheDocument();
    expect(screen.getByText("Apple Inc. Common Stock")).toBeInTheDocument();
    expect(screen.getByText("bar metrics unavailable: Data Center bars unavailable")).toBeInTheDocument();
    expect(screen.queryByText(/not tradable/i)).not.toBeInTheDocument();
  });

  it("labels unavailable Alpaca capability evidence separately from a false capability", () => {
    const row: ScreenerResultRow = {
      symbol: "AAPL",
      matched: false,
      metrics: {
        "broker.tradable": null,
      },
      failed_criteria: ["Tradable at Alpaca (metric unavailable)"],
      passed_criteria: [],
      blocked_reasons: ["Alpaca tradability evidence unavailable"],
      evidence: {
        asset_capability: { unavailable_reason: "Alpaca asset API unavailable" },
      },
      score: null,
      sparkline: [],
    };

    render(<ResultsTable results={[row]} metrics={metrics} />);

    expect(screen.getByText("capability unavailable")).toBeInTheDocument();
    expect(screen.getByText(/Alpaca capability unavailable: Alpaca asset API unavailable/)).toBeInTheDocument();
    expect(screen.queryByText(/asset is not tradable at Alpaca/i)).not.toBeInTheDocument();
  });

  it("keeps decision reasons visible while switching metric column presets", async () => {
    const user = userEvent.setup();
    const rows: ScreenerResultRow[] = [
      {
        symbol: "NVDA",
        matched: true,
        metrics: {
          "broker.name": "NVIDIA Corp",
          "broker.tradable": true,
          relative_volume: 2.1,
        },
        failed_criteria: [],
        passed_criteria: ["Relative volume >= 1.5x"],
        blocked_reasons: [],
        evidence: {},
        score: 2.1,
        sparkline: [],
      },
      {
        symbol: "TSLA",
        matched: false,
        metrics: {
          "broker.name": "Tesla Inc",
          "broker.tradable": false,
          relative_volume: 0.8,
        },
        failed_criteria: ["Relative volume below threshold"],
        passed_criteria: [],
        blocked_reasons: ["Risk blocked: not enough volume"],
        evidence: {},
        score: 0.8,
        sparkline: [],
      },
    ];

    render(<ResultsTable results={rows} metrics={metrics} />);

    expect(screen.getByText(/Decision reason/i)).toBeInTheDocument();
    expect(screen.getByText(/Passed: Relative volume >= 1.5x/i)).toBeInTheDocument();
    expect(screen.getByText(/Risk blocked: not enough volume/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Audit$/i }));
    expect(screen.getByText(/Tradable at Alpaca/i)).toBeInTheDocument();
    expect(screen.getByText(/Decision reason/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^All rows$/i }));
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.queryByText("TSLA")).not.toBeInTheDocument();
  });
});
