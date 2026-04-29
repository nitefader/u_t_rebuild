import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { WizardIntent } from "@/api/schemas/strategyComposer";
import { DEFAULT_WIZARD_INTENT, WizardStep1 } from "./WizardStep1";

function renderWizard(overrides: Partial<{
  prompt: string;
  intent: WizardIntent;
  generating: boolean;
  generateError: string | null;
}> = {}) {
  const onPromptChange = vi.fn();
  const onIntentChange = vi.fn();
  const onGenerate = vi.fn();
  const onSkipWizard = vi.fn();
  const props = {
    prompt: overrides.prompt ?? "",
    onPromptChange,
    intent: overrides.intent ?? DEFAULT_WIZARD_INTENT,
    onIntentChange,
    onGenerate,
    onSkipWizard,
    generating: overrides.generating ?? false,
    generateError: overrides.generateError ?? null,
  };
  const utils = render(<WizardStep1 {...props} />);
  return { ...utils, onPromptChange, onIntentChange, onGenerate, onSkipWizard };
}

describe("WizardStep1", () => {
  it("autofocuses the prompt textarea on mount", () => {
    renderWizard();
    expect(document.activeElement).toBe(screen.getByTestId("wizard-prompt"));
  });

  it("Generate with AI is disabled until prompt has 10+ characters", async () => {
    const user = userEvent.setup();
    const { onGenerate, rerender } = renderWizard();

    const btn = screen.getByTestId("generate-with-ai-button");
    expect(btn).toBeDisabled();

    rerender(
      <WizardStep1
        prompt="long entry"
        onPromptChange={() => {}}
        intent={DEFAULT_WIZARD_INTENT}
        onIntentChange={() => {}}
        onGenerate={onGenerate}
        onSkipWizard={() => {}}
        generating={false}
        generateError={null}
      />,
    );
    expect(screen.getByTestId("generate-with-ai-button")).toBeEnabled();
    await user.click(screen.getByTestId("generate-with-ai-button"));
    expect(onGenerate).toHaveBeenCalledOnce();
  });

  it("Cmd+Enter (or Ctrl+Enter) inside the textarea triggers Generate when valid", async () => {
    const user = userEvent.setup();
    const { onGenerate } = renderWizard({ prompt: "Long when 5m close above sma 20" });

    const textarea = screen.getByTestId("wizard-prompt");
    textarea.focus();
    await user.keyboard("{Control>}{Enter}{/Control}");
    expect(onGenerate).toHaveBeenCalledOnce();
  });

  it("clicking Skip wizard invokes onSkipWizard", async () => {
    const user = userEvent.setup();
    const { onSkipWizard } = renderWizard();
    await user.click(screen.getByTestId("skip-wizard-button"));
    expect(onSkipWizard).toHaveBeenCalledOnce();
  });

  it("changing direction radio invokes onIntentChange with new direction", async () => {
    const user = userEvent.setup();
    const { onIntentChange } = renderWizard();

    await user.click(screen.getByTestId("radio-direction-both"));
    expect(onIntentChange).toHaveBeenCalledWith(
      expect.objectContaining({ direction: "both" }),
    );
  });

  it("changing horizon radio invokes onIntentChange with new horizon", async () => {
    const user = userEvent.setup();
    const { onIntentChange } = renderWizard();

    await user.click(screen.getByTestId("radio-horizon-swing"));
    expect(onIntentChange).toHaveBeenCalledWith(
      expect.objectContaining({ horizon: "swing" }),
    );
  });

  it("toggling has_target invokes onIntentChange", async () => {
    const user = userEvent.setup();
    const { onIntentChange } = renderWizard();

    const targetCheckbox = screen
      .getByText("Target")
      .closest("label")
      ?.querySelector("input[type='checkbox']") as HTMLInputElement;
    await user.click(targetCheckbox);
    expect(onIntentChange).toHaveBeenCalledWith(
      expect.objectContaining({ has_target: true }),
    );
  });

  it("conflict warning surfaces when prompt disagrees with checkboxes", () => {
    renderWizard({
      prompt: "Swing trade daily RSI mean reversion long-only setup",
      intent: { ...DEFAULT_WIZARD_INTENT, horizon: "intraday", base_timeframe: "5m" },
    });

    const conflicts = screen.getByTestId("wizard-conflicts");
    expect(conflicts.textContent).toMatch(/disagree/i);
    expect(conflicts.textContent).toMatch(/Swing/i);
  });

  it("'Adjust to match prompt' button updates the wizard intent", async () => {
    const user = userEvent.setup();
    const { onIntentChange } = renderWizard({
      prompt: "Swing trade daily RSI mean reversion",
      intent: { ...DEFAULT_WIZARD_INTENT, horizon: "intraday" },
    });

    await user.click(screen.getByTestId("adjust-horizon"));
    expect(onIntentChange).toHaveBeenCalledWith(
      expect.objectContaining({ horizon: "swing" }),
    );
  });

  it("renders generateError banner when set", () => {
    renderWizard({ generateError: "AI provider quota exceeded" });
    expect(screen.getByText("Generate failed")).toBeInTheDocument();
    expect(screen.getByText("AI provider quota exceeded")).toBeInTheDocument();
  });

  it("Generate button shows loading state while generating", () => {
    renderWizard({ prompt: "Long when close above sma 20", generating: true });
    expect(screen.getByTestId("generate-with-ai-button")).toBeDisabled();
  });
});
