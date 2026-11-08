"""Verify a labelled, bounded single-fiber table without correcting OCR text."""

from collections import Counter
import math
import re

from apps.text.headed_inline_recovery import _hull, _overlap, _unique_pair, literal_tokens
from apps.text.material_extraction import NEGATING_MODIFIERS, UNPRICED_MATERIALS, _material_evidence, normalize_text
from apps.text.ocr_geometry import _row_options, complete_annotation_geometry


_TRIM = re.compile(r"\(\s*심지\s*,\s*상표\s*,\s*보강재\s*,\s*자수\s*,\s*장식\s*제외\s*\)")
_PUNCTUATION = re.compile(r"[-,:;()/]+")


def _content_tokens(text):
    return tuple(token for token in literal_tokens(text) if re.fullmatch(r"\w+", token))


def _chain(text, words, tokenise):
    """Prove adjacent literal name/caption pieces across a modest label bend."""
    if not words or len(words) > 16:
        return False
    anchor = max(words, key=lambda word: math.dist(word.vertices[0], word.vertices[1]))
    a, b, *_ = anchor.vertices
    length = math.dist(a, b)
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    frames = []
    for word in words:
        a, b, *_ = word.vertices
        span = math.dist(a, b)
        if (not _PUNCTUATION.fullmatch(word.text.strip())
                and (ux * (b[0] - a[0]) + uy * (b[1] - a[1])) / span < math.cos(math.radians(15))):
            return False
        xs = [ux * x + uy * y for x, y in word.vertices]
        ys = [-uy * x + ux * y for x, y in word.vertices]
        frames.append((min(xs), max(xs), min(ys), max(ys), word))
    ordered = sorted(frames, key=lambda row: row[0])
    if tuple(token for *_, word in ordered for token in tokenise(word.text)) != tokenise(text):
        return False
    for left, right in zip(ordered, ordered[1:]):
        heights = left[3] - left[2], right[3] - right[2]
        if (right[0] - left[1] > 2 * max(heights)
                or min(left[3], right[3]) - max(left[2], right[2]) < .45 * min(heights)):
            return False
    return True


def _chain_options(text, words, *, caption=False):
    tokenise = _content_tokens if caption else literal_tokens
    found = []
    for indices in _row_options(text, words, tokenise=tokenise):
        chosen = tuple(words[index] for index in indices)
        if not _chain(text, chosen, tokenise):
            continue
        envelopes = [_hull(word.vertices) for word in chosen]
        envelopes.extend(_hull((*left.vertices, *right.vertices))
                         for left, right in zip(chosen, chosen[1:]))
        if all(word in chosen or _PUNCTUATION.fullmatch(word.text.strip())
               or not any(_overlap(envelope, word.vertices) for envelope in envelopes) for word in words):
            found.append(chosen)
    return found[0] if len(found) == 1 else ()


