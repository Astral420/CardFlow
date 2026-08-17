"""Regression coverage: app.api.cards.get_card constructs DuplicateCandidateOut
directly (not via app.api.duplicates._to_out), so it needed updating
alongside the batch_id/source_label fields added to that schema for the
duplicate-review batch label feature -- otherwise any card with duplicate
history would 500 on a missing-required-field pydantic validation error.
"""

from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.cards import get_card
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


def test_get_card_duplicate_history_includes_batch_label():
    db = _make_session()
    try:
        batch = Batch(status=BatchStatus.complete, source_label="acme-batch-7")
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

        db.add(
            DuplicateCandidate(
                card_crop_id_a=crop_a.id,
                card_crop_id_b=crop_b.id,
                status=DuplicateStatus.intentional_duplicate,
            )
        )
        db.commit()

        with patch("app.storage.presigned_url", return_value="https://example.com/x.jpg"):
            detail = get_card(crop_id=crop_a.id, db=db, _user=None)

        assert len(detail.duplicate_history) == 1
        assert detail.duplicate_history[0].batch_id == batch.id
        assert detail.duplicate_history[0].source_label == "acme-batch-7"
    finally:
        db.close()
