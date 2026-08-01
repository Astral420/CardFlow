"""Structured request logging for every FastAPI request.

Assigns (or reuses, from an inbound X-Request-Id) a request_id, binds it
into context so anything logged while handling the request is tagged with
it, and logs one line per request: method, route, status code, latency,
and the authenticated user if the request carried a valid bearer token.

User resolution is done directly here (reusing app.security's own token
decode/validation) rather than by threading a Request into
app.api.deps.get_current_user[_optional] -- those are plain FastAPI
dependency functions today, called directly (no Request arg) from several
existing tests (see tests/test_rbac.py), so leaving their signatures alone
avoids any risk of breaking that. The trade-off is one extra (cheap,
already-Redis-backed-elsewhere) token decode per authenticated request,
purely for the log line.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.context import bind
from app.security import decode_access_token

logger = logging.getLogger("cardflow.request")


def _resolve_user_id(request: Request) -> int | None:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    try:
        return decode_access_token(auth_header[7:].strip())
    except Exception:
        # Logging enrichment must never be able to break a request.
        return None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        start = time.monotonic()

        with bind(request_id=request_id, user_id=_resolve_user_id(request)):
            try:
                response = await call_next(request)
            except Exception:
                duration_ms = int((time.monotonic() - start) * 1000)
                logger.exception(
                    "unhandled request exception",
                    extra={
                        "method": request.method,
                        "route": request.url.path,
                        "duration_ms": duration_ms,
                    },
                )
                raise

            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "request handled",
                extra={
                    "method": request.method,
                    "route": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            response.headers["X-Request-Id"] = request_id
            return response
