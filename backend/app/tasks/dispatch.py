"""Small task-dispatch helpers used by API routes and task fan-out.

Celery broker availability should not turn an already-committed user action
into a 500 response. Callers that need strict dispatch guarantees can still use
``task.delay`` directly; review/API paths should use ``enqueue_task``.
"""

import logging

from celery.app.task import Task
from kombu.exceptions import KombuError, OperationalError

logger = logging.getLogger(__name__)


def enqueue_task(task: Task, *args, **kwargs) -> bool:
    try:
        task.delay(*args, **kwargs)
    except (KombuError, OperationalError, OSError) as exc:
        logger.warning(
            "Could not enqueue Celery task %s with args=%s kwargs=%s: %s",
            task.name,
            args,
            kwargs,
            exc,
        )
        return False
    return True
