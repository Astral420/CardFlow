"""Auto-crop pipeline (spec Section 6.2).

Detect the card/protector contour against a near-black scan background, expand
the detected rectangle slightly so dark card edges are not mistaken for
background, and perspective-warp while preserving portrait vs landscape
orientation. The aspect-ratio safety check still flags suspect detections
instead of silently corrupting downstream hashes.

Some intake sources hand us images that are already cropped tight to the
card (e.g. a scanner that auto-crops on-device) rather than a raw shot of
the whole scan bed. Those are detected up front, before contour detection
runs, and short-circuited to a passthrough path -- see
`_perimeter_background_fraction` / `_passthrough_crop` below.

That fast, perimeter-based check is a proxy (a real raw scan's outermost
pixels are almost all background), and proxies have blind spots: a
pre-cropped image whose card art itself runs dark right to the edge (e.g. a
black-bordered foil/chrome card) can read as enough "background" along its
border to miss the passthrough cutoff even though there's no actual scan
bed to find. Rather than loosen that cutoff -- real raw scans and this edge
case overlap in the same range, so a looser cutoff risks the opposite,
much worse failure of treating a genuine raw scan as pre-cropped and never
cropping it -- `auto_crop` also checks a second, independent signal after
contour detection runs: if the detected box still covers essentially the
whole frame, there was nothing to crop away regardless of what the
perimeter heuristic said. See `_full_frame_area_fraction` below.
"""

from dataclasses import dataclass
from io import BytesIO
from typing import cast

import cv2
import numpy as np
from PIL import Image, ImageOps

from app.config import settings


@dataclass
class CropResult:
    image_bytes: bytes
    bbox: list[list[float]]
    aspect_ratio: float
    aspect_ratio_ok: bool
    orientation: str
    # True when this image was judged to already be cropped tight to the
    # card -- either via the fast perimeter-background check up front, or
    # via the post-contour full-frame-area fallback below -- and therefore
    # graded against precropped_aspect_ratio_tolerance instead of
    # aspect_ratio_tolerance. Callers use this to label the scan `skipped`
    # (no crop transform was needed) instead of `cropped`.
    already_cropped: bool = False


def _order_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _clean_mask(mask: np.ndarray) -> np.ndarray:
    close_kernel = np.ones((9, 9), np.uint8)
    open_kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_kernel, iterations=1)
    return mask


def _perimeter_background_fraction(gray: np.ndarray, threshold: int) -> float:
    """Fraction of the image's own border pixels that read as scan background.

    A raw, uncropped scan sits on a near-black bed, so its outermost row/
    column of pixels is almost entirely background. An image that arrives
    already cropped (e.g. by the scanning device itself) has little to no
    such border left -- the card or its sleeve/toploader already runs to
    the frame edge on most or all sides. This ratio is the signal used to
    tell the two cases apart before deciding whether to run contour
    detection at all.
    """
    top = gray[0, :]
    bottom = gray[-1, :]
    left = gray[:, 0]
    right = gray[:, -1]
    perimeter = np.concatenate([top, bottom, left, right])
    return float(np.count_nonzero(perimeter <= threshold)) / perimeter.size


def _refine_warped_crop(warped: np.ndarray) -> np.ndarray:
    """Trim residual scan-bed / toploader border from a perspective-warped
    (or already-cropped/passthrough) image.

    Detection padding intentionally overshoots the card a bit -- see the
    crop_padding_fraction comment in app.config -- so the crop this
    function receives can still have thin bands of near-black scan bed (or,
    on the passthrough path, a toploader margin) on one or more edges. This
    scans inward from each edge to find where card content begins, trims to
    that inner rectangle, and returns it.

    Uses the median pixel value per row/column (robust to isolated bright
    glare pixels off a toploader/sleeve, unlike a mean) and caps trimming at
    a configurable fraction of each dimension so a pathological input (e.g.
    a mostly-black photo) can't eat into the card itself.
    """
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    threshold = settings.crop_refine_bg_threshold
    max_trim = settings.crop_refine_max_trim_fraction

    max_trim_v = int(h * max_trim)
    max_trim_h = int(w * max_trim)

    top = 0
    for row in range(max_trim_v):
        if np.median(gray[row, :].astype(float)) > threshold:
            break
        top = row + 1

    bottom = h
    for row in range(h - 1, h - 1 - max_trim_v, -1):
        if np.median(gray[row, :].astype(float)) > threshold:
            break
        bottom = row

    left = 0
    for col in range(max_trim_h):
        if np.median(gray[:, col].astype(float)) > threshold:
            break
        left = col + 1

    right = w
    for col in range(w - 1, w - 1 - max_trim_h, -1):
        if np.median(gray[:, col].astype(float)) > threshold:
            break
        right = col

    # Safety: if trimming would produce an invalid rect, return unchanged.
    if top >= bottom or left >= right:
        return warped

    return warped[top:bottom, left:right]


