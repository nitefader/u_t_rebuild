import type {
  AllowedDirections,
  SessionPreference,
  StrategyControlsVersion,
  TradingHorizon,
} from "@/api/schemas/strategyComposer";
import { Banner } from "@/components/ui/Banner";
import { Select } from "@/components/ui/Select";
import { TextField } from "@/components/ui/TextField";
import { cn } from "@/lib/cn";
import type { CoherenceWarning } from "../coherenceValidator";
import { SectionCard } from "./SectionCard";
import type { SectionSeverity } from "./SectionCard";

/**
 * StrategyControlsSection (#11) — fielded form for the
 * StrategyControlsVersion that decides *when* a strategy is allowed to
 * produce SignalPlans.
 *
 * Doctrine guards (per `feedback_strategy_controls_first_class` and
 * Decision 9 of the plan):
 *   - Strategy Controls is first-class. Trading horizon, allowed
 *     directions, base timeframe, HTF confirmation, session preference,
 *     earnings/news blackout — all live here.
 *   - Strategy Controls is NOT Governor and NOT Account Risk.
 *     This section never edits buying power, sizing, broker restrictions,
 *     daily loss, or final approval — those belong to the runtime.
 *   - There is no `StrategyGovernor` concept. Use the canonical name
 *     `Strategy Controls`.
 *
 * Card layout:
 *   Card A — Timeframe & horizon
 *     name, trading_horizon, allowed_directions, timeframe,
 *     higher_timeframe_confirmation_required
 *   Card B — Session windows
 *     session_preference, earnings_news_blackout_enabled
 *   Card C — Cooldowns & caps
 *     cooldown_bars OR cooldown_minutes (mutually exclusive),
 *     max_trades_per_session, max_trades_per_day
 *
 * Cards for PDT & gap risk and the structured Regime filter remain on
 * the roadmap pending brand-new backend slices.
 */
export interface StrategyControlsSectionProps {
  controls: StrategyControlsVersion | null;
  onChange: (next: StrategyControlsVersion | null) => void;
  warnings?: CoherenceWarning[];
}

export function StrategyControlsSection(props: StrategyControlsSectionProps): JSX.Element {
  const { controls, onChange, warnings } = props;

  const sectionSeverity: SectionSeverity = warnings && warnings.some((w) => w.severity === "error")
    ? "error"
    : warnings && warnings.some((w) => w.severity === "warn" && !w.dismissed)
    ? "warn"
    : "ok";

  if (!controls) {
    return (
      <SectionCard
        id="section-strategy-controls"
        number={11}
        title="Strategy Controls"
        severity={sectionSeverity}
        subtitle="Decides when this strategy is allowed to produce SignalPlans. Not Governor and not Account Risk."
      >
        <Banner
          severity="warning"
          title="No Strategy Controls"
          message="The AI draft did not include Strategy Controls. Regenerate from Page 1 to seed them, or this strategy will save without controls and the runtime will reject it on deploy."
        />
      </SectionCard>
    );
  }

  function patch(next: Partial<StrategyControlsVersion>): void {
    onChange({ ...controls!, ...next });
  }

  // Warning rows render once at the top of the first card; both cards share
  // the same SignalPlan/StrategyControls target, so the panel rollup is
  // already correct without duplicating warnings per card.
  const warningRows =
    warnings && warnings.length > 0 ? (
      <div className="mb-2 space-y-1">
        {warnings.filter((w) => !w.dismissed || w.severity === "error").map((w) => (
          <div
            key={w.id}
            className={cn(
              "rounded px-2 py-1 text-[11px]",
              w.severity === "error"
                ? "text-danger bg-danger-subtle/30"
                : w.severity === "warn"
                ? "text-warn bg-warn-subtle/30"
                : "text-fg-muted bg-bg-inset",
            )}
          >
            {w.message}
          </div>
        ))}
      </div>
    ) : null;

  return (
    <div
      id="section-strategy-controls"
      data-testid="section-strategy-controls"
      className="flex flex-col gap-3"
    >
      <SectionCard
        id="section-strategy-controls-timeframe"
        number={11}
        title="Strategy Controls — Timeframe & horizon"
        severity={sectionSeverity}
        subtitle="When this strategy is allowed to produce SignalPlans (timeframe + horizon decisions)."
      >
        {warningRows}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <TextField
            label="Controls name"
            value={controls.name}
            onChange={(e) => patch({ name: e.target.value })}
            data-testid="controls-name"
          />
          <Select
            label="Trading horizon"
            value={controls.trading_horizon}
            onChange={(e) => patch({ trading_horizon: e.target.value as TradingHorizon })}
            data-testid="controls-horizon"
          >
            <option value="scalping">Scalping</option>
            <option value="intraday">Intraday</option>
            <option value="swing">Swing</option>
            <option value="position">Position</option>
          </Select>
          <Select
            label="Allowed directions"
            value={controls.allowed_directions}
            onChange={(e) => patch({ allowed_directions: e.target.value as AllowedDirections })}
            data-testid="controls-directions"
          >
            <option value="long">Long only</option>
            <option value="short">Short only</option>
            <option value="both">Both</option>
          </Select>
          <Select
            label="Base timeframe"
            value={controls.timeframe}
            onChange={(e) => patch({ timeframe: e.target.value })}
            data-testid="controls-timeframe"
          >
            <option value="1m">1 minute</option>
            <option value="5m">5 minutes</option>
            <option value="15m">15 minutes</option>
            <option value="30m">30 minutes</option>
            <option value="1h">1 hour</option>
            <option value="4h">4 hours</option>
            <option value="1d">1 day</option>
            <option value="1w">1 week</option>
          </Select>
          <label className="flex items-center gap-2 self-end pb-1 text-xs md:col-span-2">
            <input
              type="checkbox"
              checked={controls.higher_timeframe_confirmation_required}
              onChange={(e) =>
                patch({ higher_timeframe_confirmation_required: e.target.checked })
              }
              data-testid="controls-htf-required"
            />
            <span>Require higher-timeframe confirmation</span>
          </label>
        </div>
      </SectionCard>

      <SectionCard
        id="section-strategy-controls-session"
        number={11}
        title="Strategy Controls — Session windows"
        severity={sectionSeverity}
        subtitle="Which sessions and event windows the strategy is allowed to operate in."
      >
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <Select
            label="Session preference"
            value={controls.session_preference}
            onChange={(e) =>
              patch({ session_preference: e.target.value as SessionPreference })
            }
            data-testid="controls-session-preference"
          >
            <option value="regular_only">Regular session only</option>
            <option value="regular_and_extended">Regular + extended hours</option>
          </Select>
          <label className="flex items-center gap-2 self-end pb-1 text-xs">
            <input
              type="checkbox"
              checked={controls.earnings_news_blackout_enabled}
              onChange={(e) =>
                patch({ earnings_news_blackout_enabled: e.target.checked })
              }
              data-testid="controls-earnings-blackout"
            />
            <span>Earnings / news blackout</span>
          </label>
        </div>
      </SectionCard>

      <SectionCard
        id="section-strategy-controls-cooldowns"
        number={11}
        title="Strategy Controls — Cooldowns & caps"
        severity={sectionSeverity}
        subtitle="Throttle re-entries after a fill and cap how many trades this strategy can take per session or day."
      >
        <CooldownsAndCapsCard controls={controls} patch={patch} />
      </SectionCard>
    </div>
  );
}

