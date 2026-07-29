"""Helpers for the client's front/back filename convention.

Filenames look like ``{card_id}-front.jpg`` / ``{card_id}-back.jpg``. We never
need to persist ``card_id`` as its own column — it's only used to (a) decide
which side a scan is, and (b) pair a front/back scan together for display and
as a duplicate-detection filename tiebreaker.
"""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import ScanSide

_SIDE_RE = re.compile(r"^(?P<stem>.+)-(?P<side>front|back)\.[^.]+$", re.IGNORECASE)


def parse_side(filename: str) -> "ScanSide | None":
    # Local import: RawScan computes pairing_key() (below) on insert/update,
    # so app.models.raw_scan imports this module at load time. Importing
    # ScanSide at module level here would close a circular import loop
    # (app.models -> raw_scan -> app.naming -> app.models). parse_side is
    # only called at runtime, well after app.models has finished loading,
    # so a local import here is safe.
    from app.models import ScanSide

    match = _SIDE_RE.match(filename)
    if not match:
        return None
    return ScanSide(match.group("side").lower())


def pairing_key(filename: str) -> str:
    """Filename with the side suffix stripped, used to match front <-> back."""
    match = _SIDE_RE.match(filename)
    if not match:
        return filename
    return match.group("stem").lower()
