import enum

from app.db import Base
from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column


class UserRole(str, enum.Enum):
    admin = "admin"
    reviewer = "reviewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False
    )
