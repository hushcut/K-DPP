"""Restore only a registered colon heading without borrowing fiber evidence."""

import pytest

from apps.text.material_extraction import normalize_text
from apps.text.parse_label import parse_label


@pytest.mark.parametrize("heading", ["里 料", "裡 料", "里\t料"])
@pytest.mark.parametrize("prefix", ["", "面料:锦纶100% "])
def test_spaced_lining_heading_keeps_its_own_composition(heading, prefix):
    result = parse_label(prefix + heading + ":锦纶100%")
    assert result["status"] == "success"
    assert result["parts"]["lining"] == {"nylon": 100}
    if prefix:
        assert result["selected_part"] == "outer"
        assert result["parts"]["outer"] == {"nylon": 100}


@pytest.mark.parametrize("heading", ["里 料", "裡 料"])
@pytest.mark.parametrize("fiber", ["龍100%", "未知纤维100%", "锦纶95%", "锦纶100% 氨纶5%"])
def test_bad_lining_remains_rejected_without_contaminating_a_complete_outer(heading, fiber):
    result = parse_label(f"面料:锦纶100% {heading}:{fiber}")
    assert result["status"] == "success"
    assert result["parts"] == {"outer": {"nylon": 100}}
    assert "lining" in result["parse_evidence"]["rejected_composition_parts"]


def test_unknown_outer_cannot_be_replaced_by_a_restored_lining():
    result = parse_label("面料:未知纤维100% 里 料:锦纶100%")
    assert result["status"] == "failed"
    assert result["materials"] == {}


@pytest.mark.parametrize("text", [
    "非里 料:锦纶100%", "NOT 里 料:锦纶100%", "里\n料:锦纶100%",
    "里 UNKNOWN 料:锦纶100%", "里 料锦纶100%", "里 料 100%", "里 料?锦纶100%",
    "锦纶95 里 料:氨纶5%", "锦纶100% 里\n料:锦纶100%",
])
def test_unproven_or_negated_text_is_not_rewritten(text):
    assert normalize_text(text) == text.casefold()


def test_registered_filling_heading_does_not_invent_a_fiber_or_ratio():
    result = parse_label("面料:锦纶100%\n填充 物:UNKNOWN")
    assert result["parts"] == {"outer": {"nylon": 100}}
    assert "filling" in result["parse_evidence"]["rejected_composition_parts"]
