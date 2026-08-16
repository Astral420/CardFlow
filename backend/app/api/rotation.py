from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.common import crop_item, find_sibling_crop
from app.api.deps import get_current_user_optional, require_reviewer
from app.batch_status import refresh_batch_status
from app.db import get_db
from app.models import CardCrop, RawScan, ScanSide, ScanStatus
from app.naming import pairing_key
from app.schemas import CropQueueItemOut, QueueCountOut, RotateRequest, RotationNextOut
from app.tasks.dispatch import enqueue_task
from app.tasks.hashing import hash_crop

router = APIRouter(prefix="/api/review/rotation", tags=["rotation-review"])


def _next_pending(
    db: Session, batch_id: int | None, after_id: int | None = None
) -> RotationNextOut | None:
    query = (
        db.query(CardCrop)
        .join(RawScan)
        .filter(
            # `skipped` scans (already properly cropped, crop transform
            # skipped) still need a human to confirm rotation, same as
            # `cropped` -- see app.batch_status.refresh_batch_status.
            RawScan.status.in_((ScanStatus.cropped, ScanStatus.skipped)),
            CardCrop.rotation_confirmed_at.is_(None),
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
        .filter(
            RawScan.status.in_((ScanStatus.cropped, ScanStatus.skipped)),
            CardCrop.rotation_confirmed_at.is_(None),
        )
        .count()
    )
    return QueueCountOut(count=count)


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

    crop.rotation_confirmed_at = datetime.now(timezone.utc)
    batch_id = crop.raw_scan.batch_id
    refresh_batch_status(db, batch_id)
    db.commit()

    enqueue_task(hash_crop, crop_id)

    # Note: intentionally global (no batch_id filter), matching the
    # unscoped /next endpoint the review page actually polls. Scoping this
    # to the just-confirmed crop's own batch made the queue report "empty"
    # as soon as one batch was finished, even while other batches still had
    # cards waiting on rotation review.
    return _next_pending(db, None)
