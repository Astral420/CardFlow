import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import settings
from app.token_store import consume_refresh_token, is_token_revoked, register_refresh_token, revoke_user_sessions

# bcrypt has a 72-byte input limit; longer passwords are truncated by the
# library itself, but we cap here too so behavior is explicit either way.
_MAX_PASSWORD_BYTES = 72

_ACCESS_TOKEN_TYPE = "access"
_REFRESH_TOKEN_TYPE = "refresh"


def hash_password(password: str) -> str:
    """Hash a plaintext password for storage (per-user Reviewer accounts)."""
    truncated = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash."""
    truncated = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    try:
        return bcrypt.checkpw(truncated, password_hash.encode("utf-8"))
    except ValueError:
        # Malformed/legacy hash -- fail closed rather than raising 500s.
        return False


def _encode(user_id: int, token_type: str, lifetime: timedelta) -> tuple[str, str]:
    """Build and sign a JWT of the given type. Returns (token, jti).

    `iat` is kept at full float precision (not truncated to whole
    seconds) specifically so it compares correctly against the float
    revocation timestamp in app.token_store -- truncating it could make
    a token minted milliseconds after a revoke land in the same integer
    second as the revoke and get wrongly rejected as pre-revocation.
    """
    now = datetime.now(timezone.utc)
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now.timestamp(),
        "exp": now + lifetime,
        "jti": jti,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, jti


def _decode(token: str, expected_type: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload


def create_access_token(user_id: int) -> str:
    token, _jti = _encode(
        user_id, _ACCESS_TOKEN_TYPE, timedelta(minutes=settings.access_token_expires_minutes)
    )
    return token


def create_refresh_token(user_id: int) -> str:
    """Issue a refresh token and register it as live in its user's family
    (app.token_store) so it can be individually consumed on rotation or
    revoked as part of `revoke_user_sessions`."""
    token, jti = _encode(
        user_id, _REFRESH_TOKEN_TYPE, timedelta(days=settings.refresh_token_expires_days)
    )
    register_refresh_token(user_id, jti)
    return token


def decode_access_token(token: str) -> int | None:
    """Validate an access token's signature, type, and expiry, then check
    it against Redis for per-user revocation. Returns the user id, or
    None if the token is invalid, expired, malformed, or belongs to a
    user whose sessions were revoked at/after this token's issued-at
    time (e.g. an Admin deleted them after it was issued)."""
    payload = _decode(token, _ACCESS_TOKEN_TYPE)
    if payload is None:
        return None
    sub, iat = payload.get("sub"), payload.get("iat")
    if sub is None or iat is None:
        return None
    try:
        user_id = int(sub)
    except ValueError:
        return None
    if is_token_revoked(user_id, float(iat)):
        return None
    return user_id


def rotate_refresh_token(token: str) -> tuple[str, str] | None:
    """Validate and consume a refresh token, returning a fresh
    (access_token, refresh_token) pair -- or None if the token is
    invalid, expired, or already used.

    A refresh token that's already been consumed (its jti is no longer
    in the user's family) is treated as a replayed/stolen token, not
    merely an expired one: a legitimate client always rotates on use, so
    this can only happen if an old copy of the token is being reused.
    Revoking the rest of the family here -- instead of just rejecting
    this one call -- makes sure that whoever holds any other copy of a
    leaked token family is cut off too.
    """
    payload = _decode(token, _REFRESH_TOKEN_TYPE)
    if payload is None:
        return None
    sub, jti = payload.get("sub"), payload.get("jti")
    if sub is None or jti is None:
        return None
    try:
        user_id = int(sub)
    except ValueError:
        return None

    if not consume_refresh_token(user_id, jti):
        revoke_user_sessions(user_id)
        return None

    return create_access_token(user_id), create_refresh_token(user_id)


def revoke_refresh_token(token: str) -> None:
    """Consume (invalidate) a single refresh token -- used for an explicit
    logout of just the current session. Best-effort: a garbled, expired,
    or already-used token is simply ignored rather than raising, since
    the caller's goal (this session no longer works) is already true."""
    payload = _decode(token, _REFRESH_TOKEN_TYPE)
    if payload is None:
        return
    sub, jti = payload.get("sub"), payload.get("jti")
    if sub is None or jti is None:
        return
    try:
        user_id = int(sub)
    except ValueError:
        return
    consume_refresh_token(user_id, jti)
