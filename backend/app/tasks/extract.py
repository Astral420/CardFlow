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
from app.observability import redis_state
from app.observability.events import log_event, stage
from app.tasks.dispatch import enqueue_task

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}


@celery_app.task(name="extract_batch")
def _extract_batch(batch_id: int, zip_filename: str | None = None) -> None:
    """`zip_filename` is optional (defaults to None) purely for
    observability -- it's the original uploaded filename, passed through
    from app.api.batches.upload_batch so extraction/failure logs can
    reference it. Existing enqueued/retried calls without it still work."""
    from app.tasks.crop import crop_scan

    created_scan_ids: list[int] = []

    with stage("zip_extraction", batch_id=batch_id, zip_filename=zip_filename):
        db = SessionLocal()
        try:
            batch = db.get(Batch, batch_id)
            if batch is None:
                log_event(
                    "extract_batch: batch not found, skipping",
                    batch_id=batch_id,
                    zip_filename=zip_filename,
                )
                return

            zip_key = storage.temp_upload_key(batch_id)
            zip_bytes = storage.download_bytes(zip_key)
            compressed_size = len(zip_bytes)

            log_event(
                "ZIP validated",
                batch_id=batch_id,
                zip_filename=zip_filename,
                compressed_size=compressed_size,
            )

            supported = 0
            unsupported_files = 0
            unmatched_naming = 0
            duplicate_entries = 0
            uncompressed_size = 0
            seen_entries: set[tuple[str, str]] = set()

            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    uncompressed_size += info.file_size
                    filename = info.filename.rsplit("/", 1)[-1]
                    if "." not in filename:
                        unsupported_files += 1
                        continue
                    ext = filename.rsplit(".", 1)[-1].lower()
                    if ext not in IMAGE_EXTENSIONS:
                        unsupported_files += 1
                        continue
                    side = parse_side(filename)
                    if side is None:
                        unmatched_naming += 1
                        continue

                    dedup_key = (filename.lower(), side.value)
                    if dedup_key in seen_entries:
                        duplicate_entries += 1
                        continue
                    seen_entries.add(dedup_key)

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
                    supported += 1

            batch.status = BatchStatus.cropping
            db.commit()

            storage.delete_object(zip_key)

            log_event(
                "ZIP extracted",
                batch_id=batch_id,
                zip_filename=zip_filename,
                compressed_size=compressed_size,
                uncompressed_size=uncompressed_size,
                supported_images=supported,
                unsupported_files=unsupported_files,
                unmatched_naming=unmatched_naming,
                duplicate_entries_in_zip=duplicate_entries,
            )
            redis_state.push_recent(
                "obs:recent_uploads",
                {
                    "batch_id": batch_id,
                    "zip_filename": zip_filename,
                    "compressed_size": compressed_size,
                    "uncompressed_size": uncompressed_size,
                    "supported_images": supported,
                    "unsupported_files": unsupported_files,
                    "unmatched_naming": unmatched_naming,
                    "duplicate_entries_in_zip": duplicate_entries,
                    "at": redis_state.now_iso(),
                },
            )
            redis_state.set_batch_stage(batch_id, "cropping", image_total=supported)
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
