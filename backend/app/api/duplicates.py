from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.common import card_pair, crop_item, finite_float_or_none
from app.api.deps import get_current_user_optional, require_reviewer
from app.batch_status import refresh_batch_status
from app.db import get_db
from app.models import DuplicateCandidate, DuplicateStatus, User
from app.schemas import DuplicateCandidateOut, DuplicateDecisionRequest, QueueCountOut

router = APIRouter(prefix="/api/review/duplicates", tags=["duplicate-review"])


def _to_out(db: Session, candidate: DuplicateCandidate) -> DuplicateCandidateOut:
    batch = candidate.card_crop_a.raw_scan.batch
    return DuplicateCandidateOut(
        candidate_id=candidate.id,
        batch_id=batch.id,
        source_label=batch.source_label,
        status=candidate.status,
        structural_score=finite_float_or_none(candidate.structural_score),
        color_score=finite_float_or_none(candidate.color_score),
        filename_match=candidate.filename_match,
        crop_a=crop_item(candidate.card_crop_a),
        crop_b=crop_item(candidate.card_crop_b),
        card_a=card_pair(db, candidate.card_crop_a),
        card_b=card_pair(db, candidate.card_crop_b),
    )


def _next_pending(db: Session) -> DuplicateCandidateOut | None:
    candidate = (
        db.query(DuplicateCandidate)
        .filter(DuplicateCandidate.status == DuplicateStatus.pending)
        .order_by(DuplicateCandidate.id)
        .first()
    )
    return _to_out(db, candidate) if candidate else None


@router.get("/next", response_model=DuplicateCandidateOut | None)
def next_in_queue(
    db: Session = Depends(get_db), _user=Depends(get_current_user_optional)
) -> DuplicateCandidateOut | None:
    return _next_pending(db)


@router.get("/queue-count", response_model=QueueCountOut)
def queue_count(
    db: Session = Depends(get_db), _user=Depends(get_current_user_optional)
) -> QueueCountOut:
    count = (
        db.query(DuplicateCandidate)
        .filter(DuplicateCandidate.status == DuplicateStatus.pending)
        .count()
    )
    return QueueCountOut(count=count)


@router.post("/{candidate_id}/decision", response_model=DuplicateCandidateOut | None)
def decide(
    candidate_id: int,
    payload: DuplicateDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer),
) -> DuplicateCandidateOut | None:
    candidate = db.get(DuplicateCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")
    if payload.status not in (
        DuplicateStatus.confirmed_duplicate,
        DuplicateStatus.intentional_duplicate,
        DuplicateStatus.rejected,
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid decision status")

    candidate.status = payload.status
    candidate.reviewed_by = current_user.id
    candidate.reviewed_at = datetime.now(timezone.utc)
    batch_id = candidate.card_crop_a.raw_scan.batch_id
    refresh_batch_status(db, batch_id)
    db.commit()

    return _next_pending(db)
