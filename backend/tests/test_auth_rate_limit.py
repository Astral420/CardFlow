"""Regression coverage for the login-endpoint hardening:

1. app.rate_limit is a plain sliding-window limiter -- tested directly.
2. auth.login() applies it per-client and returns 429 once exhausted,
   and still uses a constant-time comparison for the shared passcode.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import rate_limit
from app.api.auth import LOGIN_RATE_LIMIT_MAX_ATTEMPTS, login
from app.config import settings
from app.db import Base
from app.models import User, UserRole
from app.schemas import LoginRequest


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _fake_request(ip: str):
    request = MagicMock()
    request.client.host = ip
    return request


def setup_function(_):
    rate_limit.reset()


def test_rate_limiter_allows_up_to_the_limit_then_blocks():
    for _ in range(3):
        assert rate_limit.is_rate_limited("k", max_attempts=3, window_seconds=60) is False
    assert rate_limit.is_rate_limited("k", max_attempts=3, window_seconds=60) is True


def test_rate_limiter_keys_are_independent():
    for _ in range(3):
        rate_limit.is_rate_limited("a", max_attempts=3, window_seconds=60)
    # A different key has its own budget.
    assert rate_limit.is_rate_limited("b", max_attempts=3, window_seconds=60) is False


def test_login_rejects_wrong_password_without_tripping_rate_limit_early():
    db = _make_session()
    db.add(User(name="alex", role=UserRole.admin))
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        login(
            LoginRequest(name="alex", password="wrong"),
            _fake_request("1.2.3.4"),
            db=db,
        )
    assert exc_info.value.status_code == 401


def test_login_blocks_after_too_many_attempts_from_same_ip():
    db = _make_session()
    db.add(User(name="alex", role=UserRole.admin))
    db.commit()

    for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
        with pytest.raises(HTTPException) as exc_info:
            login(
                LoginRequest(name="alex", password="wrong"),
                _fake_request("9.9.9.9"),
                db=db,
            )
        assert exc_info.value.status_code == 401

    with pytest.raises(HTTPException) as exc_info:
        login(
            LoginRequest(name="alex", password=settings.app_passcode),
            _fake_request("9.9.9.9"),
            db=db,
        )
    assert exc_info.value.status_code == 429


def test_login_from_a_different_ip_is_not_affected_by_another_ips_lockout():
    db = _make_session()
    db.add(User(name="alex", role=UserRole.admin))
    db.commit()

    for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
        with pytest.raises(HTTPException):
            login(
                LoginRequest(name="alex", password="wrong"),
                _fake_request("9.9.9.9"),
                db=db,
            )

    # A different client IP should still get a normal 401, not a 429.
    with pytest.raises(HTTPException) as exc_info:
        login(
            LoginRequest(name="alex", password="wrong"),
            _fake_request("1.1.1.1"),
            db=db,
        )
    assert exc_info.value.status_code == 401
