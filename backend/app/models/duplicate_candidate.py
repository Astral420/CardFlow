import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.card_crop import CardCrop
    from app.models.user import User


class DuplicateStatus(str, enum.Enum):
    pending = "pending"
    confirmed_duplicate = "confirmed_duplicate"
    # Same physical card legitimately scanned more than once (e.g. multiple
    # copies in inventory) -- acknowledged as a match, but unlike
    # confirmed_duplicate neither side is excluded from the batch export.
    intentional_duplicate = "intentional_duplicate"
    rejected = "rejected"


class DuplicateCandidate(Base):
    __tablename__ = "duplicate_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Indexed: record_duplicate_candidates() looks up an existing row by
    # this pair before inserting, and cards.py filters by either side of it.
    card_crop_id_a: Mapped[int] = mapped_column(
        ForeignKey("card_crops.id", ondelete="CASCADE"), nullable=False, index=True
    )
    card_crop_id_b: Mapped[int] = mapped_column(
        ForeignKey("card_crops.id", ondelete="CASCADE"), nullable=False, index=True
    )
    structural_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    color_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    filename_match: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Indexed: batch counts and the duplicate-review queue both filter on
    # status across every candidate row.
    status: Mapped[DuplicateStatus] = mapped_column(
        Enum(DuplicateStatus, name="duplicate_status"),
        default=DuplicateStatus.pending,
        nullable=False,
        index=True,
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    card_crop_a: Mapped["CardCrop"] = relationship(foreign_keys=[card_crop_id_a])
    card_crop_b: Mapped["CardCrop"] = relationship(foreign_keys=[card_crop_id_b])
    reviewer: Mapped["User | None"] = relationship()
