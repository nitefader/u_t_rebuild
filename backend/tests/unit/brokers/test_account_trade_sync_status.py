from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.brokers import AccountTradeSyncState, AccountTradeSyncStatus
from backend.app.domain import TradingMode


def test_trading_paused_account_can_still_have_open_trade_sync_status() -> None:
    status = AccountTradeSyncStatus(
        account_id=uuid4(),
        provider="alpaca",
        broker_mode=TradingMode.BROKER_PAPER,
        enabled=True,
        open=True,
        connected=True,
        authenticated=True,
        status=AccountTradeSyncState.CONNECTED,
    )

    assert status.open is True
    assert status.status == AccountTradeSyncState.CONNECTED


def test_operator_paused_trade_sync_requires_timestamp() -> None:
    with pytest.raises(ValidationError):
        AccountTradeSyncStatus(
            account_id=uuid4(),
            provider="alpaca",
            broker_mode=TradingMode.BROKER_PAPER,
            enabled=False,
            open=False,
            connected=False,
            authenticated=False,
            status=AccountTradeSyncState.OPERATOR_PAUSED,
        )


def test_operator_paused_trade_sync_is_visible() -> None:
    paused_at = datetime.now(timezone.utc)
    status = AccountTradeSyncStatus(
        account_id=uuid4(),
        provider="alpaca",
        broker_mode=TradingMode.BROKER_PAPER,
        enabled=False,
        open=False,
        connected=False,
        authenticated=False,
        status=AccountTradeSyncState.OPERATOR_PAUSED,
        operator_paused_at=paused_at,
    )

    assert status.operator_paused_at == paused_at
