import { describe, expect, it } from "vitest";
import {
  STARTER_TEMPLATES,
  deferredTemplates,
  findTemplateById,
  readyTemplates,
} from "./templates";
import { AIComposerRequestSchema, WizardIntentSchema } from "@/api/schemas/strategyComposer";

const ALLOWED_HORIZONS = ["scalping", "intraday", "swing", "position"] as const;
const ALLOWED_DIRECTIONS = ["long", "short", "both"] as const;
const ALLOWED_REGIMES = [
  "ranging",
  "trending",
  "high_vol",
  "regime_agnostic",
] as const;
const ALLOWED_HOLD_TIMES = ["minutes", "hours", "days", "weeks"] as const;

describe("Starter template catalog", () => {
  it("ships exactly 12 templates", () => {
    expect(STARTER_TEMPLATES).toHaveLength(12);
  });

  it("partitions into 9 ready + 3 deferred", () => {
    expect(readyTemplates()).toHaveLength(9);
    expect(deferredTemplates()).toHaveLength(3);
  });

  it("each template has all required qualitative-provenance fields", () => {
    for (const t of STARTER_TEMPLATES) {
      expect(t.id).toMatch(/^[a-z][a-z0-9-]+$/);
      expect(t.display_name.length).toBeGreaterThan(0);
      expect(t.short_description.length).toBeGreaterThan(0);
      expect(t.long_description.length).toBeGreaterThan(0);
      expect(ALLOWED_HORIZONS).toContain(t.intended_horizon);
      expect(ALLOWED_DIRECTIONS).toContain(t.default_direction);
      expect(t.default_base_timeframe).toMatch(/^\d+(m|h|d|w|mo)$/);
      expect(ALLOWED_REGIMES).toContain(t.regime_assumption);
      expect(ALLOWED_HOLD_TIMES).toContain(t.expected_hold_time);
      expect(t.known_behavior.length).toBeGreaterThan(0);
      expect(t.caveats.length).toBeGreaterThan(0);
      expect(typeof t.indicative_only_disclaimer).toBe("boolean");
      expect(t.required_feature_families.length).toBeGreaterThan(0);
      expect(t.feature_seeds.length).toBeGreaterThan(0);
      expect(t.prompt_seed.length).toBeGreaterThan(0);
      expect(t.entry_logic_plain_english.length).toBeGreaterThan(0);
      expect(t.stop_logic_plain_english.length).toBeGreaterThan(0);
      expect(t.target_logic_plain_english.length).toBeGreaterThan(0);
      expect(t.logical_exit_logic_plain_english.length).toBeGreaterThan(0);
      expect(t.intent_keywords.length).toBeGreaterThan(0);
    }
  });

  it("indicative_only_disclaimer is true everywhere (no quantitative provenance in this slice)", () => {
    for (const t of STARTER_TEMPLATES) {
      expect(t.indicative_only_disclaimer).toBe(true);
    }
  });

  it("ids are unique", () => {
    const ids = STARTER_TEMPLATES.map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("wizard_intent_seed.base_timeframe matches default_base_timeframe", () => {
    for (const t of STARTER_TEMPLATES) {
      expect(t.wizard_intent_seed.base_timeframe).toBe(t.default_base_timeframe);
    }
  });

  it("wizard_intent_seed.direction matches default_direction", () => {
    for (const t of STARTER_TEMPLATES) {
      expect(t.wizard_intent_seed.direction).toBe(t.default_direction);
    }
  });

  it("wizard_intent_seed.horizon matches intended_horizon", () => {
    for (const t of STARTER_TEMPLATES) {
      expect(t.wizard_intent_seed.horizon).toBe(t.intended_horizon);
    }
  });

  it("deferred templates have a non-null deferred_reason", () => {
    for (const t of deferredTemplates()) {
      expect(t.requires_session_execution).toBe(true);
      expect(t.deferred_reason).not.toBeNull();
      expect(t.deferred_reason).toMatch(/Slice 6a-ii/);
    }
  });

  it("ready templates have null deferred_reason", () => {
    for (const t of readyTemplates()) {
      expect(t.requires_session_execution).toBe(false);
      expect(t.deferred_reason).toBeNull();
    }
  });

  it("all 12 expected ids are present", () => {
    const expected = [
      "vwap-reclaim",
      "supertrend-trend-follow",
      "rsi-mean-reversion",
      "connors-rsi-2",
      "internal-bar-strength",
      "ichimoku-cloud-trend",
      "moving-average-pullback",
      "atr-breakout",
      "fvg-htf",
      "opening-range-breakout",
      "gap-and-go",
      "prior-day-high-low-breakout",
    ];
    for (const id of expected) {
      expect(findTemplateById(id)).not.toBeNull();
    }
  });

  it("findTemplateById returns null for unknown id", () => {
    expect(findTemplateById("nonexistent-template")).toBeNull();
  });

  it("Connors RSI-2 carries the expected qualitative provenance", () => {
    const t = findTemplateById("connors-rsi-2")!;
    expect(t.intended_horizon).toBe("swing");
    expect(t.default_direction).toBe("long");
    expect(t.default_base_timeframe).toBe("1d");
    expect(t.regime_assumption).toBe("ranging");
    expect(t.expected_hold_time).toBe("days");
    expect(t.intent_keywords).toContain("connors");
    expect(t.intent_keywords).toContain("RSI");
  });

  it("FVG + HTF wizard seed sets higher_timeframe_confirmation = true", () => {
    const t = findTemplateById("fvg-htf")!;
    expect(t.wizard_intent_seed.higher_timeframe_confirmation).toBe(true);
  });

  it("Ichimoku template caveats name the senkou displacement limitation", () => {
    const t = findTemplateById("ichimoku-cloud-trend")!;
    expect(t.caveats.toLowerCase()).toContain("displacement");
  });

  it("Connors RSI-2 required_feature_families does not include ROC (not seeded)", () => {
    const t = findTemplateById("connors-rsi-2")!;
    expect(t.required_feature_families).not.toContain("ROC");
    // ROC is not in feature_seeds — families must reflect seeds only
    expect(t.feature_seeds.some((s) => s.includes(".roc"))).toBe(false);
  });

  it("VWAP Reclaim required_feature_families does not include session-low (SESSION feature, not seeded)", () => {
    const t = findTemplateById("vwap-reclaim")!;
    expect(t.required_feature_families).not.toContain("session-low");
    // template is READY (not deferred); no SESSION-scope seeds
    expect(t.requires_session_execution).toBe(false);
    expect(t.feature_seeds.some((s) => s.includes("session_low"))).toBe(false);
  });

  it("feature_seeds grammar: every seed matches {tf}.{kind}[:{params}][[{lookback}]]", () => {
    const SEED_RE = /^[A-Za-z0-9]+\.[a-z][a-z0-9_]*(?::[a-z][a-z0-9_]*=[^,\[\]:]+(?:,[a-z][a-z0-9_]*=[^,\[\]:]+)*)?(?:\[\d+\])?$/;
    for (const t of STARTER_TEMPLATES) {
      for (const seed of t.feature_seeds) {
        expect(seed, `template "${t.id}" seed "${seed}"`).toMatch(SEED_RE);
      }
    }
  });

  it("every intent_keywords list has at least 2 entries (sufficient intent-extraction surface)", () => {
    for (const t of STARTER_TEMPLATES) {
      expect(t.intent_keywords.length, `template "${t.id}" intent_keywords`).toBeGreaterThanOrEqual(2);
    }
  });
});

// ── Seeding contract: AIComposerRequest round-trip (R3 + R5) ──────────────────

function buildComposerRequest(templateId: string) {
  const t = findTemplateById(templateId);
  if (!t) throw new Error(`template not found: ${templateId}`);
  return {
    prompt: t.prompt_seed,
    timeframe: t.default_base_timeframe,
    initial_capital: 100_000,
    feature_refs: t.feature_seeds,
    execution_style_preset: "market_entry_market_exit" as const,
    wizard_intent: t.wizard_intent_seed,
  };
}

describe("AIComposerRequest seeding contract — 9 ready templates (R5)", () => {
  const READY_IDS = [
    "vwap-reclaim",
    "supertrend-trend-follow",
    "rsi-mean-reversion",
    "connors-rsi-2",
    "internal-bar-strength",
    "ichimoku-cloud-trend",
    "moving-average-pullback",
    "atr-breakout",
    "fvg-htf",
  ] as const;

  for (const id of READY_IDS) {
    it(`${id}: AIComposerRequestSchema.parse succeeds on seed payload`, () => {
      const req = buildComposerRequest(id);
      expect(() => AIComposerRequestSchema.parse(req)).not.toThrow();
    });

    it(`${id}: parsed wizard_intent.direction matches template default (R3)`, () => {
      const t = findTemplateById(id)!;
      const req = AIComposerRequestSchema.parse(buildComposerRequest(id));
      expect(req.wizard_intent?.direction).toBe(t.default_direction);
    });

    it(`${id}: parsed wizard_intent.horizon matches template intended_horizon (R3)`, () => {
      const t = findTemplateById(id)!;
      const req = AIComposerRequestSchema.parse(buildComposerRequest(id));
      expect(req.wizard_intent?.horizon).toBe(t.intended_horizon);
    });

    it(`${id}: parsed wizard_intent.base_timeframe matches template default (R3)`, () => {
      const t = findTemplateById(id)!;
      const req = AIComposerRequestSchema.parse(buildComposerRequest(id));
      expect(req.wizard_intent?.base_timeframe).toBe(t.default_base_timeframe);
    });

    it(`${id}: wizard_intent_seed round-trips through WizardIntentSchema`, () => {
      const t = findTemplateById(id)!;
      expect(() => WizardIntentSchema.parse(t.wizard_intent_seed)).not.toThrow();
      const parsed = WizardIntentSchema.parse(t.wizard_intent_seed);
      expect(parsed.direction).toBe(t.default_direction);
      expect(parsed.horizon).toBe(t.intended_horizon);
      expect(parsed.base_timeframe).toBe(t.default_base_timeframe);
    });
  }
});

describe("AIComposerRequest seeding contract — 3 deferred SESSION templates (R5)", () => {
  const DEFERRED_IDS = [
    "opening-range-breakout",
    "gap-and-go",
    "prior-day-high-low-breakout",
  ] as const;

  for (const id of DEFERRED_IDS) {
    it(`${id}: AIComposerRequestSchema.parse succeeds on seed shape (ready for 6a-ii)`, () => {
      // Deferred templates have a valid seed shape — schema parse must pass.
      // No Generate call is exercised here.
      const req = buildComposerRequest(id);
      expect(() => AIComposerRequestSchema.parse(req)).not.toThrow();
    });

    it(`${id}: requires_session_execution = true and deferred_reason references Slice 6a-ii`, () => {
      const t = findTemplateById(id)!;
      expect(t.requires_session_execution).toBe(true);
      expect(t.deferred_reason).toMatch(/Slice 6a-ii/);
    });

    it(`${id}: wizard_intent_seed round-trips through WizardIntentSchema`, () => {
      const t = findTemplateById(id)!;
      expect(() => WizardIntentSchema.parse(t.wizard_intent_seed)).not.toThrow();
    });
  }
});
