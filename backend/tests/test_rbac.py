"""Regression coverage for RBAC (Admin / Reviewer / Guest):

1. Login supports two credential paths on the same endpoint: legacy/seeded
   users with no individual password fall back to the shared APP_PASSCODE,
   while accounts created via the admin user-management API must match
   their own password exactly (and the shared passcode must NOT work for
   them).
2. `require_roles` (and the `require_reviewer` / `require_admin` presets
   built from it) let permitted roles through and reject others with 403.
3. `get_current_user_optional` never raises -- it's what lets Guests hit
   read-only endpoints without a token.
4. The admin user-management endpoints (list/create/delete) enforce the
   "Admins manage Reviewers, not other Admins" rule end to end.

These exercise the route/dependency functions directly against an
in-memory sqlite DB, matching this project's existing unit-test style
(see test_rotation_review.py) rather than spinning up the full app.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user_optional, require_admin, require_reviewer
from app.api.auth import login
from app.api.users import create_reviewer, delete_reviewer, list_users
from app.config import settings
from app.db import Base
from app.models import User, UserRole
from app.schemas import LoginRequest, UserCreateRequest
from app.security import hash_password
from unittest.mock import MagicMock


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _fake_request(ip: str = "1.2.3.4"):
    request = MagicMock()
    request.client.host = ip
    return request


def _fake_response():
    # login() now sets a refresh-token cookie on the response
    # (app.api.auth._set_refresh_cookie) -- a MagicMock happily accepts
    # that .set_cookie(...) call without needing a real Response.
    return MagicMock()


# ---- Login: legacy shared-passcode vs. individual Reviewer password ----


def test_legacy_seeded_user_still_logs_in_with_shared_passcode():
    db = _make_session()
    db.add(User(name="alex", role=UserRole.admin))  # no password_hash
    db.commit()

    token = login(
        LoginRequest(name="alex", password=settings.app_passcode),
        _fake_request(),
        _fake_response(),
        db=db,
    )
    assert token.access_token


def test_reviewer_with_individual_password_cannot_use_shared_passcode():
    db = _make_session()
    db.add(
        User(
            name="jamie",
            role=UserRole.reviewer,
            password_hash=hash_password("correct horse battery staple"),
        )
    )
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        login(
            LoginRequest(name="jamie", password=settings.app_passcode),
            _fake_request(),
            _fake_response(),
            db=db,
        )
    assert exc_info.value.status_code == 401


def test_reviewer_logs_in_with_their_own_password():
    db = _make_session()
    db.add(
        User(
            name="jamie",
            role=UserRole.reviewer,
            password_hash=hash_password("correct horse battery staple"),
        )
    )
    db.commit()

    token = login(
        LoginRequest(name="jamie", password="correct horse battery staple"),
        _fake_request(),
        _fake_response(),
        db=db,
    )
    assert token.access_token


def test_unknown_user_and_wrong_password_return_the_same_generic_error():
    db = _make_session()
    db.add(User(name="alex", role=UserRole.admin))
    db.commit()

    with pytest.raises(HTTPException) as unknown_exc:
        login(
            LoginRequest(name="nobody", password="whatever"),
            _fake_request("2.2.2.2"),
            _fake_response(),
            db=db,
        )
    with pytest.raises(HTTPException) as wrong_exc:
        login(
            LoginRequest(name="alex", password="whatever"),
            _fake_request("3.3.3.3"),
            _fake_response(),
            db=db,
        )

    assert unknown_exc.value.status_code == wrong_exc.value.status_code == 401
    assert unknown_exc.value.detail == wrong_exc.value.detail


# ---- get_current_user_optional never raises ----


def test_get_current_user_optional_is_none_without_credentials():
    db = _make_session()
    assert get_current_user_optional(credentials=None, db=db) is None


def test_get_current_user_optional_is_none_for_a_garbage_token():
    db = _make_session()
    creds = MagicMock()
    creds.credentials = "not-a-real-jwt"
    assert get_current_user_optional(credentials=creds, db=db) is None


# ---- require_roles / require_reviewer / require_admin ----


def test_require_reviewer_allows_reviewer_and_admin_but_not_none():
    admin = User(id=1, name="admin", role=UserRole.admin)
    reviewer = User(id=2, name="reviewer", role=UserRole.reviewer)

    # require_reviewer is itself the FastAPI dependency function -- call it
    # directly with an already-resolved user, bypassing the inner
    # get_current_user Depends() (which needs a real request/token).
    assert require_reviewer(current_user=admin) is admin
    assert require_reviewer(current_user=reviewer) is reviewer


def test_require_admin_rejects_reviewer_with_403():
    reviewer = User(id=2, name="reviewer", role=UserRole.reviewer)
    with pytest.raises(HTTPException) as exc_info:
        require_admin(current_user=reviewer)
    assert exc_info.value.status_code == 403


# ---- Admin user management ----


def test_admin_can_create_list_and_delete_an_reviewer():
    db = _make_session()
    admin = User(name="root", role=UserRole.admin)
    db.add(admin)
    db.commit()

    created = create_reviewer(
        UserCreateRequest(name="new-reviewer", password="a very good password"),
        db=db,
        _admin=admin,
    )
    assert created.role == UserRole.reviewer
    assert created.password_hash is not None
    assert created.password_hash != "a very good password"  # never store plaintext

    names = {u.name for u in list_users(db=db, _admin=admin)}
    assert {"root", "new-reviewer"} <= names

    delete_reviewer(created.id, db=db, _admin=admin)
    assert db.get(User, created.id) is None


def test_creating_reviewer_with_duplicate_name_is_rejected():
    db = _make_session()
    admin = User(name="root", role=UserRole.admin)
    db.add(admin)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_reviewer(
            UserCreateRequest(name="root", password="a very good password"),
            db=db,
            _admin=admin,
        )
    assert exc_info.value.status_code == 409


def test_admin_accounts_cannot_be_deleted_via_the_reviewer_delete_endpoint():
    db = _make_session()
    admin = User(name="root", role=UserRole.admin)
    other_admin = User(name="second-admin", role=UserRole.admin)
    db.add_all([admin, other_admin])
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        delete_reviewer(other_admin.id, db=db, _admin=admin)
    assert exc_info.value.status_code == 403
    assert db.get(User, other_admin.id) is not None
