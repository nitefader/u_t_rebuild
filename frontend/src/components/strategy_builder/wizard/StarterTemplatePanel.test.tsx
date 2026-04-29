import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StarterTemplatePanel } from "./StarterTemplatePanel";
import type { StarterTemplate } from "./templates";

beforeEach(() => {
  window.localStorage.clear();
});

describe("StarterTemplatePanel", () => {
  it("renders 9 ready and 3 deferred templates by default", () => {
    render(<StarterTemplatePanel prompt="" onApplyTemplate={() => {}} />);

    const panel = screen.getByTestId("starter-template-panel");
    expect(within(panel).getByText("Available")).toBeInTheDocument();
    expect(
      within(panel).getByText(/Awaiting backend update.*Slice 6a-ii/),
    ).toBeInTheDocument();

    // 9 ready templates
    expect(within(panel).getByTestId("template-card-vwap-reclaim")).toBeInTheDocument();
    expect(within(panel).getByTestId("template-card-supertrend-trend-follow")).toBeInTheDocument();
    expect(within(panel).getByTestId("template-card-rsi-mean-reversion")).toBeInTheDocument();
    expect(within(panel).getByTestId("template-card-connors-rsi-2")).toBeInTheDocument();
    expect(within(panel).getByTestId("template-card-internal-bar-strength")).toBeInTheDocument();
    expect(within(panel).getByTestId("template-card-ichimoku-cloud-trend")).toBeInTheDocument();
    expect(within(panel).getByTestId("template-card-moving-average-pullback")).toBeInTheDocument();
    expect(within(panel).getByTestId("template-card-atr-breakout")).toBeInTheDocument();
    expect(within(panel).getByTestId("template-card-fvg-htf")).toBeInTheDocument();

    // 3 deferred
    expect(
      within(panel).getByTestId("template-card-opening-range-breakout"),
    ).toBeInTheDocument();
    expect(within(panel).getByTestId("template-card-gap-and-go")).toBeInTheDocument();
    expect(
      within(panel).getByTestId("template-card-prior-day-high-low-breakout"),
    ).toBeInTheDocument();
  });

  it("blocked templates render with data-blocked and disabled Apply", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn();
    render(<StarterTemplatePanel prompt="" onApplyTemplate={onApply} />);

    const card = screen.getByTestId("template-card-opening-range-breakout");
    expect(card).toHaveAttribute("data-blocked", "true");

    // Expand the card to see the apply button.
    await user.click(within(card).getByRole("button", { expanded: false }));
    const applyBtn = screen.getByTestId("apply-template-opening-range-breakout");
    expect(applyBtn).toBeDisabled();
    expect(applyBtn.textContent).toMatch(/Generate disabled/i);

    // Should also show the deferred-reason banner.
    expect(
      within(card).getByText(/Requires SESSION execution.*Slice 6a-ii/),
    ).toBeInTheDocument();
  });

  it("clicking Apply on a ready template invokes onApplyTemplate", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn();
    render(<StarterTemplatePanel prompt="" onApplyTemplate={onApply} />);

    const card = screen.getByTestId("template-card-vwap-reclaim");
    await user.click(within(card).getByRole("button", { expanded: false }));
    await user.click(screen.getByTestId("apply-template-vwap-reclaim"));

    expect(onApply).toHaveBeenCalledTimes(1);
    const applied = onApply.mock.calls[0][0] as StarterTemplate;
    expect(applied.id).toBe("vwap-reclaim");
  });

  it("filtering by horizon=swing hides intraday templates", async () => {
    const user = userEvent.setup();
    render(<StarterTemplatePanel prompt="" onApplyTemplate={() => {}} />);

    await user.selectOptions(screen.getByLabelText("Horizon"), "swing");
    expect(screen.queryByTestId("template-card-vwap-reclaim")).toBeNull();
    expect(screen.getByTestId("template-card-rsi-mean-reversion")).toBeInTheDocument();
  });

  it("filtering by direction=short hides long-only templates", async () => {
    const user = userEvent.setup();
    render(<StarterTemplatePanel prompt="" onApplyTemplate={() => {}} />);

    await user.selectOptions(screen.getByLabelText("Direction"), "short");
    expect(screen.queryByTestId("template-card-vwap-reclaim")).toBeNull();
    expect(screen.queryByTestId("template-card-rsi-mean-reversion")).toBeNull();
  });

  it("prompt that matches Connors RSI-2 marks the card as suggested", () => {
    render(
      <StarterTemplatePanel
        prompt="Connors RSI-2 mean reversion daily long"
        onApplyTemplate={() => {}}
      />,
    );

    const card = screen.getByTestId("template-card-connors-rsi-2");
    expect(card).toHaveAttribute("data-suggested", "true");
    expect(within(card).getByText("Matches prompt")).toBeInTheDocument();
  });

  it("recently used sort orders applied templates first after re-render", async () => {
    const user = userEvent.setup();
    const { unmount } = render(
      <StarterTemplatePanel prompt="" onApplyTemplate={() => {}} />,
    );

    // Apply RSI Mean Reversion first.
    const rsiCard = screen.getByTestId("template-card-rsi-mean-reversion");
    await user.click(within(rsiCard).getByRole("button", { expanded: false }));
    await user.click(screen.getByTestId("apply-template-rsi-mean-reversion"));

    unmount();
    render(<StarterTemplatePanel prompt="" onApplyTemplate={() => {}} />);
    await user.selectOptions(screen.getByLabelText("Sort"), "recently_used");

    const cards = screen.getAllByRole("article");
    expect(cards[0].getAttribute("data-template-id")).toBe("rsi-mean-reversion");
  });

  it("filter and sort persist to localStorage", async () => {
    const user = userEvent.setup();
    render(<StarterTemplatePanel prompt="" onApplyTemplate={() => {}} />);

    await user.selectOptions(screen.getByLabelText("Horizon"), "swing");
    await user.selectOptions(screen.getByLabelText("Sort"), "recently_used");

    expect(window.localStorage.getItem("compose:wizard:filter")).toContain("swing");
    expect(window.localStorage.getItem("compose:wizard:sort")).toBe("recently_used");
  });

  it("filtered-empty state shows fallback copy", async () => {
    const user = userEvent.setup();
    render(<StarterTemplatePanel prompt="" onApplyTemplate={() => {}} />);

    // No starter is "scalping + short" — filter returns empty.
    await user.selectOptions(screen.getByLabelText("Horizon"), "scalping");
    await user.selectOptions(screen.getByLabelText("Direction"), "short");

    expect(screen.getByText(/No templates match the current filter/)).toBeInTheDocument();
  });
});
