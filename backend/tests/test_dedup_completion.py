from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.tasks.duplicates as duplicate_task
from app.db import Base
from app.models import Batch, BatchStatus, CardCrop, RawScan, ScanSide, ScanStatus


def test_duplicate_task_marks_front_complete_even_when_no_matches(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    TestSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    setup_db = TestSessionLocal()
    batch = Batch(status=BatchStatus.rotation_review)
    setup_db.add(batch)
    setup_db.flush()
    scan = RawScan(
        batch_id=batch.id,
        r2_key_raw="raw/1/card-1-front.jpg",
        original_filename="card-1-front.jpg",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    setup_db.add(scan)
    setup_db.flush()
    crop = CardCrop(
        raw_scan_id=scan.id,
        r2_key_cropped="cropped/1/1-front.jpg",
        rotation_confirmed_at=datetime.now(timezone.utc),
        hash_0="0" * 16,
        color_sig_0=[0.0],
    )
    setup_db.add(crop)
    setup_db.commit()
    batch_id = batch.id
    crop_id = crop.id
    setup_db.close()

    monkeypatch.setattr(duplicate_task, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(
        duplicate_task, "find_within_batch_duplicates", lambda *_args: []
    )
    monkeypatch.setattr(
        duplicate_task, "record_duplicate_candidates", lambda *_args: []
    )

    duplicate_task._find_duplicates(crop_id)

    verify_db = TestSessionLocal()
    try:
        processed_crop = verify_db.get(CardCrop, crop_id)
        processed_batch = verify_db.get(Batch, batch_id)
        assert processed_crop.dedup_completed_at is not None
        assert processed_batch.status == BatchStatus.complete
    finally:
        verify_db.close()
