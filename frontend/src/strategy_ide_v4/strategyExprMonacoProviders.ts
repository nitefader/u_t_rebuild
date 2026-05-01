/**
 * Single global registration of strategy-expr completion + hover for Monaco.
 *
 * Monaco merges suggestions from every `registerCompletionItemProvider` for a
 * language; multiple `MonacoExpressionEditor` instances would duplicate the
 * entire catalog. Register once per page lifetime.
 */

import type * as Monaco from "monaco-editor";
import { listExpressionFeatures } from "@/api/strategiesV4";
import type { CatalogEntry } from "@/api/strategiesV4";
import { STRATEGY_EXPR_KEYWORDS } from "./strategyExprLanguage";

export const STRATEGY_EXPR_VALIDATION_MARKER_OWNER = "strategy-expr-validator";

/** Shared catalog for completion + hover (warmed from API). */
let featureCatalogCache: CatalogEntry[] | null = null;

let completionDisposable: Monaco.IDisposable | null = null;
let hoverDisposable: Monaco.IDisposable | null = null;
let providersRegistered = false;

/** Test-only: allow a second registration in the same JS realm. */
export function __resetStrategyExprMonacoProvidersForTests(): void {
  providersRegistered = false;
  featureCatalogCache = null;
  completionDisposable?.dispose();
  hoverDisposable?.dispose();
  completionDisposable = null;
  hoverDisposable = null;
}

export function getStrategyExprFeatureCatalog(): CatalogEntry[] {
  return featureCatalogCache ?? [];
}

/** Warm the catalog once; safe to call from every editor mount. */
export function warmStrategyExprFeatureCatalog(): void {
  if (featureCatalogCache) return;
  void listExpressionFeatures()
    .then((features) => {
      featureCatalogCache = features;
    })
    .catch(() => {
      /* optional — completion will retry on demand */
    });
}

/** monaco.languages.CompletionItemKind — stable without full ESM enums in tests */
const CMP_KIND_FUNCTION = 1;
const CMP_KIND_VARIABLE = 4;
const CMP_KIND_KEYWORD = 17;
const CMP_INSERT_AS_SNIPPET = 4;

const CATEGORY_RANK: Record<string, string> = {
  trend: "0",
  momentum: "1",
  volatility: "2",
  volume: "3",
  bb: "4",
  time: "5",
  bar: "6",
  other: "7",
};

const CATEGORY_EXAMPLES: Record<string, string> = {
  trend: "5m.ema(20) > 5m.ema(50)",
  momentum: "5m.rsi(14) < 30",
  volatility: "5m.atr(14) > 0.5",
  volume: "5m.volume > 5m.sma_volume(20)",
  bb: "5m.bb_width(20, 2) < 0.02",
  time: "session.is_open",
  bar: "bar.close > bar.open",
  other: "",
};

interface KeywordMeta {
  detail: string;
  documentation: string;
  snippet?: string;
}

const KEYWORD_META: Record<string, KeywordMeta> = {
  AND: {
    detail: "language keyword",
    documentation: "**AND** — boolean operator",
  },
  OR: {
    detail: "language keyword",
    documentation: "**OR** — boolean operator",
  },
  NOT: {
    detail: "language keyword",
    documentation: "**NOT** — boolean operator",
  },
  crosses_above: {
    detail: "special form",
    documentation:
      "**crosses_above** — true on the bar where a goes from ≤ b to > b.\n\nUsage: `5m.ema(9) crosses_above 5m.ema(20)`",
    snippet: "crosses_above(${1:a}, ${2:b})",
  },
  crosses_below: {
    detail: "special form",
    documentation:
      "**crosses_below** — true on the bar where a goes from ≥ b to < b.\n\nUsage: `5m.ema(9) crosses_below 5m.ema(20)`",
    snippet: "crosses_below(${1:a}, ${2:b})",
  },
  within: {
    detail: "special form",
    documentation:
      "**within** — true when value is within [low, high].\n\nUsage: `within(5m.rsi(14), 30, 70)`",
    snippet: "within(${1:value}, ${2:low}, ${3:high})",
  },
  any_of: {
    detail: "special form",
    documentation:
      "**any_of** — true if any argument is true.\n\nUsage: `any_of(cond1, cond2, cond3)`",
    snippet: "any_of(${1:cond1}, ${2:cond2})",
  },
  all_of: {
    detail: "special form",
    documentation:
      "**all_of** — true if all arguments are true.\n\nUsage: `all_of(cond1, cond2, cond3)`",
    snippet: "all_of(${1:cond1}, ${2:cond2})",
  },
};

