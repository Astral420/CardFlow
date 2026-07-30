from io import BytesIO

import cv2
import numpy as np
import pytest
from PIL import Image
from app.vision.crop import auto_crop


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


def _make_precropped_bytes(width: int, height: int) -> bytes:
    """A card image with no scan-bed background left around it, simulating
    an intake source (e.g. a scanner) that already auto-crops on-device.
    A distinct marker in the top-left corner lets tests confirm the output
    wasn't rotated/flipped relative to the input.
    """
    canvas = np.full((height, width, 3), (200, 200, 200), dtype=np.uint8)
    marker = min(width, height) // 6
    canvas[0:marker, 0:marker] = (0, 0, 220)  # red-ish marker, top-left, BGR
    ok, buf = cv2.imencode(".jpg", canvas)
    assert ok
    return buf.tobytes()


def test_auto_crop_accepts_card_aspect_ratio():
    image_bytes = _make_scan_bytes(card_w=125, card_h=175, canvas_size=400)
    result = auto_crop(image_bytes)
    assert result.aspect_ratio_ok is True
    # NOTE: _expanded_box() pads the detected rect by crop_padding_fraction
    # (a fixed fraction of the *longer* side) equally on width and height.
    # Adding equal absolute padding to two unequal sides always pulls the
    # ratio toward 1, so the measured aspect_ratio is expected to sit a bit
    # below the bare-card ideal of 1.4 -- this isn't measurement noise, it's
    # the intentional padding margin. At crop_padding_fraction=0.07 the
    # algebraic skew alone is ~4.7% low; rel=0.1 leaves headroom for that
    # plus normal contour/JPEG-quantization jitter while still catching a
    # real regression (production code treats anything outside
    # aspect_ratio_tolerance=0.15 as failing the check entirely).
    assert result.aspect_ratio == pytest.approx(3.5 / 2.5, rel=0.1)


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
# Originally this coverage depended on two real scanned photos of a physical
# laminated card checked in under tests/fixtures/. Those binary fixtures were
# never actually committed, which is what you're looking at if you found
# this comment via a CI failure about missing laminated_card-*.jpg files.
# Rather than depend on binary photo assets going forward, `_make_laminated_
# card_bytes()` below synthesizes the same failure signature in code: a
# near-black scan bed, a card-shaped region, a brighter inset "artwork"
# panel, and bright glare blobs sitting just outside the card's true edges
# (simulating sleeve reflection) -- no external files, nothing that can go
# missing.
#
# That signature previously caused two failure modes depending on tuning:
#   - close_kernel=(9,9) + an Otsu-thresholded mask candidate: Otsu isolated
#     only the brightest interior artwork panel, producing a tightly zoomed
#     crop that clipped real card content. Otsu was removed as a candidate
#     source entirely for this reason (see the NOTE in _candidate_contours),
#     so today that failure mode is guarded structurally rather than by a
#     numeric race between candidates -- see
#     test_auto_crop_candidate_contours_never_uses_otsu below.
#   - close_kernel=(21,21): the larger closing kernel bridged the glare
#     streaks into the card contour for every mask, producing an
#     under-cropped image with excess black background on all sides. This
#     one *is* reproduced numerically below (area_fraction climbs from
#     ~0.133 to ~0.172 with a 21x21 kernel against the same synthetic image),
#     so the area-band check keeps catching a regression here.
#
# Rather than pin exact pixel coordinates (brittle), the two tests below
# check scan-setup-independent invariants: (1) the front and back detections
# of the same physical card should agree closely, since it's the same
# rectangle on the same rig, and (2) the detected area should fall within a
# band wide enough for normal variation but narrow enough to catch an
# over-crop (kernel-bridging) or under-crop regression.
_LAMINATED_AREA_FRACTION_BOUNDS = (0.10, 0.16)


