import enum
from datetime import datetime

from app.db import Base
from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column


class UserRole(str, enum.Enum):
    admin = "admin"
    reviewer = "reviewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False
    )
    # Nullable: legacy/seeded users (the original Admin, and any user
    # created before individual passwords existed) have no password_hash
    # and continue to authenticate with the shared APP_PASSCODE (see
    # app.api.auth.login). Reviewer accounts created via the admin user
    # management UI always get one.
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
