import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.db import get_db
from app.models import User
from app.rate_limit import is_rate_limited
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.security import (
    create_access_token,
    create_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# A short shared passcode is brute-forceable with unlimited guesses; this
# doesn't make the passcode itself stronger, just stops unlimited guessing.
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 10
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 60.0

# Scope the refresh cookie to just the auth routes -- the browser then
# only ever attaches it to /login, /refresh, /logout, never to every
# other /api/* call, which limits its exposure.
_REFRESH_COOKIE_PATH = "/api/auth"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        domain=settings.refresh_cookie_domain,
        path=_REFRESH_COOKIE_PATH,
        max_age=settings.refresh_token_expires_days * 86400,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        domain=settings.refresh_cookie_domain,
        path=_REFRESH_COOKIE_PATH,
    )


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
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

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response) -> TokenResponse:
    """Exchange the httpOnly refresh cookie for a new access token,
    rotating the refresh token in the same call. The frontend calls this
    transparently whenever an access token has expired or gone missing
    (see the response interceptor in frontend/src/lib/api.ts) -- the
    person never sees this as a separate "log in" step."""
    token = request.cookies.get(settings.refresh_cookie_name)
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh session")

    rotated = rotate_refresh_token(token)
    if rotated is None:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Session expired, please sign in again"
        )

    access_token, new_refresh_token = rotated
    _set_refresh_cookie(response, new_refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response) -> None:
    """Revoke just the current session's refresh token and clear its
    cookie. Deliberately doesn't require a valid access token -- signing
    out should work even if the access token already expired."""
    token = request.cookies.get(settings.refresh_cookie_name)
    if token is not None:
        revoke_refresh_token(token)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
