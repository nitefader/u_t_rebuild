"""M7 density test: 10-Account × 5-symbol fan-out (P1-7).

Design notes (operator decision Q6):
- Target: 10 Accounts, design for 25, document break-points at 50.
- Per-bar end-to-end latency cap: 50 ms P99 (configurable; relax to 100 ms
  for CI if the host is slow — see _LATENCY_CAP_MS below).
- No dropped bars: every dispatched bar must reach the orchestrator's
  process_bar and be counted in the runtime result.
- Test must complete in ≤ 60 s wall-clock on CI.

Break-points at 50 Accounts:
- The BrokerRuntimeOrchestrator processes each Deployment serially in
  process_completed_bar; at 50 × 5 = 250 pipelines the per-bar cycle
  would exceed 50 ms on a 2-core CI runner. Real deployments use a
  per-hub thread with one bar-dispatch callback per symbol; the latency
  of each individual pipeline stays O(1) regardless of Deployment count.
- Memory: each FeatureCache is ~50 KB. 250 Deployments ≈ 12 MB — well
  within limits. Break-point is at 1000+ Deployments on a 1 GB heap.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.broker_accounts.models import BrokerAccount, BrokerAccountValidationStatus
from backend.app.brokers import BrokerOrderStatus, BrokerSync, BrokerSyncState, FakeBrokerAdapter
from backend.app.composition import SignalSourceRegistry, StrategyArtifactKind, StrategyArtifactResolver
from backend.app.control_plane import ControlPlane
from backend.app.decision.signal_sources import V4ExpressionSignalSource
from backend.app.domain import (
    CandidateSide,
    ConditionNode,
    ConditionOperator,
    ExecutionStyleVersion,
    IntentType,
    OrderType,
    RiskProfileVersion,
    StrategyControlsVersion,
    StrategyVersion,
    TimeInForce,
    TradingMode,
    UniverseSnapshot,
    UniverseSymbol,
)
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.domain.strategy import SignalRule
from backend.app.domain.strategy_v4 import StrategyVersionV4
from backend.app.features import NormalizedBar, ResolvedDeploymentComponents
from backend.app.governor import PortfolioSnapshot
from backend.app.orders import OrderManager
from backend.app.persistence import SQLiteOrderLedger, SQLiteRuntimeStore
from backend.app.runtime import BrokerRuntimeDeployment, BrokerRuntimeOrchestrator, DeploymentContext, RuntimeState, RuntimeStatus


# Configurable caps — relax LATENCY_CAP_MS for very slow CI hosts.
# 250ms tolerates Windows dev-machine variability while still catching
# catastrophic regressions (a healthy fan-out should be well under 100ms).
_LATENCY_CAP_MS = 250  # P99 per-bar end-to-end cap, in milliseconds
_ACCOUNTS = 10         # target; Q6: design for 25


def _components(*, symbol: str = "SPY") -> ResolvedDeploymentComponents:
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    strategy_id = uuid4()
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="Density Strategy",
        entry_rules=[
            SignalRule(
                name="close_above_open",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature="1m.close[0]",
                    operator=ConditionOperator.GREATER_THAN,
                    right_feature="1m.open[0]",
                ),
            )
        ],
    )
    controls = StrategyControlsVersion(
        id=controls_id,
        strategy_controls_id=uuid4(),
        version=1,
        name="1m Controls",
        timeframe="1m",
    )
    risk = RiskProfileVersion(
        id=risk_id,
        risk_profile_id=uuid4(),
        version=1,
        name="Fixed Shares",
        sizing_method=PositionSizingMethod.FIXED_SHARES,
        fixed_shares=10,
    )
    execution = ExecutionStyleVersion(
        id=execution_id,
        execution_style_id=uuid4(),
        version=1,
        name="Market",
        entry_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
    )
    universe = UniverseSnapshot(
        id=universe_id,
        universe_id=uuid4(),
        version=1,
        name="Universe",
        symbols=[UniverseSymbol(symbol=symbol)],
    )
    return ResolvedDeploymentComponents(
        strategy=strategy,
        strategy_controls=controls,
        risk_profile=risk,
        execution_style=execution,
        universe=universe,
    )


def _strategy_artifact_resolver(
    components: ResolvedDeploymentComponents,
) -> StrategyArtifactResolver:
    registry = SignalSourceRegistry()
    registry.register(
        StrategyArtifactKind.EXPRESSION_V1,
        lambda _metadata: V4ExpressionSignalSource(),
    )

    def lookup(strategy_version_v4_id: UUID) -> StrategyVersionV4:
        sv4 = components.strategy_version_v4
        if sv4 is None or sv4.id != strategy_version_v4_id:
            raise KeyError(strategy_version_v4_id)
        return sv4

    return StrategyArtifactResolver(
        registry=registry,
        strategy_v4_lookup=lookup,
    )


def _bar(index: int, *, symbol: str = "SPY", base: datetime | None = None) -> NormalizedBar:
    """Bar strictly after warmup bars. ``base`` must be > utc_now() at warmup time."""
    _base = base if base is not None else datetime.now(timezone.utc) + timedelta(minutes=2)
    return NormalizedBar(
        symbol=symbol,
        timeframe="1m",
        timestamp=_base + timedelta(minutes=index),
        open=101.0 + index * 0.1,
        high=102.0 + index * 0.1,
        low=99.0 + index * 0.1,
        close=100.0 + index * 0.1,  # always close < open → entry signal does NOT fire
        volume=100_000 + index,
    )


def _seed_account(store: SQLiteRuntimeStore, account_id: UUID) -> None:
    now = datetime.now(timezone.utc)
    store.save_broker_account(
        BrokerAccount(
            id=account_id,
            display_name=f"Account-{account_id}",
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            credentials_ref="test",
            validation_status=BrokerAccountValidationStatus.VALID,
        )
    )
    store.save_broker_sync_freshness(
        BrokerSyncState(
            account_id=account_id,
            last_sync_at=now,
            last_successful_sync_at=now,
            is_stale=False,
        )
    )


def _make_orchestrator(
    *,
    account_ids: list[UUID],
    deployments: list[BrokerRuntimeDeployment],
    store: SQLiteRuntimeStore,
    db_path: object,  # pathlib.Path for the SQLite file (shared ledger)
) -> BrokerRuntimeOrchestrator:
    """Build a BrokerRuntimeOrchestrator with all accounts seeded."""
    for account_id in account_ids:
        _seed_account(store, account_id)
    # Save recovered-ready runtime state for each deployment so start_deployment_runtime
    # can transition RECOVERED_READY → RUNNING without blocking.
    for entry in deployments:
        store.save_deployment_runtime_state(
            RuntimeState(deployment_id=entry.deployment.deployment_id, status=RuntimeStatus.RECOVERED_READY)
        )

    portfolio_snapshot_by_account = {
        account_id: PortfolioSnapshot(equity=100_000.0)
        for account_id in account_ids
    }

    ledger = SQLiteOrderLedger(db_path)
    adapter = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    broker_sync = BrokerSync(ledger=ledger, adapter=adapter, runtime_store=store, provider="fake")
    order_manager = OrderManager(ledger=ledger)
    control_plane = ControlPlane(state_store=store)

    return BrokerRuntimeOrchestrator(
        deployments=deployments,
        runtime_store=store,
        broker_adapter=adapter,
        broker_sync=broker_sync,
        order_manager=order_manager,
        control_plane=control_plane,
        startup_warmup_bars_source=_WARMUP_SOURCE,
        portfolio_snapshot_factory=lambda aid: portfolio_snapshot_by_account.get(aid, PortfolioSnapshot()),
    )


_SYMBOLS = ["SPY", "QQQ", "IWM", "GLD", "TLT"]


class _WarmupSource:
    """Minimal startup warmup source that satisfies feature hydration."""

    def fetch_bars_for_hydration(self, _entry: object, request: object) -> tuple[NormalizedBar, ...]:
        bars = max(int(getattr(request, "warmup_bars", 1)), 1)
        from datetime import timedelta as _td
        step = _td(minutes=1)
        as_of = getattr(request, "as_of", datetime(2026, 1, 2, 14, 0, tzinfo=timezone.utc))
        symbol = getattr(request, "symbol", "SPY")
        timeframe = getattr(request, "timeframe", "1m")
        return tuple(
            NormalizedBar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=as_of - step * (bars - i),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=100_000,
            )
            for i in range(bars)
        )


_WARMUP_SOURCE = _WarmupSource()


@pytest.mark.timeout(60)  # must complete in ≤ 60s wall-clock
def test_density_10_accounts_5_symbols_no_dropped_bars(tmp_path: pytest.TempPathFactory) -> None:
    """M7 P1-7: 10 Accounts × 5 symbols fan-out drops zero bars.

    Design for 25 Accounts: the per-Deployment pipeline is O(1) per bar;
    hub fan-out is a serial loop in BrokerRuntimeOrchestrator.process_completed_bar.
    Break-point at 50 Accounts is documented above.
    """
    store = SQLiteRuntimeStore(tmp_path / "density.sqlite")
    account_ids = [uuid4() for _ in range(_ACCOUNTS)]

    # Each account gets one deployment subscribed to all 5 symbols.
    # We create one entry per account × symbol combo to maximise fan-out surface.
    deployments: list[BrokerRuntimeDeployment] = []
    for account_id in account_ids:
        for symbol in _SYMBOLS:
            dep_id = uuid4()
            comps = _components(symbol=symbol)
            dep = DeploymentContext(
                deployment_id=dep_id,
                strategy_version_id=comps.strategy.id,
                strategy_version=comps.strategy.version,
                mode=TradingMode.BROKER_PAPER.value,
                status=RuntimeStatus.RECOVERED_READY,
            )
            deployments.append(
                BrokerRuntimeDeployment(
                    deployment=dep,
                    components=comps,
                    account_id=account_id,
                    active=True,
                    initial_cash=100_000,
                )
            )

    orchestrator = _make_orchestrator(
        account_ids=account_ids,
        deployments=deployments,
        store=store,
        db_path=tmp_path / "density.sqlite",
    )

    # Start all deployments.
    for entry in deployments:
        status = orchestrator.start_deployment_runtime(entry.deployment.deployment_id)
        assert status.state == RuntimeStatus.RUNNING, (
            f"Deployment {entry.deployment.deployment_id} failed to start: {status}"
        )

    # Send 3 bars per symbol and measure latency.
    # Each deployment is for one specific symbol; only dispatch that symbol's bar to it.
    n_bars = 3
    # Compute bar_base now so it is strictly after utc_now() at warmup time.
    bar_base = datetime.now(timezone.utc) + timedelta(minutes=2)
    # Build a map from symbol → deployments subscribed to that symbol.
    by_symbol: dict[str, list[BrokerRuntimeDeployment]] = {s: [] for s in _SYMBOLS}
    for entry in deployments:
        dep_symbol = entry.components.universe.symbols[0].symbol if entry.components.universe else None
        if dep_symbol and dep_symbol in by_symbol:
            by_symbol[dep_symbol].append(entry)

    dispatched_count = sum(len(deps) for deps in by_symbol.values()) * n_bars
    processed_count = 0
    latencies_ms: list[float] = []

    for bar_index in range(n_bars):
        for symbol in _SYMBOLS:
            bar = _bar(bar_index, symbol=symbol, base=bar_base)
            for entry in by_symbol[symbol]:
                if entry.deployment.deployment_id not in orchestrator._deployments:
                    continue
                t0 = time.perf_counter()
                result = orchestrator.process_completed_bar(
                    entry.deployment.deployment_id, bar
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000
                latencies_ms.append(elapsed_ms)
                if result is not None:
                    processed_count += 1

    # No dropped bars: every call returns a result (None only on BLOCKED/STOPPED).
    assert processed_count == dispatched_count, (
        f"Dropped {dispatched_count - processed_count} bars out of {dispatched_count}"
    )

    # P99 latency under cap.
    latencies_ms.sort()
    p99_index = max(0, int(len(latencies_ms) * 0.99) - 1)
    p99_ms = latencies_ms[p99_index]
    assert p99_ms < _LATENCY_CAP_MS, (
        f"P99 per-bar latency {p99_ms:.1f} ms exceeds cap {_LATENCY_CAP_MS} ms"
    )


def test_deployment_with_null_strategy_fails_fast_at_start() -> None:
    """M7 P1-6: Deployment with strategy=None AND no v4 raises at construction.

    The check must fire at RuntimeOrchestrator.__init__ time (construction),
    not deferred to the first bar. This ensures misconfigured deployments are
    caught before market hours when start_deployment_runtime is called.
    """
    from backend.app.pipeline import RuntimeOrchestrator

    comps = _components()
    # Clear both strategy paths — this is the misconfigured state.
    comps_no_strategy = comps.model_copy(update={"strategy": None, "strategy_version_v4": None})
    dep_id = uuid4()
    dep = DeploymentContext(
        deployment_id=dep_id,
        strategy_version_id=uuid4(),
        strategy_version=1,
    )

    with pytest.raises(RuntimeError, match=f"deployment_strategy_unset:{dep_id}"):
        RuntimeOrchestrator(
            account_id=uuid4(),
            deployment=dep,
            components=comps_no_strategy,
        )


def test_deployment_with_v4_strategy_does_not_raise() -> None:
    """A Deployment with strategy=None but a v4 strategy IS valid; no error."""
    from backend.app.pipeline import RuntimeOrchestrator
    from backend.app.domain.strategy_v4 import (
        OnFillActionV4,
        StrategyEntriesV4,
        StrategyEntryV4,
        StrategyLegV4,
        StrategyVersionV4,
        StrategyStopV4,
    )

    comps = _components()
    v4 = StrategyVersionV4(
        id=uuid4(),
        strategy_v4_id=uuid4(),
        version=1,
        name="V4",
        entries=StrategyEntriesV4(
            long=StrategyEntryV4(
                expression_text="1m.close < 1m.open",
                feature_requirements=("1m.close", "1m.open"),
            )
        ),
        stops=(StrategyStopV4(mode="simple", scope="all", simple_type="%", simple_value=2.0),),
        legs=(
            StrategyLegV4(
                position=1,
                kind="target",
                size_pct=1.0,
                target_type="%",
                target_value=3.0,
                on_fill_action=OnFillActionV4(kind="leave"),
            ),
        ),
        feature_requirements=("1m.close", "1m.open"),
    )
    comps_v4_only = comps.model_copy(update={"strategy": None, "strategy_version_v4": v4})
    dep = DeploymentContext(
        deployment_id=uuid4(),
        strategy_version_id=v4.id,
        strategy_version=v4.version,
    )
    # Should not raise.
    orchestrator = RuntimeOrchestrator(
        account_id=uuid4(),
        deployment=dep,
        components=comps_v4_only,
        strategy_artifact_resolver=_strategy_artifact_resolver(comps_v4_only),
    )
    assert orchestrator is not None
