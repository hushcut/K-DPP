from io import BytesIO

from PIL import Image
import pytest

from apps.text import ocr_image, ocr_text


def make_image(size=(60, 80)):
    buffer = BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def mock_candidates(monkeypatch):
    calls = []
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_: object())
    monkeypatch.setattr(ocr_text, "preprocess_image_bytes", lambda _: b"basic")
    monkeypatch.setattr(
        ocr_text, "preprocess_reflection_image_bytes", lambda _: b"reflection"
    )
    monkeypatch.setattr(
        ocr_text, "preprocess_denoised_image_bytes", lambda _: b"denoised"
    )

    def fake_ocr(_client, content, **_kwargs):
        calls.append(content)
        return "COTTON 100%" if content == b"denoised" else "SIZE M"

    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_ocr)
    return calls


def test_denoised_candidate_recovers_after_reflection_failure(mock_candidates):
    result = ocr_text.run_ocr_bytes(
        make_image(), enable_reflection=True, enable_denoised=True
    )
    assert result.metadata.source == "denoised"
    assert result.metadata.external_call_count == 4
    assert mock_candidates[1:] == [b"basic", b"reflection", b"denoised"]
    assert "노이즈를 완화한 이미지의 OCR 결과를 사용했습니다." in result.metadata.warnings


def test_denoised_candidate_is_disabled_by_default(monkeypatch, mock_candidates):
    monkeypatch.delenv("KDPP_ENABLE_DENOISED_OCR", raising=False)
    ocr_text.run_ocr_bytes(make_image(), enable_reflection=False)
    assert len(mock_candidates) == 2


def test_denoised_candidate_can_be_enabled_without_reflection(monkeypatch, mock_candidates):
    monkeypatch.setenv("KDPP_ENABLE_DENOISED_OCR", "1")
    result = ocr_text.run_ocr_bytes(make_image(), enable_reflection=False)
    assert result.metadata.source == "denoised"
    assert mock_candidates[1:] == [b"basic", b"denoised"]


def test_successful_original_skips_denoised(monkeypatch, mock_candidates):
    monkeypatch.setattr(ocr_text, "_run_google_ocr", lambda *a, **kw: "COTTON 100%")
    monkeypatch.setattr(
        ocr_text, "preprocess_denoised_image_bytes",
        lambda _: pytest.fail("Successful original must not be replaced"),
    )
    result = ocr_text.run_ocr_bytes(make_image(), enable_denoised=True)
    assert result.metadata.source == "original"
    assert result.metadata.attempt_count == 1


def test_denoised_error_preserves_previous_candidates(monkeypatch, mock_candidates):
    def fail(_content):
        raise ocr_text.InvalidImageError("Invalid image")

    monkeypatch.setattr(ocr_text, "preprocess_denoised_image_bytes", fail)
    result = ocr_text.run_ocr_bytes(
        make_image(), enable_reflection=False, enable_denoised=True
    )
    assert result.text == "SIZE M"
    assert "denoised:InvalidImageError" in result.metadata.attempt_failures
    assert len(mock_candidates) == 2


def test_expired_budget_does_not_send_denoised_image(monkeypatch, mock_candidates):
    now = [0.0]
    monkeypatch.setattr(ocr_text.time, "monotonic", lambda: now[0])

    def slow_preprocess(_content):
        now[0] = 30.0
        return b"denoised"

    monkeypatch.setattr(ocr_text, "preprocess_denoised_image_bytes", slow_preprocess)
    result = ocr_text.run_ocr_bytes(
        make_image(), enable_reflection=False, enable_denoised=True
    )
    assert "denoised:total_timeout" in result.metadata.attempt_failures
    assert len(mock_candidates) == 2


def test_denoised_preprocess_preserves_aspect_and_pixel_limit(monkeypatch):
    monkeypatch.setattr(ocr_image, "MAX_PREPROCESSED_PIXELS", 4800)
    result = ocr_image.preprocess_denoised_image_bytes(make_image())
    with Image.open(BytesIO(result)) as image:
        assert image.format == "JPEG"
        assert image.size == (60, 80)
        assert image.width * image.height <= 4800


def test_denoised_preprocess_removes_isolated_texture(monkeypatch):
    monkeypatch.setattr(ocr_image, "MIN_OCR_WIDTH", 30)
    sample = Image.new("L", (30, 30), 240)
    sample.putpixel((15, 15), 0)
    buffer = BytesIO()
    sample.save(buffer, format="PNG")
    result = ocr_image.preprocess_denoised_image_bytes(buffer.getvalue())
    with Image.open(BytesIO(result)) as image:
        assert image.getpixel((15, 15)) > 200


def test_denoised_preprocess_rejects_invalid_image():
    with pytest.raises(ocr_text.InvalidImageError):
        ocr_image.preprocess_denoised_image_bytes(b"not an image")


def test_basic_preprocess_uses_compact_jpeg(monkeypatch):
    monkeypatch.setattr(ocr_image, "MIN_OCR_WIDTH", 60)
    result = ocr_image.preprocess_image_bytes(make_image())
    with Image.open(BytesIO(result)) as image:
        assert image.format == "JPEG"
        assert image.size == (60, 80)


@pytest.mark.parametrize("successful_source", [b"basic", b"reflection"])
def test_successful_previous_fallback_skips_denoised(
    monkeypatch, mock_candidates, successful_source
):
    def fake_ocr(_client, content, **_kwargs):
        return "COTTON 100%" if content == successful_source else "SIZE M"

    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_ocr)
    monkeypatch.setattr(
        ocr_text, "preprocess_denoised_image_bytes",
        lambda _: pytest.fail("Successful fallback must not be replaced"),
    )
    result = ocr_text.run_ocr_bytes(
        make_image(), enable_reflection=True, enable_denoised=True
    )
    assert result.metadata.source in {"preprocessed", "reflection"}
