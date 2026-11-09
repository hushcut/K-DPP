"""Verify a labelled, bounded single-fiber table without correcting OCR text."""

from collections import Counter
import math
import re

from apps.text.headed_inline_recovery import _hull, _overlap, _unique_pair, literal_tokens
from apps.text.material_extraction import NEGATING_MODIFIERS, UNPRICED_MATERIALS, _material_evidence, normalize_text
from apps.text.ocr_geometry import _row_options, complete_annotation_geometry, same_place_annotations


_TRIM = re.compile(r"\(\s*(?P<noun>[가-힣]{1,6})\s*,\s*상표\s*,\s*보강재\s*,\s*자수\s*,?\s*장식\s*제외\s*\)")
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


def _curved_name_ratio(name, owner, percentage, words):
    """A split literal alias can meet a ratio along a modest curved baseline.

    Each end must be a valid physical word/ratio. Its centre-to-centre bridge
    must agree with the mean of BOTH printed directions, with an empty gap.
    This cannot connect a lone guessed fragment or a different material row.
    """
    options = _row_options(name, owner, tokenise=literal_tokens)
    if len(options) != 1 or len(options[0]) < 2:
        return False
    alias = tuple(owner[i] for i in options[0])
    if alias[-1] != owner[-1] or not percentage:
        return False
    last, first = alias[-1], percentage[0]
    if not _unique_pair(last.text, (last,)):
        return False
    def direction(word):
        a, b, *_ = word.vertices
        size = math.dist(a, b)
        return ((b[0] - a[0]) / size, (b[1] - a[1]) / size)
    left, right = direction(last), direction(first)
    if sum(a * b for a, b in zip(left, right)) < math.cos(math.radians(10)):
        return False
    length = math.hypot(left[0] + right[0], left[1] + right[1])
    u = ((left[0] + right[0]) / length, (left[1] + right[1]) / length)
    normal = (-u[1], u[0])
    start = tuple((a + b) / 2 for a, b in zip(last.vertices[1], last.vertices[2]))
    end = tuple((a + b) / 2 for a, b in zip(first.vertices[0], first.vertices[3]))
    delta = (end[0] - start[0], end[1] - start[1])
    heights = [math.dist(word.vertices[0], word.vertices[3]) for word in (last, first)]
    gap = sum(a * b for a, b in zip(u, delta))
    if not (0 < gap <= 6 * max(heights)) or abs(sum(a * b for a, b in zip(normal, delta))) > .4 * min(heights):
        return False
    selected = (last, *percentage)
    envelope = _hull(point for word in selected for point in word.vertices)
    return all(word in selected or _PUNCTUATION.fullmatch(word.text.strip())
               or not _overlap(envelope, word.vertices) for word in words)


def literal_single_part_table_over_failed_layout(raw, layout):
    """Keep only a fully located outer declaration from one original reply."""
    return _literal_single_part_table(raw, layout, original_only=True)


def _literal_single_part_table(raw, layout, *, original_only):
    from apps.text.parse_label import build_line_infos, _is_metadata_line

    if ((original_only and raw.source != "original")
            or raw.source not in {"original", "preprocessed", "material_crop", "material_crop_rotated"}
            or raw.layout_used or not layout.layout_used
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
            or set(layout.observed_materials) - ({"generic", "outer"} if original_only
                                               else {"generic", "outer", "embroidery_yarn"})
            or set(layout.observed_ratios) - ({"generic", "outer"} if original_only
                                            else {"generic", "outer", "embroidery_yarn"})
            or Counter(material for values in layout.observed_materials.values() for material in values)
            != Counter(raw.parts["outer"].keys())):
        return False
    observed = [value for values in layout.observed_ratios.values() for value in values]
    # The literal percentage can be swallowed by a reordered exclusion block.
    # It must still exist exactly once in that block, never be supplied from
    # a size/identifier or inferred because a declaration ought to total 100.
    if 100 not in observed and not re.search(
        r"\([^)]*\b100\s*%[^)]*제외[^)]*\)", layout.text, re.DOTALL,
    ):
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
    noun = _TRIM.fullmatch(footer.normalized).group("noun")
    # A literal exclusion noun is retained as printed, not corrected to 심지.
    # Actual fibers, negation and unpriced materials cannot supply this fence.
    if _material_evidence(noun) or noun in NEGATING_MODIFIERS | UNPRICED_MATERIALS:
        return False
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
        name = owner.normalized[evidence[0].start:evidence[0].end]
        if not _curved_name_ratio(name, owner_cell, percent_cell, words):
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


