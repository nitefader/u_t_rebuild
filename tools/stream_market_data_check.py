from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv() -> bool:
        return False

from backend.app.market_data import AlpacaMarketDataAdapter, AlpacaMarketDataError, MarketDataSubscription


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the first normalized Alpaca market data bars.")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args(argv)

    print("[stream_market_data_check] Loading .env", flush=True)
    load_dotenv()
    error = _validate_environment()
    if error is not None:
        print(json.dumps({"ok": False, "error": error}), file=sys.stderr, flush=True)
        return 2

    try:
        subscription = MarketDataSubscription(symbol=args.symbol, timeframe=args.timeframe, limit=args.limit)
        adapter = AlpacaMarketDataAdapter()
        print(
            f"[stream_market_data_check] Subscribing to {subscription.symbol} {subscription.timeframe}",
            flush=True,
        )
        bars = adapter.collect_bars_sync(subscription=subscription, timeout_seconds=args.timeout)
    except (ValueError, AlpacaMarketDataError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr, flush=True)
        return 2

    for bar in bars:
        print(json.dumps(_bar_payload(bar), sort_keys=True), flush=True)
    print(json.dumps({"ok": True, "bars": len(bars), "orders_submitted": 0}, sort_keys=True), flush=True)
    return 0


def _validate_environment() -> str | None:
    if not os.getenv("ALPACA_API_KEY") or not os.getenv("ALPACA_SECRET_KEY"):
        return "ALPACA_API_KEY and ALPACA_SECRET_KEY are required"
    return None


def _bar_payload(bar) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "symbol": bar.symbol,
        "timeframe": bar.timeframe,
        "timestamp": bar.timestamp.isoformat(),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }


if __name__ == "__main__":
    raise SystemExit(main())
