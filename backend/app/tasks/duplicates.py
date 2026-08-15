"""find_duplicates (spec Section 6.4 / 8): within-batch brute force +
cross-batch BK-tree lookup, writes duplicate_candidates rows.
"""

from typing import cast
from celery.app.task import Task

from app.celery_app import celery_app
from app.batch_status import refresh_batch_status
from app.db import SessionLocal
from app.dedup.matching import (
    find_within_batch_duplicates,
    record_duplicate_candidates,
)
from app.models import CardCrop, RawScan
from app.observability.events import log_event, stage


@celery_app.task(name="find_duplicates")
def _find_duplicates(card_crop_id: int) -> None:
    db = SessionLocal()
    try:
        crop = db.get(CardCrop, card_crop_id)
        if crop is None or crop.hash_0 is None:
            return

        raw_scan = db.get(RawScan, crop.raw_scan_id)
        if raw_scan is None:
            return

        batch_id = raw_scan.batch_id
        with stage("duplicate_detection", batch_id=batch_id, image_name=raw_scan.original_filename):
            hits = find_within_batch_duplicates(db, crop, batch_id)

            record_duplicate_candidates(db, crop, hits)
            refresh_batch_status(db, batch_id)
            db.commit()

            log_event(
                "duplicate check finished",
                batch_id=batch_id,
                image_name=raw_scan.original_filename,
                candidates_found=len(hits),
            )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


find_duplicates = cast(Task, _find_duplicates)
