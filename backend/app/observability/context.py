"""Request/task-scoped fields propagated into every structured log line.

Held in a single contextvars.ContextVar (not one var per field) so a
logging.Filter can pull the whole dict in one read, and so nested binds
(request -> celery task -> pipeline stage) layer additively: each `bind()`
merges onto whatever the caller already set, and restores it afterwards.

Contextvars are process/thread/async-task local. They do NOT cross a
Celery broker hop -- a request_id bound while an API route enqueues a task
will not automatically appear in the worker process that later executes
it (see app.observability.celery_signals, which rebuilds its own context
from the task's own identity instead: task_id, batch_id, worker_name).
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_CONTEXT: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "observability_context", default={}
)


def current_context() -> dict[str, Any]:
    return dict(_CONTEXT.get())


def set_context(**fields: Any) -> contextvars.Token:
    """Merge `fields` into the active context immediately, returning a
    token that undoes exactly this merge later via reset_context().

    Prefer `bind()` (below) wherever the affected block is lexically
    scoped. Use set_context/reset_context directly only where the two
    ends genuinely happen in separate callbacks -- e.g. Celery's
    task_prerun / task_postrun signals, which fire at different times
    with no shared `with` block available.
    """
    previous = _CONTEXT.get()
    merged = {**previous, **{k: v for k, v in fields.items() if v is not None}}
    return _CONTEXT.set(merged)


def reset_context(token: contextvars.Token | None) -> None:
    if token is None:
        return
    try:
        _CONTEXT.reset(token)
    except ValueError:
        # Reset attempted from a different context than the set() call
        # (shouldn't happen given how this module is used, but a stale
        # token must never crash whatever code is trying to clean up).
        pass


@contextmanager
def bind(**fields: Any) -> Iterator[None]:
    """Merge `fields` into context for the duration of the block, then
    restore the prior context -- including if the block raises."""
    token = set_context(**fields)
    try:
        yield
    finally:
        reset_context(token)
