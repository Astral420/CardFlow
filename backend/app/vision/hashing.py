"""Structural hashing + color-signature computation (spec Section 6.4).

- Structural hash: pHash, computed at all 4 rotations for every stored card
  so a new card (hashed once, at its current rotation) can be matched
  against whichever stored rotation lines up.
- Color signature: region-sampled HSV histogram over the border/corner
  ring only, to catch color-only parallel differences that a whole-card
  average would wash out.
"""

import cv2
import imagehash
import numpy as np
from PIL import Image

ROTATIONS = (0, 90, 180, 270)
BORDER_FRACTION = 0.12


def decode_image(image_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def encode_jpeg(image: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise ValueError("Failed to encode image")
    return buf.tobytes()


def rotate_image(image: np.ndarray, degrees: int) -> np.ndarray:
    degrees = degrees % 360
    if degrees == 0:
        return image
    if degrees == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if degrees == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if degrees == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError(f"Unsupported rotation: {degrees}")


def structural_hash(image_bytes: bytes) -> str:
    bgr = decode_image(image_bytes)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return str(imagehash.phash(Image.fromarray(rgb)))


def hash_distance(hash_a: str, hash_b: str) -> int:
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)


def color_signature(image_bytes: bytes) -> list[float]:
    bgr = decode_image(image_bytes)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    h, w = hsv.shape[:2]
    border_h = max(1, int(h * BORDER_FRACTION))
    border_w = max(1, int(w * BORDER_FRACTION))

    mask = np.zeros((h, w), dtype=np.uint8)
    mask[:border_h, :] = 1
    mask[-border_h:, :] = 1
    mask[:, :border_w] = 1
    mask[:, -border_w:] = 1

    hist = cv2.calcHist([hsv], [0, 1], mask, [16, 8], [0, 180, 0, 256])
    cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    return hist.flatten().tolist()


def color_distance(sig_a: list[float], sig_b: list[float]) -> float:
    """Bhattacharyya distance between two color signatures (0 = identical)."""
    a = np.asarray(sig_a, dtype=np.float32)
    b = np.asarray(sig_b, dtype=np.float32)
    return float(cv2.compareHist(a, b, cv2.HISTCMP_BHATTACHARYYA))


def hash_and_color_at_all_rotations(
    image_bytes: bytes,
) -> dict[int, tuple[str, list[float]]]:
    base_image = decode_image(image_bytes)

    results: dict[int, tuple[str, list[float]]] = {}
    for degrees in ROTATIONS:
        rotated_bytes = encode_jpeg(rotate_image(base_image, degrees))
        results[degrees] = (
            structural_hash(rotated_bytes),
            color_signature(rotated_bytes),
        )
    return results
