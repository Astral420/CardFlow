from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.raw_scan import RawScan


class CardCrop(Base):
    __tablename__ = "card_crops"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_scan_id: Mapped[int] = mapped_column(
        ForeignKey("raw_scans.id"), nullable=False, unique=True
    )
    r2_key_cropped: Mapped[str | None] = mapped_column(String, nullable=True)
    crop_bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    aspect_ratio_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    rotation_degrees: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Indexed: the rotation-review queue filters on "IS NULL" across every
    # cropped scan (app.api.rotation._next_pending / queue_count).
    rotation_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    hash_0: Mapped[str | None] = mapped_column(String, nullable=True)
    hash_90: Mapped[str | None] = mapped_column(String, nullable=True)
    hash_180: Mapped[str | None] = mapped_column(String, nullable=True)
    hash_270: Mapped[str | None] = mapped_column(String, nullable=True)

    # Stored as a JSON array (a flattened HSV histogram), not an object.
    color_sig_0: Mapped[list | None] = mapped_column(JSON, nullable=True)
    color_sig_90: Mapped[list | None] = mapped_column(JSON, nullable=True)
    color_sig_180: Mapped[list | None] = mapped_column(JSON, nullable=True)
    color_sig_270: Mapped[list | None] = mapped_column(JSON, nullable=True)

    raw_scan: Mapped["RawScan"] = relationship(back_populates="crop")