def literal_single_part_table_over_failed_layout(raw, layout):
    """Keep only a fully located outer declaration from one original reply."""
    from apps.text.parse_label import build_line_infos, _is_metadata_line

    if (raw.source != "original" or raw.layout_used or not layout.layout_used
            or raw.parser_status != "success" or layout.parser_status != "failed"
            or raw.selected_part != "outer" or set(raw.parts) != {"outer"}
            or len(raw.parts["outer"]) != 1 or tuple(raw.parts["outer"].values()) != (100,)
            or raw.conflicting_parts or raw.unpaired_ratio_parts or raw.rejected_composition_parts
            or layout.parts or layout.conflicting_parts
            or raw.source != layout.source or raw.image_key != layout.image_key
            or raw.image_variant_key != layout.image_variant_key or raw.image_region != layout.image_region
            or raw.image_words != layout.image_words
            or Counter(literal_tokens(raw.text)) != Counter(literal_tokens(layout.text))
            or not complete_annotation_geometry(raw, literal_tokens)
            or not complete_annotation_geometry(layout, literal_tokens)
            or set(layout.observed_materials) - {"generic", "outer"}
            or set(layout.observed_ratios) - {"generic", "outer"}
            or Counter(material for values in layout.observed_materials.values() for material in values)
            != Counter(raw.parts["outer"].keys())
            or 100 not in [value for values in layout.observed_ratios.values() for value in values]):
        return False
    forbidden = NEGATING_MODIFIERS | UNPRICED_MATERIALS | {"unknown", "olefin", "未知繊維", "未知纤维"}
    if any(token in forbidden for token in literal_tokens(raw.text)):
        return False
    infos = build_line_infos(raw.text)
    headings = [info for info in infos if info.normalized in {"혼용률", "혼용율"}]
    owners = [info for info in infos if info.materials]
    ratios = [info for info in infos if "%" in info.normalized]
    footers = [info for info in infos if _TRIM.fullmatch(info.normalized)]
    if (len(headings) != 1 or len(owners) != 1 or len(ratios) != 1 or len(footers) != 1
            or any(info.unresolved_materials for info in infos)):
        return False
    heading, owner, ratio, footer = headings[0], owners[0], ratios[0], footers[0]
    metadata = Counter(float(token) for row in infos if row not in (owner, ratio)
                       and _is_metadata_line(row) and not row.materials and "%" not in row.raw
                       for token in literal_tokens(row.raw)
                       if re.fullmatch(r"[0-9]+", token) and 0 < int(token) <= 100)
    extra = (Counter(value for values in layout.observed_ratios.values() for value in values)
             - Counter({100: 1}))
    if not extra <= metadata:
        return False
    evidence = _material_evidence(owner.normalized)
    if (owner.marker_part != "outer" or owner.numbers or owner.invalid_evidence
            or owner.materials != tuple(raw.parts["outer"]) or len(evidence) != 1
            or not re.fullmatch(r"겉\s*감\s*:\s*", owner.normalized[:evidence[0].start])
            or owner.normalized[evidence[0].end:].strip()
            or not re.fullmatch(r"100\s*%", ratio.normalized)
            or not heading.index < owner.index < footer.index or ratio.index >= footer.index
            or any(info.marker_part and info is not owner for info in infos)):
        return False
    words = raw.image_words
    title_cell = _chain_options(heading.raw, words)
    owner_cell = _chain_options(owner.raw, words)
    percent_cell = _unique_pair(ratio.raw, words)
    footer_cell = _chain_options(footer.raw, words, caption=True)
    groups = (title_cell, owner_cell, percent_cell, footer_cell)
    if not all(groups) or len({word for group in groups for word in group}) != sum(map(len, groups)):
        return False
    # The final printed alias piece and the percentage must form one unique
    # physical row. This ties the ratio to the complete registered name chain.
    tail = _unique_pair(owner_cell[-1].text + " " + ratio.raw, words)
    if not tail or set(tail) != {owner_cell[-1], *percent_cell}:
        return False
    anchor = max(owner_cell, key=lambda word: math.dist(word.vertices[0], word.vertices[1]))
    a, b, *_ = anchor.vertices
    length = math.dist(a, b)
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    def bounds(group):
        xs = [ux * x + uy * y for word in group for x, y in word.vertices]
        ys = [-uy * x + ux * y for word in group for x, y in word.vertices]
        return min(xs), max(xs), min(ys), max(ys)
    title_box, owner_box, percent_box, footer_box = map(bounds, groups)
    height = max(owner_box[3] - owner_box[2], percent_box[3] - percent_box[2])
    centers = [(box[2] + box[3]) / 2 for box in (title_box, owner_box, percent_box, footer_box)]
    if (not centers[0] < centers[1] < centers[3] or not centers[0] <= centers[2] < centers[3]
            or not -2 <= percent_box[0] - owner_box[1] <= 6 * height
            or min(owner_box[0], percent_box[0]) < footer_box[0] - height
            or max(owner_box[1], percent_box[1]) > footer_box[1] + height):
        return False
    return True


def verified_single_part_layout(raw, layout):
    """Render the proved physical pair, preserving every literal source token."""
    from apps.text.parse_label import build_line_infos

    if not literal_single_part_table_over_failed_layout(raw, layout):
        return None
    infos = build_line_infos(raw.text)
    owner = next(info for info in infos if info.materials)
    ratio = next(info for info in infos if "%" in info.normalized)
    lines = raw.text.splitlines()
    owners = [i for i, line in enumerate(lines) if normalize_text(line) == owner.normalized]
    ratios = [i for i, line in enumerate(lines) if normalize_text(line) == ratio.normalized]
    if len(owners) != 1 or len(ratios) != 1 or owners[0] == ratios[0]:
        return None
    lines[owners[0]] = lines[owners[0]].rstrip() + " " + lines[ratios[0]].strip()
    lines[ratios[0]] = ""
    rendered = "\n".join(lines)
    if Counter(literal_tokens(rendered)) != Counter(literal_tokens(raw.text)):
        return None
    return rendered
