import re
import unicodedata
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
        "表布",
        "表層",
        "表地",
        "表素材",
        "表生地",
        "主面料",
        "外层",
        "外層",
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
        "内里",
        "內裡",
        "裏素材",
        "裏生地",
        "里布",
        "裏布",
        "内衬",
        "內襯",
        "衬里",
        "襯裡",
    ],
    "filling": [
        "충전재",
        "충전제",
        "충전",
        "솜",
        "filling",
        "fill",
        "中わた",
        "中綿",
        "填充",
        "填充物",
        "填充料",
    ],
    "pocket": [
        "주머니감", "주머니천", "주머니", "pocket", "口袋布", "袋布", "ポケット布"
    ],
    "rib": ["립", "리브", "rib", "罗纹", "羅紋"],
    "sleeve": ["소매", "sleeve", "袖子", "袖部", "袖"],
    "color_block": ["배색", "contrast", "配色", "拼接", "別布"],
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
    "装饰",
    "裝飾",
    "刺绣",
    "刺繍",
    "辅料",
    "輔料",
    "配件",
    "付属",
    "附属",
    "除く",
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

_TOKEN_PATTERN = re.compile(
    r"[a-zà-ÿ]+|[가-힣]+|[一-龥]+|[ぁ-んァ-ンー]+",
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
            "mixed_lines": 2,
            "adjacent_lines": 1,
        }.get(self.source, 0)
        return (
            1 if self.explicit_percent else 0,
            -abs(100.0 - self.total),
            len(self.materials),
            source_rank,
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

    # Normalize full-width digits/punctuation and compatibility characters
    # commonly returned from Japanese and Chinese care labels.
    normalized = unicodedata.normalize("NFKC", text).casefold()
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
    corrected = _normalized_alias(corrected)
    material = ALIAS_TO_MATERIAL.get(corrected)
    if material:
        return material

    # OCR sometimes joins a Korean part marker and its first material
    # (for example, ``배색면``). Only split a known non-ASCII marker and
    # require the remainder to be a complete material alias.
    for aliases in PART_PATTERNS.values():
        for prefix in aliases:
            normalized_prefix = _normalized_alias(prefix)
            if (
                not normalized_prefix.isascii()
                and corrected.startswith(normalized_prefix)
                and len(corrected) > len(normalized_prefix)
            ):
                material = ALIAS_TO_MATERIAL.get(
                    corrected[len(normalized_prefix) :]
                )
                if material:
                    return material
    return None


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
    tokenizable = cleaned
    for alias, material in MULTIWORD_ALIASES:
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", cleaned):
            found.append(material)
            # A spatial OCR row can split a Korean compound such as
            # ``폴리 우레탄``. Remove a matched multiword alias before the
            # token pass so its partial token ``폴리`` is not also read as
            # polyester.
            tokenizable = re.sub(
                rf"(?<![a-z]){re.escape(alias)}(?![a-z])",
                " ",
                tokenizable,
            )

    for token in _TOKEN_PATTERN.findall(tokenizable):
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
    # A partial OCR result such as ``cotton 95%`` must not be promoted to a
    # complete single-material composition. Multi-material labels retain the
    # existing small total-error tolerance because every component is present.
    if len(paired) == 1 and abs(total - 100.0) > EXACT_RATIO_TOLERANCE:
        return None
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
    return int(
        any(
            0 < candidate.start_index - heading_index <= 6
            for heading_index in heading_indices
        )
    )


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
    infos = build_line_infos(text)
    candidates = _collect_candidates(infos)
    heading_indices = _composition_heading_indices(infos)
    best_by_part: dict[str, CompositionCandidate] = {}
    ambiguous_parts: set[str] = set()

    for candidate in candidates:
        current = best_by_part.get(candidate.part)
        candidate_rank = (_context_rank(candidate, heading_indices), *candidate.score)
        current_rank = (
            (_context_rank(current, heading_indices), *current.score)
            if current
            else None
        )
        if current is None or candidate_rank > current_rank:
            best_by_part[candidate.part] = candidate
            ambiguous_parts.discard(candidate.part)
        elif (
            candidate_rank == current_rank
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
    if (
        len(candidate.materials) == 1
        and abs(candidate.total - 100.0) > EXACT_RATIO_TOLERANCE
    ):
        return {}
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
