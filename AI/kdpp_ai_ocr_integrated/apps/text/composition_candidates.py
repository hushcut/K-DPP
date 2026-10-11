"""Enumerate complete composition blocks from normalized OCR rows.

The collectors run in the original order so candidate tie-breaking remains stable.
"""

from dataclasses import dataclass
from decimal import Decimal
import re

from apps.text.rules import EQUIVALENT_MATERIALS
from apps.text.material_extraction import ALIAS_TO_MATERIAL, _TOKEN_PATTERN, find_material_key

from apps.text.ratio_contract import EXACT_RATIO_TOTAL, has_exact_total, sum_ratios

EXACT_RATIO_TOLERANCE = 0.0


def equivalent_composition(
    materials: dict[str, float | int],
) -> tuple[tuple[str, float | int], ...]:
    """파서와 OCR 후보가 같은 섬유의 다국어 표기를 동일하게 비교한다."""

    return tuple(
        sorted(
            (EQUIVALENT_MATERIALS.get(material, material), value)
            for material, value in materials.items()
        )
    )


@dataclass(frozen=True)
class LineInfo:
    index: int
    raw: str
    normalized: str
    part: str
    materials: tuple[str, ...]
    numbers: tuple[Decimal, ...]
    explicit_percent: bool
    unresolved_materials: tuple[str, ...] = ()
    marker_part: str | None = None
    invalid_evidence: bool = False
    is_metadata: bool = False
    inferred_metadata: bool = False

    @property
    def is_standalone_marker(self) -> bool:
        return self.marker_part is not None and not self.materials and not self.numbers


@dataclass(frozen=True)
class CompositionCandidate:
    part: str
    materials: dict[str, Decimal]
    source: str
    explicit_percent: bool
    start_index: int
    row_indices: tuple[int, ...] = ()

    @property
    def total(self) -> Decimal:
        return sum_ratios(self.materials.values())

    @property
    def score(self) -> tuple[int, float, int, int]:
        source_rank = {
            "same_line": 3,
            "line_pairs": 2,
            "alternating_lines": 2,
            "stacked_columns": 2,
            "mixed_lines": 2,
            "translated_lines": 2,
            "ratio_first_lines": 2,
            "adjacent_lines": 1,
            "leading_ratio": 1,
            "enclosing_ratios": 1,
        }.get(self.source, 0)
        return (
            1 if self.explicit_percent else 0,
            -abs(EXACT_RATIO_TOTAL - self.total),
            len(self.materials),
            source_rank,
        )


def _pair_values(
    part: str,
    materials: list[str] | tuple[str, ...],
    numbers: list[float] | tuple[float, ...],
    *,
    source: str,
    explicit_percent: bool,
    start_index: int,
    row_indices: tuple[int, ...] = (),
) -> CompositionCandidate | None:
    if not materials or not numbers or len(materials) != len(numbers):
        return None

    paired: dict[str, float] = {}
    for material, number in zip(materials, numbers):
        if material in paired or not (0 < number <= 100):
            return None
        paired[material] = Decimal(str(number))

    # A partial or misread OCR result must not be rescaled into a valid-looking
    # composition. Every supplied ratio needs to form one complete 100% block.
    if not has_exact_total(paired.values()):
        return None

    return CompositionCandidate(
        part=part,
        materials=paired,
        source=source,
        explicit_percent=explicit_percent,
        start_index=start_index,
        row_indices=row_indices or (start_index,),
    )


def _is_standalone_composition(info: LineInfo) -> bool:
    """Whether a row's own ratios already form one complete composition."""

    return has_exact_total(info.numbers)


def _same_line_candidates(infos: list[LineInfo]) -> list[CompositionCandidate]:
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
    return candidates


def _line_pair_candidates(infos: list[LineInfo]) -> list[CompositionCandidate]:
    candidates: list[CompositionCandidate] = []
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
                row_indices=tuple(row.index for row in run[: offset + 1]),
            )
            if candidate:
                candidates.append(candidate)
    return candidates


def _alternating_line_candidates(infos: list[LineInfo]) -> list[CompositionCandidate]:
    candidates: list[CompositionCandidate] = []
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
            row_indices=tuple(row.index for row in infos[position:cursor]),
        )
        if candidate:
            candidates.append(candidate)
    return candidates


