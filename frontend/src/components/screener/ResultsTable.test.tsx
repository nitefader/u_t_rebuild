import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
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
});
