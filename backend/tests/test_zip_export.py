import io
import zipfile
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.batches import export_batch_zip
from app.db import Base
from app.models import Batch, BatchStatus, CardCrop, RawScan, ScanSide, ScanStatus


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_export_batch_zip_success():
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

    with patch("app.storage.download_bytes", return_value=dummy_jpeg):
        response = export_batch_zip(batch_id=1, db=db, _user=None)

    assert response.status_code == 200
    assert response.media_type == "application/zip"
    assert response.headers["Content-Disposition"] == 'attachment; filename="test_batch.zip"'
    assert response.headers["Content-Length"] == str(len(response.body))

    zf = zipfile.ZipFile(io.BytesIO(response.body))
    assert zf.testzip() is None
    assert zf.namelist() == ["card_1_front_front.jpg"]
    assert zf.read("card_1_front_front.jpg") == dummy_jpeg


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
