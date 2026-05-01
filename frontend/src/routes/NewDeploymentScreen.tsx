/**
 * NewDeploymentScreen — 6-step focused-mode wizard for creating a v4
 * Deployment. Mounted outside AppShell at ROUTE_DEPLOYMENTS_NEW so the
 * operator has a clean canvas without the sidenav.
 *
 * Steps:
 *   1. Strategy   — pick a v4 strategy head
 *   2. Controls   — pick a Strategy Controls library or "use defaults"
 *   3. Execution  — pick an Execution Plan library or "use defaults"
 *   4. Watchlist  — pick one or more watchlists (required)
 *   5. Accounts   — pick one or more accounts (required)
 *   6. Horizon    — pick scalping/intraday/swing/position or none
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Check } from "lucide-react";
import { ApiError } from "@/api/client";
import { DeploymentsApi } from "@/api/deployments";
import { AccountsApi } from "@/api/accounts";
import { WatchlistsApi } from "@/api/watchlists";
import { StrategyControlsApi } from "@/api/strategyControls";
import { ExecutionPlansApi } from "@/api/executionPlans";
import { listAllHeads, type StrategyHeadSummary } from "@/api/strategiesV4";
import { TRADING_HORIZON_LABELS, type TradingHorizon } from "@/api/schemas/risk";
import { ROUTE_DEPLOYMENTS } from "@/strategy_ide_v4/routes";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/TextField";

const TOTAL_STEPS = 6;

const STEP_LABELS = [
  "Strategy",
  "Controls",
  "Execution Plan",
  "Watchlist",
  "Accounts",
  "Horizon",
] as const;

function StepRail({
  current,
  onJump,
  completedUpTo,
}: {
  current: number;
  onJump: (step: number) => void;
  completedUpTo: number;
}): JSX.Element {
  return (
    <nav className="flex flex-col gap-1 py-6 pr-6 text-sm" aria-label="Deployment wizard steps">
      {STEP_LABELS.map((label, i) => {
        const step = i + 1;
        const done = step <= completedUpTo;
        const active = step === current;
        return (
          <button
            key={label}
            type="button"
            onClick={() => {
              if (step <= completedUpTo + 1) onJump(step);
            }}
            disabled={step > completedUpTo + 1}
            className={[
              "flex items-center gap-2 rounded px-3 py-2 text-left transition-colors",
              active
                ? "bg-accent/20 font-semibold text-fg"
                : done
                  ? "text-fg-muted hover:bg-bg-raised"
                  : "cursor-not-allowed text-fg-subtle",
            ].join(" ")}
          >
            <span
              className={[
                "flex h-5 w-5 items-center justify-center rounded-full border text-[10px] font-bold",
                active
                  ? "border-accent bg-accent text-white"
                  : done
                    ? "border-ok bg-ok/10 text-ok"
                    : "border-border text-fg-subtle",
              ].join(" ")}
            >
              {done && !active ? <Check className="h-3 w-3" /> : step}
            </span>
            {label}
          </button>
        );
      })}
    </nav>
  );
}

function StepHeader({ step, label }: { step: number; label: string }): JSX.Element {
  return (
    <div className="mb-4">
      <div className="text-xs font-medium uppercase tracking-widest text-fg-muted">
        Step {step} of {TOTAL_STEPS}
      </div>
      <h2 className="mt-1 text-xl font-semibold">{label}</h2>
    </div>
  );
}

export function NewDeploymentScreen(): JSX.Element {
  const navigate = useNavigate();

  const [step, setStep] = useState(1);
  const [completedUpTo, setCompletedUpTo] = useState(0);

  // Step 1 — Strategy
  const [selectedStrategy, setSelectedStrategy] = useState<StrategyHeadSummary | null>(null);

  // Step 2 — Controls
  const [controlsId, setControlsId] = useState<string>("");

  // Step 3 — Execution Plan
  const [execPlanId, setExecPlanId] = useState<string>("");

  // Step 4 — Watchlists
  const [watchlistIds, setWatchlistIds] = useState<string[]>([]);

  // Step 5 — Accounts
  const [accountIds, setAccountIds] = useState<string[]>([]);

  // Step 6 — Horizon
  const [horizon, setHorizon] = useState<TradingHorizon | "">("");

  // Bottom fields
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const strategies = useQuery({
    queryKey: ["strategies-v4", "heads"],
    queryFn: listAllHeads,
    staleTime: 30_000,
  });
  const controlsList = useQuery({
    queryKey: ["strategy-controls", "list"],
    queryFn: () => StrategyControlsApi.list(),
    staleTime: 30_000,
  });
  const execPlansList = useQuery({
    queryKey: ["execution-plans", "list"],
    queryFn: () => ExecutionPlansApi.list(),
    staleTime: 30_000,
  });
  const watchlists = useQuery({
    queryKey: ["watchlists", "list"],
    queryFn: () => WatchlistsApi.list(),
    staleTime: 30_000,
  });
  const accounts = useQuery({
    queryKey: ["accounts", "list"],
    queryFn: () => AccountsApi.list(),
    staleTime: 30_000,
  });

  function advance(): void {
    const next = step + 1;
    setCompletedUpTo((prev) => Math.max(prev, step));
    setStep(next);
  }

  function retreat(): void {
    setStep((prev) => Math.max(1, prev - 1));
  }

  function stepIsValid(s: number): boolean {
    switch (s) {
      case 1:
        return selectedStrategy !== null;
      case 2:
        return true; // optional — "use defaults" is valid
      case 3:
        return true; // optional
      case 4:
        return watchlistIds.length > 0;
      case 5:
        return accountIds.length > 0;
      case 6:
        return true; // optional
      default:
        return false;
    }
  }

  const canCreate =
    name.trim().length > 0 &&
    selectedStrategy !== null &&
    watchlistIds.length > 0 &&
    accountIds.length > 0;

  const create = useMutation({
    mutationFn: () =>
      DeploymentsApi.create({
        name: name.trim(),
        description: description.trim() || null,
        strategy_version_id: undefined,
        strategy_version_v4_id: selectedStrategy?.head_version_id ?? "",
        strategy_controls_version_id: controlsId || undefined,
        execution_plan_version_id: execPlanId || undefined,
        watchlist_ids: watchlistIds,
        subscribed_account_ids: accountIds,
        runtime_overrides: {},
        risk_horizon: horizon !== "" ? horizon : null,
      }),
    onSuccess: () => {
      navigate(ROUTE_DEPLOYMENTS);
    },
    onError: (e) =>
      setSubmitError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  return (
    <div className="flex h-screen flex-col bg-bg">
      {/* Top bar */}
      <header className="flex items-center gap-3 border-b border-border px-6 py-3">
        <button
          type="button"
          onClick={() => navigate(ROUTE_DEPLOYMENTS)}
          className="flex items-center gap-1 rounded text-sm text-fg-muted hover:text-fg"
        >
          <ChevronLeft className="h-4 w-4" />
          Deployments
        </button>
        <span className="text-fg-subtle">/</span>
        <span className="text-sm font-medium">New Deployment</span>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* Left rail — step navigation */}
        <aside className="w-48 shrink-0 border-r border-border">
          <StepRail
            current={step}
            onJump={setStep}
            completedUpTo={completedUpTo}
          />
        </aside>

        {/* Right pane — step content */}
        <main className="flex min-w-0 flex-1 flex-col overflow-y-auto px-8 py-6">
          {step === 1 && (
            <Step1Strategy
              strategies={strategies.data ?? []}
              loading={strategies.isLoading}
              selected={selectedStrategy}
              onSelect={setSelectedStrategy}
            />
          )}
          {step === 2 && (
            <Step2Controls
              libraries={controlsList.data?.libraries ?? []}
              loading={controlsList.isLoading}
              selected={controlsId}
              onSelect={setControlsId}
            />
          )}
          {step === 3 && (
            <Step3ExecPlan
              libraries={execPlansList.data?.libraries ?? []}
              loading={execPlansList.isLoading}
              selected={execPlanId}
              onSelect={setExecPlanId}
            />
          )}
          {step === 4 && (
            <Step4Watchlists
              watchlists={watchlists.data?.watchlists ?? []}
              loading={watchlists.isLoading}
              selected={watchlistIds}
              onToggle={(id) =>
                setWatchlistIds((prev) =>
                  prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
                )
              }
            />
          )}
          {step === 5 && (
            <Step5Accounts
              accounts={accounts.data?.accounts ?? []}
              loading={accounts.isLoading}
              selected={accountIds}
              onToggle={(id) =>
                setAccountIds((prev) =>
                  prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
                )
              }
            />
          )}
          {step === 6 && (
            <Step6Horizon selected={horizon} onSelect={setHorizon} />
          )}

          {/* Bottom form */}
          {step === TOTAL_STEPS ? (
            <div className="mt-8 space-y-3 border-t border-border pt-6">
              <h3 className="text-sm font-semibold">Deployment name</h3>
              {submitError ? (
                <Banner severity="danger" title="Could not create" message={submitError} />
              ) : null}
              <TextField
                label="Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <TextField
                label="Description (optional)"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          ) : null}

          {/* Navigation buttons */}
          <div className="mt-8 flex gap-2">
            {step > 1 ? (
              <Button
                variant="ghost"
                size="sm"
                leftIcon={<ChevronLeft className="h-4 w-4" />}
                onClick={retreat}
              >
                Back
              </Button>
            ) : null}
            {step < TOTAL_STEPS ? (
              <Button
                variant="primary"
                size="sm"
                disabled={!stepIsValid(step)}
                onClick={advance}
              >
                Next
                <ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            ) : (
              <Button
                variant="primary"
                size="sm"
                disabled={!canCreate}
                loading={create.isPending}
                onClick={() => create.mutate()}
              >
                Create Deployment
              </Button>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step components
// ---------------------------------------------------------------------------

function Step1Strategy({
  strategies,
  loading,
  selected,
  onSelect,
}: {
  strategies: StrategyHeadSummary[];
  loading: boolean;
  selected: StrategyHeadSummary | null;
  onSelect: (s: StrategyHeadSummary) => void;
}): JSX.Element {
  const [search, setSearch] = useState("");
  const filtered = strategies.filter((s) =>
    s.name.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div>
      <StepHeader step={1} label="Choose a Strategy" />
      <TextField
        label="Search"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="mb-3 max-w-md"
      />
      {loading ? (
        <div className="text-sm text-fg-muted">Loading strategies…</div>
      ) : filtered.length === 0 ? (
        <div className="text-sm text-fg-muted">
          No v4 strategies found. Create one in the Strategies IDE.
        </div>
      ) : (
        <div className="grid max-h-[60vh] grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((s) => (
            <button
              key={s.strategy_v4_id}
              type="button"
              onClick={() => onSelect(s)}
              className={[
                "rounded border p-3 text-left transition-colors",
                selected?.strategy_v4_id === s.strategy_v4_id
                  ? "border-accent bg-accent/10"
                  : "border-border hover:bg-bg-raised",
              ].join(" ")}
            >
              <div className="font-medium">{s.name}</div>
              {s.description ? (
                <div className="mt-0.5 truncate text-xs text-fg-muted">{s.description}</div>
              ) : null}
              <div className="mt-1 text-[11px] text-fg-subtle">
                v{s.head_version} · {s.total_versions} version{s.total_versions === 1 ? "" : "s"}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Step2Controls({
  libraries,
  loading,
  selected,
  onSelect,
}: {
  libraries: { strategy_controls_id: string; name: string; is_default: boolean; retired_at: string | null }[];
  loading: boolean;
  selected: string;
  onSelect: (id: string) => void;
}): JSX.Element {
  return (
    <div>
      <StepHeader step={2} label="Strategy Controls (optional)" />
      <p className="mb-4 text-sm text-fg-muted">
        Strategy Controls govern timing, session preferences, and risk-count rules. You can leave
        this unbound to rely on account defaults.
      </p>
      {loading ? (
        <div className="text-sm text-fg-muted">Loading…</div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => onSelect("")}
            className={[
              "rounded border p-3 text-left transition-colors",
              selected === ""
                ? "border-accent bg-accent/10"
                : "border-border hover:bg-bg-raised",
            ].join(" ")}
          >
            <div className="font-medium">Use defaults</div>
            <div className="text-xs text-fg-muted">No explicit Controls binding</div>
          </button>
          {libraries.map((lib) => (
            <button
              key={lib.strategy_controls_id}
              type="button"
              onClick={() => onSelect(lib.strategy_controls_id)}
              disabled={lib.retired_at !== null}
              className={[
                "rounded border p-3 text-left transition-colors",
                lib.retired_at ? "cursor-not-allowed opacity-50" : "",
                selected === lib.strategy_controls_id
                  ? "border-accent bg-accent/10"
                  : "border-border hover:bg-bg-raised",
              ].join(" ")}
            >
              <div className="font-medium">
                {lib.name}
                {lib.is_default ? (
                  <span className="ml-1 text-[10px] text-fg-subtle">[default]</span>
                ) : null}
              </div>
              {lib.retired_at ? (
                <div className="text-xs text-warn">Retired</div>
              ) : null}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Step3ExecPlan({
  libraries,
  loading,
  selected,
  onSelect,
}: {
  libraries: { execution_plan_id: string; name: string; is_default: boolean; retired_at: string | null }[];
  loading: boolean;
  selected: string;
  onSelect: (id: string) => void;
}): JSX.Element {
  return (
    <div>
      <StepHeader step={3} label="Execution Plan (optional)" />
      <p className="mb-4 text-sm text-fg-muted">
        Execution Plans describe order behavior: entry/exit type, time-in-force, bracket specs.
        Leave unbound to use account defaults.
      </p>
      {loading ? (
        <div className="text-sm text-fg-muted">Loading…</div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => onSelect("")}
            className={[
              "rounded border p-3 text-left transition-colors",
              selected === ""
                ? "border-accent bg-accent/10"
                : "border-border hover:bg-bg-raised",
            ].join(" ")}
          >
            <div className="font-medium">Use defaults</div>
            <div className="text-xs text-fg-muted">No explicit Execution Plan binding</div>
          </button>
          {libraries.map((lib) => (
            <button
              key={lib.execution_plan_id}
              type="button"
              onClick={() => onSelect(lib.execution_plan_id)}
              disabled={lib.retired_at !== null}
              className={[
                "rounded border p-3 text-left transition-colors",
                lib.retired_at ? "cursor-not-allowed opacity-50" : "",
                selected === lib.execution_plan_id
                  ? "border-accent bg-accent/10"
                  : "border-border hover:bg-bg-raised",
              ].join(" ")}
            >
              <div className="font-medium">
                {lib.name}
                {lib.is_default ? (
                  <span className="ml-1 text-[10px] text-fg-subtle">[default]</span>
                ) : null}
              </div>
              {lib.retired_at ? (
                <div className="text-xs text-warn">Retired</div>
              ) : null}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Step4Watchlists({
  watchlists,
  loading,
  selected,
  onToggle,
}: {
  watchlists: { watchlist_id: string; name: string; kind: string }[];
  loading: boolean;
  selected: string[];
  onToggle: (id: string) => void;
}): JSX.Element {
  return (
    <div>
      <StepHeader step={4} label="Entry Watchlists" />
      <p className="mb-4 text-sm text-fg-muted">
        Select one or more Watchlists. Symbols from these lists generate entry candidates.
      </p>
      {loading ? (
        <div className="text-sm text-fg-muted">Loading…</div>
      ) : watchlists.length === 0 ? (
        <Banner
          severity="warning"
          title="No watchlists"
          message="Create at least one Watchlist before creating a Deployment."
        />
      ) : (
        <div className="grid max-h-[50vh] grid-cols-1 gap-1 overflow-y-auto rounded border border-border bg-bg-inset p-2">
          {watchlists.map((w) => (
            <label key={w.watchlist_id} className="flex cursor-pointer items-center gap-2 rounded p-2 hover:bg-bg-raised">
              <input
                type="checkbox"
                checked={selected.includes(w.watchlist_id)}
                onChange={() => onToggle(w.watchlist_id)}
              />
              <span className="font-medium">{w.name}</span>
              <span className="ml-auto text-xs text-fg-muted">{w.kind}</span>
            </label>
          ))}
        </div>
      )}
      {selected.length === 0 ? (
        <div className="mt-2 text-xs text-fg-muted">Select at least one watchlist to continue.</div>
      ) : (
        <div className="mt-2 text-xs text-ok">{selected.length} selected</div>
      )}
    </div>
  );
}

function Step5Accounts({
  accounts,
  loading,
  selected,
  onToggle,
}: {
  accounts: { id: string; display_name: string; mode: string }[];
  loading: boolean;
  selected: string[];
  onToggle: (id: string) => void;
}): JSX.Element {
  return (
    <div>
      <StepHeader step={5} label="Subscribed Accounts" />
      <p className="mb-4 text-sm text-fg-muted">
        Select which broker accounts subscribe to this Deployment. Each Account decides
        independently whether to take an entry.
      </p>
      {loading ? (
        <div className="text-sm text-fg-muted">Loading…</div>
      ) : accounts.length === 0 ? (
        <Banner
          severity="warning"
          title="No accounts"
          message="Add at least one broker account in Accounts before creating a Deployment."
        />
      ) : (
        <div className="grid max-h-[50vh] grid-cols-1 gap-1 overflow-y-auto rounded border border-border bg-bg-inset p-2">
          {accounts.map((a) => (
            <label key={a.id} className="flex cursor-pointer items-center gap-2 rounded p-2 hover:bg-bg-raised">
              <input
                type="checkbox"
                checked={selected.includes(a.id)}
                onChange={() => onToggle(a.id)}
              />
              <span className="font-medium">{a.display_name}</span>
              <span className="ml-auto text-xs text-fg-muted">
                {a.mode === "BROKER_LIVE" ? "Live" : "Paper"}
              </span>
            </label>
          ))}
        </div>
      )}
      {selected.length === 0 ? (
        <div className="mt-2 text-xs text-fg-muted">Select at least one account to continue.</div>
      ) : (
        <div className="mt-2 text-xs text-ok">{selected.length} selected</div>
      )}
    </div>
  );
}

function Step6Horizon({
  selected,
  onSelect,
}: {
  selected: TradingHorizon | "";
  onSelect: (h: TradingHorizon | "") => void;
}): JSX.Element {
  return (
    <div>
      <StepHeader step={6} label="Risk Horizon (optional)" />
      <p className="mb-2 text-sm text-fg-muted">
        Horizon shapes per-account risk sizing and gating (Governor). When set, the Governor
        requires each subscribed Account to map a RiskPlan for this horizon. When left as None,
        horizon enforcement is off and only AccountRiskConfig limits apply.
      </p>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <button
          type="button"
          onClick={() => onSelect("")}
          className={[
            "rounded border p-3 text-left transition-colors",
            selected === ""
              ? "border-accent bg-accent/10"
              : "border-border hover:bg-bg-raised",
          ].join(" ")}
        >
          <div className="font-medium">No horizon</div>
          <div className="text-xs text-fg-muted">Enforcement off; account limits only</div>
        </button>
        {(Object.entries(TRADING_HORIZON_LABELS) as [TradingHorizon, string][]).map(
          ([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => onSelect(value)}
              className={[
                "rounded border p-3 text-left transition-colors",
                selected === value
                  ? "border-accent bg-accent/10"
                  : "border-border hover:bg-bg-raised",
              ].join(" ")}
            >
              <div className="font-medium">{label}</div>
            </button>
          ),
        )}
      </div>
    </div>
  );
}
