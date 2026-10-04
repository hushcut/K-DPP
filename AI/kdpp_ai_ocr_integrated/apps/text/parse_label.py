import re
from collections import Counter
from dataclasses import replace, dataclass
from decimal import Decimal, InvalidOperation

from apps.text.ratio_contract import EXACT_RATIO_TOTAL, has_exact_total

from apps.text.composition_candidates import (
    CompositionCandidate,
    LineInfo,
    _collect_candidates,
    equivalent_composition as _equivalent_composition,
)

from apps.text.material_extraction import (
    PART_PATTERNS,
    ALIAS_TO_MATERIAL,
    _material_evidence,
    _strip_excluded_segments,
    _TOKEN_PATTERN,
    clean_ocr_preview,
    declared_part,
    extract_materials,
    find_material_key,
    is_part_marker_match,
    normalize_text,
    restore_registered_han_aliases,
    unresolved_material_tokens,
)
from apps.text.rules import (
    CARE_CONFLICTS,
    CARE_RULES,
    MATERIAL_KOREAN,
)


PART_PRIORITY = [
    "outer",
    "generic",
    "outer_2",
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

_RATIO_ROW_LABELS = COMPOSITION_HINTS | {
    normalize_text(alias) for aliases in PART_PATTERNS.values() for alias in aliases
}
_RATIO_ROW_LABEL_PATTERN = re.compile(
    "|".join(
        rf"(?<![a-z]){re.escape(label)}(?![a-z])" if label.isascii() else re.escape(label)
        for label in sorted(_RATIO_ROW_LABELS, key=len, reverse=True)
    )
)

_RATIO_NUMBER = r"([-+−]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+))"
_PERCENT_PATTERN = re.compile(
    rf"(?<![a-z0-9.+−-])(?<![0-9],){_RATIO_NUMBER}\s*[%％]",
    re.IGNORECASE,
)
_PLAIN_NUMBER_PATTERN = re.compile(
    rf"(?<![a-z0-9.+−-])(?<![0-9],){_RATIO_NUMBER}(?![a-z0-9.]|,[0-9])",
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


_NUMERIC_IDENTIFIER_ROW_PATTERN = re.compile(r"\(?\s*[0-9]+(?:\s*-\s*[0-9]+){1,3}\s*\)?")
_WASH_SYMBOL_OCR_PATTERN = re.compile(r"1(?:30|40|50|60|70|95)\s*[/\\]")
_PAREN_WASH_SYMBOL_OCR_PATTERN = re.compile(r"\(\s*(?:30|40|50|60|70|95)0\s*\)?")
_NUMBERED_OUTER_MARKER_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:outshell|cutshell|shell|outer|겉\s*감)\s*[12](?![a-z0-9.,]|\s*%)"
)
_STORAGE_DOWN_PATTERN = re.compile(r"(?<![a-z])(?:fold|ford)\s+down(?![a-z])")


def _has_complete_preceding_composition(infos: list[LineInfo]) -> bool:
    if not infos or infos[-1].is_metadata or infos[-1].invalid_evidence:
        return False
    return any(
        candidate.part == infos[-1].part and candidate.explicit_percent
        and candidate.row_indices and candidate.row_indices[-1] == infos[-1].index
        and has_exact_total(candidate.materials.values())
        for candidate in _collect_candidates(infos[-12:])
    )


def _is_non_composition_numeric_row(
    line: str, previous: LineInfo | None, following: str,
    *, preceding_infos: list[LineInfo] | None = None,
) -> bool:
    """Recognize whole identifier rows and a narrow wash-symbol OCR shape."""

    if _NUMERIC_IDENTIFIER_ROW_PATTERN.fullmatch(line):
        groups = re.findall(r"[0-9]+", line)
        # Long hyphenated product/contact numbers cannot be percentage ranges.
        return sum(map(len, groups)) >= 7 and max(map(len, groups)) >= 4
    # A tub outline can turn 30 degrees into '(300'. Keep explicit ratios,
    # incomplete blocks and plain out-of-range numbers under normal validation.
    if _PAREN_WASH_SYMBOL_OCR_PATTERN.fullmatch(line):
        return _has_complete_preceding_composition(preceding_infos or [])
    if line in {"30", "40", "50", "60", "70", "95"} and (
        previous is not None
        and not previous.is_standalone_marker
        and not any(hint in previous.normalized for hint in COMPOSITION_HINTS)
        and _mentions_care(following)
        and not extract_materials(following)
        and "%" not in following
        and not any(hint in following for hint in COMPOSITION_HINTS)
    ):
        # Vision often puts the wash-tub temperature directly before HAND WASH.
        # Do not use that number to complete a partial fiber composition.
        return True
    # A tub outline can become a leading 1 and trailing slash around its
    # temperature. Require an explicit fiber row immediately before it;
    # a composition/part heading or a percent sign must never be discarded.
    return bool(
        _WASH_SYMBOL_OCR_PATTERN.fullmatch(line)
        and previous is not None
        and not previous.is_metadata
        and not previous.invalid_evidence
        and previous.explicit_percent
        and previous.materials
        and len(previous.materials) == len(previous.numbers)
    )


