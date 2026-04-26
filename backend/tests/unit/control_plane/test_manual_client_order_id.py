"""Pin contracts for manual client_order_id minting + parsing.

The DE memo (2026-04-26) explicitly required these contracts so program
code that filters by deployment_id correctly skips manual orders, and
``manual_trade.py`` mints a recognizable shape.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from backend.app.control_plane.client_order_id import (
    _MANUAL_CLIENT_ORDER_ID_RE,
    build_manual_client_order_id,
    is_manual_client_order_id,
    parse_manual_account_id,
    parse_order_deployment_id,
    parse_order_intent,
)


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")


def test_build_manual_client_order_id_shape() -> None:
    cid = build_manual_client_order_id(ACCOUNT_ID, intent="open")
    assert cid.startswith(f"manual-{ACCOUNT_ID.hex[:8]}-open-")
    assert _MANUAL_CLIENT_ORDER_ID_RE.fullmatch(cid) is not None
    assert is_manual_client_order_id(cid) is True


def test_build_manual_supports_close_and_reduce() -> None:
    for intent in ("open", "close", "reduce"):
        cid = build_manual_client_order_id(ACCOUNT_ID, intent=intent)
        assert _MANUAL_CLIENT_ORDER_ID_RE.fullmatch(cid) is not None
        assert parse_order_intent(cid) == intent


def test_build_manual_rejects_unsupported_intent() -> None:
    for bad in ("tp", "sl", "scale", "unknown"):
        with pytest.raises(ValueError, match="manual order intent"):
            build_manual_client_order_id(ACCOUNT_ID, intent=bad)


def test_parse_order_deployment_id_returns_none_for_manual() -> None:
    """Critical: deployment-scoped queries must skip manual orders.

    Programs filter "orders for this deployment" via this helper. Returning
    something other than ``None`` for a manual order would let manual
    submits leak into deployment-scoped scope filters.
    """
    cid = build_manual_client_order_id(ACCOUNT_ID, intent="open")
    assert parse_order_deployment_id(cid) is None


def test_parse_manual_account_id_returns_account_hex() -> None:
    cid = build_manual_client_order_id(ACCOUNT_ID, intent="close")
    assert parse_manual_account_id(cid) == ACCOUNT_ID.hex[:8]
    # Program-form orders return None.
    assert parse_manual_account_id("utos-deadbeef-open-cafebabe") is None


def test_parse_order_intent_prefers_manual_form_over_program_match() -> None:
    """The program regex is permissive enough to accidentally match a
    manual-prefixed id ("manual" fits the [a-z0-9]{2,12} program abbrev
    slot, account hex fits the deployment slot). The parser checks the
    manual form first so the manual intent label wins."""

    cid = build_manual_client_order_id(ACCOUNT_ID, intent="open")
    assert parse_order_intent(cid) == "open"
    assert parse_order_deployment_id(cid) is None


def test_is_manual_returns_false_for_program_form() -> None:
    assert is_manual_client_order_id("utos-deadbeef-open-cafebabe") is False
    assert is_manual_client_order_id("not-a-client-order-id") is False
    assert is_manual_client_order_id("") is False
