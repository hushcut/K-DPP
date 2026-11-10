"""Converted MPO pixels, OCR metadata and crop bounds share one coordinate frame."""

from io import BytesIO

import pytest
from PIL import Image

from apps.text.ocr_image import validate_image_bytes
from apps.text.ocr_errors import InvalidImageError
from apps.text.ocr_regions import prepare_material_region


def mpo_bytes(orientation):
    first = Image.new("RGB", (120, 80), "red")
    second = Image.new("RGB", (120, 80), "blue")
    exif = Image.Exif()
    exif[274] = orientation
    buffer = BytesIO()
    first.save(buffer, format="MPO", save_all=True, append_images=[second], exif=exif)
    return buffer.getvalue()


@pytest.mark.parametrize("orientation", range(1, 9))
def test_real_mpo_first_frame_dimensions_match_oriented_jpeg_pixels(orientation):
    content = mpo_bytes(orientation)
    with Image.open(BytesIO(content)) as original:
        assert original.format == "MPO" and original.n_frames == 2
        assert original.size == (120, 80)
    validated = validate_image_bytes(content, declared_content_type="image/mpo")
    with Image.open(BytesIO(validated.content)) as converted:
        expected = (80, 120) if orientation >= 5 else (120, 80)
        assert converted.format == "JPEG" and converted.mode == "RGB"
        assert converted.size == expected
        assert (validated.width, validated.height) == converted.size
        assert converted.getexif().get(274, 1) == 1
        red, _, blue = converted.getpixel((10, 10))
        assert red > 200 and blue < 20  # The first frame, rather than the blue second one.
    assert validated.image_format == "MPO"  # Preserve the input-format contract.


def test_crop_accepts_the_bottom_of_the_rotated_mpo_frame():
    upright = validate_image_bytes(mpo_bytes(6)).content
    result = prepare_material_region(upright, (10, 90, 70, 115), enhancement="original")
    assert result.region == (10., 90., 70., 115.)
    with Image.open(BytesIO(result.content)) as crop:
        width, height = crop.size
    a, b, c, d, e, f = result.transform
    assert (c, f) == pytest.approx((10, 90))
    assert (a * width + b * height + c, d * width + e * height + f) == pytest.approx((70, 115))


def test_crop_rejects_area_that_would_only_exist_before_mpo_rotation():
    upright = validate_image_bytes(mpo_bytes(6)).content
    with pytest.raises(InvalidImageError):
        prepare_material_region(upright, (90, 10, 115, 70), enhancement="original")


def test_ocr_metadata_matches_the_jpeg_pixels_sent_to_the_provider(monkeypatch):
    from apps.text import ocr_text

    dimensions = []
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_a, **_kw: object())
    def fake_ocr(_client, content, **_kwargs):
        with Image.open(BytesIO(content)) as image:
            assert image.format == "JPEG"
            dimensions.append(image.size)
        return ocr_text.OcrPayload(text="COTTON 100%")
    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_ocr)
    result = ocr_text.run_ocr_bytes(mpo_bytes(6))
    assert dimensions == [(80, 120)]
    assert (result.metadata.width, result.metadata.height) == dimensions[0]
    assert result.metadata.image_format == "MPO"
