"""Corroborate a complete label panel, separate from tiny remote print."""

from collections import Counter
from dataclasses import dataclass
import math
import re

from apps.text.headed_inline_recovery import _unique_pair, literal_tokens
from apps.text.material_extraction import (
    NEGATING_MODIFIERS,
    UNPRICED_MATERIALS,
    _material_evidence,
    declared_part,
    unresolved_material_tokens,
)
from apps.text.ocr_geometry import complete_annotation_geometry, same_place_annotations
from apps.text.ocr_row_search import physical_row_options
from apps.text.single_part_table_recovery import _chain_options


@dataclass(frozen=True)
class _Panel:
    core: tuple
    origin: tuple
    height: float
    number: object = None


def _height(word):
    a, b, c, d = word.vertices
    length = math.dist(a, b)
    return (
        abs((b[0] - a[0]) * (d[1] - a[1]) - (b[1] - a[1]) * (d[0] - a[0]))
        + abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
    ) / (2 * length)


def _rows(item, *, crop=False):
    from apps.text.parse_label import build_line_infos

    if not complete_annotation_geometry(item, literal_tokens):
        return None
    infos = build_line_infos(item.text)
    fibers = [row for row in infos if row.materials]
    origins = [
        row
        for row in infos
        if re.fullmatch(r"made\s+in\s+[a-z]+(?:\s+[a-z]+){0,2}", row.normalized)
    ]
    if (
        len(fibers) != 1
        or len(origins) != 1
        or any(
            row.marker_part is not None
            or row.unresolved_materials
            or row.invalid_evidence
            and not (
                not crop
                and re.fullmatch(r"[0-9]{3,6}", row.normalized)
                and int(row.normalized) > 100
            )
            for row in infos
        )
    ):
        return None
    fiber, origin = fibers[0], origins[0]
    evidence = _material_evidence(fiber.normalized)
    if (
        len(evidence) != 1
        or fiber.part != "generic"
        or fiber.numbers != (100,)
        or not fiber.explicit_percent
        or len(fiber.materials) != 1
    ):
        return None
    alias = fiber.normalized[evidence[0].start : evidence[0].end]
    if literal_tokens(fiber.raw) not in (
        literal_tokens(alias) + ("100", "%"),
        ("100", "%") + literal_tokens(alias),
    ):
        return None
    if crop and len(infos) != 2:
        return None
    core = (_chain_options if crop else _unique_pair)(fiber.raw, item.image_words)
    options = physical_row_options(origin.raw, item.image_words, tokenise=literal_tokens)
    if not core or len(options) != 1:
        return None
    footer = tuple(item.image_words[i] for i in options[0])
    if set(core).intersection(footer):
        return None
    heights = [_height(word) for word in core + footer]
    if min(heights) < 12 or max(heights) > 2 * min(heights):
        return None
    anchor = max(core, key=lambda w: math.dist(w.vertices[0], w.vertices[1]))
    a, b, *_ = anchor.vertices
    # The two-axis remote-print proof is confined to upright panels. Rotated
    # labels keep the existing coordinate-aware recovery paths.
    if (b[0] - a[0]) / math.dist(a, b) < math.cos(math.radians(15)):
        return None
    height = min(heights)
    gap = min(w.top for w in footer) - max(w.bottom for w in core)
    overlap = min(max(w.right for w in core), max(w.right for w in footer)) - max(
        min(w.left for w in core), min(w.left for w in footer)
    )
    width = min(
        max(w.right for w in group) - min(w.left for w in group) for group in (core, footer)
    )
    if not height <= gap <= 6 * height or overlap < 0.5 * width:
        return None
    return _Panel(core, footer, height)


def _tiny_remote(word, crop, height):
    left, top, right, bottom = crop
    return (
        _height(word) <= 0.35 * height
        and (word.right + 2 * height < left or word.left - 2 * height > right)
        and (word.bottom + 2 * height < top or word.top - 2 * height > bottom)
    )


def _clean(item):
    return (
        item.parser_status == "success"
        and item.selected_part == "generic"
        and set(item.parts) == {"generic"}
        and len(item.parts["generic"]) == 1
        and tuple(item.parts["generic"].values()) == (100,)
        and not any(
            (
                item.parser_warnings,
                item.rejected_composition_parts,
                item.unpaired_ratio_parts,
                item.conflicting_parts,
                item.unconfirmed_outer_parts,
            )
        )
    )


