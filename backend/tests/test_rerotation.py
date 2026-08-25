from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.batches import export_batch_zip
from app.api.rotation import (
    _next_pending,
    bulk_rerotation,
    confirm,
    request_rerotation,
    rotate,
)
from app.batch_status import refresh_batch_status
from app.db import Base
from app.models import (
    Batch,
    BatchExport,
    BatchStatus,
    CardCrop,
    DuplicateCandidate,
    DuplicateStatus,
    RawScan,
    ScanSide,
    ScanStatus,
)
from app.schemas import BulkRerotationRequest, RotateRequest


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _add_confirmed_pair(db, batch_id: int, stem: str):
    crops = {}
    for side in (ScanSide.front, ScanSide.back):
        scan = RawScan(
            batch_id=batch_id,
            r2_key_raw=f"raw/{batch_id}/{stem}-{side.value}.jpg",
            original_filename=f"{stem}-{side.value}.jpg",
            side=side,
            status=ScanStatus.cropped,
        )
        db.add(scan)
        db.flush()
        crop = CardCrop(
            raw_scan_id=scan.id,
            r2_key_cropped=f"cropped/{batch_id}/{stem}-{side.value}.jpg",
            aspect_ratio_ok=True,
            rotation_confirmed_at=datetime.now(timezone.utc),
            dedup_completed_at=datetime.now(timezone.utc),
            hash_0="0" * 16,
            hash_90="1" * 16,
            hash_180="2" * 16,
            hash_270="3" * 16,
            color_sig_0=[0.0],
            color_sig_90=[1.0],
            color_sig_180=[2.0],
            color_sig_270=[3.0],
        )
        db.add(crop)
        db.flush()
        crops[side] = crop
    return crops[ScanSide.front], crops[ScanSide.back]


def _assert_reset(crop: CardCrop):
    assert crop.rotation_confirmed_at is None
    assert crop.dedup_completed_at is None
    assert crop.hash_0 is None
    assert crop.hash_90 is None
    assert crop.hash_180 is None
    assert crop.hash_270 is None
    assert crop.color_sig_0 is None
    assert crop.color_sig_90 is None
    assert crop.color_sig_180 is None
    assert crop.color_sig_270 is None


def test_request_rerotation_resets_pair_candidates_cache_and_completed_batch(
    monkeypatch,
):
    db = _make_session()
    batch = Batch(status=BatchStatus.complete)
    db.add(batch)
    db.flush()
    front, back = _add_confirmed_pair(db, batch.id, "card-1")
    other_front, _ = _add_confirmed_pair(db, batch.id, "card-2")
    candidate = DuplicateCandidate(
        card_crop_id_a=min(front.id, other_front.id),
        card_crop_id_b=max(front.id, other_front.id),
        structural_score=0.0,
        color_score=0.0,
        filename_match=False,
        status=DuplicateStatus.pending,
    )
    db.add(candidate)
    cached_export = BatchExport(
        batch_id=batch.id,
        manifest_hash="a" * 64,
        r2_key=f"exports/{batch.id}/{'a' * 64}.zip",
        file_size_bytes=123,
        image_count=4,
        checksum="b" * 16,
    )
    db.add(cached_export)
    db.commit()
    candidate_id = candidate.id
    cached_export_id = cached_export.id
    cached_export_key = cached_export.r2_key
    deleted_keys = []
    monkeypatch.setattr(
        "app.api.rotation.storage.delete_object", deleted_keys.append
    )
    monkeypatch.setattr(
        "app.api.common.storage.presigned_url", lambda key: f"https://test/{key}"
    )

    result = request_rerotation(back.id, db=db, _user=None)

    db.refresh(front)
    db.refresh(back)
    db.refresh(batch)
    _assert_reset(front)
    _assert_reset(back)
    assert db.get(DuplicateCandidate, candidate_id) is None
    assert db.get(BatchExport, cached_export_id) is None
    assert deleted_keys == [cached_export_key]
    assert result.requeued_count == 1
    assert result.batch_id == batch.id
    assert result.batch_status == BatchStatus.rotation_review
    assert batch.status == BatchStatus.rotation_review
    queued = _next_pending(db, batch.id)
    assert queued is not None
    assert queued.front is not None and queued.front.crop_id == front.id
    assert queued.back is not None and queued.back.crop_id == back.id


def test_rerotation_succeeds_when_stale_r2_cleanup_fails(monkeypatch):
    db = _make_session()
    batch = Batch(status=BatchStatus.complete)
    db.add(batch)
    db.flush()
    front, _ = _add_confirmed_pair(db, batch.id, "card-1")
    cached_export = BatchExport(
        batch_id=batch.id,
        manifest_hash="c" * 64,
        r2_key=f"exports/{batch.id}/{'c' * 64}.zip",
        file_size_bytes=123,
        image_count=2,
        checksum="d" * 16,
    )
    db.add(cached_export)
    db.commit()

    def fail_delete(_key):
        raise RuntimeError("simulated cleanup outage")

    monkeypatch.setattr("app.api.rotation.storage.delete_object", fail_delete)

    result = request_rerotation(front.id, db=db, _user=None)

    assert result.batch_status == BatchStatus.rotation_review
    assert db.query(BatchExport).filter_by(batch_id=batch.id).count() == 0