def _is_metadata_line(info: LineInfo) -> bool:
    """Whether an OCR row is safe to skip while pairing composition rows."""

    if info.is_metadata:
        return True
    if any(phrase in info.normalized for phrase in DESCRIPTIVE_MATERIAL_PHRASES):
        return True
    # Metadata headings cannot erase a fiber declaration. Unknown fibers and
    # rows with material/percentage evidence still need composition validation.
    if (
        info.unresolved_materials
        or (info.materials and "%" in info.normalized)
        or (info.invalid_evidence and _has_invalid_numeric_row(info))
        or _is_unresolved_percent_row(info)
    ):
        return False
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
    if info.materials or info.explicit_percent or (info.invalid_evidence and "%" in info.normalized and _is_ratio_only_composition_row(info)):
        return False

    # Product codes often appear between a material and its percentage in
    # Vision's paragraph order. They contain letters with digits, or several
    # bare numeric groups, but never form a material/ratio pair by themselves.
    has_letters = bool(re.search(r"[a-z가-힣一-龥ぁ-んァ-ン]", info.normalized))
    has_digits = bool(re.search(r"\d", info.normalized))
    if has_letters and has_digits:
        return True
    return len(_PLAIN_NUMBER_PATTERN.findall(info.normalized)) >= 2


def extract_numbers(line: str, allow_plain_numbers: bool = False) -> list[Decimal]:
    numbers, invalid, _, _ = _read_numbers(
        line,
        allow_plain_numbers=allow_plain_numbers,
    )
    return [] if invalid else list(numbers)


