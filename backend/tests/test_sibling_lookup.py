"""Regression coverage for the find_sibling_crop N+1 fix.

`find_sibling_crop` (and its two now-removed duplicates in rotation.py and
cards.py) used to load every CardCrop in a batch and linear-scan for a
filename match. The fix adds an auto-computed, indexed `pairing_key`
column on RawScan and queries directly against it. These tests exercise:

1. That RawScan.pairing_key is actually populated automatically (via the
   before_insert/before_update event listener) for any code path that
   creates a RawScan -- not just the extract_batch task.
2. That find_sibling_crop() still returns the correct sibling (or None)
   using that column.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.common import find_sibling_crop
from app.db import Base
from app.models import Batch, BatchStatus, CardCrop, RawScan, ScanSide, ScanStatus


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _add_crop(db, batch_id: int, filename: str, side: ScanSide) -> CardCrop:
    raw_scan = RawScan(
        batch_id=batch_id,
        r2_key_raw=f"raw/{batch_id}/{filename}",
        original_filename=filename,
        side=side,
        status=ScanStatus.cropped,
    )
    db.add(raw_scan)
    db.flush()

    crop = CardCrop(raw_scan_id=raw_scan.id, aspect_ratio_ok=True)
    db.add(crop)
    db.flush()
    return crop


def test_pairing_key_is_computed_automatically_on_insert():
    """Any RawScan creation path gets pairing_key populated -- callers never
    set it explicitly."""
    db = _make_session()
    batch = Batch(status=BatchStatus.cropping)
    db.add(batch)
    db.flush()

    raw_scan = RawScan(
        batch_id=batch.id,
        r2_key_raw="raw/1/card-42-front.jpg",
        original_filename="card-42-FRONT.jpg",
        side=ScanSide.front,
        status=ScanStatus.pending,
    )
    db.add(raw_scan)
    db.flush()

    assert raw_scan.pairing_key == "card-42"


def test_pairing_key_updates_if_filename_changes():
    db = _make_session()
    batch = Batch(status=BatchStatus.cropping)
    db.add(batch)
    db.flush()

    raw_scan = RawScan(
        batch_id=batch.id,
        r2_key_raw="raw/1/card-1-front.jpg",
        original_filename="card-1-front.jpg",
        side=ScanSide.front,
        status=ScanStatus.pending,
    )
    db.add(raw_scan)
    db.commit()
    assert raw_scan.pairing_key == "card-1"

    raw_scan.original_filename = "card-99-front.jpg"
    db.commit()
    assert raw_scan.pairing_key == "card-99"


def test_find_sibling_crop_returns_matching_back_for_front():
    db = _make_session()
    batch = Batch(status=BatchStatus.rotation_review)
    db.add(batch)
    db.flush()

    front = _add_crop(db, batch.id, "card-7-front.jpg", ScanSide.front)
    back = _add_crop(db, batch.id, "card-7-back.jpg", ScanSide.back)
    db.commit()

    assert find_sibling_crop(db, front).id == back.id
    assert find_sibling_crop(db, back).id == front.id


def test_find_sibling_crop_does_not_cross_batches():
    """A same-pairing-key filename in a *different* batch must not be
    picked up as a sibling."""
    db = _make_session()
    batch_a = Batch(status=BatchStatus.rotation_review)
    batch_b = Batch(status=BatchStatus.rotation_review)
    db.add_all([batch_a, batch_b])
    db.flush()

    front_a = _add_crop(db, batch_a.id, "card-1-front.jpg", ScanSide.front)
    _add_crop(db, batch_b.id, "card-1-back.jpg", ScanSide.back)  # different batch
    db.commit()

    assert find_sibling_crop(db, front_a) is None


def test_find_sibling_crop_returns_none_when_only_one_side_scanned():
    db = _make_session()
    batch = Batch(status=BatchStatus.rotation_review)
    db.add(batch)
    db.flush()

    front = _add_crop(db, batch.id, "card-3-front.jpg", ScanSide.front)
    db.commit()

    assert find_sibling_crop(db, front) is None


def test_find_sibling_crop_does_not_match_same_side_duplicate_filename():
    """Two scans that happen to share a pairing key and side (e.g. a bad
    duplicate upload) should not be paired with each other."""
    db = _make_session()
    batch = Batch(status=BatchStatus.rotation_review)
    db.add(batch)
    db.flush()

    front_1 = _add_crop(db, batch.id, "card-5-front.jpg", ScanSide.front)
    _add_crop(db, batch.id, "card-5-front.jpg", ScanSide.front)
    db.commit()

    assert find_sibling_crop(db, front_1) is None
