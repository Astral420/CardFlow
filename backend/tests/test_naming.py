from app.models import ScanSide
from app.naming import pairing_key, parse_side


def test_parse_side_front():
    assert parse_side("12345-front.jpg") == ScanSide.front


def test_parse_side_back_case_insensitive():
    assert parse_side("ABC-BACK.PNG") == ScanSide.back


def test_parse_side_unrecognized_returns_none():
    assert parse_side("randomfile.jpg") is None


def test_pairing_key_strips_side_suffix():
    assert pairing_key("12345-front.jpg") == pairing_key("12345-back.jpg") == "12345"
