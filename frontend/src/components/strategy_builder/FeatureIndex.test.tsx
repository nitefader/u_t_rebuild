import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FeatureCatalogItem } from "@/api/schemas/strategyComposer";
import { FeatureIndex } from "./FeatureIndex";

const CATALOG: FeatureCatalogItem[] = [
  {
    kind: "ema",
    display_name: "EMA",
    namespace: "technical",
    scope: "symbol",
    source: "close",
    description: "Exponential moving average.",
    allowed_params: ["length"],
    default_params: { length: 20 },
    supported_timeframes: ["1m", "5m", "15m", "1h", "1d"],
    supported_consumers: ["backtest"],
    supported_modes: ["batch"],
    example_refs: [],
  },
  {
    kind: "rsi",
    display_name: "RSI",
    namespace: "technical",
    scope: "symbol",
    source: "close",
    description: "Wilder Relative Strength Index.",
    allowed_params: ["length"],
    default_params: { length: 14 },
    supported_timeframes: ["5m", "15m"],
    supported_consumers: ["backtest"],
    supported_modes: ["batch"],
    example_refs: [],
  },
  {
    kind: "open",
    display_name: "Open",
    namespace: "price",
    scope: "symbol",
    source: "open",
    description: "Bar open.",
    allowed_params: [],
    default_params: {},
    supported_timeframes: ["1m", "5m"],
    supported_consumers: ["backtest"],
    supported_modes: ["batch"],
    example_refs: [],
  },
  {
    kind: "gross_exposure_pct",
    display_name: "Gross Exposure %",
    namespace: "portfolio",
    scope: "portfolio",
    source: "portfolio",
    description: "Total gross exposure across the portfolio.",
    allowed_params: [],
    default_params: {},
    supported_timeframes: ["5m"],
    supported_consumers: ["backtest"],
    supported_modes: ["batch"],
    example_refs: [],
  },
];

describe("<FeatureIndex /> — Slice 6c drawer", () => {
  it("does not render anything when closed", () => {
    render(
      <FeatureIndex
        open={false}
        onOpenChange={() => {}}
        catalog={CATALOG}
        onInsert={() => {}}
      />,
    );
    expect(screen.queryByTestId("feature-index-drawer")).not.toBeInTheDocument();
  });

  it("renders as a drawer when open and groups by namespace", () => {
    render(
      <FeatureIndex
        open
        onOpenChange={() => {}}
        catalog={CATALOG}
        onInsert={() => {}}
      />,
    );
    expect(screen.getByTestId("feature-index-drawer")).toBeInTheDocument();
    expect(screen.getByText(/Technical/i)).toBeInTheDocument();
    expect(screen.getByText(/Price/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Insert ema at 5m/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Insert ema at 1h/i })).toBeInTheDocument();
  });

  it("filters by search query", async () => {
    const user = userEvent.setup();
    render(
      <FeatureIndex
        open
        onOpenChange={() => {}}
        catalog={CATALOG}
        onInsert={() => {}}
      />,
    );
    await user.type(screen.getByRole("textbox", { name: /Search features/i }), "rsi");
    expect(screen.queryByRole("button", { name: /Insert ema at 5m/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Insert rsi at 5m/i })).toBeInTheDocument();
  });

  it("clicking a timeframe pill emits onInsert and closes the drawer", async () => {
    const user = userEvent.setup();
    const onInsert = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <FeatureIndex
        open
        onOpenChange={onOpenChange}
        catalog={CATALOG}
        onInsert={onInsert}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Insert ema at 5m/i }));
    expect(onInsert).toHaveBeenCalledWith("5m.ema:length=20[0]");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("Advanced raw expression input emits and closes", async () => {
    const user = userEvent.setup();
    const onInsert = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <FeatureIndex
        open
        onOpenChange={onOpenChange}
        catalog={CATALOG}
        onInsert={onInsert}
      />,
    );
    const input = screen.getByPlaceholderText(/5m\.sma:length=20\[0\]/);
    fireEvent.change(input, { target: { value: "1h.vwap:session=regular[0]" } });
    await user.click(screen.getByRole("button", { name: "Insert" }));
    expect(onInsert).toHaveBeenCalledWith("1h.vwap:session=regular[0]");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("PORTFOLIO-scope features are filtered out at the Strategy-author surface", () => {
    render(
      <FeatureIndex
        open
        onOpenChange={() => {}}
        catalog={CATALOG}
        onInsert={() => {}}
      />,
    );
    expect(screen.queryByText(/gross_exposure_pct/i)).not.toBeInTheDocument();
  });

  it("slot label appears in the drawer description when provided", () => {
    render(
      <FeatureIndex
        open
        onOpenChange={() => {}}
        catalog={CATALOG}
        onInsert={() => {}}
        slotLabel="Long entry rules feature pool"
      />,
    );
    expect(screen.getByText(/Insert into Long entry rules feature pool/i)).toBeInTheDocument();
  });
});
