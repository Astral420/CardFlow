from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import storage
from app.api.common import card_pair, crop_item, finite_float_or_none, find_sibling_crop
from app.api.deps import get_current_user_optional
from app.db import get_db
from app.models import CardCrop, DuplicateCandidate, RawScan, ScanSide, ScanStatus
from app.schemas import CardCropDetailOut, CardCropOut, DuplicateCandidateOut

router = APIRouter(prefix="/api/cards", tags=["card-log"])


@router.get("", response_model=list[CardCropOut])
def list_cards(
    batch_id: int | None = Query(default=None),
    status_filter: ScanStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> list[CardCropOut]:
    query = db.query(CardCrop).join(RawScan)
    if batch_id is not None:
        query = query.filter(RawScan.batch_id == batch_id)
    if status_filter is not None:
        query = query.filter(RawScan.status == status_filter)
    if search:
        query = query.filter(RawScan.original_filename.ilike(f"%{search}%"))

    crops = query.order_by(CardCrop.id.desc()).offset(offset).limit(limit).all()

    return [
        CardCropOut(
            id=crop.id,
            original_filename=crop.raw_scan.original_filename,
            side=crop.raw_scan.side,
            status=crop.raw_scan.status,
            batch_id=crop.raw_scan.batch_id,
            image_url=storage.presigned_url(crop.r2_key_cropped)
            if crop.r2_key_cropped
            else None,
            aspect_ratio_ok=crop.aspect_ratio_ok,
            rotation_confirmed_at=crop.rotation_confirmed_at,
        )
        for crop in crops
    ]


@router.get("/{crop_id}", response_model=CardCropDetailOut)
def get_card(
    crop_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user_optional)
) -> CardCropDetailOut:
    crop = db.get(CardCrop, crop_id)
    if crop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Card crop not found")

    raw_scan = crop.raw_scan
    sibling = find_sibling_crop(db, crop)
    front = crop if raw_scan.side == ScanSide.front else sibling
    back = crop if raw_scan.side == ScanSide.back else sibling

    duplicates = (
        db.query(DuplicateCandidate)
        .filter(
            (DuplicateCandidate.card_crop_id_a == crop_id)
            | (DuplicateCandidate.card_crop_id_b == crop_id)
        )
        .all()
    )

    return CardCropDetailOut(
        id=crop.id,
        original_filename=raw_scan.original_filename,
        side=raw_scan.side,
        status=raw_scan.status,
        batch_id=raw_scan.batch_id,
        image_url=storage.presigned_url(crop.r2_key_cropped)
        if crop.r2_key_cropped
        else None,
        aspect_ratio_ok=crop.aspect_ratio_ok,
        rotation_confirmed_at=crop.rotation_confirmed_at,
        front_image_url=storage.presigned_url(front.r2_key_cropped)
        if front and front.r2_key_cropped
        else None,
        back_image_url=storage.presigned_url(back.r2_key_cropped)
        if back and back.r2_key_cropped
        else None,
        hash_0=crop.hash_0,
        hash_90=crop.hash_90,
        hash_180=crop.hash_180,
        hash_270=crop.hash_270,
        duplicate_history=[
            DuplicateCandidateOut(
                candidate_id=d.id,
                batch_id=d.card_crop_a.raw_scan.batch_id,
                source_label=d.card_crop_a.raw_scan.batch.source_label,
                status=d.status,
                structural_score=finite_float_or_none(d.structural_score),
                color_score=finite_float_or_none(d.color_score),
                filename_match=d.filename_match,
                crop_a=crop_item(d.card_crop_a),
                crop_b=crop_item(d.card_crop_b),
                card_a=card_pair(db, d.card_crop_a),
                card_b=card_pair(db, d.card_crop_b),
            )
            for d in duplicates
        ],
    )
