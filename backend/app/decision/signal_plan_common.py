from __future__ import annotations


class SignalPlanBuilderError(ValueError):
    """Raised when a candidate cannot become a neutral SignalPlan."""


# T-3 (Bracket Program): rule prefix used when stop/target prices are computed
# *post-fill* by the OrderManager rather than pre-baked in the SignalPlan.
# Format is ``post_fill_pct:<pct>``. The ProtectiveOrderPlacer parses this back.
POST_FILL_PCT_RULE_PREFIX = "post_fill_pct"


def post_fill_pct_rule(pct: float) -> str:
    """Encode a post-fill percent for SignalPlanStop.rule / SignalPlanTarget.rule.

    Doctrine: SignalPlan stays neutral and quantity-free. When the operator
    declared "5% stop / 10% target" on a market entry, the *concrete* prices
    can only be known after the fill price is known. The builder encodes the
    operator's intent here; the runtime decodes it after BrokerSync confirms
    the entry fill.
    """

    if pct <= 0:
        raise SignalPlanBuilderError(f"post_fill_pct must be > 0; got {pct}")
    return f"{POST_FILL_PCT_RULE_PREFIX}:{pct}"


def parse_post_fill_pct(rule: str | None) -> float | None:
    """Parse ``post_fill_pct:<pct>`` back to a float. Returns None on miss."""

    if not rule or ":" not in rule:
        return None
    prefix, _, value = rule.partition(":")
    if prefix != POST_FILL_PCT_RULE_PREFIX:
        return None
    try:
        pct = float(value)
    except ValueError:
        return None
    if pct <= 0:
        return None
    return pct
