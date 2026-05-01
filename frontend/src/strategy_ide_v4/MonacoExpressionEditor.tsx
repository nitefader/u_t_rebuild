/**
 * MonacoExpressionEditor — React wrapper around @monaco-editor/react.
 *
 * - Lazy-loads Monaco; shows a skeleton while loading.
 * - Registers the strategy-expr language + themes on mount; re-registers
 *   themes when the app theme changes so CSS-var colors stay fresh.
 * - Debounces validation 300ms; cancels in-flight requests on change.
 * - Surfaces backend errors/warnings as Monaco markers.
 * - Completion + hover for `strategy-expr` are registered once globally
 *   (`strategyExprMonacoProviders.ts`) so multiple editors do not duplicate
 *   IntelliSense rows.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import type * as Monaco from "monaco-editor";
import { registerStrategyExprLanguage } from "./strategyExprLanguage";
import { ensureStrategyExprMonacoProviders, STRATEGY_EXPR_VALIDATION_MARKER_OWNER } from "./strategyExprMonacoProviders";
import { validateExpressionAbortable } from "@/api/strategiesV4";
import type { ExpressionValidateResult } from "@/api/strategiesV4";
import { useAppShell } from "@/store/useAppShell";

export type { ExpressionValidateResult };

/** Clamp Monaco marker ranges to the current line length so hover + glyphs work reliably. */
function squiggleMarkersForModel(
  monaco: typeof Monaco,
  model: Monaco.editor.ITextModel,
  result: ExpressionValidateResult,
): Monaco.editor.IMarkerData[] {
  const lc = Math.max(1, model.getLineCount());
  const severityError = monaco.MarkerSeverity.Error;
  const severityWarn = monaco.MarkerSeverity.Warning;

  function one(
    severity: Monaco.MarkerSeverity,
    msg: string,
    lineRaw: number | null | undefined,
    colRaw: number | null | undefined,
  ): Monaco.editor.IMarkerData {
    const lineNum = Math.min(Math.max(lineRaw ?? 1, 1), lc);
    /** Exclusive end column (Monaco convention; empty line ⇒ 1). */
    const lineMaxExclusive = model.getLineMaxColumn(lineNum);

    let startColumn = 1;
    if (typeof colRaw === "number" && colRaw >= 1) {
      const lastUsableCol = Math.max(1, lineMaxExclusive - 1);
      startColumn = Math.min(Math.max(colRaw, 1), lastUsableCol);
    }

    let endColumnExclusive = lineMaxExclusive;
    if (typeof colRaw === "number" && colRaw >= 1) {
      endColumnExclusive = Math.min(Math.max(colRaw + 140, startColumn + 1), lineMaxExclusive);
    }
    if (endColumnExclusive <= startColumn) endColumnExclusive = Math.min(startColumn + 1, lineMaxExclusive + 1);

    return {
      severity,
      message: msg,
      startLineNumber: lineNum,
      startColumn,
      endLineNumber: lineNum,
      endColumn: endColumnExclusive,
    };
  }

  return [
    ...result.errors.map((e) => one(severityError, e.message, e.line, e.col)),
    ...result.warnings.map((w) => one(severityWarn, w.message, w.line, w.col)),
  ];
}

export interface MonacoExpressionEditorHandle {
  /** Insert text at the current cursor position using Monaco's executeEdits API. */
  insertAtCursor: (text: string) => void;
}

export interface MonacoExpressionEditorProps {
  value: string;
  onChange: (value: string) => void;
  variableNames?: string[];
  timeframeVariableNames?: string[];
  onValidationChange?: (result: ExpressionValidateResult) => void;
  height?: string;
  width?: string;
  readOnly?: boolean;
  editorHandleRef?: React.MutableRefObject<MonacoExpressionEditorHandle | null>;
}

function EditorSkeleton({ height }: { height: string }): JSX.Element {
  return (
    <div
      style={{ height, width: "100%" }}
      className="animate-pulse rounded bg-bg-inset border border-border"
      aria-label="Loading editor"
      role="progressbar"
    />
  );
}

