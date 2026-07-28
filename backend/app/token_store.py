"""Redis-backed session state: per-user revocation markers and the live
refresh-token registry. This is what lets an Admin's user-delete action
immediately invalidate every access and refresh token already issued to
that account, instead of waiting for natural JWT expiry.

Key layout (all on settings.redis_auth_url, a dedicated DB index -- see
app.redis_client):

  revoked:user:{user_id}    -> unix timestamp (float), no TTL
      Access tokens whose `iat` is at or before this timestamp are
      rejected regardless of their own `exp` (checked in
      app.security.decode_access_token). Set on delete; the natural hook
      for a future "sign out everywhere" action too. No TTL: a deleted
      user's row is gone, so there's nothing to let this key outlive.

  refresh:family:{user_id}  -> Redis SET of live refresh-token jti's
      Membership means "this refresh token hasn't been used (rotated) or
      revoked yet". TTL matches the refresh-token lifetime so an
      abandoned session's Redis footprint cleans itself up on its own.
"""

import time

from app.config import settings
from app.redis_client import redis_client

_REVOKED_KEY_FMT = "revoked:user:{user_id}"
_FAMILY_KEY_FMT = "refresh:family:{user_id}"


def _revoked_key(user_id: int) -> str:
    return _REVOKED_KEY_FMT.format(user_id=user_id)


def _family_key(user_id: int) -> str:
    return _FAMILY_KEY_FMT.format(user_id=user_id)


def register_refresh_token(user_id: int, jti: str) -> None:
    """Record a newly issued refresh token as live in its user's family."""
    key = _family_key(user_id)
    redis_client.sadd(key, jti)
    redis_client.expire(key, settings.refresh_token_expires_days * 86400)


def consume_refresh_token(user_id: int, jti: str) -> bool:
    """Atomically check-and-remove a refresh token's jti from its family.

    Returns True if the jti was present (this refresh token hadn't
    already been used/rotated) -- the caller should proceed to rotate it.
    Returns False if it was already gone: either it's being replayed
    after rotation (possible theft) or the user's sessions were revoked.
    Either way, the caller should refuse and revoke the rest of the
    family too (see revoke_user_sessions), since a reused token means
    the family can no longer be trusted.
    """
    return redis_client.srem(_family_key(user_id), jti) == 1


def revoke_user_sessions(user_id: int) -> None:
    """Immediately invalidate every access and refresh token for a user.

    Bumping the revocation timestamp invalidates outstanding access
    tokens on their next use; clearing the refresh family stops any of
    them from minting a new access token afterward. Called when an Admin
    deletes the account.
    """
    redis_client.set(_revoked_key(user_id), time.time())
    redis_client.delete(_family_key(user_id))


def is_token_revoked(user_id: int, issued_at: float) -> bool:
    """True if `user_id`'s sessions were revoked at or after `issued_at`."""
    revoked_at = redis_client.get(_revoked_key(user_id))
    if revoked_at is None:
        return False
    return issued_at <= float(revoked_at)
