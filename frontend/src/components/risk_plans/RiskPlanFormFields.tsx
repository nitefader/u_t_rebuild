import type { Dispatch, SetStateAction } from "react";
import { Select } from "@/components/ui/Select";
import { TextField } from "@/components/ui/TextField";
import type {
  RiskPlanSizingMethod,
  RiskPlanTier,
  WholeShareRounding,
} from "@/api/schemas/riskPlans";
import type { RiskPlanFormState } from "./riskPlanForm";

/**
 * RiskPlanFormFields — pure presentational component used by both the
 * Create/Edit drawer and the AI-draft preview. All ~30 fields per
 * RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §4.3 + §9.4.
 */
export interface RiskPlanFormFieldsProps {
  form: RiskPlanFormState;
  setForm: Dispatch<SetStateAction<RiskPlanFormState>>;
  /** Per-field error messages keyed on field name. */
  errors?: Record<string, string>;
}

export function RiskPlanFormFields({
  form,
  setForm,
  errors = {},
}: RiskPlanFormFieldsProps): JSX.Element {
  function set<K extends keyof RiskPlanFormState>(key: K, value: RiskPlanFormState[K]): void {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <div className="space-y-5">
      <Section title="Identity">
        <TextField
          label="Name *"
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
          placeholder="Balanced Momentum Risk"
          hint={errors.name}
        />
        <TextField
          label="Description"
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
          placeholder="What this Risk Plan is for, in one line."
        />
        <div className="grid grid-cols-2 gap-3">
          <TextField
            type="number"
            label="Risk score (0..10)"
            min={0}
            max={10}
            step={0.5}
            value={String(form.risk_score)}
            onChange={(e) => set("risk_score", Number(e.target.value))}
            hint={errors.risk_score}
          />
          <Select
            label="Risk tier"
            value={form.risk_tier}
            onChange={(e) => set("risk_tier", e.target.value as RiskPlanTier)}
            hint={errors.risk_tier}
          >
            <option value="conservative">conservative</option>
            <option value="balanced">balanced</option>
            <option value="aggressive">aggressive</option>
            <option value="custom">custom</option>
          </Select>
        </div>
      </Section>

      <Section title="Sizing">
        <Select
          label="Sizing method"
          value={form.sizing_method}
          onChange={(e) => set("sizing_method", e.target.value as RiskPlanSizingMethod)}
        >
          <option value="risk_percent">risk_percent</option>
          <option value="fixed_shares">fixed_shares</option>
          <option value="fixed_notional">fixed_notional</option>
          <option value="account_percent">account_percent</option>
          <option value="volatility_adjusted">volatility_adjusted</option>
          <option value="custom">custom</option>
        </Select>
        <div className="grid grid-cols-2 gap-3">
          <TextField
            type="number"
            label="Risk per trade (%)"
            value={form.risk_per_trade_pct}
            onChange={(e) => set("risk_per_trade_pct", e.target.value)}
            hint={errors.risk_per_trade_pct ?? "Used by risk_percent sizing."}
          />
          <TextField
            type="number"
            label="Account allocation (%)"
            value={form.account_allocation_pct}
            onChange={(e) => set("account_allocation_pct", e.target.value)}
            hint={errors.account_allocation_pct ?? "Used by account_percent sizing."}
          />
          <TextField
            type="number"
            label="Fixed shares"
            value={form.fixed_shares}
            onChange={(e) => set("fixed_shares", e.target.value)}
            hint={errors.fixed_shares ?? "Used by fixed_shares sizing."}
          />
          <TextField
            type="number"
            label="Fixed notional ($)"
            value={form.fixed_notional}
            onChange={(e) => set("fixed_notional", e.target.value)}
            hint={errors.fixed_notional ?? "Used by fixed_notional sizing."}
          />
          <TextField
            type="number"
            label="Min trade notional ($)"
            value={form.min_trade_notional}
            onChange={(e) => set("min_trade_notional", e.target.value)}
          />
          <TextField
            type="number"
            label="Max trade notional ($)"
            value={form.max_trade_notional}
            onChange={(e) => set("max_trade_notional", e.target.value)}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Select
            label="Fractional quantity"
            value={form.fractional_quantity_allowed ? "yes" : "no"}
            onChange={(e) => set("fractional_quantity_allowed", e.target.value === "yes")}
          >
            <option value="no">disallowed</option>
            <option value="yes">allowed</option>
          </Select>
          <Select
            label="Whole-share rounding"
            value={form.whole_share_rounding}
            onChange={(e) => set("whole_share_rounding", e.target.value as WholeShareRounding)}
            hint={errors.whole_share_rounding}
          >
            <option value="floor">floor</option>
            <option value="round">round</option>
            <option value="ceil">ceil</option>
          </Select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <TextField
            type="number"
            label="Min quantity"
            value={form.min_quantity}
            onChange={(e) => set("min_quantity", e.target.value)}
          />
          <TextField
            type="number"
            label="Max quantity"
            value={form.max_quantity}
            onChange={(e) => set("max_quantity", e.target.value)}
          />
        </div>
      </Section>

      <Section title="Exposure limits">
        <div className="grid grid-cols-2 gap-3">
          <TextField
            type="number"
            label="Max position notional ($)"
            value={form.max_position_notional}
            onChange={(e) => set("max_position_notional", e.target.value)}
          />
          <TextField
            type="number"
            label="Max position (% of equity)"
            value={form.max_position_pct_of_equity}
            onChange={(e) => set("max_position_pct_of_equity", e.target.value)}
            hint={errors.max_position_pct_of_equity}
          />
          <TextField
            type="number"
            label="Max symbol exposure (%)"
            value={form.max_symbol_exposure_pct}
            onChange={(e) => set("max_symbol_exposure_pct", e.target.value)}
          />
          <TextField
            type="number"
            label="Max sector exposure (%)"
            value={form.max_sector_exposure_pct}
            onChange={(e) => set("max_sector_exposure_pct", e.target.value)}
          />
          <TextField
            type="number"
            label="Max gross exposure (%)"
            value={form.max_gross_exposure_pct}
            onChange={(e) => set("max_gross_exposure_pct", e.target.value)}
            hint={errors.max_gross_exposure_pct}
          />
          <TextField
            type="number"
            label="Max net exposure (%)"
            value={form.max_net_exposure_pct}
            onChange={(e) => set("max_net_exposure_pct", e.target.value)}
          />
          <TextField
            type="number"
            label="Max open positions"
            value={form.max_open_positions}
            onChange={(e) => set("max_open_positions", e.target.value)}
          />
          <TextField
            type="number"
            label="Max open risk (%)"
            value={form.max_open_risk_pct}
            onChange={(e) => set("max_open_risk_pct", e.target.value)}
          />
        </div>
      </Section>

      <Section title="Loss limits">
        <div className="grid grid-cols-2 gap-3">
          <TextField
            type="number"
            label="Max daily loss (%)"
            value={form.max_daily_loss_pct}
            onChange={(e) => set("max_daily_loss_pct", e.target.value)}
            hint={errors.max_daily_loss_pct}
          />
          <TextField
            type="number"
            label="Max drawdown (%)"
            value={form.max_drawdown_pct}
            onChange={(e) => set("max_drawdown_pct", e.target.value)}
          />
          <TextField
            type="number"
            label="Max trades per day"
            value={form.max_trades_per_day}
            onChange={(e) => set("max_trades_per_day", e.target.value)}
          />
          <TextField
            type="number"
            label="Cooldown after loss (minutes)"
            value={form.cooldown_after_loss_minutes}
            onChange={(e) => set("cooldown_after_loss_minutes", e.target.value)}
          />
        </div>
      </Section>

      <Section title="Position rules">
        <div className="grid grid-cols-2 gap-3">
          <Toggle
            label="Stop required"
            checked={form.stop_required}
            onChange={(v) => set("stop_required", v)}
            hint={errors.stop_required}
          />
          <Toggle
            label="Reject if no stop"
            checked={form.reject_if_no_stop}
            onChange={(v) => set("reject_if_no_stop", v)}
          />
          <Toggle
            label="Target required"
            checked={form.target_required}
            onChange={(v) => set("target_required", v)}
          />
          <Toggle
            label="Runner allowed"
            checked={form.runner_allowed}
            onChange={(v) => set("runner_allowed", v)}
          />
          <Toggle
            label="Allow scale-in"
            checked={form.allow_scale_in}
            onChange={(v) => set("allow_scale_in", v)}
          />
          <Toggle
            label="Allow scale-out"
            checked={form.allow_scale_out}
            onChange={(v) => set("allow_scale_out", v)}
          />
          <Toggle
            label="Allow short"
            checked={form.allow_short}
            onChange={(v) => set("allow_short", v)}
          />
          <Toggle
            label="Allow extended hours"
            checked={form.allow_extended_hours}
            onChange={(v) => set("allow_extended_hours", v)}
          />
        </div>
        <TextField
          label="Default stop policy"
          value={form.default_stop_policy}
          onChange={(e) => set("default_stop_policy", e.target.value)}
          placeholder="e.g. atr_2x · prior_swing_low · fixed_pct_3"
        />
      </Section>

      <Section title="Restrictions">
        <TextField
          label="Symbol restrictions (comma-separated)"
          value={form.symbol_restrictions}
          onChange={(e) => set("symbol_restrictions", e.target.value)}
          placeholder="e.g. SPY, QQQ"
        />
        <TextField
          label="Asset class restrictions (comma-separated)"
          value={form.asset_class_restrictions}
          onChange={(e) => set("asset_class_restrictions", e.target.value)}
          placeholder="e.g. equity, etf"
        />
        <TextField
          label="Account mode restrictions (comma-separated)"
          value={form.account_mode_restrictions}
          onChange={(e) => set("account_mode_restrictions", e.target.value)}
          placeholder="e.g. paper, live"
        />
      </Section>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <fieldset className="space-y-2 rounded border border-border/60 bg-bg-subtle/50 p-3">
      <legend className="px-1 text-[11px] font-semibold uppercase tracking-wider text-fg-subtle">
        {title}
      </legend>
      {children}
    </fieldset>
  );
}

function Toggle({
  label,
  checked,
  onChange,
  hint,
}: {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  hint?: string;
}): JSX.Element {
  return (
    <label className="flex cursor-pointer items-start gap-2 rounded border border-border bg-bg-inset px-2 py-1.5 text-xs">
      <input
        type="checkbox"
        className="mt-0.5"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <div className="min-w-0 flex-1">
        <span className="text-fg">{label}</span>
        {hint ? <span className="mt-0.5 block text-[10px] text-danger">{hint}</span> : null}
      </div>
    </label>
  );
}
