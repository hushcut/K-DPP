from io import BytesIO

import pytest
from PIL import Image

from apps.text import ocr_text


def image_bytes(image_format: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (120, 80), "white").save(buffer, format=image_format)
    return buffer.getvalue()


def test_validate_image_accepts_png() -> None:
    result = ocr_text.validate_image_bytes(
        image_bytes(),
        declared_content_type="image/png",
    )

    assert result.image_format == "PNG"
    assert (result.width, result.height) == (120, 80)


def test_validate_image_rejects_empty_content() -> None:
    with pytest.raises(ocr_text.InvalidImageError):
        ocr_text.validate_image_bytes(b"")


def test_validate_image_rejects_unsupported_format() -> None:
    with pytest.raises(ocr_text.UnsupportedImageError):
        ocr_text.validate_image_bytes(image_bytes("GIF"))


def test_validate_image_rejects_declared_content_type() -> None:
    with pytest.raises(ocr_text.UnsupportedImageError):
        ocr_text.validate_image_bytes(
            image_bytes(),
            declared_content_type="image/gif",
        )


def test_validate_image_enforces_byte_limit(monkeypatch) -> None:
    monkeypatch.setattr(ocr_text, "MAX_IMAGE_BYTES", 10)

    with pytest.raises(ocr_text.ImageTooLargeError):
        ocr_text.validate_image_bytes(image_bytes())


def test_high_confidence_original_uses_one_paid_ocr_call(monkeypatch) -> None:
    calls: list[bytes] = []
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_: object())

    def fake_ocr(_client, content: bytes) -> str:
        calls.append(content)
        return "COTTON 80% POLYESTER 20%"

    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_ocr)
    result = ocr_text.run_ocr_bytes(image_bytes())

    assert result.metadata.source == "original"
    assert result.metadata.candidate_count == 1
    assert len(calls) == 1


def test_low_confidence_original_tries_preprocessed_candidate(monkeypatch) -> None:
    responses = iter(
        [
            "BRAND AND SIZE ONLY",
            "COTTON 80% POLYESTER 20%",
        ]
    )
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_: object())
    monkeypatch.setattr(
        ocr_text,
        "_run_google_ocr",
        lambda _client, _content: next(responses),
    )

    result = ocr_text.run_ocr_bytes(image_bytes())

    assert result.metadata.source == "preprocessed"
    assert result.metadata.candidate_count == 2
    assert result.text == "COTTON 80% POLYESTER 20%"

