"""대표 부위 선택과 OCR 후보 점수가 같은 우선순위를 유지하는지 검사한다."""

from itertools import combinations

import pytest

from apps.text.ocr_candidates import score_candidate
from apps.text.parse_label import choose_representative_materials
from apps.text.part_policy import PART_PRIORITY, part_rank


@pytest.mark.parametrize("higher,lower", list(combinations(PART_PRIORITY, 2)))
@pytest.mark.parametrize("reverse", [False, True])
def test_parser_and_candidate_score_agree_for_competing_parts(higher, lower, reverse):
    parts = [higher, lower] if not reverse else [lower, higher]
    materials = {"cotton": 100}
    selected, composition = choose_representative_materials(
        {part: dict(materials) for part in parts},
    )
    scores = {
        part: score_candidate(
            "COTTON 100%", materials, part, "success", "high", "original",
            ratio_total_before_normalization=100, warning_count=0,
        ) for part in parts
    }
    assert selected == max(scores, key=scores.get) == higher
    assert composition == materials


@pytest.mark.parametrize("part,rank", [
    ("outer", 8), ("outer_2", 7), ("generic", 6), ("color_block", 0),
    ("embroidery_yarn", -1), ("unknown", 0), ("", 0),
])
def test_candidate_part_rank_prioritizes_outer_and_keeps_unknown_default(part, rank):
    assert part_rank(part) == rank
