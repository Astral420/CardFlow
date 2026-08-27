from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import storage
from app.api.common import crop_item, find_sibling_crop
from app.api.deps import get_current_user_optional, require_reviewer
from app.batch_status import lock_batch_for_pipeline_write, refresh_batch_status
from app.db import get_db
from app.models import (
    Batch,
    BatchExport,
    BatchStatus,
    CardCrop,
    DuplicateCandidate,
    RawScan,
    ScanSide,
    ScanStatus,
)
from app.naming import pairing_key
from app.schemas import (
    BulkRerotationRequest,
    CropQueueItemOut,
    QueueCountOut,
    RerotationResultOut,
    RotateRequest,
    RotationNextOut,
)
from app.tasks.dispatch import enqueue_task
from app.tasks.hashing import hash_crop

router = APIRouter(prefix="/api/review/rotation", tags=["rotation-review"])
logger = logging.getLogger("cardflow.rotation")

_HASH_FIELDS = (
    "hash_0",
    "hash_90",
    "hash_180",
    "hash_270",
    "color_sig_0",
    "color_sig_90",
    "color_sig_180",
    "color_sig_270",
)


def _rerotate_pairs(
    db: Session, selected_crops: list[CardCrop]
) -> RerotationResultOut:
    """Reset unique front/back pairs and remove their stale dedup results."""
    batch_ids = {crop.raw_scan.batch_id for crop in selected_crops}
    if len(batch_ids) != 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "All crops in a bulk re-rotation request must belong to one batch",
        )

    batch_id = next(iter(batch_ids))
    batch = (
        db.query(Batch)
        .filter(Batch.id == batch_id)
        .with_for_update()
        .one_or_none()
    )
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
    if batch.status == BatchStatus.deleting:
        raise HTTPException(status.HTTP_409_CONFLICT, "Batch is being deleted")

    seen_pairs: set[tuple[int, str]] = set()
    front_crop_ids: set[int] = set()
    requeued_count = 0

    for crop in selected_crops:
        pair_key = (crop.raw_scan.batch_id, crop.raw_scan.pairing_key)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        requeued_count += 1

        sibling = find_sibling_crop(db, crop)
        pair = (crop, sibling) if sibling is not None else (crop,)
        for pair_crop in pair:
            pair_crop.rotation_confirmed_at = None
            pair_crop.dedup_completed_at = None
            for field_name in _HASH_FIELDS:
                setattr(pair_crop, field_name, None)
            if pair_crop.raw_scan.side == ScanSide.front:
                front_crop_ids.add(pair_crop.id)

    if front_crop_ids:
        db.query(DuplicateCandidate).filter(
            (DuplicateCandidate.card_crop_id_a.in_(front_crop_ids))
            | (DuplicateCandidate.card_crop_id_b.in_(front_crop_ids))
        ).delete(synchronize_session=False)

    stale_exports = (
        db.query(BatchExport).filter(BatchExport.batch_id == batch_id).all()
    )
    stale_export_keys = [export.r2_key for export in stale_exports]
    for stale_export in stale_exports:
        db.delete(stale_export)

    # A completed batch is terminal to the normal status derivation. Unlock it
    # explicitly, then let the status machine confirm that pending rotations
    # put it back in rotation review.
    batch.status = BatchStatus.rotation_review
    batch_status = refresh_batch_status(db, batch_id)
    db.commit()

    # R2 cleanup intentionally happens after the database commit. If object
    # deletion fails, no cache row can reference the stale archive; only an
    # unreferenced object remains for later lifecycle cleanup.
    for export_key in stale_export_keys:
        try:
            storage.delete_object(export_key)
        except Exception as exc:
            logger.warning(
                "Failed to delete invalidated export object %s: %s",
                export_key,
                exc,
            )

    return RerotationResultOut(
        requeued_count=requeued_count,
        batch_id=batch_id,
        batch_status=batch_status or batch.status,
    )


def _next_pending(
    db: Session, batch_id: int | None, after_id: int | None = None
) -> RotationNextOut | None:
    query = (
        db.query(CardCrop)
        .join(RawScan)
        .join(Batch, RawScan.batch_id == Batch.id)
        .filter(
            # `skipped` scans (already properly cropped, crop transform
            # skipped) still need a human to confirm rotation, same as
            # `cropped` -- see app.batch_status.refresh_batch_status.
            RawScan.status.in_((ScanStatus.cropped, ScanStatus.skipped)),
            CardCrop.rotation_confirmed_at.is_(None),
            Batch.status != BatchStatus.deleting,
        )
        .order_by(CardCrop.id)
    )
    if batch_id is not None:
        query = query.filter(RawScan.batch_id == batch_id)
    if after_id is not None:
        query = query.filter(CardCrop.id > after_id)

    crop = query.first()
    if crop is None:
        return None

    raw_scan = crop.raw_scan
    sibling = find_sibling_crop(db, crop)

    front = crop if raw_scan.side == ScanSide.front else sibling
    back = crop if raw_scan.side == ScanSide.back else sibling

    return RotationNextOut(
        batch_id=raw_scan.batch_id,
        original_filename=pairing_key(raw_scan.original_filename),
        front=crop_item(front) if front else None,
        back=crop_item(back) if back else None,
    )


