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
 * Slice 6c surfaces the fields that already exist in the typed
 * `StrategyControlsVersionSchema`. Slice 6a-i extends the backend with
 * trading-window / no-new-entries-after / force-flat-by / cooldown /
 * max-trades-per-session / regime-filter; the frontend schema's
 * `.passthrough()` already accepts those, so when 6a-i lands the
 * fielded form below grows additively without churning the wire shape.
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

  return (
    <SectionCard
      id="section-strategy-controls"
      number={11}
      title="Strategy Controls"
      severity={sectionSeverity}
      subtitle="Decides when this strategy is allowed to produce SignalPlans. Not Governor and not Account Risk."
    >
      {warnings && warnings.length > 0 ? (
        <div className="mb-2 space-y-1">
          {warnings.filter((w) => !w.dismissed || w.severity === "error").map((w) => (
            <div key={w.id} className={cn("rounded px-2 py-1 text-[11px]", w.severity === "error" ? "text-danger bg-danger-subtle/30" : "text-warn bg-warn-subtle/30")}>
              {w.message}
            </div>
          ))}
        </div>
      ) : null}
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
        <Select
          label="Session preference"
          value={controls.session_preference}
          onChange={(e) => patch({ session_preference: e.target.value as SessionPreference })}
          data-testid="controls-session-preference"
        >
          <option value="regular_only">Regular session only</option>
          <option value="regular_and_extended">Regular + extended hours</option>
        </Select>
        <label className="flex items-center gap-2 self-end pb-1 text-xs">
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
      <p className="mt-3 text-[11px] text-fg-muted">
        Trading windows, force-flat-by, cooldown, max-trades-per-session, and regime filters
        ship in the next backend slice (Slice 6a-i extension) and surface here additively.
      </p>
    </SectionCard>
  );
}