def test_rerotation_does_not_delete_r2_cache_before_database_commit(monkeypatch):
    db = _make_session()
    batch = Batch(status=BatchStatus.complete)
    db.add(batch)
    db.flush()
    front, _ = _add_confirmed_pair(db, batch.id, "card-1")
    cached_export = BatchExport(
        batch_id=batch.id,
        manifest_hash="e" * 64,
        r2_key=f"exports/{batch.id}/{'e' * 64}.zip",
        file_size_bytes=123,
        image_count=2,
        checksum="f" * 16,
    )
    db.add(cached_export)
    db.commit()

    monkeypatch.setattr(
        db, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed"))
    )
    deleted_keys = []
    monkeypatch.setattr("app.api.rotation.storage.delete_object", deleted_keys.append)

    with pytest.raises(RuntimeError, match="commit failed"):
        request_rerotation(front.id, db=db, _user=None)

    assert deleted_keys == []
    db.rollback()
    assert db.query(BatchExport).filter_by(batch_id=batch.id).count() == 1


def test_export_rerotation_reprocessing_and_regenerated_export(monkeypatch):
    db = _make_session()
    batch = Batch(status=BatchStatus.complete, source_label="rerotated")
    db.add(batch)
    db.flush()
    front, back = _add_confirmed_pair(db, batch.id, "card-1")
    db.commit()

    source_bytes = b"\xff\xd8source-image\xff\xd9"
    objects = {
        front.r2_key_cropped: source_bytes,
        back.r2_key_cropped: source_bytes,
    }

    def download(key):
        if key not in objects:
            raise FileNotFoundError(key)
        return objects[key]

    def upload(key, data, content_type="image/jpeg"):
        objects[key] = data

    monkeypatch.setattr("app.storage.download_bytes", download)
    monkeypatch.setattr("app.storage.upload_bytes", upload)
    monkeypatch.setattr("app.storage.delete_object", lambda key: objects.pop(key, None))
    monkeypatch.setattr(
        "app.api.common.storage.presigned_url", lambda key: f"https://test/{key}"
    )
    monkeypatch.setattr("app.api.rotation.enqueue_task", lambda *_args: True)

    first_export = export_batch_zip(batch.id, db=db, _user=None)
    assert first_export.headers["X-Export-Cached"] == "false"
    first_cache = db.query(BatchExport).filter_by(batch_id=batch.id).one()
    first_manifest = first_cache.manifest_hash
    first_export_key = first_cache.r2_key
    assert first_export_key in objects

    request_rerotation(front.id, db=db, _user=None)
    assert db.query(BatchExport).filter_by(batch_id=batch.id).count() == 0
    assert first_export_key not in objects

    with pytest.raises(HTTPException) as pending_rotation:
        export_batch_zip(batch.id, db=db, _user=None)
    assert pending_rotation.value.status_code == 409

    rotate(front.id, RotateRequest(degrees=90), db=db, _user=None)
    confirm(front.id, db=db, _user=None)

    # Confirmation alone is no longer enough to make the batch exportable.
    db.refresh(batch)
    assert batch.status == BatchStatus.rotation_review
    with pytest.raises(HTTPException) as pending_dedup:
        export_batch_zip(batch.id, db=db, _user=None)
    assert pending_dedup.value.status_code == 409

    front.hash_0 = "f" * 16
    front.color_sig_0 = [0.0]
    front.dedup_completed_at = datetime.now(timezone.utc)
    refresh_batch_status(db, batch.id)
    db.commit()

    regenerated = export_batch_zip(batch.id, db=db, _user=None)
    replacement = db.query(BatchExport).filter_by(batch_id=batch.id).one()
    assert regenerated.headers["X-Export-Cached"] == "false"
    assert replacement.manifest_hash != first_manifest
    assert replacement.r2_key != first_export_key
    assert replacement.r2_key in objects


def test_bulk_rerotation_deduplicates_selected_siblings():
    db = _make_session()
    batch = Batch(status=BatchStatus.complete)
    db.add(batch)
    db.flush()
    first_front, first_back = _add_confirmed_pair(db, batch.id, "card-1")
    second_front, second_back = _add_confirmed_pair(db, batch.id, "card-2")
    db.commit()

    result = bulk_rerotation(
        BulkRerotationRequest(
            crop_ids=[first_front.id, first_back.id, second_front.id]
        ),
        db=db,
        _user=None,
    )

    for crop in (first_front, first_back, second_front, second_back):
        db.refresh(crop)
        _assert_reset(crop)
    assert result.requeued_count == 2
    assert result.batch_status == BatchStatus.rotation_review


def test_bulk_rerotation_rejects_crops_from_multiple_batches_before_mutating():
    db = _make_session()
    first_batch = Batch(status=BatchStatus.complete)
    second_batch = Batch(status=BatchStatus.complete)
    db.add_all([first_batch, second_batch])
    db.flush()
    first_front, _ = _add_confirmed_pair(db, first_batch.id, "card-1")
    second_front, _ = _add_confirmed_pair(db, second_batch.id, "card-2")
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        bulk_rerotation(
            BulkRerotationRequest(crop_ids=[first_front.id, second_front.id]),
            db=db,
            _user=None,
        )

    assert exc_info.value.status_code == 400
    assert first_front.rotation_confirmed_at is not None
    assert second_front.rotation_confirmed_at is not None
