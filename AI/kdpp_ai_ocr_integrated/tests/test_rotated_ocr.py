from io import BytesIO

from PIL import Image
import pytest

from apps.text import ocr_image, ocr_text


def image_bytes(size=(60, 80)):
    buffer = BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def candidates(monkeypatch):
    calls = []
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_: object())
    for name, content in (
        ("preprocess_image_bytes", b"basic"),
        ("preprocess_reflection_image_bytes", b"reflection"),
        ("preprocess_denoised_image_bytes", b"denoised"),
        ("preprocess_rotated_image_bytes", b"rotated"),
    ):
        monkeypatch.setattr(ocr_text, name, lambda _, value=content: value)

    def fake_ocr(_client, content, **kwargs):
        calls.append((content, kwargs.get("timeout_seconds")))
        return "RAYON 100%" if content == b"rotated" else "SIZE M"

    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_ocr)
    return calls


def test_rotated_candidate_is_opt_in(monkeypatch, candidates):
    monkeypatch.delenv("KDPP_ENABLE_ROTATED_OCR", raising=False)
    result = ocr_text.run_ocr_bytes(
        image_bytes(), enable_reflection=False, enable_denoised=False
    )
    assert result.metadata.attempt_count == 2
    assert len(candidates) == 2


def test_rotated_candidate_enabled_by_environment(monkeypatch, candidates):
    monkeypatch.setenv("KDPP_ENABLE_ROTATED_OCR", "1")
    result = ocr_text.run_ocr_bytes(
        image_bytes(), enable_reflection=False, enable_denoised=False
    )
    assert result.metadata.source == "rotated"
    assert [content for content, _ in candidates[1:]] == [b"basic", b"rotated"]
    assert candidates[-1][1] <= 5.0


def test_explicit_disable_overrides_environment(monkeypatch, candidates):
    monkeypatch.setenv("KDPP_ENABLE_ROTATED_OCR", "1")
    ocr_text.run_ocr_bytes(
        image_bytes(), enable_reflection=False, enable_denoised=False,
        enable_rotated=False,
    )
    assert len(candidates) == 2


def test_rotated_runs_after_previous_candidates_fail(candidates):
    result = ocr_text.run_ocr_bytes(
        image_bytes(), enable_reflection=True, enable_denoised=True,
        enable_rotated=True,
    )
    assert result.metadata.source == "rotated"
    assert result.metadata.attempt_count == 5
    assert [content for content, _ in candidates[1:]] == [
        b"basic", b"reflection", b"denoised", b"rotated"
    ]


@pytest.mark.parametrize("successful_source", ["original", "basic", "reflection", "denoised"])
def test_rotated_never_replaces_successful_previous_candidate(
    monkeypatch, candidates, successful_source
):
    original = image_bytes()
    success_content = original if successful_source == "original" else successful_source.encode()

    def fake_ocr(_client, content, **_kwargs):
        assert content != b"rotated"
        return "RAYON 100%" if content == success_content else "SIZE M"

    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_ocr)
    result = ocr_text.run_ocr_bytes(
        original, enable_reflection=True, enable_denoised=True,
        enable_rotated=True,
    )
    assert result.metadata.source != "rotated"


def test_rotated_timeout_does_not_send_another_request(monkeypatch, candidates):
    now = [0.0]
    monkeypatch.setattr(ocr_text.time, "monotonic", lambda: now[0])

    def slow_rotation(_content):
        now[0] = 26.0
        return b"rotated"

    monkeypatch.setattr(ocr_text, "preprocess_rotated_image_bytes", slow_rotation)
    result = ocr_text.run_ocr_bytes(
        image_bytes(), enable_reflection=False, enable_denoised=False,
        enable_rotated=True,
    )
    assert "rotated:total_timeout" in result.metadata.attempt_failures
    assert len(candidates) == 2


def test_rotation_failure_preserves_original(monkeypatch, candidates):
    def fail(_content):
        raise ocr_text.InvalidImageError("Invalid image")

    monkeypatch.setattr(ocr_text, "preprocess_rotated_image_bytes", fail)
    result = ocr_text.run_ocr_bytes(
        image_bytes(), enable_reflection=False, enable_denoised=False,
        enable_rotated=True,
    )
    assert result.text == "SIZE M"
    assert "rotated:InvalidImageError" in result.metadata.attempt_failures
    assert len(candidates) == 2


def test_rotation_expands_canvas_without_cutting_edges(monkeypatch):
    monkeypatch.setattr(ocr_image, "MIN_OCR_WIDTH", 60)
    result = ocr_image.preprocess_rotated_image_bytes(image_bytes())
    with Image.open(BytesIO(result)) as image:
        assert image.format == "JPEG"
        assert image.width > 60
        assert image.height > 80


@pytest.mark.parametrize("limit", ["MAX_PREPROCESSED_PIXELS", "MAX_PREPROCESSED_DIMENSION"])
def test_rotation_expansion_respects_image_limits(monkeypatch, limit):
    monkeypatch.setattr(ocr_image, limit, 4800 if limit.endswith("PIXELS") else 80)
    result = ocr_image.preprocess_rotated_image_bytes(image_bytes())
    with Image.open(BytesIO(result)) as image:
        assert image.width * image.height <= ocr_image.MAX_PREPROCESSED_PIXELS
        assert max(image.size) <= ocr_image.MAX_PREPROCESSED_DIMENSION


def test_rotation_rejects_invalid_images():
    with pytest.raises(ocr_text.InvalidImageError):
        ocr_image.preprocess_rotated_image_bytes(b"not an image")
