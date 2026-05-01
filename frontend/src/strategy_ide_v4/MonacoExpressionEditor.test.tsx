/**
 * Tests for MonacoExpressionEditor.
 * Monaco is mocked with a <textarea>-based stub.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, act } from "@testing-library/react";
import { installFetchMock, renderRoute } from "@/test/renderRoute";
import { MonacoExpressionEditor } from "./MonacoExpressionEditor";
import { STRATEGY_EXPR_KEYWORDS } from "./strategyExprLanguage";
import { __resetStrategyExprMonacoProvidersForTests } from "./strategyExprMonacoProviders";
import * as strategiesV4 from "@/api/strategiesV4";

// ---------------------------------------------------------------------------
// Monaco mock — replaces @monaco-editor/react with a textarea stub.
// The mock calls onMount synchronously (in a resolved promise) so that
// the editor ref is populated before tests run.
// The captured completion provider is exposed on the mock for inspection.
// ---------------------------------------------------------------------------

type CompletionSuggestion = {
  label: string | { label: string; detail?: string; description?: string };
  detail?: string;
  insertText?: string;
  sortText?: string;
};

type CompletionProvider = {
  provideCompletionItems: (
    model: unknown,
    position: unknown,
  ) => Promise<{ suggestions: CompletionSuggestion[] }>;
};

type HoverProvider = {
  provideHover: (
    model: unknown,
    position: unknown,
  ) => { contents: Array<{ value: string }> } | null;
};

let capturedCompletionProvider: CompletionProvider | null = null;
let capturedHoverProvider: HoverProvider | null = null;

vi.mock("@monaco-editor/react", () => ({
  default: vi.fn(
    ({
      value,
      onChange,
      onMount,
    }: {
      value: string;
      onChange?: (val: string) => void;
      onMount?: (editor: unknown, monaco: unknown) => void;
    }) => {
      const mockMonaco = {
        languages: {
          register: vi.fn(),
          setMonarchTokensProvider: vi.fn(),
          registerCompletionItemProvider: vi.fn(
            (_lang: string, provider: CompletionProvider) => {
              capturedCompletionProvider = provider;
              return { dispose: vi.fn() };
            },
          ),
          registerHoverProvider: vi.fn(
            (_lang: string, provider: HoverProvider) => {
              capturedHoverProvider = provider;
              return { dispose: vi.fn() };
            },
          ),
        },
        editor: {
          defineTheme: vi.fn(),
          setModelMarkers: vi.fn(),
          getModelMarkers: vi.fn(() => []),
          setTheme: vi.fn(),
        },
        MarkerSeverity: { Error: 8, Warning: 4 },
      };

      const mockEditor = {
        getModel: vi.fn(() => ({ uri: "test" })),
        getPosition: vi.fn(() => ({ lineNumber: 1, column: 1 })),
        executeEdits: vi.fn(),
        focus: vi.fn(),
      };

      if (onMount) {
        // Use queueMicrotask so it fires after render, but before timers
        queueMicrotask(() => onMount(mockEditor, mockMonaco));
      }

      return (
        <textarea
          data-testid="monaco-stub"
          value={value}
          aria-label="Expression editor"
          onChange={(e) => onChange?.(e.target.value)}
        />
      );
    },
  ),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const VALIDATE_RESPONSE_VALID = {
  valid: true,
  errors: [],
  warnings: [],
  feature_requirements: [],
  variables_used: [],
};

const VALIDATE_RESPONSE_ERROR = {
  valid: false,
  errors: [{ level: "error", message: "Unknown identifier: foo", line: 1, col: 1 }],
  warnings: [],
  feature_requirements: [],
  variables_used: [],
};

describe("<MonacoExpressionEditor />", () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
    capturedCompletionProvider = null;
    capturedHoverProvider = null;
    __resetStrategyExprMonacoProvidersForTests();
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("renders the textarea stub (monaco mock active)", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/strategies/expression/validate",
        method: "POST",
        body: VALIDATE_RESPONSE_VALID,
      },
    ]);
    renderRoute(
      <MonacoExpressionEditor value="" onChange={vi.fn()} />,
    );
    // The lazy import resolves in a microtask; waitFor polls until the stub appears
    await waitFor(() => {
      expect(screen.getByTestId("monaco-stub")).toBeInTheDocument();
    });
  });

  it("calls validateExpression after 300ms debounce", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/strategies/expression/validate",
        method: "POST",
        body: VALIDATE_RESPONSE_VALID,
      },
    ]);
    vi.useFakeTimers();
    renderRoute(
      <MonacoExpressionEditor value="5m.ema(9) > 5m.ema(21)" onChange={vi.fn()} />,
    );

    // Flush the dynamic import microtask + React re-render so the editor appears
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId("monaco-stub")).toBeInTheDocument();

    // The component schedules validation on mount for non-empty value.
    // Fast-forward past debounce.
    await act(async () => {
      vi.advanceTimersByTime(350);
    });

    vi.useRealTimers();

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/validate"),
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("fires onValidationChange with valid result after debounce", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/strategies/expression/validate",
        method: "POST",
        body: VALIDATE_RESPONSE_VALID,
      },
    ]);
    vi.useFakeTimers();
    const onValidationChange = vi.fn();
    renderRoute(
      <MonacoExpressionEditor
        value="5m.ema(9) > 5m.ema(21)"
        onChange={vi.fn()}
        onValidationChange={onValidationChange}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });

    await act(async () => {
      vi.advanceTimersByTime(350);
    });

    vi.useRealTimers();

    await waitFor(() => {
      expect(onValidationChange).toHaveBeenCalledWith(
        expect.objectContaining({ valid: true }),
      );
    });
  });

  it("fires onValidationChange with errors when expression is invalid", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/strategies/expression/validate",
        method: "POST",
        body: VALIDATE_RESPONSE_ERROR,
      },
    ]);
    vi.useFakeTimers();
    const onValidationChange = vi.fn();
    renderRoute(
      <MonacoExpressionEditor
        value="foo"
        onChange={vi.fn()}
        onValidationChange={onValidationChange}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });

    await act(async () => {
      vi.advanceTimersByTime(350);
    });

    vi.useRealTimers();

    await waitFor(() => {
      expect(onValidationChange).toHaveBeenCalledWith(
        expect.objectContaining({ valid: false }),
      );
    });
  });

  it("completion provider includes all STRATEGY_EXPR_KEYWORDS", async () => {
    const listSpy = vi.spyOn(strategiesV4, "listExpressionFeatures").mockResolvedValue([
      {
        key: "ema",
        name: "ema",
        namespace: "",
        timeframe_bound: true,
        arity: 1,
        arg_names: ["period"],
        arg_defaults: [9],
        return_type: "float",
        description: "Exponential moving average",
        category: "trend",
      },
    ]);

    renderRoute(<MonacoExpressionEditor value="" onChange={vi.fn()} />);

    await act(async () => {
      await Promise.resolve();
    });

    await waitFor(() => expect(capturedCompletionProvider).not.toBeNull());

    const mockModel = {
      getWordUntilPosition: vi.fn(() => ({ startColumn: 1, endColumn: 1, word: "" })),
      getValueInRange: vi.fn(() => ""),
    };
    const mockPosition = { lineNumber: 1, column: 1 };

    const result = await capturedCompletionProvider!.provideCompletionItems(
      mockModel,
      mockPosition,
    );

    const labels = result.suggestions.map((s) =>
      typeof s.label === "object" ? (s.label as { label: string }).label : s.label,
    );

    for (const kw of STRATEGY_EXPR_KEYWORDS) {
      expect(labels).toContain(kw);
    }

    listSpy.mockRestore();
  });

  it("keyword completion items carry correct detail values", async () => {
    const listSpy = vi.spyOn(strategiesV4, "listExpressionFeatures").mockResolvedValue([]);

    renderRoute(<MonacoExpressionEditor value="" onChange={vi.fn()} />);

    await act(async () => {
      await Promise.resolve();
    });

    await waitFor(() => expect(capturedCompletionProvider).not.toBeNull());

    const mockModel = {
      getWordUntilPosition: vi.fn(() => ({ startColumn: 1, endColumn: 1, word: "" })),
      getValueInRange: vi.fn(() => ""),
    };
    const mockPosition = { lineNumber: 1, column: 1 };

    const result = await capturedCompletionProvider!.provideCompletionItems(
      mockModel,
      mockPosition,
    );

    const byLabel = Object.fromEntries(result.suggestions.map((s) => [s.label, s]));

    expect(byLabel["AND"]?.detail).toBe("language keyword");
    expect(byLabel["OR"]?.detail).toBe("language keyword");
    expect(byLabel["NOT"]?.detail).toBe("language keyword");
    expect(byLabel["crosses_above"]?.detail).toBe("special form");
    expect(byLabel["crosses_below"]?.detail).toBe("special form");
    expect(byLabel["within"]?.detail).toBe("special form");
    expect(byLabel["any_of"]?.detail).toBe("special form");
    expect(byLabel["all_of"]?.detail).toBe("special form");

    listSpy.mockRestore();
  });

  it("hover provider is registered on mount", async () => {
    const listSpy = vi.spyOn(strategiesV4, "listExpressionFeatures").mockResolvedValue([]);

    renderRoute(<MonacoExpressionEditor value="" onChange={vi.fn()} />);

    await act(async () => {
      await Promise.resolve();
    });

    await waitFor(() => expect(capturedHoverProvider).not.toBeNull());

    listSpy.mockRestore();
  });

  it("hover provider returns markdown with description and usage example for known feature", async () => {
    const listSpy = vi.spyOn(strategiesV4, "listExpressionFeatures").mockResolvedValue([
      {
        key: "ema",
        name: "ema",
        namespace: "",
        timeframe_bound: true,
        arity: 1,
        arg_names: ["period"],
        arg_defaults: [9],
        return_type: "float",
        description: "Exponential moving average",
        category: "trend",
      },
    ]);

    renderRoute(<MonacoExpressionEditor value="5m.ema(9)" onChange={vi.fn()} />);

    await act(async () => {
      await Promise.resolve();
    });

    await waitFor(() => expect(capturedHoverProvider).not.toBeNull());

    // Trigger a completion fetch to populate the cache
    const mockModelCompletion = {
      getWordUntilPosition: vi.fn(() => ({ startColumn: 5, endColumn: 8, word: "ema" })),
      getValueInRange: vi.fn(() => "5m."),
    };
    await capturedCompletionProvider!.provideCompletionItems(mockModelCompletion, { lineNumber: 1, column: 4 });

    const mockModel = {
      getWordAtPosition: vi.fn(() => ({ word: "ema", startColumn: 1, endColumn: 4 })),
    };
    const result = capturedHoverProvider!.provideHover(mockModel, { lineNumber: 1, column: 2 });

    expect(result).not.toBeNull();
    const md = result!.contents[0].value;
    expect(md).toContain("Exponential moving average");
    expect(md).toContain("5m.ema(20) > 5m.ema(50)");

    listSpy.mockRestore();
  });

  it("ema completion item detail contains 'period' and '→ float', insertText references default 9", async () => {
    const listSpy = vi.spyOn(strategiesV4, "listExpressionFeatures").mockResolvedValue([
      {
        key: "ema",
        name: "ema",
        namespace: "",
        timeframe_bound: true,
        arity: 1,
        arg_names: ["period"],
        arg_defaults: [9],
        return_type: "float",
        description: "Exponential moving average",
        category: "trend",
      },
    ]);

    renderRoute(<MonacoExpressionEditor value="" onChange={vi.fn()} />);

    await act(async () => {
      await Promise.resolve();
    });

    await waitFor(() => expect(capturedCompletionProvider).not.toBeNull());

    const mockModel = {
      getWordUntilPosition: vi.fn(() => ({ startColumn: 1, endColumn: 4, word: "ema" })),
      getValueInRange: vi.fn(() => ""),
    };

    const result = await capturedCompletionProvider!.provideCompletionItems(mockModel, {
      lineNumber: 1,
      column: 4,
    });

    const emaSuggestion = result.suggestions.find((s) =>
      typeof s.label === "object" ? (s.label as { label: string }).label === "ema" : s.label === "ema",
    );

    expect(emaSuggestion).toBeDefined();
    expect(emaSuggestion!.detail).toContain("period");
    expect(emaSuggestion!.detail).toContain("→ float");
    // Default value 9 should appear in the insertText snippet
    expect(emaSuggestion!.insertText).toContain("9");

    listSpy.mockRestore();
  });

  it("trend features sort before momentum features via sortText", async () => {
    const listSpy = vi.spyOn(strategiesV4, "listExpressionFeatures").mockResolvedValue([
      {
        key: "rsi",
        name: "rsi",
        namespace: "",
        timeframe_bound: true,
        arity: 1,
        arg_names: ["period"],
        arg_defaults: [14],
        return_type: "float",
        description: "Relative strength index",
        category: "momentum",
      },
      {
        key: "ema",
        name: "ema",
        namespace: "",
        timeframe_bound: true,
        arity: 1,
        arg_names: ["period"],
        arg_defaults: [9],
        return_type: "float",
        description: "Exponential moving average",
        category: "trend",
      },
    ]);

    renderRoute(<MonacoExpressionEditor value="" onChange={vi.fn()} />);

    await act(async () => {
      await Promise.resolve();
    });

    await waitFor(() => expect(capturedCompletionProvider).not.toBeNull());

    const mockModel = {
      getWordUntilPosition: vi.fn(() => ({ startColumn: 1, endColumn: 1, word: "" })),
      getValueInRange: vi.fn(() => ""),
    };

    const result = await capturedCompletionProvider!.provideCompletionItems(mockModel, {
      lineNumber: 1,
      column: 1,
    });

    function suggestionName(s: CompletionSuggestion): string {
      return typeof s.label === "object" ? s.label.label : s.label;
    }

    const emaSuggestion = result.suggestions.find((s) => suggestionName(s) === "ema");
    const rsiSuggestion = result.suggestions.find((s) => suggestionName(s) === "rsi");

    expect(emaSuggestion?.sortText).toBe("0_ema");
    expect(rsiSuggestion?.sortText).toBe("1_rsi");
    expect(emaSuggestion).toBeDefined();
    expect(rsiSuggestion).toBeDefined();

    listSpy.mockRestore();
  });
});
