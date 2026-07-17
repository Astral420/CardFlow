from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image
from app.vision.crop import auto_crop

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _polygon_area(points: list[list[float]]) -> float:
    pts = np.array(points, dtype="float64")
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def _make_scan_bytes(card_w: int, card_h: int, canvas_size: int = 400) -> bytes:
    canvas = np.zeros(
        (canvas_size, canvas_size, 3), dtype=np.uint8
    )  # near-black background
    x0 = (canvas_size - card_w) // 2
    y0 = (canvas_size - card_h) // 2
    canvas[y0 : y0 + card_h, x0 : x0 + card_w] = (200, 200, 200)
    ok, buf = cv2.imencode(".jpg", canvas)
    assert ok
    return buf.tobytes()


def test_auto_crop_accepts_card_aspect_ratio():
    image_bytes = _make_scan_bytes(card_w=125, card_h=175, canvas_size=400)
    result = auto_crop(image_bytes)
    assert result.aspect_ratio_ok is True
    assert result.aspect_ratio == pytest.approx(3.5 / 2.5, rel=0.05)


def test_auto_crop_flags_bad_aspect_ratio():
    image_bytes = _make_scan_bytes(card_w=200, card_h=200, canvas_size=400)
    result = auto_crop(image_bytes)
    assert result.aspect_ratio_ok is False


def test_auto_crop_preserves_landscape_output():
    image_bytes = _make_scan_bytes(card_w=175, card_h=125, canvas_size=400)
    result = auto_crop(image_bytes)
    decoded = cv2.imdecode(
        np.frombuffer(result.image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
    )
    assert result.orientation == "landscape"
    assert decoded.shape[1] > decoded.shape[0]  # width > height


def test_auto_crop_honors_exif_orientation_for_portrait_cards(tmp_path):
    # Simulates a common phone/scanner JPEG: the stored pixels are landscape,
    # but EXIF orientation says the displayed image is portrait.
    canvas = np.zeros((400, 400, 3), dtype=np.uint8)
    canvas[137:262, 112:287] = (200, 200, 200)
    rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
    image_path = tmp_path / "sideways-with-exif.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.fromarray(rgb).save(image_path, exif=exif)

    result = auto_crop(image_path.read_bytes())
    decoded = cv2.imdecode(
        np.frombuffer(result.image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
    )

    assert result.orientation == "portrait"
    assert decoded.shape[0] > decoded.shape[1]  # height > width


def test_auto_crop_keeps_dark_card_border_instead_of_bright_interior():
    canvas_size = 400
    canvas = np.zeros((canvas_size, canvas_size, 3), dtype=np.uint8)
    x0, y0 = 100, 140
    card_w, card_h = 200, 140
    canvas[y0 : y0 + card_h, x0 : x0 + card_w] = (20, 20, 20)
    inset = 24
    canvas[
        y0 + inset : y0 + card_h - inset,
        x0 + inset : x0 + card_w - inset,
    ] = (210, 210, 210)

    ok, buf = cv2.imencode(".jpg", canvas)
    assert ok

    result = auto_crop(buf.tobytes())
    decoded = cv2.imdecode(
        np.frombuffer(result.image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
    )

    top_edge = decoded[20:60, decoded.shape[1] // 3 : decoded.shape[1] * 2 // 3]
    assert result.aspect_ratio_ok is True
    assert float(top_edge.mean()) < 90


# --- Regression coverage for the laminated/protector-sleeve glare bug ---
#
# These fixtures are real scans of a single laminated card (front + back) shot
# on a near-black scan bed. The sleeve produces bright glare streaks outside
# the card's true edges, which previously caused two failure modes depending
# on tuning:
#   - close_kernel=(9,9) + an Otsu-thresholded mask candidate: Otsu isolated
#     only the brightest interior artwork panel, producing a tightly zoomed
#     crop that clipped real card content.
#   - close_kernel=(21,21): the larger closing kernel bridged the glare
#     streaks into the card contour for every mask, producing an
#     under-cropped image with excess black background on all sides.
#
# Rather than pin exact pixel coordinates (brittle), these tests check two
# scan-setup-independent invariants: (1) the front and back detections of the
# same physical card should agree closely, since it's the same rectangle on
# the same rig, and (2) the detected area should fall within a band wide
# enough for normal variation but narrow enough to catch either failure mode.
_LAMINATED_AREA_FRACTION_BOUNDS = (0.10, 0.16)


@pytest.mark.parametrize("side", ["front", "back"])
def test_auto_crop_laminated_card_area_within_expected_band(side):
    image_bytes = (FIXTURES_DIR / f"laminated_card-{side}.jpg").read_bytes()
    with Image.open(FIXTURES_DIR / f"laminated_card-{side}.jpg") as img:
        image_area = img.width * img.height

    result = auto_crop(image_bytes)
    area_fraction = _polygon_area(result.bbox) / image_area

    low, high = _LAMINATED_AREA_FRACTION_BOUNDS
    assert low <= area_fraction <= high, (
        f"{side} crop covers {area_fraction:.3f} of the scan bed, expected "
        f"between {low} and {high}. Below this band usually means a bright "
        "interior panel (e.g. an Otsu-style mask) was picked instead of the "
        "full card; above it usually means glare/background got merged "
        "into the card contour (e.g. too large a morphological close kernel)."
    )
    assert result.aspect_ratio_ok is True


def test_auto_crop_laminated_card_front_and_back_are_consistent():
    front_bytes = (FIXTURES_DIR / "laminated_card-front.jpg").read_bytes()
    back_bytes = (FIXTURES_DIR / "laminated_card-back.jpg").read_bytes()

    with Image.open(FIXTURES_DIR / "laminated_card-front.jpg") as img:
        front_area = img.width * img.height
    with Image.open(FIXTURES_DIR / "laminated_card-back.jpg") as img:
        back_area = img.width * img.height

    front = auto_crop(front_bytes)
    back = auto_crop(back_bytes)

    front_fraction = _polygon_area(front.bbox) / front_area
    back_fraction = _polygon_area(back.bbox) / back_area

    # Same physical card, same rig -> detected coverage should agree closely
    # even though the front (photo art) and back (text block) have very
    # different content. A content-sensitive mask (Otsu) made this diverge
    # sharply in the past (~0.02 front vs ~0.09 back on this fixture pair).
    relative_diff = abs(front_fraction - back_fraction) / max(
        front_fraction, back_fraction
    )
    assert relative_diff < 0.15, (
        f"front area fraction {front_fraction:.3f} vs back {back_fraction:.3f} "
        f"differ by {relative_diff:.1%}, expected close agreement for the "
        "same physical card"
    )
