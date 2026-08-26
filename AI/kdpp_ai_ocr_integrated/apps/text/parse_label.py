import re
from dataclasses import dataclass

from apps.text.rules import (
    CARE_CONFLICTS,
    CARE_RULES,
    MATERIAL_ALIASES,
    MATERIAL_KOREAN,
    OCR_CORRECTIONS,
)


PART_PATTERNS = {
    "outer": [
        "겉감",
        "겉 감",
        "외피",
        "표면",
        "본체",
        "몸판",
        "본피",
        "shell",
        "outshell",
        "outer",
        "face",
        "main fabric",
        "本体",
        "面料",
    ],
    "lining": [
        "안감",
        "안 감",
        "내피",
        "lining",
        "lning",
        "裏地",
        "里料",
        "裡料",
    ],
    "filling": [
        "충전재",
        "충전제",
        "충전",
        "솜",
        "filling",
        "fill",
        "中わた",
        "填充",
    ],
    "pocket": ["주머니감", "주머니천", "주머니", "pocket"],
    "rib": ["립", "리브", "rib"],
    "sleeve": ["소매", "sleeve"],
    "color_block": ["배색", "contrast", "配色"],
}

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

MIN_ACCEPTED_RATIO_TOTAL = 95.0
MAX_ACCEPTED_RATIO_TOTAL = 105.0
EXACT_RATIO_TOLERANCE = 0.5

EXCLUDED_SEGMENT_WORDS = {
    "심지",
    "보강재",
    "상표",
    "무늬",
    "밴드",
    "레이스",
    "자수",
    "장식",
    "부자재",
    "제외",
    "except",
    "excluding",
    "exclusive of decoration",
    "decoration",
    "embroidery",
    "accessory",
    "trim",
}

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
}

_TOKEN_PATTERN = re.compile(
    r"[a-zà-ÿ]+|[가-힣]+|[一-龥]+|[ぁ-んァ-ン]+",
    re.IGNORECASE,
)
_PERCENT_PATTERN = re.compile(
    r"(?<![a-z0-9])([0-9]{1,3}(?:\.[0-9]+)?)\s*[%％]",
    re.IGNORECASE,
)
_PLAIN_NUMBER_PATTERN = re.compile(
    r"(?<![a-z0-9])([0-9]{1,3}(?:\.[0-9]+)?)(?![a-z0-9])",
    re.IGNORECASE,
)


def _normalized_alias(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().strip())


ALIAS_TO_MATERIAL = {
    _normalized_alias(alias): material
    for material, aliases in MATERIAL_ALIASES.items()
    for alias in aliases
    if alias.strip()
}

MULTIWORD_ALIASES = sorted(
    (
        (alias, material)
        for alias, material in ALIAS_TO_MATERIAL.items()
        if " " in alias
    ),
    key=lambda item: len(item[0]),
    reverse=True,
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
            "adjacent_lines": 1,
        }.get(self.source, 0)
        return (
            1 if self.explicit_percent else 0,
            -abs(100.0 - self.total),
            source_rank,
            len(self.materials),
        )


def _replace_token(text: str, wrong: str, correct: str) -> str:
    if wrong.isascii():
        pattern = rf"(?<![a-z]){re.escape(wrong)}(?![a-z])"
    else:
        pattern = re.escape(wrong)
    return re.sub(pattern, correct, text, flags=re.IGNORECASE)


def normalize_text(text: str) -> str:
    if not text:
        return ""

    normalized = text.casefold()
    normalized = normalized.replace("：", ":").replace("％", "%")
    normalized = normalized.replace("·", " ").replace("\u00a0", " ")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    for wrong, correct in OCR_CORRECTIONS.items():
        normalized = _replace_token(normalized, wrong.casefold(), correct.casefold())

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.split("\n")]
    return "\n".join(line for line in lines if line)


def clean_ocr_preview(text: str, max_len: int = 220) -> str:
    if not text:
        return ""
    preview = re.sub(r"\s+", " ", text).strip()
    return preview if len(preview) <= max_len else preview[:max_len] + "..."


def find_material_key(word: str) -> str | None:
    token = _normalized_alias(word.strip(" .,:;/()[]{}<>|+-_=*\"'"))
    if not token:
        return None
    corrected = OCR_CORRECTIONS.get(token, token)
    return ALIAS_TO_MATERIAL.get(_normalized_alias(corrected))