def _mixed_line_candidates(infos: list[LineInfo]) -> list[CompositionCandidate]:
    candidates: list[CompositionCandidate] = []
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
            row_indices=tuple(row.index for row in infos[position:cursor]),
        )
        # Mixed layouts must still show every ratio explicitly.
        if candidate and explicit_percent:
            candidates.append(candidate)
    return candidates


def _stacked_column_candidates(infos: list[LineInfo]) -> list[CompositionCandidate]:
    candidates: list[CompositionCandidate] = []
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
            row_indices=tuple(row.index for row in infos[position:cursor]),
        )
        # Bare number-only lines are too easily confused with product codes,
        # dates, or temperatures. A stacked ratio column is accepted only
        # when every ratio carries an explicit percent marker.
        if candidate and explicit_percent:
            candidates.append(candidate)
    return candidates


def _adjacent_line_candidates(infos: list[LineInfo]) -> list[CompositionCandidate]:
    candidates: list[CompositionCandidate] = []
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
            from apps.text.parse_label import COMPOSITION_HINTS

            if (not neighbor.numbers and _TOKEN_PATTERN.search(neighbor.normalized)
                    and neighbor.normalized.rstrip(" :") not in COMPOSITION_HINTS):
                break
            candidate = _pair_values(
                info.part,
                info.materials,
                neighbor.numbers,
                source="adjacent_lines",
                explicit_percent=neighbor.explicit_percent,
                start_index=info.index,
                row_indices=(info.index, neighbor.index),
            )
            if candidate:
                candidates.append(candidate)
                break
    return candidates


def _leading_ratio_candidates(infos: list[LineInfo]) -> list[CompositionCandidate]:
    """Pair adjacent explicit percentages printed before their material names.

    Only a one-material pair or a fully bounded two-material block is
    unambiguous; a partial block still has uncovered material rows.
    """
    candidates: list[CompositionCandidate] = []
    for position, first in enumerate(infos):
        if (
            first.materials
            or len(first.numbers) != 1
            or not first.explicit_percent
            or position + 1 >= len(infos)
        ):
            continue
        second = infos[position + 1]
        if (
            second.part != first.part
            or second.index != first.index + 1
            or len(second.materials) != 1
            or second.numbers
        ):
            continue
        following_ratio = (
            position + 2 < len(infos)
            and infos[position + 2].part == first.part
            and infos[position + 2].index == second.index + 1
            and not infos[position + 2].materials
            and infos[position + 2].explicit_percent
        )
        # A material with its own following ratio cannot also borrow a
        # preceding ratio. Otherwise a damaged 100% row can validate the
        # wrong 95/5 block (QA031).
        if not following_ratio:
            candidate = _pair_values(
                first.part,
                second.materials,
                first.numbers,
                source="leading_ratio",
                explicit_percent=True,
                start_index=first.index,
                row_indices=(first.index, second.index),
            )
            if candidate:
                candidates.append(candidate)

        if position + 3 >= len(infos):
            continue
        third, fourth = infos[position + 2 : position + 4]
        if (
            third.part != first.part
            or fourth.part != first.part
            or third.index != second.index + 1
            or fourth.index != third.index + 1
            or len(third.materials) != 1
            or third.numbers
            or fourth.materials
            or len(fourth.numbers) != 1
            or not fourth.explicit_percent
        ):
            continue
        candidate = _pair_values(
            first.part,
            (*second.materials, *third.materials),
            (*first.numbers, *fourth.numbers),
            source="enclosing_ratios",
            explicit_percent=True,
            start_index=first.index,
            row_indices=(first.index, second.index, third.index, fourth.index),
        )
        if candidate:
            candidates.append(candidate)
    return candidates


def _has_translation_context(info: LineInfo) -> bool:
    return (
        "/" in info.normalized or "-" in info.normalized
        or sum(find_material_key(token) is not None
               for token in _TOKEN_PATTERN.findall(info.normalized)) >= 2
        or any(find_material_key(token) is not None
               and re.search(r"[Ѐ-ԯ぀-ヿ㐀-鿿가-힯]", token)
               for token in _TOKEN_PATTERN.findall(info.normalized))
    )


def _consume_registered_translation_aliases(remainder: str) -> tuple[set[str], str]:
    materials: set[str] = set()
    for alias in sorted(ALIAS_TO_MATERIAL, key=len, reverse=True):
        pattern = rf"(?<!\w){re.escape(alias)}(?!\w)"
        if re.search(pattern, remainder):
            materials.add(ALIAS_TO_MATERIAL[alias])
            remainder = re.sub(pattern, " ", remainder)
    return materials, remainder


