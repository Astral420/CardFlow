import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

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

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), nullable=False)
    r2_key_raw: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
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
