import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.db import get_db
from app.models import User
from app.rate_limit import is_rate_limited
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.security import create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

# A short shared passcode is brute-forceable with unlimited guesses; this
# doesn't make the passcode itself stronger, just stops unlimited guessing.
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 10
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 60.0


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest, request: Request, db: Session = Depends(get_db)
) -> TokenResponse:
    # Minimal auth for two known users (spec Section 13): a shared app
    # passcode plus a known display name, rather than per-user passwords
    # (the users table intentionally has no password column).
    client_ip = request.client.host if request.client else "unknown"
    if is_rate_limited(
        f"login:{client_ip}",
        LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
        LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    ):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many login attempts. Try again in a minute.",
        )

    # Constant-time comparison: a plain `!=` short-circuits on the first
    # mismatched byte, which in principle leaks timing information about
    # how many leading characters of a guess were correct.
    if not secrets.compare_digest(payload.passcode, settings.app_passcode):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid passcode")

    user = db.query(User).filter(User.name == payload.name).first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")

    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
