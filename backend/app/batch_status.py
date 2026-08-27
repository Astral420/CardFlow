from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Batch,
    BatchStatus,
    CardCrop,
    DuplicateCandidate,
    DuplicateStatus,
    RawScan,
    ScanSide,
    ScanStatus,
)
from app.observability import redis_state


def lock_batch_for_pipeline_write(db: Session, batch_id: int) -> Batch | None:
    """Lock a batch before a worker's final write and reject deletion races.

    A delete request takes the same row lock before setting ``deleting``.
    Work that reached this lock first may finish atomically; work that arrives
    after the transition observes ``deleting`` and must not publish artifacts.
    """
    batch = (
        db.query(Batch)
        .filter(Batch.id == batch_id)
        .with_for_update()
        .one_or_none()
    )
    if batch is None or batch.status == BatchStatus.deleting:
        return None
    return batch


def refresh_batch_status(db: Session, batch_id: int) -> BatchStatus | None:
    """Derive and persist the current batch pipeline status.

    Batch status is operational state, not a separately-owned workflow flag. It
    should reflect the child rows so batches do not get stuck when async tasks
    finish in a different process.
    """
    batch = db.get(Batch, batch_id)
    if batch is None:
        return None

    # Terminal state: once a batch has completed its pipeline, it is done
    # for good and must not be re-derived. Without this guard, a batch can
    # be pulled back into an active stage by state that has nothing to do
    # with its own pipeline -- most notably cross-batch duplicate detection
    # (app.dedup.matching.find_cross_batch_duplicates), which compares new
    # uploads against cards in *every* batch, including already-completed
    # ones. A duplicate candidate created against an old batch's card would
    # otherwise cause that old batch to flip from "complete" back to
    # "duplicate_review" the next time its status happened to be refreshed
    # (e.g. viewing its detail page, or resolving that candidate in the
    # review queue), even though nothing in that batch itself is unfinished.
    if batch.status in (BatchStatus.complete, BatchStatus.deleting):
        return batch.status

    scans_count = (
        db.query(func.count(RawScan.id)).filter(RawScan.batch_id == batch_id).scalar()
        or 0
    )
    if scans_count == 0:
        batch.status = BatchStatus.extracting
        redis_state.set_batch_stage(batch_id, batch.status.value)
        return batch.status

    pending_scans = (
        db.query(func.count(RawScan.id))
        .filter(RawScan.batch_id == batch_id, RawScan.status == ScanStatus.pending)
        .scalar()
        or 0
    )
    if pending_scans:
        batch.status = BatchStatus.cropping
        redis_state.set_batch_stage(batch_id, batch.status.value)
        return batch.status

    pending_rotation = (
        db.query(func.count(CardCrop.id))
        .join(RawScan)
        .filter(
            RawScan.batch_id == batch_id,
            # `skipped` (crop transform was a no-op -- already properly
            # cropped) still needs a human to confirm rotation, same as
            # `cropped`; only `crop_failed` scans skip rotation review.
            RawScan.status.in_((ScanStatus.cropped, ScanStatus.skipped)),
            CardCrop.rotation_confirmed_at.is_(None),
        )
        .scalar()
        or 0
    )
    if pending_rotation:
        batch.status = BatchStatus.rotation_review
        redis_state.set_batch_stage(batch_id, batch.status.value)
        return batch.status

    pending_duplicate_detection = (
        db.query(func.count(CardCrop.id))
        .join(RawScan)
        .filter(
            RawScan.batch_id == batch_id,
            RawScan.side == ScanSide.front,
            RawScan.status.in_((ScanStatus.cropped, ScanStatus.skipped)),
            CardCrop.rotation_confirmed_at.isnot(None),
            CardCrop.dedup_completed_at.is_(None),
        )
        .scalar()
        or 0
    )
    if pending_duplicate_detection:
        # No new public status is needed: keep the batch in its existing
        # processing/review state until the dedup worker records completion.
        batch.status = BatchStatus.rotation_review
        redis_state.set_batch_stage(batch_id, batch.status.value)
        return batch.status

    pending_duplicate_review = (
        db.query(func.count(DuplicateCandidate.id))
        .join(CardCrop, DuplicateCandidate.card_crop_id_a == CardCrop.id)
        .join(RawScan, CardCrop.raw_scan_id == RawScan.id)
        .filter(
            RawScan.batch_id == batch_id,
            DuplicateCandidate.status == DuplicateStatus.pending,
        )
        .scalar()
        or 0
    )
    if pending_duplicate_review:
        batch.status = BatchStatus.duplicate_review
        redis_state.set_batch_stage(batch_id, batch.status.value)
        return batch.status

    batch.status = BatchStatus.complete
    redis_state.mark_batch_terminal(batch_id, "complete")
    return batch.status
