"""crop_scan (spec Section 6.2 / 8): auto-crop + aspect-ratio safety check,
write the card_crops row.
"""

import logging
from typing import cast
from celery.app.task import Task

from app import storage
from app.batch_status import refresh_batch_status
from app.celery_app import celery_app
from app.db import SessionLocal
from app.models import CardCrop, RawScan, ScanStatus
from app.observability import redis_state
from app.observability.events import log_event, stage
from app.vision.crop import auto_crop


@celery_app.task(name="crop_scan")
def _crop_scan(raw_scan_id: int) -> None:
    db = SessionLocal()
    try:
        raw_scan = db.get(RawScan, raw_scan_id)
        if raw_scan is None:
            return

        batch_id = raw_scan.batch_id
        with stage("cropping", batch_id=batch_id, image_name=raw_scan.original_filename):
            raw_bytes = storage.download_bytes(raw_scan.r2_key_raw)

            try:
                result = auto_crop(raw_bytes)
            except ValueError as exc:
                raw_scan.status = ScanStatus.crop_failed
                refresh_batch_status(db, batch_id)
                db.commit()
                log_event(
                    "crop failed -- flagged crop_failed, batch continues",
                    level=logging.WARNING,
                    batch_id=batch_id,
                    image_name=raw_scan.original_filename,
                    skipped_reason=str(exc),
                )
                redis_state.incr_counter("images_crop_failed")
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

            key = storage.cropped_key(batch_id, card_crop.id, raw_scan.side.value)
            storage.upload_bytes(key, result.image_bytes)
            card_crop.r2_key_cropped = key

            # Flag instead of silently trusting a bad crop; a human corrects it
            # via the card log / rotation review before it feeds into hashing.
            # `skipped` means the crop transform itself was a no-op (the
            # image was already tight to the card and within tolerance) --
            # it still proceeds to rotation review / hashing exactly like
            # `cropped` does, see app.batch_status and app.api.rotation.
            if not result.aspect_ratio_ok:
                raw_scan.status = ScanStatus.crop_failed
            elif result.already_cropped:
                raw_scan.status = ScanStatus.skipped
            else:
                raw_scan.status = ScanStatus.cropped
            refresh_batch_status(db, batch_id)
            db.commit()

            log_event(
                "image cropped" if raw_scan.status != ScanStatus.skipped else "image already cropped -- crop skipped",
                batch_id=batch_id,
                image_name=raw_scan.original_filename,
                aspect_ratio_ok=result.aspect_ratio_ok,
                orientation=result.orientation,
                already_cropped=result.already_cropped,
            )
            redis_state.incr_counter(
                "images_skipped" if raw_scan.status == ScanStatus.skipped else "images_cropped"
            )
    except Exception:
        # e.g. storage.upload_bytes() raising after the db.flush() above
        # left a partial card_crop row staged on this session. Roll it back
        # explicitly instead of relying on close()'s implicit behavior.
        db.rollback()
        raise
    finally:
        db.close()


crop_scan = cast(Task, _crop_scan)
