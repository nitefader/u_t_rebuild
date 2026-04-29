"""Process-local poller for durable discovery schedules.

The durable schedule table is the source of truth. This thread is only the
small loop that asks the service to execute due Screeners/Watchlist refreshes.
"""

from __future__ import annotations

import logging
import threading

from .schedule_service import create_discovery_schedule_service_from_environment

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_stop_event: threading.Event | None = None
_thread: threading.Thread | None = None


def start_discovery_schedule_poller(*, interval_seconds: float = 30.0) -> None:
    global _stop_event, _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop_event = threading.Event()
        _thread = threading.Thread(
            target=_poll_loop,
            args=(_stop_event, interval_seconds),
            daemon=True,
            name="discovery-schedule-poller",
        )
        _thread.start()


def stop_discovery_schedule_poller() -> None:
    global _stop_event, _thread
    with _lock:
        stop_event = _stop_event
        thread = _thread
        _stop_event = None
        _thread = None
    if stop_event is not None:
        stop_event.set()
    if thread is not None:
        thread.join(timeout=2.0)


def _poll_loop(stop_event: threading.Event, interval_seconds: float) -> None:
    while not stop_event.is_set():
        try:
            service = create_discovery_schedule_service_from_environment()
            service.run_due()
        except Exception as exc:  # noqa: BLE001
            logger.warning("discovery schedule poll failed: %s", exc, exc_info=True)
        stop_event.wait(interval_seconds)
