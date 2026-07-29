"""Regression coverage for the "no rollback on exception" fix.

Every Celery task did `db = SessionLocal(); try: ... db.commit(); finally:
db.close()` with no except/rollback. If something raised after a
`db.flush()` had already sent a partial insert to the database (e.g.
storage.upload_bytes() failing after crop.py's card_crop flush), the
session would just close -- relying on SQLAlchemy's implicit rollback-on-
close rather than an explicit one.

This test drives crop_scan's underlying function directly (bypassing
Celery's dispatch machinery, matching this project's existing style of
testing task bodies as plain functions) with a SessionLocal patched onto
an in-memory sqlite engine, and forces storage.upload_bytes to raise after
the card_crop row has already been flushed. It asserts:

1. The exception still propagates (Celery needs to see the task failed).
2. The flushed-but-never-committed CardCrop row does not linger in the
   database afterwards -- i.e. it was actually rolled back, not merely
   left uncommitted-and-hopefully-cleaned-up by close().
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Batch, BatchStatus, CardCrop, RawScan, ScanSide, ScanStatus
from app.vision.crop import CropResult


def _make_sessionmaker():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_crop_scan_rolls_back_partial_state_when_upload_fails(monkeypatch):
    import app.tasks.crop as crop_task

    TestSessionLocal = _make_sessionmaker()
    monkeypatch.setattr(crop_task, "SessionLocal", TestSessionLocal)

    setup_db = TestSessionLocal()
    batch = Batch(status=BatchStatus.cropping)
    setup_db.add(batch)
    setup_db.flush()
    raw_scan = RawScan(
        batch_id=batch.id,
        r2_key_raw="raw/1/card-1-front.jpg",
        original_filename="card-1-front.jpg",
        side=ScanSide.front,
        status=ScanStatus.pending,
    )
    setup_db.add(raw_scan)
    setup_db.commit()
    raw_scan_id = raw_scan.id
    setup_db.close()

    monkeypatch.setattr(
        crop_task.storage, "download_bytes", lambda key: b"fake-image-bytes"
    )
    monkeypatch.setattr(
        crop_task,
        "auto_crop",
        lambda raw_bytes: CropResult(
            image_bytes=b"cropped",
            bbox=[[0, 0], [1, 0], [1, 1], [0, 1]],
            aspect_ratio=1.4,
            aspect_ratio_ok=True,
            orientation="portrait",
        ),
    )

    def _boom(key, data):
        raise RuntimeError("simulated R2 outage")

    monkeypatch.setattr(crop_task.storage, "upload_bytes", _boom)

    with pytest.raises(RuntimeError, match="simulated R2 outage"):
        crop_task._crop_scan(raw_scan_id)

    # A fresh session/query -- not the one the task used -- confirms the
    # card_crop row it flushed before failing was actually rolled back.
    verify_db = TestSessionLocal()
    try:
        assert verify_db.query(CardCrop).count() == 0
        # The raw_scan's status update never got a chance to commit either,
        # since it's set *after* the upload in this task -- still "pending".
        refetched = verify_db.get(RawScan, raw_scan_id)
        assert refetched.status == ScanStatus.pending
    finally:
        verify_db.close()