@router.get("/next", response_model=RotationNextOut | None)
def next_in_queue(
    batch_id: int | None = Query(default=None),
    after_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> RotationNextOut | None:
    return _next_pending(db, batch_id, after_id)


@router.get("/queue-count", response_model=QueueCountOut)
def queue_count(
    db: Session = Depends(get_db), _user=Depends(get_current_user_optional)
) -> QueueCountOut:
    count = (
        db.query(CardCrop)
        .join(RawScan)
        .join(Batch, RawScan.batch_id == Batch.id)
        .filter(
            RawScan.status.in_((ScanStatus.cropped, ScanStatus.skipped)),
            CardCrop.rotation_confirmed_at.is_(None),
            Batch.status != BatchStatus.deleting,
        )
        .count()
    )
    return QueueCountOut(count=count)


@router.post("/bulk-rerotation", response_model=RerotationResultOut)
def bulk_rerotation(
    payload: BulkRerotationRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_reviewer),
) -> RerotationResultOut:
    crops: list[CardCrop] = []
    for crop_id in dict.fromkeys(payload.crop_ids):
        crop = db.get(CardCrop, crop_id)
        if crop is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"Crop {crop_id} not found"
            )
        crops.append(crop)
    return _rerotate_pairs(db, crops)


@router.post("/{crop_id}/request-rerotation", response_model=RerotationResultOut)
def request_rerotation(
    crop_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_reviewer),
) -> RerotationResultOut:
    crop = db.get(CardCrop, crop_id)
    if crop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Crop not found")
    return _rerotate_pairs(db, [crop])


@router.post("/{crop_id}/rotate", response_model=CropQueueItemOut)
def rotate(
    crop_id: int,
    payload: RotateRequest,
    db: Session = Depends(get_db),
    _user=Depends(require_reviewer),
) -> CropQueueItemOut:
    crop = db.get(CardCrop, crop_id)
    if crop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Crop not found")
    if lock_batch_for_pipeline_write(db, crop.raw_scan.batch_id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Batch is being deleted")

    crop.rotation_degrees = (crop.rotation_degrees + payload.degrees) % 360
    refresh_batch_status(db, crop.raw_scan.batch_id)
    db.commit()
    return crop_item(crop)


@router.post("/{crop_id}/confirm", response_model=RotationNextOut | None)
def confirm(
    crop_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_reviewer),
) -> RotationNextOut | None:
    crop = db.get(CardCrop, crop_id)
    if crop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Crop not found")
    if lock_batch_for_pipeline_write(db, crop.raw_scan.batch_id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Batch is being deleted")

    # Rotation review is presented as one physical card (front + back), so a
    # single confirmation must resolve that whole pair. Confirming only the
    # crop named in the URL leaves its sibling pending; because the queue is
    # ordered by crop id, that sibling can surface much later and reconstruct
    # the same pair with one side already marked "Confirmed".
    sibling = find_sibling_crop(db, crop)
    pair = (crop, sibling) if sibling is not None else (crop,)
    confirmed_at = datetime.now(timezone.utc)
    newly_confirmed = []
    for pair_crop in pair:
        if pair_crop.rotation_confirmed_at is None:
            pair_crop.rotation_confirmed_at = confirmed_at
            newly_confirmed.append(pair_crop)

    batch_id = crop.raw_scan.batch_id
    refresh_batch_status(db, batch_id)
    db.commit()

    # Only fronts are hashed. Restrict dispatch to newly-confirmed rows so a
    # retried/idempotent confirm request cannot enqueue duplicate hash work.
    for pair_crop in newly_confirmed:
        if pair_crop.raw_scan.side == ScanSide.front:
            enqueue_task(hash_crop, pair_crop.id)

    # Note: intentionally global (no batch_id filter), matching the
    # unscoped /next endpoint the review page actually polls. Scoping this
    # to the just-confirmed crop's own batch made the queue report "empty"
    # as soon as one batch was finished, even while other batches still had
    # cards waiting on rotation review.
    return _next_pending(db, None)