def recover_corroborated_single_part_layout(candidate, alternative, part, candidates):
    """A crop's scrambled view cannot veto its own physically proved raw table.

    The original reply must independently retain the same outer declaration,
    heading and literal exclusion boundary at the same image coordinates.
    """
    from apps.text.parse_label import build_line_infos

    if (part not in {"generic", "outer", "embroidery_yarn"}
            or candidate.source not in {"preprocessed", "material_crop", "material_crop_rotated"}
            or not candidate.layout_used or candidate.parser_status != "failed"
            or alternative.source != "original" or alternative.layout_used
            or alternative.parser_status != "success" or set(alternative.parts) != {"outer"}
            or alternative.parser_warnings or alternative.unpaired_ratio_parts
            or alternative.rejected_composition_parts or alternative.conflicting_parts
            or alternative.unconfirmed_outer_parts
            or candidate.image_key != alternative.image_key
            or candidate.image_variant_key == alternative.image_variant_key
            or not complete_annotation_geometry(alternative, literal_tokens)):
        return False
    original = build_line_infos(alternative.text)
    original_owners = [row for row in original if row.materials]
    original_ratios = [row for row in original if '%' in row.raw]
    original_headings = [row for row in original if row.normalized in {"혼용률", "혼용율"}]
    original_footers = [row for row in original if _TRIM.fullmatch(row.normalized)]
    if not all(len(rows) == 1 for rows in (original_owners, original_ratios, original_headings, original_footers)):
        return False
    a, b, c, d = alternative.image_region
    left, top, right, bottom = candidate.image_region
    if not a <= left < right <= c or not b <= top < bottom <= d:
        return False
    for raw in candidates:
        if (raw.layout_used or raw.source != candidate.source
                or raw.image_key != candidate.image_key or raw.image_variant_key != candidate.image_variant_key
                or raw.image_words != candidate.image_words or raw.image_region != candidate.image_region
                or raw.parts != alternative.parts
                or not _literal_single_part_table(raw, candidate, original_only=False)):
            continue
        infos = build_line_infos(raw.text)
        owner = next(row for row in infos if row.materials)
        ratio = next(row for row in infos if '%' in row.raw)
        heading = next(row for row in infos if row.normalized in {"혼용률", "혼용율"})
        footer = next(row for row in infos if _TRIM.fullmatch(row.normalized))
        source_core = _chain_options(owner.raw, raw.image_words) + _unique_pair(ratio.raw, raw.image_words)
        target_core = (_chain_options(original_owners[0].raw, alternative.image_words)
                       + _unique_pair(original_ratios[0].raw, alternative.image_words))
        source_heading = _chain_options(heading.raw, raw.image_words)
        target_heading = _chain_options(original_headings[0].raw, alternative.image_words)
        source_footer = _chain_options(footer.raw, raw.image_words, caption=True)
        target_footer = _chain_options(original_footers[0].raw, alternative.image_words, caption=True)
        if (not all((source_core, target_core, source_heading, target_heading, source_footer, target_footer))
                or not same_place_annotations(source_core, target_core)
                or not same_place_annotations(source_heading, target_heading)
                or _content_tokens(footer.raw) != _content_tokens(original_footers[0].raw)):
            continue
        # Both complete literal lists are proved separately; OCR punctuation
        # may differ, but each substantive cell must overlap the other list.
        if (all(any(_overlap(word.vertices, other.vertices) for other in target_footer) for word in source_footer)
                and all(any(_overlap(word.vertices, other.vertices) for other in source_footer) for word in target_footer)):
            return True
    return False