def _passthrough_crop(image: np.ndarray) -> CropResult:
    """Build a CropResult for input that's already cropped to the card.

    There's no background bed around it for us to find and remove, so
    there's nothing for contour detection + perspective warp to usefully
    do. Worse, minAreaRect's angle estimate is unstable on a contour that
    already spans (or nearly spans) the full frame -- exactly the
    already-cropped case -- so running it anyway risks introducing a
    spurious rotation/flip into an image that was already sitting upright.
    Pass the pixels through untouched (re-encoding only) and validate
    against a tolerance meant for input we didn't crop ourselves.

    Some already-cropped sources still leave a thin toploader/sleeve margin
    around the card -- refine (trim) that out first, before any of the
    below is computed, so the aspect ratio, orientation, bbox, and encoded
    output all agree on the same, final pixel dimensions rather than the
    aspect/orientation/bbox describing pre-trim geometry that no longer
    matches what's actually returned.
    """
    if settings.crop_refine_enabled:
        image = _refine_warped_crop(image)

    height, width = image.shape[:2]
    long_side = max(width, height)
    short_side = min(width, height)
    aspect_ratio = long_side / short_side if short_side > 0 else 0.0
    aspect_ratio_ok = (
        abs(aspect_ratio - settings.expected_card_aspect_ratio)
        <= settings.precropped_aspect_ratio_tolerance
    )
    orientation = "landscape" if width >= height else "portrait"

    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise ValueError("Failed to encode cropped image")

    bbox = [
        [0.0, 0.0],
        [float(width - 1), 0.0],
        [float(width - 1), float(height - 1)],
        [0.0, float(height - 1)],
    ]

    return CropResult(
        image_bytes=buf.tobytes(),
        bbox=bbox,
        aspect_ratio=aspect_ratio,
        aspect_ratio_ok=aspect_ratio_ok,
        orientation=orientation,
        already_cropped=True,
    )


def _full_frame_area_fraction(box: np.ndarray, image_shape: tuple[int, ...]) -> float:
    """Fraction of the total image area the (already padding-expanded,
    clipped) detected box covers.

    Contour detection always returns *some* box -- on a genuine raw scan
    that's a small fraction of the frame (the card, plus padding). If it
    instead covers essentially the entire frame, contour detection found no
    real scan-bed background to separate from the card, which happens on
    already-cropped input that slipped past the perimeter pre-check (e.g. a
    dark-bordered card pushing enough near-black pixels onto its own edge).
    That's independent evidence of the same "nothing to crop" condition the
    perimeter check looks for, just observed after the fact instead of
    before.
    """
    image_area = image_shape[0] * image_shape[1]
    if image_area <= 0:
        return 0.0
    # Shoelace formula over the (already ordered) box points.
    x = box[:, 0]
    y = box[:, 1]
    box_area = 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
    return float(box_area / image_area)


