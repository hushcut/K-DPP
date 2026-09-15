import os
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from apps.text.ocr_cache import OcrCacheMissError, OcrTextCache
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


def test_reflection_preprocess_respects_output_pixel_limit(monkeypatch) -> None:
    monkeypatch.setattr(ocr_text, "MIN_OCR_WIDTH", 1800)
    monkeypatch.setattr(ocr_text, "MAX_PREPROCESSED_PIXELS", 120 * 80)

    result = ocr_text.preprocess_reflection_image_bytes(image_bytes())

    with Image.open(BytesIO(result)) as image:
        assert image.format == "JPEG"
        assert image.width * image.height <= ocr_text.MAX_PREPROCESSED_PIXELS


def test_explicit_credentials_do_not_mutate_environment(monkeypatch, tmp_path) -> None:
    environment_key = tmp_path / "environment-key.json"
    explicit_key = tmp_path / "explicit-key.json"
    environment_key.write_text("{}", encoding="utf-8")
    explicit_key.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(environment_key))

    resolved_path, _ = ocr_text._resolve_credential_path(str(explicit_key))

    assert resolved_path == str(explicit_key.resolve())
    assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == str(environment_key)


@pytest.mark.parametrize(
    ("status_code", "expected_exception"),
    [
        (7, ocr_text.OcrConfigurationError),
        (8, ocr_text.OcrQuotaExceededError),
        (4, ocr_text.OcrTimeoutError),
        (14, ocr_text.OcrUnavailableError),
    ],
)
def test_response_error_status_is_classified(
    status_code,
    expected_exception,
) -> None:
    response = SimpleNamespace(
        error=SimpleNamespace(code=status_code, message="provider error")
    )

    with pytest.raises(expected_exception):
        ocr_text._extract_response_text(response)


@pytest.mark.parametrize(
    ("provider_error", "expected_exception"),
    [
        ("forbidden", ocr_text.OcrConfigurationError),
        ("quota", ocr_text.OcrQuotaExceededError),
        ("timeout", ocr_text.OcrTimeoutError),
        ("unavailable", ocr_text.OcrUnavailableError),
    ],
)
def test_google_ocr_classifies_provider_exception(
    provider_error,
    expected_exception,
) -> None:
    from google.api_core import exceptions as google_exceptions

    errors = {
        "forbidden": google_exceptions.Forbidden("permission denied"),
        "quota": google_exceptions.ResourceExhausted("quota exceeded"),
        "timeout": google_exceptions.DeadlineExceeded("provider timeout"),
        "unavailable": google_exceptions.ServiceUnavailable("unavailable"),
    }

    class FailingClient:
        def document_text_detection(self, **_kwargs):
            raise errors[provider_error]

    with pytest.raises(expected_exception):
        ocr_text._run_google_ocr(FailingClient(), image_bytes())


def test_google_ocr_classifies_retry_deadline() -> None:
    from google.api_core import exceptions as google_exceptions

    class RetryDeadlineClient:
        def document_text_detection(self, **_kwargs):
            raise google_exceptions.RetryError(
                "retry deadline reached",
                google_exceptions.DeadlineExceeded("provider timeout"),
            )

    with pytest.raises(ocr_text.OcrTimeoutError):
        ocr_text._run_google_ocr(RetryDeadlineClient(), image_bytes())


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


def test_spatial_text_reassembles_material_and_ratio_rows() -> None:
    words = [
        ocr_text.OcrWord("겉감", 0, 0, 30, 12),
        ocr_text.OcrWord("레이온", 0, 20, 40, 32),
        ocr_text.OcrWord("100%", 80, 20, 120, 32),
        ocr_text.OcrWord("배색", 0, 40, 30, 52),
        ocr_text.OcrWord("면", 0, 60, 20, 72),
        ocr_text.OcrWord("95%", 80, 60, 120, 72),
        ocr_text.OcrWord("폴리우레탄", 0, 80, 60, 92),
        ocr_text.OcrWord("5%", 80, 80, 110, 92),
    ]

    assert ocr_text._spatial_text_from_words(words) == (
        "겉감\n레이온 100%\n배색\n면 95%\n폴리우레탄 5%"
    )


def test_spatial_layout_candidate_beats_flattened_column_order(monkeypatch) -> None:
    raw_text = "겉감\n레이온\n배색\n면\n100%\n폴리우레탄\n95%\n5%"
    layout_text = "겉감\n레이온 100%\n배색\n면 95%\n폴리우레탄 5%"
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_: object())
    monkeypatch.setattr(
        ocr_text,
        "_run_google_ocr",
        lambda _client, _content: ocr_text.OcrPayload(raw_text, layout_text),
    )

    result = ocr_text.run_ocr_bytes(image_bytes())

    assert result.text == layout_text
    assert result.metadata.source == "original"
    assert result.metadata.candidate_count == 1
    assert "OCR 좌표를 바탕으로 재구성한 줄 순서를 사용했습니다." in (
        result.metadata.warnings
    )


def test_outer_candidate_beats_more_complete_color_block_candidate(monkeypatch) -> None:
    raw_text = "겉감: 리오셀 100%"
    layout_text = "배색: 면 95% 폴리우레탄 5%"
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_: object())
    monkeypatch.setattr(
        ocr_text,
        "_run_google_ocr",
        lambda _client, _content: ocr_text.OcrPayload(raw_text, layout_text),
    )

    result = ocr_text.run_ocr_bytes(image_bytes())

    assert result.text == raw_text
    assert "OCR 좌표를 바탕으로 재구성한 줄 순서를 사용했습니다." not in (
        result.metadata.warnings
    )


