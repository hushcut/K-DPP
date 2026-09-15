import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

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

EXACT_RATIO_TOTAL = Decimal("100")

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
_ALIAS_SEPARATOR_PATTERN = re.compile(r"[\s/|,;:()\[\]{}\-]*")
_NUMBER_VALUE_PATTERN = re.compile(r"(?:[0-9]+(?:[.,][0-9]+)?|[.,][0-9]+)")
_NUMBER_CANDIDATE_PATTERN = re.compile(
    r"[+\-−]?(?:[0-9]+(?:[.,][0-9]+)?|[.,][0-9]+)(?:\s*%)?"
)
_MEASUREMENT_UNIT_PATTERN = re.compile(
    r"\s*(?:°(?:\s*[cf])?|[cf]|degrees?(?:\s*[cf])?|"
    r"deg(?:\s*[cf])?|celsius|fahrenheit|"
    r"cm|mm|kg|mg|g|lb|lbs|oz|호|년|월|일|번|원|円|元|도)(?:\b|$)",
    re.IGNORECASE,
)
_INEXACT_SIGNS = "+-−±∓‐‑‒–—<>≤≥≦≧~≈≃∼"
_PLAIN_NUMBER_METADATA_PREFIX = re.compile(
    r"(?:\b(?:size|style|model|sku|lot|item|date|price|wash|iron|dry|"
    r"bleach|rn|ca|made|year|no)\b|제품명|제조년월|제조국|품번|호칭|"
    r"수입자|판매자|신체치수|가슴둘레|허리둘레|검사필)"
    r"\s*[:#.\-]?\s*$",
    re.IGNORECASE,
)
_METADATA_HEADER_PATTERN = re.compile(
    r"(?:(?P<size>size(?![a-z])|사이즈|호칭)|"
    r"(?P<shrinkage>shrinkage(?:\s+rate)?(?![a-z])|수축률|수축율))"
    r"\s*[:=]?\s*(?P<value>.*)",
)
_METADATA_VALUE_PATTERNS = {
    "size": re.compile(
        r"(?:[0-9]+(?:[.,][0-9]+)?"
        r"(?:\s*[-/x×]\s*[0-9]+(?:[.,][0-9]+)?)*\s*(?:cm|mm|호)?|"
        r"[2-9]?x{0,3}[sl]|m|free|one\s*size)"
    ),
    "shrinkage": re.compile(
        r"(?:[<>≤≥~±+\-]|up\s+to|max(?:imum)?|less\s+than|최대)?\s*"
        r"[0-9]+(?:[.,][0-9]+)?\s*%(?:\s*(?:이하|미만|max(?:imum)?))?"
    ),
}
_RATIO_PAIR_DESCRIPTORS = {
    "organic",
    "recycled",
    "combed",
    "certified",
    "pure",
    "fiber",
    "fibre",
    "content",
    "blend",
    "of",
    "and",
    "유기농",
    "재생",
    "섬유",
    "함량",
    "혼방",
    "및",
}
_RATIO_PREFIX_CONTEXTS = {
    *COMPOSITION_HINTS,
    *(alias for aliases in PART_PATTERNS.values() for alias in aliases),
    "fiber",
    "fibre",
    "content",
    "body",
    "組成",
    "組成表示",
    "纤维",
    "纤维成分",
    "成分",
}


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
class MaterialEvidence:
    material: str
    start: int
    end: int


@dataclass(frozen=True)
class NumberEvidence:
    value: Decimal
    start: int
    end: int
    explicit_percent: bool


@dataclass(frozen=True)
class LineInfo:
    index: int
    raw: str
    normalized: str
    part: str
    materials: tuple[str, ...]
    numbers: tuple[Decimal, ...]
    explicit_percent: bool
    invalid_evidence: bool
    explicit_part: bool
    is_metadata: bool