def _candidate_contours(gray: np.ndarray) -> list[np.ndarray]:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    _, non_background = cv2.threshold(
        blurred,
        settings.scan_background_threshold,
        255,
        cv2.THRESH_BINARY,
    )

    edges = cv2.Canny(blurred, 30, 100)
    edge_kernel = np.ones((5, 5), np.uint8)
    edges = cv2.dilate(edges, edge_kernel, iterations=1)

    # NOTE: an Otsu-thresholded mask used to be included here as a third
    # candidate source. It has been removed. Otsu picks a single global
    # split point from the image's own brightness histogram, which assumes
    # the frame is roughly bimodal (object vs. background). Laminated/
    # protector-sleeve scans on a near-black bed are not: they contain the
    # background, the card border, the (often much brighter) printed
    # artwork, and glare streaks off the sleeve, i.e. several brightness
    # clusters. Otsu has no notion of "near-black scan background" and will
    # happily draw its line between the artwork and everything else,
    # isolating only the brightest interior panel as "foreground." That
    # panel is a real, clean, solidly-shaped contour, so nothing downstream
    # flags it as wrong -- it just happens to describe the art box, not the
    # card. `non_background` (threshold against settings.scan_background_
    # threshold) and its edge-augmented variant are both anchored to the
    # actual near-black bed, which is the correct invariant for this rig.
    masks = [
        _clean_mask(non_background),
        _clean_mask(cv2.bitwise_or(non_background, edges)),
    ]

    contours: list[np.ndarray] = []
    for mask in masks:
        found, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours.extend(found)
    return contours


def _score_contour(
    contour: np.ndarray, image_area: int, max_candidate_area: int
) -> tuple[float, float]:
    rect = cv2.minAreaRect(contour)
    (_, (rect_w, rect_h), _) = rect
    if rect_w <= 0 or rect_h <= 0:
        return (float("inf"), 0.0)

    long_side = max(rect_w, rect_h)
    short_side = min(rect_w, rect_h)
    aspect_ratio = long_side / short_side if short_side > 0 else 0.0
    contour_area = cv2.contourArea(contour)
    area_ratio = contour_area / max(1, image_area)
    aspect_error = abs(aspect_ratio - settings.expected_card_aspect_ratio)

    # Relative-size penalty, scored against the largest candidate in *this*
    # image rather than a flat fraction of the whole scan bed. A flat
    # area_ratio bonus (e.g. "+0.25 per 100% of image area") is calibrated
    # to one particular camera distance/bed size; tighten the zoom or crop
    # the scan bed differently and the same bonus stops being big enough to
    # out-vote a small-but-conveniently-card-shaped interior panel (this is
    # what let the Otsu art-box contour win before). Comparing against the
    # largest candidate actually found in this frame keeps the penalty
    # meaningful regardless of scan setup: a contour at 20% of the biggest
    # candidate's area is suspect no matter how big the image is.
    relative_size = contour_area / max(1, max_candidate_area)
    size_penalty = (1 - relative_size) * 0.5

    return (aspect_error + size_penalty, area_ratio)


def _best_contour(contours: list[np.ndarray], image_shape: tuple[int, ...]) -> np.ndarray:
    image_area = image_shape[0] * image_shape[1]
    min_area = image_area * 0.005
    candidates = [c for c in contours if cv2.contourArea(c) >= min_area]
    if not candidates:
        raise ValueError("No contours found against the scan background")

    max_candidate_area = max(cv2.contourArea(c) for c in candidates)
    return min(
        candidates,
        key=lambda c: _score_contour(c, image_area, int(max_candidate_area)),
    )


def _expanded_box(rect: tuple, image_shape: tuple[int, ...]) -> np.ndarray:
    center, size, angle = rect
    rect_w, rect_h = size
    padding = max(
        settings.crop_padding_min_pixels,
        max(rect_w, rect_h) * settings.crop_padding_fraction,
    )
    expanded = (
        center,
        (rect_w + padding * 2, rect_h + padding * 2),
        angle,
    )
    box = cv2.boxPoints(expanded)
    max_x = image_shape[1] - 1
    max_y = image_shape[0] - 1
    box[:, 0] = np.clip(box[:, 0], 0, max_x)
    box[:, 1] = np.clip(box[:, 1], 0, max_y)
    return box


