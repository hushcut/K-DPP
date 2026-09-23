import re
from dataclasses import replace

from apps.text.composition_candidates import (
    EXACT_RATIO_TOLERANCE,
    CompositionCandidate,
    LineInfo,
    _collect_candidates,
)

from apps.text.material_extraction import (
    PART_PATTERNS,
    _strip_excluded_segments,
    _TOKEN_PATTERN,
    clean_ocr_preview,
    declared_part,
    extract_materials,
    normalize_text,
    unresolved_material_tokens,
)
from apps.text.rules import (
    CARE_CONFLICTS,
    CARE_RULES,
    EQUIVALENT_MATERIALS,
    MATERIAL_KOREAN,
)


PART_PRIORITY = [
    "outer",
    "generic",
    "lining",
    "filling",
    "pocket",
    "rib",
    "sleeve",
    "color_block",
]

NON_COMPOSITION_WORDS = {
    "제품명",
    "제조년월",
    "제조국",
    "수입자",
    "판매자",
    "품번",
    "호칭",
    "신체치수",
    "가슴둘레",
    "허리둘레",
    "검사필",
    "产品名称",
    "產品名稱",
    "货号",
    "貨號",
    "型号",
    "型號",
    "尺码",
    "尺碼",
    "生产日期",
    "生產日期",
    "製造年月",
    "製造国",
    "製造國",
    "品番",
    "サイズ",
}

# Marketing copy can contain a material name and a percentage-like decoration
# without declaring fiber content. Treat these phrases as non-composition so
# a false positive is not returned as a confirmed material ratio.
DESCRIPTIVE_MATERIAL_PHRASES = {
    "silk touch",
    "cotton feel",
    "polyester look",
    "wool like",
    "wool-like",
}

COMPOSITION_HINTS = {
    "섬유의 조성",
    "혼용률",
    "혼용율",
    "소재",
    "composition",
    "fabric content",
    "material",
    "materials",
    "fiber content",
    "纤维成分",
    "纖維成分",
    "面料成分",
    "材质",
    "材質",
    "組成表示",
    "混用率",
    "品質表示",
}

_PERCENT_PATTERN = re.compile(
    r"(?<![a-z0-9])([0-9]{1,3}(?:\.[0-9]+)?)\s*[%％]",
    re.IGNORECASE,
)
_PLAIN_NUMBER_PATTERN = re.compile(
    r"(?<![a-z0-9])([0-9]{1,3}(?:\.[0-9]+)?)(?![a-z0-9])",
    re.IGNORECASE,
)
# A wash temperature carries no percent marker, so it would otherwise be free
# to complete a partial composition (``COTTON 70% SPANDEX 30°C``).
_TEMPERATURE_PATTERN = re.compile(
    r"(?<![a-z0-9])[0-9]{1,3}(?:\.[0-9]+)?\s*(?:°c|°f|도(?![가-힣]))",
    re.IGNORECASE,
)


_CARE_PHRASES = tuple(
    {alias.casefold() for aliases in CARE_RULES.values() for alias in aliases}
)
# Number safety needs broader context than the phrases used to display care
# instructions. These words alone do not imply a specific care recommendation.
_CARE_CONTEXT_PATTERN = re.compile(
    r"(?<![a-z])(?:wash(?:ing)?|rinse|bleach(?:ing)?|iron(?:ing)?|dry(?:ing)?)(?![a-z])"
    r"|세탁|표백|다림질|건조|드라이"
    r"|水洗|洗涤|洗滌|漂白|熨|烘|干洗|乾洗"
    r"|洗濯|手洗|アイロン|乾燥|ドライ"
)


def _mentions_care(line: str) -> bool:
    """Whether a row also carries care text, whose numbers are not ratios."""

    return bool(_CARE_CONTEXT_PATTERN.search(line)) or any(
        phrase in line for phrase in _CARE_PHRASES
    )


def _mask_temperatures(line: str) -> str:
    """Blank temperature values, keeping every other offset unchanged."""

    return _TEMPERATURE_PATTERN.sub(lambda match: " " * len(match.group(0)), line)


def _looks_like_non_composition_number(line: str) -> bool:
    if any(word in line for word in NON_COMPOSITION_WORDS):
        return True
    if any(phrase in line for phrase in DESCRIPTIVE_MATERIAL_PHRASES):
        return True
    if re.search(r"\b(?:19|20)\d{2}\b", line):
        return True
    if re.search(r"\d+(?:\.\d+)?\s*(?:cm|mm|kg|g|호|년|월|일)\b", line):
        return True
    return False


