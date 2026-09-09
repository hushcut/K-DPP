"""Integration QA runner tests that do not send images or call the API."""

from __future__ import annotations

import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from QA.run_qa_batch import classify_result, parse_api_materials


def test_api_materials_use_the_same_parser_aliases() -> None:
    assert parse_api_materials({"materials": {"면": 95, "elastane": 5}}) == {
        "cotton": 95.0,
        "spandex": 5.0,
    }


def test_api_result_emits_the_shared_failure_category() -> None:
    judgment, reason, category = classify_result(
        answer={"cotton": 80, "polyester": 20},
        actual={"cotton": 70, "acrylic": 30},
        status_code=200,
        error_message="",
        tolerance=3.0,
    )

    assert judgment == "소재 실패"
    assert "missing=polyester" in reason
    assert category == "material_missing_and_extra"
