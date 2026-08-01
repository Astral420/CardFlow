"""Pipeline-stage logging helpers used by Celery tasks and API routes.

`stage()` emits a "<name> started" / "<name> finished" (or "failed") pair
of structured log lines around a block of work, tags every log line
emitted from inside that block with `processing_stage=<name>` and
`batch_id=<id>` via app.observability.context, and mirrors the outcome
into Redis (current stage for the live dashboard, running duration stats
for the metrics summary). `log_event()` is for one-off lines that aren't
themselves a start/finish pair -- a single per-image outcome, a validation
count, a rejection.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

from app.observability import redis_state
from app.observability.context import bind

logger = logging.getLogger("cardflow.pipeline")


@contextmanager
def stage(name: str, batch_id: int | None = None, **fields: object) -> Iterator[None]:
    start = time.monotonic()
    with bind(processing_stage=name, batch_id=batch_id, **fields):
        logger.info(f"{name} started", extra={"status": "started"})
        if batch_id is not None:
            redis_state.set_batch_stage(batch_id, name)
        try:
            yield
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.exception(
                f"{name} failed",
                extra={"status": "failed", "duration_ms": duration_ms},
            )
            redis_state.record_stage_duration(name, duration_ms, failed=True)
            if batch_id is not None:
                redis_state.push_recent(
                    "obs:recent_failures",
                    {
                        "batch_id": batch_id,
                        "stage": name,
                        "exception_type": type(exc).__name__,
                        "message": str(exc)[:500],
                        "at": redis_state.now_iso(),
                    },
                )
            raise
        else:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                f"{name} finished",
                extra={"status": "finished", "duration_ms": duration_ms},
            )
            redis_state.record_stage_duration(name, duration_ms, failed=False)


def log_event(message: str, level: int = logging.INFO, **fields: object) -> None:
    """A single structured log line, tagged with whatever fields the
    caller passes (batch_id, image_name, zip_filename, skipped_reason,
    ...). Does not open/close a stage -- use `stage()` for that."""
    logger.log(level, message, extra=fields)
