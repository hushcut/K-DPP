import pytest

from apps.text.ocr_cache import OcrTextCache
from apps.text.ocr_text import OcrMetadata, OcrResult
from scripts import run_qa_batch
from scripts.run_qa_batch import (
    AnswerKeyError,
    analyze_label_image_cached,
    classify_failure,
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


def test_failure_categories_distinguish_parser_and_material_errors() -> None:
    parser_failure = classify_failure(
        result={"status": "failed", "error_code": "composition_not_found"},
        exception="",
        judgment="failed",
        failure_reason="no_predicted_materials",
    )
    material_failure = classify_failure(
        result={"status": "success"},
        exception="",
        judgment="failed",
        failure_reason="missing=polyester | extra=acrylic",
    )

    assert parser_failure == "composition_not_found"
    assert material_failure == "material_missing_and_extra"
    assert classify_failure(
        result={"status": "failed"},
        exception="",
        judgment="not_compared",
        failure_reason="answer_missing",
    ) == "not_compared"


def _write_answer_key(tmp_path, file_name: str) -> str:
    answer_key = tmp_path / "answer_key.csv"
    answer_key.write_text(
        "file_name,answer_materials,answer_ratios\n"
        f"{file_name},cotton,100\n",
        encoding="utf-8",
    )
    return str(answer_key)


def test_main_processes_answer_key_images_only_by_default(monkeypatch, tmp_path) -> None:
    matched_image = tmp_path / "QA001.jpg"
    unmatched_image = tmp_path / "OTHER.jpg"
    matched_image.write_bytes(b"matched")
    unmatched_image.write_bytes(b"unmatched")
    called_names: list[str] = []

    def fake_analyze(image_path, **_kwargs):
        called_names.append(image_path.name)
        return {
            "status": "success",
            "materials": {"cotton": 100},
            "confidence": {"ocr": "high", "parser": "high"},
            "ocr": {"source": "original"},
        }, True

    output_path = tmp_path / "results.csv"
    monkeypatch.setattr(run_qa_batch, "analyze_label_image_cached", fake_analyze)
    monkeypatch.setattr(
        run_qa_batch.sys,
        "argv",
        [
            "run_qa_batch.py",
            "--image-dir",
            str(tmp_path),
            "--answer-key",
            _write_answer_key(tmp_path, matched_image.name),
            "--output",
            str(output_path),
        ],
    )

    run_qa_batch.main()

    assert called_names == [matched_image.name]
    assert "QA001.jpg" in output_path.read_text(encoding="utf-8-sig")
    assert "OTHER.jpg" not in output_path.read_text(encoding="utf-8-sig")


def test_main_exits_nonzero_after_unexpected_image_exception(monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "QA001.jpg"
    image_path.write_bytes(b"matched")
    output_path = tmp_path / "results.csv"

    def broken_analyze(*_args, **_kwargs):
        raise RuntimeError("unexpected test failure")

    monkeypatch.setattr(run_qa_batch, "analyze_label_image_cached", broken_analyze)
    monkeypatch.setattr(
        run_qa_batch.sys,
        "argv",
        [
            "run_qa_batch.py",
            "--image-dir",
            str(tmp_path),
            "--answer-key",
            _write_answer_key(tmp_path, image_path.name),
            "--output",
            str(output_path),
        ],
    )

    with pytest.raises(SystemExit, match="예상 밖 예외가 1건"):
        run_qa_batch.main()

    assert output_path.is_file()


def test_main_rejects_duplicate_answer_key_file_names(monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "QA001.jpg"
    duplicate_dir = tmp_path / "nested"
    duplicate_dir.mkdir()
    image_path.write_bytes(b"first")
    (duplicate_dir / image_path.name).write_bytes(b"second")
    monkeypatch.setattr(
        run_qa_batch.sys,
        "argv",
        [
            "run_qa_batch.py",
            "--image-dir",
            str(tmp_path),
            "--answer-key",
            _write_answer_key(tmp_path, image_path.name),
        ],
    )

    with pytest.raises(AnswerKeyError, match="여러 경로"):
        run_qa_batch.main()