def _is_metadata_line(info: LineInfo) -> bool:
    """Whether an OCR row is safe to skip while pairing composition rows."""

    if any(phrase in info.normalized for phrase in DESCRIPTIVE_MATERIAL_PHRASES):
        return True
    # A product code, origin, date or size can share a row with the fiber
    # content. Every material still carries its own explicit percent there,
    # and ``extract_numbers`` has already kept only those percent values.
    if (
        info.materials
        and info.explicit_percent
        and len(info.materials) == len(info.numbers)
    ):
        return False
    if _looks_like_non_composition_number(info.normalized):
        return True
    if info.materials or info.explicit_percent:
        return False

    # Product codes often appear between a material and its percentage in
    # Vision's paragraph order. They contain letters with digits, or several
    # bare numeric groups, but never form a material/ratio pair by themselves.
    has_letters = bool(re.search(r"[a-z가-힣一-龥ぁ-んァ-ン]", info.normalized))
    has_digits = bool(re.search(r"\d", info.normalized))
    if has_letters and has_digits:
        return True
    return len(_PLAIN_NUMBER_PATTERN.findall(info.normalized)) >= 2


def extract_numbers(line: str, allow_plain_numbers: bool = False) -> list[float]:
    normalized = normalize_text(line)
    percentage_matches = [
        match
        for match in _PERCENT_PATTERN.finditer(normalized)
        if 0 < float(match.group(1)) <= 100
    ]
    percentages = [float(match.group(1)) for match in percentage_matches]
    # A bare number is only inferred as a ratio on a row without care text:
    # ``SPANDEX 30 MACHINE WASH`` may be a wash temperature, not 30%.
    infer_plain = (
        allow_plain_numbers
        and not _looks_like_non_composition_number(normalized)
        and not _mentions_care(normalized)
    )
    if percentages:
        if not infer_plain:
            return percentages

        material_count = len(extract_materials(normalized))
        if material_count <= len(percentages):
            return percentages

        values_by_position = [
            (match.start(), float(match.group(1)))
            for match in percentage_matches
        ]
        percentage_spans = [match.span() for match in percentage_matches]
        for match in _PLAIN_NUMBER_PATTERN.finditer(_mask_temperatures(normalized)):
            start, end = match.span()
            overlaps_percentage = any(
                start < percent_end and end > percent_start
                for percent_start, percent_end in percentage_spans
            )
            if overlaps_percentage:
                continue

            value = float(match.group(1))
            if 0 < value <= 100:
                values_by_position.append((start, value))

        values_by_position.sort(key=lambda item: item[0])
        if len(values_by_position) == material_count:
            return [value for _, value in values_by_position]
        return percentages

    if not infer_plain:
        return []

    stripped = re.sub(r"[0-9.,:;/\-\s]", "", normalized)
    has_material = bool(extract_materials(normalized))
    if stripped and not has_material:
        return []

    return [
        float(match.group(1))
        for match in _PLAIN_NUMBER_PATTERN.finditer(_mask_temperatures(normalized))
        if 0 < float(match.group(1)) <= 100
    ]


def _split_part_markers(text: str) -> str:
    prepared = text
    markers = {
        alias
        for aliases in PART_PATTERNS.values()
        for alias in aliases
        if len(alias) >= 2
    }
    for marker in sorted(markers, key=len, reverse=True):
        prepared = re.sub(
            rf"(?i)(?<!^)(?<!\n)(?<![a-z])({re.escape(marker)})(?![a-z])",
            r"\n\1",
            prepared,
        )
    return prepared


