from celery import Celery

from app.config import settings

celery_app = Celery(
    "card_tool",
    broker=settings.redis_url,
    backend=settings.redis_result_backend_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

import app.observability.celery_signals  # noqa: E402,F401  registers structured-logging + task-lifecycle signal handlers
import app.tasks  # noqa: E402,F401  registers @shared_task functions
