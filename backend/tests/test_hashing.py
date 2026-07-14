import cv2
import numpy as np
import pytest
from app.vision.hashing import (
    color_distance,
    color_signature,
    hash_and_color_at_all_rotations,
    hash_distance,
    rotate_image,
    structural_hash,
)


def _encode(image: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", image)
    assert ok
    return buf.tobytes()


def _sample_card() -> np.ndarray:
    image = np.full((350, 250, 3), (30, 30, 30), dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (230, 330), (0, 140, 220), thickness=-1)
    cv2.circle(image, (125, 175), 50, (200, 50, 50), thickness=-1)
    return image


def test_structural_hash_is_stable_for_identical_images():
    image_bytes = _encode(_sample_card())
    assert structural_hash(image_bytes) == structural_hash(image_bytes)


def test_hash_distance_zero_for_identical_hash():
    image_bytes = _encode(_sample_card())
    h = structural_hash(image_bytes)
    assert hash_distance(h, h) == 0


def test_rotation_invariant_index_recovers_rotated_query():
    card = _sample_card()
    original_bytes = _encode(card)
    rotated_bytes = _encode(rotate_image(card, 180))

    index = hash_and_color_at_all_rotations(original_bytes)
    query_hash = structural_hash(rotated_bytes)

    # The stored 180-degree entry should closely match a query hashed from
    # the same card scanned/confirmed at 180 degrees.
    assert hash_distance(query_hash, index[180][0]) <= 4


def test_color_distance_zero_for_identical_signature():
    image_bytes = _encode(_sample_card())
    sig = color_signature(image_bytes)
    assert color_distance(sig, sig) == pytest.approx(0.0, abs=1e-6)


def test_color_distance_higher_for_different_cards():
    card_a = _sample_card()
    card_b = np.full((350, 250, 3), (30, 30, 30), dtype=np.uint8)
    cv2.rectangle(card_b, (20, 20), (230, 330), (60, 200, 60), thickness=-1)

    sig_a = color_signature(_encode(card_a))
    sig_b = color_signature(_encode(card_b))

    assert color_distance(sig_a, sig_b) > color_distance(sig_a, sig_a)
