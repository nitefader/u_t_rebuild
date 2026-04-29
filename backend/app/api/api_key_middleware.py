"""Optional shared-secret gate for the HTTP API.

When ``UTOS_API_KEY`` is set, every request must send the same value via
``X-UTOS-API-Key`` or ``Authorization: Bearer <key>``. When unset, the
middleware is a no-op (localhost / trusted-network deployments unchanged).
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

API_KEY_ENV = "UTOS_API_KEY"


class OptionalApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        expected = (os.getenv(API_KEY_ENV) or "").strip()
        if not expected:
            return await call_next(request)

        # WebSocket handshakes use a separate ASGI scope; do not block upgrades here.
        if request.scope.get("type") != "http":
            return await call_next(request)

        path = request.url.path
        if path in ("/docs", "/redoc", "/openapi.json") or path.startswith("/docs/"):
            return await call_next(request)

        header_key = (request.headers.get("x-utos-api-key") or "").strip()
        auth = request.headers.get("authorization") or ""
        bearer = ""
        if auth.lower().startswith("bearer "):
            bearer = auth[7:].strip()

        if header_key and secrets.compare_digest(header_key, expected):
            return await call_next(request)
        if bearer and secrets.compare_digest(bearer, expected):
            return await call_next(request)

        return JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)
