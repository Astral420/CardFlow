"""Small task-dispatch helpers used by API routes and task fan-out.

Celery broker availability should not turn an already-committed user action
into a 500 response. Callers that need strict dispatch guarantees can still use
``task.delay`` directly; review/API paths should use ``enqueue_task``.
"""

import logging

from celery.app.task import Task
from kombu.exceptions import KombuError, OperationalError

from app.observability import redis_state

logger = logging.getLogger("cardflow.dispatch")


def enqueue_task(task: Task, *args, **kwargs) -> bool:
    try:
        task.delay(*args, **kwargs)
    except (KombuError, OperationalError, OSError) as exc:
        logger.warning(
            "could not enqueue Celery task -- broker unreachable, is Redis up?",
            extra={
                "task_name": task.name,
                "exception_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )
        redis_state.incr_counter("dispatch_failures")
        return False
    return True
