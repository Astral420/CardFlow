"""Regression coverage for the access/refresh token architecture
(app.security, app.token_store):

1. Access tokens issued before revoke_user_sessions() stop decoding
   afterward -- this is the mechanism that makes an Admin's user-delete
   take effect immediately, without waiting for the token's own exp.
2. Refresh tokens rotate on use: the old jti stops working, the new one
   works, and a fresh access token comes back with it.
3. Replaying an already-rotated refresh token is treated as theft --
   it's rejected *and* it revokes the rest of that user's sessions too.
4. The full user-delete flow (app.api.users.delete_reviewer) revokes
   sessions as a side effect, exercised end to end with real JWTs.
"""

import time

from app.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    rotate_refresh_token,
)
from app.token_store import revoke_user_sessions


def test_access_token_round_trips_normally():
    token = create_access_token(user_id=42)
    assert decode_access_token(token) == 42


def test_access_token_stops_working_immediately_after_revocation():
    token = create_access_token(user_id=7)
    assert decode_access_token(token) == 7

    revoke_user_sessions(7)

    assert decode_access_token(token) is None


def test_revocation_does_not_affect_other_users():
    victim_token = create_access_token(user_id=1)
    bystander_token = create_access_token(user_id=2)

    revoke_user_sessions(1)

    assert decode_access_token(victim_token) is None
    assert decode_access_token(bystander_token) == 2


def test_access_token_issued_after_revocation_still_works():
    # Revocation is a point-in-time marker (iat <= revoked_at), not a
    # permanent ban -- a token minted *after* the revoke call (e.g. the
    # user logging back in, or a refresh completed a moment later) must
    # not be caught by an earlier revoke.
    revoke_user_sessions(99)
    time.sleep(0.01)  # ensure the new token's iat is strictly later
    token = create_access_token(user_id=99)

    assert decode_access_token(token) == 99


def test_refresh_token_rotates_and_issues_a_new_working_access_token():
    refresh = create_refresh_token(user_id=5)

    rotated = rotate_refresh_token(refresh)

    assert rotated is not None
    new_access, new_refresh = rotated
    assert decode_access_token(new_access) == 5
    assert new_refresh != refresh


def test_reusing_an_already_rotated_refresh_token_is_rejected():
    refresh = create_refresh_token(user_id=8)
    first = rotate_refresh_token(refresh)
    assert first is not None

    # Replaying the *original* (already-consumed) token.
    replay = rotate_refresh_token(refresh)

    assert replay is None


def test_replaying_a_rotated_refresh_token_revokes_the_whole_family():
    refresh = create_refresh_token(user_id=11)
    first = rotate_refresh_token(refresh)
    assert first is not None
    _new_access, new_refresh = first

    # A replay of the old token is treated as theft -- even the
    # legitimately-rotated new token should now be dead too, since the
    # whole family is considered compromised.
    assert rotate_refresh_token(refresh) is None
    assert rotate_refresh_token(new_refresh) is None


def test_decode_access_token_rejects_a_refresh_token():
    # The two token types share a signing key; type-checking in
    # app.security._decode is what stops a refresh token from being used
    # directly as a bearer access token.
    refresh = create_refresh_token(user_id=3)
    assert decode_access_token(refresh) is None


def test_decode_access_token_rejects_garbage():
    assert decode_access_token("not-a-real-jwt") is None


# ---- End-to-end through the actual delete endpoint ----


def test_deleting_a_user_revokes_their_outstanding_access_token():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.api.users import delete_reviewer
    from app.db import Base
    from app.models import User, UserRole

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    admin = User(name="root", role=UserRole.admin)
    reviewer = User(name="jamie", role=UserRole.reviewer)
    db.add_all([admin, reviewer])
    db.commit()

    token = create_access_token(reviewer.id)
    assert decode_access_token(token) == reviewer.id

    delete_reviewer(reviewer.id, db=db, _admin=admin)

    assert decode_access_token(token) is None
