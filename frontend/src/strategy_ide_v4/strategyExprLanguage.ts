/**
 * Registers the `strategy-expr` Monaco language (tokenizer + themes).
 * Idempotent — safe to call multiple times; only registers language once per
 * Monaco instance.  Themes are (re)defined on every call so that CSS-variable
 * color changes (e.g. dark <-> light switch) are picked up.
 */

export type MonacoInstance = typeof import("monaco-editor");

/**
 * Canonical list of DSL keywords.  This is the single source of truth used by
 * both the Monarch tokenizer and the completion item provider.
 */
export const STRATEGY_EXPR_KEYWORDS: readonly string[] = [
  "AND",
  "OR",
  "NOT",
  "crosses_above",
  "crosses_below",
  "within",
  "any_of",
  "all_of",
] as const;

let _languageRegistered = false;

/**
 * Read a CSS custom property from documentElement and convert it from the
 * "R G B" space-separated triplet format used by the theme to a Monaco
 * RRGGBB hex string.
 */
function readVar(name: string): string {
  if (typeof document === "undefined") return "000000";
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  const parts = raw
    .split(/\s+/)
    .filter((p) => p.length > 0)
    .map((n) => Number(n));
  if (parts.length < 3) return "000000";
  const rgb = parts.slice(0, 3);
  if (!rgb.every((c) => typeof c === "number" && !Number.isNaN(c))) {
    return "000000";
  }
  return rgb.map((c) => c.toString(16).padStart(2, "0")).join("");
}

export function registerStrategyExprLanguage(monaco: MonacoInstance): void {
  // Register language + tokenizer exactly once
  if (!_languageRegistered) {
    _languageRegistered = true;

    monaco.languages.register({ id: "strategy-expr" });

    monaco.languages.setMonarchTokensProvider("strategy-expr", {
      keywords: STRATEGY_EXPR_KEYWORDS as string[],

      operators: [">", "<", ">=", "<=", "==", "!=", "+", "-", "*", "/"],

      tokenizer: {
        root: [
          // Line comments
          [/\/\/.*$/, "comment"],

          // Numbers (decimal, int)
          [/\d+\.\d*([eE][+-]?\d+)?/, "number.float"],
          [/\d+/, "number"],

          // Identifiers with dot-notation (e.g. 5m.ema(9) handled at tokenizer level)
          // Timeframe prefix: digits followed by m/h/d/w
          [/\d+[mhdw](?=\.)/, "timeframe"],

          // Keywords
          [
            /[a-zA-Z_][a-zA-Z0-9_]*/,
            {
              cases: {
                "@keywords": "keyword",
                "@default": "identifier",
              },
            },
          ],

          // Dot operator (for member access like 5m.ema or bar.close)
          [/\./, "delimiter.dot"],

          // Operators
          [/>=|<=|==|!=|>|<|\+|-|\*|\//, "operator"],

          // Punctuation
          [/[(),]/, "delimiter"],

          // Whitespace
          [/\s+/, "white"],
        ],
      },
    });
  }

  // Always (re)define both themes so they pick up current CSS variable values.
  // This makes a live theme switch take effect on the next re-register call.
  monaco.editor.defineTheme("strategy-expr-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "keyword", foreground: readVar("--ut-ai"), fontStyle: "bold" },
      { token: "number", foreground: readVar("--ut-warn") },
      { token: "number.float", foreground: readVar("--ut-warn") },
      { token: "timeframe", foreground: readVar("--ut-info") },
      { token: "identifier", foreground: readVar("--ut-fg") },
      { token: "operator", foreground: readVar("--ut-fg-muted") },
      { token: "delimiter", foreground: readVar("--ut-fg-muted") },
      { token: "delimiter.dot", foreground: readVar("--ut-fg-muted") },
      { token: "comment", foreground: readVar("--ut-fg-subtle"), fontStyle: "italic" },
    ],
    colors: {
      "editor.background": `#${readVar("--ut-bg-inset")}`,
      "editor.foreground": `#${readVar("--ut-fg")}`,
      "editorLineNumber.foreground": `#${readVar("--ut-fg-subtle")}`,
      "editorCursor.foreground": `#${readVar("--ut-accent")}`,
      "editor.selectionBackground": `#${readVar("--ut-info-subtle")}`,
      "editor.lineHighlightBackground": `#${readVar("--ut-bg-subtle")}`,
      "editorIndentGuide.background": `#${readVar("--ut-border")}`,
      "editorGutter.background": `#${readVar("--ut-bg-inset")}`,
    },
  });

  monaco.editor.defineTheme("strategy-expr-light", {
    base: "vs",
    inherit: true,
    rules: [
      { token: "keyword", foreground: readVar("--ut-ai"), fontStyle: "bold" },
      { token: "number", foreground: readVar("--ut-warn") },
      { token: "number.float", foreground: readVar("--ut-warn") },
      { token: "timeframe", foreground: readVar("--ut-info") },
      { token: "identifier", foreground: readVar("--ut-fg") },
      { token: "operator", foreground: readVar("--ut-fg-muted") },
      { token: "delimiter", foreground: readVar("--ut-fg-muted") },
      { token: "delimiter.dot", foreground: readVar("--ut-fg-muted") },
      { token: "comment", foreground: readVar("--ut-fg-subtle"), fontStyle: "italic" },
    ],
    colors: {
      "editor.background": `#${readVar("--ut-bg-inset")}`,
      "editor.foreground": `#${readVar("--ut-fg")}`,
      "editorLineNumber.foreground": `#${readVar("--ut-fg-subtle")}`,
      "editorCursor.foreground": `#${readVar("--ut-accent")}`,
      "editor.selectionBackground": `#${readVar("--ut-info-subtle")}`,
      "editor.lineHighlightBackground": `#${readVar("--ut-bg-subtle")}`,
      "editorIndentGuide.background": `#${readVar("--ut-border")}`,
      "editorGutter.background": `#${readVar("--ut-bg-inset")}`,
    },
  });
}

/**
 * Reset registration state (used in tests to allow re-registration with a
 * fresh Monaco mock).
 */
export function resetRegistrationForTest(): void {
  _languageRegistered = false;
}
