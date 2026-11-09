"""Verify repeated outer declarations against a separate physical reread."""

from collections import Counter
import math
import re

from apps.text.candidate_evidence import _has_explicit_complete_pairs
from apps.text.material_extraction import (
    NEGATING_MODIFIERS, UNPRICED_MATERIALS, declared_part, find_material_key,
    unresolved_material_tokens,
)
from apps.text.ocr_geometry import (
    _covers_row_tokens, _overlaps, _row_options,
    complete_annotation_geometry as _complete_geometry,
    same_place_annotations as _same_place,
)


def _declarations(item, tokenise):
    from apps.text.parse_label import build_line_infos

    if (item.layout_used or item.selected_part != "outer" or set(item.parts) != {"outer"}
            or len(item.parts["outer"]) != 2 or sum(item.parts["outer"].values()) != 100
            or not _has_explicit_complete_pairs(item) or not _complete_geometry(item, tokenise)):
        return None
    infos = build_line_infos(item.text)
    rows = [info for info in infos if info.materials]
    if (not 3 <= len(rows) <= 4
            or len({tokenise(info.raw) for info in rows}) != len(rows)
            or any(info.part != "outer" or info.marker_part != "outer"
                   or len(info.materials) != 2 or len(info.numbers) != 2
                   or not info.explicit_percent or info.invalid_evidence or info.unresolved_materials
                   or Counter(zip(info.materials, map(float, info.numbers)))
                   != Counter(item.parts["outer"].items()) for info in rows)):
        return None
    lines = [line.strip() for line in item.text.splitlines() if line.strip()]
    positions = [[i for i, line in enumerate(lines) if tokenise(line) == tokenise(info.raw)] for info in rows]
    if any(len(indices) != 1 for indices in positions):
        return None
    indices = [position[0] for position in positions]
    if indices != list(range(indices[0], indices[0] + len(rows))):
        return None
    before, after = lines[:indices[0]], lines[indices[-1] + 1:]
    # A labelled SKU and a printed choking-hazard caption are explicit
    # metadata boundaries. An arbitrary brand or unknown fiber is not one.
    if before and (len(before) != 2 or not re.fullmatch(r"style\s+no\s*:", before[0].casefold())
                   or not re.fullmatch(r"(?=[a-z0-9-]*[a-z])(?=[a-z0-9-]*\d)[a-z0-9]+(?:-[a-z0-9]+)*",
                                       before[1].casefold())):
        return None
    if after and (len(after) != 2 or not re.fullmatch(r"\d{3,6}", after[0]) or int(after[0]) <= 100
                  or not re.fullmatch(r"[가-힣\s]*삼킬\s*수\s*있으므로\s*주의\s*하십시오[.!]*", after[1])):
        return None
    forbidden = NEGATING_MODIFIERS | UNPRICED_MATERIALS | {"unknown", "olefin", "未知繊維", "未知纤维"}
    from apps.text.ocr_geometry import _tokens

    if any("%" in line or declared_part(line) or unresolved_material_tokens(line)
           or any(find_material_key(token) or token in forbidden for token in _tokens(line))
           for line in before + after):
        return None
    return rows, before, after


def _context_outside(item, rows, groups, before, after, tokenise, *, reference_groups=None):
    core = {word for group in groups for word in group}
    if len(core) != sum(map(len, groups)):
        return False
    remaining = tuple(word for word in item.image_words if word not in core)
    prefix = ()
    if before:
        options = _row_options("\n".join(before), remaining, tokenise=tokenise)
        if len(options) != 1:
            return False
        prefix = tuple(remaining[index] for index in options[0])
    suffix = tuple(word for word in remaining if word not in prefix)
    if (not _covers_row_tokens(tokenise("\n".join(after)), list(suffix), tokenise=tokenise)
            or not _covers_row_tokens(tokenise("\n".join(info.raw for info in rows)), list(core), tokenise=tokenise)):
        return False
    for group, reference in zip(groups, reference_groups or groups):
        # Once all source glyphs match a strict reread at the same positions,
        # use its verified direction instead of the source's noisy top edge.
        # The source polygons and their full context remain unchanged.
        anchor = max(reference, key=lambda word: math.dist(word.vertices[0], word.vertices[1]))
        (x0, y0), (x1, y1), *_ = anchor.vertices
        length = math.hypot(x1 - x0, y1 - y0)
        nx, ny = -(y1 - y0) / length, (x1 - x0) / length

        def extent(words):
            values = [nx * x + ny * y for word in words for x, y in word.vertices]
            return min(values), max(values)

        low, high = extent(group)
        if (any(extent((word,))[1] >= low - 1 for word in prefix)
                or any(extent((word,))[0] <= high + 1 for word in suffix)):
            return False
    return True


