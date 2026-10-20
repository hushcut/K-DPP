"""OCR 후보 근거를 확인하는 하위 계층 도우미.

``ocr_candidates``와 ``ocr_corrections``가 함께 쓰는 순수 판정 함수만 둔다.
두 모듈을 import하지 않으므로 둘 사이의 상호 import 없이 공유할 수 있다.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

from apps.text.composition_candidates import equivalent_composition
from apps.text.material_extraction import PART_PATTERNS, _material_evidence, normalize_text
from apps.text.rules import EQUIVALENT_MATERIALS

if TYPE_CHECKING:
    from apps.text.ocr_candidates import OcrCandidate


def literal_yarn_table_over_failed_layout(raw: OcrCandidate, layout: OcrCandidate) -> bool:
    """Keep a complete provider language table when row grouping breaks it.

    This is one response with identical complete annotations, not an extra
    OCR supporter. A different successful composition or any missing box is
    never discarded. Unreadable foreign clauses remain in the raw evidence.
    """
    if (raw.layout_used or not layout.layout_used or raw.parser_status != "success"
            or layout.parser_status != "failed" or layout.parts or layout.conflicting_parts
            or raw.selected_part != "embroidery_yarn"
            or "country_labelled_yarn_translations" not in raw.parser_warnings
            or not raw.image_key or not raw.image_variant_key or not raw.image_words
            or len(raw.image_region) != 4 or raw.source != layout.source
            or raw.image_key != layout.image_key or raw.image_variant_key != layout.image_variant_key
            or raw.image_words != layout.image_words or raw.image_region != layout.image_region
            or len({word.page for word in raw.image_words}) != 1):
        return False
    from apps.text.scoped_materials import confirmed_yarn_declaration
    from apps.text.ocr_geometry import _annotation_tokens, _covers_row_tokens

    declaration = confirmed_yarn_declaration(raw.text)
    if not declaration or len({item["language"] for item in declaration[1]["observations"]}) < 3:
        return False
    left, top, right, bottom = raw.image_region
    if any(not (left - 2 <= word.left and word.right <= right + 2
                and top - 2 <= word.top and word.bottom <= bottom + 2) for word in raw.image_words):
        return False
    return (Counter(_annotation_tokens(raw.text)) == Counter(_annotation_tokens(layout.text))
            and _covers_row_tokens(_annotation_tokens(raw.text), list(raw.image_words),
                                   tokenise=_annotation_tokens)
            and _covers_row_tokens(_annotation_tokens(layout.text), list(layout.image_words),
                                   tokenise=_annotation_tokens))


def _has_explicit_complete_pairs(
    candidate: OcrCandidate, *, allow_translation_warnings: bool = False,
) -> bool:
    """Every observed material and ratio must have a same-row explicit pair."""

    warnings = set(candidate.parser_warnings)
    if allow_translation_warnings:
        warnings -= {"registered_translation_alternatives", "damaged_translation_fragment",
                     "multilingual_translation_rows", "unread_translation_rows"}
    if (
        candidate.parser_status != "success" or warnings
        or candidate.conflicting_parts or candidate.unpaired_ratio_parts
        or candidate.rejected_composition_parts or not candidate.parts
        or candidate.observed_materials.keys() != candidate.parts.keys()
        or candidate.observed_ratios.keys() != candidate.parts.keys()
        or candidate.paired_material_ratios.keys() != candidate.parts.keys()
    ):
        return False
    from apps.text.parse_label import build_line_infos

    for info in build_line_infos(candidate.text):
        if not info.materials or info.is_metadata:
            continue
        if not info.explicit_percent:
            return False
        materials = _material_evidence(info.normalized)
        numbers = list(re.finditer(r"\d+(?:[.,]\d+)?\s*%", info.normalized))
        order = sorted(
            [(item.start, "material") for item in materials]
            + [(item.start(), "ratio") for item in numbers]
        )
        # A material column followed by its ratio column still guesses the
        # pairing, even when the parser records them on one reconstructed row.
        if (
            len(materials) != len(info.materials) or len(numbers) != len(info.numbers)
            or any(left[1] == right[1] for left, right in zip(order, order[1:]))
        ):
            return False
    for part, pairs in candidate.paired_material_ratios.items():
        if (
            Counter(material for material, _ratio in pairs) != Counter(candidate.observed_materials[part])
            or Counter(ratio for _material, ratio in pairs) != Counter(candidate.observed_ratios[part])
            or set((EQUIVALENT_MATERIALS.get(material, material), ratio) for material, ratio in pairs)
            != set(equivalent_composition(candidate.parts[part]))
        ):
            return False
    return True


def _is_plain_part_heading(text: str, part: str) -> bool:
    heading = normalize_text(text).strip(" :;()[]{}")
    return heading in {normalize_text(alias) for alias in PART_PATTERNS.get(part, [])}