def _strip_excluded_segments(line: str) -> str:
    def remove_if_excluded(match: re.Match[str]) -> str:
        content = match.group(0).casefold()
        return " " if any(word in content for word in EXCLUDED_SEGMENT_WORDS) else content

    cleaned = re.sub(r"[\(\[][^\)\]]*[\)\]]", remove_if_excluded, line)
    exclusion_pattern = "|".join(
        re.escape(word)
        for word in sorted(EXCLUDED_SEGMENT_WORDS, key=len, reverse=True)
    )
    cleaned = re.sub(
        rf"(?:{exclusion_pattern}).*$",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_materials(line: str) -> list[str]:
    cleaned = _strip_excluded_segments(normalize_text(line))
    if not cleaned:
        return []

    found: list[str] = []
    for alias, material in MULTIWORD_ALIASES:
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", cleaned):
            found.append(material)

    for token in _TOKEN_PATTERN.findall(cleaned):
        material = find_material_key(token)
        if material:
            found.append(material)

    return list(dict.fromkeys(found))


def detect_part(line: str, current_part: str) -> str:
    normalized = normalize_text(line)
    for part, aliases in PART_PATTERNS.items():
        if any(alias.casefold() in normalized for alias in aliases):
            return part
    return current_part


def _looks_like_non_composition_number(line: str) -> bool:
    if any(word in line for word in NON_COMPOSITION_WORDS):
        return True
    if re.search(r"\b(?:19|20)\d{2}\b", line):
        return True
    if re.search(r"\d+(?:\.\d+)?\s*(?:cm|mm|kg|g|호|년|월|일)\b", line):
        return True
    return False


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
        for match in _PLAIN_NUMBER_PATTERN.finditer(normalized):
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
        for match in _PLAIN_NUMBER_PATTERN.finditer(normalized)
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


def build_line_infos(text: str) -> list[LineInfo]:
    infos: list[LineInfo] = []
    current_part = "generic"
    prepared = _split_part_markers(normalize_text(text))

    for index, raw in enumerate(prepared.split("\n")):
        normalized = normalize_text(raw)
        if not normalized:
            continue

        current_part = detect_part(normalized, current_part)
        materials = tuple(extract_materials(normalized))
        number_only_line = not materials and not _TOKEN_PATTERN.search(normalized)
        allow_plain = bool(materials) or number_only_line
        numbers = tuple(extract_numbers(normalized, allow_plain_numbers=allow_plain))
        explicit_percent = bool(numbers) and len(
            _PERCENT_PATTERN.findall(normalized)
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
            )
        )
    return infos


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
    if not MIN_ACCEPTED_RATIO_TOTAL <= total <= MAX_ACCEPTED_RATIO_TOTAL:
        return None

    return CompositionCandidate(
        part=part,
        materials=paired,
        source=source,
        explicit_percent=explicit_percent,
        start_index=start_index,
    )


def _collect_candidates(infos: list[LineInfo]) -> list[CompositionCandidate]:
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

        materials: list[str] = []
        numbers: list[float] = []
        explicit_percent = True
        for current in infos[position : position + 6]:
            if (
                current.part != info.part
                or not current.materials
                or not current.numbers
                or len(current.materials) != len(current.numbers)
            ):
                break
            materials.extend(current.materials)
            numbers.extend(current.numbers)
            explicit_percent = explicit_percent and current.explicit_percent
            candidate = _pair_values(
                info.part,
                materials,
                numbers,
                source="line_pairs",
                explicit_percent=explicit_percent,
                start_index=info.index,
            )
            if candidate and len(materials) > len(info.materials):
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

    for position, info in enumerate(infos):
        if not info.materials or info.numbers:
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
        if candidate:
            candidates.append(candidate)

    for position, info in enumerate(infos):
        if not info.materials or info.numbers:
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


def _normalize_candidate(
    candidate: CompositionCandidate,
) -> tuple[dict[str, float | int], list[str]]:
    total = candidate.total
    warnings: list[str] = []
    values = candidate.materials

    if not candidate.explicit_percent:
        warnings.append("ratio_marker_inferred")

    if abs(total - 100.0) > 0.01:
        warnings.append(
            f"ratio_total_normalized:{round(total, 2)}"
        )
        values = {
            material: ratio * 100.0 / total
            for material, ratio in candidate.materials.items()
        }

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
]:
    candidates = _collect_candidates(build_line_infos(text))
    best_by_part: dict[str, CompositionCandidate] = {}
    ambiguous_parts: set[str] = set()

    for candidate in candidates:
        current = best_by_part.get(candidate.part)
        if current is None or candidate.score > current.score:
            best_by_part[candidate.part] = candidate
            ambiguous_parts.discard(candidate.part)
        elif (
            candidate.score == current.score
            and candidate.materials != current.materials
        ):
            ambiguous_parts.add(candidate.part)

    parts: dict[str, dict[str, float | int]] = {}
    warnings: list[str] = []
    for part, candidate in best_by_part.items():
        if part in ambiguous_parts:
            warnings.append(f"{part}:ambiguous_composition_candidates")
            continue
        normalized, candidate_warnings = _normalize_candidate(candidate)
        parts[part] = normalized
        warnings.extend(f"{part}:{warning}" for warning in candidate_warnings)

    return parts, best_by_part, warnings


def parse_parts(text: str) -> dict[str, dict[str, float | int]]:
    parts, _, _ = _best_candidates_by_part(text)
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
    if not MIN_ACCEPTED_RATIO_TOTAL <= candidate.total <= MAX_ACCEPTED_RATIO_TOTAL:
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

    parts, candidates, warnings = _best_candidates_by_part(text)
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
            "source": selected_candidate.source,
            "ratio_total_before_normalization": round(
                selected_candidate.total,
                2,
            ),
            "explicit_percent": selected_candidate.explicit_percent,
        },
    }
