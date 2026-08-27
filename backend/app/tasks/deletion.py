"""Durable background hard-deletion for batches and their R2 objects."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import cast

from celery.app.task import Task
from sqlalchemy import or_

from app import storage
from app.celery_app import celery_app
from app.db import SessionLocal
from app.models import (
    Batch,
    BatchAuditLog,
    BatchExport,
    BatchStatus,
    CardCrop,
    RawScan,
)
from app.observability import redis_state
from app.observability.events import log_event
from app.tasks.dispatch import enqueue_task

logger = logging.getLogger("cardflow.deletion")


def _restore_failed_deletion(db, batch_id: int) -> None:
    """Restore the pre-delete status after the final failed attempt."""
    batch = (
        db.query(Batch)
        .filter(Batch.id == batch_id)
        .with_for_update()
        .one_or_none()
    )
    if batch is None or batch.status != BatchStatus.deleting:
        return

    previous_status = batch.deletion_previous_status
    if previous_status is None:
        raise RuntimeError(f"Batch {batch_id} has no deletion_previous_status")

    restored_status = BatchStatus(previous_status)
    if restored_status == BatchStatus.deleting:
        raise RuntimeError(f"Batch {batch_id} has invalid deletion_previous_status")

    batch.status = restored_status
    batch.deletion_requested_at = None
    batch.deletion_previous_status = None
    batch.deletion_requested_by = None
    db.commit()


@celery_app.task(name="delete_batch", bind=True, max_retries=2, default_retry_delay=30)
def _delete_batch(self, batch_id: int) -> None:
    """Delete DB rows first, then perform best-effort R2 cleanup.

    Failures before the database commit are retried while the batch remains
    hidden in ``deleting``. Only the final failed attempt restores its prior
    status. Once the DB commit succeeds, deletion is irreversible and all
    remaining audit/storage/observability work is deliberately non-fatal.
    """
    db = SessionLocal()
    try:
        try:
            # Serialize against final writes from pipeline/export work and
            # make duplicate deliveries idempotent.
            batch = (
                db.query(Batch)
                .filter(Batch.id == batch_id)
                .with_for_update()
                .one_or_none()
            )
            if batch is None:
                logger.info("delete_batch: batch %d is already absent", batch_id)
                return
            if batch.status != BatchStatus.deleting:
                logger.warning(
                    "delete_batch: batch %d is %s, not deleting; ignoring delivery",
                    batch_id,
                    batch.status.value,
                )
                return

            r2_keys: list[str] = [storage.temp_upload_key(batch_id)]
            scans = db.query(RawScan).filter(RawScan.batch_id == batch_id).all()
            for scan in scans:
                if scan.r2_key_raw:
                    r2_keys.append(scan.r2_key_raw)

            crop_ids = [scan.crop.id for scan in scans if scan.crop is not None]
            if crop_ids:
                crops = db.query(CardCrop).filter(CardCrop.id.in_(crop_ids)).all()
                r2_keys.extend(crop.r2_key_cropped for crop in crops if crop.r2_key_cropped)

            exports = db.query(BatchExport).filter(BatchExport.batch_id == batch_id).all()
            r2_keys.extend(export.r2_key for export in exports if export.r2_key)
            # Avoid inflating audit counts if legacy/bad rows point at one key.
            r2_keys = list(dict.fromkeys(r2_keys))

            audit = BatchAuditLog(
                batch_id=batch_id,
                performed_by=batch.deletion_requested_by,
                action="hard_delete",
                source_label=batch.source_label,
                batch_status=batch.deletion_previous_status,
                scan_count=len(scans),
                r2_keys_deleted=0,
                r2_keys_failed=0,
            )
            db.add(audit)
            db.flush()
            # Snapshot everything needed after the irreversible commit while
            # the ORM objects are definitely live and the DB is reachable.
            audit_id = audit.id
            performed_by = audit.performed_by
            source_label = audit.source_label
            scan_count = audit.scan_count
            db.delete(batch)
            db.commit()
        except Exception as exc:
            db.rollback()
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc)

            try:
                _restore_failed_deletion(db, batch_id)
                logger.error(
                    "delete_batch failed after retries; restored batch %d",
                    batch_id,
                    exc_info=(type(exc), exc, exc.__traceback__),
                )
            except Exception as restore_exc:
                db.rollback()
                logger.critical(
                    "delete_batch failed and batch %d could not be restored",
                    batch_id,
                    exc_info=(type(restore_exc), restore_exc, restore_exc.__traceback__),
                )
            raise

        r2_deleted = 0
        r2_failed = 0
        failure_notes: list[str] = []
        for key in r2_keys:
            try:
                storage.delete_object(key)
                r2_deleted += 1
            except Exception as exc:
                r2_failed += 1
                failure_notes.append(f"{key}: {exc}")
                logger.warning(
                    "R2 delete failed for key %s (batch %d): %s",
                    key,
                    batch_id,
                    exc,
                    extra={"batch_id": batch_id, "r2_key": key},
                )

        try:
            persisted_audit = db.get(BatchAuditLog, audit_id)
            if persisted_audit is not None:
                persisted_audit.r2_keys_deleted = r2_deleted
                persisted_audit.r2_keys_failed = r2_failed
                persisted_audit.notes = "; ".join(failure_notes) or None
                db.commit()
        except Exception:
            db.rollback()
            logger.warning(
                "Failed to update deletion audit %d for batch %d",
                audit_id,
                batch_id,
                exc_info=True,
            )

        try:
            log_event(
                "batch hard deleted",
                batch_id=batch_id,
                performed_by=performed_by,
                source_label=source_label,
                scan_count=scan_count,
                r2_keys_deleted=r2_deleted,
                r2_keys_failed=r2_failed,
            )
            redis_state.push_recent(
                "obs:recent_batch_deletes",
                {
                    "batch_id": batch_id,
                    "source_label": source_label,
                    "performed_by": performed_by,
                    "scan_count": scan_count,
                    "r2_keys_deleted": r2_deleted,
                    "r2_keys_failed": r2_failed,
                    "at": redis_state.now_iso(),
                },
            )
        except Exception:
            logger.warning(
                "Failed to publish deletion observability for batch %d",
                batch_id,
                exc_info=True,
            )
    finally:
        db.close()


delete_batch_task = cast(Task, _delete_batch)


def enqueue_stuck_deletions(
    *, min_age_minutes: int = 5, batch_id: int | None = None
) -> tuple[int, int]:
    """Re-dispatch stale durable deletion requests.

    Returns ``(dispatched, failed)``. Duplicate delivery is safe because the
    deletion task locks and rechecks the batch row before doing any work.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=min_age_minutes)
    db = SessionLocal()
    try:
        query = db.query(Batch).filter(Batch.status == BatchStatus.deleting)
        if batch_id is not None:
            query = query.filter(Batch.id == batch_id)
        else:
            query = query.filter(
                or_(
                    Batch.deletion_requested_at.is_(None),
                    Batch.deletion_requested_at <= cutoff,
                )
            )
        ids = [row.id for row in query.order_by(Batch.id).all()]
    finally:
        db.close()

    dispatched = sum(1 for candidate_id in ids if enqueue_task(delete_batch_task, candidate_id))
    return dispatched, len(ids) - dispatched
