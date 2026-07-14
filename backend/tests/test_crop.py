import cv2
import numpy as np
import pytest
from PIL import Image
from app.vision.crop import auto_crop


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
