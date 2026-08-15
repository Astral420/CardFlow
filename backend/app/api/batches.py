import hashlib
import io
import logging
import zipfile

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import storage
from app.api.deps import get_current_user_optional, require_admin, require_reviewer
from app.batch_status import refresh_batch_status
from app.db import get_db
from app.models import (
    Batch,
    BatchAuditLog,
    BatchStatus,
    CardCrop,
    DuplicateCandidate,
    DuplicateStatus,
    RawScan,
    ScanStatus,
)
from app.schemas import (
    BatchCountsOut,
    BatchCreateResponse,
    BatchDetailOut,
    BatchDuplicateCropOut,
    BatchDuplicatePairOut,
    BatchOut,
    RawScanOut,
)
import re as _re

from app.api.common import finite_float_or_none
from app.observability import redis_state
from app.observability.events import log_event, stage
from app.tasks.extract import extract_batch
from app.vision.hashing import decode_image, encode_jpeg, rotate_image

logger = logging.getLogger("cardflow.batches")

router = APIRouter(prefix="/api/batches", tags=["batches"])




def _natural_sort_key(filename: str, side: str) -> tuple:
    """Sort key that orders by card stem numerically then front before back.

    Splits the pairing stem (filename without -front/-back suffix) into
    alternating text/int chunks so that e.g. 'card-2' sorts before 'card-10'.
    Side ordering: front (0) before back (1).
    """
    from app.naming import pairing_key as _pairing_key

    stem = _pairing_key(filename).lower()
    # Split into alternating non-digit / digit segments for natural ordering
    parts: list = []
    for chunk in _re.split(r"(\d+)", stem):
        parts.append(int(chunk) if chunk.isdigit() else chunk)
    side_order = 0 if side.lower() == "front" else 1
    return (*parts, side_order)


