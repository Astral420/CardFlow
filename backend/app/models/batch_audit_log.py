"""Durable audit log for hard-deleted batches.

When a batch is hard-deleted via DELETE /api/batches/{id}, one row is
written here *before* the cascade delete fires.  This table survives
Redis flushes and server restarts -- unlike the obs:recent_batch_deletes
Redis list (which is a best-effort ops-dashboard feed only).

Postgres is authoritative; Redis is cosmetic.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.user import User


class BatchAuditLog(Base):
    __tablename__ = "batch_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # The original batch ID.  NOT a FK -- the batch row is gone after the
    # delete, so a FK would violate the constraint the moment the cascade
    # fires.  We keep the raw int so history is still queryable.
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Which admin triggered this action.
    performed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Snapshot of key batch metadata at delete time (the source row is gone).
    action: Mapped[str] = mapped_column(String, nullable=False, default="hard_delete")
    source_label: Mapped[str | None] = mapped_column(String, nullable=True)
    batch_status: Mapped[str | None] = mapped_column(String, nullable=True)

    # Deletion accounting
    scan_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    r2_keys_deleted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    r2_keys_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Free-form notes (e.g. reason, error details for partial R2 failures)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    performer: Mapped["User | None"] = relationship(foreign_keys=[performed_by])
