from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db import get_db
from app.models import User, UserRole
from app.schemas import UserCreateRequest, UserOut
from app.security import hash_password
from app.token_store import revoke_user_sessions

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db), _admin: User = Depends(require_admin)
) -> list[User]:
    return db.query(User).order_by(User.created_at).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_reviewer(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> User:
    # Admins can only create Reviewer accounts through this endpoint -- there
    # is intentionally no way to mint another Admin from the UI/API.
    existing = db.query(User).filter(User.name == payload.name).first()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with that name already exists"
        )

    user = User(
        name=payload.name,
        role=UserRole.reviewer,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with that name already exists"
        )
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reviewer(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")

    # Admins manage Reviewers, not other Admins -- this also rules out an
    # Admin deleting their own account by accident.
    if user.role != UserRole.reviewer:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only Reviewer accounts can be deleted"
        )

    db.delete(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This account has review history and can't be deleted",
        )

    # Only after the delete has actually committed -- if it failed above
    # (e.g. the IntegrityError case), the account still exists and its
    # sessions should keep working normally.
    revoke_user_sessions(user_id)
