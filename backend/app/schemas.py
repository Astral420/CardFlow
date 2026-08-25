from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import BatchStatus, DuplicateStatus, ScanSide, ScanStatus, UserRole


class LoginRequest(BaseModel):
    name: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    role: UserRole
    created_at: datetime


class UserCreateRequest(BaseModel):
    name: str
    password: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Display name is required")
        return stripped

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    source_label: str | None
    status: BatchStatus


class BatchCreateResponse(BaseModel):
    batch_id: int


class BatchCountsOut(BaseModel):
    scans: int
    cropped: int
    skipped: int
    crop_failed: int
    pending_rotation: int
    pending_duplicate_review: int
    total_duplicate_candidates: int = 0


class BatchDetailOut(BatchOut):
    counts: BatchCountsOut


class RawScanOut(BaseModel):
    id: int
    original_filename: str
    side: ScanSide
    status: ScanStatus
    thumbnail_url: str | None = None
    raw_image_url: str | None = None
    crop_failure_reason: Literal["crop_error", "bad_aspect_ratio"] | None = None
    # Present whenever a CardCrop row exists, including aspect-ratio failures.
    crop_id: int | None = None
    rotation_confirmed_at: datetime | None = None
    rotation_degrees: int = 0
    # True for either confirmed_duplicate or intentional_duplicate --
    # "this scan matched another card in the batch". See
    # is_intentional_duplicate to tell the two apart.
    is_duplicate: bool = False
    # True only for intentional_duplicate: acknowledged as a match but NOT
    # excluded from the batch export (unlike confirmed_duplicate).
    is_intentional_duplicate: bool = False


class CropQueueItemOut(BaseModel):
    crop_id: int
    original_filename: str
    side: ScanSide
    image_url: str
    rotation_degrees: int
    rotation_confirmed_at: datetime | None


class RotationNextOut(BaseModel):
    batch_id: int
    original_filename: str
    front: CropQueueItemOut | None
    back: CropQueueItemOut | None


class RotateRequest(BaseModel):
    degrees: int

    @field_validator("degrees")
    @classmethod
    def validate_degrees(cls, value: int) -> int:
        normalized = value % 360
        if normalized not in {90, 180, 270}:
            raise ValueError("Rotation must be 90, 180, 270, or -90 degrees")
        return normalized


class BulkRerotationRequest(BaseModel):
    crop_ids: list[int] = Field(min_length=1)


class RerotationResultOut(BaseModel):
    requeued_count: int
    batch_id: int
    batch_status: BatchStatus


class QueueCountOut(BaseModel):
    count: int


class CardPairOut(BaseModel):
    pairing_key: str
    front: CropQueueItemOut | None
    back: CropQueueItemOut | None


class DuplicateCandidateOut(BaseModel):
    candidate_id: int
    # Both crops in a pair always belong to the same batch (duplicate
    # detection only ever compares within-batch, see
    # app.dedup.matching.find_within_batch_duplicates), so a single
    # batch_id/source_label pair describes the whole candidate -- lets the
    # duplicate review queue (intentionally global, not batch-scoped -- see
    # app.api.duplicates._next_pending) show which batch is being reviewed.
    batch_id: int
    source_label: str | None
    status: DuplicateStatus
    structural_score: float | None
    color_score: float | None
    filename_match: bool
    crop_a: CropQueueItemOut
    crop_b: CropQueueItemOut
    card_a: CardPairOut
    card_b: CardPairOut


class DuplicateDecisionRequest(BaseModel):
    status: DuplicateStatus


class CardCropOut(BaseModel):
    id: int
    original_filename: str
    side: ScanSide
    status: ScanStatus
    batch_id: int
    image_url: str | None
    aspect_ratio_ok: bool | None
    rotation_confirmed_at: datetime | None


class CardCropDetailOut(CardCropOut):
    front_image_url: str | None
    back_image_url: str | None
    hash_0: str | None
    hash_90: str | None
    hash_180: str | None
    hash_270: str | None
    duplicate_history: list[DuplicateCandidateOut]


class BatchDuplicateCropOut(BaseModel):
    """Lightweight crop info for the batch duplicates log."""
    crop_id: int
    original_filename: str
    side: ScanSide
    image_url: str | None
    rotation_degrees: int


class BatchDuplicatePairOut(BaseModel):
    """A resolved (confirmed or intentional) duplicate pair surfaced in the
    batch duplicates log."""
    candidate_id: int
    status: DuplicateStatus  # confirmed_duplicate or intentional_duplicate
    structural_score: float | None
    color_score: float | None
    filename_match: bool
    kept: BatchDuplicateCropOut
    # card_crop_b. Named "removed" from the confirmed_duplicate era, kept
    # for frontend compatibility -- for status=intentional_duplicate this
    # side is NOT actually excluded from export, see
    # app.api.batches.export_batch_zip.
    removed: BatchDuplicateCropOut
