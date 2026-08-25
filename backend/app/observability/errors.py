"""Explainable error responses.

Every error returned to a developer/operator includes a human-readable
explanation, a technical explanation, the likely cause, a suggested fix,
and the correlation IDs (request_id/batch_id/task_id) needed to find the
matching log lines -- not just an HTTP status code and a generic message.

Two entry points, both wired up in app.main:
  - ExplainedError: raise this directly from a route when you already know
    exactly what went wrong and want full control over the message.
  - unhandled_exception_handler: the catch-all for everything else. It
    classifies the exception (translate_exception) into the same envelope
    shape, so callers never have to guess whether an error will come back
    "nicely explained" or not.
"""

from __future__ import annotations

import logging
import uuid
import zipfile
from dataclasses import dataclass, field

import redis
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError as DBOperationalError

from app.observability.context import current_context

logger = logging.getLogger("cardflow.errors")


@dataclass
class ExplainedError(Exception):
    human_explanation: str
    technical_explanation: str
    likely_cause: str
    suggested_fix: str
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    extra: dict = field(default_factory=dict)


def translate_exception(exc: Exception) -> ExplainedError:
    if isinstance(exc, zipfile.BadZipFile):
        return ExplainedError(
            human_explanation="The uploaded ZIP file couldn't be read.",
            technical_explanation=f"zipfile raised BadZipFile: {exc}",
            likely_cause=(
                "The archive is corrupted, truncated (upload interrupted "
                "partway through), or isn't actually a ZIP file."
            ),
            suggested_fix=(
                "Re-export the ZIP from the source and re-upload. If it "
                "still fails, try opening the file locally first to "
                "confirm it isn't corrupted."
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    if isinstance(exc, redis.RedisError):
        return ExplainedError(
            human_explanation="A background service (Redis) isn't reachable right now.",
            technical_explanation=f"{type(exc).__name__}: {exc}",
            likely_cause="Redis is down, restarting, or unreachable from this container.",
            suggested_fix=(
                "Check `docker compose ps redis` and `docker compose logs "
                "redis`. GET /api/health/redis has live status."
            ),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if isinstance(exc, DBOperationalError):
        return ExplainedError(
            human_explanation="The database isn't reachable right now.",
            technical_explanation=f"{type(exc).__name__}: {exc}",
            likely_cause="Postgres is down, restarting, or out of connections.",
            suggested_fix=(
                "Check `docker compose ps postgres` and `docker compose "
                "logs postgres`. GET /api/health/database has live status."
            ),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if isinstance(exc, (BotoCoreError, ClientError)):
        return ExplainedError(
            human_explanation="Image storage (R2) rejected or couldn't complete a request.",
            technical_explanation=f"{type(exc).__name__}: {exc}",
            likely_cause="Wrong/expired R2 credentials, wrong bucket name, or R2 is unreachable.",
            suggested_fix=(
                "Verify R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / "
                "R2_SECRET_ACCESS_KEY / R2_BUCKET_NAME in backend/.env. "
                "GET /api/health/storage has live status."
            ),
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return ExplainedError(
            human_explanation="The server ran out of disk space.",
            technical_explanation=str(exc),
            likely_cause="Local disk (logs, temp files, or the Docker volume) is full.",
            suggested_fix="Free up disk space on the host, then retry.",
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
        )
    if isinstance(exc, PermissionError):
        return ExplainedError(
            human_explanation="The server couldn't access a file or resource it needed.",
            technical_explanation=str(exc),
            likely_cause="A filesystem/volume permission mismatch, often after a deploy or image change.",
            suggested_fix="Check container volume ownership/permissions on the host.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if isinstance(exc, ValueError) and "crop" in str(exc).lower():
        return ExplainedError(
            human_explanation="This image couldn't be auto-cropped.",
            technical_explanation=str(exc),
            likely_cause=(
                "OpenCV couldn't find a card-shaped contour against the "
                "scan background (bad lighting, no card present, or an "
                "unusual background color)."
            ),
            suggested_fix=(
                "Re-scan against the standard dark background, or crop "
                "manually -- the scan is flagged crop_failed and doesn't "
                "block the rest of the batch."
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return ExplainedError(
        human_explanation="Something went wrong processing your request.",
        technical_explanation=f"{type(exc).__name__}: {exc}",
        likely_cause="Unclassified error -- see the stack trace in the server logs for this request_id.",
        suggested_fix="Check the logs for this request_id/task_id, or retry.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _envelope(err: ExplainedError) -> dict:
    ctx = current_context()
    return {
        "error_id": uuid.uuid4().hex[:12],
        "human_explanation": err.human_explanation,
        "technical_explanation": err.technical_explanation,
        "likely_cause": err.likely_cause,
        "suggested_fix": err.suggested_fix,
        "request_id": ctx.get("request_id"),
        "batch_id": ctx.get("batch_id"),
        "task_id": ctx.get("task_id"),
        **err.extra,
    }


async def explained_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ExplainedError):
        err = translate_exception(exc)
    else:
        err = exc
    body = _envelope(err)
    logger.error(
        "explained error",
        extra={"status_code": err.status_code, **{k: v for k, v in body.items() if k != "error_id"}},
    )
    return JSONResponse(status_code=err.status_code, content=body)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    err = translate_exception(exc)
    body = _envelope(err)
    logger.error(
        "unhandled exception",
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"status_code": err.status_code, **{k: v for k, v in body.items() if k != "error_id"}},
    )
    return JSONResponse(status_code=err.status_code, content=body)
