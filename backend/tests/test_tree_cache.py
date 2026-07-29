"""Regression coverage for the BK-tree rebuild-on-every-call fix.

`find_cross_batch_duplicates` used to load every historical hashed crop
and rebuild a fresh BKTree on every single call. The fix (app.dedup.
tree_cache) keeps one tree per process, built once lazily and then kept
current via an incremental "catch up" query instead of a full rebuild.

These tests exercise the cache module directly (build-once, incremental
catch-up, process-reset-via-reset()) and then the integration through
find_cross_batch_duplicates to make sure cross-batch matching behavior is
unchanged by the rewrite.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.dedup import tree_cache
from app.dedup.matching import find_cross_batch_duplicates
from app.db import Base
from app.models import Batch, BatchStatus, CardCrop, RawScan, ScanSide, ScanStatus

HASH_A = "f0f0f0f0f0f0f0f0"
HASH_A_CLOSE = "f0f0f0f0f0f0f0f1"  # 1 bit away from HASH_A
HASH_FAR = "0000000000000000"


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _add_hashed_crop(
    db, batch_id: int, filename: str, hash_0: str, color_sig=None
) -> CardCrop:
    raw_scan = RawScan(
        batch_id=batch_id,
        r2_key_raw=f"raw/{batch_id}/{filename}",
        original_filename=filename,
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    db.add(raw_scan)
    db.flush()

    # A valid (normalized, non-all-zero) histogram -- cv2's Bhattacharyya
    # distance is NaN for an all-zero histogram, and _best_match correctly
    # treats a non-finite color score as "no match", so an all-zero
    # signature would silently defeat these tests.
    crop = CardCrop(
        raw_scan_id=raw_scan.id,
        aspect_ratio_ok=True,
        hash_0=hash_0,
        color_sig_0=color_sig if color_sig is not None else [1.0] + [0.0] * 7,
    )
    db.add(crop)
    db.flush()
    return crop


def setup_function(_):
    # Each test gets a fresh process-local cache; otherwise a tree built
    # against one test's in-memory sqlite engine would leak into the next.
    tree_cache.reset()


def test_get_tree_builds_lazily_from_existing_hashed_crops():
    db = _make_session()
    batch = Batch(status=BatchStatus.duplicate_review)
    db.add(batch)
    db.flush()
    crop = _add_hashed_crop(db, batch.id, "card-1-front.jpg", HASH_A)
    db.commit()

    tree = tree_cache.get_tree(db)
    results = {payload for payload, _dist in tree.query(HASH_A, max_distance=0)}
    assert results == {crop.id}


def test_get_tree_catches_up_incrementally_without_full_rebuild():
    db = _make_session()
    batch = Batch(status=BatchStatus.duplicate_review)
    db.add(batch)
    db.flush()
    crop_1 = _add_hashed_crop(db, batch.id, "card-1-front.jpg", HASH_A)
    db.commit()

    # First call builds the tree from scratch.
    tree_cache.get_tree(db)

    # A new crop gets hashed later (simulating another card processed
    # after this process's tree was already built).
    crop_2 = _add_hashed_crop(db, batch.id, "card-2-front.jpg", HASH_A_CLOSE)
    db.commit()

    # The next call must pick up crop_2 without needing a reset/rebuild.
    tree = tree_cache.get_tree(db)
    results = {payload for payload, _dist in tree.query(HASH_A, max_distance=2)}
    assert results == {crop_1.id, crop_2.id}


def test_cross_batch_duplicates_still_excludes_same_batch_matches():
    db = _make_session()
    batch_a = Batch(status=BatchStatus.duplicate_review)
    batch_b = Batch(status=BatchStatus.duplicate_review)
    db.add_all([batch_a, batch_b])
    db.flush()

    query_crop = _add_hashed_crop(db, batch_a.id, "card-1-front.jpg", HASH_A)
    same_batch_match = _add_hashed_crop(
        db, batch_a.id, "card-2-front.jpg", HASH_A_CLOSE
    )
    other_batch_match = _add_hashed_crop(
        db, batch_b.id, "card-3-front.jpg", HASH_A_CLOSE
    )
    far_crop = _add_hashed_crop(db, batch_b.id, "card-4-front.jpg", HASH_FAR)
    db.commit()

    hits = find_cross_batch_duplicates(db, query_crop, batch_a.id)
    hit_ids = {hit.other_crop_id for hit in hits}

    assert other_batch_match.id in hit_ids
    assert same_batch_match.id not in hit_ids  # same batch: not this function's job
    assert far_crop.id not in hit_ids  # too far a hash distance


def test_cross_batch_duplicates_returns_empty_when_crop_not_hashed_yet():
    db = _make_session()
    batch = Batch(status=BatchStatus.rotation_review)
    db.add(batch)
    db.flush()
    raw_scan = RawScan(
        batch_id=batch.id,
        r2_key_raw="raw/1/card-1-front.jpg",
        original_filename="card-1-front.jpg",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    db.add(raw_scan)
    db.flush()
    unhashed_crop = CardCrop(raw_scan_id=raw_scan.id, aspect_ratio_ok=True)
    db.add(unhashed_crop)
    db.commit()

    assert find_cross_batch_duplicates(db, unhashed_crop, batch.id) == []
