from __future__ import annotations

import hashlib
import re
from uuid import UUID, uuid4


_SUPPORTED_INTENTS = {"open", "close", "tp", "sl", "scale"}
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
_CLIENT_ORDER_ID_RE = re.compile(
    r"^(?P<program>[a-z0-9]{2,12})-(?P<deployment>[0-9a-f]{8})-"
    r"(?P<intent>open|close|tp|sl|scale)-(?P<rand>[0-9a-f]{8})$"
)
_MANUAL_CLIENT_ORDER_ID_RE = re.compile(
    r"^manual-(?P<account>[0-9a-f]{8})-(?P<intent>open|close|reduce)-(?P<rand>[0-9a-f]{8})$"
)


def build_program_client_order_id(
    program_name: str,
    deployment_id: UUID,
    intent: object = "open",
) -> str:
    normalized_intent = str(getattr(intent, "value", intent))
    if normalized_intent not in _SUPPORTED_INTENTS:
        raise ValueError(f"unsupported order intent: {intent}")
    return f"{_program_abbrev(program_name)}-{deployment_id.hex[:8]}-{normalized_intent}-{uuid4().hex[:8]}"


def build_manual_client_order_id(account_id: UUID, intent: object = "open") -> str:
    """Mint a client_order_id for an operator-driven manual order.

    Manual orders carry a ``manual-`` prefix instead of a program abbrev so
    ``parse_order_deployment_id`` can recognize them and return ``None``
    rather than treating ``manual`` as a strategy name with a fake
    deployment hex. Layout: ``manual-<account-hex8>-<intent>-<rand8>``.
    """
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
    # Check manual form first; the program regex is permissive enough to
    # accidentally match a manual-prefixed id ("manual" fits the program
    # abbrev slot), which would mislabel the intent.
    manual_match = _MANUAL_CLIENT_ORDER_ID_RE.fullmatch(client_order_id)
    if manual_match is not None:
        return manual_match.group("intent")
    match = _CLIENT_ORDER_ID_RE.fullmatch(client_order_id)
    if match is not None:
        return match.group("intent")
    return "unknown"


def parse_order_deployment_id(client_order_id: str) -> str | None:
    """Return the deployment hex for program orders, or ``None`` for manual orders.

    Manual orders deliberately have no deployment scope; callers that filter
    "orders for this deployment" must skip these (returning ``None`` is the
    correct contract — they're not part of any deployment's scope).
    """
    if _MANUAL_CLIENT_ORDER_ID_RE.fullmatch(client_order_id) is not None:
        return None
    match = _CLIENT_ORDER_ID_RE.fullmatch(client_order_id)
    if match is None:
        return None
    return match.group("deployment")


def parse_manual_account_id(client_order_id: str) -> str | None:
    """Return the 8-hex account prefix for manual orders, or ``None``."""
    match = _MANUAL_CLIENT_ORDER_ID_RE.fullmatch(client_order_id)
    if match is None:
        return None
    return match.group("account")


def _program_abbrev(program_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", program_name.lower())
    if len(normalized) < 2:
        normalized = "utos"
    return normalized[:12]


def _signal_plan_intent_abbrev(intent: str) -> str:
    return {
        "breakeven": "be",
        "logical_exit": "lx",
        "take_profit": "tp",
        "stop_loss": "sl",
    }.get(intent, intent[:8])