interface CooldownsAndCapsCardProps {
  controls: StrategyControlsVersion;
  patch: (next: Partial<StrategyControlsVersion>) => void;
}

function CooldownsAndCapsCard({ controls, patch }: CooldownsAndCapsCardProps): JSX.Element {
  const bothCooldownsSet =
    controls.cooldown_bars != null && controls.cooldown_minutes != null;

  return (
    <div className="flex flex-col gap-3">
      {bothCooldownsSet ? (
        <Banner
          severity="warning"
          title="Pick one cooldown unit"
          message="Set either cooldown bars or cooldown minutes — not both. The save will be rejected until one is cleared."
        />
      ) : null}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <NullableIntField
          label="Cooldown — bars"
          hint="Minimum bars to wait after a fill before this strategy may signal again."
          min={0}
          value={controls.cooldown_bars ?? null}
          onChange={(next) => patch({ cooldown_bars: next })}
          data-testid="controls-cooldown-bars"
        />
        <NullableIntField
          label="Cooldown — minutes"
          hint="Minimum wall-clock minutes to wait after a fill. Use this on daily+ timeframes where bars are coarse."
          min={0}
          value={controls.cooldown_minutes ?? null}
          onChange={(next) => patch({ cooldown_minutes: next })}
          data-testid="controls-cooldown-minutes"
        />
        <NullableIntField
          label="Max trades per session"
          hint="Hard cap on entries during a single session. Empty = no cap."
          min={1}
          value={controls.max_trades_per_session ?? null}
          onChange={(next) => patch({ max_trades_per_session: next })}
          data-testid="controls-max-per-session"
        />
        <NullableIntField
          label="Max trades per day"
          hint="Hard cap across all sessions in a calendar day. Empty = no cap."
          min={1}
          value={controls.max_trades_per_day ?? null}
          onChange={(next) => patch({ max_trades_per_day: next })}
          data-testid="controls-max-per-day"
        />
      </div>
    </div>
  );
}

interface NullableIntFieldProps {
  label: string;
  hint?: string;
  min: number;
  value: number | null;
  onChange: (next: number | null) => void;
  "data-testid"?: string;
}

function NullableIntField({
  label,
  hint,
  min,
  value,
  onChange,
  ...rest
}: NullableIntFieldProps): JSX.Element {
  const raw = value == null ? "" : String(value);
  const invalid = value != null && (!Number.isInteger(value) || value < min);
  return (
    <TextField
      label={label}
      hint={hint}
      type="number"
      inputMode="numeric"
      min={min}
      step={1}
      value={raw}
      invalid={invalid}
      onChange={(e) => {
        const text = e.target.value.trim();
        if (text === "") {
          onChange(null);
          return;
        }
        const parsed = Number.parseInt(text, 10);
        if (Number.isNaN(parsed)) {
          onChange(null);
          return;
        }
        onChange(parsed);
      }}
      data-testid={rest["data-testid"]}
    />
  );
}