def _full(item, target, panel):
    from apps.text.parse_label import build_line_infos

    if (
        item.source not in {"original", "preprocessed"}
        or item.parser_status != "failed"
        or item.parts
        or item.conflicting_parts
        or item.rejected_composition_parts
        or item.unconfirmed_outer_parts
        or set(item.unpaired_ratio_parts) != {"generic"}
        or set(item.parser_warnings) != {"generic:unpaired_ratio_rows"}
        or item.image_key != target.image_key
        or item.image_variant_key == target.image_variant_key
        or len(item.image_region) != 4
        or item.image_region[:2] != (0, 0)
        or item.observed_materials != target.observed_materials
        or set(item.observed_ratios) != {"generic"}
    ):
        return None
    source = _rows(item)
    if (
        source is None
        or not same_place_annotations(source.core, panel.core)
        or not same_place_annotations(source.origin, panel.origin)
    ):
        return None
    full, crop = item.image_region, target.image_region
    if not (
        0 < crop[0] < crop[2] < full[2]
        and 0 < crop[1] < crop[3] < full[3]
        and (crop[2] - crop[0]) * (crop[3] - crop[1]) < 0.35 * full[2] * full[3]
    ):
        return None
    ratios = Counter(item.observed_ratios["generic"])
    extra = list((ratios - Counter({100: 1})).elements())
    if len(extra) != 1 or ratios != Counter([100, extra[0]]) or not 0 < extra[0] < 100:
        return None
    numbers = [
        word
        for word in item.image_words
        if re.fullmatch(r"[0-9]{1,2}", word.text) and int(word.text) == extra[0]
    ]
    if len(numbers) != 1 or not _tiny_remote(numbers[0], crop, source.height):
        return None
    known = set(source.core + source.origin)
    forbidden = (
        NEGATING_MODIFIERS | UNPRICED_MATERIALS | {"unknown", "olefin", "未知繊維", "未知纤维"}
    )
    for word in item.image_words:
        if word in known:
            continue
        tokens = literal_tokens(word.text)
        if (
            not tokens
            or any(token in forbidden for token in tokens)
            or _material_evidence(word.text)
            or declared_part(word.text)
            or unresolved_material_tokens(word.text)
        ):
            return None
        if re.fullmatch(r"[0-9]{1,6}", word.text):
            if not _tiny_remote(word, crop, source.height):
                return None
        elif len(tokens) == 1 and len(tokens[0]) == 1 and tokens[0].isalpha():
            # A single logo glyph must be above the panel or far to its side,
            # never between its material and country-of-origin rows.
            if not (
                word.bottom + 2 * source.height < min(w.top for w in source.core)
                or word.right + 2 * source.height < crop[0]
                or word.left - 2 * source.height > crop[2]
            ):
                return None
        elif (
            not 1 <= len(tokens) <= 3
            or not all(len(t) == 1 and t.isalpha() and not t.isascii() for t in tokens)
            or not _tiny_remote(word, crop, source.height)
        ):
            return None
    # A rejected row must be precisely the bare number. A percent, minus sign,
    # decimal, second unknown material or a care instruction cannot vanish.
    for row in build_line_infos(item.text):
        if row.numbers and not row.materials and not re.fullmatch(r"[0-9]{1,6}", row.normalized):
            return None
    return _Panel(source.core, source.origin, source.height, numbers[0])


def recover_remote_background_number(candidate, alternative, part, candidates):
    """Require two full readings and a literal raw/layout crop agreement.

    Only an already printed 100% declaration is selected. No numeric cell or
    material is repaired, and no region is called a washing symbol by guessing.
    """
    if (
        part != "generic"
        or alternative.source != "material_crop"
        or not alternative.layout_used
        or not _clean(alternative)
        or not alternative.image_key
    ):
        return False
    panel = _rows(alternative, crop=True)
    if panel is None or set(panel.core + panel.origin) != set(alternative.image_words):
        return False
    if not any(
        peer.source == alternative.source
        and not peer.layout_used
        and _clean(peer)
        and peer.image_key == alternative.image_key
        and peer.image_variant_key == alternative.image_variant_key
        and peer.image_region == alternative.image_region
        and peer.image_words == alternative.image_words
        and peer.parts == alternative.parts
        and Counter(literal_tokens(peer.text)) == Counter(literal_tokens(alternative.text))
        and _rows(peer, crop=True) is not None
        for peer in candidates
    ):
        return False
    source = _full(candidate, alternative, panel)
    if source is None:
        return False
    for peer in candidates:
        if (
            peer.layout_used
            or peer.source == candidate.source
            or peer.image_variant_key == candidate.image_variant_key
            or peer.image_region != candidate.image_region
        ):
            continue
        other = _full(peer, alternative, panel)
        if (
            other is not None
            and int(source.number.text) != int(other.number.text)
            and math.dist(
                (source.number.center_x, source.number.center_y),
                (other.number.center_x, other.number.center_y),
            )
            > 2 * max(source.height, other.height)
        ):
            return True
    return False
