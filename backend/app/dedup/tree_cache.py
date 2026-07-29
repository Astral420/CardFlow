"""Process-local BK-tree cache for cross-batch duplicate lookups.

``find_cross_batch_duplicates`` used to load every hashed CardCrop from
every other batch and build a brand-new BKTree from scratch on every single
call. With N historical cards that's an O(N) query plus O(N) tree
insertions *per new card processed* -- exactly the cost the BK-tree was
supposed to avoid (spec Section 6.4 calls for a persistent index).

This module keeps one BK-tree per worker process. It's built once, lazily,
on first use, and then kept up to date with a cheap incremental "catch up"
query (``WHERE id > <high watermark>``) instead of a full rebuild:

- First call on a process: full scan of hashed crops, one-time cost.
- Every later call: only crops hashed since this process last checked are
  fetched and added -- typically zero or a handful of rows, not the whole
  history.

Trade-offs, accepted as reasonable at this app's scale:
- With a multi-process (prefork) Celery worker pool, each process holds its
  own copy of the tree. That's fine here -- each process still only pays
  the incremental catch-up cost, it just does so independently.
- If a worker process restarts, its tree resets and rebuilds from the
  database on its next call -- a one-time cost per restart, not per crop.
- Cards are never hard-deleted through the app today, so a deleted row
  silently lingering in an already-built tree isn't a live concern; worth
  revisiting if hard deletes are added later.
"""

import threading

from sqlalchemy.orm import Session

from app.dedup.bktree import BKTree
from app.models import CardCrop
from app.vision.hashing import ROTATIONS, hash_distance

_lock = threading.Lock()
_tree: BKTree[int] | None = None
_max_indexed_id = 0


def _hash_columns(crop: CardCrop) -> dict[int, str | None]:
    return {0: crop.hash_0, 90: crop.hash_90, 180: crop.hash_180, 270: crop.hash_270}


def _index_crop(tree: BKTree[int], crop: CardCrop) -> None:
    hashes = _hash_columns(crop)
    for rotation in ROTATIONS:
        hash_value = hashes[rotation]
        if hash_value is not None:
            tree.add(hash_value, crop.id)


def get_tree(db: Session) -> BKTree[int]:
    """Return this process's cached tree, building or catching it up first."""
    global _tree, _max_indexed_id
    with _lock:
        if _tree is None:
            _tree = BKTree(hash_distance)
            _max_indexed_id = 0

        new_crops = (
            db.query(CardCrop)
            .filter(CardCrop.hash_0.isnot(None), CardCrop.id > _max_indexed_id)
            .order_by(CardCrop.id)
            .all()
        )
        for crop in new_crops:
            _index_crop(_tree, crop)
            _max_indexed_id = max(_max_indexed_id, crop.id)

        return _tree


def reset() -> None:
    """Test hook: drop the cached tree so the next get_tree() rebuilds it."""
    global _tree, _max_indexed_id
    with _lock:
        _tree = None
        _max_indexed_id = 0
