"""Duplicate-candidate matching (spec Section 6.4).

Two signals are both required to flag a candidate: structural hash distance
and color-signature distance. Filename is a tiebreaker recorded on the
candidate row, never a gate. Output is always a *candidate* for human
review, never an automatic merge/discard.
"""

from dataclasses import dataclass
import math

from sqlalchemy.orm import Session

from app.config import settings
from app.dedup import tree_cache
from app.models import CardCrop, DuplicateCandidate, DuplicateStatus, RawScan
from app.naming import pairing_key
from app.vision.hashing import ROTATIONS, color_distance, hash_distance


@dataclass
class DuplicateHit:
    other_crop_id: int
    structural_score: int
    color_score: float
    matched_rotation: int


def _hash_columns(crop: CardCrop) -> dict[int, str | None]:
    return {0: crop.hash_0, 90: crop.hash_90, 180: crop.hash_180, 270: crop.hash_270}


def _color_columns(crop: CardCrop) -> dict[int, list | None]:
    return {
        0: crop.color_sig_0,
        90: crop.color_sig_90,
        180: crop.color_sig_180,
        270: crop.color_sig_270,
    }


def _best_match(
    query_hash: str, query_color: list[float], candidate: CardCrop
) -> DuplicateHit | None:
    hashes = _hash_columns(candidate)
    colors = _color_columns(candidate)

    best: DuplicateHit | None = None
    for rotation in ROTATIONS:
        candidate_hash = hashes[rotation]
        if candidate_hash is None:
            continue
        structural_score = hash_distance(query_hash, candidate_hash)
        if structural_score > settings.structural_hash_max_distance:
            continue

        candidate_color = colors[rotation]
        if candidate_color is None:
            continue
        color_score = color_distance(query_color, candidate_color)
        if not math.isfinite(color_score):
            continue
        if color_score > settings.color_sig_max_distance:
            continue

        if best is None or structural_score < best.structural_score:
            best = DuplicateHit(candidate.id, structural_score, color_score, rotation)
    return best


def find_within_batch_duplicates(
    db: Session, crop: CardCrop, batch_id: int
) -> list[DuplicateHit]:
    """Brute-force pairwise comparison within the same batch (cheap at
    batch scale, per spec)."""
    query_hash, query_color = crop.hash_0, crop.color_sig_0
    if query_hash is None or query_color is None:
        return []

    others = (
        db.query(CardCrop)
        .join(RawScan)
        .filter(
            RawScan.batch_id == batch_id,
            CardCrop.id != crop.id,
            CardCrop.hash_0.isnot(None),
        )
        .all()
    )
    hits = []
    for other in others:
        hit = _best_match(query_hash, query_color, other)
        if hit is not None:
            hits.append(hit)
    return hits


def find_cross_batch_duplicates(
    db: Session, crop: CardCrop, batch_id: int
) -> list[DuplicateHit]:
    """BK-tree shortlist over structural hashes from other batches, then the
    more expensive color check only on that shortlist.

    The tree itself is a process-local cache (see app.dedup.tree_cache) that
    gets incrementally caught up rather than rebuilt from every historical
    crop on every call.
    """
    query_hash, query_color = crop.hash_0, crop.color_sig_0
    if query_hash is None or query_color is None:
        return []

    tree = tree_cache.get_tree(db)
    candidate_ids = {
        other_id
        for other_id, _dist in tree.query(
            query_hash, settings.structural_hash_max_distance
        )
        if other_id != crop.id
    }
    if not candidate_ids:
        return []

    # The tree is global across all batches (that's what makes the
    # incremental catch-up possible); re-apply the "other batches only"
    # filter here against just the shortlist, not the full history.
    candidates = (
        db.query(CardCrop)
        .join(RawScan)
        .filter(CardCrop.id.in_(candidate_ids), RawScan.batch_id != batch_id)
        .all()
    )
    hits = []
    for candidate in candidates:
        hit = _best_match(query_hash, query_color, candidate)
        if hit is not None:
            hits.append(hit)
    return hits


def _filenames_match(crop_a: CardCrop, crop_b: CardCrop) -> bool:
    return pairing_key(crop_a.raw_scan.original_filename) == pairing_key(
        crop_b.raw_scan.original_filename
    )


def record_duplicate_candidates(
    db: Session, crop: CardCrop, hits: list[DuplicateHit]
) -> list[DuplicateCandidate]:
    created = []
    for hit in hits:
        crop_a_id, crop_b_id = sorted((crop.id, hit.other_crop_id))
        existing = (
            db.query(DuplicateCandidate)
            .filter(
                DuplicateCandidate.card_crop_id_a == crop_a_id,
                DuplicateCandidate.card_crop_id_b == crop_b_id,
            )
            .first()
        )
        if existing is not None:
            continue

        other = db.get(CardCrop, hit.other_crop_id)
        candidate = DuplicateCandidate(
            card_crop_id_a=crop_a_id,
            card_crop_id_b=crop_b_id,
            structural_score=float(hit.structural_score),
            color_score=hit.color_score,
            filename_match=_filenames_match(crop, other) if other else False,
            status=DuplicateStatus.pending,
        )
        db.add(candidate)
        created.append(candidate)
    db.flush()
    return created
