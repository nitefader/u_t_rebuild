import { useQuery } from "@tanstack/react-query";
import { Shield } from "lucide-react";
import { RiskApi } from "@/api/risk";
import type { AccountRestrictions, AccountRiskConfig } from "@/api/schemas/risk";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { formatCurrency, formatPercent, formatTimestamp } from "@/lib/format";

/**
 * RiskCardPanel — operator's risk posture for a single Account.
 *
 * Reads `/api/v1/broker-accounts/{id}/risk-config` and
 * `/api/v1/broker-accounts/{id}/restrictions`.
 */
export function RiskCardPanel({ accountId }: { accountId: string }): JSX.Element {
  const config = useQuery({
    queryKey: ["accounts", accountId, "risk-config"],
    queryFn: () => RiskApi.getRiskConfig(accountId),
    retry: false,
  });
  const restrictions = useQuery({
    queryKey: ["accounts", accountId, "restrictions"],
    queryFn: () => RiskApi.getRestrictions(accountId),
    retry: false,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-fg-subtle" aria-hidden="true" />
            Risk Card
          </span>
        </CardTitle>
        <StatusBadge tone="info">Account-scoped</StatusBadge>
      </CardHeader>
      <CardBody className="space-y-3">
        {config.isLoading || restrictions.isLoading ? (
          <LoadingState title="Loading risk posture" />
        ) : null}

        {config.isError ? (
          <ErrorState
            title="Risk config"
            detail={(config.error as Error)?.message}
            onRetry={() => config.refetch()}
          />
        ) : config.data ? (
          <RiskConfigSummary cfg={config.data} />
        ) : null}

        {restrictions.isError ? (
          <ErrorState
            title="Account restrictions"
            detail={(restrictions.error as Error)?.message}
            onRetry={() => restrictions.refetch()}
          />
        ) : restrictions.data ? (
          <RestrictionsSummary restr={restrictions.data} />
        ) : null}
      </CardBody>
    </Card>
  );
}

function RiskConfigSummary({ cfg }: { cfg: AccountRiskConfig }): JSX.Element {
  return (
    <div className="space-y-2">
      <div className="text-xs font-medium uppercase tracking-wide text-fg-subtle">Sizing & exposure</div>
      <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
        <KV label="Sizing method" value={cfg.sizing_method} />
        <KV label="Fixed shares" value={cfg.fixed_shares != null ? String(cfg.fixed_shares) : "—"} />
        <KV label="Fixed notional" value={formatCurrency(cfg.fixed_notional ?? null)} />
        <KV
          label="Risk per trade"
          value={cfg.risk_per_trade_pct != null ? formatPercent(cfg.risk_per_trade_pct) : "—"}
        />
        <KV label="Max position" value={formatCurrency(cfg.max_position_notional ?? null)} />
        <KV
          label="Max open positions"
          value={cfg.max_open_positions != null ? String(cfg.max_open_positions) : "—"}
        />
        <KV
          label="Max gross exposure"
          value={cfg.max_gross_exposure_pct != null ? formatPercent(cfg.max_gross_exposure_pct) : "—"}
        />
        <KV
          label="Max net exposure"
          value={cfg.max_net_exposure_pct != null ? formatPercent(cfg.max_net_exposure_pct) : "—"}
        />
        <KV
          label="Symbol concentration"
          value={
            cfg.max_symbol_concentration_pct != null
              ? formatPercent(cfg.max_symbol_concentration_pct)
              : "—"
          }
        />
        <KV
          label="Max daily loss"
          value={cfg.max_daily_loss_pct != null ? formatPercent(cfg.max_daily_loss_pct) : "—"}
        />
        <KV
          label="Max drawdown"
          value={cfg.max_drawdown_pct != null ? formatPercent(cfg.max_drawdown_pct) : "—"}
        />
        <KV
          label="Fractional"
          value={cfg.fractional_quantity_allowed === undefined ? "—" : cfg.fractional_quantity_allowed ? "yes" : "no"}
        />
      </div>
      <div className="text-[11px] text-fg-subtle">Updated {formatTimestamp(cfg.updated_at)}</div>
    </div>
  );
}

function RestrictionsSummary({ restr }: { restr: AccountRestrictions }): JSX.Element {
  return (
    <div className="space-y-2">
      <div className="text-xs font-medium uppercase tracking-wide text-fg-subtle">Restrictions</div>
      <div className="flex flex-wrap gap-1.5">
        {restr.long_only ? <StatusBadge tone="info">Long only</StatusBadge> : null}
        {restr.short_only ? <StatusBadge tone="info">Short only</StatusBadge> : null}
        {restr.extended_hours_allowed ? (
          <StatusBadge tone="info">Extended hours</StatusBadge>
        ) : (
          <StatusBadge tone="muted">RTH only</StatusBadge>
        )}
        {restr.symbol_blocklist.length > 0 ? (
          <StatusBadge tone="warn">{restr.symbol_blocklist.length} symbol blocks</StatusBadge>
        ) : null}
        {restr.asset_class_blocklist.length > 0 ? (
          <StatusBadge tone="warn">
            {restr.asset_class_blocklist.length} asset blocks
          </StatusBadge>
        ) : null}
        {restr.time_of_day_windows.length > 0 ? (
          <StatusBadge tone="warn">
            {restr.time_of_day_windows.length} time windows
          </StatusBadge>
        ) : null}
      </div>
      {restr.symbol_blocklist.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {restr.symbol_blocklist.map((sym) => (
            <span
              key={sym}
              className="rounded border border-warn/40 bg-warn-subtle px-1.5 py-0.5 font-mono text-[11px] text-warn"
            >
              {sym}
            </span>
          ))}
        </div>
      ) : null}
      {restr.notes ? <div className="text-xs text-fg-muted">{restr.notes}</div> : null}
      <div className="text-[11px] text-fg-subtle">Updated {formatTimestamp(restr.updated_at)}</div>
    </div>
  );
}

function KV({ label, value }: { label: string; value: React.ReactNode }): JSX.Element {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-fg-subtle">{label}</span>
      <span className="tabular text-fg">{value}</span>
    </div>
  );
}
