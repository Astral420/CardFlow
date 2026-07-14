"""crop_scan (spec Section 6.2 / 8): auto-crop + aspect-ratio safety check,
write the card_crops row.
"""

from typing import cast
from celery.app.task import Task

from app import storage
from app.batch_status import refresh_batch_status
from app.celery_app import celery_app
from app.db import SessionLocal
from app.models import CardCrop, RawScan, ScanStatus
from app.vision.crop import auto_crop


@celery_app.task(name="crop_scan")
def _crop_scan(raw_scan_id: int) -> None:
    db = SessionLocal()
    try:
        raw_scan = db.get(RawScan, raw_scan_id)
        if raw_scan is None:
            return

        raw_bytes = storage.download_bytes(raw_scan.r2_key_raw)

        try:
            result = auto_crop(raw_bytes)
        except ValueError:
            raw_scan.status = ScanStatus.crop_failed
            refresh_batch_status(db, raw_scan.batch_id)
            db.commit()
            return

        card_crop = CardCrop(
            raw_scan_id=raw_scan.id,
            aspect_ratio_ok=result.aspect_ratio_ok,
            crop_bbox={
                "points": result.bbox,
                "aspect_ratio": result.aspect_ratio,
                "orientation": result.orientation,
            },
        )
        db.add(card_crop)
        db.flush()  # assign card_crop.id

        key = storage.cropped_key(raw_scan.batch_id, card_crop.id, raw_scan.side.value)
        storage.upload_bytes(key, result.image_bytes)
        card_crop.r2_key_cropped = key

        # Flag instead of silently trusting a bad crop; a human corrects it
        # via the card log / rotation review before it feeds into hashing.
        raw_scan.status = (
            ScanStatus.cropped if result.aspect_ratio_ok else ScanStatus.crop_failed
        )
        refresh_batch_status(db, raw_scan.batch_id)
        db.commit()
    finally:
        db.close()


crop_scan = cast(Task, _crop_scan)
