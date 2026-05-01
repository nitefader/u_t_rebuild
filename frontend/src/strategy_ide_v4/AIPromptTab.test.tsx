/**
 * Tests for AIPromptTab.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { renderRoute } from "@/test/renderRoute";
import { AIPromptTab } from "./AIPromptTab";
import type { AISeedFillResponse } from "@/api/strategiesV4";
import type { StrategyVersionV4Draft } from "@/api/schemas/strategiesV4";
import { ApiError } from "@/api/client";

// ---------------------------------------------------------------------------
// Mock the API module
// ---------------------------------------------------------------------------

vi.mock("@/api/strategiesV4", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/strategiesV4")>();
  return {
    ...actual,
    aiFillStrategy: vi.fn(),
  };
});

// We import it after mocking so we can control it per-test
import { aiFillStrategy } from "@/api/strategiesV4";
const mockAiFillStrategy = vi.mocked(aiFillStrategy);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function _makeOkDraft(): StrategyVersionV4Draft {
  return {
    name: "IBS Mean Reversion",
    description: null,
    identity: { tags: [], direction: "long" },
    timeframe_aliases: {},
    variables: [],
    entries: { long: { expression_text: "ibs < 0.2" } },
    stops: [{ id: "stop-1", mode: "simple", scope: "all", simple_type: "%", simple_value: 2.0 }],
    legs: [
      {
        id: "leg-1",
        position: 1,
        kind: "target",
        size_pct: 1.0,
        target_type: "%",
        target_value: 4.0,
        on_fill_action: { kind: "leave", offset_value: null },
      },
    ],
    logical_exits: { long: [], short: [] },
  };
}

function _makeOkResponse(overrides: Partial<AISeedFillResponse> = {}): AISeedFillResponse {
  return {
    draft: _makeOkDraft(),
    validation_status: { valid: true, errors: [], warnings: [] },
    provider_used: "groq",
    model_used: "llama-3.1-70b-versatile",
    raw_response_excerpt: '{"name":"IBS Mean Reversion"...',
    notes: ["This is a mean reversion strategy."],
    ...overrides,
  };
}

function _defaultProps(overrides?: Partial<Parameters<typeof AIPromptTab>[0]>) {
  return {
    onApplyTemplate: vi.fn(),
    currentDraft: undefined,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("<AIPromptTab />", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("Generate button is disabled when prompt is empty", () => {
    renderRoute(<AIPromptTab {..._defaultProps()} />);
    const btn = screen.getByTestId("ai-generate-btn");
    expect(btn).toBeDisabled();
  });

  it("Generate button is disabled when prompt is fewer than 8 characters", () => {
    renderRoute(<AIPromptTab {..._defaultProps()} />);
    const textarea = screen.getByLabelText(/strategy idea prompt/i);
    fireEvent.change(textarea, { target: { value: "short" } });
    expect(screen.getByTestId("ai-generate-btn")).toBeDisabled();
  });

  it("Generate button is enabled when prompt is 8+ characters", () => {
    renderRoute(<AIPromptTab {..._defaultProps()} />);
    const textarea = screen.getByLabelText(/strategy idea prompt/i);
    fireEvent.change(textarea, { target: { value: "FVG strategy on 5m" } });
    expect(screen.getByTestId("ai-generate-btn")).not.toBeDisabled();
  });

  it("clicking a suggestion chip fills the textarea", () => {
    renderRoute(<AIPromptTab {..._defaultProps()} />);
    const firstChip = screen.getByRole("listitem", { name: /FVG long-only on 5m/i });
    fireEvent.click(firstChip);
    const textarea = screen.getByLabelText(/strategy idea prompt/i) as HTMLTextAreaElement;
    expect(textarea.value).toBe("FVG long-only on 5m");
  });

  it("clicking Generate calls aiFillStrategy with the prompt", async () => {
    mockAiFillStrategy.mockResolvedValueOnce(_makeOkResponse());

    renderRoute(<AIPromptTab {..._defaultProps()} />);
    const textarea = screen.getByLabelText(/strategy idea prompt/i);
    fireEvent.change(textarea, { target: { value: "FVG strategy on 5m long-only" } });
    fireEvent.click(screen.getByTestId("ai-generate-btn"));

    await waitFor(() => {
      expect(mockAiFillStrategy).toHaveBeenCalledWith("FVG strategy on 5m long-only", undefined);
    });
  });

  it("renders success card with strategy name and apply button after successful generation", async () => {
    mockAiFillStrategy.mockResolvedValueOnce(_makeOkResponse());

    renderRoute(<AIPromptTab {..._defaultProps()} />);
    const textarea = screen.getByLabelText(/strategy idea prompt/i);
    fireEvent.change(textarea, { target: { value: "FVG strategy on 5m long-only" } });
    fireEvent.click(screen.getByTestId("ai-generate-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("ai-result-card")).toBeInTheDocument();
    });

    expect(screen.getByText("IBS Mean Reversion")).toBeInTheDocument();
    expect(screen.getByTestId("ai-apply-btn")).toBeInTheDocument();
    expect(screen.getByTestId("ai-discard-btn")).toBeInTheDocument();
  });

  it("Apply button fires onApplyTemplate with the AI draft", async () => {
    const onApplyTemplate = vi.fn();
    mockAiFillStrategy.mockResolvedValueOnce(_makeOkResponse());

    renderRoute(<AIPromptTab {..._defaultProps({ onApplyTemplate })} />);
    const textarea = screen.getByLabelText(/strategy idea prompt/i);
    fireEvent.change(textarea, { target: { value: "FVG strategy on 5m long-only" } });
    fireEvent.click(screen.getByTestId("ai-generate-btn"));

    await waitFor(() => screen.getByTestId("ai-apply-btn"));
    fireEvent.click(screen.getByTestId("ai-apply-btn"));

    expect(onApplyTemplate).toHaveBeenCalledOnce();
    const draft = onApplyTemplate.mock.calls[0][0] as StrategyVersionV4Draft;
    expect(draft.name).toBe("IBS Mean Reversion");
    expect(draft.entries.long?.expression_text).toBe("ibs < 0.2");
  });

  it("Discard button removes the result card", async () => {
    mockAiFillStrategy.mockResolvedValueOnce(_makeOkResponse());

    renderRoute(<AIPromptTab {..._defaultProps()} />);
    const textarea = screen.getByLabelText(/strategy idea prompt/i);
    fireEvent.change(textarea, { target: { value: "FVG strategy on 5m long-only" } });
    fireEvent.click(screen.getByTestId("ai-generate-btn"));

    await waitFor(() => screen.getByTestId("ai-result-card"));
    fireEvent.click(screen.getByTestId("ai-discard-btn"));

    await waitFor(() => {
      expect(screen.queryByTestId("ai-result-card")).not.toBeInTheDocument();
    });
  });

  it("shows validation warning banner when validation_status.valid=false", async () => {
    mockAiFillStrategy.mockResolvedValueOnce(
      _makeOkResponse({
        validation_status: {
          valid: false,
          errors: ["'ibs < 0.2': unknown variable 'ibs'"],
          warnings: [],
        },
      }),
    );

    renderRoute(<AIPromptTab {..._defaultProps()} />);
    const textarea = screen.getByLabelText(/strategy idea prompt/i);
    fireEvent.change(textarea, { target: { value: "FVG strategy on 5m long-only" } });
    fireEvent.click(screen.getByTestId("ai-generate-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("ai-validation-warning-banner")).toBeInTheDocument();
    });

    expect(screen.getByText(/AI output has validation errors/i)).toBeInTheDocument();
    // Apply button still present so operator can apply and fix manually
    expect(screen.getByTestId("ai-apply-btn")).toBeInTheDocument();
  });

  it("412 response renders the no-default-provider banner with Providers link", async () => {
    mockAiFillStrategy.mockRejectedValueOnce(
      new ApiError({
        message: "No default AI provider configured.",
        status: 412,
        detail: "No default AI provider configured.",
        url: "/api/v1/strategies/v4/ai-fill",
        body: {},
      }),
    );

    renderRoute(<AIPromptTab {..._defaultProps()} />);
    const textarea = screen.getByLabelText(/strategy idea prompt/i);
    fireEvent.change(textarea, { target: { value: "FVG strategy on 5m long-only" } });
    fireEvent.click(screen.getByTestId("ai-generate-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("ai-error-412")).toBeInTheDocument();
    });

    expect(screen.getByText(/no default AI provider configured/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /providers settings/i });
    expect(link).toHaveAttribute("href", "/providers");
  });

  it("502 response renders error banner with Retry button", async () => {
    mockAiFillStrategy.mockRejectedValueOnce(
      new ApiError({
        message: "AI provider unreachable",
        status: 502,
        detail: "Groq returned HTTP 500: internal server error",
        url: "/api/v1/strategies/v4/ai-fill",
        body: {},
      }),
    );

    renderRoute(<AIPromptTab {..._defaultProps()} />);
    const textarea = screen.getByLabelText(/strategy idea prompt/i);
    fireEvent.change(textarea, { target: { value: "FVG strategy on 5m long-only" } });
    fireEvent.click(screen.getByTestId("ai-generate-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("ai-error-banner")).toBeInTheDocument();
    });

    expect(screen.getByTestId("ai-retry-btn")).toBeInTheDocument();
  });

  it("Retry button re-invokes aiFillStrategy", async () => {
    mockAiFillStrategy
      .mockRejectedValueOnce(
        new ApiError({
          message: "AI provider unreachable",
          status: 502,
          detail: "Groq returned HTTP 500",
          url: "/api/v1/strategies/v4/ai-fill",
          body: {},
        }),
      )
      .mockResolvedValueOnce(_makeOkResponse());

    renderRoute(<AIPromptTab {..._defaultProps()} />);
    const textarea = screen.getByLabelText(/strategy idea prompt/i);
    fireEvent.change(textarea, { target: { value: "FVG strategy on 5m long-only" } });
    fireEvent.click(screen.getByTestId("ai-generate-btn"));

    await waitFor(() => screen.getByTestId("ai-retry-btn"));
    fireEvent.click(screen.getByTestId("ai-retry-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("ai-result-card")).toBeInTheDocument();
    });

    expect(mockAiFillStrategy).toHaveBeenCalledTimes(2);
  });
});
