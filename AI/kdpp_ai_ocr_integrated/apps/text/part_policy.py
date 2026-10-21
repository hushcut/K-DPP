"""파서와 OCR 후보가 함께 사용하는 대표 부위 우선순위."""

OUTER_PARTS = ("outer", "outer_2")

PART_PRIORITY = [
    *OUTER_PARTS,
    "generic",
    "lining",
    "filling",
    "pocket",
    "rib",
    "sleeve",
    "color_block",
    "embroidery_yarn",
]


_PART_RANK = {part: len(PART_PRIORITY) - index - 2
              for index, part in enumerate(PART_PRIORITY)}


def part_rank(part: str) -> int:
    """기존 후보 점수 범위(8~-1)와 미등록 부위 기본값을 유지한다."""
    return _PART_RANK.get(part, 0)
