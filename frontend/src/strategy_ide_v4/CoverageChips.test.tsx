/**
 * Tests for CoverageChips.
 */

import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderRoute } from "@/test/renderRoute";
import { CoverageChips } from "./CoverageChips";
import { buildPlaceholderLegs, buildPlaceholderStops } from "./draftDefaults";
import type { ExitsSectionValue } from "./ExitsSection";

const EMPTY_EXITS: ExitsSectionValue = { long: [], short: [] };

function makeExits(longCount: number): ExitsSectionValue {
  return {
    long: Array.from({ length: longCount }, (_, i) => ({
      id: `exit-${i}`,
      template_id: "session_end" as const,
      params: {},
    })),
    short: [],
  };
}

describe("<CoverageChips />", () => {
  it("Entry chip is satisfied when entryLong is non-empty", () => {
    renderRoute(
      <CoverageChips
        entryLong="5m.ema(9) > 5m.ema(21)"
        entryShort=""
        stops={buildPlaceholderStops()}
        legs={buildPlaceholderLegs()}
        logicalExits={EMPTY_EXITS}
      />,
    );
    const chip = screen.getByLabelText(/entry satisfied/i);
    expect(chip.className).toContain("text-ok");
  });

  it("Entry chip is not satisfied when both entries are empty", () => {
    renderRoute(
      <CoverageChips
        entryLong=""
        entryShort=""
        stops={buildPlaceholderStops()}
        legs={buildPlaceholderLegs()}
        logicalExits={EMPTY_EXITS}
      />,
    );
    const chip = screen.getByLabelText(/entry not configured/i);
    expect(chip.className).toContain("text-fg-subtle");
  });

  it("Entry chip is satisfied when only entryShort is non-empty", () => {
    renderRoute(
      <CoverageChips
        entryLong=""
        entryShort="5m.rsi(14) > 70"
        stops={buildPlaceholderStops()}
        legs={buildPlaceholderLegs()}
        logicalExits={EMPTY_EXITS}
      />,
    );
    const chip = screen.getByLabelText(/entry satisfied/i);
    expect(chip.className).toContain("text-ok");
  });

  it("Stop chip is satisfied when stops array has at least one item", () => {
    renderRoute(
      <CoverageChips
        entryLong=""
        entryShort=""
        stops={buildPlaceholderStops()}
        legs={buildPlaceholderLegs()}
        logicalExits={EMPTY_EXITS}
      />,
    );
    const chip = screen.getByLabelText(/stop satisfied/i);
    expect(chip.className).toContain("text-ok");
  });

  it("Stop chip is not satisfied when stops array is empty", () => {
    renderRoute(
      <CoverageChips
        entryLong=""
        entryShort=""
        stops={[]}
        legs={buildPlaceholderLegs()}
        logicalExits={EMPTY_EXITS}
      />,
    );
    const chip = screen.getByLabelText(/stop not configured/i);
    expect(chip.className).toContain("text-fg-subtle");
  });

  it("Target chip is satisfied when at least one leg has kind=target", () => {
    renderRoute(
      <CoverageChips
        entryLong=""
        entryShort=""
        stops={buildPlaceholderStops()}
        legs={buildPlaceholderLegs()}
        logicalExits={EMPTY_EXITS}
      />,
    );
    const chip = screen.getByLabelText(/target satisfied/i);
    expect(chip.className).toContain("text-ok");
  });

  it("Runner chip is not satisfied when no runner leg exists", () => {
    renderRoute(
      <CoverageChips
        entryLong=""
        entryShort=""
        stops={buildPlaceholderStops()}
        legs={buildPlaceholderLegs()}
        logicalExits={EMPTY_EXITS}
      />,
    );
    const chip = screen.getByLabelText(/runner not configured/i);
    expect(chip.className).toContain("text-fg-subtle");
  });

  it("Exit chip is satisfied when logical exits has entries", () => {
    renderRoute(
      <CoverageChips
        entryLong=""
        entryShort=""
        stops={buildPlaceholderStops()}
        legs={buildPlaceholderLegs()}
        logicalExits={makeExits(1)}
      />,
    );
    const chip = screen.getByLabelText(/exit satisfied/i);
    expect(chip.className).toContain("text-ok");
  });

  it("Exit chip is not satisfied when logical exits are empty", () => {
    renderRoute(
      <CoverageChips
        entryLong=""
        entryShort=""
        stops={buildPlaceholderStops()}
        legs={buildPlaceholderLegs()}
        logicalExits={EMPTY_EXITS}
      />,
    );
    const chip = screen.getByLabelText(/exit not configured/i);
    expect(chip.className).toContain("text-fg-subtle");
  });

  it("renders five chip elements", () => {
    renderRoute(
      <CoverageChips
        entryLong="expr"
        entryShort=""
        stops={buildPlaceholderStops()}
        legs={buildPlaceholderLegs()}
        logicalExits={EMPTY_EXITS}
      />,
    );
    // Five chips: Entry, Stop, Target, Runner, Exit
    const container = screen.getByLabelText(/coverage status/i);
    expect(container.children).toHaveLength(5);
  });
});
