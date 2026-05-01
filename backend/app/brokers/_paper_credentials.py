"""Shared helper for resolving Alpaca paper-account credentials from environment.

Operator tools call ``resolve_paper_credentials()`` instead of inlining
``os.getenv`` calls. The runtime composition root reads credentials from the
encrypted ``BrokerCredentialStore``; tools that run outside the composition
root (CLI scripts) use this single helper so the env-var names stay in one
place.

Environment variables consumed:
    ALPACA_API_KEY    — Alpaca API key for the paper account.
    ALPACA_SECRET_KEY — Alpaca secret key for the paper account.
"""

from __future__ import annotations

import os


_KEY_VAR = "ALPACA_API_KEY"
_SECRET_VAR = "ALPACA_SECRET_KEY"


def resolve_paper_credentials() -> tuple[str, str]:
    """Return ``(api_key, secret_key)`` from environment variables.

    Raises ``RuntimeError`` with a clear message when either variable is
    absent or empty so tools surface a human-readable error rather than a
    cryptic ``AlpacaBrokerError: missing_credentials``.
    """
    api_key = os.getenv(_KEY_VAR, "").strip()
    secret_key = os.getenv(_SECRET_VAR, "").strip()
    missing: list[str] = []
    if not api_key:
        missing.append(_KEY_VAR)
    if not secret_key:
        missing.append(_SECRET_VAR)
    if missing:
        raise RuntimeError(
            f"Alpaca paper credentials missing from environment: {', '.join(missing)}. "
            "Set these variables in your .env file before running operator tools."
        )
    return api_key, secret_key
