import re
from dataclasses import dataclass, replace

from apps.text.material_extraction import (
    PART_PATTERNS,
    _strip_excluded_segments,
    _TOKEN_PATTERN,
    clean_ocr_preview,
    declared_part,
    detect_part,
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

EXACT_RATIO_TOLERANCE = 0.01

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


@dataclass(frozen=True)
class LineInfo:
    index: int
    raw: str
    normalized: str
    part: str
    materials: tuple[str, ...]
    numbers: tuple[float, ...]
    explicit_percent: bool
    unresolved_materials: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompositionCandidate:
    part: str
    materials: dict[str, float]
    source: str
    explicit_percent: bool
    start_index: int

    @property
    def total(self) -> float:
        return sum(self.materials.values())

    @property
    def score(self) -> tuple[int, float, int, int]:
        source_rank = {
            "same_line": 3,
            "line_pairs": 2,
            "stacked_columns": 2,
            "mixed_lines": 2,
            "adjacent_lines": 1,
        }.get(self.source, 0)
        return (
            1 if self.explicit_percent else 0,
            -abs(100.0 - self.total),
            len(self.materials),
            source_rank,
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
    if percentages:
        if not allow_plain_numbers or _looks_like_non_composition_number(normalized):
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

    if not allow_plain_numbers or _looks_like_non_composition_number(normalized):
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

    ``100% COTTON LINING`` and ``表地 / 55% モダール`` are both common layouts,
    so which side a marker names is decided once per label: whichever comes
    first, a composition row or a standalone marker, sets the direction.
    """

    first_material = next(
        (position for position, info in enumerate(infos) if info.materials),
        None,
    )
    first_marker = next(
        (
            position
            for position, info in enumerate(infos)
            if not info.materials
            and not info.numbers
            and declared_part(info.normalized) is not None
        ),
        None,
    )
    if first_material is None or first_marker is None or first_marker < first_material:
        return infos

    adjusted = list(infos)
    for position in range(1, len(adjusted)):
        marker_line = adjusted[position]
        if marker_line.materials or marker_line.numbers:
            continue

        marker_part = declared_part(marker_line.normalized)
        if marker_part is None:
            continue

        previous = adjusted[position - 1]
        if not previous.materials or not previous.numbers:
            continue
        if previous.part == marker_part:
            continue
        # A row that names its own part already states where it belongs.
        if declared_part(previous.normalized) is not None:
            continue

        adjusted[position - 1] = replace(previous, part=marker_part)
    return adjusted


def build_line_infos(text: str) -> list[LineInfo]:
    infos: list[LineInfo] = []
    current_part = "generic"
    prepared = _split_part_markers(normalize_text(text))

    for index, raw in enumerate(prepared.split("\n")):
        normalized = normalize_text(raw)
        if not normalized:
            continue

        current_part = detect_part(normalized, current_part)
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
            )
        )
    return _apply_trailing_part_markers(infos)


def _pair_values(
    part: str,
    materials: list[str] | tuple[str, ...],
    numbers: list[float] | tuple[float, ...],
    *,
    source: str,
    explicit_percent: bool,
    start_index: int,
) -> CompositionCandidate | None:
    if not materials or not numbers or len(materials) != len(numbers):
        return None

    paired: dict[str, float] = {}
    for material, number in zip(materials, numbers):
        if material in paired or not (0 < number <= 100):
            return None
        paired[material] = float(number)

    total = sum(paired.values())
    # A partial or misread OCR result must not be rescaled into a valid-looking
    # composition. Every supplied ratio needs to form one complete 100% block.
    if abs(total - 100.0) > EXACT_RATIO_TOLERANCE:
        return None

    return CompositionCandidate(
        part=part,
        materials=paired,
        source=source,
        explicit_percent=explicit_percent,
        start_index=start_index,
    )


def _is_standalone_composition(info: LineInfo) -> bool:
    """Whether a row's own ratios already form one complete composition."""

    return abs(sum(info.numbers) - 100.0) <= EXACT_RATIO_TOLERANCE


def _collect_candidates(infos: list[LineInfo]) -> list[CompositionCandidate]:
    infos = [info for info in infos if not _is_metadata_line(info)]
    candidates: list[CompositionCandidate] = []

    for info in infos:
        candidate = _pair_values(
            info.part,
            info.materials,
            info.numbers,
            source="same_line",
            explicit_percent=info.explicit_percent,
            start_index=info.index,
        )
        if candidate:
            candidates.append(candidate)

    for position, info in enumerate(infos):
        if not info.materials or not info.numbers:
            continue

        run: list[LineInfo] = []
        for current in infos[position : position + 6]:
            if (
                current.part != info.part
                or not current.materials
                or not current.numbers
                or len(current.materials) != len(current.numbers)
            ):
                break
            run.append(current)

        materials: list[str] = []
        numbers: list[float] = []
        explicit_percent = True
        for offset, current in enumerate(run):
            materials.extend(current.materials)
            numbers.extend(current.numbers)
            explicit_percent = explicit_percent and current.explicit_percent
            if len(materials) <= len(info.materials):
                continue

            # A following row that cannot stand on its own is part of this
            # block, so an exact total reached before it is only a fragment.
            following = run[offset + 1 :]
            if following and not _is_standalone_composition(following[0]):
                continue

            candidate = _pair_values(
                info.part,
                materials,
                numbers,
                source="line_pairs",
                explicit_percent=explicit_percent,
                start_index=info.index,
            )
            if candidate:
                candidates.append(candidate)

    for position, info in enumerate(infos):
        if not info.materials or info.numbers:
            continue

        alternating_materials: list[str] = []
        alternating_numbers: list[float] = []
        cursor = position
        while cursor + 1 < len(infos) and len(alternating_materials) < 6:
            material_line = infos[cursor]
            ratio_line = infos[cursor + 1]
            if (
                material_line.part != info.part
                or ratio_line.part != info.part
                or not material_line.materials
                or material_line.numbers
                or ratio_line.materials
                or not ratio_line.numbers
                or not ratio_line.explicit_percent
                or len(material_line.materials) != len(ratio_line.numbers)
            ):
                break
            alternating_materials.extend(material_line.materials)
            alternating_numbers.extend(ratio_line.numbers)
            cursor += 2

        candidate = _pair_values(
            info.part,
            alternating_materials,
            alternating_numbers,
            source="alternating_lines",
            explicit_percent=True,
            start_index=info.index,
        )
        if candidate:
            candidates.append(candidate)

    # Mixed layouts occur in real labels: one component can be split across
    # two lines while the next component is complete on one line. Accumulate
    # only exact material/ratio pairs, without borrowing a ratio twice.
    for position, info in enumerate(infos):
        if not info.materials:
            continue

        materials: list[str] = []
        numbers: list[float] = []
        explicit_percent = True
        component_count = 0
        used_split_pair = False
        used_same_line_pair = False
        cursor = position

        while cursor < len(infos) and component_count < 6:
            current = infos[cursor]
            if current.part != info.part:
                break

            if (
                current.materials
                and current.numbers
                and len(current.materials) == len(current.numbers)
            ):
                materials.extend(current.materials)
                numbers.extend(current.numbers)
                explicit_percent = explicit_percent and current.explicit_percent
                component_count += len(current.materials)
                used_same_line_pair = True
                cursor += 1
                continue

            if (
                current.materials
                and not current.numbers
                and cursor + 1 < len(infos)
            ):
                ratio_line = infos[cursor + 1]
                if (
                    ratio_line.part == info.part
                    and not ratio_line.materials
                    and ratio_line.numbers
                    and ratio_line.explicit_percent
                    and len(current.materials) == len(ratio_line.numbers)
                ):
                    materials.extend(current.materials)
                    numbers.extend(ratio_line.numbers)
                    component_count += len(current.materials)
                    used_split_pair = True
                    cursor += 2
                    continue
            break

        if not (used_split_pair and used_same_line_pair):
            continue
        candidate = _pair_values(
            info.part,
            materials,
            numbers,
            source="mixed_lines",
            explicit_percent=explicit_percent,
            start_index=info.index,
        )
        # Mixed layouts must still show every ratio explicitly.
        if candidate and explicit_percent:
            candidates.append(candidate)

    for position, info in enumerate(infos):
        if not info.materials or info.numbers:
            continue

        # Start only at the beginning of a material block. Otherwise a
        # mismatched block could be made to look valid by dropping its first
        # material and pairing only a suffix with the ratio column.
        if position > 0:
            previous = infos[position - 1]
            if (
                previous.part == info.part
                and previous.materials
                and not previous.numbers
            ):
                continue

        material_block: list[str] = []
        number_block: list[float] = []
        explicit_percent = True
        cursor = position

        while cursor < len(infos) and len(material_block) < 6:
            current = infos[cursor]
            if current.part != info.part or current.numbers or not current.materials:
                break
            material_block.extend(current.materials)
            cursor += 1

        while cursor < len(infos) and len(number_block) < len(material_block):
            current = infos[cursor]
            if current.part != info.part or current.materials or not current.numbers:
                break
            number_block.extend(current.numbers)
            explicit_percent = explicit_percent and current.explicit_percent
            cursor += 1

        candidate = _pair_values(
            info.part,
            material_block,
            number_block,
            source="stacked_columns",
            explicit_percent=explicit_percent,
            start_index=info.index,
        )
        # Bare number-only lines are too easily confused with product codes,
        # dates, or temperatures. A stacked ratio column is accepted only
        # when every ratio carries an explicit percent marker.
        if candidate and explicit_percent:
            candidates.append(candidate)

    for position, info in enumerate(infos):
        if not info.materials or info.numbers:
            continue

        # If this material belongs to a consecutive material block, pairing
        # only its last row with the next ratio would hide a count mismatch.
        if position > 0:
            previous = infos[position - 1]
            if (
                previous.part == info.part
                and previous.materials
                and not previous.numbers
            ):
                continue

        for next_position in range(position + 1, min(position + 3, len(infos))):
            neighbor = infos[next_position]
            if neighbor.part != info.part or neighbor.materials:
                break
            candidate = _pair_values(
                info.part,
                info.materials,
                neighbor.numbers,
                source="adjacent_lines",
                explicit_percent=neighbor.explicit_percent,
                start_index=info.index,
            )
            if candidate:
                candidates.append(candidate)
                break

    return candidates


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
    candidates = _collect_candidates(infos)
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
    unresolved_parts = {info.part for info in infos if info.unresolved_materials}

    parts: dict[str, dict[str, float | int]] = {}
    warnings: list[str] = []
    for part, candidate in best_by_part.items():
        if part in ambiguous_parts:
            warnings.append(f"{part}:ambiguous_composition_candidates")
            continue
        if part in unresolved_parts:
            warnings.append(f"{part}:unresolved_material_token")
            continue
        normalized, candidate_warnings = _normalize_candidate(candidate)
        parts[part] = normalized
        warnings.extend(f"{part}:{warning}" for warning in candidate_warnings)

    expected_parts = unresolved_parts | {
        part
        for info in infos
        if (part := declared_part(info.normalized)) is not None
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
