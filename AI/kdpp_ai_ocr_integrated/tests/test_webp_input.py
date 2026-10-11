"""Keep the backend's existing WebP upload contract through the OCR boundary."""

from io import BytesIO

from PIL import Image

from apps.service.label_analysis import analyze_ocr_result
from apps.text import ocr_text


def webp_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (120, 80), "white").save(buffer, format="WEBP", lossless=True)
    return buffer.getvalue()


def test_webp_upload_passes_image_validation() -> None:
    content = webp_bytes()
    validated = ocr_text.validate_image_bytes(content, declared_content_type="image/webp")

    assert validated.content == content
    assert validated.image_format == "WEBP"
    assert (validated.width, validated.height) == (120, 80)
    candidate = ocr_text.preprocess_image_bytes(content)
    assert candidate is not None
    with Image.open(BytesIO(candidate)) as prepared:
        assert prepared.format == "JPEG"


def test_webp_reaches_the_shared_analysis_pipeline(monkeypatch) -> None:
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_args: object())
    calls = []

    def fake_vision(_client, content, **_kwargs):
        calls.append(content)
        return "COTTON 100%"

    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_vision)
    content = webp_bytes()
    result = analyze_ocr_result(
        ocr_text.run_ocr_bytes(content, declared_content_type="image/webp")
    )

    assert calls == [content]
    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 100}
    assert result["parse_evidence"]["composition_status"] == "confirmed"
    assert result["ocr"]["image_format"] == "WEBP"