@dataclass(frozen=True)
class CompositionCandidate:
    part: str
    materials: dict[str, Decimal]
    source: str
    explicit_percent: bool
    start_index: int
    evidence_indices: frozenset[int]

    @property
    def total(self) -> Decimal:
        return sum(self.materials.values(), Decimal(0))

    @property
    def score(self) -> tuple[int, Decimal, int, int]:
        source_rank = {
            "same_line": 3,
            "line_pairs": 2,
            "stacked_columns": 2,
            "adjacent_lines": 1,
        }.get(self.source, 0)
        return (
            1 if self.explicit_percent else 0,
            -abs(EXACT_RATIO_TOTAL - self.total),
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
    return [evidence.material for evidence in _material_evidence(line)]


def _material_evidence(line: str) -> tuple[MaterialEvidence, ...]:
    cleaned = _strip_excluded_segments(normalize_text(line))
    if not cleaned:
        return ()

    occurrences: list[MaterialEvidence] = []
    occupied_spans: list[tuple[int, int]] = []
    for alias, material in MULTIWORD_ALIASES:
        for match in re.finditer(
            rf"(?<![a-z]){re.escape(alias)}(?![a-z])",
            cleaned,
        ):
            if any(
                match.start() < end and match.end() > start
                for start, end in occupied_spans
            ):
                continue
            occurrences.append(
                MaterialEvidence(material, match.start(), match.end())
            )
            occupied_spans.append(match.span())

    for match in _TOKEN_PATTERN.finditer(cleaned):
        if any(
            match.start() < end and match.end() > start
            for start, end in occupied_spans
        ):
            continue
        material = find_material_key(match.group())
        if material:
            occurrences.append(
                MaterialEvidence(material, match.start(), match.end())
            )

    ordered: list[MaterialEvidence] = []
    for evidence in sorted(occurrences, key=lambda item: (item.start, item.end)):
        # 인접한 동일 소재의 병기는 전체 위치를 보존한 하나의 근거로 묶는다.
        # 숫자나 다른 단어를 사이에 둔 반복 표기는 별도 근거로 남겨 검증한다.
        if (
            ordered
            and ordered[-1].material == evidence.material
            and _ALIAS_SEPARATOR_PATTERN.fullmatch(
                cleaned[ordered[-1].end : evidence.start]
            )
        ):
            ordered[-1] = MaterialEvidence(
                evidence.material,
                ordered[-1].start,
                evidence.end,
            )
            continue
        ordered.append(evidence)
    return tuple(ordered)


def _explicit_part(line: str) -> str | None:
    normalized = normalize_text(line)
    for part, aliases in PART_PATTERNS.items():
        if any(alias.casefold() in normalized for alias in aliases):
            return part
    return None


def detect_part(line: str, current_part: str) -> str:
    matched = _explicit_part(line)
    if matched:
        return matched
    return current_part


def _has_explicit_unknown_material_marker(
    line: str,
    numbers: tuple[Decimal, ...],
) -> bool:
    if not numbers or not extract_materials(line):
        return False
    if any(marker in line for marker in ("알 수 없는 소재", "未知繊維", "未知纤维")):
        return True
    return re.search(r"\bunknown\b", line, re.IGNORECASE) is not None


def _read_numbers(
    line: str,
    *,
    allow_plain_numbers: bool,
) -> tuple[tuple[Decimal, ...], bool, bool, tuple[NumberEvidence, ...]]:
    normalized = normalize_text(line)
    matches = list(_NUMBER_CANDIDATE_PATTERN.finditer(normalized))
    explicit_matches = [
        match for match in matches if match.group().strip().endswith("%")
    ]
    invalid = False

    def parse_match(
        match: re.Match[str],
    ) -> tuple[NumberEvidence | None, bool]:
        token = match.group().strip()
        has_percent = token.endswith("%")
        value_text = token.removesuffix("%").strip()
        prefix = normalized[: match.start()].rstrip()
        suffix = normalized[match.end() :]
        if _MEASUREMENT_UNIT_PATTERN.match(suffix):
            return None, False
        if not has_percent and (
            _PLAIN_NUMBER_METADATA_PREFIX.search(prefix)
            or re.fullmatch(r"(?:19|20)\d{2}", value_text)
        ):
            return None, False

        malformed = (
            not _NUMBER_VALUE_PATTERN.fullmatch(value_text)
            or re.match(r"[0-9%]", suffix) is not None
            or re.match(r"[.,](?=[0-9.,])", suffix) is not None
            or (not has_percent and re.match(r"[a-z]", suffix) is not None)
            or re.match(r"\s*%", suffix) is not None
            or (prefix and prefix[-1] in "0123456789.,")
            or (prefix and prefix[-1] in _INEXACT_SIGNS)
            or (suffix.strip() and suffix.strip()[0] in _INEXACT_SIGNS)
        )
        if malformed:
            return None, True

        try:
            value = Decimal(value_text.replace(",", "."))
        except InvalidOperation:
            return None, True
        if not value.is_finite() or not Decimal(0) < value <= EXACT_RATIO_TOTAL:
            return None, True

        return NumberEvidence(
            value=value,
            start=match.start(),
            end=match.end(),
            explicit_percent=has_percent,
        ), False

    explicit_values: list[NumberEvidence] = []
    for match in explicit_matches:
        evidence, match_invalid = parse_match(match)
        invalid = invalid or match_invalid
        if evidence is not None:
            explicit_values.append(evidence)

    invalid = invalid or normalized.count("%") != len(explicit_matches)
    values = list(explicit_values)
    material_count = len(extract_materials(normalized))

    # Plain numbers are considered only when explicit percentages do not
    # already account for every recognized material. This keeps identifiers,
    # years, and RN numbers from invalidating an otherwise complete ratio.
    needs_plain_values = not explicit_matches or material_count > len(values)
    if allow_plain_numbers and needs_plain_values:
        for match in matches:
            if match in explicit_matches:
                continue
            evidence, match_invalid = parse_match(match)
            invalid = invalid or match_invalid
            if evidence is not None:
                values.append(evidence)

    evidence = tuple(sorted(values, key=lambda item: item.start))
    result = tuple(item.value for item in evidence)
    invalid = invalid or _has_explicit_unknown_material_marker(normalized, result)
    explicit_percent = bool(evidence) and all(
        item.explicit_percent for item in evidence
    )
    return result, invalid, explicit_percent, evidence


def _contains_only_known_phrases(text: str, phrases: set[str]) -> bool:
    remainder = normalize_text(text)
    for phrase in sorted(phrases, key=len, reverse=True):
        if phrase.isascii():
            remainder = re.sub(
                rf"(?<![a-z]){re.escape(phrase.casefold())}(?![a-z])",
                " ",
                remainder,
            )
        else:
            remainder = remainder.replace(phrase.casefold(), " ")
    return _TOKEN_PATTERN.search(remainder) is None


def _same_line_pairing_is_supported(
    line: str,
    numbers: tuple[NumberEvidence, ...],
) -> bool:
    materials = _material_evidence(line)
    if not materials or len(materials) != len(numbers):
        return False

    material_first = all(
        material.end <= number.start
        and _contains_only_known_phrases(
            line[material.end : number.start],
            _RATIO_PAIR_DESCRIPTORS,
        )
        and (
            index == len(materials) - 1
            or (
                number.end <= materials[index + 1].start
                and _contains_only_known_phrases(
                    line[number.end : materials[index + 1].start],
                    _RATIO_PAIR_DESCRIPTORS,
                )
            )
        )
        for index, (material, number) in enumerate(zip(materials, numbers))
    )
    if material_first:
        return True

    ratio_first = all(
        number.end <= material.start
        and _contains_only_known_phrases(
            line[number.end : material.start],
            _RATIO_PAIR_DESCRIPTORS,
        )
        and (
            index == len(numbers) - 1
            or (
                material.end <= numbers[index + 1].start
                and _contains_only_known_phrases(
                    line[material.end : numbers[index + 1].start],
                    _RATIO_PAIR_DESCRIPTORS,
                )
            )
        )
        for index, (number, material) in enumerate(zip(numbers, materials))
    )
    if not ratio_first:
        return False

    return _contains_only_known_phrases(
        line[: numbers[0].start],
        _RATIO_PREFIX_CONTEXTS,
    )


def extract_numbers(line: str, allow_plain_numbers: bool = False) -> list[Decimal]:
    numbers, invalid, _, _ = _read_numbers(
        line,
        allow_plain_numbers=allow_plain_numbers,
    )
    return [] if invalid else list(numbers)


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


def _classify_metadata_line(
    line: str, pending_kind: str | None
) -> tuple[bool, str | None]:
    """명시한 항목의 값만 제외하며, 헤더의 대기 상태는 바로 다음 줄에만 적용한다."""
    header = _METADATA_HEADER_PATTERN.fullmatch(line)
    if header:
        kind = "size" if header.group("size") else "shrinkage"
        value = header.group("value").strip()
        if not value:
            return True, kind
    elif pending_kind:
        kind, value = pending_kind, line
    else:
        return False, None

    value = value.strip(" \t()[]")
    return _METADATA_VALUE_PATTERNS[kind].fullmatch(value) is not None, None


def build_line_infos(text: str) -> list[LineInfo]:
    infos: list[LineInfo] = []
    current_part = "generic"
    pending_metadata_kind: str | None = None
    prepared = _split_part_markers(normalize_text(text))

    for index, raw in enumerate(prepared.split("\n")):
        normalized = normalize_text(raw)
        if not normalized:
            continue

        is_metadata, pending_metadata_kind = _classify_metadata_line(
            normalized, pending_metadata_kind
        )
        explicit_part = None if is_metadata else _explicit_part(normalized)
        current_part = explicit_part or current_part
        composition_text = "" if is_metadata else _strip_excluded_segments(normalized)
        materials = tuple(extract_materials(composition_text))
        number_only_line = (
            not materials and not _TOKEN_PATTERN.search(composition_text)
        )
        allow_plain = bool(materials) or number_only_line
        numbers, invalid_evidence, explicit_percent, number_evidence = _read_numbers(
            composition_text,
            allow_plain_numbers=allow_plain,
        )
        if materials and numbers and len(materials) == len(numbers):
            invalid_evidence = invalid_evidence or not _same_line_pairing_is_supported(
                composition_text,
                number_evidence,
            )

        infos.append(
            LineInfo(
                index=index,
                raw=raw.strip(),
                normalized=normalized,
                part=current_part,
                materials=materials,
                numbers=numbers,
                explicit_percent=explicit_percent,
                invalid_evidence=invalid_evidence,
                explicit_part=explicit_part is not None,
                is_metadata=is_metadata,
            )
        )
    return infos


def _pair_values(
    part: str,
    materials: list[str] | tuple[str, ...],
    numbers: list[Decimal] | tuple[Decimal, ...],
    *,
    source: str,
    explicit_percent: bool,
    start_index: int,
    evidence_indices: frozenset[int],
) -> CompositionCandidate | None:
    if not materials or not numbers or len(materials) != len(numbers):
        return None

    paired: dict[str, Decimal] = {}
    for material, number in zip(materials, numbers):
        if material in paired or not (Decimal(0) < number <= EXACT_RATIO_TOTAL):
            return None
        paired[material] = number

    total = sum(paired.values(), Decimal(0))
    if total != EXACT_RATIO_TOTAL:
        return None

    return CompositionCandidate(
        part=part,
        materials=paired,
        source=source,
        explicit_percent=explicit_percent,
        start_index=start_index,
        evidence_indices=evidence_indices,
    )


def _collect_candidates(infos: list[LineInfo]) -> list[CompositionCandidate]:
    candidates: list[CompositionCandidate] = []

    for info in infos:
        if info.invalid_evidence:
            continue
        candidate = _pair_values(
            info.part,
            info.materials,
            info.numbers,
            source="same_line",
            explicit_percent=info.explicit_percent,
            start_index=info.index,
            evidence_indices=frozenset({info.index}),
        )
        if candidate:
            candidates.append(candidate)

    for position, info in enumerate(infos):
        if not info.materials or not info.numbers:
            continue

        materials: list[str] = []
        numbers: list[Decimal] = []
        explicit_percent = True
        evidence_indices: set[int] = set()
        for current in infos[position : position + 6]:
            if (
                current.part != info.part
                or current.invalid_evidence
                or not current.materials
                or not current.numbers
                or len(current.materials) != len(current.numbers)
            ):
                break
            materials.extend(current.materials)
            numbers.extend(current.numbers)
            evidence_indices.add(current.index)
            explicit_percent = explicit_percent and current.explicit_percent
            candidate = _pair_values(
                info.part,
                materials,
                numbers,
                source="line_pairs",
                explicit_percent=explicit_percent,
                start_index=info.index,
                evidence_indices=frozenset(evidence_indices),
            )
            if candidate and len(materials) > len(info.materials):
                candidates.append(candidate)

    for position, info in enumerate(infos):
        if not info.materials or info.numbers:
            continue

        alternating_materials: list[str] = []
        alternating_numbers: list[Decimal] = []
        evidence_indices: set[int] = set()
        cursor = position
        while cursor + 1 < len(infos) and len(alternating_materials) < 6:
            material_line = infos[cursor]
            ratio_line = infos[cursor + 1]
            if (
                material_line.part != info.part
                or ratio_line.part != info.part
                or material_line.invalid_evidence
                or ratio_line.invalid_evidence
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
            evidence_indices.update({material_line.index, ratio_line.index})
            cursor += 2

        candidate = _pair_values(
            info.part,
            alternating_materials,
            alternating_numbers,
            source="alternating_lines",
            explicit_percent=True,
            start_index=info.index,
            evidence_indices=frozenset(evidence_indices),
        )
        if candidate:
            candidates.append(candidate)

    for position, info in enumerate(infos):
        if not info.materials or info.numbers:
            continue

        material_block: list[str] = []
        number_block: list[Decimal] = []
        explicit_percent = True
        evidence_indices: set[int] = set()
        cursor = position

        while cursor < len(infos) and len(material_block) < 6:
            current = infos[cursor]
            if (
                current.part != info.part
                or current.invalid_evidence
                or current.numbers
                or not current.materials
            ):
                break
            material_block.extend(current.materials)
            evidence_indices.add(current.index)
            cursor += 1

        while cursor < len(infos) and len(number_block) < len(material_block):
            current = infos[cursor]
            if (
                current.part != info.part
                or current.invalid_evidence
                or current.materials
                or not current.numbers
            ):
                break
            number_block.extend(current.numbers)
            evidence_indices.add(current.index)
            explicit_percent = explicit_percent and current.explicit_percent
            cursor += 1

        candidate = _pair_values(
            info.part,
            material_block,
            number_block,
            source="stacked_columns",
            explicit_percent=explicit_percent,
            start_index=info.index,
            evidence_indices=frozenset(evidence_indices),
        )
        if candidate:
            candidates.append(candidate)

    for position, info in enumerate(infos):
        if not info.materials or info.numbers:
            continue

        for next_position in range(position + 1, min(position + 3, len(infos))):
            neighbor = infos[next_position]
            if (
                neighbor.part != info.part
                or neighbor.is_metadata
                or neighbor.invalid_evidence
                or neighbor.materials
            ):
                break
            candidate = _pair_values(
                info.part,
                info.materials,
                neighbor.numbers,
                source="adjacent_lines",
                explicit_percent=neighbor.explicit_percent,
                start_index=info.index,
                evidence_indices=frozenset({info.index, neighbor.index}),
            )
            if candidate:
                candidates.append(candidate)
                break

    return candidates


def _normalize_candidate(
    candidate: CompositionCandidate,
) -> tuple[dict[str, float | int], list[str]]:
    warnings: list[str] = []

    if not candidate.explicit_percent:
        warnings.append("ratio_marker_inferred")

    normalized: dict[str, float | int] = {}
    for material, value in candidate.materials.items():
        normalized[material] = (
            int(value) if value == value.to_integral_value() else float(value)
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
    best_by_part: dict[str, CompositionCandidate] = {}
    signatures_by_part: dict[str, set[tuple[tuple[str, Decimal], ...]]] = {}
    covered_indices_by_part: dict[str, set[int]] = {}

    for candidate in candidates:
        signatures_by_part.setdefault(candidate.part, set()).add(
            tuple(sorted(candidate.materials.items()))
        )
        covered_indices_by_part.setdefault(candidate.part, set()).update(
            candidate.evidence_indices
        )
        current = best_by_part.get(candidate.part)
        if current is None or candidate.score > current.score:
            best_by_part[candidate.part] = candidate

    ambiguous_parts = {
        part
        for part, signatures in signatures_by_part.items()
        if len(signatures) > 1
    }

    blocked_parts = set(ambiguous_parts)
    invalid_parts = {
        info.part
        for info in infos
        if info.invalid_evidence and (info.materials or info.numbers)
    }
    blocked_parts.update(invalid_parts)
    incomplete_parts = {
        info.part
        for info in infos
        if (info.materials or info.numbers or info.invalid_evidence)
        and info.index not in covered_indices_by_part.get(info.part, set())
    }
    blocked_parts.update(incomplete_parts)

    parts: dict[str, dict[str, float | int]] = {}
    warnings: list[str] = []
    for part, candidate in best_by_part.items():
        if part in blocked_parts:
            warning = (
                "ambiguous_composition_candidates"
                if part in ambiguous_parts
                else "invalid_composition_evidence"
            )
            warnings.append(f"{part}:{warning}")
            continue
        normalized, candidate_warnings = _normalize_candidate(candidate)
        parts[part] = normalized
        warnings.extend(f"{part}:{warning}" for warning in candidate_warnings)

    for part in sorted(blocked_parts - set(best_by_part)):
        warning = (
            "invalid_composition_evidence"
            if part in invalid_parts
            else "incomplete_composition_candidate"
        )
        warnings.append(f"{part}:{warning}")

    return parts, best_by_part, warnings, blocked_parts


def parse_parts(text: str) -> dict[str, dict[str, float | int]]:
    parts, _, _, _ = _best_candidates_by_part(text)
    return parts


def normalize_percentages(
    materials: dict[str, float],
) -> dict[str, float | int]:
    if not materials:
        return {}

    try:
        decimal_materials = {
            key: Decimal(str(value)) for key, value in materials.items()
        }
    except (InvalidOperation, ValueError):
        return {}
    if (
        any(
            not value.is_finite()
            or not Decimal(0) < value <= EXACT_RATIO_TOTAL
            for value in decimal_materials.values()
        )
        or sum(decimal_materials.values(), Decimal(0)) != EXACT_RATIO_TOTAL
    ):
        return {}
    candidate = CompositionCandidate(
        part="generic",
        materials=decimal_materials,
        source="same_line",
        explicit_percent=True,
        start_index=0,
        evidence_indices=frozenset({0}),
    )
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


def _choose_unblocked_representative(
    parts: dict[str, dict[str, float | int]],
    blocked_parts: set[str],
) -> tuple[str, dict[str, float | int]]:
    for part in PART_PRIORITY:
        if part in blocked_parts:
            return part, {}
        materials = parts.get(part)
        if materials:
            return part, materials
    return "", {}


def parse_materials(text: str) -> dict[str, float | int]:
    parts, _, _, blocked_parts = _best_candidates_by_part(text)
    _, materials = _choose_unblocked_representative(parts, blocked_parts)
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
        value = Decimal(str(percent))
        percent_text = (
            str(int(value))
            if value == value.to_integral_value()
            else format(value.normalize(), "f")
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
        "parse_evidence": {},
    }


def parse_label(text: str) -> dict:
    if not text or not text.strip():
        return failed_response(
            "",
            error_code="ocr_text_empty",
            message="OCR에서 라벨 텍스트를 추출하지 못했습니다.",
        )

    parts, candidates, warnings, blocked_parts = _best_candidates_by_part(text)
    selected_part, materials = _choose_unblocked_representative(
        parts,
        blocked_parts,
    )
    if not materials:
        error_code = (
            "ambiguous_composition"
            if any(
                item.startswith(f"{selected_part}:")
                and "ambiguous_composition_candidates" in item
                for item in warnings
            )
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
            "ratio_total_before_normalization": int(selected_candidate.total),
            "explicit_percent": selected_candidate.explicit_percent,
        },
    }