def _side_lengths(ordered: np.ndarray) -> tuple[float, float]:
    width_a = float(np.linalg.norm(ordered[2] - ordered[3]))
    width_b = float(np.linalg.norm(ordered[1] - ordered[0]))
    height_a = float(np.linalg.norm(ordered[1] - ordered[2]))
    height_b = float(np.linalg.norm(ordered[0] - ordered[3]))
    return max(width_a, width_b), max(height_a, height_b)


def _decode_image_with_display_orientation(image_bytes: bytes) -> np.ndarray:
    """Decode image bytes with EXIF orientation applied.

    A lot of phone/scanner JPEGs store portrait photos as landscape pixel data
    plus an EXIF orientation tag. OpenCV's decoder is not a reliable contract
    for that across versions, so normalize explicitly before contour detection.
    """
    with Image.open(BytesIO(image_bytes)) as pil_image:
        pil_image = ImageOps.exif_transpose(pil_image).convert("RGB")  # type: ignore[union-attr]
        rgb = np.asarray(pil_image)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def auto_crop(image_bytes: bytes) -> CropResult:
    try:
        image = _decode_image_with_display_orientation(image_bytes)
    except Exception:
        raise ValueError("Could not decode image")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    bg_fraction = _perimeter_background_fraction(
        gray, settings.scan_background_threshold
    )
    if bg_fraction <= settings.precropped_perimeter_bg_max_fraction:
        return _passthrough_crop(image)

    contours = _candidate_contours(gray)
    contour = _best_contour(contours, image.shape)
    rect = cv2.minAreaRect(contour)
    box = _expanded_box(rect, image.shape)

    # Fallback already-cropped signal (see _full_frame_area_fraction):
    # contour detection ran but found essentially the whole frame, meaning
    # there was no real scan-bed background to separate from the card in
    # the first place -- the same underlying condition the perimeter
    # pre-check above is trying to catch, just missed by that heuristic
    # (e.g. a dark-bordered card inflating the perimeter's own background
    # count). Defer to the same passthrough path used for that case rather
    # than trusting this box's perspective warp: minAreaRect's angle is
    # unstable on a near-full-frame contour for exactly the same reason
    # _passthrough_crop's docstring gives for skipping contour detection on
    # already-cropped input entirely -- running it anyway risks introducing
    # a spurious rotation/flip into an image that was already upright.
    if (
        _full_frame_area_fraction(box, image.shape)
        >= settings.contour_full_frame_area_fraction
    ):
        return _passthrough_crop(image)

    ordered = _order_points(box)
    source_w, source_h = _side_lengths(ordered)

    long_side = max(source_w, source_h)
    short_side = min(source_w, source_h)
    aspect_ratio = long_side / short_side if short_side > 0 else 0.0
    aspect_ratio_ok = (
        abs(aspect_ratio - settings.expected_card_aspect_ratio)
        <= settings.aspect_ratio_tolerance
    )
    orientation = "landscape" if source_w >= source_h else "portrait"

    short_out = min(settings.crop_output_width, settings.crop_output_height)
    long_out = max(settings.crop_output_width, settings.crop_output_height)
    if orientation == "landscape":
        out_w, out_h = long_out, short_out
    else:
        out_w, out_h = short_out, long_out

    dst = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(ordered, dst)
    warped = cv2.warpPerspective(image, matrix, (out_w, out_h))

    # Trim residual scan-bed border left by the detection padding above,
    # then rescale back to the fixed output canvas size -- aspect_ratio/
    # orientation/bbox below describe the *pre*-trim detected rectangle
    # (that's the actual detection result being validated), so this only
    # needs to affect the encoded pixels, not those fields.
    if settings.crop_refine_enabled:
        trimmed = _refine_warped_crop(warped)
        if trimmed.shape[:2] != (out_h, out_w):
            warped = cv2.resize(trimmed, (out_w, out_h), interpolation=cv2.INTER_AREA)
        else:
            warped = trimmed

    ok, buf = cv2.imencode(".jpg", warped, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise ValueError("Failed to encode cropped image")

    return CropResult(
        image_bytes=buf.tobytes(),
        bbox=cast(list, ordered.tolist()),
        aspect_ratio=aspect_ratio,
        aspect_ratio_ok=aspect_ratio_ok,
        orientation=orientation,
    )
