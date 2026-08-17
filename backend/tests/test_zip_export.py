import io
import zipfile
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.batches import delete_batch, export_batch_zip
from app.db import Base
from app.models import (
    Batch,
    BatchExport,
    BatchStatus,
    CardCrop,
    DuplicateCandidate,
    DuplicateStatus,
    RawScan,
    ScanSide,
    ScanStatus,
    User,
    UserRole,
)


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_export_batch_zip_cache_miss_and_hit():
    """First export creates ZIP, uploads to R2, and saves BatchExport (cache miss).
    Second export returns cached export directly without re-reading crops (cache hit).
    """
    db = _make_session()
    batch = Batch(id=1, status=BatchStatus.complete, source_label="test_batch")
    db.add(batch)
    scan = RawScan(
        id=10,
        batch_id=1,
        r2_key_raw="raw/1/10-front.jpg",
        original_filename="card_1_front.jpg",
        pairing_key="card_1",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    db.add(scan)
    crop = CardCrop(
        id=100,
        raw_scan_id=10,
        r2_key_cropped="cropped/1/100-front.jpg",
        rotation_degrees=0,
    )
    db.add(crop)
    db.commit()

    dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xd9"

    with patch("app.storage.download_bytes", return_value=dummy_jpeg) as mock_download, \
         patch("app.storage.upload_bytes") as mock_upload:

        # 1. First call -> Cache Miss
        res1 = export_batch_zip(batch_id=1, db=db, _user=None)

        assert res1.status_code == 200
        assert res1.media_type == "application/zip"
        assert res1.headers["Content-Disposition"] == 'attachment; filename="test_batch.zip"'
        assert res1.headers["X-Export-Cached"] == "false"
        assert mock_download.call_count == 1
        assert mock_upload.call_count == 1

        # Verify uploaded ZIP content
        uploaded_key, uploaded_data = mock_upload.call_args[0][:2]
        assert uploaded_key.startswith("exports/1/")
        assert uploaded_key.endswith(".zip")
        zf = zipfile.ZipFile(io.BytesIO(uploaded_data))
        assert zf.testzip() is None
        assert zf.namelist() == ["card_1_front_front.jpg"]

        # Verify BatchExport record created in DB
        export_row = db.query(BatchExport).filter_by(batch_id=1).first()
        assert export_row is not None
        assert export_row.r2_key == uploaded_key

        # 2. Second call -> Cache Hit
        mock_download.reset_mock()
        mock_download.return_value = uploaded_data  # return cached zip bytes
        mock_upload.reset_mock()

        res2 = export_batch_zip(batch_id=1, db=db, _user=None)

        assert res2.status_code == 200
        assert res2.media_type == "application/zip"
        assert res2.headers["X-Export-Cached"] == "true"
        # On cache hit, download_bytes is called ONCE for the cached archive key, not for individual crop images
        assert mock_download.call_count == 1
        mock_download.assert_called_with(export_row.r2_key)
        assert mock_upload.call_count == 0    # no re-upload on cache hit


def test_export_batch_zip_invalidation_and_pruning():
    """When a crop rotation changes, manifest hash changes:
    - Generates new ZIP and uploads new archive to R2
    - Deletes previous stale export archive from R2
    - Updates BatchExport record in DB
    """
    db = _make_session()
    batch = Batch(id=1, status=BatchStatus.complete, source_label="test_batch")
    db.add(batch)
    scan = RawScan(
        id=10,
        batch_id=1,
        r2_key_raw="raw/1/10-front.jpg",
        original_filename="card_1_front.jpg",
        pairing_key="card_1",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    db.add(scan)
    crop = CardCrop(
        id=100,
        raw_scan_id=10,
        r2_key_cropped="cropped/1/100-front.jpg",
        rotation_degrees=0,
    )
    db.add(crop)
    db.commit()

    dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xd9"

    with patch("app.storage.download_bytes", return_value=dummy_jpeg), \
         patch("app.storage.upload_bytes"), \
         patch("app.storage.delete_object") as mock_delete:

        # First export (rotation = 0)
        res1 = export_batch_zip(batch_id=1, db=db, _user=None)
        assert res1.headers["X-Export-Cached"] == "false"
        old_export = db.query(BatchExport).filter_by(batch_id=1).first()
        assert old_export is not None
        old_hash = old_export.manifest_hash
        old_key = old_export.r2_key

        # Update rotation
        crop.rotation_degrees = 90
        db.commit()

        # Second export -> Cache Miss due to new manifest hash
        res2 = export_batch_zip(batch_id=1, db=db, _user=None)

        assert res2.headers["X-Export-Cached"] == "false"
        # Stale archive was deleted from R2
        mock_delete.assert_called_with(old_key)

        # DB has only the new export row
        exports = db.query(BatchExport).filter_by(batch_id=1).all()
        assert len(exports) == 1
        assert exports[0].manifest_hash != old_hash


def test_export_batch_zip_intentional_duplicate_ships_both_sides():
    """intentional_duplicate is an acknowledged match that's expected to
    stay in inventory as-is (e.g. genuinely holding 2 copies of the same
    card) -- unlike confirmed_duplicate, neither side should be excluded
    from the export."""
    db = _make_session()
    batch = Batch(id=4, status=BatchStatus.complete, source_label="test_batch_intentional")
    db.add(batch)
    scan1 = RawScan(
        id=41,
        batch_id=4,
        r2_key_raw="raw/4/41.jpg",
        original_filename="card_a.jpg",
        pairing_key="card_a",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    scan2 = RawScan(
        id=42,
        batch_id=4,
        r2_key_raw="raw/4/42.jpg",
        original_filename="card_b.jpg",
        pairing_key="card_b",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    db.add_all([scan1, scan2])
    db.flush()

    crop1 = CardCrop(id=401, raw_scan_id=41, r2_key_cropped="cropped/4/401.jpg")
    crop2 = CardCrop(id=402, raw_scan_id=42, r2_key_cropped="cropped/4/402.jpg")
    db.add_all([crop1, crop2])
    db.flush()

    dup = DuplicateCandidate(
        card_crop_id_a=401,
        card_crop_id_b=402,
        status=DuplicateStatus.intentional_duplicate,
    )
    db.add(dup)
    db.commit()

    dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xd9"
    with patch("app.storage.download_bytes", return_value=dummy_jpeg), \
         patch("app.storage.upload_bytes") as mock_upload:
        res = export_batch_zip(batch_id=4, db=db, _user=None)

    assert res.status_code == 200
    uploaded_data = mock_upload.call_args[0][1]
    zf = zipfile.ZipFile(io.BytesIO(uploaded_data))
    assert zf.testzip() is None
    # Both sides of the intentional-duplicate pair shipped -- nothing
    # excluded, unlike the confirmed_duplicate case below.
    assert len(zf.namelist()) == 2


def test_export_batch_zip_empty_or_all_duplicates_raises_404():
    """If all crops are confirmed duplicates, export raises 404 and does not create an export record."""
    db = _make_session()
    batch = Batch(id=3, status=BatchStatus.complete)
    db.add(batch)
    scan1 = RawScan(
        id=31,
        batch_id=3,
        r2_key_raw="raw/3/31.jpg",
        original_filename="card_a.jpg",
        pairing_key="card_a",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    scan2 = RawScan(
        id=32,
        batch_id=3,
        r2_key_raw="raw/3/32.jpg",
        original_filename="card_b.jpg",
        pairing_key="card_b",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    db.add_all([scan1, scan2])
    db.flush()

    crop1 = CardCrop(id=301, raw_scan_id=31, r2_key_cropped="cropped/3/301.jpg")
    crop2 = CardCrop(id=302, raw_scan_id=32, r2_key_cropped="cropped/3/302.jpg")
    db.add_all([crop1, crop2])
    db.flush()

    # Mark crop 301 and 302 both as duplicate 'b' sides in confirmed duplicates
    dup1 = DuplicateCandidate(
        card_crop_id_a=301,
        card_crop_id_b=301,
        status=DuplicateStatus.confirmed_duplicate,
    )
    dup2 = DuplicateCandidate(
        card_crop_id_a=301,
        card_crop_id_b=302,
        status=DuplicateStatus.confirmed_duplicate,
    )
    db.add_all([dup1, dup2])
    db.commit()

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        export_batch_zip(batch_id=3, db=db, _user=None)
    assert exc_info.value.status_code == 404
    assert db.query(BatchExport).filter_by(batch_id=3).count() == 0


def test_export_batch_zip_storage_failure_raises():
    """If R2 storage download fails, the error is raised so FastAPI can return a 500
    instead of delivering a corrupted/empty ZIP."""
    db = _make_session()
    batch = Batch(id=2, status=BatchStatus.complete, source_label="test_batch_err")
    db.add(batch)
    scan = RawScan(
        id=20,
        batch_id=2,
        r2_key_raw="raw/2/20-front.jpg",
        original_filename="card_2_front.jpg",
        pairing_key="card_2",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    db.add(scan)
    crop = CardCrop(
        id=200,
        raw_scan_id=20,
        r2_key_cropped="cropped/2/200-front.jpg",
        rotation_degrees=0,
    )
    db.add(crop)
    db.commit()

    with patch("app.storage.download_bytes", side_effect=RuntimeError("R2 connection timeout")):
        with pytest.raises(RuntimeError, match="R2 connection timeout"):
            export_batch_zip(batch_id=2, db=db, _user=None)


def test_delete_batch_cleans_up_cached_export():
    """Hard-deleting a batch cleans up the cached BatchExport archive in R2."""
    db = _make_session()
    admin = User(name="admin_user", role=UserRole.admin)
    db.add(admin)
    batch = Batch(id=5, source_label="batch-5", status=BatchStatus.complete)
    db.add(batch)
    db.flush()

    raw_scan = RawScan(
        batch_id=batch.id,
        r2_key_raw=f"raw/{batch.id}/scan.jpg",
        original_filename="card.jpg",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    db.add(raw_scan)
    db.flush()

    crop = CardCrop(raw_scan_id=raw_scan.id, r2_key_cropped=f"cropped/{batch.id}/crop.jpg")
    db.add(crop)
    db.flush()

    batch_export = BatchExport(
        batch_id=batch.id,
        manifest_hash="hash123",
        r2_key=f"exports/{batch.id}/hash123.zip",
        file_size_bytes=1024,
        image_count=1,
    )
    db.add(batch_export)
    db.commit()

    with patch("app.api.batches.storage") as mock_storage, \
         patch("app.api.batches.redis_state"), \
         patch("app.api.batches.log_event"):

        mock_storage.temp_upload_key.return_value = f"tmp/uploads/{batch.id}.zip"

        delete_batch(batch_id=batch.id, db=db, current_user=admin)

        # Verify that export R2 key was deleted
        mock_storage.delete_object.assert_any_call(f"exports/{batch.id}/hash123.zip")
        assert db.get(Batch, batch.id) is None
        assert db.query(BatchExport).filter_by(batch_id=batch.id).first() is None


def test_export_batch_zip_blocked_when_not_complete():
    """Verify that export is rejected with 409 Conflict if pipeline is not complete."""
    from fastapi import HTTPException

    db = _make_session()
    # 1. Batch in cropping with pending scans
    batch = Batch(id=6, status=BatchStatus.cropping, source_label="incomplete_batch")
    db.add(batch)
    scan = RawScan(
        id=61,
        batch_id=6,
        r2_key_raw="raw/6/61.jpg",
        original_filename="card_61.jpg",
        pairing_key="card_61",
        side=ScanSide.front,
        status=ScanStatus.pending,
    )
    db.add(scan)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        export_batch_zip(batch_id=6, db=db, _user=None)
    assert exc_info.value.status_code == 409
    assert "pipeline is not complete" in exc_info.value.detail

    # 2. Batch in rotation_review (crop unconfirmed)
    scan.status = ScanStatus.cropped
    crop = CardCrop(
        id=601,
        raw_scan_id=61,
        r2_key_cropped="cropped/6/601.jpg",
        rotation_degrees=0,
        rotation_confirmed_at=None,
    )
    db.add(crop)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        export_batch_zip(batch_id=6, db=db, _user=None)
    assert exc_info.value.status_code == 409
    assert "current status: rotation_review" in exc_info.value.detail

