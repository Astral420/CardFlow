import math

from sqlalchemy.orm import Session

from app import storage
from app.models import CardCrop, RawScan, ScanSide
from app.naming import pairing_key
from app.schemas import CardPairOut, CropQueueItemOut


def finite_float_or_none(value: float | int | None) -> float | None:
    if value is None:
        return None
    float_value = float(value)
    return float_value if math.isfinite(float_value) else None


def crop_item(crop: CardCrop) -> CropQueueItemOut:
    return CropQueueItemOut(
        crop_id=crop.id,
        original_filename=crop.raw_scan.original_filename,
        side=crop.raw_scan.side,
        image_url=storage.presigned_url(crop.r2_key_cropped)
        if crop.r2_key_cropped
        else "",
        rotation_degrees=crop.rotation_degrees,
        rotation_confirmed_at=crop.rotation_confirmed_at,
    )


def find_sibling_crop(db: Session, crop: CardCrop) -> CardCrop | None:
    raw_scan = crop.raw_scan
    key = pairing_key(raw_scan.original_filename)
    candidates = (
        db.query(CardCrop)
        .join(RawScan)
        .filter(RawScan.batch_id == raw_scan.batch_id, RawScan.id != raw_scan.id)
        .all()
    )
    return next(
        (c for c in candidates if pairing_key(c.raw_scan.original_filename) == key),
        None,
    )


def card_pair(db: Session, crop: CardCrop) -> CardPairOut:
    raw_scan = crop.raw_scan
    sibling = find_sibling_crop(db, crop)

    front = crop if raw_scan.side == ScanSide.front else sibling
    back = crop if raw_scan.side == ScanSide.back else sibling

    return CardPairOut(
        pairing_key=pairing_key(raw_scan.original_filename),
        front=crop_item(front) if front else None,
        back=crop_item(back) if back else None,
    )