def _apply_trailing_part_markers(infos: list[LineInfo]) -> list[LineInfo]:
    """Retag composition rows on labels that print the part marker after them.

    ``100% COTTON LINING`` names the row before the marker, while
    ``表地 / 55% モダール`` and ``면 100% / 안감 / 폴리 100%`` name the rows after
    it. A label is read marker-after only when it opens with a composition row
    and closes with a standalone marker; otherwise the forward scan stands.
    """

    marker_rows = [
        position for position, info in enumerate(infos) if info.is_standalone_marker
    ]
    material_rows = [position for position, info in enumerate(infos) if info.materials]
    if not marker_rows or not material_rows:
        return infos
    trailing_layout = (
        material_rows[0] < marker_rows[0]
        and material_rows[-1] < marker_rows[-1]
        # A ratio after the last marker belongs to its forward block even
        # when OCR omitted that block's material name.
        and not any(info.explicit_percent for info in infos[marker_rows[-1] + 1 :])
    )

    adjusted = list(infos)
    for position, next_marker in zip(marker_rows, [*marker_rows[1:], len(infos)]):
        marker_part = infos[position].marker_part
        # An outer marker that owns no row before the next marker can only be
        # naming the row printed before it (``면 100% 겉감 / 안감 / ...``). Other
        # parts are not inferred: a stray ``배색`` must not claim the main row.
        orphan_outer = marker_part == "outer" and not any(
            info.materials for info in infos[position + 1 : next_marker]
        )
        if position == 0 or not (trailing_layout or orphan_outer):
            continue

        # A trailing marker owns the whole preceding composition, including
        # alternating rows and stacked ratio columns. Stop at a part boundary
        # or unrelated text; metadata between composition rows can be skipped.
        block_positions: list[int] = []
        for cursor in range(position - 1, -1, -1):
            previous = infos[cursor]
            if previous.marker_part is not None:
                # A composition that explicitly names its part must not have
                # only its continuation rows reassigned to another part.
                if previous.materials or previous.unresolved_materials:
                    block_positions.clear()
                break
            if previous.materials or previous.unresolved_materials or previous.numbers:
                block_positions.append(cursor)
            elif _mentions_care(previous.normalized) or not _is_metadata_line(previous):
                break

        for cursor in block_positions:
            adjusted[cursor] = replace(infos[cursor], part=marker_part)
    return adjusted


def build_line_infos(text: str) -> list[LineInfo]:
    infos: list[LineInfo] = []
    current_part = "generic"
    prepared = _split_part_markers(normalize_text(text))

    for index, raw in enumerate(prepared.split("\n")):
        normalized = normalize_text(raw)
        if not normalized:
            continue

        marker_part = declared_part(normalized)
        current_part = marker_part or current_part
        composition_text = _strip_excluded_segments(normalized)
        materials = tuple(extract_materials(composition_text))
        number_only_line = not materials and not _TOKEN_PATTERN.search(composition_text)
        allow_plain = bool(materials) or number_only_line
        numbers = tuple(extract_numbers(composition_text, allow_plain_numbers=allow_plain))
        explicit_percent = bool(numbers) and len(
            _PERCENT_PATTERN.findall(composition_text)
        ) == len(numbers)

        infos.append(
            LineInfo(
                index=index,
                raw=raw.strip(),
                normalized=normalized,
                part=current_part,
                materials=materials,
                numbers=numbers,
                explicit_percent=explicit_percent,
                unresolved_materials=tuple(
                    unresolved_material_tokens(composition_text)
                ),
                marker_part=marker_part,
            )
        )
    return _apply_trailing_part_markers(infos)


def _equivalent_composition(materials: dict[str, float]) -> tuple[tuple[str, float], ...]:
    """Composition keyed so alternate names for one fiber compare as equal."""

    return tuple(
        sorted(
            (EQUIVALENT_MATERIALS.get(material, material), value)
            for material, value in materials.items()
        )
    )


def _composition_heading_indices(infos: list[LineInfo]) -> list[int]:
    return [
        info.index
        for info in infos
        if any(hint.casefold() in info.normalized for hint in COMPOSITION_HINTS)
    ]


def _context_rank(
    candidate: CompositionCandidate,
    heading_indices: list[int],
) -> int:
    """Prefer a material block immediately following a composition heading.

    The heading is only a tie-breaker: labels without a heading and valid
    composition blocks elsewhere remain accepted.
    """
    for heading_index in heading_indices:
        distance = candidate.start_index - heading_index
        if distance == 0:
            return 2
        if 0 < distance <= 6:
            return 1
    return 0


def _normalize_candidate(
    candidate: CompositionCandidate,
) -> tuple[dict[str, float | int], list[str]]:
    warnings: list[str] = []
    values = candidate.materials

    if not candidate.explicit_percent:
        warnings.append("ratio_marker_inferred")

    normalized: dict[str, float | int] = {}
    for material, value in values.items():
        rounded = round(value, 1)
        normalized[material] = (
            int(rounded) if float(rounded).is_integer() else rounded
        )
    return normalized, warnings


