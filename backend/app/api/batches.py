import io
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
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import storage
from app.api.deps import get_current_user
from app.batch_status import refresh_batch_status
from app.db import get_db
from app.models import (
    Batch,
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
from app.tasks.extract import extract_batch
from app.vision.hashing import decode_image, encode_jpeg, rotate_image

router = APIRouter(prefix="/api/batches", tags=["batches"])


class _FlushableZipStream:
    """Minimal write-only, non-seekable file-like object for zipfile.

    zipfile.ZipFile checks for a working .seek() and falls back to writing
    a data descriptor after each entry instead of patching its local file
    header in place when the target isn't seekable -- which is exactly
    what lets us hand bytes to the client as they're produced rather than
    only after the whole archive is built. Deliberately has no .seek
    attribute at all so zipfile's AttributeError-based feature check finds
    it non-seekable rather than raising at request time.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._pos = 0

    def write(self, data: bytes) -> int:
        self._buffer += data
        self._pos += len(data)
        return len(data)

    def tell(self) -> int:
        return self._pos

    def flush(self) -> None:
        pass

    def close(self) -> None:
        # zipfile doesn't call this for an externally-provided file-like
        # object (only for paths it opened itself), but implementing it
        # keeps this a fully well-behaved writable-file object rather than
        # one that happens to work because of that specific code path.
        pass

    def take(self) -> bytes:
        """Return and clear whatever has been written since the last take()."""
        data = bytes(self._buffer)
        self._buffer.clear()
        return data


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
    _user=Depends(get_current_user),
) -> list[Batch]:
    return db.query(Batch).order_by(Batch.created_at.desc()).limit(limit).all()


@router.post(
    "", response_model=BatchCreateResponse, status_code=status.HTTP_201_CREATED
)
async def upload_batch(
    file: UploadFile = File(...),
    source_label: str | None = Form(default=None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
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

    extract_batch.delay(batch.id)

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
    batch_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)
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
    batch_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)
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
    batch_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)
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
    batch_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)
) -> StreamingResponse:
    """Stream a ZIP of all cropped card images for the batch, with rotation applied."""
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")

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
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No cropped images found for this batch",
        )

    # Convert to plain tuples NOW, before the session closes.
    # Exclude confirmed duplicates and sort: card number naturally, front before back.
    # The generator must not touch any SQLAlchemy ORM objects.
    entries: list[tuple[str, int, str, str]] = sorted(
        (
            (r2_key, rotation or 0, original_filename, side.value)
            for crop_id, r2_key, rotation, original_filename, side in rows
            if r2_key is not None
            and crop_id not in confirmed_dup_crop_ids
        ),
        key=lambda e: _natural_sort_key(e[2], e[3]),
    )

    def generate_zip():
        # zipfile writes sequentially and only needs .write()/.tell() to
        # work; it doesn't need to seek backwards as long as it detects the
        # stream isn't seekable (no .seek attribute here), in which case it
        # writes a trailing data descriptor instead of patching the local
        # file header in place. That lets us flush each entry's bytes out
        # to the client as soon as it's written, instead of building the
        # whole archive in a BytesIO before sending anything -- a batch of
        # 200 cards at ~300KB each no longer means ~60MB held in memory for
        # one request, just one entry's worth at a time.
        stream = _FlushableZipStream()
        with zipfile.ZipFile(stream, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for r2_key, rotation_degrees, original_filename, side_value in entries:
                try:
                    img_bytes = storage.download_bytes(r2_key)
                except Exception:
                    continue  # skip missing/inaccessible images gracefully

                # Apply stored rotation
                if rotation_degrees % 360 != 0:
                    try:
                        img = decode_image(img_bytes)
                        img = rotate_image(img, rotation_degrees)
                        img_bytes = encode_jpeg(img)
                    except Exception:
                        pass  # use unrotated image if rotation fails

                # Build a clean filename: stem_side.jpg
                stem = original_filename.rsplit(".", 1)[0]
                filename = f"{stem}_{side_value}.jpg"
                zf.writestr(filename, img_bytes)

                chunk = stream.take()
                if chunk:
                    yield chunk

        # Central directory (and anything else written on __exit__)
        trailing = stream.take()
        if trailing:
            yield trailing

    label = batch.source_label or f"batch_{batch_id}"
    safe_label = "".join(c if c.isalnum() or c in "-_ " else "_" for c in label).strip()
    disposition = f'attachment; filename="{safe_label}.zip"'

    return StreamingResponse(
        generate_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": disposition},
    )


@router.get("/{batch_id}/duplicates", response_model=list[BatchDuplicatePairOut])
def get_batch_duplicates(
    batch_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)
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
