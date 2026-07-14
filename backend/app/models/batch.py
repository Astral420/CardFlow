import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.raw_scan import RawScan


class BatchStatus(str, enum.Enum):
    extracting = "extracting"
    cropping = "cropping"
    rotation_review = "rotation_review"
    duplicate_review = "duplicate_review"
    complete = "complete"


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source_label: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[BatchStatus] = mapped_column(
        Enum(BatchStatus, name="batch_status"),
        default=BatchStatus.extracting,
        nullable=False,
    )

    raw_scans: Mapped[list["RawScan"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )
