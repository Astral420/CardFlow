"""hash_crop (spec Section 6.4 / 8): structural + color signatures at all 4
rotations, queued after rotation is confirmed. Front images only — backs
are frequently a shared template across a set's parallels/inserts and carry
little distinguishing signal.
"""

from typing import cast
from celery.app.task import Task

from app import storage
from app.celery_app import celery_app
from app.db import SessionLocal
from app.models import CardCrop, RawScan, ScanSide
from app.observability.events import log_event, stage
from app.tasks.dispatch import enqueue_task
from app.vision.hashing import (
    decode_image,
    encode_jpeg,
    hash_and_color_at_all_rotations,
    rotate_image,
)


@celery_app.task(name="hash_crop")
def _hash_crop(card_crop_id: int) -> None:
    from app.tasks.duplicates import find_duplicates

    db = SessionLocal()
    try:
        crop = db.get(CardCrop, card_crop_id)
        if crop is None or crop.r2_key_cropped is None:
            return

        raw_scan = db.get(RawScan, crop.raw_scan_id)
        if raw_scan is None or raw_scan.side != ScanSide.front:
            return  # hash only the front image

        batch_id = raw_scan.batch_id
        with stage("hashing", batch_id=batch_id, image_name=raw_scan.original_filename):
            crop.dedup_completed_at = None
            image_bytes = storage.download_bytes(crop.r2_key_cropped)

            if crop.rotation_degrees % 360:
                image = decode_image(image_bytes)
                image = rotate_image(image, crop.rotation_degrees)
                image_bytes = encode_jpeg(image)

            results = hash_and_color_at_all_rotations(image_bytes)
            crop.hash_0, crop.color_sig_0 = results[0]
            crop.hash_90, crop.color_sig_90 = results[90]
            crop.hash_180, crop.color_sig_180 = results[180]
            crop.hash_270, crop.color_sig_270 = results[270]
            db.commit()

            log_event("image hashed", batch_id=batch_id, image_name=raw_scan.original_filename)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    enqueue_task(find_duplicates, card_crop_id)


hash_crop = cast(Task, _hash_crop)