def _make_laminated_card_bytes(
    side: str,
    canvas_size: int = 1000,
    card_w: int = 260,
    card_h: int = 364,
    bg_val: int = 4,
    card_val: int = 70,
    art_val: int = 235,
    art_margin: int = 20,
    glare_gap: int = 25,
    glare_thickness: int = 18,
) -> bytes:
    """Synthetic reproduction of a laminated/sleeved card scan.

    Card dimensions keep the true 3.5:2.5 aspect ratio (260 * 1.4 == 364) and
    are sized so the *expanded* (padded) detection lands mid-band at
    ~0.133 -- comfortably inside _LAMINATED_AREA_FRACTION_BOUNDS for the
    current pipeline, while still failing it if the close kernel is widened
    enough to bridge the glare blobs into the card contour.
    """
    rng = np.random.default_rng(0)
    canvas = np.full((canvas_size, canvas_size, 3), bg_val, dtype=np.uint8)
    canvas += rng.integers(0, 3, canvas.shape, dtype=np.uint8)  # slight bed noise

    x0 = (canvas_size - card_w) // 2
    y0 = (canvas_size - card_h) // 2
    canvas[y0 : y0 + card_h, x0 : x0 + card_w] = card_val

    if side == "front":
        # photo-like artwork panel: brighter, inset
        ax0, ay0 = x0 + art_margin, y0 + art_margin
        ax1, ay1 = x0 + card_w - art_margin, y0 + card_h - art_margin
        canvas[ay0:ay1, ax0:ax1] = art_val
    else:
        # text-block back: slightly less bright, different inset than front
        m = art_margin + 15
        ax0, ay0 = x0 + m, y0 + m
        ax1, ay1 = x0 + card_w - m, y0 + card_h - m
        canvas[ay0:ay1, ax0:ax1] = art_val - 15

    # Glare blobs just outside the card's true edges, not touching it -- the
    # gap (25px) is calibrated to survive close_kernel=(9,9)/iterations=2 but
    # bridge into the card contour under a wider kernel like (21,21).
    glare_val = 250
    gx0, gx1 = x0 + 40, x0 + card_w - 40
    gy1 = y0 - glare_gap
    gy0 = gy1 - glare_thickness
    canvas[max(0, gy0) : max(0, gy1), gx0:gx1] = glare_val
    gy0b, gy1b = y0 + 60, y0 + card_h - 60
    gx1b = x0 - glare_gap
    gx0b = gx1b - glare_thickness
    canvas[gy0b:gy1b, max(0, gx0b) : max(0, gx1b)] = glare_val

    ok, buf = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert ok
    return buf.tobytes()


@pytest.mark.parametrize("side", ["front", "back"])
def test_auto_crop_laminated_card_area_within_expected_band(side):
    image_bytes = _make_laminated_card_bytes(side)
    with Image.open(BytesIO(image_bytes)) as img:
        image_area = img.width * img.height

    result = auto_crop(image_bytes)
    area_fraction = _polygon_area(result.bbox) / image_area

    low, high = _LAMINATED_AREA_FRACTION_BOUNDS
    assert low <= area_fraction <= high, (
        f"{side} crop covers {area_fraction:.3f} of the scan bed, expected "
        f"between {low} and {high}. Below this band usually means a bright "
        "interior panel was picked instead of the full card; above it "
        "usually means glare/background got merged into the card contour "
        "(e.g. too large a morphological close kernel)."
    )
    assert result.aspect_ratio_ok is True


def test_auto_crop_laminated_card_front_and_back_are_consistent():
    front_bytes = _make_laminated_card_bytes("front")
    back_bytes = _make_laminated_card_bytes("back")

    with Image.open(BytesIO(front_bytes)) as img:
        front_area = img.width * img.height
    with Image.open(BytesIO(back_bytes)) as img:
        back_area = img.width * img.height

    front = auto_crop(front_bytes)
    back = auto_crop(back_bytes)

    front_fraction = _polygon_area(front.bbox) / front_area
    back_fraction = _polygon_area(back.bbox) / back_area

    # Same physical card, same rig -> detected coverage should agree closely
    # even though the front (photo art) and back (text block) have
    # different content.
    relative_diff = abs(front_fraction - back_fraction) / max(
        front_fraction, back_fraction
    )
    assert relative_diff < 0.15, (
        f"front area fraction {front_fraction:.3f} vs back {back_fraction:.3f} "
        f"differ by {relative_diff:.1%}, expected close agreement for the "
        "same physical card"
    )


