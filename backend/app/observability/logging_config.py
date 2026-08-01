"""Structured JSON logging, shared by the API process and every Celery
worker process so both produce the exact same log shape.

One JSON object per line on stdout -- greppable/jq-able directly out of
`docker compose logs`, and needs no parsing step if a log shipper is ever
added later. No new dependency: this is a stdlib logging.Formatter, which
is all a single-VM deployment like this one (see docker-compose.yml) needs.
"""

from __future__ import annotations

import json
import logging
import socket
import time
import traceback

from app.observability.context import current_context

# Redacted if present under any of these keys, anywhere in a log line --
# the record's own fields, `extra=`, or the ambient request/task context.
# This is a belt-and-suspenders safety net: call sites should never pass
# secrets into logging in the first place, but a field renamed or reused
# later shouldn't silently start leaking one.
_REDACTED_KEYS = {
    "password",
    "passwd",
    "secret",
    "secret_key",
    "app_passcode",
    "token",
    "access_token",
    "refresh_token",
    "jwt",
    "authorization",
    "r2_secret_access_key",
    "r2_access_key_id",
    "redis_auth_url",
    "database_url",  # embeds the DB password
}

_STANDARD_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
_HOSTNAME = socket.gethostname()


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, environment: str) -> None:
        super().__init__()
        self.service = service
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": (
                time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                + f".{int(record.msecs):03d}Z"
            ),
            "level": record.levelname,
            "service": self.service,
            "environment": self.environment,
            "hostname": _HOSTNAME,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Ambient context: request_id, batch_id, task_id, worker_name,
        # worker_pid, user_id, processing_stage, image_name, ... (see
        # app.observability.context / celery_signals / middleware).
        payload.update(current_context())

        # Anything the call site passed via extra={...}.
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_KEYS or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            exc_type, exc_value, _ = record.exc_info
            payload["exception_type"] = exc_type.__name__ if exc_type else None
            payload["exception_message"] = str(exc_value) if exc_value else None
            # Capped so one runaway traceback can't dominate log storage.
            payload["stack_trace"] = "".join(
                traceback.format_exception(*record.exc_info)
            )[-4000:]

        for key in list(payload):
            if key.lower() in _REDACTED_KEYS:
                payload[key] = "***REDACTED***"

        return json.dumps(payload, default=str)


def setup_logging(service: str) -> None:
    """Install the JSON formatter on the root logger.

    Idempotent (clears existing handlers first), so it's safe to call more
    than once in the same process -- which happens: Celery calls this once
    per worker process (see celery_signals.py's celeryd_init /
    worker_process_init handlers).
    """
    from app.config import settings  # local import: avoids a config <->
    # logging import-order dependency at module load time

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(service=service, environment=settings.environment))
    root.addHandler(handler)

    # Third-party connection-pool/retry chatter would otherwise bury
    # pipeline events at INFO level.
    for noisy in ("botocore", "boto3", "urllib3", "s3transfer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
