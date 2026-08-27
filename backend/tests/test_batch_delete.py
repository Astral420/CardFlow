"""Regression coverage for durable background batch deletion."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from celery.exceptions import Retry
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.api.batches import delete_batch, export_batch_zip, get_batch, list_batches
from app.api.duplicates import queue_count as duplicate_queue_count
from app.api.rotation import queue_count as rotation_queue_count
from app.batch_status import refresh_batch_status
from app.db import Base
from app.models import (
    Batch,
    BatchAuditLog,
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


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _make_sessionmaker():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_admin(db) -> User:
    admin = User(name="admin_user", role=UserRole.admin)
    db.add(admin)
    db.commit()
    return admin


def _seed_batch_with_crop(db, label: str = "batch-1") -> tuple[Batch, RawScan, CardCrop]:
    batch = Batch(source_label=label, status=BatchStatus.duplicate_review)
    db.add(batch)
    db.flush()
    scan = RawScan(
        batch_id=batch.id,
        r2_key_raw=f"raw/{batch.id}/card-1-front.jpg",
        original_filename="card-1-front.jpg",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    db.add(scan)
    db.flush()
    crop = CardCrop(
        raw_scan_id=scan.id,
        r2_key_cropped=f"cropped/{batch.id}/crop-1-front.jpg",
    )
    db.add(crop)
    db.commit()
    return batch, scan, crop


def _mark_deleting(batch: Batch, admin: User) -> None:
    batch.deletion_previous_status = batch.status.value
    batch.deletion_requested_at = datetime.now(timezone.utc)
    batch.deletion_requested_by = admin.id
    batch.status = BatchStatus.deleting


def test_delete_batch_accepts_and_persists_durable_request():
    Session = _make_sessionmaker()
    db = Session()
    admin = _seed_admin(db)
    batch, _, _ = _seed_batch_with_crop(db)

    with patch("app.api.batches.enqueue_task", return_value=True) as enqueue:
        result = delete_batch(batch_id=batch.id, db=db, current_user=admin)

    assert result == {"status": "deleting", "batch_id": batch.id}
    db.refresh(batch)
    assert batch.status == BatchStatus.deleting
    assert batch.deletion_previous_status == BatchStatus.duplicate_review.value
    assert batch.deletion_requested_at is not None
    assert batch.deletion_requested_by == admin.id
    enqueue.assert_called_once()


def test_delete_batch_conflicts_when_already_deleting():
    Session = _make_sessionmaker()
    db = Session()
    admin = _seed_admin(db)
    batch, _, _ = _seed_batch_with_crop(db)
    _mark_deleting(batch, admin)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        delete_batch(batch_id=batch.id, db=db, current_user=admin)
    assert exc_info.value.status_code == 409


def test_delete_batch_reverts_when_broker_is_unavailable():
    Session = _make_sessionmaker()
    db = Session()
    admin = _seed_admin(db)
    batch, _, _ = _seed_batch_with_crop(db)

    with patch("app.api.batches.enqueue_task", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            delete_batch(batch_id=batch.id, db=db, current_user=admin)

    assert exc_info.value.status_code == 503
    db.refresh(batch)
    assert batch.status == BatchStatus.duplicate_review
    assert batch.deletion_requested_at is None
    assert batch.deletion_previous_status is None
    assert batch.deletion_requested_by is None


def test_delete_batch_not_found():
    Session = _make_sessionmaker()
    db = Session()
    admin = _seed_admin(db)

    with pytest.raises(HTTPException) as exc_info:
        delete_batch(batch_id=99999, db=db, current_user=admin)
    assert exc_info.value.status_code == 404


def test_delete_task_success_cascades_audits_and_cleans_storage(monkeypatch):
    import app.tasks.deletion as deletion_task

    Session = _make_sessionmaker()
    monkeypatch.setattr(deletion_task, "SessionLocal", Session)
    db = Session()
    admin = _seed_admin(db)
    batch, scan, crop = _seed_batch_with_crop(db, "test-box-1")
    batch_id, scan_id, crop_id, admin_id = batch.id, scan.id, crop.id, admin.id
    _mark_deleting(batch, admin)
    db.commit()
    db.close()

    with patch.object(deletion_task.storage, "temp_upload_key", return_value=f"tmp/uploads/{batch_id}.zip"), \
         patch.object(deletion_task.storage, "delete_object") as delete_object, \
         patch.object(deletion_task.redis_state, "push_recent"), \
         patch.object(deletion_task, "log_event"):
        deletion_task._delete_batch(batch_id)

    verify = Session()
    assert verify.get(Batch, batch_id) is None
    assert verify.get(RawScan, scan_id) is None
    assert verify.get(CardCrop, crop_id) is None
    audit = verify.query(BatchAuditLog).filter_by(batch_id=batch_id).one()
    assert audit.performed_by == admin_id
    assert audit.batch_status == BatchStatus.duplicate_review.value
    assert audit.source_label == "test-box-1"
    assert audit.scan_count == 1
    assert audit.r2_keys_deleted == 3
    assert audit.r2_keys_failed == 0
    assert delete_object.call_count == 3


def test_delete_task_records_r2_partial_failure_non_fatally(monkeypatch):
    import app.tasks.deletion as deletion_task

    Session = _make_sessionmaker()
    monkeypatch.setattr(deletion_task, "SessionLocal", Session)
    db = Session()
    admin = _seed_admin(db)
    batch, _, _ = _seed_batch_with_crop(db)
    batch_id = batch.id
    _mark_deleting(batch, admin)
    db.commit()
    db.close()

    def delete_side_effect(key: str) -> None:
        if key.startswith("cropped/"):
            raise OSError("simulated R2 timeout")

    with patch.object(deletion_task.storage, "delete_object", side_effect=delete_side_effect), \
         patch.object(deletion_task.redis_state, "push_recent"), \
         patch.object(deletion_task, "log_event"):
        deletion_task._delete_batch(batch_id)

    verify = Session()
    audit = verify.query(BatchAuditLog).filter_by(batch_id=batch_id).one()
    assert verify.get(Batch, batch_id) is None
    assert audit.r2_keys_deleted == 2
    assert audit.r2_keys_failed == 1
    assert "simulated R2 timeout" in (audit.notes or "")


def test_delete_task_keeps_deleting_during_retry(monkeypatch):
    import app.tasks.deletion as deletion_task

    Session = _make_sessionmaker()
    monkeypatch.setattr(deletion_task, "SessionLocal", Session)
    db = Session()
    admin = _seed_admin(db)
    batch, _, _ = _seed_batch_with_crop(db)
    batch_id = batch.id
    _mark_deleting(batch, admin)
    db.commit()
    db.close()

    with patch.object(deletion_task, "BatchAuditLog", side_effect=RuntimeError("db failure")):
        deletion_task._delete_batch.push_request(
            retries=0,
            called_directly=False,
            is_eager=True,
            args=(batch_id,),
            kwargs={},
        )
        try:
            with pytest.raises(Retry):
                deletion_task._delete_batch.run(batch_id)
        finally:
            deletion_task._delete_batch.pop_request()

    verify = Session()
    assert verify.get(Batch, batch_id).status == BatchStatus.deleting


def test_delete_task_restores_status_after_final_failed_attempt(monkeypatch):
    import app.tasks.deletion as deletion_task

    Session = _make_sessionmaker()
    monkeypatch.setattr(deletion_task, "SessionLocal", Session)
    db = Session()
    admin = _seed_admin(db)
    batch, _, _ = _seed_batch_with_crop(db)
    batch_id = batch.id
    _mark_deleting(batch, admin)
    db.commit()
    db.close()

    with patch.object(deletion_task, "BatchAuditLog", side_effect=RuntimeError("db failure")):
        deletion_task._delete_batch.push_request(retries=2, called_directly=False)
        try:
            with pytest.raises(RuntimeError, match="db failure"):
                deletion_task._delete_batch.run(batch_id)
        finally:
            deletion_task._delete_batch.pop_request()

    verify = Session()
    restored = verify.get(Batch, batch_id)
    assert restored.status == BatchStatus.duplicate_review
    assert restored.deletion_requested_at is None
    assert restored.deletion_previous_status is None
    assert restored.deletion_requested_by is None


def test_deleting_batch_is_hidden_from_list_but_visible_by_id(monkeypatch):
    Session = _make_sessionmaker()
    db = Session()
    admin = _seed_admin(db)
    visible, _, _ = _seed_batch_with_crop(db, "visible")
    deleting, _, _ = _seed_batch_with_crop(db, "hidden")
    _mark_deleting(deleting, admin)
    db.commit()
    monkeypatch.setattr("app.batch_status.redis_state.set_batch_stage", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.batch_status.redis_state.mark_batch_terminal", lambda *args, **kwargs: None)

    listed = list_batches(limit=50, db=db, _user=None)
    assert [item.id for item in listed] == [visible.id]

    detail = get_batch(batch_id=deleting.id, db=db, _user=None)
    assert detail.id == deleting.id
    assert detail.status == BatchStatus.deleting


def test_status_refresh_never_overwrites_deleting():
    Session = _make_sessionmaker()
    db = Session()
    admin = _seed_admin(db)
    batch, _, _ = _seed_batch_with_crop(db)
    _mark_deleting(batch, admin)
    db.commit()

    assert refresh_batch_status(db, batch.id) == BatchStatus.deleting
    assert batch.status == BatchStatus.deleting


def test_deleting_batch_is_removed_from_review_queues():
    Session = _make_sessionmaker()
    db = Session()
    admin = _seed_admin(db)
    batch, _, crop = _seed_batch_with_crop(db)
    duplicate = DuplicateCandidate(
        card_crop_id_a=crop.id,
        card_crop_id_b=crop.id,
        status=DuplicateStatus.pending,
    )
    db.add(duplicate)
    _mark_deleting(batch, admin)
    db.commit()

    assert rotation_queue_count(db=db, _user=None).count == 0
    assert duplicate_queue_count(db=db, _user=None).count == 0


def test_export_rejects_deleting_batch():
    Session = _make_sessionmaker()
    db = Session()
    admin = _seed_admin(db)
    batch, _, _ = _seed_batch_with_crop(db)
    _mark_deleting(batch, admin)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        export_batch_zip(batch_id=batch.id, db=db, _user=admin)
    assert exc_info.value.status_code == 409


def test_crop_worker_does_not_publish_after_deletion_starts(monkeypatch):
    import app.tasks.crop as crop_task
    from app.vision.crop import CropResult

    Session = _make_sessionmaker()
    monkeypatch.setattr(crop_task, "SessionLocal", Session)
    db = Session()
    admin = _seed_admin(db)
    batch = Batch(status=BatchStatus.cropping)
    db.add(batch)
    db.flush()
    scan = RawScan(
        batch_id=batch.id,
        r2_key_raw=f"raw/{batch.id}/card-2-front.jpg",
        original_filename="card-2-front.jpg",
        side=ScanSide.front,
        status=ScanStatus.pending,
    )
    db.add(scan)
    db.commit()
    scan_id = scan.id
    _mark_deleting(batch, admin)
    db.commit()
    db.close()

    monkeypatch.setattr(crop_task.storage, "download_bytes", lambda key: b"raw")
    monkeypatch.setattr(
        crop_task,
        "auto_crop",
        lambda data: CropResult(
            image_bytes=b"crop",
            bbox=[[0, 0], [1, 0], [1, 1], [0, 1]],
            aspect_ratio=1.4,
            aspect_ratio_ok=True,
            orientation="portrait",
        ),
    )
    upload = patch.object(crop_task.storage, "upload_bytes")
    with upload as upload_bytes:
        crop_task._crop_scan(scan_id)

    verify = Session()
    assert verify.query(CardCrop).count() == 0
    upload_bytes.assert_not_called()


def test_delete_cascades_cross_batch_duplicate_candidates(monkeypatch):
    import app.tasks.deletion as deletion_task

    Session = _make_sessionmaker()
    monkeypatch.setattr(deletion_task, "SessionLocal", Session)
    db = Session()
    admin = _seed_admin(db)
    batch_1, _, crop_1 = _seed_batch_with_crop(db, "batch-1")
    batch_2, _, crop_2 = _seed_batch_with_crop(db, "batch-2")
    duplicate = DuplicateCandidate(
        card_crop_id_a=crop_1.id,
        card_crop_id_b=crop_2.id,
        status=DuplicateStatus.pending,
    )
    db.add(duplicate)
    db.commit()
    batch_1_id, batch_2_id = batch_1.id, batch_2.id
    crop_2_id, duplicate_id = crop_2.id, duplicate.id
    _mark_deleting(batch_1, admin)
    db.commit()
    db.close()

    with patch.object(deletion_task.storage, "delete_object"), \
         patch.object(deletion_task.redis_state, "push_recent"), \
         patch.object(deletion_task, "log_event"):
        deletion_task._delete_batch(batch_1_id)

    verify = Session()
    assert verify.get(Batch, batch_1_id) is None
    assert verify.get(DuplicateCandidate, duplicate_id) is None
    assert verify.get(Batch, batch_2_id) is not None
    assert verify.get(CardCrop, crop_2_id) is not None
