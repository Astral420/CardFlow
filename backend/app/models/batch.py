import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.batch_export import BatchExport
    from app.models.raw_scan import RawScan


class BatchStatus(str, enum.Enum):
    extracting = "extracting"
    cropping = "cropping"
    rotation_review = "rotation_review"
    duplicate_review = "duplicate_review"
    complete = "complete"
    deleting = "deleting"


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
    # Durable hand-off metadata for asynchronous deletion. Keeping this on
    # the batch makes a queued deletion recoverable after API/worker restarts
    # without treating Celery message arguments as the only source of truth.
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deletion_previous_status: Mapped[str | None] = mapped_column(String, nullable=True)
    deletion_requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    raw_scans: Mapped[list["RawScan"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )
    exports: Mapped[list["BatchExport"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )
