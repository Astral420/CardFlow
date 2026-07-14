import pytest
from pydantic import ValidationError

from app.api.common import finite_float_or_none
from app.schemas import RotateRequest


def test_rotate_request_accepts_supported_quarter_turns():
    assert RotateRequest(degrees=90).degrees == 90
    assert RotateRequest(degrees=180).degrees == 180
    assert RotateRequest(degrees=270).degrees == 270
    assert RotateRequest(degrees=-90).degrees == 270


def test_rotate_request_rejects_unsupported_degrees():
    with pytest.raises(ValidationError):
        RotateRequest(degrees=45)

    with pytest.raises(ValidationError):
        RotateRequest(degrees=360)


def test_duplicate_score_sanitizer_rejects_non_json_floats():
    assert finite_float_or_none(0.25) == 0.25
    assert finite_float_or_none(None) is None
    assert finite_float_or_none(float("nan")) is None
    assert finite_float_or_none(float("inf")) is None
