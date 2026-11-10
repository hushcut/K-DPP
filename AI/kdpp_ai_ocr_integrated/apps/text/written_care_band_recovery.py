"""Separate a complete declaration from a literally bounded care-number band."""

from collections import Counter
from dataclasses import dataclass
import math
import re

from apps.text.headed_inline_recovery import _unique_pair, literal_tokens, _overlap
from apps.text.material_extraction import _material_evidence
from apps.text.ocr_geometry import complete_annotation_geometry, same_place_annotations
from apps.text.single_part_table_recovery import _chain_options


@dataclass(frozen=True)
class _Frame:
    core: tuple
    wash: tuple
    dry: tuple
    footer: tuple


def _compact(text):
    return re.sub(r"\s", "", text.casefold())


def _frame(item, number):
    from apps.text.parse_label import build_line_infos

    if not complete_annotation_geometry(item, literal_tokens):
        return None
    infos = build_line_infos(item.text)
    materials = [row for row in infos if row.materials]
    if (
        len(materials) != 1
        or any(
            row.marker_part is not None or row.unresolved_materials or row.invalid_evidence
            for row in infos
        )
        or len([row for row in infos if "%" in row.raw]) != 1
    ):
        return None
    row = materials[0]
    evidence = _material_evidence(row.normalized)
    if (
        len(evidence) != 1
        or row.part != "generic"
        or row.numbers != (100,)
        or not row.explicit_percent
    ):
        return None
    alias = row.normalized[evidence[0].start : evidence[0].end]
    if literal_tokens(row.raw) not in (
        literal_tokens(alias) + ("100", "%"),
        ("100", "%") + literal_tokens(alias),
    ):
        return None
    words = item.image_words
    core = _unique_pair(row.raw, words)
    washes = [r for r in infos if _compact(r.normalized) == "machinewashcold"]
    dries = [r for r in infos if _compact(r.normalized) == "tumbledrylow"]
    # LineInfo normalizes registration separators. Locate the literal supplied
    # row instead, retaining its original dot annotations and exact digits.
    footers = [
        line
        for line in item.text.splitlines()
        if re.fullmatch(r"rn\s*[·:.]?\s*\d{4,6}\s+ca\s*[·:.]?\s*\d{4,6}", line.strip().casefold())
    ]
    if not core or not all(len(rows) == 1 for rows in (washes, dries, footers)):
        return None
    wash = _chain_options(washes[0].raw, words)
    dry = _chain_options(dries[0].raw, words)
    footer = _chain_options(footers[0], words)
    if not all((wash, dry, footer)):
        return None
    groups = core + wash + dry + footer
    if len(set(groups)) != len(groups):
        return None
    anchor = max(wash, key=lambda w: math.dist(w.vertices[0], w.vertices[1]))
    a, b, *_ = anchor.vertices
    length = math.dist(a, b)
    normal = (-(b[1] - a[1]) / length, (b[0] - a[0]) / length)

    def extent(group):
        values = [normal[0] * x + normal[1] * y for w in group for x, y in w.vertices]
        return min(values), max(values)

    core_y, wash_y, dry_y, footer_y = map(extent, (core, wash, dry, footer))
    if not core_y[1] < wash_y[0] < wash_y[1] < dry_y[0] < dry_y[1] < footer_y[0]:
        return None
    known = set(groups)
    numeric = []
    for word in words:
        if word in known:
            continue
        low, high = extent((word,))
        # Any unknown print touching this written care interval is retained as
        # uncertainty. Neither a percent nor another fiber may disappear here.
        if high <= wash_y[1] or low >= footer_y[0]:
            continue
        if (
            number is None
            or not dry_y[1] < low < high < footer_y[0]
            or not re.fullmatch(r"[0-9]{1,2}", word.text)
            or int(word.text) != number
        ):
            return None
        numeric.append(word)
    if len(numeric) != int(number is not None):
        return None
    return _Frame(core, wash, dry, footer)


def _same_caption(source, target):
    # Joined OCR words may split in a reread; both phrases have independently
    # matched the same complete literal caption before comparing their cells.
    return all(
        any(_overlap(w.vertices, other.vertices) for other in target) for w in source
    ) and all(any(_overlap(w.vertices, other.vertices) for other in source) for w in target)


def recover_written_care_band(candidate, alternative, part):
    """Use an independently read panel; never interpret or repair a symbol."""
    if (
        part != "generic"
        or candidate.source != "original"
        or candidate.parser_status != "failed"
        or candidate.parts
        or candidate.conflicting_parts
        or candidate.unconfirmed_outer_parts
        or candidate.rejected_composition_parts
        or set(candidate.unpaired_ratio_parts) != {part}
        or set(candidate.parser_warnings) != {"generic:unpaired_ratio_rows"}
        or set(candidate.observed_ratios) != {part}
        or alternative.source != "preprocessed"
        or not alternative.layout_used
        or alternative.parser_status != "success"
        or set(alternative.parts) != {part}
        or len(alternative.parts[part]) != 1
        or tuple(alternative.parts[part].values()) != (100,)
        or alternative.parser_warnings
        or alternative.unpaired_ratio_parts
        or alternative.rejected_composition_parts
        or alternative.conflicting_parts
        or alternative.unconfirmed_outer_parts
        or not candidate.image_key
        or candidate.image_key != alternative.image_key
        or candidate.image_region != alternative.image_region
        or candidate.image_variant_key == alternative.image_variant_key
        or candidate.observed_materials != alternative.observed_materials
    ):
        return False
    ratios = Counter(candidate.observed_ratios[part])
    extra = list((ratios - Counter({100: 1})).elements())
    if len(extra) != 1 or ratios != Counter([100, extra[0]]) or not 0 < extra[0] < 100:
        return False
    source, target = _frame(candidate, int(extra[0])), _frame(alternative, None)
    if source is None or target is None:
        return False
    return (
        same_place_annotations(source.core, target.core)
        and _same_caption(source.wash, target.wash)
        and _same_caption(source.dry, target.dry)
        and same_place_annotations(source.footer, target.footer)
    )
