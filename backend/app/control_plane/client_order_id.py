from __future__ import annotations

import re
from uuid import UUID, uuid4

from backend.app.orders.models import InternalOrderIntent


_SUPPORTED_INTENTS = {intent.value for intent in InternalOrderIntent}
_CLIENT_ORDER_ID_RE = re.compile(
    r"^(?P<program>[a-z0-9]{2,12})-(?P<deployment>[0-9a-f]{8})-"
    r"(?P<intent>open|close|tp|sl|scale)-(?P<rand>[0-9a-f]{8})$"
)


def build_program_client_order_id(
    program_name: str,
    deployment_id: UUID,
    intent: str | InternalOrderIntent = InternalOrderIntent.OPEN,
) -> str:
    normalized_intent = intent.value if isinstance(intent, InternalOrderIntent) else str(intent)
    if normalized_intent not in _SUPPORTED_INTENTS:
        raise ValueError(f"unsupported order intent: {intent}")
    return f"{_program_abbrev(program_name)}-{deployment_id.hex[:8]}-{normalized_intent}-{uuid4().hex[:8]}"


def parse_order_intent(client_order_id: str) -> str:
    match = _CLIENT_ORDER_ID_RE.fullmatch(client_order_id)
    if match is None:
        return "unknown"
    return match.group("intent")


def parse_order_deployment_id(client_order_id: str) -> str | None:
    match = _CLIENT_ORDER_ID_RE.fullmatch(client_order_id)
    if match is None:
        return None
    return match.group("deployment")


def _program_abbrev(program_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", program_name.lower())
    if len(normalized) < 2:
        normalized = "utos"
    return normalized[:12]
