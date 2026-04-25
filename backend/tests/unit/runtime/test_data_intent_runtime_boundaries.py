from __future__ import annotations

from backend.app.market_data import DataConsumer, DataIntent, DataIntentMode, DataPurpose, Timeframe


def test_sim_lab_live_intent_uses_market_data_requirements_not_broker_adapter() -> None:
    intent = DataIntent(
        consumer=DataConsumer.SIM_LAB,
        mode=DataIntentMode.LIVE_PREVIEW,
        symbols=["SPY"],
        timeframe=Timeframe.M1,
        purpose=DataPurpose.SIGNAL_PREVIEW,
    )

    assert intent.requires_streaming is True
    assert intent.requires_realtime is True
    assert intent.requires_intraday is True
    assert "BrokerAdapter" not in intent.model_dump_json()
    assert "broker_account_id" not in intent.model_dump()