def _split_part_markers(text: str) -> str:
    markers = {
        alias
        for aliases in PART_PATTERNS.values()
        for alias in aliases
        if len(alias) >= 2
    }
    prepared_lines: list[str] = []
    for line in text.split("\n"):
        prepared_line = line
        for marker in sorted(markers, key=len, reverse=True):
            suffix = re.search(
                rf"(?i)({_part_alias_pattern(marker)})"
                r"[\s)\]}>:;,./|\-‐‑‒–—]*$",
                prepared_line,
            )
            if not suffix or suffix.start() == 0:
                continue

            composition = prepared_line[: suffix.start()].rstrip(
                " \t([{<:;,./|-‐‑‒–—"
            )
            if extract_materials(composition):
                prepared_line = f"{composition} {suffix.group(1)}"
                break
        prepared_lines.append(prepared_line)

    prepared = "\n".join(prepared_lines)
    for marker in sorted(markers, key=len, reverse=True):
        prepared = re.sub(
            rf"(?i)(?<!^)(?<!\n)({_part_alias_pattern(marker)})"
            r"(?=[^\n]*[0-9a-zà-ÿ가-힣一-龥ぁ-んァ-ン])",
            lambda match: "\n" + match.group() if is_part_marker_match(prepared, match) else match.group(),
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


_WRAPPED_ALIAS_PATTERN = re.compile(r"([^\W\d_]+)[ \t]*\n[ \t]*([^\W\d_]+)")
_LANGUAGE_RATIO_PREFIX_PATTERN = re.compile(
    r"(?<![\w])(?:en|uk|us|fr|de|es|es-mx|cat|pt|it|jp|cn|nl|cz|dk|fi|no|pl|"
    r"sk|se|si|hr|lt|lv|ee|kr|ru|tr|el)\s*:\s*(?=[0-9]+(?:[.,][0-9]+)?\s*%)"
)


def _prepare_multilingual_rows(text: str) -> str:
    """Restore exact wrapped aliases and separate explicit language blocks."""

    text = restore_registered_han_aliases(text, allow_newlines=True)

    def restore_alias(match: re.Match[str]) -> str:
        joined = match.group(1) + match.group(2)
        # A complete table entry is required; partial or fuzzy words stay put.
        return (
            joined if match.group(1) not in ALIAS_TO_MATERIAL
            and joined in ALIAS_TO_MATERIAL else match.group()
        )

    for _ in range(3):
        restored = _WRAPPED_ALIAS_PATTERN.sub(restore_alias, text)
        if restored == text:
            break
        text = restored
    # Restore only complete registered multiword names, across OCR row breaks.
    for alias in ALIAS_TO_MATERIAL:
        if " " not in alias:
            continue
        pattern = r"(?<!\w)" + r"[ \t\n]+".join(map(re.escape, alias.split())) + r"(?!\w)"
        text = re.sub(pattern, lambda match, alias=alias: alias if "\n" in match.group() else match.group(), text)
    # Keep the printed percent sign, attaching only its standalone OCR row.
    text = re.sub(r"(?m)^(.*[0-9])[ \t]*\n[ \t]*%[ \t]*$", r"\1%", text)
    # Each language's percentages remain independent; conflicting copies
    # must still produce conflicting candidates rather than being deduplicated.
    return _LANGUAGE_RATIO_PREFIX_PATTERN.sub("\n", text)


def build_line_infos(text: str) -> list[LineInfo]:
    infos: list[LineInfo] = []
    current_part = "generic"
    pending_metadata_kind = None
    original_prepared = _split_part_markers(normalize_text(text))
    prepared = _split_part_markers(_prepare_multilingual_rows(original_prepared))
    original_rows = Counter(normalize_text(original_prepared).splitlines())
    prepared_rows = Counter(normalize_text(prepared).splitlines())
    restored_rows = {row for row, count in prepared_rows.items() if count > original_rows[row]}
    raw_lines = prepared.split("\n")
    content_indices = [i for i, raw in enumerate(raw_lines) if normalize_text(raw)]
    last_content_index = content_indices[-1] if content_indices else -1
    following_lines = {
        current: normalize_text(raw_lines[following])
        for current, following in zip(content_indices, content_indices[1:])
    }
    for position, index in enumerate(content_indices[:-1]):
        if following_lines[index] != "neutral":
            continue
        # Printed NEUTRAL DETERGENT HAND WASH may span three OCR rows.
        # Join only this care prefix, keeping fiber/percent guards below.
        care_context = " ".join(
            normalize_text(raw_lines[following])
            for following in content_indices[position + 1:position + 4]
        )
        if care_context.startswith("neutral detergent "):
            following_lines[index] = care_context
    for index, raw in enumerate(raw_lines):
        normalized = normalize_text(raw)
        if not normalized:
            continue
        is_metadata, pending_metadata_kind = _classify_metadata_line(normalized, pending_metadata_kind)
        if not is_metadata:
            is_metadata = _is_non_composition_numeric_row(
                normalized, infos[-1] if infos else None, following_lines.get(index, ""),
                preceding_infos=infos,
            )
        inferred_metadata = False
        if not is_metadata and _is_unlabeled_korean_garment_size(
            normalized, infos[-1] if infos else None, is_last_line=index == last_content_index,
        ):
            is_metadata = inferred_metadata = True
        marker_part = None if is_metadata else declared_part(normalized)
        current_part = marker_part or current_part
        composition_text = "" if is_metadata else _strip_excluded_segments(normalized)
        # FOLD DOWN describes storage, not down filling. Mask only that
        # action phrase; all remaining fibers and percentages still count.
        composition_text = _STORAGE_DOWN_PATTERN.sub(
            lambda match: " " * len(match.group()), composition_text,
        )
        # Heading indices name separate fabrics; they are not fiber ratios.
        composition_text = normalize_text(_NUMBERED_OUTER_MARKER_PATTERN.sub(
            lambda match: re.sub(r"[12]", " ", match.group()), composition_text,
        ))
        materials = tuple(extract_materials(composition_text))
        number_only_line = not materials and not _TOKEN_PATTERN.search(composition_text)
        numbers, invalid_evidence, explicit_percent, number_evidence = _read_numbers(
            composition_text, allow_plain_numbers=bool(materials) or number_only_line,
        )
        invalid_evidence |= bool(_IMITATION_LEATHER_PATTERN.search(composition_text))
        if materials and normalized in restored_rows:
            # Joining an alias must not move an unknown continuation into an
            # unchecked trailing suffix of a material/ratio row.
            invalid_evidence |= not _contains_only_known_phrases(
                composition_text, _MATERIAL_ONLY_LINE_CONTEXTS,
            )
        if materials and not numbers:
            invalid_evidence |= not _contains_only_known_phrases(composition_text, _MATERIAL_ONLY_LINE_CONTEXTS)
        if materials and numbers and len(materials) == len(numbers):
            invalid_evidence |= not _same_line_pairing_is_supported(composition_text, number_evidence)
        unresolved = unresolved_material_tokens(composition_text)
        if _has_explicit_unknown_material_marker(composition_text, numbers):
            unresolved.append("unknown")
        infos.append(LineInfo(
            index=index, raw=raw.strip(), normalized=normalized, part=current_part,
            materials=materials, numbers=numbers, explicit_percent=explicit_percent,
            unresolved_materials=tuple(unresolved),
            marker_part=marker_part, invalid_evidence=invalid_evidence,
            is_metadata=is_metadata, inferred_metadata=inferred_metadata,
        ))
    return _mark_split_imitation_leather(_apply_trailing_part_markers(_mark_leading_garment_size(infos)))


def _mark_leading_garment_size(infos: list[LineInfo]) -> list[LineInfo]:
    """Infer a small header size only before an origin row and complete content."""
    first = next((position for position, info in enumerate(infos) if info.materials), None)
    if first is None:
        return infos
    prefix = infos[:first]
    sizes = [info for info in prefix if info.normalized in {"0", "1", "2", "3", "4", "5"}]
    if len(sizes) != 1 or not any(re.search(r"(?<![a-z])made\s+in\s+[a-z]+", info.normalized) for info in prefix):
        return infos
    size = sizes[0]
    if any(
        info.explicit_percent or info.unresolved_materials or info.marker_part is not None
        or any(hint in info.normalized for hint in COMPOSITION_HINTS)
        or (info is not size and (info.numbers or info.invalid_evidence))
        for info in prefix
    ):
        return infos
    if not any(
        candidate.start_index == infos[first].index
        and has_exact_total(candidate.materials.values())
        for candidate in _collect_candidates(infos[first:])
    ):
        return infos
    return [replace(info, numbers=(), is_metadata=True, inferred_metadata=True)
            if info is size else info for info in infos]


def _mark_split_imitation_leather(infos: list[LineInfo]) -> list[LineInfo]:
    """Preserve a negating modifier split by OCR, within its own part only."""

    adjusted = list(infos)
    for position in range(1, len(infos)):
        previous, current = infos[position - 1], infos[position]
        if (
            previous.part != current.part
            or _is_metadata_line(previous)
            or _is_metadata_line(current)
            or current.marker_part is not None
        ):
            continue
        boundary = len(previous.normalized)
        joined = f"{previous.normalized}\n{current.normalized}"
        if any(
            match.start() < boundary < match.end()
            for match in _IMITATION_LEATHER_PATTERN.finditer(joined)
        ):
            adjusted[position] = replace(current, invalid_evidence=True)
    return adjusted


def _has_invalid_numeric_row(info: LineInfo) -> bool:
    """Reject malformed ratio-shaped rows without converting unbounded ints."""

    if not _is_ratio_only_composition_row(info):
        return False
    if re.fullmatch(r"[0-9]+", info.normalized):
        # Small bare zero/out-of-range integers remain ignorable identifiers.
        # Excessively long numeric tokens are unsafe OCR evidence, not a size.
        if len(info.normalized) > 128:
            return True
        return Decimal(0) < Decimal(info.normalized) <= Decimal(125)
    return bool(_NUMBER_CANDIDATE_PATTERN.search(info.normalized))


def _is_ratio_only_composition_row(info: LineInfo) -> bool:
    """조성 제목·부위명 외에는 소재 없이 비율만 남은 행인지 확인한다."""

    if info.materials:
        return False
    text = _strip_excluded_segments(info.normalized)
    remaining = _RATIO_ROW_LABEL_PATTERN.sub(
        lambda match: " " if is_part_marker_match(text, match) else match.group(),
        text,
    )
    return not _TOKEN_PATTERN.search(remaining)


def _is_unresolved_percent_row(info: LineInfo) -> bool:
    """유효 비율을 읽지 못해도 미등록 소재의 퍼센트 표기는 보존한다."""

    metadata_header = _METADATA_HEADER_PATTERN.fullmatch(info.normalized)
    if (
        metadata_header
        and not metadata_header.group("measurement")
        and _looks_like_non_composition_number(info.normalized)
        and not _TOKEN_PATTERN.search(metadata_header.group("value"))
    ):
        # Retain numeric-only fields already treated as metadata. Any fiber
        # words on the same row still require composition validation.
        return False

    return (
        not info.materials
        and "%" in _strip_excluded_segments(info.normalized)
        # Only strictly classified metadata is safe to discard. Product/date
        # text on a shared row must not hide an unknown fiber declaration.
        and not info.is_metadata
        and not _mentions_care(info.normalized)
        and not any(phrase in info.normalized for phrase in DESCRIPTIVE_MATERIAL_PHRASES)
        and not _is_ratio_only_composition_row(info)
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
        decimal_value = Decimal(str(value))
        normalized[material] = int(decimal_value) if decimal_value == decimal_value.to_integral_value() else float(decimal_value)
    if not has_exact_total(normalized.values()):
        return {}, [*warnings, "ratio_precision_loss"]
    return normalized, warnings


def _translated_alias_rows(
    infos: list[LineInfo], candidates: list[CompositionCandidate]
) -> set[int]:
    """Cover adjacent, ratio-free translations of a confirmed single fiber.

    A translation line must contain two complete aliases for that same fiber.
    An unrelated or unresolved material ends the group and still blocks the
    composition under the normal unpaired-row rule.
    """
    by_index = {info.index: info for info in infos}
    covered: set[int] = set()
    anchors = (
        candidate for candidate in candidates
        if candidate.source == "same_line"
        and candidate.explicit_percent
        and len(candidate.materials) == 1
    )
    for candidate in anchors:
        material = next(iter(candidate.materials))
        for step in (-1, 1):
            cursor = candidate.start_index + step
            while (info := by_index.get(cursor)) is not None:
                if (
                    info.part != candidate.part
                    or info.marker_part is not None
                    or info.unresolved_materials
                    or info.materials != (material,)
                ):
                    break
                if info.numbers:
                    if info.numbers != (100.0,) or not info.explicit_percent:
                        break
                else:
                    if "%" in info.normalized or "％" in info.normalized:
                        break
                    aliases = [
                        find_material_key(token)
                        for token in _TOKEN_PATTERN.findall(info.normalized)
                    ]
                    if sum(alias == material for alias in aliases) < 2:
                        break
                    covered.add(info.index)
                cursor += step
    return covered


def _best_candidates_by_part(
    text: str,
    *,
    conflicting_parts: tuple[str, ...] = (),
    unpaired_ratio_parts: tuple[str, ...] = (),
    rejected_composition_parts: dict[str, tuple[str, ...]] | None = None,
) -> tuple[
    dict[str, dict[str, float | int]],
    dict[str, CompositionCandidate],
    list[str],
    set[str],
    dict,
]:
    infos = build_line_infos(text)
    candidates = []
    segment = []
    body_measurement_block = False
    for info in infos:
        # A complete body-measurement block is ignorable; an isolated SIZE
        # header must never bridge a material to a later percentage.
        if any(word in info.normalized for word in ("신체치수", "가슴둘레", "허리둘레")):
            body_measurement_block = True
        if info.is_metadata and not body_measurement_block:
            candidates.extend(_collect_candidates(segment))
            segment = []
        elif not _is_metadata_line(info) and not info.invalid_evidence:
            segment.append(info)
            if info.materials or info.numbers:
                body_measurement_block = False
    candidates.extend(_collect_candidates(segment))
    heading_indices = _composition_heading_indices(infos)
    best_by_part: dict[str, CompositionCandidate] = {}
    ambiguous_parts: set[str] = set(conflicting_parts)

    for candidate in candidates:
        current = best_by_part.get(candidate.part)
        # Scores choose the clearest representation of an agreed composition;
        # they cannot resolve contradictory declarations for the same part.
        if current is not None and _equivalent_composition(
            candidate.materials
        ) != _equivalent_composition(current.materials):
            ambiguous_parts.add(candidate.part)
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

    # A row naming a fiber the table cannot resolve has no trustworthy
    # material/ratio mapping: its ratio would silently move to a neighbour.
    unresolved_percent_indices = {
        info.index for info in infos if _is_unresolved_percent_row(info)
    }
    composition_rows = [
        info for info in infos
        if (info.materials or info.unresolved_materials or info.index in unresolved_percent_indices)
        and not _is_metadata_line(info)
    ]
    unresolved_parts = {
        info.part for info in composition_rows
        if info.unresolved_materials or info.index in unresolved_percent_indices
    }
    # Every recognized material row must belong to a complete candidate.
    # A valid 100% row cannot hide an unpaired row before or after it. Keep
    # coverage from all complete blocks so multilingual repetitions remain valid.
    covered_rows = {index for candidate in candidates for index in candidate.row_indices}
    covered_rows.update(_translated_alias_rows(infos, candidates))
    incomplete_parts = {
        info.part for info in composition_rows
        if info.materials and info.index not in covered_rows
    }

    # OCR can lose a material/part name but retain its standalone percentage.
    # Do not let another complete block hide that missing composition (QA031).
    # 조성 제목·부위명만 붙은 비율 행도 포함한다. 세탁·홍보·제품 정보는 제외한다.
    orphan_ratio_parts = set(unpaired_ratio_parts) | {
        info.part for info in infos
        if (info.explicit_percent or info.numbers)
        and not info.materials
        and _is_ratio_only_composition_row(info)
        and info.index not in covered_rows
        and not _is_metadata_line(info)
    }

    observed_ratios: dict[str, list[float]] = {}
    # % 없는 숫자 행도 잔여 비율 검사와 같은 기준으로 비교 근거에 남긴다.
    for info in infos:
        if not _is_metadata_line(info) and (
            info.materials
            or info.unresolved_materials
            or info.index in unresolved_percent_indices
            or (
                (info.explicit_percent or info.numbers)
                and _is_ratio_only_composition_row(info)
            )
        ):
            observed_ratios.setdefault(info.part, []).extend(float(value) for value in info.numbers)
    ratio_evidence = {
        "observed_ratios": observed_ratios,
        "unpaired_ratio_parts": sorted(orphan_ratio_parts),
    }

    # A malformed composition row must also block a different, complete block
    # in the same part. Keep lower-priority parts independent of a valid shell.
    invalid_ratio_parts = {
        info.part for info in infos
        if (info.materials or _is_ratio_only_composition_row(info))
        and (info.explicit_percent or info.materials or "%" in info.normalized)
        and not _is_metadata_line(info)
        and any(
            not 0 < Decimal(match.group(1)) <= 100
            for match in _PERCENT_PATTERN.finditer(_strip_excluded_segments(info.normalized).replace("−", "-"))
        )
    }

    invalid_evidence_parts = {
        info.part for info in infos if info.invalid_evidence and not _is_metadata_line(info)
        and (info.materials or "%" in info.normalized
             or _has_invalid_numeric_row(info))
    }
    parts: dict[str, dict[str, float | int]] = {}
    warnings: list[str] = [
        *(f"{part}:invalid_composition_evidence" for part in sorted(invalid_evidence_parts)),
        *(f"{part}:unresolved_material_token" for part in sorted(unresolved_parts - best_by_part.keys())),
        *(f"{part}:invalid_ratio" for part in sorted(invalid_ratio_parts)),
        *(f"{part}:unpaired_ratio_rows"
          for part in sorted(orphan_ratio_parts - best_by_part.keys())),
        *(f"{part}:ambiguous_composition_candidates"
          for part in sorted(ambiguous_parts - best_by_part.keys())),
    ]
    for part, candidate in best_by_part.items():
        if part in invalid_ratio_parts or part in invalid_evidence_parts:
            continue
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
        warnings.extend(f"{part}:{warning}" for warning in candidate_warnings)
        if normalized:
            parts[part] = normalized

    expected_parts = (
        invalid_evidence_parts | invalid_ratio_parts | orphan_ratio_parts | ambiguous_parts
        | {info.part for info in composition_rows}
        | {info.marker_part for info in infos if info.marker_part is not None}
    )

    # 후보가 실패해도 확인한 소재와 안전한 소재/비율 연결을 잃지 않는다.
    observed_materials: dict[str, list[str]] = {}
    paired_material_ratios: dict[str, list[tuple[str, float]]] = {}
    for info in composition_rows:
        observed_materials.setdefault(info.part, []).extend(info.materials)
        if (
            info.materials and len(info.materials) == len(info.numbers)
            and not info.invalid_evidence and not info.unresolved_materials
        ):
            paired_material_ratios.setdefault(info.part, []).extend(
                (material, float(ratio))
                for material, ratio in zip(info.materials, info.numbers)
            )
    rejections: dict[str, set[str]] = {}
    # 충돌과 잔여 비율은 전용 메타데이터로 해소한다. 같은 부위의 다른
    # 거절 사유까지 제외하면 숫자 복원만으로 미등록 소재·수치 오류가 숨겨진다.
    independent_reasons = {
        "invalid_composition_evidence": invalid_evidence_parts,
        "invalid_ratio": invalid_ratio_parts,
        "unresolved_material_token": unresolved_parts,
        "unpaired_material_rows": incomplete_parts,
    }
    for part in expected_parts - parts.keys():
        reasons = {
            warning.split(":", 1)[1] for warning in warnings
            if warning.startswith(f"{part}:")
        } - {"ambiguous_composition_candidates", "unpaired_ratio_rows"}
        reasons.update(
            reason for reason, affected_parts in independent_reasons.items()
            if part in affected_parts
        )
        if not reasons and part not in ambiguous_parts | orphan_ratio_parts:
            reasons.add("unpaired_material_rows")
        if reasons:
            rejections[part] = reasons
    for part, reasons in (rejected_composition_parts or {}).items():
        parts.pop(part, None)
        expected_parts.add(part)
        rejections.setdefault(part, set()).update(reasons)
        for reason in reasons:
            warning = f"{part}:{reason}"
            if warning not in warnings:
                warnings.append(warning)
    ratio_evidence.update({
        "observed_materials": observed_materials,
        "paired_material_ratios": {
            part: [list(pair) for pair in pairs]
            for part, pairs in paired_material_ratios.items()
        },
        "rejected_composition_parts": {
            part: sorted(reasons) for part, reasons in sorted(rejections.items())
        },
    })

    if any(info.inferred_metadata for info in infos):
        warnings.append("unlabeled_garment_size_inferred")
    return parts, best_by_part, warnings, expected_parts, ratio_evidence


def parse_parts(text: str) -> dict[str, dict[str, float | int]]:
    parts, _, _, _, _ = _best_candidates_by_part(text)
    return parts


def normalize_percentages(
    materials: dict[str, Decimal | float | int],
) -> dict[str, float | int]:
    if not has_exact_total(materials.values()):
        return {}

    candidate = CompositionCandidate(
        part="generic",
        materials={key: Decimal(str(value)) for key, value in materials.items()},
        source="same_line",
        explicit_percent=True,
        start_index=0,
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


def parse_materials(text: str) -> dict[str, float | int]:
    """Expose materials only after the same safety checks as the label response."""
    return parse_label(text)["materials"]


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
            else str(float(percent))
        )
        parts.append(f"{korean} {percent_text}%")
    return ", ".join(parts)


def parse_care(text: str) -> str:
    normalized = normalize_text(text)
    found: set[str] = set()
    matches: list[tuple[int, int, str]] = []
    for korean, aliases in CARE_RULES.items():
        for alias in aliases:
            phrase = r"\s+".join(re.escape(word) for word in alias.casefold().split())
            for match in re.finditer(rf"(?<![a-z]){phrase}(?![a-z])", normalized):
                matches.append((match.start(), match.end(), korean))

    # Match prohibitions and specific methods before their embedded general
    # phrases (HAND WASH COLD contains WASH COLD; 손세탁 금지 contains 세탁 금지).
    occupied: list[tuple[int, int]] = []
    for start, end, korean in sorted(
        matches, key=lambda item: (item[2].endswith("금지"), item[1] - item[0]), reverse=True
    ):
        if any(start < right and end > left for left, right in occupied):
            continue
        occupied.append((start, end))
        if not korean.endswith("금지") and re.search(
            r"\b(?:not|no|never|don't|dont)\s*$", normalized[:start]
        ):
            continue
        found.add(korean)

    blocked = {rule for matched in found for rule in CARE_CONFLICTS.get(matched, set())}
    found.difference_update(blocked)

    return "; ".join(rule for rule in CARE_RULES if rule in found)


def failed_response(
    raw_text: str = "",
    *,
    error_code: str = "composition_not_found",
    message: str = "소재 혼용률을 신뢰할 수 있게 인식하지 못했습니다.",
    warnings: list[str] | None = None,
    parse_evidence: dict | None = None,
) -> dict:
    care_instruction = parse_care(raw_text)
    result = {
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
    if parse_evidence is not None:
        result["parse_evidence"] = parse_evidence
    return result


def parse_label(
    text: str,
    *,
    conflicting_parts: tuple[str, ...] = (),
    unpaired_ratio_parts: tuple[str, ...] = (),
    rejected_composition_parts: dict[str, tuple[str, ...]] | None = None,
) -> dict:
    """OCR 후보의 상충 부위도 포함해 최종 대표 조성을 안전하게 판단한다."""

    if not text or not text.strip():
        return failed_response(
            "",
            error_code="ocr_text_empty",
            message="OCR에서 라벨 텍스트를 추출하지 못했습니다.",
        )

    parts, candidates, warnings, expected_parts, ratio_evidence = _best_candidates_by_part(
        text, conflicting_parts=conflicting_parts, unpaired_ratio_parts=unpaired_ratio_parts,
        rejected_composition_parts=rejected_composition_parts,
    )
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
            parse_evidence=ratio_evidence,
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
            parse_evidence=ratio_evidence,
        )

    selected_candidate = candidates[selected_part]
    parser_confidence = (
        "high"
        if selected_candidate.explicit_percent
        and has_exact_total(selected_candidate.materials.values())
        and selected_candidate.source == "same_line"
        and "unlabeled_garment_size_inferred" not in warnings
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
            **ratio_evidence,
            "composition_status": "confirmed",
            "source": selected_candidate.source,
            "ratio_total_before_normalization": int(selected_candidate.total),
            "explicit_percent": selected_candidate.explicit_percent,
        },
    }


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
_IMITATION_LEATHER_PATTERN = re.compile(
    r"(?<![a-z])(?:faux|fake|synthetic|artificial|imitation|vegan|pu|pvc)"
    r"[\s\-‐‑‒–—_/]*(?:leather(?![a-z])|가죽|피혁|레더)|"
    r"(?:인조|합성|모조|비건)[\s\-‐‑‒–—_/]*(?:가죽|피혁|레더)|"
    r"(?:人造|合成|人工|仿)[\s\-‐‑‒–—_/]*(?:皮革|革)|"
    r"(?:フェイク|合成|人工|ヴィーガン)[\s\-‐‑‒–—_/]*(?:レザー|皮革)|"
    r"(?<![a-z])simili[\s\-‐‑‒–—_/]*cuir(?![a-z])|"
    r"(?<![a-z])kunst[\s\-‐‑‒–—_/]*leder(?![a-z])",
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
    r"(?P<measurement>신체\s*치수|가슴\s*둘레|허리\s*둘레)|"
    r"(?P<shrinkage>shrinkage(?:\s+rate)?(?![a-z])|수축률|수축율))"
    r"\s*[:=]?\s*(?P<value>.*)",
)
_METADATA_VALUE_PATTERNS = {
    "measurement": re.compile(
        r"[0-9]+(?:[.,][0-9]+)?(?:\s*[-/x×]\s*[0-9]+(?:[.,][0-9]+)?)*\s*(?:cm|mm)?"
    ),
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
# 한국 의류 호칭에서 흔한 5단위 값만 무표기 사이즈 후보로 인정한다.
_UNLABELED_KOREAN_GARMENT_SIZE_VALUES = {
    str(value) for value in range(80, 125, 5)
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
    "fabric",
    "content",
    "body",
    "組成",
    "組成表示",
    "纤维",
    "纤维成分",
    "成分",
}
_EXPLICIT_PART_HEADER_CONTEXTS = _RATIO_PREFIX_CONTEXTS | {
    "fabric",
    "재질",
}



_MATERIAL_ONLY_LINE_CONTEXTS = set(ALIAS_TO_MATERIAL) | _RATIO_PAIR_DESCRIPTORS | _EXPLICIT_PART_HEADER_CONTEXTS

@dataclass(frozen=True)
class NumberEvidence:
    value: Decimal
    start: int
    end: int
    explicit_percent: bool


def _part_alias_pattern(alias: str) -> str:
    escaped = re.escape(alias.casefold())
    if alias.isascii():
        return rf"(?<![a-z]){escaped}(?![a-z])"
    return escaped


def _has_explicit_unknown_material_marker(
    line: str,
    numbers: tuple[Decimal, ...],
) -> bool:
    if not numbers and "%" not in line:
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
    material_evidence = _material_evidence(normalized)
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
        # A comma immediately after a fiber separates the next ratio, not a fractional value.
        if value_text.startswith(",") and _material_evidence(normalized[:match.start()]):
            value_text = value_text[1:]
        prefix = normalized[: match.start()].rstrip()
        suffix = normalized[match.end() :]
        comma_prefix = _strip_excluded_segments(prefix)
        comma_materials = _material_evidence(comma_prefix)
        valid_material_comma = (
            prefix.endswith(",")
            and bool(comma_materials)
            and comma_prefix[comma_materials[-1].end :].strip() == ","
        )
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
            or (
                prefix
                and prefix[-1] in "0123456789.,"
                and not valid_material_comma
            )
            or (prefix and prefix[-1] in _INEXACT_SIGNS and not (
                prefix.endswith("-") and match.start() > 0
                and normalized[match.start() - 1].isspace() and _material_evidence(prefix[:-1])
            ))
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
    material_count = len(material_evidence)

    # Plain numbers are considered only when explicit percentages do not
    # already account for every recognized material. This keeps identifiers,
    # years, and RN numbers from invalidating an otherwise complete ratio.
    needs_plain_values = not explicit_matches or material_count > len(values)
    if _mentions_care(normalized) and (
        explicit_matches or not any(phrase in normalized for phrase in _CARE_PHRASES)
    ):
        needs_plain_values = False
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
    # Use the same normalized aliases and OCR corrections as extraction. This
    # preserves multilingual names such as bombaž that normalize to bombaz.
    if phrases is _MATERIAL_ONLY_LINE_CONTEXTS:
        for evidence in reversed(_material_evidence(remainder)):
            remainder = remainder[:evidence.start] + " " * (evidence.end - evidence.start) + remainder[evidence.end:]
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

    # A flattened material column followed by its ratio column is supported,
    # but an unknown fiber or a ratio-first list cannot silently shift pairs.
    if (
        len(materials) > 1
        and materials[-1].end <= numbers[0].start
        and _contains_only_known_phrases(line[:materials[0].start], _RATIO_PREFIX_CONTEXTS)
        and all(
            _contains_only_known_phrases(line[left.end:right.start], _RATIO_PAIR_DESCRIPTORS)
            for left, right in zip(materials, materials[1:])
        )
        and _contains_only_known_phrases(line[materials[-1].end:numbers[0].start], _RATIO_PAIR_DESCRIPTORS)
        and all(
            re.fullmatch(r"[\s,;:/|]*", line[left.end:right.start])
            for left, right in zip(numbers, numbers[1:])
        )
    ):
        return True

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


def _classify_metadata_line(
    line: str, pending_kind: str | None
) -> tuple[bool, str | None]:
    """명시한 항목의 값만 제외하며, 헤더의 대기 상태는 바로 다음 줄에만 적용한다."""
    header = _METADATA_HEADER_PATTERN.fullmatch(line)
    if header:
        kind = "size" if header.group("size") else "measurement" if header.group("measurement") else "shrinkage"
        value = header.group("value").strip()
        if not value:
            return True, kind
    elif pending_kind:
        kind, value = pending_kind, line
    else:
        return False, None

    value = value.strip(" \t()[]")
    return _METADATA_VALUE_PATTERNS[kind].fullmatch(value) is not None, None


def _is_unlabeled_korean_garment_size(
    line: str,
    previous: LineInfo | None,
    *,
    is_last_line: bool,
) -> bool:
    if (
        not is_last_line
        or line not in _UNLABELED_KOREAN_GARMENT_SIZE_VALUES
        or previous is None
        or previous.is_metadata
        or previous.invalid_evidence
        or not previous.explicit_percent
        or not previous.materials
        or len(previous.materials) != len(previous.numbers)
        or len(set(previous.materials)) != len(previous.materials)
        or not has_exact_total(previous.numbers)
    ):
        return False

    return any(
        find_material_key(match.group())
        for match in re.finditer(r"[가-힣]+", previous.normalized)
    )
