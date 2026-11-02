"""가죽 부위는 혼용률 없이 종류만 표시한다는 2026-10-21 정책의 허용·거부 경계."""

import pytest

from apps.text.parse_label import parse_label


LINING = "\n안감 폴리에스터 100%"


@pytest.mark.parametrize("outer", [
    "겉감 가죽",
    "겉감 천연가죽(양가죽)",
    "겉감 천연 가죽 ( 양가죽 )",
    "겉감 소가죽",
    "겉감: 천연가죽",
    "SHELL LEATHER",
    "OUTER GENUINE LEATHER",
    "OUTER 천연가죽(양가죽)",
    "SHELL: REAL LEATHER (COW)",
])
def test_explicit_part_with_only_leather_is_leather(outer):
    result = parse_label(outer + LINING)
    assert result["status"] == "success", result
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"leather": 100}
    assert result["parts"]["lining"] == {"polyester": 100}
    assert "implicit_leather_composition:outer" in result["warnings"]
    assert result["confidence"]["parser"] == "medium"
    assert result["parse_evidence"]["source"] == "implicit_leather"


@pytest.mark.parametrize("outer", [
    "겉감 인조가죽",
    "겉감 합성피혁",
    "SHELL PU LEATHER",
    "SHELL FAUX LEATHER",
    "겉감 가죽 80%",
    "겉감 가죽 (양가죽) 10",
    "겉감 가죽 면",
    "겉감 가죽 UNKNOWN",
    "겉감 가죽 트리밍",
    "겉감 천연가죽 외 면",
    "겉감 천연",
    "겉감\n가죽",
    "겉감 천연가죽\n겉감 폴리에스터",
    "겉감 가죽\n겉감 면 100%",
])
def test_leather_is_not_assumed_with_other_words_numbers_or_substitutes(outer):
    result = parse_label(outer + LINING)
    assert not (result["status"] == "success" and "leather" in result["materials"]), result


def test_unlabelled_leather_row_does_not_become_the_representative_part():
    result = parse_label("가죽" + LINING)
    assert result["selected_part"] == "lining"
    assert "leather" not in result["materials"]
