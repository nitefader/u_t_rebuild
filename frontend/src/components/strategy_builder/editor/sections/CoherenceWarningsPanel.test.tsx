import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { StrategyDraft } from "@/api/schemas/strategyComposer";
import type { CoherenceWarning } from "../coherenceValidator";
import { CoherenceWarningsPanel } from "./CoherenceWarningsPanel";

const DRAFT_STUB = {
  validation: { valid: true, errors: [], warnings: [], normalized_feature_refs: [] },
} as unknown as StrategyDraft;

const ERROR_WARNING: CoherenceWarning = {
  id: "logical_exit_fires_immediately_after_entry",
  severity: "error",
  sectionId: "section-logical-exit",
  message: "Logical exit can fire immediately after entry.",
  dismissed: false,
};

const WARN_WARNING: CoherenceWarning = {
  id: "stop_target_ratio_nonsensical",
  severity: "warn",
  sectionId: "section-stop-plan",
  message: "Reward/risk ratio looks inverted.",
  dismissed: false,
};

describe("<CoherenceWarningsPanel /> — jump-to-section (Slice C-3)", () => {
  it("when onJumpToSection is provided, error rows render the message as a button", () => {
    const onJump = vi.fn();
    render(
      <CoherenceWarningsPanel
        draft={DRAFT_STUB}
        warnings={[ERROR_WARNING]}
        onDismiss={() => {}}
        onJumpToSection={onJump}
      />,
    );
    expect(
      screen.getByTestId(`coherence-warning-jump-${ERROR_WARNING.id}`),
    ).toBeInTheDocument();
  });

  it("clicking the row button calls onJumpToSection with the offending sectionId", async () => {
    const user = userEvent.setup();
    const onJump = vi.fn();
    render(
      <CoherenceWarningsPanel
        draft={DRAFT_STUB}
        warnings={[ERROR_WARNING, WARN_WARNING]}
        onDismiss={() => {}}
        onJumpToSection={onJump}
      />,
    );

    await user.click(screen.getByTestId(`coherence-warning-jump-${WARN_WARNING.id}`));
    expect(onJump).toHaveBeenCalledTimes(1);
    expect(onJump).toHaveBeenCalledWith("section-stop-plan");
  });

  it("when onJumpToSection is omitted, the row stays as inert text (no button)", () => {
    render(
      <CoherenceWarningsPanel
        draft={DRAFT_STUB}
        warnings={[ERROR_WARNING]}
        onDismiss={() => {}}
      />,
    );
    expect(
      screen.queryByTestId(`coherence-warning-jump-${ERROR_WARNING.id}`),
    ).not.toBeInTheDocument();
    // Row body still exists.
    expect(screen.getByTestId(`coherence-warning-${ERROR_WARNING.id}`)).toBeInTheDocument();
  });
});