def recover_multilingual_outer_layout(candidate, alternative, part, candidates, *, tokenise):
    """Release one failed layout only after a different input proves every row."""
    if (part not in {"generic", "outer"} or not candidate.layout_used
            or candidate.parser_status != "failed" or candidate.parts or candidate.conflicting_parts
            or set(candidate.rejected_composition_parts) != {"generic"}
            or not candidate.rejected_composition_parts["generic"]
            or set(candidate.rejected_composition_parts["generic"])
            - {"invalid_composition_evidence", "unpaired_material_rows"}
            or set(candidate.unpaired_ratio_parts) - {"generic", "outer"}
            or set(candidate.observed_materials) - {"generic", "outer"}
            or set(candidate.observed_ratios) - {"generic", "outer"}
            or alternative.parser_status != "success" or alternative.conflicting_parts
            or set(alternative.parts) != {"outer"} or not _complete_geometry(candidate, tokenise)):
        return False
    from apps.text.ocr_row_search import physical_row_options

    for raw in candidates:
        if (raw.layout_used or raw.source != candidate.source or raw.image_key != candidate.image_key
                or raw.image_variant_key != candidate.image_variant_key
                or raw.image_words != candidate.image_words or raw.image_region != candidate.image_region
                or Counter(tokenise(raw.text)) != Counter(tokenise(candidate.text))
                or raw.parts != alternative.parts):
            continue
        declaration = _declarations(raw, tokenise)
        if declaration is None:
            continue
        rows, before, after = declaration
        if (Counter(material for values in candidate.observed_materials.values() for material in values)
                != Counter(raw.observed_materials["outer"])
                or Counter(value for values in candidate.observed_ratios.values() for value in values)
                != Counter(raw.observed_ratios["outer"])):
            continue
        direct = [physical_row_options(info.raw, raw.image_words, tokenise=tokenise) for info in rows]
        if any(len(options) > 1 for options in direct) or sum(bool(options) for options in direct) < len(rows) - 1:
            continue
        for target in candidates:
            if (target.layout_used or target.source == raw.source or target.image_key != raw.image_key
                    or not target.image_variant_key or target.image_variant_key == raw.image_variant_key
                    or {word.page for word in target.image_words} != {word.page for word in raw.image_words}
                    or target.parts != raw.parts):
                continue
            target_declaration = _declarations(target, tokenise)
            if target_declaration is None:
                continue
            target_rows, target_before, target_after = target_declaration
            if [tokenise(info.raw) for info in target_rows] != [tokenise(info.raw) for info in rows]:
                continue
            target_options = [physical_row_options(info.raw, target.image_words, tokenise=tokenise)
                              for info in target_rows]
            if any(len(options) != 1 for options in target_options):
                continue
            target_groups = [tuple(target.image_words[index] for index in options[0]) for options in target_options]
            groups = []
            strict_words = {raw.image_words[index] for options in direct for choice in options for index in choice}
            for info, strict, target_group in zip(rows, direct, target_groups):
                if strict:
                    group = tuple(raw.image_words[index] for index in strict[0])
                else:
                    pool = tuple(word for word in raw.image_words if word not in strict_words
                                 and any(_overlaps(word, other) for other in target_group))
                    options = _row_options(info.raw, pool, tokenise=tokenise)
                    if len(options) != 1:
                        break
                    group = tuple(pool[index] for index in options[0])
                if not _same_place(group, target_group):
                    break
                groups.append(group)
            else:
                if (_context_outside(raw, rows, groups, before, after, tokenise,
                                     reference_groups=target_groups)
                        and _context_outside(target, target_rows, target_groups, target_before, target_after, tokenise)):
                    return True
    return False
