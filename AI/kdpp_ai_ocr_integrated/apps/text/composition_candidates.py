"""Enumerate complete composition blocks from normalized OCR rows.

The collectors run in the original order so candidate tie-breaking remains stable.
"""

from dataclasses import dataclass

EXACT_RATIO_TOLERANCE = 0.01


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
    marker_part: str | None = None

    @property
    def is_standalone_marker(self) -> bool:
        return self.marker_part is not None and not self.materials and not self.numbers


@dataclass(frozen=True)
class CompositionCandidate:
    part: str
    materials: dict[str, float]
    source: str
    explicit_percent: bool
    start_index: int
    row_indices: tuple[int, ...] = ()

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
        row_indices=row_indices or (start_index,),
    )


def _is_standalone_composition(info: LineInfo) -> bool:
    """Whether a row's own ratios already form one complete composition."""

    return abs(sum(info.numbers) - 100.0) <= EXACT_RATIO_TOLERANCE


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
    ):
        candidates.extend(collector(infos))
    return candidates
