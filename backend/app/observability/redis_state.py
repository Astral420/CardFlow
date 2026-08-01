"""Lightweight, Redis-backed live pipeline state.

This is deliberately NOT a metrics/time-series system -- this app runs as
a single API container and a single worker container on one VM (see
docker-compose.yml), so a handful of Redis hashes/lists that answer
"what's happening right now" and "how has today been trending" are enough,
and they add zero new runtime dependencies. Postgres (the `batches` /
`raw_scans` / etc. tables) remains the durable record of truth; everything
here is disposable, TTL'd, best-effort dashboard state.

All keys live under the `obs:` prefix on the existing auth-Redis
connection (app.redis_client), namespaced away from the session-revocation
keys already stored there (see app.token_store). Every public function
swallows Redis errors rather than raising -- a dashboard hiccup must never
be able to fail an upload, a crop, or an export.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache

from app.redis_client import redis_client

_BATCH_TTL_SECONDS = 2 * 24 * 3600  # live state only; Postgres is authoritative
_RECENT_CAP = 50


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _batch_key(batch_id: int) -> str:
    return f"obs:batch:{batch_id}"


def set_batch_stage(batch_id: int, stage: str, **fields: object) -> None:
    """Record the current pipeline stage for a batch, for the live
    dashboard. Sets `started_at` the first time a batch is seen."""
    key = _batch_key(batch_id)
    mapping = {k: v for k, v in {"stage": stage, "updated_at": now_iso(), **fields}.items() if v is not None}
    try:
        if not redis_client.hexists(key, "started_at"):
            mapping["started_at"] = now_iso()
        redis_client.hset(key, mapping=mapping)
        redis_client.expire(key, _BATCH_TTL_SECONDS)
    except Exception:
        pass


def mark_batch_terminal(batch_id: int, status: str) -> None:
    """status: 'complete' or 'failed'. Also bumps the matching counter."""
    try:
        redis_client.hset(_batch_key(batch_id), mapping={"stage": status, "updated_at": now_iso()})
        redis_client.expire(_batch_key(batch_id), _BATCH_TTL_SECONDS)
        incr_counter(f"batches_{status}")
    except Exception:
        pass


def list_active_batches(limit: int = 30) -> list[dict]:
    """Scan obs:batch:* keys. A full SCAN is fine at this app's scale
    (a family card-selling operation processes at most a handful of
    batches concurrently) -- a real index would be over-engineering here."""
    try:
        results: list[dict] = []
        for key in redis_client.scan_iter(match="obs:batch:*", count=100):
            data = redis_client.hgetall(key)
            if data:
                data["batch_id"] = key.split(":")[-1]
                results.append(data)
            if len(results) >= limit:
                break
        return results
    except Exception:
        return []


def record_stage_duration(stage: str, duration_ms: int, failed: bool = False) -> None:
    """Accumulate count/sum/max for a named stage (a pipeline stage like
    'cropping', or a Celery task name like 'task:hash_crop'). Average is
    derived at read time (duration_ms_sum / count) -- see stage_summary()."""
    key = f"obs:stage:{stage}"
    try:
        pipe = redis_client.pipeline()
        pipe.hincrby(key, "count", 1)
        pipe.hincrbyfloat(key, "duration_ms_sum", duration_ms)
        if failed:
            pipe.hincrby(key, "failed_count", 1)
        pipe.execute()
        current_max = redis_client.hget(key, "duration_ms_max")
        if current_max is None or duration_ms > float(current_max):
            redis_client.hset(key, "duration_ms_max", duration_ms)
    except Exception:
        pass


def stage_summary() -> dict[str, dict]:
    try:
        summary: dict[str, dict] = {}
        for key in redis_client.scan_iter(match="obs:stage:*", count=100):
            stage_name = key.split(":", 2)[-1]
            data = redis_client.hgetall(key)
            count = int(data.get("count", 0) or 0)
            duration_sum = float(data.get("duration_ms_sum", 0) or 0)
            summary[stage_name] = {
                "count": count,
                "failed_count": int(data.get("failed_count", 0) or 0),
                "avg_duration_ms": round(duration_sum / count, 1) if count else None,
                "max_duration_ms": (float(data["duration_ms_max"]) if data.get("duration_ms_max") else None),
            }
        return summary
    except Exception:
        return {}


def push_recent(list_key: str, item: dict, cap: int = _RECENT_CAP) -> None:
    """Prepend `item` to a capped recent-activity list (recent_uploads,
    recent_exports, recent_failures)."""
    try:
        redis_client.lpush(list_key, json.dumps(item, default=str))
        redis_client.ltrim(list_key, 0, cap - 1)
    except Exception:
        pass


def get_recent(list_key: str, limit: int = 20) -> list[dict]:
    try:
        raw = redis_client.lrange(list_key, 0, limit - 1)
        return [json.loads(r) for r in raw]
    except Exception:
        return []


def incr_counter(name: str, by: int = 1) -> None:
    try:
        redis_client.incrby(f"obs:counter:{name}", by)
    except Exception:
        pass


def get_counter(name: str) -> int:
    try:
        value = redis_client.get(f"obs:counter:{name}")
        return int(value) if value else 0
    except Exception:
        return 0


@lru_cache
def _broker_client():
    """Separate connection to the *broker* DB (settings.redis_url) -- the
    rest of this module talks to the auth-DB connection instead (see
    module docstring). Only used for a queue-depth check, so its own
    short-lived, timeout-bounded client is fine."""
    import redis as redis_lib

    from app.config import settings

    return redis_lib.Redis.from_url(
        settings.redis_url, socket_timeout=1.0, socket_connect_timeout=1.0
    )


def broker_queue_depth(queue_name: str = "celery") -> int | None:
    """LLEN on Celery's Redis-transport queue list -- "celery" is the
    default queue name this app never overrides (see app/celery_app.py)."""
    try:
        return _broker_client().llen(queue_name)
    except Exception:
        return None