type MonacoEditorType = typeof import("@monaco-editor/react").default;
type EditorInstance = Monaco.editor.IStandaloneCodeEditor;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MonacoExpressionEditor({
  value,
  onChange,
  variableNames = [],
  timeframeVariableNames = [],
  onValidationChange,
  height = "200px",
  width = "100%",
  readOnly = false,
  editorHandleRef,
}: MonacoExpressionEditorProps): JSX.Element {
  const { theme } = useAppShell();
  const [EditorComponent, setEditorComponent] = useState<MonacoEditorType | null>(null);
  const monacoRef = useRef<typeof Monaco | null>(null);
  const editorRef = useRef<EditorInstance | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Lazy-load @monaco-editor/react
  useEffect(() => {
    let cancelled = false;
    void import("@monaco-editor/react").then((mod) => {
      if (!cancelled) setEditorComponent(() => mod.default);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Re-register themes (with fresh CSS vars) and switch Monaco theme when
  // the app theme changes.
  useEffect(() => {
    const monaco = monacoRef.current;
    if (!monaco) return;
    // Re-define both themes so colors resolve from current CSS vars
    registerStrategyExprLanguage(monaco);
    const monacoTheme =
      theme === "light" ? "strategy-expr-light" : "strategy-expr-dark";
    monaco.editor.setTheme(monacoTheme);
  }, [theme]);

  const runValidation = useCallback(
    (text: string, exprVars: string[], tfVars: string[]) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (abortRef.current) abortRef.current.abort();

      debounceRef.current = setTimeout(() => {
        const controller = new AbortController();
        abortRef.current = controller;

        validateExpressionAbortable(text, exprVars, tfVars, controller.signal)
          .then((result) => {
            if (controller.signal.aborted) return;
            onValidationChange?.(result);

            // Surface Monaco markers
            const monaco = monacoRef.current;
            const editor = editorRef.current;
            if (!monaco || !editor) return;
            const model = editor.getModel();
            if (!model) return;

            const markers = squiggleMarkersForModel(monaco, model, result);
            monaco.editor.setModelMarkers(model, STRATEGY_EXPR_VALIDATION_MARKER_OWNER, markers);
          })
          .catch((err: unknown) => {
            if (err instanceof Error && err.name === "AbortError") return;
          });
      }, 300);
    },
    [onValidationChange],
  );

  // Re-run validation when referenced variables change
  useEffect(() => {
    if (value.trim()) runValidation(value, variableNames, timeframeVariableNames);
  }, [variableNames, timeframeVariableNames, value, runValidation]);

  function handleEditorDidMount(
    editor: EditorInstance,
    monaco: typeof Monaco,
  ): void {
    monacoRef.current = monaco;
    editorRef.current = editor;

    // Register language + themes (re-reads CSS vars for current theme)
    registerStrategyExprLanguage(monaco);

    // Apply the current app theme immediately
    const monacoTheme =
      theme === "light" ? "strategy-expr-light" : "strategy-expr-dark";
    monaco.editor.setTheme(monacoTheme);

    // Expose imperative insert handle
    if (editorHandleRef) {
      editorHandleRef.current = {
        insertAtCursor: (text: string) => {
          const position = editor.getPosition();
          if (!position) return;
          editor.executeEdits("palette", [
            {
              range: {
                startLineNumber: position.lineNumber,
                startColumn: position.column,
                endLineNumber: position.lineNumber,
                endColumn: position.column,
              },
              text,
            },
          ]);
          editor.focus();
        },
      };
    }

    ensureStrategyExprMonacoProviders(monaco);

    // Initial validation
    if (value.trim()) runValidation(value, variableNames, timeframeVariableNames);
  }

  function handleChange(val: string | undefined): void {
    const text = val ?? "";
    onChange(text);
    runValidation(text, variableNames, timeframeVariableNames);
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  const monacoTheme =
    theme === "light" ? "strategy-expr-light" : "strategy-expr-dark";

  if (!EditorComponent) {
    return <EditorSkeleton height={height} />;
  }

  return (
    <EditorComponent
      height={height}
      width={width}
      language="strategy-expr"
      theme={monacoTheme}
      value={value}
      options={{
        readOnly,
        minimap: { enabled: false },
        lineNumbers: "on",
        wordWrap: "on",
        scrollBeyondLastLine: false,
        fontSize: 13,
        tabSize: 2,
        automaticLayout: true,
        suggestOnTriggerCharacters: true,
        quickSuggestions: { other: true, comments: false, strings: false },
        parameterHints: { enabled: true },
        folding: false,
        overviewRulerLanes: 0,
        renderLineHighlight: "line",
      }}
      onMount={handleEditorDidMount}
      onChange={handleChange}
    />
  );
}
