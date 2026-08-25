"""Regression coverage for rotation-review queue bugs:

1. `confirm()` was narrowing the "next pending" lookup to the just-
   confirmed crop's own batch, so the queue reported empty as soon as one
   batch finished even if other batches still had pending rotation
   reviews. `_next_pending` must still support returning the *global*
   next item, matching what the review page actually polls.
2. The "Skip" action had no way to move past the current pending pair
   without confirming it -- it would just refetch and get the exact same
   pair back. `_next_pending` needs an `after_id` cursor so skip can
   advance past a specific id.
3. The UI reviews a front/back pair, but `confirm()` used to confirm only
   the crop ID sent by the frontend. The still-pending sibling could appear
   later as the queue advanced and reconstruct the same card with one side
   already marked confirmed.

These exercise the query logic directly against an in-memory sqlite DB
rather than going through the FastAPI/auth layers, matching the style of
this project's other pure-logic unit tests.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.rotation import _next_pending, confirm
from app.db import Base
from app.models import Batch, BatchStatus, CardCrop, RawScan, ScanSide, ScanStatus


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _add_pending_crop(db, batch_id: int, stem: str, side: ScanSide) -> CardCrop:
    raw_scan = RawScan(
        batch_id=batch_id,
        r2_key_raw=f"raw/{batch_id}/{stem}-{side.value}.jpg",
        original_filename=f"{stem}-{side.value}.jpg",
        side=side,
        status=ScanStatus.cropped,
    )
    db.add(raw_scan)
    db.flush()

    crop = CardCrop(raw_scan_id=raw_scan.id, aspect_ratio_ok=True)
    db.add(crop)
    db.flush()
    return crop


def test_next_pending_global_sees_other_batches_after_one_finishes():
    db = _make_session()
    batch_a = Batch(status=BatchStatus.rotation_review)
    batch_b = Batch(status=BatchStatus.rotation_review)
    db.add_all([batch_a, batch_b])
    db.flush()

    # Batch A has one pending card (front+back), already confirmed here to
    # simulate "the user just finished reviewing batch A".
    a_front = _add_pending_crop(db, batch_a.id, "card-a1", ScanSide.front)
    a_back = _add_pending_crop(db, batch_a.id, "card-a1", ScanSide.back)
    from datetime import datetime, timezone

    a_front.rotation_confirmed_at = datetime.now(timezone.utc)
    a_back.rotation_confirmed_at = datetime.now(timezone.utc)

    # Batch B still has a pending card.
    _add_pending_crop(db, batch_b.id, "card-b1", ScanSide.front)
    _add_pending_crop(db, batch_b.id, "card-b1", ScanSide.back)
    db.commit()

    # Scoping to batch A (the bug) finds nothing left -> queue looks empty.
    assert _next_pending(db, batch_a.id) is None

    # The global lookup (the fix) still finds batch B's pending card.
    result = _next_pending(db, None)
    assert result is not None
    assert result.batch_id == batch_b.id


def test_next_pending_after_id_skips_past_current_pair():
    db = _make_session()
    batch = Batch(status=BatchStatus.rotation_review)
    db.add(batch)
    db.flush()

    front1 = _add_pending_crop(db, batch.id, "card-1", ScanSide.front)
    back1 = _add_pending_crop(db, batch.id, "card-1", ScanSide.back)
    _add_pending_crop(db, batch.id, "card-2", ScanSide.front)
    _add_pending_crop(db, batch.id, "card-2", ScanSide.back)
    db.commit()

    # Without a cursor, repeatedly calling next just returns the same head
    # of the queue every time (the old "Skip" behavior).
    first_call = _next_pending(db, None)
    second_call = _next_pending(db, None)
    assert first_call.original_filename == second_call.original_filename == "card-1"

    # With after_id set past the current pair, skip actually advances.
    anchor = max(front1.id, back1.id)
    skipped = _next_pending(db, None, after_id=anchor)
    assert skipped is not None
    assert skipped.original_filename == "card-2"


def test_confirm_endpoint_returns_next_pending_from_other_batch():
    """End-to-end regression test for the actual bug: confirming the last
    pending card in one batch must still surface pending work waiting in a
    different batch, not report the queue as empty.
    """
    db = _make_session()
    batch_a = Batch(status=BatchStatus.rotation_review)
    batch_b = Batch(status=BatchStatus.rotation_review)
    db.add_all([batch_a, batch_b])
    db.flush()

    # Batch A: a single pending side left to confirm.
    a_front = _add_pending_crop(db, batch_a.id, "card-a1", ScanSide.front)

    # Batch B: still has pending work.
    _add_pending_crop(db, batch_b.id, "card-b1", ScanSide.front)
    db.commit()

    result = confirm(a_front.id, db=db, _user=None)

    assert result is not None, (
        "confirm() reported the queue empty even though batch B still has "
        "a pending rotation review"
    )
    assert result.batch_id == batch_b.id


def test_confirm_resolves_whole_pair_and_does_not_return_it_again(monkeypatch):
    """One pair-level UI confirmation must confirm both underlying crops.

    Crops are deliberately inserted front-A, front-B, back-A, back-B to
    mirror asynchronous crop workers assigning non-adjacent IDs. With the
    old side-level confirmation, card A's pending back would return later
    with its front already marked confirmed.
    """
    db = _make_session()
    batch = Batch(status=BatchStatus.rotation_review)
    db.add(batch)
    db.flush()

    a_front = _add_pending_crop(db, batch.id, "card-a", ScanSide.front)
    _add_pending_crop(db, batch.id, "card-b", ScanSide.front)
    a_back = _add_pending_crop(db, batch.id, "card-a", ScanSide.back)
    _add_pending_crop(db, batch.id, "card-b", ScanSide.back)
    db.commit()

    enqueued_crop_ids = []
    monkeypatch.setattr(
        "app.api.rotation.enqueue_task",
        lambda _task, crop_id: enqueued_crop_ids.append(crop_id),
    )

    result = confirm(a_front.id, db=db, _user=None)

    db.refresh(a_front)
    db.refresh(a_back)
    assert a_front.rotation_confirmed_at is not None
    assert a_back.rotation_confirmed_at == a_front.rotation_confirmed_at
    assert result is not None
    assert result.original_filename == "card-b"
    assert enqueued_crop_ids == [a_front.id]

    # A repeated request is idempotent and does not dispatch hashing again.
    confirm(a_front.id, db=db, _user=None)
    assert enqueued_crop_ids == [a_front.id]


def test_confirm_by_back_id_still_hashes_newly_confirmed_front(monkeypatch):
    db = _make_session()
    batch = Batch(status=BatchStatus.rotation_review)
    db.add(batch)
    db.flush()

    front = _add_pending_crop(db, batch.id, "card-1", ScanSide.front)
    back = _add_pending_crop(db, batch.id, "card-1", ScanSide.back)
    db.commit()

    enqueued_crop_ids = []
    monkeypatch.setattr(
        "app.api.rotation.enqueue_task",
        lambda _task, crop_id: enqueued_crop_ids.append(crop_id),
    )

    assert confirm(back.id, db=db, _user=None) is None
    assert front.rotation_confirmed_at is not None
    assert back.rotation_confirmed_at == front.rotation_confirmed_at
    assert enqueued_crop_ids == [front.id]


def test_next_pending_returns_none_when_queue_truly_empty():
    db = _make_session()
    batch = Batch(status=BatchStatus.rotation_review)
    db.add(batch)
    db.flush()
    db.commit()

    assert _next_pending(db, None) is None
    assert _next_pending(db, batch.id) is None