function inferArgType(defaultVal: unknown, returnType: string): string {
  if (typeof defaultVal === "number") {
    return Number.isInteger(defaultVal) ? "int" : "float";
  }
  if (returnType === "bool" || returnType === "boolean") return "bool";
  return "float";
}

function buildArgsSignatureSegments(entry: CatalogEntry): string[] {
  if (entry.arity <= 0) return [];
  return entry.arg_names.map((arg, i) => {
    const def = entry.arg_defaults[i];
    const ty = inferArgType(def, entry.return_type);
    if (def !== undefined && def !== null) {
      return `${arg}: ${ty} = ${String(def)}`;
    }
    return `${arg}: ${ty}`;
  });
}

function buildCategorySuffix(entry: CatalogEntry): string {
  const parts: string[] = [];
  if (entry.timeframe_bound) parts.push("timeframed");
  parts.push(entry.category);
  return parts.join(", ");
}

function buildOneLineDetail(entry: CatalogEntry): string {
  const args = buildArgsSignatureSegments(entry);
  const head = args.length > 0 ? `${entry.name}(${args.join(", ")})` : entry.name;
  const suffix = buildCategorySuffix(entry);
  return `${head} → ${entry.return_type} (${suffix})`;
}

function buildHoverMarkdown(name: string, catalog: CatalogEntry[]): string | null {
  const kwMeta = KEYWORD_META[name];
  if (kwMeta) {
    return kwMeta.documentation;
  }

  const entry = catalog.find((f) => f.name === name);
  if (!entry) return null;

  const segments = buildArgsSignatureSegments(entry);
  const sigHead = segments.length > 0 ? `${entry.name}(${segments.join(", ")})` : entry.name;

  const signature = `${sigHead} → ${entry.return_type}`;

  const tfNote = entry.timeframe_bound ? " *(timeframed)*" : "";
  const example =
    entry.category !== "other" ? CATEGORY_EXAMPLES[entry.category] : entry.description;

  const lines: string[] = [
    `**${entry.name}**${tfNote} — ${entry.description}`,
    "",
    `\`\`\`\n${signature}\n\`\`\``,
  ];

  if (example && example !== entry.description) {
    lines.push("", `**Example:** \`${example}\``);
  }

  lines.push("", `_Category: ${entry.category}_`);

  return lines.join("\n");
}

function buildInsertText(entry: CatalogEntry, textBefore: string): string {
  const charBeforeWord = textBefore.length > 0 ? textBefore[textBefore.length - 1] : "";
  const isDotAccess = charBeforeWord === ".";

  if (entry.arity === 0) {
    if (entry.timeframe_bound && !isDotAccess) {
      return `5m.${entry.name}`;
    }
    return entry.name;
  }

  const params = entry.arg_names
    .map((arg, i) => {
      const def = entry.arg_defaults[i];
      return def !== undefined && def !== null
        ? `\${${i + 1}:${String(def)}}`
        : `\${${i + 1}:${arg}}`;
    })
    .join(", ");

  if (entry.timeframe_bound && !isDotAccess) {
    return `5m.${entry.name}(${params})`;
  }
  return `${entry.name}(${params})`;
}

function markerCoversPosition(
  m: Monaco.editor.IMarker,
  lineNumber: number,
  column: number,
): boolean {
  if (lineNumber < m.startLineNumber || lineNumber > m.endLineNumber) return false;
  if (lineNumber === m.startLineNumber && column < m.startColumn) return false;
  if (lineNumber === m.endLineNumber && column > m.endColumn) return false;
  return true;
}

