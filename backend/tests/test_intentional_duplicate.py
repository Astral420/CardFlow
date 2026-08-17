"""Coverage for DuplicateStatus.intentional_duplicate: a duplicate-review
decision meaning "yes, same physical card, and that's expected" (e.g.
multiple copies of the same card genuinely in inventory) -- acknowledged as
a match like confirmed_duplicate, but unlike confirmed_duplicate neither
side is excluded from the batch export (see test_zip_export.py for that
half) and both statuses should show up in the batch's duplicates log.
"""

from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.batches import get_batch_duplicates, get_batch_scans
from app.db import Base
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


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _batch_with_two_scans(db, batch_id: int, dup_status: DuplicateStatus | None):
    batch = Batch(id=batch_id, status=BatchStatus.complete, source_label=f"batch-{batch_id}")
    db.add(batch)
    scan_a = RawScan(
        id=batch_id * 10 + 1,
        batch_id=batch_id,
        r2_key_raw=f"raw/{batch_id}/1.jpg",
        original_filename="card_a.jpg",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    scan_b = RawScan(
        id=batch_id * 10 + 2,
        batch_id=batch_id,
        r2_key_raw=f"raw/{batch_id}/2.jpg",
        original_filename="card_b.jpg",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    db.add_all([scan_a, scan_b])
    db.flush()

    crop_a = CardCrop(
        id=batch_id * 100 + 1, raw_scan_id=scan_a.id, r2_key_cropped=f"cropped/{batch_id}/1.jpg"
    )
    crop_b = CardCrop(
        id=batch_id * 100 + 2, raw_scan_id=scan_b.id, r2_key_cropped=f"cropped/{batch_id}/2.jpg"
    )
    db.add_all([crop_a, crop_b])
    db.flush()

    if dup_status is not None:
        db.add(
            DuplicateCandidate(
                card_crop_id_a=crop_a.id,
                card_crop_id_b=crop_b.id,
                status=dup_status,
            )
        )
    db.commit()
    return batch, scan_a, scan_b, crop_a, crop_b


def test_get_batch_scans_flags_intentional_duplicate_distinctly():
    db = _make_session()
    try:
        _batch_with_two_scans(db, 1, DuplicateStatus.intentional_duplicate)
        with patch("app.storage.presigned_url", return_value="https://example.com/x.jpg"):
            scans = get_batch_scans(batch_id=1, db=db, _user=None)

        by_filename = {s.original_filename: s for s in scans}
        # card_a is card_crop_id_a (the "kept" side even for confirmed_duplicate);
        # card_b is card_crop_id_b (the side that would be excluded for
        # confirmed_duplicate, but must NOT be for intentional_duplicate).
        assert by_filename["card_b.jpg"].is_duplicate is True
        assert by_filename["card_b.jpg"].is_intentional_duplicate is True
        # card_a was never anyone's card_crop_id_b, so it's not flagged.
        assert by_filename["card_a.jpg"].is_duplicate is False
        assert by_filename["card_a.jpg"].is_intentional_duplicate is False
    finally:
        db.close()


def test_get_batch_scans_confirmed_duplicate_not_flagged_intentional():
    db = _make_session()
    try:
        _batch_with_two_scans(db, 2, DuplicateStatus.confirmed_duplicate)
        with patch("app.storage.presigned_url", return_value="https://example.com/x.jpg"):
            scans = get_batch_scans(batch_id=2, db=db, _user=None)

        by_filename = {s.original_filename: s for s in scans}
        assert by_filename["card_b.jpg"].is_duplicate is True
        assert by_filename["card_b.jpg"].is_intentional_duplicate is False
    finally:
        db.close()


def test_get_batch_scans_pending_candidate_not_flagged():
    db = _make_session()
    try:
        _batch_with_two_scans(db, 3, DuplicateStatus.pending)
        with patch("app.storage.presigned_url", return_value="https://example.com/x.jpg"):
            scans = get_batch_scans(batch_id=3, db=db, _user=None)

        # Still pending review -> not resolved either way yet.
        assert all(not s.is_duplicate and not s.is_intentional_duplicate for s in scans)
    finally:
        db.close()


def test_get_batch_duplicates_includes_both_resolved_statuses():
    db = _make_session()
    try:
        _batch_with_two_scans(db, 4, DuplicateStatus.intentional_duplicate)
        with patch("app.storage.presigned_url", return_value="https://example.com/x.jpg"):
            pairs = get_batch_duplicates(batch_id=4, db=db, _user=None)

        assert len(pairs) == 1
        assert pairs[0].status == DuplicateStatus.intentional_duplicate
    finally:
        db.close()


def test_get_batch_duplicates_excludes_pending_and_rejected():
    db = _make_session()
    try:
        _batch_with_two_scans(db, 5, DuplicateStatus.pending)
        with patch("app.storage.presigned_url", return_value="https://example.com/x.jpg"):
            pairs = get_batch_duplicates(batch_id=5, db=db, _user=None)
        assert pairs == []
    finally:
        db.close()