def _best_candidates_by_part(
    text: str,
) -> tuple[
    dict[str, dict[str, float | int]],
    dict[str, CompositionCandidate],
    list[str],
    set[str],
]:
    infos = build_line_infos(text)
    candidates = _collect_candidates(
        [info for info in infos if not _is_metadata_line(info)]
    )
    heading_indices = _composition_heading_indices(infos)
    best_by_part: dict[str, CompositionCandidate] = {}
    ambiguous_parts: set[str] = set()

    for candidate in candidates:
        current = best_by_part.get(candidate.part)
        candidate_rank = (
            *candidate.score[:3],
            _context_rank(candidate, heading_indices),
            candidate.score[3],
        )
        current_rank = (
            (
                *current.score[:3],
                _context_rank(current, heading_indices),
                current.score[3],
            )
            if current
            else None
        )
        if current is None or candidate_rank > current_rank:
            best_by_part[candidate.part] = candidate
            ambiguous_parts.discard(candidate.part)
        elif candidate_rank == current_rank and _equivalent_composition(
            candidate.materials
        ) != _equivalent_composition(current.materials):
            ambiguous_parts.add(candidate.part)

    # A row naming a fiber the table cannot resolve has no trustworthy
    # material/ratio mapping: its ratio would silently move to a neighbour.
    composition_rows = [
        info for info in infos
        if (info.materials or info.unresolved_materials) and not _is_metadata_line(info)
    ]
    unresolved_parts = {
        info.part for info in composition_rows if info.unresolved_materials
    }
    # Every recognized material row must belong to a complete candidate.
    # A valid 100% row cannot hide an unpaired row before or after it. Keep
    # coverage from all complete blocks so multilingual repetitions remain valid.
    covered_rows = {index for candidate in candidates for index in candidate.row_indices}
    incomplete_parts = {
        info.part for info in composition_rows
        if info.materials and info.index not in covered_rows
    }

    # OCR can lose a material/part name but retain its standalone percentage.
    # Do not let another complete block hide that missing composition (QA031).
    # Limit this to ratio-only rows: care/marketing text is not fiber evidence.
    orphan_ratio_parts = {
        info.part for info in infos
        if info.explicit_percent
        and not info.materials
        and not _TOKEN_PATTERN.search(info.normalized)
        and info.index not in covered_rows
        and not _is_metadata_line(info)
    }

    parts: dict[str, dict[str, float | int]] = {}
    warnings: list[str] = []
    for part, candidate in best_by_part.items():
        if part in ambiguous_parts:
            warnings.append(f"{part}:ambiguous_composition_candidates")
            continue
        if part in unresolved_parts:
            warnings.append(f"{part}:unresolved_material_token")
            continue
        if part in orphan_ratio_parts:
            warnings.append(f"{part}:unpaired_ratio_rows")
            continue
        if part in incomplete_parts:
            warnings.append(f"{part}:unpaired_material_rows")
            continue
        normalized, candidate_warnings = _normalize_candidate(candidate)
        parts[part] = normalized
        warnings.extend(f"{part}:{warning}" for warning in candidate_warnings)

    expected_parts = orphan_ratio_parts | {info.part for info in composition_rows} | {
        info.marker_part for info in infos if info.marker_part is not None
    }

    return parts, best_by_part, warnings, expected_parts


def parse_parts(text: str) -> dict[str, dict[str, float | int]]:
    parts, _, _, _ = _best_candidates_by_part(text)
    return parts


def normalize_percentages(
    materials: dict[str, float],
) -> dict[str, float | int]:
    if not materials:
        return {}

    candidate = CompositionCandidate(
        part="generic",
        materials={key: float(value) for key, value in materials.items()},
        source="same_line",
        explicit_percent=True,
        start_index=0,
    )
    if abs(candidate.total - 100.0) > EXACT_RATIO_TOLERANCE:
        return {}
    normalized, _ = _normalize_candidate(candidate)
    return normalized


def choose_representative_materials(
    parts: dict[str, dict[str, float | int]],
) -> tuple[str, dict[str, float | int]]:
    for part in PART_PRIORITY:
        materials = parts.get(part)
        if materials:
            return part, materials
    return "", {}


def parse_materials(text: str) -> dict[str, float | int]:
    _, materials = choose_representative_materials(parse_parts(text))
    return materials


