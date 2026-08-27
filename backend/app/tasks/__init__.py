# `celery_app` must exist (and become Celery's "current app") before any
# @shared_task-decorated function below is defined or called, otherwise
# .delay()/.apply_async() silently falls back to Celery's bare default app
# (amqp://localhost, not our configured Redis broker).
from app.celery_app import celery_app  # noqa: F401
from app.tasks import crop, deletion, duplicates, extract, hashing  # noqa: E402,F401
