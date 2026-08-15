"""Regression and unit tests for batch hard-delete (DELETE /api/batches/{id}):

1. Successful hard-delete removes Batch, RawScans, CardCrops, DuplicateCandidates
   from the database, writes a durable BatchAuditLog row, and cleans up R2 objects.
2. Storage safety (Step 3): If a database error occurs during the deletion
   transaction commit, storage.delete_object is NEVER invoked, ensuring R2 images
   are never orphaned or deleted prematurely.
3. R2 partial failures are recorded non-fatally in the BatchAuditLog notes and counts.
4. Cross-batch duplicate candidates are cleanly cascade-deleted when one batch is
   removed, while the sibling crop in the surviving batch remains intact.
5. Deleting a non-existent batch raises 404.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.api.batches import delete_batch
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


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_admin(db) -> User:
    admin = User(name="admin_user", role=UserRole.admin)
    db.add(admin)
    db.commit()
    return admin


def _seed_batch_with_crop(db, label: str = "batch-1") -> tuple[Batch, RawScan, CardCrop]:
    batch = Batch(source_label=label, status=BatchStatus.duplicate_review)
    db.add(batch)
    db.flush()

    raw_scan = RawScan(
        batch_id=batch.id,
        r2_key_raw=f"raw/{batch.id}/card-1-front.jpg",
        original_filename="card-1-front.jpg",
        side=ScanSide.front,
        status=ScanStatus.cropped,
    )
    db.add(raw_scan)
    db.flush()

    crop = CardCrop(
        raw_scan_id=raw_scan.id,
        r2_key_cropped=f"crops/{batch.id}/crop-1.jpg",
    )
    db.add(crop)
    db.commit()
    return batch, raw_scan, crop


def test_delete_batch_success():
    db = _make_session()
    admin = _seed_admin(db)
    batch, scan, crop = _seed_batch_with_crop(db, "test-box-1")

    with patch("app.api.batches.storage") as mock_storage, \
         patch("app.api.batches.redis_state") as mock_redis, \
         patch("app.api.batches.log_event") as mock_log:

        mock_storage.temp_upload_key.return_value = f"temp_uploads/{batch.id}.zip"

        delete_batch(batch_id=batch.id, db=db, current_user=admin)

        # 1. Batch & child rows deleted from DB
        assert db.get(Batch, batch.id) is None
        assert db.get(RawScan, scan.id) is None
        assert db.get(CardCrop, crop.id) is None

        # 2. Audit log recorded
        audit = db.query(BatchAuditLog).filter_by(batch_id=batch.id).first()
        assert audit is not None
        assert audit.performed_by == admin.id
        assert audit.action == "hard_delete"
        assert audit.source_label == "test-box-1"
        assert audit.scan_count == 1
        assert audit.r2_keys_deleted == 3  # temp zip, raw scan, crop
        assert audit.r2_keys_failed == 0
        assert audit.notes is None

        # 3. Storage objects deleted
        expected_keys = [
            f"temp_uploads/{batch.id}.zip",
            f"raw/{batch.id}/card-1-front.jpg",
            f"crops/{batch.id}/crop-1.jpg",
        ]
        assert mock_storage.delete_object.call_count == 3
        for k in expected_keys:
            mock_storage.delete_object.assert_any_call(k)

        # 4. Redis feed pushed
        mock_redis.push_recent.assert_called_once()
        mock_log.assert_called_once()


def test_delete_batch_db_error_protects_storage():
    """If the DB commit fails during batch deletion, storage.delete_object
    must NOT be called, preventing orphaned storage deletions."""
    db = _make_session()
    admin = _seed_admin(db)
    batch, scan, crop = _seed_batch_with_crop(db)

    with patch("app.api.batches.storage") as mock_storage:
        mock_storage.temp_upload_key.return_value = f"temp_uploads/{batch.id}.zip"

        # Simulate a database failure on the initial commit
        original_commit = db.commit
        call_count = 0

        def failing_commit():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Simulated database failure during batch delete commit")
            return original_commit()

        db.commit = failing_commit

        with pytest.raises(RuntimeError, match="Simulated database failure"):
            delete_batch(batch_id=batch.id, db=db, current_user=admin)

        # Storage delete must NOT have been called
        assert mock_storage.delete_object.call_count == 0


def test_delete_batch_handles_r2_partial_failure():
    db = _make_session()
    admin = _seed_admin(db)
    batch, _, _ = _seed_batch_with_crop(db)

    with patch("app.api.batches.storage") as mock_storage, \
         patch("app.api.batches.redis_state"), \
         patch("app.api.batches.log_event"):

        mock_storage.temp_upload_key.return_value = f"temp_uploads/{batch.id}.zip"

        def delete_side_effect(key):
            if "crops/" in key:
                raise IOError("Network timeout talking to R2")

        mock_storage.delete_object.side_effect = delete_side_effect

        delete_batch(batch_id=batch.id, db=db, current_user=admin)

        # DB batch is deleted
        assert db.get(Batch, batch.id) is None

        # Audit log reflects partial failure
        audit = db.query(BatchAuditLog).filter_by(batch_id=batch.id).first()
        assert audit is not None
        assert audit.r2_keys_deleted == 2
        assert audit.r2_keys_failed == 1
        assert "Network timeout talking to R2" in (audit.notes or "")


def test_delete_batch_cascades_cross_batch_duplicate_candidates():
    """When Batch 1 is deleted, duplicate candidate pairs referencing Crop 1
    are removed, but Batch 2 and Crop 2 remain untouched."""
    db = _make_session()
    admin = _seed_admin(db)

    batch_1, _, crop_1 = _seed_batch_with_crop(db, "batch-1")
    batch_2, _, crop_2 = _seed_batch_with_crop(db, "batch-2")

    dup = DuplicateCandidate(
        card_crop_id_a=crop_1.id,
        card_crop_id_b=crop_2.id,
        status=DuplicateStatus.pending,
    )
    db.add(dup)
    db.commit()

    dup_id = dup.id

    with patch("app.api.batches.storage"), \
         patch("app.api.batches.redis_state"), \
         patch("app.api.batches.log_event"):

        delete_batch(batch_id=batch_1.id, db=db, current_user=admin)

    # Batch 1 and Crop 1 are gone
    assert db.get(Batch, batch_1.id) is None
    assert db.get(CardCrop, crop_1.id) is None

    # DuplicateCandidate referencing Crop 1 is cascade-deleted
    assert db.get(DuplicateCandidate, dup_id) is None

    # Batch 2 and Crop 2 are intact
    assert db.get(Batch, batch_2.id) is not None
    assert db.get(CardCrop, crop_2.id) is not None


def test_delete_batch_not_found():
    db = _make_session()
    admin = _seed_admin(db)

    with pytest.raises(HTTPException) as exc_info:
        delete_batch(batch_id=99999, db=db, current_user=admin)
    assert exc_info.value.status_code == 404
