import pytest

from apps.text.ocr_cache import OcrTextCache
from apps.text.ocr_text import OcrMetadata, OcrResult
from scripts import run_qa_batch
from scripts.run_qa_batch import (
    AnswerKeyError,
    analyze_label_image_cached,
    compare_materials,
    parse_answer_materials,
)


def test_answer_key_materials_and_ratios_must_align() -> None:
    with pytest.raises(AnswerKeyError):
        parse_answer_materials(
            {
                "answer_materials": "cotton;polyester",
                "answer_ratios": "100",
            },
            row_number=2,
        )


def test_answer_key_ratio_total_must_be_100() -> None:
    with pytest.raises(AnswerKeyError):
        parse_answer_materials(
            {
                "answer_materials": "cotton;polyester",
                "answer_ratios": "80;10",
            },
            row_number=2,
        )


def test_compare_materials_reports_missing_extra_and_ratio_errors() -> None:
    judgment, reason = compare_materials(
        {"cotton": 80, "polyester": 20},
        {"cotton": 70, "acrylic": 30},
        tolerance=2.0,
    )

    assert judgment == "failed"
    assert "missing=polyester" in reason
    assert "extra=acrylic" in reason
    assert "ratio_diff=cotton:-10.0" in reason


def test_cached_qa_calls_ocr_only_once(monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "QA001.jpg"
    image_path.write_bytes(b"image bytes")
    cache = OcrTextCache(tmp_path / "qa_ocr_cache.json")
    api_calls = 0

    def fake_ocr(
        _content,
        credential_path=None,
        *,
        ocr_cache=None,
        refresh_ocr_cache=False,
        offline=False,
        cache_label="",
    ):
        nonlocal api_calls
        if ocr_cache is not None and not refresh_ocr_cache:
            cached = ocr_cache.get(_content)
            if cached is not None:
                return OcrResult(
                    text=cached,
                    metadata=OcrMetadata(
                        source="original",
                        confidence="high",
                        candidate_count=1,
                        image_format="JPEG",
                        width=1200,
                        height=900,
                    ),
                )
        if offline:
            raise AssertionError("cache miss must not call OCR in offline mode")

        api_calls += 1
        result = OcrResult(
            text="COTTON 100%",
            metadata=OcrMetadata(
                source="original",
                confidence="high",
                candidate_count=1,
                image_format="JPEG",
                width=1200,
                height=900,
            ),
        )
        if ocr_cache is not None:
            ocr_cache.put(
                _content,
                result.text,
                file_name=cache_label,
                source="original",
            )
        return result

    monkeypatch.setattr(run_qa_batch, "run_ocr_bytes", fake_ocr)

    first, first_hit = analyze_label_image_cached(image_path, cache=cache)
    second, second_hit = analyze_label_image_cached(image_path, cache=cache)

    assert first["materials"] == {"cotton": 100}
    assert second["materials"] == {"cotton": 100}
    assert first_hit is False
    assert second_hit is True
    assert api_calls == 1