def test_complete_multimaterial_candidate_beats_single_material_layout(monkeypatch) -> None:
    raw_text = "리오셀 70%\n나일론 30%"
    layout_text = "폴리에스터 100%"
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_: object())
    monkeypatch.setattr(
        ocr_text,
        "_run_google_ocr",
        lambda _client, _content: ocr_text.OcrPayload(raw_text, layout_text),
    )

    result = ocr_text.run_ocr_bytes(image_bytes())

    assert result.text == raw_text


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


def test_failed_standard_preprocess_tries_reflection_candidate(monkeypatch) -> None:
    calls: list[bytes] = []
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_: object())
    monkeypatch.setattr(
        ocr_text,
        "preprocess_image_bytes",
        lambda _content: b"standard-preprocessed",
    )
    monkeypatch.setattr(
        ocr_text,
        "preprocess_reflection_image_bytes",
        lambda _content: b"reflection-preprocessed",
    )

    def fake_ocr(_client, content: bytes) -> str:
        calls.append(content)
        return {
            b"standard-preprocessed": "BRAND AND SIZE ONLY",
            b"reflection-preprocessed": "COTTON 60% POLYESTER 40%",
        }.get(content, "BRAND AND SIZE ONLY")

    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_ocr)

    result = ocr_text.run_ocr_bytes(image_bytes())

    assert result.metadata.source == "reflection"
    assert result.metadata.candidate_count == 3
    assert result.text == "COTTON 60% POLYESTER 40%"
    assert len(calls) == 3
    assert "반사 보정된 이미지의 OCR 결과를 사용했습니다." in (
        result.metadata.warnings
    )


def test_successful_standard_preprocess_skips_reflection_candidate(monkeypatch) -> None:
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_: object())
    monkeypatch.setattr(
        ocr_text,
        "preprocess_reflection_image_bytes",
        lambda _content: pytest.fail("reflection candidate must be skipped"),
    )
    responses = iter(
        [
            "BRAND AND SIZE ONLY",
            "COTTON 80% POLYESTER 20%",
        ]
    )
    monkeypatch.setattr(
        ocr_text,
        "_run_google_ocr",
        lambda _client, _content: next(responses),
    )

    result = ocr_text.run_ocr_bytes(image_bytes())

    assert result.metadata.source == "preprocessed"
    assert result.metadata.candidate_count == 2


def test_reflection_ocr_failure_keeps_existing_candidates(monkeypatch) -> None:
    calls = 0
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_: object())
    monkeypatch.setattr(
        ocr_text,
        "preprocess_image_bytes",
        lambda _content: b"standard-preprocessed",
    )
    monkeypatch.setattr(
        ocr_text,
        "preprocess_reflection_image_bytes",
        lambda _content: b"reflection-preprocessed",
    )

    def fake_ocr(_client, _content: bytes) -> str:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise ocr_text.OcrTimeoutError("reflection timeout")
        return "BRAND AND SIZE ONLY"

    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_ocr)

    result = ocr_text.run_ocr_bytes(image_bytes())

    assert result.metadata.source == "original"
    assert result.metadata.candidate_count == 2
    assert "반사 보정 OCR에 실패하여 기존 후보를 유지했습니다." in (
        result.metadata.warnings
    )


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


def test_cached_original_avoids_second_paid_call(monkeypatch, tmp_path) -> None:
    cache = OcrTextCache(tmp_path / "qa_ocr_cache.json")
    calls = 0
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_: object())

    def fake_ocr(_client, _content: bytes) -> str:
        nonlocal calls
        calls += 1
        return "COTTON 100%"

    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_ocr)

    first = ocr_text.run_ocr_bytes(image_bytes(), ocr_cache=cache)
    second = ocr_text.run_ocr_bytes(
        image_bytes(),
        ocr_cache=cache,
        offline=True,
    )

    assert first.text == second.text == "COTTON 100%"
    assert calls == 1
    assert cache.write_count == 1
    assert cache.hit_count == 1


def test_cache_preserves_optional_spatial_layout(tmp_path) -> None:
    cache = OcrTextCache(tmp_path / "qa_ocr_cache.json")
    content = image_bytes()

    cache.put(content, "raw text", layout_text="spatial text")

    assert cache.get(content) == "raw text"
    assert cache.get_entry(content) == {
        "file_name": "",
        "source": "",
        "text": "raw text",
        "layout_text": "spatial text",
    }


def test_cached_candidates_are_rescored_without_api(monkeypatch, tmp_path) -> None:
    cache = OcrTextCache(tmp_path / "qa_ocr_cache.json")
    responses = iter(
        [
            "BRAND AND SIZE ONLY",
            "COTTON 80% POLYESTER 20%",
        ]
    )
    calls = 0
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_: object())

    def fake_ocr(_client, _content: bytes) -> str:
        nonlocal calls
        calls += 1
        return next(responses)

    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_ocr)

    first = ocr_text.run_ocr_bytes(image_bytes(), ocr_cache=cache)
    second = ocr_text.run_ocr_bytes(
        image_bytes(),
        ocr_cache=cache,
        offline=True,
    )

    assert first.metadata.source == "preprocessed"
    assert second.metadata.source == "preprocessed"
    assert second.text == "COTTON 80% POLYESTER 20%"
    assert calls == 2
    assert cache.write_count == 2
    assert cache.hit_count == 2


def test_offline_original_cache_miss_does_not_create_client(
    monkeypatch,
    tmp_path,
) -> None:
    cache = OcrTextCache(tmp_path / "qa_ocr_cache.json")

    def unexpected_client(*_args):
        raise AssertionError("offline mode must not create a Vision client")

    monkeypatch.setattr(ocr_text, "_get_vision_client", unexpected_client)

    with pytest.raises(OcrCacheMissError):
        ocr_text.run_ocr_bytes(
            image_bytes(),
            ocr_cache=cache,
            offline=True,
        )