export function ensureStrategyExprMonacoProviders(monaco: typeof Monaco): void {
  if (providersRegistered) return;
  providersRegistered = true;

  warmStrategyExprFeatureCatalog();

  completionDisposable = monaco.languages.registerCompletionItemProvider("strategy-expr", {
    triggerCharacters: ["."],
    provideCompletionItems: async (
      model: Monaco.editor.ITextModel,
      position: Monaco.Position,
    ): Promise<Monaco.languages.CompletionList> => {
      let features = featureCatalogCache;
      if (!features) {
        try {
          features = await listExpressionFeatures();
          featureCatalogCache = features;
        } catch {
          return { suggestions: [] };
        }
      }

      const word = model.getWordUntilPosition(position);
      const range: Monaco.IRange = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn,
      };

      const textBefore = model.getValueInRange({
        startLineNumber: position.lineNumber,
        startColumn: 1,
        endLineNumber: position.lineNumber,
        endColumn: word.startColumn,
      });

      const featureSuggestions: Monaco.languages.CompletionItem[] = features.map((entry) => {
        const rank = CATEGORY_RANK[entry.category] ?? "7";
        const kindNum = entry.arity === 0 ? CMP_KIND_VARIABLE : CMP_KIND_FUNCTION;

        const tfNote = entry.timeframe_bound ? " (timeframed)" : "";
        const nsLabel = entry.namespace ? `  ${entry.namespace}` : "";
        const labelDetail = entry.timeframe_bound ? `  (timeframed)${nsLabel}` : nsLabel;

        const docLines: string[] = [
          `**${entry.name}**${tfNote} — ${entry.description}`,
        ];
        const example = entry.category !== "other" ? CATEGORY_EXAMPLES[entry.category] : "";
        if (example) {
          docLines.push("", `**Example:** \`${example}\``);
        }
        docLines.push("", `_Category: ${entry.category}_`);

        const itemLabel: Monaco.languages.CompletionItemLabel = {
          label: entry.name,
          detail: labelDetail,
          description: entry.return_type,
        };

        return {
          label: itemLabel,
          kind: kindNum,
          insertText: buildInsertText(entry, textBefore),
          insertTextRules: CMP_INSERT_AS_SNIPPET,
          detail: buildOneLineDetail(entry),
          documentation: { value: docLines.join("\n") },
          sortText: `${rank}_${entry.name}`,
          range,
        };
      });

      const keywordSuggestions: Monaco.languages.CompletionItem[] = STRATEGY_EXPR_KEYWORDS.map(
        (kw) => {
          const meta = KEYWORD_META[kw];
          const hasSnippet = Boolean(meta?.snippet);
          return {
            label: kw,
            kind: CMP_KIND_KEYWORD,
            insertText: hasSnippet ? (meta?.snippet ?? kw) : kw,
            insertTextRules: hasSnippet ? CMP_INSERT_AS_SNIPPET : undefined,
            detail: meta?.detail ?? "language keyword",
            documentation: meta?.documentation
              ? { value: meta.documentation }
              : { value: kw },
            sortText: `8_${kw}`,
            range,
          };
        },
      );

      return { suggestions: [...featureSuggestions, ...keywordSuggestions] };
    },
  });

  hoverDisposable = monaco.languages.registerHoverProvider("strategy-expr", {
    provideHover(
      model: Monaco.editor.ITextModel,
      position: Monaco.Position,
    ): Monaco.languages.Hover | null {
      const uri = model.uri;
      const allMarkers = monaco.editor.getModelMarkers({ resource: uri });
      const hit = [...allMarkers]
        .reverse()
        .find(
          (m) =>
            m.owner === STRATEGY_EXPR_VALIDATION_MARKER_OWNER &&
            m.message &&
            (m.severity === monaco.MarkerSeverity.Error ||
              m.severity === monaco.MarkerSeverity.Warning) &&
            markerCoversPosition(m, position.lineNumber, position.column),
        );
      if (hit) {
        const label = hit.severity === monaco.MarkerSeverity.Warning ? "Warning" : "Error";
        return {
          contents: [{ value: `**${label}**\n\n${hit.message}` }],
          range: {
            startLineNumber: hit.startLineNumber,
            endLineNumber: hit.endLineNumber,
            startColumn: hit.startColumn,
            endColumn: hit.endColumn,
          },
        };
      }

      const word = model.getWordAtPosition(position);
      if (!word) return null;

      const name = word.word;
      const catalog = featureCatalogCache ?? [];
      const md = buildHoverMarkdown(name, catalog);
      if (!md) return null;

      return {
        contents: [{ value: md }],
        range: {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endColumn: word.endColumn,
        },
      };
    },
  });
}
