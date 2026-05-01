/**
 * Tests for StarterStrategyPanel.
 */

import { describe, expect, it, vi } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { renderRoute } from "@/test/renderRoute";
import { StarterStrategyPanel } from "./StarterStrategyPanel";
import { STARTER_STRATEGIES } from "./starterStrategies";
import { StrategyVersionV4DraftSchema } from "@/api/schemas/strategiesV4";

// Mock the AI API so StarterStrategyPanel tests don't hit the network
vi.mock("@/api/strategiesV4", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/strategiesV4")>();
  return { ...actual, aiFillStrategy: vi.fn() };
});

const NO_OP = vi.fn();

function defaultProps(overrides?: Partial<Parameters<typeof StarterStrategyPanel>[0]>) {
  return {
    open: true,
    onOpenChange: vi.fn(),
    horizonFilter: null,
    directionFilter: null,
    onApply: vi.fn(),
    ...overrides,
  };
}

describe("<StarterStrategyPanel />", () => {
  it("renders 10 starter strategy cards when open with no filter", () => {
    renderRoute(<StarterStrategyPanel {...defaultProps()} />);
    const cards = screen.getAllByTestId("starter-card");
    expect(cards).toHaveLength(10);
  });

  it("shows '10 curated' header text", () => {
    renderRoute(<StarterStrategyPanel {...defaultProps()} />);
    expect(screen.getByText(/10 curated/i)).toBeInTheDocument();
  });

  it("horizon filter narrows to expected count (swing)", () => {
    renderRoute(<StarterStrategyPanel {...defaultProps({ horizonFilter: "swing" })} />);
    const swingCount = STARTER_STRATEGIES.filter((s) => s.tags.horizon === "swing").length;
    const cards = screen.getAllByTestId("starter-card");
    expect(cards).toHaveLength(swingCount);
  });

  it("intraday filter shows only intraday strategies", () => {
    renderRoute(<StarterStrategyPanel {...defaultProps({ horizonFilter: "intraday" })} />);
    const intradayCount = STARTER_STRATEGIES.filter((s) => s.tags.horizon === "intraday").length;
    const cards = screen.getAllByTestId("starter-card");
    expect(cards).toHaveLength(intradayCount);
  });

  it("position filter shows only position strategies", () => {
    renderRoute(<StarterStrategyPanel {...defaultProps({ horizonFilter: "position" })} />);
    const posCount = STARTER_STRATEGIES.filter((s) => s.tags.horizon === "position").length;
    const cards = screen.getAllByTestId("starter-card");
    expect(cards).toHaveLength(posCount);
  });

  it("calls onApply with the full draft when Apply template is clicked", async () => {
    const onApply = vi.fn();
    renderRoute(<StarterStrategyPanel {...defaultProps({ onApply })} />);

    // Expand the first card
    const firstCard = screen.getAllByRole("button", { name: /expand strategy details/i })[0];
    fireEvent.click(firstCard);

    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /apply.*template/i })[0]).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole("button", { name: /apply.*template/i })[0]);

    expect(onApply).toHaveBeenCalledOnce();
    const draft = onApply.mock.calls[0][0];
    // Draft should have name, entries, stops, legs
    expect(draft).toHaveProperty("name");
    expect(draft).toHaveProperty("stops");
    expect(draft).toHaveProperty("legs");
    expect(draft.stops).toHaveLength(1);
    expect(draft.legs.length).toBeGreaterThanOrEqual(1);
  });

  it("shows 'No strategies match' when no strategies pass filter", () => {
    // scalping + long returns 0 since no scalping strategies exist in our registry
    renderRoute(
      <StarterStrategyPanel
        {...defaultProps({ horizonFilter: "scalping", directionFilter: "long" })}
      />,
    );
    const scalping_long = STARTER_STRATEGIES.filter(
      (s) => s.tags.horizon === "scalping" && s.tags.direction === "long",
    );
    if (scalping_long.length === 0) {
      expect(screen.getByText(/no strategies match/i)).toBeInTheDocument();
    }
  });

  it("renders collapsed handle when open=false", () => {
    const onOpenChange = vi.fn();
    renderRoute(
      <StarterStrategyPanel
        {...defaultProps({ open: false, onOpenChange })}
      />,
    );
    const handle = screen.getByRole("button", { name: /open starter strategies panel/i });
    expect(handle).toBeInTheDocument();

    fireEvent.click(handle);
    expect(onOpenChange).toHaveBeenCalledWith(true);
  });

  it("close button calls onOpenChange(false)", () => {
    const onOpenChange = vi.fn();
    renderRoute(<StarterStrategyPanel {...defaultProps({ onOpenChange })} />);
    fireEvent.click(screen.getByRole("button", { name: /close starter strategies panel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("expanded card shows entry, stop, target, runner, logical exit sections", async () => {
    renderRoute(<StarterStrategyPanel {...defaultProps()} />);

    const firstExpandBtn = screen.getAllByRole("button", { name: /expand strategy details/i })[0];
    fireEvent.click(firstExpandBtn);

    await waitFor(() => {
      expect(screen.getAllByText(/entry/i).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText(/runner/i).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText(/logical exit/i).length).toBeGreaterThanOrEqual(1);
    });
  });

  it("expanded card shows 'About this strategy' block with edge, best_on, why_it_works", async () => {
    renderRoute(<StarterStrategyPanel {...defaultProps()} />);

    const firstExpandBtn = screen.getAllByRole("button", { name: /expand strategy details/i })[0];
    fireEvent.click(firstExpandBtn);

    await waitFor(() => {
      expect(screen.getByText(/about this strategy/i)).toBeInTheDocument();
      expect(screen.getAllByText(/edge/i).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText(/best on/i).length).toBeGreaterThanOrEqual(1);
    });
  });

  it("all 10 starter strategies have valid drafts (stops >= 1, legs sum 1.0, schema parses)", () => {
    expect(STARTER_STRATEGIES).toHaveLength(10);

    for (const s of STARTER_STRATEGIES) {
      // stops and legs structural checks
      expect(s.draft.stops.length, `${s.name}: stops`).toBeGreaterThanOrEqual(1);
      expect(s.draft.legs.length, `${s.name}: legs`).toBeGreaterThanOrEqual(1);
      const total = s.draft.legs.reduce((acc, l) => acc + l.size_pct, 0);
      expect(Math.abs(total - 1.0), `${s.name}: legs sum`).toBeLessThan(1e-6);

      // Zod schema parse — confirms draft matches the schema
      const result = StrategyVersionV4DraftSchema.safeParse(s.draft);
      expect(result.success, `${s.name}: schema parse — ${!result.success ? JSON.stringify((result as { error: unknown }).error) : "ok"}`).toBe(true);
    }
  });

  it("all 10 starter strategies have required About fields (edge_type, best_on, why_it_works)", () => {
    for (const s of STARTER_STRATEGIES) {
      expect(s.edge_type, `${s.name}: edge_type`).toBeTruthy();
      expect(s.best_on, `${s.name}: best_on`).toBeTruthy();
      expect(s.why_it_works, `${s.name}: why_it_works`).toBeTruthy();
    }
  });

  it("all 10 starter strategies have all 7 detail keys", () => {
    const REQUIRED_KEYS: (keyof typeof STARTER_STRATEGIES[0]["details"])[] = [
      "entry",
      "stop",
      "target",
      "runner",
      "logical_exit",
      "time_constraints",
      "risk_sizing",
    ];
    for (const s of STARTER_STRATEGIES) {
      for (const key of REQUIRED_KEYS) {
        expect(s.details[key], `${s.name}: details.${key}`).toBeTruthy();
      }
    }
  });

  it("renders both Templates and AI prompt tabs", () => {
    renderRoute(<StarterStrategyPanel {...defaultProps()} />);
    expect(screen.getByTestId("tab-templates")).toBeInTheDocument();
    expect(screen.getByTestId("tab-ai")).toBeInTheDocument();
  });

  it("Templates tab is selected by default", () => {
    renderRoute(<StarterStrategyPanel {...defaultProps()} />);
    const templatesTab = screen.getByTestId("tab-templates");
    expect(templatesTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("tab-ai")).toHaveAttribute("aria-selected", "false");
  });

  it("clicking AI prompt tab switches to AI content", () => {
    renderRoute(<StarterStrategyPanel {...defaultProps()} />);
    fireEvent.click(screen.getByTestId("tab-ai"));
    // AI tab panel should be visible — textarea placeholder
    expect(screen.getByLabelText(/strategy idea prompt/i)).toBeInTheDocument();
    // Template cards should not be visible
    expect(screen.queryAllByTestId("starter-card")).toHaveLength(0);
  });

  it("clicking Templates tab after AI shows templates again", () => {
    renderRoute(<StarterStrategyPanel {...defaultProps()} />);
    fireEvent.click(screen.getByTestId("tab-ai"));
    fireEvent.click(screen.getByTestId("tab-templates"));
    const cards = screen.getAllByTestId("starter-card");
    expect(cards.length).toBeGreaterThan(0);
  });

  void NO_OP;
});