def format_materials_korean(
    material_dict: dict[str, float | int],
) -> str:
    parts = []
    for material, percent in sorted(
        material_dict.items(),
        key=lambda item: (-float(item[1]), item[0]),
    ):
        korean = MATERIAL_KOREAN.get(material, material)
        percent_text = (
            str(int(percent))
            if float(percent).is_integer()
            else f"{float(percent):.1f}"
        )
        parts.append(f"{korean} {percent_text}%")
    return ", ".join(parts)


def parse_care(text: str) -> str:
    normalized = normalize_text(text)
    found: set[str] = set()

    for korean, aliases in CARE_RULES.items():
        if any(alias.casefold() in normalized for alias in aliases):
            found.add(korean)

    for matched_rule in tuple(found):
        found.difference_update(CARE_CONFLICTS.get(matched_rule, set()))

    return "; ".join(rule for rule in CARE_RULES if rule in found)


def failed_response(
    raw_text: str = "",
    *,
    error_code: str = "composition_not_found",
    message: str = "소재 혼용률을 신뢰할 수 있게 인식하지 못했습니다.",
    warnings: list[str] | None = None,
) -> dict:
    care_instruction = parse_care(raw_text)
    return {
        "status": "failed",
        "error_code": error_code,
        "message": message,
        "materials": {},
        "materials_korean": "",
        "raw_ocr_preview": clean_ocr_preview(raw_text),
        "confidence": {
            "ocr": "unknown",
            "parser": "low",
        },
        "warnings": list(warnings or []),
        "care_instruction": care_instruction,
        "care_instructions": [
            item.strip()
            for item in care_instruction.split(";")
            if item.strip()
        ],
        "parts": {},
    }


def parse_label(text: str) -> dict:
    if not text or not text.strip():
        return failed_response(
            "",
            error_code="ocr_text_empty",
            message="OCR에서 라벨 텍스트를 추출하지 못했습니다.",
        )

    parts, candidates, warnings, expected_parts = _best_candidates_by_part(text)
    selected_part, materials = choose_representative_materials(parts)
    if not materials:
        error_code = (
            "ambiguous_composition"
            if any("ambiguous_composition_candidates" in item for item in warnings)
            else "composition_not_found"
        )
        message = (
            "서로 다른 소재 조성 후보가 있어 자동으로 선택하지 않았습니다."
            if error_code == "ambiguous_composition"
            else "소재 혼용률을 신뢰할 수 있게 인식하지 못했습니다."
        )
        return failed_response(
            text,
            error_code=error_code,
            message=message,
            warnings=warnings,
        )

    # The label names a more representative part (an outer shell above a
    # lining) whose composition never resolved. Substituting the part that
    # happened to add up would report a lining as the whole garment.
    unconfirmed_parts = [
        part
        for part in PART_PRIORITY[: PART_PRIORITY.index(selected_part)]
        if part in expected_parts and part not in parts
    ]
    if unconfirmed_parts:
        return failed_response(
            text,
            error_code="incomplete_part_composition",
            message=(
                "겉감 등 대표 부위의 혼용률을 확인하지 못해 "
                "다른 부위 값을 대신 사용하지 않았습니다."
            ),
            warnings=[
                *warnings,
                *(f"{part}:composition_not_confirmed" for part in unconfirmed_parts),
            ],
        )

    selected_candidate = candidates[selected_part]
    parser_confidence = (
        "high"
        if selected_candidate.explicit_percent
        and abs(selected_candidate.total - 100.0) <= EXACT_RATIO_TOLERANCE
        and selected_candidate.source == "same_line"
        else "medium"
    )
    care_instruction = parse_care(text)

    return {
        "status": "success",
        "materials": materials,
        "materials_korean": format_materials_korean(materials),
        "raw_ocr_preview": clean_ocr_preview(text),
        "confidence": {
            "ocr": "unknown",
            "parser": parser_confidence,
        },
        "warnings": warnings,
        "care_instruction": care_instruction,
        "care_instructions": [
            item.strip()
            for item in care_instruction.split(";")
            if item.strip()
        ],
        "selected_part": selected_part,
        "parts": parts,
        "parse_evidence": {
            "composition_status": "confirmed",
            "source": selected_candidate.source,
            "ratio_total_before_normalization": round(
                selected_candidate.total,
                2,
            ),
            "explicit_percent": selected_candidate.explicit_percent,
        },
    }
