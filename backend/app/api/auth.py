import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.db import get_db
from app.models import User
from app.rate_limit import is_rate_limited
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# A short shared passcode is brute-forceable with unlimited guesses; this
# doesn't make the passcode itself stronger, just stops unlimited guessing.
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 10
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 60.0


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest, request: Request, db: Session = Depends(get_db)
) -> TokenResponse:
    # Two ways to authenticate, distinguished by whether the account has an
    # individual password set (see app.models.user.User.password_hash):
    #   - Legacy/seeded users (the original Admin, and anyone created before
    #     individual passwords existed) have no password_hash and continue
    #     to sign in with the shared APP_PASSCODE, exactly as before.
    #   - Reviewer accounts created via the admin user-management UI always
    #     have their own password_hash and must match it exactly.
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

    user = db.query(User).filter(User.name == payload.name).first()

    if user is not None and user.password_hash is not None:
        credential_ok = verify_password(payload.password, user.password_hash)
    else:
        # Unknown name, or a legacy/seeded user with no individual
        # password: check the shared passcode. Doing this even for an
        # unknown name (rather than short-circuiting) avoids leaking which
        # display names exist via response timing, and the generic error
        # message below avoids leaking it via response content.
        credential_ok = secrets.compare_digest(payload.password, settings.app_passcode)

    if user is None or not credential_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
