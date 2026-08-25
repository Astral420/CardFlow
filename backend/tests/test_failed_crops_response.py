from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.batches import get_batch_scans
from app.db import Base
from app.models import Batch, BatchStatus, CardCrop, RawScan, ScanSide, ScanStatus


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_batch_scans_only_presigns_raw_images_for_failed_crops(monkeypatch):
    db = _make_session()
    batch = Batch(status=BatchStatus.rotation_review)
    db.add(batch)
    db.flush()

    crop_error = RawScan(
        batch_id=batch.id,
        r2_key_raw="raw/crop-error.jpg",
        original_filename="card-1-front.jpg",
        side=ScanSide.front,
        status=ScanStatus.crop_failed,
    )
    bad_ratio = RawScan(
        batch_id=batch.id,
        r2_key_raw="raw/bad-ratio.jpg",
        original_filename="card-1-back.jpg",
        side=ScanSide.back,
        status=ScanStatus.crop_failed,
    )
    successful = RawScan(
        batch_id=batch.id,
        r2_key_raw="raw/success.jpg",
        original_filename="card-2-front.jpg",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    db.add_all([crop_error, bad_ratio, successful])
    db.flush()
    db.add(
        CardCrop(
            raw_scan_id=bad_ratio.id,
            r2_key_cropped="cropped/bad-ratio.jpg",
            aspect_ratio_ok=False,
        )
    )
    db.add(
        CardCrop(
            raw_scan_id=successful.id,
            r2_key_cropped="cropped/success.jpg",
            aspect_ratio_ok=True,
        )
    )
    db.commit()

    presigned_keys = []

    def fake_presigned_url(key):
        presigned_keys.append(key)
        return f"https://example.test/{key}"

    monkeypatch.setattr("app.api.batches.storage.presigned_url", fake_presigned_url)

    scans = get_batch_scans(batch.id, db=db, _user=None)
    by_filename = {scan.original_filename: scan for scan in scans}

    assert by_filename["card-1-front.jpg"].raw_image_url.endswith(
        "/raw/crop-error.jpg"
    )
    assert by_filename["card-1-front.jpg"].crop_failure_reason == "crop_error"
    assert by_filename["card-1-back.jpg"].raw_image_url.endswith(
        "/raw/bad-ratio.jpg"
    )
    assert (
        by_filename["card-1-back.jpg"].crop_failure_reason
        == "bad_aspect_ratio"
    )
    assert by_filename["card-2-front.jpg"].raw_image_url is None
    assert by_filename["card-2-front.jpg"].crop_failure_reason is None
    assert "raw/success.jpg" not in presigned_keys


