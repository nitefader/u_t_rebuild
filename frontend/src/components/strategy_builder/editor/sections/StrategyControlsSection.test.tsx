import { describe, expect, it, vi } from "vitest";
import { useState } from "react";
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

function StatefulStrategyControlsSection({
  onChange,
}: {
  onChange: (next: StrategyControlsVersion | null) => void;
}): JSX.Element {
  const [controls, setControls] = useState<StrategyControlsVersion | null>(CONTROLS);
  return (
    <StrategyControlsSection
      controls={controls}
      onChange={(next) => {
        setControls(next);
        onChange(next);
      }}
    />
  );
}

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

  it("does NOT render scaffolding for cards still on the roadmap (PDT / regime)", () => {
    render(<StrategyControlsSection controls={CONTROLS} onChange={() => {}} />);
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

describe("Card C — Cooldowns & caps", () => {
  it("renders the cooldowns subcard with all four numeric inputs", () => {
    render(<StrategyControlsSection controls={CONTROLS} onChange={() => {}} />);
    const card = screen.getByTestId("section-strategy-controls-cooldowns");
    expect(within(card).getByTestId("controls-cooldown-bars")).toBeInTheDocument();
    expect(within(card).getByTestId("controls-cooldown-minutes")).toBeInTheDocument();
    expect(within(card).getByTestId("controls-max-per-session")).toBeInTheDocument();
    expect(within(card).getByTestId("controls-max-per-day")).toBeInTheDocument();
  });

  it("typing a value into max-trades-per-day patches the integer through onChange", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<StatefulStrategyControlsSection onChange={onChange} />);
    await user.type(screen.getByTestId("controls-max-per-day"), "20");
    const last = onChange.mock.calls.at(-1)?.[0];
    expect(last?.max_trades_per_day).toBe(20);
  });

  it("clearing a previously-set cooldown emits null instead of 0", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const seeded = { ...CONTROLS, cooldown_bars: 3 } as StrategyControlsVersion;
    render(<StrategyControlsSection controls={seeded} onChange={onChange} />);
    const input = screen.getByTestId("controls-cooldown-bars");
    await user.clear(input);
    const last = onChange.mock.calls.at(-1)?.[0];
    expect(last?.cooldown_bars).toBeNull();
  });

  it("warns inline when both cooldown_bars and cooldown_minutes are set", () => {
    const conflicting = {
      ...CONTROLS,
      cooldown_bars: 3,
      cooldown_minutes: 10,
    } as StrategyControlsVersion;
    render(<StrategyControlsSection controls={conflicting} onChange={() => {}} />);
    const card = screen.getByTestId("section-strategy-controls-cooldowns");
    expect(within(card).getByText(/Pick one cooldown unit/i)).toBeInTheDocument();
  });
});
