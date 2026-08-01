"""Celery lifecycle -> structured logs + Redis-backed counters.

Registered once via `import app.observability.celery_signals` in
app/celery_app.py, so it takes effect for both the API process (which
imports celery_app.py just to register tasks, and never fires these
signals) and every actual `celery worker` process.

Covers:
  - JSON logging setup inside worker processes (celeryd_init fires once in
    the main/arbiter process when `celery worker` actually starts;
    worker_process_init fires again in each prefork child -- see their
    handlers below for why both are wired up).
  - Queue wait time: before_task_publish stamps a timestamp into the
    message headers; task_prerun reads it back to compute how long the
    task sat on the queue before a worker picked it up.
  - Per-task start/finish/retry/failure logging with duration, worker
    name, worker PID, and retry count -- independent of and complementary
    to app.observability.events.stage(), which each task body uses for its
    own business-level stage (batch_id, image_name, etc.). The two layers
    merge naturally through the shared context: a log line from inside a
    task carries both the Celery-level fields set here and the
    pipeline-level fields set by that task's own stage() call.
"""

from __future__ import annotations

import logging
import os
import time

from celery.signals import (
    before_task_publish,
    celeryd_init,
    task_failure,
    task_postrun,
    task_prerun,
    task_retry,
    worker_process_init,
    worker_ready,
    worker_shutdown,
)

from app.observability import redis_state
from app.observability.context import reset_context, set_context
from app.observability.logging_config import setup_logging

logger = logging.getLogger("cardflow.celery")

# task_id -> (context token, monotonic start time). Populated in
# task_prerun, consumed in task_postrun (which Celery calls for both
# success and failure outcomes, so cleanup always happens exactly once
# per task execution).
_running: dict[str, tuple[object, float]] = {}


@celeryd_init.connect
def _on_celeryd_init(**_kwargs) -> None:
    setup_logging(service="cardflow-worker")


@worker_process_init.connect
def _on_worker_process_init(**_kwargs) -> None:
    setup_logging(service="cardflow-worker")


@worker_ready.connect
def _on_worker_ready(sender=None, **_kwargs) -> None:
    logger.info("celery worker ready", extra={"worker_name": getattr(sender, "hostname", None)})


@worker_shutdown.connect
def _on_worker_shutdown(sender=None, **_kwargs) -> None:
    logger.info("celery worker shutdown", extra={"worker_name": getattr(sender, "hostname", None)})


@before_task_publish.connect
def _stamp_enqueued_at(headers=None, **_kwargs) -> None:
    if headers is not None:
        headers["enqueued_at"] = time.time()


@task_prerun.connect
def _on_task_prerun(sender=None, task_id=None, task=None, **_kwargs) -> None:
    enqueued_at = getattr(task.request, "enqueued_at", None) if task is not None else None
    queue_wait_ms = int((time.time() - float(enqueued_at)) * 1000) if enqueued_at else None
    worker_name = getattr(task.request, "hostname", None) if task is not None else None
    retries = getattr(task.request, "retries", 0) if task is not None else 0

    token = set_context(
        task_id=task_id,
        task_name=getattr(sender, "name", None),
        worker_name=worker_name,
        worker_pid=os.getpid(),
        retry_count=retries,
    )
    _running[task_id] = (token, time.monotonic())

    logger.info(
        "celery task started",
        extra={"status": "started", "queue_wait_ms": queue_wait_ms},
    )
    redis_state.incr_counter("tasks_started")


@task_postrun.connect
def _on_task_postrun(sender=None, task_id=None, state=None, **_kwargs) -> None:
    entry = _running.pop(task_id, None)
    token, start = entry if entry else (None, None)
    duration_ms = int((time.monotonic() - start) * 1000) if start is not None else None

    logger.info(
        "celery task finished",
        extra={"status": state, "duration_ms": duration_ms},
    )
    if duration_ms is not None:
        redis_state.record_stage_duration(
            f"task:{getattr(sender, 'name', 'unknown')}",
            duration_ms,
            failed=(state == "FAILURE"),
        )
    redis_state.incr_counter("tasks_succeeded" if state == "SUCCESS" else "tasks_finished_other")

    reset_context(token)


@task_retry.connect
def _on_task_retry(sender=None, reason=None, **_kwargs) -> None:
    logger.warning(
        "celery task retrying",
        extra={"status": "retrying", "retry_reason": str(reason)[:300]},
    )
    redis_state.incr_counter("tasks_retried")


@task_failure.connect
def _on_task_failure(sender=None, task_id=None, exception=None, **_kwargs) -> None:
    exc_info = (type(exception), exception, exception.__traceback__) if exception else None
    logger.error("celery task failed", exc_info=exc_info, extra={"status": "failed"})
    redis_state.incr_counter("tasks_failed")
    redis_state.push_recent(
        "obs:recent_failures",
        {
            "task_id": task_id,
            "task_name": getattr(sender, "name", None),
            "exception_type": type(exception).__name__ if exception else None,
            "message": str(exception)[:500] if exception else None,
            "at": redis_state.now_iso(),
        },
    )
