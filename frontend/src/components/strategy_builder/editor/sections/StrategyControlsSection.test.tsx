import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { StrategyControlsVersion } from "@/api/schemas/strategyComposer";
import { StrategyControlsSection } from "./StrategyControlsSection";

const CONTROLS: StrategyControlsVersion = {
  id: "00000000-0000-0000-0000-0000000000dd",
  strategy_controls_id: "00000000-0000-0000-0000-0000000000ee",
  version: 1,
  name: "Draft Controls",
  timeframe: "5m",
  trading_horizon: "intraday",
  allowed_directions: "long",
  higher_timeframe_confirmation_required: false,
  session_preference: "regular_only",
  earnings_news_blackout_enabled: false,
} as unknown as StrategyControlsVersion;

describe("Slice G — StrategyControlsSection split into two cards", () => {
  it("renders the wrapper testid for the existing section→target mapping", () => {
    render(<StrategyControlsSection controls={CONTROLS} onChange={() => {}} />);
    // Wrapper carries the canonical id so handleJumpToSection still resolves.
    const wrapper = screen.getByTestId("section-strategy-controls");
    expect(wrapper).toHaveAttribute("id", "section-strategy-controls");
  });

  it("renders both Timeframe-and-horizon and Session-windows cards as distinct subcards", () => {
    render(<StrategyControlsSection controls={CONTROLS} onChange={() => {}} />);
    expect(screen.getByTestId("section-strategy-controls-timeframe")).toBeInTheDocument();
    expect(screen.getByTestId("section-strategy-controls-session")).toBeInTheDocument();
  });

  it("places timeframe / horizon / directions / HTF inside the Timeframe card", () => {
    render(<StrategyControlsSection controls={CONTROLS} onChange={() => {}} />);
    const card = screen.getByTestId("section-strategy-controls-timeframe");
    expect(within(card).getByTestId("controls-name")).toBeInTheDocument();
    expect(within(card).getByTestId("controls-horizon")).toBeInTheDocument();
    expect(within(card).getByTestId("controls-directions")).toBeInTheDocument();
    expect(within(card).getByTestId("controls-timeframe")).toBeInTheDocument();
    expect(within(card).getByTestId("controls-htf-required")).toBeInTheDocument();
  });

  it("places session preference + earnings blackout inside the Session card", () => {
    render(<StrategyControlsSection controls={CONTROLS} onChange={() => {}} />);
    const card = screen.getByTestId("section-strategy-controls-session");
    expect(within(card).getByTestId("controls-session-preference")).toBeInTheDocument();
    expect(within(card).getByTestId("controls-earnings-blackout")).toBeInTheDocument();
  });

  it("does NOT render unsupported scaffolding (cooldowns / PDT / regime cards)", () => {
    render(<StrategyControlsSection controls={CONTROLS} onChange={() => {}} />);
    // These cards are blocked on backend / frontend-schema work and must not be scaffolded.
    expect(screen.queryByTestId("section-strategy-controls-cooldowns")).toBeNull();
    expect(screen.queryByTestId("section-strategy-controls-pdt")).toBeNull();
    expect(screen.queryByTestId("section-strategy-controls-regime")).toBeNull();
  });

  it("editing a Session-card field still calls onChange with the full controls object", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<StrategyControlsSection controls={CONTROLS} onChange={onChange} />);
    await user.click(screen.getByTestId("controls-earnings-blackout"));
    expect(onChange).toHaveBeenCalled();
    const arg = onChange.mock.calls.at(-1)?.[0];
    expect(arg).toMatchObject({ ...CONTROLS, earnings_news_blackout_enabled: true });
  });
});