@router.get("", response_model=list[BatchOut])
def list_batches(
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> list[Batch]:
    return db.query(Batch).order_by(Batch.created_at.desc()).limit(limit).all()


@router.post(
    "", response_model=BatchCreateResponse, status_code=status.HTTP_201_CREATED
)
async def upload_batch(
    file: UploadFile = File(...),
    source_label: str | None = Form(default=None),
    db: Session = Depends(get_db),
    _user=Depends(require_reviewer),
) -> BatchCreateResponse:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Expected a .zip file")

    batch = Batch(source_label=source_label, status=BatchStatus.extracting)
    db.add(batch)
    db.commit()
    db.refresh(batch)

    zip_bytes = await file.read()
    storage.upload_bytes(
        storage.temp_upload_key(batch.id), zip_bytes, content_type="application/zip"
    )

    log_event(
        "ZIP uploaded",
        batch_id=batch.id,
        zip_filename=file.filename,
        compressed_size=len(zip_bytes),
    )

    extract_batch.delay(batch.id, zip_filename=file.filename)

    return BatchCreateResponse(batch_id=batch.id)


def _batch_counts(db: Session, batch_id: int) -> BatchCountsOut:
    """Compute all counts for a batch in one place."""
    scans_count = (
        db.query(func.count(RawScan.id)).filter(RawScan.batch_id == batch_id).scalar()
        or 0
    )
    cropped_count = (
        db.query(func.count(RawScan.id))
        .filter(RawScan.batch_id == batch_id, RawScan.status == ScanStatus.cropped)
        .scalar()
        or 0
    )
    crop_failed_count = (
        db.query(func.count(RawScan.id))
        .filter(RawScan.batch_id == batch_id, RawScan.status == ScanStatus.crop_failed)
        .scalar()
        or 0
    )
    pending_rotation = (
        db.query(func.count(CardCrop.id))
        .join(RawScan)
        .filter(
            RawScan.batch_id == batch_id,
            RawScan.status == ScanStatus.cropped,
            CardCrop.rotation_confirmed_at.is_(None),
        )
        .scalar()
        or 0
    )
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
    return BatchCountsOut(
        scans=scans_count,
        cropped=cropped_count,
        crop_failed=crop_failed_count,
        pending_rotation=pending_rotation,
        pending_duplicate_review=pending_duplicate_review,
    )


@router.get("/{batch_id}", response_model=BatchDetailOut)
def get_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> BatchDetailOut:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
    refresh_batch_status(db, batch_id)
    db.commit()
    db.refresh(batch)

    return BatchDetailOut(
        id=batch.id,
        created_at=batch.created_at,
        source_label=batch.source_label,
        status=batch.status,
        counts=_batch_counts(db, batch_id),
    )


@router.get("/{batch_id}/scans", response_model=list[RawScanOut])
def get_batch_scans(
    batch_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> list[RawScanOut]:
    scans = (
        db.query(RawScan)
        .filter(RawScan.batch_id == batch_id)
        .all()
    )

    # Sort: natural order on card stem (numeric-aware), then front before back
    scans.sort(key=lambda s: _natural_sort_key(s.original_filename, s.side.value))

    # Collect crop IDs that are the "loser" (card_crop_id_b) in a confirmed duplicate
    confirmed_dup_crop_ids: set[int] = set(
        row[0]
        for row in db.query(DuplicateCandidate.card_crop_id_b)
        .join(CardCrop, DuplicateCandidate.card_crop_id_a == CardCrop.id)
        .join(RawScan, CardCrop.raw_scan_id == RawScan.id)
        .filter(
            RawScan.batch_id == batch_id,
            DuplicateCandidate.status == DuplicateStatus.confirmed_duplicate,
        )
        .all()
    )

    results = []
    for scan in scans:
        thumbnail_url = None
        rotation_degrees = 0
        is_duplicate = False
        if scan.crop and scan.crop.r2_key_cropped:
            thumbnail_url = storage.presigned_url(scan.crop.r2_key_cropped)
            rotation_degrees = scan.crop.rotation_degrees or 0
            is_duplicate = scan.crop.id in confirmed_dup_crop_ids
        results.append(
            RawScanOut(
                id=scan.id,
                original_filename=scan.original_filename,
                side=scan.side,
                status=scan.status,
                thumbnail_url=thumbnail_url,
                rotation_degrees=rotation_degrees,
                is_duplicate=is_duplicate,
            )
        )
    return results


@router.post("/{batch_id}/force-advance", response_model=BatchDetailOut)
def force_advance_batch(
    batch_id: int, db: Session = Depends(get_db), _user=Depends(require_admin)
) -> BatchDetailOut:
    """Mark all stuck 'pending' scans as crop_failed and recompute batch status.

    This unblocks batches where a Celery worker crashed before it could update
    the scan status, leaving scans permanently stuck in 'pending'.
    """
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")

    if batch.status != BatchStatus.cropping:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Batch is not in cropping status (current: {batch.status})",
        )

    # Mark all pending scans as crop_failed so the pipeline can advance
    stuck_scans = (
        db.query(RawScan)
        .filter(RawScan.batch_id == batch_id, RawScan.status == ScanStatus.pending)
        .all()
    )
    for scan in stuck_scans:
        scan.status = ScanStatus.crop_failed

    refresh_batch_status(db, batch_id)
    db.commit()
    db.refresh(batch)

    return BatchDetailOut(
        id=batch.id,
        created_at=batch.created_at,
        source_label=batch.source_label,
        status=batch.status,
        counts=_batch_counts(db, batch_id),
    )


@router.get("/{batch_id}/export")
def export_batch_zip(
    batch_id: int, db: Session = Depends(get_db), _user=Depends(require_reviewer)
) -> Response:
    """Build and return a ZIP of all non-duplicate cropped card images for the batch.

    The archive is assembled fully in memory before the response is sent so that
    any R2 download failure raises a 500 *before* we commit to a 200 OK -- preventing
    the client from receiving a structurally incomplete (corrupted) archive.
    """
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")

    log_event("export requested", batch_id=batch_id)

    # Collect crop IDs that are confirmed duplicates (card_crop_id_b in a confirmed pair)
    confirmed_dup_crop_ids: set[int] = set(
        row[0]
        for row in db.query(DuplicateCandidate.card_crop_id_b)
        .join(CardCrop, DuplicateCandidate.card_crop_id_a == CardCrop.id)
        .join(RawScan, CardCrop.raw_scan_id == RawScan.id)
        .filter(
            RawScan.batch_id == batch_id,
            DuplicateCandidate.status == DuplicateStatus.confirmed_duplicate,
        )
        .all()
    )

    # Fetch all crops that have a stored image, joining raw_scan eagerly so we
    # can read all needed fields while the session is still open.
    rows = (
        db.query(
            CardCrop.id,
            CardCrop.r2_key_cropped,
            CardCrop.rotation_degrees,
            RawScan.original_filename,
            RawScan.side,
        )
        .join(RawScan, CardCrop.raw_scan_id == RawScan.id)
        .filter(
            RawScan.batch_id == batch_id,
            CardCrop.r2_key_cropped.isnot(None),
        )
        .all()
    )

    if not rows:
        log_event(
            "export rejected: no cropped images found",
            level=logging.WARNING,
            batch_id=batch_id,
        )
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No cropped images found for this batch",
        )

    # Exclude confirmed duplicates and sort: card number naturally, front before back.
    entries: list[tuple[str, int, str, str]] = sorted(
        (
            (r2_key, rotation or 0, original_filename, side.value)
            for crop_id, r2_key, rotation, original_filename, side in rows
            if r2_key is not None
            and crop_id not in confirmed_dup_crop_ids
        ),
        key=lambda e: _natural_sort_key(e[2], e[3]),
    )

    label = batch.source_label or f"batch_{batch_id}"
    safe_label = "".join(c if c.isalnum() or c in "-_ " else "_" for c in label).strip()
    disposition = f'attachment; filename="{safe_label}.zip"'

    with stage("export", batch_id=batch_id, image_count=len(entries)):
        log_event("images collected for export", batch_id=batch_id, image_count=len(entries))

        # Build the full ZIP in memory before sending a single byte. Any R2 error
        # raised here becomes a 500 response rather than a truncated/corrupt download.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for r2_key, rotation_degrees, original_filename, side_value in entries:
                img_bytes = storage.download_bytes(r2_key)  # raises on failure → 500, not corrupt ZIP

                # Apply stored rotation
                if rotation_degrees % 360 != 0:
                    try:
                        img = decode_image(img_bytes)
                        img = rotate_image(img, rotation_degrees)
                        img_bytes = encode_jpeg(img)
                    except Exception:
                        pass  # use unrotated image if rotation fails

                stem = original_filename.rsplit(".", 1)[0]
                zf.writestr(f"{stem}_{side_value}.jpg", img_bytes)

        zip_bytes = buf.getvalue()
        checksum = hashlib.sha256(zip_bytes).hexdigest()[:16]

        log_event(
            "export completed",
            batch_id=batch_id,
            output_size=len(zip_bytes),
            image_count=len(entries),
            checksum=checksum,
        )
        redis_state.push_recent(
            "obs:recent_exports",
            {
                "batch_id": batch_id,
                "output_size": len(zip_bytes),
                "image_count": len(entries),
                "checksum": checksum,
                "at": redis_state.now_iso(),
            },
        )

    # Export and download are the same request/response here (there's no
    # separate async download step) -- see /OBSERVABILITY.md.

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(len(zip_bytes)),
        },
    )


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> None:
    """Hard-delete a batch: delete DB rows within transaction, then remove R2 objects.

    Steps (in order):
      1. Load the batch (404 if missing).
      2. Collect every R2 key associated with this batch and snapshot metadata.
      3. Create a BatchAuditLog row and cascade-delete the Batch row in Postgres.
      4. Commit the DB transaction. If this fails, the transaction rolls back
         and no storage objects are deleted.
      5. Delete each object from R2 via storage.delete_object -- failures are
         non-fatal (logged and updated in the audit log).
      6. Update BatchAuditLog with actual R2 delete results.
      7. Structured log event (audit trail in centralized logs).
      8. Push a best-effort summary entry to obs:recent_batch_deletes (Redis).

    Auth: admin only (403 for reviewers and guests).
    """
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")

    # ------------------------------------------------------------------ #
    # 1. Collect R2 keys and snapshot batch metadata                       #
    # ------------------------------------------------------------------ #
    r2_keys: list[str] = []

    # Temp upload ZIP (may or may not still exist -- delete_object is idempotent)
    r2_keys.append(storage.temp_upload_key(batch_id))

    # Raw scan images
    scans = db.query(RawScan).filter(RawScan.batch_id == batch_id).all()
    for scan in scans:
        if scan.r2_key_raw:
            r2_keys.append(scan.r2_key_raw)

    # Cropped card images
    crop_ids = [scan.crop.id for scan in scans if scan.crop is not None]
    if crop_ids:
        crops = db.query(CardCrop).filter(CardCrop.id.in_(crop_ids)).all()
        for crop in crops:
            if crop.r2_key_cropped:
                r2_keys.append(crop.r2_key_cropped)

    scan_count = len(scans)
    batch_source_label = batch.source_label
    batch_status_val = batch.status.value if batch.status else None

    # ------------------------------------------------------------------ #
    # 2. Write durable Postgres audit log & cascade-delete DB rows       #
    # ------------------------------------------------------------------ #
    audit = BatchAuditLog(
        batch_id=batch_id,
        performed_by=current_user.id,
        action="hard_delete",
        source_label=batch_source_label,
        batch_status=batch_status_val,
        scan_count=scan_count,
        r2_keys_deleted=0,
        r2_keys_failed=0,
        notes=None,
    )
    db.add(audit)
    db.delete(batch)
    db.commit()

    # ------------------------------------------------------------------ #
    # 3. Delete R2 objects (post-commit, non-fatal on individual failure) #
    # ------------------------------------------------------------------ #
    r2_deleted = 0
    r2_failed = 0
    r2_failure_notes: list[str] = []

    for key in r2_keys:
        try:
            storage.delete_object(key)
            r2_deleted += 1
        except Exception as exc:
            r2_failed += 1
            r2_failure_notes.append(f"{key}: {exc}")
            logger.warning(
                "R2 delete failed for key %s (batch %d): %s",
                key,
                batch_id,
                exc,
                extra={"batch_id": batch_id, "r2_key": key},
            )

    notes_str = "; ".join(r2_failure_notes) if r2_failure_notes else None
    try:
        audit.r2_keys_deleted = r2_deleted
        audit.r2_keys_failed = r2_failed
        audit.notes = notes_str
        db.commit()
    except Exception as exc:
        logger.warning(
            "Failed to update audit log for batch %d with R2 results: %s",
            batch_id,
            exc,
        )

    # ------------------------------------------------------------------ #
    # 4. Structured log event                                              #
    # ------------------------------------------------------------------ #
    log_event(
        "batch hard deleted",
        batch_id=batch_id,
        performed_by=current_user.id,
        source_label=batch_source_label,
        scan_count=scan_count,
        r2_keys_deleted=r2_deleted,
        r2_keys_failed=r2_failed,
    )

    # ------------------------------------------------------------------ #
    # 5. Best-effort Redis feed for the ops dashboard                      #
    # ------------------------------------------------------------------ #
    redis_state.push_recent(
        "obs:recent_batch_deletes",
        {
            "batch_id": batch_id,
            "source_label": batch_source_label,
            "performed_by": current_user.id,
            "scan_count": scan_count,
            "r2_keys_deleted": r2_deleted,
            "r2_keys_failed": r2_failed,
            "at": redis_state.now_iso(),
        },
    )


