"""PaperRuntimeSupervisor — process-level lifecycle owner for paper deployments.

Bridges the three independent surfaces that the runtime composition root
already builds — ``BrokerRuntimeOrchestrator`` (per-deployment processing),
``BrokerStreamRunner`` (account/orders/fills push), ``MarketDataStreamRunner``
(bars push) — into one start/stop story so a CLI entrypoint or HTTP route
can ask for "run these deployments" and get exactly that.

Scope, intentionally narrow:

- Single broker account per supervisor instance (one set of credentials,
  one ``AlpacaBrokerAdapter``, one ``BrokerStreamRunner``).
- One ``MarketDataStreamRunner`` shared by every active deployment; the
  supervisor builds a ``symbol → {deployment_ids}`` index and dispatches
  each incoming bar to all deployments that subscribe to that symbol.
- All deployments under this supervisor share the same broker freshness;
  there is no cross-account fan-out here. Multiple paper accounts means
  multiple supervisors.

What it does NOT own:

- Loading deployments from persistence — caller passes
  ``BrokerRuntimeDeployment`` instances (or the underlying
  ``BrokerRuntimeOrchestrator`` already loaded them).
- Promotion gating, order routing, governor enforcement — those still
  live in their existing services and are exercised by the per-bar
  pipeline call inside ``BrokerRuntimeOrchestrator.process_completed_bar``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from threading import Lock
from typing import Any
from uuid import UUID

from backend.app.brokers import BrokerStreamRunner
from backend.app.features import NormalizedBar
from backend.app.market_data import AlpacaMarketDataAdapter, MarketDataStreamRunner

from .broker_runtime_orchestrator import BrokerRuntimeDeployment, BrokerRuntimeOrchestrator


class PaperRuntimeSupervisorError(RuntimeError):
    """Raised when the supervisor cannot start, stop, or dispatch safely."""


class PaperRuntimeSupervisor:
    """Owns the start/stop lifecycle for a set of paper deployments."""

    def __init__(
        self,
        *,
        broker_runtime: BrokerRuntimeOrchestrator,
        market_data_adapter: AlpacaMarketDataAdapter,
        broker_stream_runner: BrokerStreamRunner | None = None,
        market_data_stream_factory: Any | None = None,
    ) -> None:
        self._broker_runtime = broker_runtime
        self._market_data_adapter = market_data_adapter
        self._broker_runner = broker_stream_runner
        self._market_data_stream_factory = market_data_stream_factory
        self._market_data_runner: MarketDataStreamRunner | None = None
        self._deployments: dict[UUID, BrokerRuntimeDeployment] = {}
        self._symbol_index: dict[str, set[UUID]] = defaultdict(set)
        self._running = False
        self._lock = Lock()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def active_deployment_ids(self) -> tuple[UUID, ...]:
        return tuple(self._deployments)

    @property
    def subscribed_symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self._symbol_index))

    def start(self, deployments: Iterable[BrokerRuntimeDeployment]) -> None:
        """Start the broker + market-data streams and bring deployments online.

        Each deployment is preflight-checked through
        ``BrokerRuntimeOrchestrator.start_deployment_runtime``. A deployment
        that is blocked at preflight is logged in
        ``self.blocked_at_start`` rather than raising, so other deployments
        in the same supervisor can still come up.
        """
        with self._lock:
            if self._running:
                raise PaperRuntimeSupervisorError("supervisor is already running")

            blocked: dict[UUID, str] = {}
            for entry in deployments:
                deployment_id = entry.deployment.deployment_id
                self._deployments[deployment_id] = entry
                for symbol in self._symbols_for(entry):
                    self._symbol_index[symbol].add(deployment_id)
                status = self._broker_runtime.start_deployment_runtime(deployment_id)
                if not status.running:
                    blocked[deployment_id] = status.last_error or status.state.value

            self.blocked_at_start: dict[UUID, str] = blocked

            if self._broker_runner is not None:
                self._broker_runner.start()

            if self._symbol_index:
                stream = self._market_data_adapter.subscribe_bars(
                    sorted(self._symbol_index),
                    emit=self._dispatch_bar,
                )
                runner_factory = self._market_data_stream_factory or MarketDataStreamRunner
                self._market_data_runner = runner_factory(stream)
                self._market_data_runner.start()

            self._running = True

    def stop(self, *, timeout: float = 5.0) -> None:
        """Stop streams and bring deployments down. Idempotent."""
        with self._lock:
            if not self._running:
                return
            for deployment_id in list(self._deployments):
                self._broker_runtime.stop_deployment_runtime(deployment_id)
            if self._market_data_runner is not None:
                self._market_data_runner.stop(timeout=timeout)
                self._market_data_runner = None
            if self._broker_runner is not None:
                self._broker_runner.stop(timeout=timeout)
            self._symbol_index.clear()
            self._deployments.clear()
            self._running = False

    def dispatch_bar(self, bar: NormalizedBar) -> None:
        """Public hook used by tests to feed a single bar without a real stream."""
        self._dispatch_bar(bar)

    def _dispatch_bar(self, bar: NormalizedBar) -> None:
        symbol = bar.symbol.upper()
        targets = self._symbol_index.get(symbol)
        if not targets:
            return
        for deployment_id in tuple(targets):
            self._broker_runtime.process_completed_bar(deployment_id, bar)

    def _symbols_for(self, entry: BrokerRuntimeDeployment) -> tuple[str, ...]:
        return tuple(symbol.symbol.upper() for symbol in entry.components.universe.symbols)
