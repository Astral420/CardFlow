"""extract_batch (spec Section 6.1 / 8): unzip, create raw_scans rows using
the client's front/back filename convention, fan out one crop_scan per
image.
"""

import io
import zipfile

from typing import cast
from celery.app.task import Task

from app import storage
from app.celery_app import celery_app
from app.db import SessionLocal
from app.models import Batch, BatchStatus, RawScan, ScanStatus
from app.naming import parse_side
from app.tasks.dispatch import enqueue_task

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}


@celery_app.task(name="extract_batch")
def _extract_batch(batch_id: int) -> None:
    from app.tasks.crop import crop_scan

    db = SessionLocal()
    try:
        batch = db.get(Batch, batch_id)
        if batch is None:
            return

        zip_key = storage.temp_upload_key(batch_id)
        zip_bytes = storage.download_bytes(zip_key)

        created_scan_ids: list[int] = []
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                filename = info.filename.rsplit("/", 1)[-1]
                if "." not in filename:
                    continue
                ext = filename.rsplit(".", 1)[-1].lower()
                if ext not in IMAGE_EXTENSIONS:
                    continue
                side = parse_side(filename)
                if side is None:
                    continue  # doesn't match the client naming convention

                image_bytes = archive.read(info)

                raw_scan = RawScan(
                    batch_id=batch_id,
                    r2_key_raw="",
                    original_filename=filename,
                    side=side,
                    status=ScanStatus.pending,
                )
                db.add(raw_scan)
                db.flush()  # assign raw_scan.id

                key = storage.raw_key(batch_id, raw_scan.id, side.value, ext)
                storage.upload_bytes(key, image_bytes)
                raw_scan.r2_key_raw = key
                created_scan_ids.append(raw_scan.id)

        batch.status = BatchStatus.cropping
        db.commit()

        storage.delete_object(zip_key)
    except Exception:
        # A raw_scan row can be flushed (assigned an id) for one zip entry
        # and then storage.upload_bytes() can fail for a later entry, or the
        # zip can be malformed partway through -- roll back explicitly
        # rather than leaving that to close()'s implicit behavior.
        db.rollback()
        raise
    finally:
        db.close()

    for scan_id in created_scan_ids:
        enqueue_task(crop_scan, scan_id)


extract_batch = cast(Task, _extract_batch)