def _ratio_free_translation_row_is_complete(info: LineInfo, material: str) -> bool:
    """A ratio-free alias may end in one printed translation hyphen."""
    text = info.normalized.rstrip()
    if text.endswith("-"):
        text = text[:-1]
    materials, remainder = _consume_registered_translation_aliases(text)
    return materials == {material} and re.fullmatch(r"[\s/]*", remainder) is not None


def _inline_translation_ratio_is_complete(info: LineInfo, material: str) -> bool:
    """Consume one literal percent and exact aliases across the entire row."""
    percentages = list(re.finditer(r"[0-9]+(?:[.,][0-9]+)?[ \t]*%", info.normalized))
    if len(percentages) != 1:
        return False
    percent = percentages[0]
    if Decimal(percent.group().rstrip("% \t").replace(",", ".")) != info.numbers[0]:
        return False
    remainder = (info.normalized[:percent.start()] + " " * (percent.end() - percent.start())
                 + info.normalized[percent.end():])
    materials, remainder = _consume_registered_translation_aliases(remainder)
    # _read_numbers can intentionally ignore bare identifiers after an already
    # complete percent. Such leftovers cannot belong to a shared translation.
    return materials == {material} and re.fullmatch(r"[\s/]*", remainder) is not None


def _translated_component(infos: list[LineInfo], position: int, part: str):
    """Read one explicit ratio and its contiguous, fully known translations."""
    first = infos[position]
    if first.part != part or first.invalid_evidence or first.unresolved_materials or first.is_metadata:
        return None
    rows = [first.index]
    cursor = position + 1
    ratio_first = not first.materials
    if ratio_first:
        if (len(first.numbers) != 1 or not first.explicit_percent
                or _TOKEN_PATTERN.search(first.normalized) or cursor >= len(infos)):
            return None
        primary = infos[cursor]
        if (primary.part != part or primary.index != first.index + 1
                or len(primary.materials) != 1 or primary.numbers
                or primary.invalid_evidence or primary.unresolved_materials
                or primary.is_metadata or primary.marker_part is not None):
            return None
        ratio = first.numbers[0]
        rows.append(primary.index)
        cursor += 1
    else:
        primary = first
        if len(primary.materials) != 1:
            return None
        if primary.numbers and (len(primary.numbers) != 1 or not primary.explicit_percent):
            return None
        ratio = primary.numbers[0] if primary.numbers else None
    material = primary.materials[0]
    alias_infos = [primary]
    translated = False
    context = _has_translation_context(primary) or _has_registered_translation_run(infos, position, primary)
    separator = "/" in primary.normalized or "-" in primary.normalized

    def take_alias_rows():
        nonlocal cursor, translated, context, separator
        while cursor < len(infos):
            current = infos[cursor]
            if (current.part != part or current.index != rows[-1] + 1
                    or current.materials != (material,) or current.numbers
                    or current.invalid_evidence or current.unresolved_materials
                    or current.is_metadata or current.marker_part is not None
                    or not (context or _has_translation_context(current))):
                break
            rows.append(current.index)
            alias_infos.append(current)
            context = True
            separator |= "/" in current.normalized or "-" in current.normalized
            translated = True
            cursor += 1

    take_alias_rows()
    if ratio is None:
        if cursor >= len(infos):
            return None
        ratio_row = infos[cursor]
        if (ratio_row.part != part or ratio_row.index != rows[-1] + 1
                or len(ratio_row.numbers) != 1
                or not ratio_row.explicit_percent or ratio_row.invalid_evidence
                or ratio_row.unresolved_materials or ratio_row.is_metadata
                or ratio_row.marker_part is not None):
            return None
        if ratio_row.materials:
            # A printed translation separator can place the shared explicit
            # ratio on the final same-fiber alias, rather than on its own row.
            # A different fiber or an unmarked repeated name owns another row.
            if (ratio_row.materials != (material,) or not separator
                    or not all(_ratio_free_translation_row_is_complete(info, material)
                               for info in alias_infos)
                    or not _inline_translation_ratio_is_complete(ratio_row, material)):
                return None
            translated = True
        elif _TOKEN_PATTERN.search(ratio_row.normalized):
            return None
        ratio = ratio_row.numbers[0]
        rows.append(ratio_row.index)
        cursor += 1
        take_alias_rows()
    # A leading percentage cannot borrow a name with its own following ratio.
    # A different next name is required to delimit a ratio-first column.
    if ratio_first and cursor < len(infos):
        following = infos[cursor]
        if following.part == part and following.numbers and not following.materials:
            if cursor + 1 >= len(infos):
                return None
            next_name = infos[cursor + 1]
            if (next_name.index != following.index + 1 or next_name.part != part
                    or len(next_name.materials) != 1 or next_name.materials == (material,)
                    or next_name.numbers or next_name.invalid_evidence or next_name.unresolved_materials
                    or next_name.marker_part is not None or next_name.is_metadata):
                return None
    return material, ratio, cursor, rows, translated, ratio_first


