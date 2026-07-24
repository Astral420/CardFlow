from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, UserRole
from app.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Like get_current_user, but never raises -- returns None for Guests.

    Used on read-only endpoints the RBAC spec says unauthenticated Guests
    may view. A missing, malformed, or expired token is just treated as
    "not signed in" here rather than a hard failure; the strict version
    (get_current_user) is what still enforces real auth on /auth/me and
    every mutating endpoint.
    """
    if credentials is None:
        return None
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        return None
    return db.get(User, user_id)


def require_roles(*roles: UserRole):
    """Dependency factory: require an authenticated user whose role is one
    of `roles`. Unauthenticated -> 401 (via get_current_user). Wrong role
    -> 403."""

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "You don't have permission to do that"
            )
        return current_user

    return dependency


# Reviewers and Admins can use all normal application functionality (upload,
# process, review, export). Only Admins can manage user accounts.
require_reviewer = require_roles(UserRole.admin, UserRole.reviewer)
require_admin = require_roles(UserRole.admin)
