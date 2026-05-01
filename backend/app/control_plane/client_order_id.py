from __future__ import annotations

import hashlib
import re
from uuid import UUID, uuid4


_SIGNAL_PLAN_INTENTS = {
    "open",
    "close",
    "reduce",
    "target",
    "stop",
    "trail",
    "breakeven",
    "runner",
    "logical_exit",
    "tp",
    "sl",
    "scale",
}
_MANUAL_INTENTS = {"open", "close", "reduce"}
_SIGNAL_PLAN_CLIENT_ORDER_ID_RE = re.compile(
    r"^sigplan-(?P<account>[0-9a-f]{8})-(?P<signal_plan>[0-9a-f]{8})-"
    r"(?P<intent>open|close|reduce|target|stop|trail|be|runner|lx|tp|sl|scale)-"
    r"(?P<digest>[0-9a-f]{10})$"
)
_MANUAL_CLIENT_ORDER_ID_RE = re.compile(
    r"^manual-(?P<account>[0-9a-f]{8})-(?P<intent>open|close|reduce)-(?P<rand>[0-9a-f]{8})$"
)


def build_manual_client_order_id(account_id: UUID, intent: object = "open") -> str:
    """Mint a client_order_id for an operator-driven manual order."""
    normalized_intent = str(getattr(intent, "value", intent))
    if normalized_intent not in _MANUAL_INTENTS:
        raise ValueError(f"unsupported manual order intent: {intent}")
    return f"manual-{account_id.hex[:8]}-{normalized_intent}-{uuid4().hex[:8]}"


def build_signal_plan_client_order_id(
    account_id: UUID,
    deployment_id: UUID,
    signal_plan_id: UUID,
    intent: object = "open",
    position_lineage_id: UUID | None = None,
    leg_label: str | None = None,
) -> str:
    normalized_intent = str(getattr(intent, "value", intent))
    if normalized_intent not in _SIGNAL_PLAN_INTENTS:
        raise ValueError(f"unsupported signal plan order intent: {intent}")
    stable_seed = "|".join(
        (
            account_id.hex,
            deployment_id.hex,
            signal_plan_id.hex,
            normalized_intent,
            "" if position_lineage_id is None else position_lineage_id.hex,
            "" if leg_label is None else leg_label,
        )
    )
    digest = hashlib.sha256(stable_seed.encode("utf-8")).hexdigest()[:10]
    return f"sigplan-{account_id.hex[:8]}-{signal_plan_id.hex[:8]}-{_signal_plan_intent_abbrev(normalized_intent)}-{digest}"


def is_manual_client_order_id(client_order_id: str) -> bool:
    return _MANUAL_CLIENT_ORDER_ID_RE.fullmatch(client_order_id) is not None


def parse_order_intent(client_order_id: str) -> str:
    manual_match = _MANUAL_CLIENT_ORDER_ID_RE.fullmatch(client_order_id)
    if manual_match is not None:
        return manual_match.group("intent")
    signal_plan_match = _SIGNAL_PLAN_CLIENT_ORDER_ID_RE.fullmatch(client_order_id)
    if signal_plan_match is not None:
        return _signal_plan_intent_from_abbrev(signal_plan_match.group("intent"))
    return "unknown"


def parse_order_deployment_id(client_order_id: str) -> str | None:
    """Return no deployment from modern client_order_id strings.

    Modern SignalPlan client_order_id values intentionally do not encode
    Deployment authority. Callers that need Deployment scope must use the
    local InternalOrder lineage written by OrderManager.
    """
    _ = client_order_id
    return None


def parse_manual_account_id(client_order_id: str) -> str | None:
    """Return the 8-hex account prefix for manual orders, or ``None``."""
    match = _MANUAL_CLIENT_ORDER_ID_RE.fullmatch(client_order_id)
    if match is None:
        return None
    return match.group("account")


def _signal_plan_intent_abbrev(intent: str) -> str:
    return {
        "breakeven": "be",
        "logical_exit": "lx",
        "take_profit": "tp",
        "stop_loss": "sl",
    }.get(intent, intent[:8])


def _signal_plan_intent_from_abbrev(intent: str) -> str:
    return {
        "be": "breakeven",
        "lx": "logical_exit",
    }.get(intent, intent)
