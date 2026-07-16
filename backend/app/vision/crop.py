"""Auto-crop pipeline (spec Section 6.2).

Detect the card/protector contour against a near-black scan background, expand
the detected rectangle slightly so dark card edges are not mistaken for
background, and perspective-warp while preserving portrait vs landscape
orientation. The aspect-ratio safety check still flags suspect detections
instead of silently corrupting downstream hashes.
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
    close_kernel = np.ones((21, 21), np.uint8)
    open_kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_kernel, iterations=1)
    return mask


def _candidate_contours(gray: np.ndarray) -> list[np.ndarray]:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    _, otsu = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    _, non_background = cv2.threshold(
        blurred,
        settings.scan_background_threshold,
        255,
        cv2.THRESH_BINARY,
    )

    edges = cv2.Canny(blurred, 30, 100)
    edge_kernel = np.ones((5, 5), np.uint8)
    edges = cv2.dilate(edges, edge_kernel, iterations=1)

    masks = [
        _clean_mask(otsu),
        _clean_mask(non_background),
        _clean_mask(cv2.bitwise_or(non_background, edges)),
    ]

    contours: list[np.ndarray] = []
    for mask in masks:
        found, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours.extend(found)
    return contours


def _score_contour(contour: np.ndarray, image_area: int) -> tuple[float, float]:
    rect = cv2.minAreaRect(contour)
    (_, (rect_w, rect_h), _) = rect
    if rect_w <= 0 or rect_h <= 0:
        return (float("inf"), 0.0)

    long_side = max(rect_w, rect_h)
    short_side = min(rect_w, rect_h)
    aspect_ratio = long_side / short_side if short_side > 0 else 0.0
    area_ratio = cv2.contourArea(contour) / max(1, image_area)
    aspect_error = abs(aspect_ratio - settings.expected_card_aspect_ratio)

    # Prefer card-shaped contours, with area as a tie-breaker. Keeping area in
    # the score prevents a bright interior panel from beating the full dark edge
    # or protector contour when both are present.
    return (aspect_error - min(area_ratio, 0.95) * 0.25, area_ratio)


def _best_contour(contours: list[np.ndarray], image_shape: tuple[int, ...]) -> np.ndarray:
    image_area = int(image_shape[0] * image_shape[1])
    min_area = image_area * 0.005
    candidates = [c for c in contours if cv2.contourArea(c) >= min_area]
    if not candidates:
        raise ValueError("No contours found against the scan background")

    return min(candidates, key=lambda c: _score_contour(c, image_area))


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
    contours = _candidate_contours(gray)
    contour = _best_contour(contours, image.shape)
    rect = cv2.minAreaRect(contour)
    box = _expanded_box(rect, image.shape)

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
