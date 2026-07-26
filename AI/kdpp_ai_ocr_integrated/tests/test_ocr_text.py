from io import BytesIO

import pytest
from PIL import Image

from apps.text import ocr_text


def image_bytes(
    image_format: str = "PNG",
    size: tuple[int, int] = (120, 80),
) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=image_format)
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


def test_validate_image_rejects_pixel_limit_boundary(monkeypatch) -> None:
    monkeypatch.setattr(ocr_text, "MAX_IMAGE_PIXELS", 120 * 80)

    with pytest.raises(ocr_text.ImageTooLargeError):
        ocr_text.validate_image_bytes(image_bytes())


def test_validate_image_rejects_extreme_aspect_ratio(monkeypatch) -> None:
    monkeypatch.setattr(ocr_text, "MAX_IMAGE_ASPECT_RATIO", 5.0)

    with pytest.raises(ocr_text.ImageTooLargeError):
        ocr_text.validate_image_bytes(image_bytes(size=(600, 20)))


def test_preprocess_image_respects_output_pixel_limit(monkeypatch) -> None:
    monkeypatch.setattr(ocr_text, "MIN_OCR_WIDTH", 1800)
    monkeypatch.setattr(ocr_text, "MAX_PREPROCESSED_PIXELS", 120 * 80)

    result = ocr_text.preprocess_image_bytes(image_bytes())

    with Image.open(BytesIO(result)) as image:
        assert image.width * image.height <= ocr_text.MAX_PREPROCESSED_PIXELS


def test_preprocess_image_respects_output_dimension_limit(monkeypatch) -> None:
    monkeypatch.setattr(ocr_text, "MIN_OCR_WIDTH", 1800)
    monkeypatch.setattr(ocr_text, "MAX_PREPROCESSED_DIMENSION", 100)

    result = ocr_text.preprocess_image_bytes(image_bytes())

    with Image.open(BytesIO(result)) as image:
        assert max(image.size) <= ocr_text.MAX_PREPROCESSED_DIMENSION


def test_preprocess_image_converts_memory_error(monkeypatch) -> None:
    def raise_memory_error(_image):
        raise MemoryError

    monkeypatch.setattr(ocr_text.ImageOps, "exif_transpose", raise_memory_error)

    with pytest.raises(ocr_text.ImageTooLargeError):
        ocr_text.preprocess_image_bytes(image_bytes())


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


def test_preprocess_failure_keeps_original_candidate(monkeypatch) -> None:
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_: object())
    monkeypatch.setattr(
        ocr_text,
        "_run_google_ocr",
        lambda _client, _content: "BRAND AND SIZE ONLY",
    )

    def fail_preprocess(_content: bytes) -> bytes:
        raise ocr_text.InvalidImageError("preprocess failed")

    monkeypatch.setattr(ocr_text, "preprocess_image_bytes", fail_preprocess)

    result = ocr_text.run_ocr_bytes(image_bytes())

    assert result.text == "BRAND AND SIZE ONLY"
    assert result.metadata.source == "original"
    assert result.metadata.candidate_count == 1
    assert "전처리 OCR에 실패하여 원본 OCR 결과를 유지했습니다." in (
        result.metadata.warnings
    )


def test_second_ocr_failure_keeps_original_candidate(monkeypatch) -> None:
    calls = 0
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_: object())
    monkeypatch.setattr(
        ocr_text,
        "preprocess_image_bytes",
        lambda _content: b"preprocessed",
    )

    def fake_ocr(_client, _content: bytes) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            return "BRAND AND SIZE ONLY"
        raise ocr_text.OcrServiceError("second OCR failed")

    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_ocr)

    result = ocr_text.run_ocr_bytes(image_bytes())

    assert result.text == "BRAND AND SIZE ONLY"
    assert result.metadata.source == "original"
    assert result.metadata.candidate_count == 1
    assert calls == 2
