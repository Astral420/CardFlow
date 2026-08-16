"""Coverage for app.api.duplicates:
- decide() accepts DuplicateStatus.intentional_duplicate as a valid
  decision (third terminal outcome alongside confirmed_duplicate/rejected).
- DuplicateCandidateOut surfaces batch_id/source_label so the (intentionally
  global, not batch-scoped -- see _next_pending) review queue can show
  which batch is currently being reviewed.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.duplicates import decide
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
    User,
    UserRole,
)
from app.schemas import DuplicateDecisionRequest


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _pending_candidate(db):
    batch = Batch(status=BatchStatus.duplicate_review, source_label="acme-batch-42")
    db.add(batch)
    db.flush()

    scan_a = RawScan(
        batch_id=batch.id,
        r2_key_raw="raw/1/1.jpg",
        original_filename="card_a.jpg",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    scan_b = RawScan(
        batch_id=batch.id,
        r2_key_raw="raw/1/2.jpg",
        original_filename="card_b.jpg",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    db.add_all([scan_a, scan_b])
    db.flush()

    crop_a = CardCrop(raw_scan_id=scan_a.id, r2_key_cropped="cropped/1/1.jpg")
    crop_b = CardCrop(raw_scan_id=scan_b.id, r2_key_cropped="cropped/1/2.jpg")
    db.add_all([crop_a, crop_b])
    db.flush()

    candidate = DuplicateCandidate(
        card_crop_id_a=crop_a.id,
        card_crop_id_b=crop_b.id,
        status=DuplicateStatus.pending,
    )
    db.add(candidate)
    db.commit()
    return batch, candidate


def test_decide_accepts_intentional_duplicate():
    db = _make_session()
    try:
        batch, candidate = _pending_candidate(db)
        reviewer = User(name="reviewer_1", role=UserRole.reviewer)
        db.add(reviewer)
        db.commit()

        decide(
            candidate.id,
            DuplicateDecisionRequest(status=DuplicateStatus.intentional_duplicate),
            db=db,
            current_user=reviewer,
        )

        db.refresh(candidate)
        assert candidate.status == DuplicateStatus.intentional_duplicate
        assert candidate.reviewed_by == reviewer.id
        assert candidate.reviewed_at is not None
    finally:
        db.close()


def test_next_pending_surfaces_batch_label():
    db = _make_session()
    try:
        batch, candidate = _pending_candidate(db)
        from unittest.mock import patch

        from app.api.duplicates import _next_pending

        with patch("app.storage.presigned_url", return_value="https://example.com/x.jpg"):
            out = _next_pending(db)

        assert out is not None
        assert out.batch_id == batch.id
        assert out.source_label == "acme-batch-42"
    finally:
        db.close()
