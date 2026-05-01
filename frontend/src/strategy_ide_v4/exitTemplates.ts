/**
 * exitTemplates — registry of logical exit block templates.
 * Each template defines id, label, description, and param specs.
 * Frontend stores template_id + params; runtime mapping to SignalPlan.intent=logical_exit
 * happens in Slice 11.
 */

export type ExitTemplateId = "no_progress" | "opposite_cross" | "session_end" | "bars_since";

export type ExitTemplateParamSpec = {
  name: string;
  type: "number" | "string" | "boolean";
  default: number | string | boolean;
  label: string;
  min?: number;
  max?: number;
};

export type ExitTemplate = {
  id: ExitTemplateId;
  label: string;
  description: string;
  params: ExitTemplateParamSpec[];
};

export const EXIT_TEMPLATES: readonly ExitTemplate[] = [
  {
    id: "no_progress",
    label: "No-progress timeout",
    description:
      "Exit if the trade has not made meaningful progress toward target within a bar window.",
    params: [
      {
        name: "bars",
        type: "number",
        default: 10,
        label: "Bars window",
        min: 1,
      },
      {
        name: "threshold_r",
        type: "number",
        default: 0.25,
        label: "Progress threshold (R)",
        min: 0,
      },
    ],
  },
  {
    id: "opposite_cross",
    label: "Opposite EMA cross",
    description:
      "Exit when a bearish/bullish EMA crossover occurs on the opposite side of the entry direction.",
    params: [],
  },
  {
    id: "session_end",
    label: "Force flat at close",
    description: "Exit all positions a fixed number of minutes before market close.",
    params: [
      {
        name: "minutes_before_close",
        type: "number",
        default: 5,
        label: "Minutes before close",
        min: 0,
        max: 120,
      },
    ],
  },
  {
    id: "bars_since",
    label: "Exit after N bars",
    description: "Exit a fixed number of bars after a reference event.",
    params: [
      {
        name: "event",
        type: "string",
        default: "entry",
        label: "Since event",
      },
      {
        name: "bars",
        type: "number",
        default: 20,
        label: "Bar count",
        min: 1,
      },
    ],
  },
] as const;

const TEMPLATE_MAP: Map<ExitTemplateId, ExitTemplate> = new Map(
  EXIT_TEMPLATES.map((t) => [t.id, t]),
);

/** Returns the template for the given id. Throws if the id is unknown. */
export function getExitTemplate(id: ExitTemplateId): ExitTemplate {
  const tpl = TEMPLATE_MAP.get(id);
  if (!tpl) throw new Error(`Unknown exit template id: "${id}"`);
  return tpl;
}

/** Returns a fresh params dict populated with each param's default value. */
export function defaultParamsFor(id: ExitTemplateId): Record<string, number | string | boolean> {
  const tpl = getExitTemplate(id);
  const result: Record<string, number | string | boolean> = {};
  for (const spec of tpl.params) {
    result[spec.name] = spec.default;
  }
  return result;
}