@router.get("/{batch_id}/duplicates", response_model=list[BatchDuplicatePairOut])
def get_batch_duplicates(
    batch_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> list[BatchDuplicatePairOut]:
    """Return all confirmed-duplicate pairs for a batch with image URLs and scores."""
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")

    # Fetch confirmed duplicate candidates where card_crop_a belongs to this batch
    candidates = (
        db.query(DuplicateCandidate)
        .join(CardCrop, DuplicateCandidate.card_crop_id_a == CardCrop.id)
        .join(RawScan, CardCrop.raw_scan_id == RawScan.id)
        .filter(
            RawScan.batch_id == batch_id,
            DuplicateCandidate.status == DuplicateStatus.confirmed_duplicate,
        )
        .order_by(DuplicateCandidate.id)
        .all()
    )

    def _crop_out(crop: CardCrop) -> BatchDuplicateCropOut:
        return BatchDuplicateCropOut(
            crop_id=crop.id,
            original_filename=crop.raw_scan.original_filename,
            side=crop.raw_scan.side,
            image_url=storage.presigned_url(crop.r2_key_cropped)
            if crop.r2_key_cropped
            else None,
            rotation_degrees=crop.rotation_degrees or 0,
        )

    results: list[BatchDuplicatePairOut] = []
    for c in candidates:
        # Guard: card_crop_b must also exist
        if c.card_crop_b is None:
            continue
        results.append(
            BatchDuplicatePairOut(
                candidate_id=c.id,
                structural_score=finite_float_or_none(c.structural_score),
                color_score=finite_float_or_none(c.color_score),
                filename_match=c.filename_match,
                kept=_crop_out(c.card_crop_a),
                removed=_crop_out(c.card_crop_b),
            )
        )
    return results
