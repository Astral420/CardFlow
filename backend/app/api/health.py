"""Health and pipeline-observability endpoints.

Kept public (no bearer auth), matching the original single GET /api/health
check this replaces -- standard practice for endpoints meant to be hit by
a load balancer, an uptime check, or a local dashboard without a token,
and consistent with how the frontend already polls /api/health for its
"Operational" badge (see frontend/src/lib/use-health.ts). None of these
endpoints return card images or PII -- if this deployment ever wants them
private, restrict the /api/health/* and /api/ops/* paths at the Cloudflare
Tunnel layer (already part of this app's deploy topology) rather than
adding app-level auth here.

GET /api/health/pipeline is the single call the ops dashboard
(GET /api/ops/dashboard) polls -- see /OBSERVABILITY.md for the full
health-check and dashboard writeup.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import redis
from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app import storage
from app.celery_app import celery_app
from app.config import settings
from app.db import get_db
from app.models import Batch, BatchStatus
from app.observability import redis_state
from app.redis_client import redis_client

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
def health() -> dict:
    # Preserves the original {"status": "ok"} contract exactly (the
    # frontend only checks that field) while adding a bit more context
    # for anyone hitting this directly.
    return {"status": "ok", "service": "cardflow-api", "environment": settings.environment}


@router.get("/redis")
def health_redis() -> dict:
    start = time.monotonic()
    try:
        redis_client.ping()
        return {"status": "ok", "latency_ms": round((time.monotonic() - start) * 1000, 1)}
    except redis.RedisError as exc:
        return {"status": "error", "error": str(exc)}


@router.get("/database")
def health_database(db: Session = Depends(get_db)) -> dict:
    start = time.monotonic()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "latency_ms": round((time.monotonic() - start) * 1000, 1)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@router.get("/storage")
def health_storage() -> dict:
    start = time.monotonic()
    try:
        storage.health_check()
        return {
            "status": "ok",
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "bucket": settings.r2_bucket_name,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@router.get("/celery")
def health_celery() -> dict:
    try:
        inspect = celery_app.control.inspect(timeout=0.5)
        ping = inspect.ping() or {}
        if not ping:
            # No point spending another 2 round-trip timeouts on
            # active()/stats() when nothing answered ping -- and this is
            # exactly the state (workers down) where a fast answer matters
            # most, both here and for GET /api/health/pipeline, which
            # calls this on every dashboard poll.
            return {
                "status": "error",
                "worker_count": 0,
                "workers": [],
                "queue_depth": redis_state.broker_queue_depth(),
            }
        active = inspect.active() or {}
        stats = inspect.stats() or {}
        workers = [
            {
                "worker": name,
                "active_tasks": len(active.get(name, [])),
                "concurrency": (stats.get(name) or {}).get("pool", {}).get("max-concurrency"),
            }
            for name in ping
        ]
        return {
            "status": "ok",
            "worker_count": len(workers),
            "workers": workers,
            "queue_depth": redis_state.broker_queue_depth(),
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _derive_alerts(*, celery_status: dict, redis_status: dict, active_batches: list[dict],
                    tasks_started: int, tasks_failed: int) -> list[str]:
    alerts: list[str] = []
    if celery_status.get("status") != "ok":
        alerts.append("No Celery workers are responding to `inspect ping` -- the pipeline is stalled.")
    if redis_status.get("status") != "ok":
        alerts.append("Redis is not reachable.")
    if tasks_started > 10 and tasks_failed / tasks_started > 0.2:
        alerts.append(f"High task failure rate: {tasks_failed}/{tasks_started} Celery tasks have failed.")

    now = time.time()
    # rotation_review / duplicate_review wait on a human reviewer, often
    # for hours -- that's expected, not a stall. Only alert when a batch is
    # stuck in a fully-automated stage past a reasonable processing time.
    automated_stages = {"extracting", "cropping", "zip_extraction", "hashing", "duplicate_detection"}
    for batch in active_batches:
        updated_at = batch.get("updated_at")
        stage = batch.get("stage")
        if not updated_at or stage not in automated_stages:
            continue
        try:
            age_seconds = now - datetime.fromisoformat(updated_at).timestamp()
        except ValueError:
            continue
        if age_seconds > 600:
            alerts.append(
                f"Batch {batch.get('batch_id')} has been stuck on '{stage}' "
                f"for over {int(age_seconds // 60)} minutes."
            )
    return alerts


@router.get("/pipeline")
def health_pipeline(db: Session = Depends(get_db)) -> dict:
    """Everything the ops dashboard needs in one call: live per-batch
    stage, recent uploads/exports/failures, per-stage timings, and derived
    alert conditions -- see /OBSERVABILITY.md's Dashboard section."""
    active_batches = redis_state.list_active_batches(limit=30)

    batches_by_status = {
        (st.value if hasattr(st, "value") else st): count
        for st, count in db.query(Batch.status, func.count(Batch.id)).group_by(Batch.status).all()
    }

    tasks_started = redis_state.get_counter("tasks_started")
    tasks_succeeded = redis_state.get_counter("tasks_succeeded")
    tasks_failed = redis_state.get_counter("tasks_failed")
    tasks_retried = redis_state.get_counter("tasks_retried")

    celery_status = health_celery()
    redis_status = health_redis()
    deleting_rows = (
        db.query(Batch)
        .filter(Batch.status == BatchStatus.deleting)
        .order_by(Batch.deletion_requested_at, Batch.id)
        .all()
    )
    now = datetime.now(timezone.utc)
    deleting_batches = []
    for batch in deleting_rows:
        requested_at = batch.deletion_requested_at
        if requested_at is not None and requested_at.tzinfo is None:
            requested_at = requested_at.replace(tzinfo=now.tzinfo)
        age_seconds = int((now - requested_at).total_seconds()) if requested_at else None
        deleting_batches.append(
            {
                "batch_id": batch.id,
                "source_label": batch.source_label,
                "requested_at": requested_at.isoformat() if requested_at else None,
                "age_seconds": age_seconds,
            }
        )

    alerts = _derive_alerts(
        celery_status=celery_status,
        redis_status=redis_status,
        active_batches=active_batches,
        tasks_started=tasks_started,
        tasks_failed=tasks_failed,
    )
    stale_deletions = [
        item for item in deleting_batches
        if item["age_seconds"] is None or item["age_seconds"] >= 300
    ]
    if stale_deletions:
        ids = ", ".join(str(item["batch_id"]) for item in stale_deletions)
        alerts.append(
            "Stuck batch deletion(s): " + ids + ". Run "
            "`python -m app.commands.retry_stuck_deletions` on the backend."
        )

    return {
        "generated_at": redis_state.now_iso(),
        "batches_by_status": batches_by_status,
        "active_batches": active_batches,
        "recent_uploads": redis_state.get_recent("obs:recent_uploads", limit=15),
        "recent_exports": redis_state.get_recent("obs:recent_exports", limit=15),
        "recent_failures": redis_state.get_recent("obs:recent_failures", limit=20),
        "recent_batch_deletes": redis_state.get_recent("obs:recent_batch_deletes", limit=15),
        "deleting_batches": deleting_batches,
        "stage_timings": redis_state.stage_summary(),
        "task_counters": {
            "started": tasks_started,
            "succeeded": tasks_succeeded,
            "failed": tasks_failed,
            "retried": tasks_retried,
            "failure_rate": round(tasks_failed / tasks_started, 4) if tasks_started else 0,
        },
        "celery": celery_status,
        "redis": redis_status,
        "alerts": alerts,
    }