def _translated_line_candidates(infos: list[LineInfo]) -> list[CompositionCandidate]:
    candidates = []
    for position, first in enumerate(infos):
        materials, numbers, row_indices = [], [], []
        cursor = position
        translated = False
        any_ratio_first = False
        while cursor < len(infos) and len(materials) < 6:
            if row_indices and infos[cursor].index != row_indices[-1] + 1:
                break
            component = _translated_component(infos, cursor, first.part)
            if component is None:
                break
            material, number, following, rows, has_translation, ratio_first = component
            if material in materials:
                break
            materials.append(material)
            numbers.append(number)
            row_indices.extend(rows)
            translated |= has_translation
            any_ratio_first |= ratio_first
            cursor = following
        if not translated and not (any_ratio_first and len(materials) > 1):
            continue
        candidate = _pair_values(
            first.part, materials, numbers,
            source="translated_lines" if translated else "ratio_first_lines",
            explicit_percent=True, start_index=first.index, row_indices=tuple(row_indices),
        )
        if candidate:
            candidates.append(candidate)
    return candidates


def _collect_candidates(infos: list[LineInfo]) -> list[CompositionCandidate]:
    """Collect candidates from rows already filtered for metadata."""

    candidates: list[CompositionCandidate] = []
    for collector in (
        _same_line_candidates,
        _line_pair_candidates,
        _alternating_line_candidates,
        _mixed_line_candidates,
        _stacked_column_candidates,
        _adjacent_line_candidates,
        _leading_ratio_candidates,
        _translated_line_candidates,
    ):
        candidates.extend(collector(infos))
    return candidates


def _has_registered_translation_run(infos: list[LineInfo], position: int, primary: LineInfo) -> bool:
    """Require a composition heading and two distinct, complete translations."""
    from apps.text.parse_label import COMPOSITION_HINTS, _CARE_PHRASES, _contains_only_known_phrases, _mentions_care

    headed = primary.marker_part == primary.part
    for preceding in reversed(infos[:position]):
        if preceding.part != primary.part or preceding.is_metadata or preceding.invalid_evidence or preceding.unresolved_materials:
            break
        if preceding.marker_part is not None:
            headed = preceding.marker_part == primary.part and preceding.is_standalone_marker
            break
        if (not preceding.materials and not preceding.numbers
                and preceding.normalized.rstrip(" :") in COMPOSITION_HINTS):
            headed = True
            break
    if not headed:
        return False
    material = primary.materials[0]
    primary_aliases = {token for token in _TOKEN_PATTERN.findall(primary.normalized)
                       if find_material_key(token) == material}
    aliases = set()
    cursor = infos.index(primary) + 1
    last_index = primary.index
    while cursor < len(infos):
        row = infos[cursor]
        alias = row.normalized.strip(" /-")
        if (row.index != last_index + 1 or row.part != primary.part
                or row.materials != (material,) or row.numbers or "%" in row.normalized
                or row.invalid_evidence or row.unresolved_materials or row.is_metadata
                or row.marker_part is not None or find_material_key(alias) != material):
            break
        if alias not in primary_aliases:
            aliases.add(alias)
        last_index = row.index
        cursor += 1
    if cursor < len(infos):
        following = infos[cursor]
        if (following.part == primary.part and not following.marker_part
                and not following.is_metadata and not following.materials and not following.numbers
                and _TOKEN_PATTERN.search(following.normalized)):
            # An unregistered name cannot end a translated material column.
            # Only a fully recognized care instruction is a confirmed boundary.
            if not (_mentions_care(following.normalized)
                    and _contains_only_known_phrases(following.normalized, set(_CARE_PHRASES))):
                return False
    return len(aliases) >= 2
