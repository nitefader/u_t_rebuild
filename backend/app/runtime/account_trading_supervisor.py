"""BrokerRuntimeSupervisor — process-level lifecycle for broker-runtime deployments.

The supervisor owns the broker-side concerns that are unique to a running
deployment (the broker trade-update stream, the per-deployment lifecycle)
and **consumes** the generic ``MarketDataStreamHub`` for bars rather than
owning it. The hub is shared across consumers (this supervisor, Sim Lab
Live Simulation, Chart Lab Live Preview, etc.) so the system subscribes
to each market-data symbol exactly once.

Scope:

- Today, the broker adapter wired in is ``AlpacaBrokerAdapter`` which
  only supports ``BROKER_PAPER``. The supervisor does not enforce paper
  vs. live; it accepts whatever ``BrokerRuntimeOrchestrator`` was built
  with. Live becomes a swap of the adapter once the promotion gate is
  wired in.
- One broker account per supervisor instance (one ``BrokerStreamRunner``,
  one set of credentials). Multiple accounts → multiple supervisors.
- Each deployment's universe symbols are registered with the hub under
  one consumer id per supervisor; bars route into
  ``BrokerRuntimeOrchestrator.process_completed_bar``.

What it does NOT own:

- Loading deployments from persistence (caller passes them in or the
  ``BrokerRuntimeOrchestrator`` already loaded them).
- Promotion gating, order routing, governor enforcement (those run
  inside ``process_completed_bar``).
- The market-data stream lifecycle (the hub owns that).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from threading import Lock
from uuid import UUID, uuid4

from backend.app.brokers import BrokerStreamRunner
from backend.app.features import NormalizedBar
from backend.app.market_data import MarketDataStreamHub

from .account_trading_orchestrator import BrokerRuntimeDeployment, BrokerRuntimeOrchestrator


class BrokerRuntimeSupervisorError(RuntimeError):
    """Raised when the supervisor cannot start, stop, or dispatch safely."""


class BrokerRuntimeSupervisor:
    """Owns broker-stream + deployment lifecycle for one broker account."""

    def __init__(
        self,
        *,
        account_trading: BrokerRuntimeOrchestrator,
        market_data_hub: MarketDataStreamHub,
        broker_stream_runner: BrokerStreamRunner | None = None,
        consumer_id: str | None = None,
    ) -> None:
        self._account_trading = account_trading
        self._market_data_hub = market_data_hub
        self._broker_runner = broker_stream_runner
        self._consumer_id = consumer_id or f"broker-runtime-supervisor:{uuid4().hex[:8]}"
        self._deployments: dict[UUID, BrokerRuntimeDeployment] = {}
        self._symbol_index: dict[str, set[UUID]] = defaultdict(set)
        self._running = False
        self._lock = Lock()
        self.blocked_at_start: dict[UUID, str] = {}

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def consumer_id(self) -> str:
        return self._consumer_id

    @property
    def active_deployment_ids(self) -> tuple[UUID, ...]:
        return tuple(self._deployments)

    @property
    def subscribed_symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self._symbol_index))

    def start(self, deployments: Iterable[BrokerRuntimeDeployment]) -> None:
        """Bring deployments online and register with the hub.

        Each deployment is preflight-checked through
        ``BrokerRuntimeOrchestrator.start_deployment_runtime``. Deployments
        that fail preflight land in ``self.blocked_at_start`` rather than
        raising, so other deployments in the same supervisor still come up.

        The hub is **not** started here — that's the caller's job. The
        same hub may be shared with other consumers (sim-lab live, chart-lab
        live preview), and the lifecycle owner of the hub is whoever
        composed it.
        """
        with self._lock:
            if self._running:
                raise BrokerRuntimeSupervisorError("supervisor is already running")

            blocked: dict[UUID, str] = {}
            for entry in deployments:
                deployment_id = entry.deployment.deployment_id
                self._deployments[deployment_id] = entry
                for symbol in self._symbols_for(entry):
                    self._symbol_index[symbol].add(deployment_id)
                status = self._account_trading.start_deployment_runtime(deployment_id)
                if not status.running:
                    blocked[deployment_id] = status.last_error or status.state.value

            self.blocked_at_start = blocked

            if self._broker_runner is not None:
                self._broker_runner.start()

            if self._symbol_index:
                self._market_data_hub.register(
                    self._consumer_id,
                    sorted(self._symbol_index),
                    self._dispatch_bar,
                )

            self._running = True

    def stop(self, *, timeout: float = 5.0) -> None:
        """Stop the broker stream and bring deployments down. Idempotent.

        Does **not** stop the hub — the hub may be shared. The hub's
        lifecycle is the caller's responsibility.
        """
        with self._lock:
            if not self._running:
                return
            for deployment_id in list(self._deployments):
                self._account_trading.stop_deployment_runtime(deployment_id)
            try:
                self._market_data_hub.unregister(self._consumer_id)
            except Exception:  # noqa: BLE001 - hub may already be torn down
                pass
            if self._broker_runner is not None:
                self._broker_runner.stop(timeout=timeout)
            self._symbol_index.clear()
            self._deployments.clear()
            self._running = False

    def reload_deployment(self, deployment_id: UUID) -> bool:
        # Drop the cached components + compiled pipeline for this deployment so
        # the next bar rebuilds them from persistence. Refresh the hub's
        # symbol subscriptions in case the rebind changed the universe.
        # Returns True if the deployment is still active after reload, False
        # if it was deactivated (in which case the supervisor stops dispatching
        # to it — the caller handles cleanup).
        with self._lock:
            if not self._running:
                return False
            new_entry = self._account_trading.evict_deployment_caches(deployment_id)
            old_symbols = {sym for sym, ids in self._symbol_index.items() if deployment_id in ids}
            for sym in old_symbols:
                self._symbol_index[sym].discard(deployment_id)
                if not self._symbol_index[sym]:
                    del self._symbol_index[sym]
            if new_entry is None:
                self._account_trading.stop_deployment_runtime(deployment_id)
                self._deployments.pop(deployment_id, None)
                if self._symbol_index:
                    self._market_data_hub.register(
                        self._consumer_id,
                        sorted(self._symbol_index),
                        self._dispatch_bar,
                    )
                else:
                    try:
                        self._market_data_hub.unregister(self._consumer_id)
                    except Exception:  # noqa: BLE001 - hub may already be torn down
                        pass
                return False
            self._deployments[deployment_id] = new_entry
            for sym in self._symbols_for(new_entry):
                self._symbol_index[sym].add(deployment_id)
            if self._symbol_index:
                self._market_data_hub.register(
                    self._consumer_id,
                    sorted(self._symbol_index),
                    self._dispatch_bar,
                )
            status = self._account_trading.start_deployment_runtime(deployment_id)
            if status.running:
                self.blocked_at_start.pop(deployment_id, None)
            else:
                self.blocked_at_start[deployment_id] = status.last_error or status.state.value
            return True

    def dispatch_bar(self, bar: NormalizedBar) -> None:
        """Public dispatch hook used by tests to bypass the hub."""
        self._dispatch_bar(bar)

    def _dispatch_bar(self, bar: NormalizedBar) -> None:
        symbol = bar.symbol.upper()
        targets = self._symbol_index.get(symbol)
        if not targets:
            return
        for deployment_id in tuple(targets):
            self._account_trading.process_completed_bar(deployment_id, bar)

    def _symbols_for(self, entry: BrokerRuntimeDeployment) -> tuple[str, ...]:
        return tuple(symbol.symbol.upper() for symbol in entry.components.universe.symbols)
