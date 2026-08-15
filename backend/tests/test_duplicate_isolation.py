"""Test batch isolation during duplicate detection."""

from datetime import datetime, timezone
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.dedup.matching import find_within_batch_duplicates, record_duplicate_candidates
from app.models import (
    Batch,
    BatchStatus,
    CardCrop,
    DuplicateCandidate,
    DuplicateStatus,
    RawScan,
    ScanSide,
    ScanStatus,
)
from app.tasks.duplicates import _find_duplicates


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_intra_batch_duplicate_detected():
    db = _make_session()
    try:
        batch = Batch(status=BatchStatus.duplicate_review)
        db.add(batch)
        db.flush()

        scan_1 = RawScan(
            batch_id=batch.id,
            r2_key_raw="raw/1/card-1-front.jpg",
            original_filename="card-1-front.jpg",
            side=ScanSide.front,
            status=ScanStatus.cropped,
        )
        scan_2 = RawScan(
            batch_id=batch.id,
            r2_key_raw="raw/1/card-2-front.jpg",
            original_filename="card-2-front.jpg",
            side=ScanSide.front,
            status=ScanStatus.cropped,
        )
        db.add_all([scan_1, scan_2])
        db.flush()

        crop_1 = CardCrop(
            raw_scan_id=scan_1.id,
            r2_key_cropped="cropped/1/1-front.jpg",
            rotation_confirmed_at=datetime.now(timezone.utc),
            hash_0="0" * 16,
            color_sig_0=[1.0] + [0.0] * 7,
        )
        crop_2 = CardCrop(
            raw_scan_id=scan_2.id,
            r2_key_cropped="cropped/1/2-front.jpg",
            rotation_confirmed_at=datetime.now(timezone.utc),
            hash_0="0" * 16,
            color_sig_0=[1.0] + [0.0] * 7,
        )
        db.add_all([crop_1, crop_2])
        db.commit()

        hits = find_within_batch_duplicates(db, crop_2, batch.id)
        assert len(hits) == 1
        assert hits[0].other_crop_id == crop_1.id

        created = record_duplicate_candidates(db, crop_2, hits)
        db.commit()
        assert len(created) == 1
        assert created[0].status == DuplicateStatus.pending
    finally:
        db.close()


def test_cross_batch_duplicate_is_ignored_by_task():
    db = _make_session()
    try:
        # Existing completed batch A with card
        batch_a = Batch(status=BatchStatus.complete)
        db.add(batch_a)
        db.flush()

        scan_a = RawScan(
            batch_id=batch_a.id,
            r2_key_raw="raw/1/card-1-front.jpg",
            original_filename="card-1-front.jpg",
            side=ScanSide.front,
            status=ScanStatus.cropped,
        )
        db.add(scan_a)
        db.flush()

        crop_a = CardCrop(
            raw_scan_id=scan_a.id,
            r2_key_cropped="cropped/1/1-front.jpg",
            rotation_confirmed_at=datetime.now(timezone.utc),
            hash_0="0" * 16,
            color_sig_0=[1.0] + [0.0] * 7,
        )
        db.add(crop_a)

        # New batch B uploading the EXACT SAME card image
        batch_b = Batch(status=BatchStatus.duplicate_review)
        db.add(batch_b)
        db.flush()

        scan_b = RawScan(
            batch_id=batch_b.id,
            r2_key_raw="raw/2/card-1-front.jpg",
            original_filename="card-1-front.jpg",
            side=ScanSide.front,
            status=ScanStatus.cropped,
        )
        db.add(scan_b)
        db.flush()

        crop_b = CardCrop(
            raw_scan_id=scan_b.id,
            r2_key_cropped="cropped/2/2-front.jpg",
            rotation_confirmed_at=datetime.now(timezone.utc),
            hash_0="0" * 16,
            color_sig_0=[1.0] + [0.0] * 7,
        )
        db.add(crop_b)
        db.commit()

        # Run _find_duplicates on crop_b with SessionLocal mocked to our test db
        with patch("app.tasks.duplicates.SessionLocal", return_value=db):
            _find_duplicates(crop_b.id)

        # Confirm NO duplicate candidate was recorded between batch A and batch B
        candidates = db.query(DuplicateCandidate).all()
        assert len(candidates) == 0
    finally:
        db.close()
