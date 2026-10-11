"""Parser regressions from privacy-reviewed excerpts of cached real-photo OCR.

The fixture covers 11 corrected photos, two safe rejections, one confirmed-part fallback, and one control.
Five identical PIMA OCR snippets share one case. Only composition evidence is
retained, so these tests measure parser behavior, not end-to-end Vision accuracy.
"""

import json
from pathlib import Path

import pytest

from apps.text.parse_label import parse_label


CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "real_ocr_composition_cases.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_real_ocr_composition_excerpt(case: dict) -> None:
    result = parse_label(case["ocr_excerpt"])

    assert result["status"] == case["status"]
    assert result["materials"] == case["materials"]
    if "selected_part" in case:
        assert result["selected_part"] == case["selected_part"]
    if "error_code" in case:
        assert result["error_code"] == case["error_code"]
    if case["id"] == "QA083":
        assert "outer" not in result["parts"]
        assert "outer:composition_not_confirmed" in result["warnings"]
        assert "representative_part_fallback:color_block" in result["warnings"]
