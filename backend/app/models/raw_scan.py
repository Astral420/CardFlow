import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, String, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.naming import pairing_key as _compute_pairing_key

if TYPE_CHECKING:
    from app.models.batch import Batch
    from app.models.card_crop import CardCrop


class ScanSide(str, enum.Enum):
    front = "front"
    back = "back"


class ScanStatus(str, enum.Enum):
    pending = "pending"
    cropped = "cropped"
    crop_failed = "crop_failed"


class RawScan(Base):
    __tablename__ = "raw_scans"
    __table_args__ = (
        # Sibling front/back lookups (see app.api.common.find_sibling_crop)
        # filter on exactly these two columns together.
        Index("ix_raw_scans_batch_id_pairing_key", "batch_id", "pairing_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), nullable=False)
    r2_key_raw: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    # Filename with the -front/-back suffix stripped (see app.naming), kept
    # as its own column so a sibling front/back scan can be found with a
    # direct indexed lookup instead of loading every scan in the batch and
    # linear-scanning for a filename match. Computed automatically below —
    # callers never set this directly.
    pairing_key: Mapped[str] = mapped_column(String, nullable=False)
    side: Mapped[ScanSide] = mapped_column(
        Enum(ScanSide, name="scan_side"), nullable=False
    )
    status: Mapped[ScanStatus] = mapped_column(
        Enum(ScanStatus, name="scan_status"),
        default=ScanStatus.pending,
        nullable=False,
    )

    batch: Mapped["Batch"] = relationship(back_populates="raw_scans")
    crop: Mapped["CardCrop | None"] = relationship(
        back_populates="raw_scan", uselist=False, cascade="all, delete-orphan"
    )


@event.listens_for(RawScan, "before_insert")
@event.listens_for(RawScan, "before_update")
def _set_pairing_key(mapper, connection, target: RawScan) -> None:
    target.pairing_key = _compute_pairing_key(target.original_filename)
