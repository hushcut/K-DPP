"""Keep a literal composition separate from verified fit/origin metadata."""

from collections import Counter
import math
import re

from apps.text.candidate_evidence import _has_explicit_complete_pairs
from apps.text.material_extraction import (
    NEGATING_MODIFIERS, UNPRICED_MATERIALS, _material_evidence, declared_part,
    find_material_key, unresolved_material_tokens,
)
from apps.text.ocr_geometry import _tokens, complete_annotation_geometry
from apps.text.ocr_row_search import physical_row_options


def recover_fit_origin_layout(candidate, alternative, part, *, tokenise):
    """Release only the failed reordered view of one explicit 100% fiber row."""
    from apps.text.parse_label import build_line_infos

    if (part != "generic" or not candidate.layout_used or alternative.layout_used
            or candidate.parser_status != "failed" or candidate.parts or candidate.conflicting_parts
            or set(candidate.rejected_composition_parts) != {part}
            or not candidate.rejected_composition_parts[part]
            or set(candidate.rejected_composition_parts[part])
            - {"invalid_composition_evidence", "unpaired_material_rows", "unresolved_material_token"}
            or set(candidate.unpaired_ratio_parts) - {part}
            or alternative.selected_part != part or set(alternative.parts) != {part}
            or len(alternative.parts[part]) != 1 or tuple(alternative.parts[part].values()) != (100,)
            or not _has_explicit_complete_pairs(alternative)
            or candidate.source != alternative.source or candidate.image_key != alternative.image_key
            or candidate.image_variant_key != alternative.image_variant_key
            or candidate.image_words != alternative.image_words or candidate.image_region != alternative.image_region
            or set(candidate.observed_materials) - {part} or set(candidate.observed_ratios) - {part}
            or not Counter(candidate.observed_materials.get(part, ())) <= Counter(alternative.observed_materials[part])
            or not Counter(candidate.observed_ratios.get(part, ())) <= Counter(alternative.observed_ratios[part])
            or Counter(tokenise(candidate.text)) != Counter(tokenise(alternative.text))
            or not complete_annotation_geometry(candidate, tokenise)
            or not complete_annotation_geometry(alternative, tokenise)):
        return False
    lines = [line.strip() for line in alternative.text.splitlines() if line.strip()]
    infos = build_line_infos(alternative.text)
    if not 3 <= len(lines) <= 5 or not infos or any(info.marker_part is not None for info in infos):
        return False
    first = infos[0]
    evidence = _material_evidence(first.normalized)
    if (first.part != part or first.materials != tuple(alternative.parts[part])
            or first.numbers != (100,) or not first.explicit_percent or len(evidence) != 1
            or first.invalid_evidence or first.unresolved_materials
            or tokenise(first.raw) != tokenise(lines[0])):
        return False
    name = first.normalized[evidence[0].start:evidence[0].end]
    if not re.fullmatch(r"[a-z]+(?:\s+[a-z]+)*", name):
        return False
    alias = r"\s+".join(map(re.escape, name.split()))
    if (not re.fullmatch(rf"(?:100\s*%\s*{alias}|{alias}\s*100\s*%)", lines[0].casefold())
            or not re.fullmatch(r"(?:regular|slim|relaxed|classic|loose|tailored)\s+fit", lines[1].casefold())
            or not re.fullmatch(r"made\s+in\s+[a-z]+(?:[ -][a-z]+)*", lines[2].casefold())):
        return False
    identifiers = (
        r"rn\s*\d{4,8}\s*[-/]\s*ca\s*\d{4,8}",
        r"(?:fr|eu|uk)\s*\d{1,3}\s*[-/]\s*us\s*(?:\d{1,3}|xxs|xs|s|m|l|xl|xxl|2xl|3xl)",
    )
    kinds = [next((i for i, pattern in enumerate(identifiers) if re.fullmatch(pattern, line.casefold())), None)
             for line in lines[3:]]
    if None in kinds or len(kinds) != len(set(kinds)):
        return False
    forbidden = NEGATING_MODIFIERS | UNPRICED_MATERIALS | {"unknown", "olefin", "未知繊維", "未知纤维"}
    if any("%" in line or declared_part(line) or unresolved_material_tokens(line)
           or any(find_material_key(token) or token in forbidden for token in _tokens(line))
           for line in lines[1:]):
        return False
    groups = []
    for line in lines:
        options = physical_row_options(line, alternative.image_words, tokenise=tokenise)
        if len(options) != 1:
            return False
        groups.append(tuple(alternative.image_words[index] for index in options[0]))
    if (len({word for group in groups for word in group}) != sum(map(len, groups))
            or sum(map(len, groups)) != len(alternative.image_words)):
        return False
    core = groups[0]
    anchor = max(core, key=lambda word: math.dist(word.vertices[0], word.vertices[1]))
    (x0, y0), (x1, y1), *_ = anchor.vertices
    length = math.hypot(x1 - x0, y1 - y0)
    direction = ((x1 - x0) / length, (y1 - y0) / length)
    nx, ny = -direction[1], direction[0]
    high = max(nx * x + ny * y for word in core for x, y in word.vertices)
    for group in groups[1:]:
        for word in group:
            (a, b), (c, d), *_ = word.vertices
            span = math.hypot(c - a, d - b)
            if not span or ((c - a) * direction[0] + (d - b) * direction[1]) / span < math.cos(math.radians(3)):
                return False
    return all(min(nx * x + ny * y for x, y in word.vertices) > high + 1
               for group in groups[1:] for word in group)
