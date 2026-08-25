"""Regression coverage for "completed batch reopened by a later re-upload".

Cross-batch duplicate detection (app.dedup.matching.find_cross_batch_duplicates)
intentionally compares a new upload's cards against cards in *every* batch,
including ones that already finished their pipeline. That can create a
pending DuplicateCandidate row that points at an old, already-`complete`
batch. Before the fix, refresh_batch_status() unconditionally re-derived
status from the child rows every time it ran, so simply viewing that old
batch again (GET /api/batches/{id}) or resolving the candidate in the
review queue would flip it from "complete" back to "duplicate_review" --
i.e. re-enter the pipeline -- even though nothing about the batch itself
was actually unfinished.

This test drives refresh_batch_status() directly against an in-memory
sqlite database that reproduces that exact shape: batch A is fully
complete, then a duplicate candidate is recorded between one of batch A's
crops and a crop from a brand new batch B.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.batch_status import refresh_batch_status
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


def _finished_batch_with_crop(db):
    """A batch that has fully finished its own pipeline: one scan, cropped,
    rotation-confirmed, no pending duplicates of its own."""
    batch = Batch(status=BatchStatus.duplicate_review)
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

    crop = CardCrop(
        raw_scan_id=raw_scan.id,
        r2_key_cropped="cropped/1/1-front.jpg",
        rotation_confirmed_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
        dedup_completed_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
        hash_0="0" * 16,
        color_sig_0=[0.0],
    )
    db.add(crop)
    db.flush()

    # Batch has no pending duplicates of its own -> refresh should settle
    # on "complete".
    status = refresh_batch_status(db, batch.id)
    db.commit()
    assert status == BatchStatus.complete
    return batch, crop


def test_completed_batch_is_not_reopened_by_new_cross_batch_duplicate():
    db = _make_session()
    try:
        old_batch, old_crop = _finished_batch_with_crop(db)

        # A brand new batch uploads a card that turns out to be a duplicate
        # of the old, completed batch's card. This is exactly what
        # find_cross_batch_duplicates + record_duplicate_candidates
        # produces in production.
        new_batch = Batch(status=BatchStatus.duplicate_review)
        db.add(new_batch)
        db.flush()

        new_raw_scan = RawScan(
            batch_id=new_batch.id,
            r2_key_raw="raw/2/card-1-front.jpg",
            original_filename="card-1-front.jpg",
            side=ScanSide.front,
            status=ScanStatus.cropped,
        )
        db.add(new_raw_scan)
        db.flush()

        new_crop = CardCrop(
            raw_scan_id=new_raw_scan.id,
            r2_key_cropped="cropped/2/2-front.jpg",
            hash_0="0" * 16,
            color_sig_0=[0.0],
        )
        db.add(new_crop)
        db.flush()

        crop_a_id, crop_b_id = sorted((old_crop.id, new_crop.id))
        db.add(
            DuplicateCandidate(
                card_crop_id_a=crop_a_id,
                card_crop_id_b=crop_b_id,
                structural_score=0.0,
                color_score=0.0,
                filename_match=True,
                status=DuplicateStatus.pending,
            )
        )
        db.commit()

        # Simulate the old batch's detail page being viewed again (or the
        # candidate being resolved in the review queue) after the new
        # cross-batch candidate was recorded.
        status = refresh_batch_status(db, old_batch.id)
        db.commit()
        db.refresh(old_batch)

        assert status == BatchStatus.complete
        assert old_batch.status == BatchStatus.complete
    finally:
        db.close()


def test_non_terminal_batch_still_advances_normally():
    """Sanity check the fix didn't turn refresh_batch_status into a no-op:
    a batch that hasn't finished yet must still be derived as before."""
    db = _make_session()
    try:
        batch = Batch(status=BatchStatus.extracting)
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
        db.commit()

        crop = CardCrop(
            raw_scan_id=raw_scan.id,
            r2_key_cropped="cropped/1/1-front.jpg",
            hash_0="0" * 16,
            color_sig_0=[0.0],
        )
        db.add(crop)
        db.commit()

        # rotation not confirmed yet -> should land on rotation_review
        status = refresh_batch_status(db, batch.id)
        db.commit()
        assert status == BatchStatus.rotation_review
    finally:
        db.close()


def test_confirmed_front_waits_for_duplicate_detection_before_completion():
    db = _make_session()
    try:
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
        crop = CardCrop(
            raw_scan_id=raw_scan.id,
            r2_key_cropped="cropped/1/1-front.jpg",
            rotation_confirmed_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ),
            hash_0="0" * 16,
            color_sig_0=[0.0],
        )
        db.add(crop)
        db.commit()

        assert refresh_batch_status(db, batch.id) == BatchStatus.rotation_review

        crop.dedup_completed_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )
        assert refresh_batch_status(db, batch.id) == BatchStatus.complete
    finally:
        db.close()


def test_skipped_scan_gates_status_same_as_cropped():
    """`skipped` (crop transform was a no-op -- image was already properly
    cropped, see app.vision.crop.CropResult.already_cropped) must be
    treated identically to `cropped` for pipeline-progress purposes: still
    needs rotation review, and once rotation is confirmed and there are no
    pending duplicates, the batch still reaches `complete`. A `skipped`
    scan getting excluded here would silently strand it out of rotation
    review / hashing / dedup forever."""
    db = _make_session()
    try:
        batch = Batch(status=BatchStatus.extracting)
        db.add(batch)
        db.flush()

        raw_scan = RawScan(
            batch_id=batch.id,
            r2_key_raw="raw/1/card-1-front.jpg",
            original_filename="card-1-front.jpg",
            side=ScanSide.front,
            status=ScanStatus.skipped,
        )
        db.add(raw_scan)
        db.flush()

        crop = CardCrop(
            raw_scan_id=raw_scan.id,
            r2_key_cropped="cropped/1/1-front.jpg",
        )
        db.add(crop)
        db.commit()

        # Rotation not confirmed yet -> same as a `cropped` scan would be.
        status = refresh_batch_status(db, batch.id)
        db.commit()
        assert status == BatchStatus.rotation_review

        # Confirm rotation, then re-derive -> should progress past rotation
        # review exactly like `cropped` does, straight to complete (no
        # pending duplicates).
        crop.rotation_confirmed_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )
        crop.dedup_completed_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )
        crop.hash_0 = "0" * 16
        crop.color_sig_0 = [0.0]
        db.commit()

        status = refresh_batch_status(db, batch.id)
        db.commit()
        assert status == BatchStatus.complete
    finally:
        db.close()