def test_auto_crop_candidate_contours_never_uses_otsu(monkeypatch):
    """Direct guard for the Otsu failure mode described above.

    Rather than relying on a synthetic image winning a numeric scoring race
    against Otsu (fragile, and no longer reproducible now that the
    relative-size penalty fix is also in place -- see _score_contour), this
    asserts the actual mechanism directly: cv2.threshold is never called
    with the THRESH_OTSU flag anywhere inside candidate generation. If
    someone reintroduces an Otsu candidate, this fails immediately and
    explicitly instead of depending on it also happening to out-score the
    other candidates on some particular image.
    """
    from app.vision import crop as crop_module

    calls: list[int] = []
    real_threshold = cv2.threshold

    def spy_threshold(src, thresh, maxval, type, **kwargs):  # noqa: A002
        calls.append(type)
        return real_threshold(src, thresh, maxval, type, **kwargs)

    monkeypatch.setattr(crop_module.cv2, "threshold", spy_threshold)

    image_bytes = _make_laminated_card_bytes("front")
    auto_crop(image_bytes)

    assert calls, "expected cv2.threshold to be called at all"
    assert not any(t & cv2.THRESH_OTSU for t in calls), (
        "cv2.threshold was called with THRESH_OTSU during candidate "
        "generation -- Otsu was intentionally removed as a candidate mask "
        "source (see the NOTE in _candidate_contours) because it isolates "
        "the brightest interior panel instead of the full card on "
        "laminated/sleeved scans"
    )


# --- Already-cropped input (e.g. a scanner that auto-crops on-device) ---
#
# Regression coverage for two bugs from the same root cause: contour
# detection was being run against images that never had a scan-bed
# background to begin with, which (a) failed the raw-scan aspect-ratio
# tolerance far too often, since the "crop" it found was just the frame
# itself with a margin that doesn't match a bare card, and (b) was liable to
# introduce a spurious rotation via an unstable minAreaRect angle on a
# near-full-frame contour, flipping images that were already upright.


def test_auto_crop_accepts_already_cropped_input_with_no_background():
    # Card fills the whole frame -- e.g. 750x1050 is the standard output
    # canvas size, no black scan-bed border anywhere.
    image_bytes = _make_precropped_bytes(750, 1050)
    result = auto_crop(image_bytes)
    assert result.aspect_ratio_ok is True
    assert result.orientation == "portrait"


def test_auto_crop_already_cropped_passthrough_does_not_rotate_or_resize():
    width, height = 908, 1103
    image_bytes = _make_precropped_bytes(width, height)
    result = auto_crop(image_bytes)
    decoded = cv2.imdecode(
        np.frombuffer(result.image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
    )

    # Same pixel dimensions as the input -- no perspective warp applied.
    assert decoded.shape[1] == width
    assert decoded.shape[0] == height

    # The top-left marker is still top-left: nothing got rotated or flipped.
    # Marker is BGR (0, 0, 220); background is gray (200, 200, 200) -- the
    # blue channel cleanly tells them apart.
    marker_region = decoded[0:20, 0:20]
    assert int(marker_region[:, :, 0].mean()) < 50  # marker: blue channel ~0
    opposite_corner = decoded[-20:, -20:]
    assert int(opposite_corner[:, :, 0].mean()) > 150  # background: blue channel ~200


def test_auto_crop_already_cropped_uses_widened_tolerance():
    # A toploader/sleeve margin (or a slightly loose device crop) commonly
    # pulls the measured ratio further from the bare-card ideal (1.4) than
    # our own contour-based crops would. This should still be accepted even
    # though it's well outside the raw-scan aspect_ratio_tolerance (0.15).
    image_bytes = _make_precropped_bytes(900, 1100)  # ratio ~1.222
    result = auto_crop(image_bytes)
    assert abs(result.aspect_ratio - 3.5 / 2.5) > 0.15  # would fail the strict tolerance
    assert result.aspect_ratio_ok is True


def test_auto_crop_already_cropped_still_flags_wildly_wrong_ratio():
    # Even on the passthrough path, something that isn't remotely
    # card-shaped should still be caught rather than silently accepted.
    image_bytes = _make_precropped_bytes(600, 600)  # square, ratio 1.0
    result = auto_crop(image_bytes)
    assert result.aspect_ratio_ok is False


def test_auto_crop_raw_scan_with_background_is_unaffected():
    # A real raw scan (card well inset from the frame edges, near-black
    # bed all around) must still go through normal contour detection, not
    # the already-cropped passthrough.
    image_bytes = _make_scan_bytes(card_w=250, card_h=350, canvas_size=400)
    result = auto_crop(image_bytes)
    decoded = cv2.imdecode(
        np.frombuffer(result.image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
    )
    # The passthrough path never resizes; the normal path always outputs
    # the fixed crop canvas size, so this confirms which path ran.
    assert (decoded.shape[1], decoded.shape[0]) in {(750, 1050), (1050, 750)}
    assert result.aspect_ratio_ok is True
