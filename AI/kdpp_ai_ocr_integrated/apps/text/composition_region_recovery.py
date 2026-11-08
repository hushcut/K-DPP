"""Verify a labelled material table and a separate written care-number cell."""

from collections import Counter
from dataclasses import dataclass
import math
import re
import unicodedata

from apps.text.candidate_evidence import _has_explicit_complete_pairs
from apps.text.care_cell_geometry import care_cell_clear, vertical_care_cell
from apps.text.line_context import COMPOSITION_HINTS
from apps.text.material_extraction import (
    NEGATING_MODIFIERS, UNPRICED_MATERIALS, _material_evidence, declared_part, find_material_key,
    unresolved_material_tokens,
)
from apps.text.ocr_geometry import (
    _covers_row_tokens, _row_options, _tokens, complete_annotation_geometry, same_place_annotations,
)
from apps.text.ocr_row_search import physical_row_options


@dataclass(frozen=True)
class _Region:
    item: object
    groups: tuple
    prefix: tuple
    heading: tuple
    footer: tuple
    footer_lines: tuple


def _region(item, rows, tokenise):
    from apps.text.parse_label import build_line_infos

    lines = [line.strip() for line in item.text.splitlines() if line.strip()]
    headings = [i for i, line in enumerate(lines)
                if "".join(tokenise(line)) in {"品質表示", "composition"}]
    if len(headings) != 1 or not complete_annotation_geometry(item, tokenise):
        return None
    h = headings[0]
    before = [unicodedata.normalize("NFKC", line).casefold() for line in lines[:h]]
    if before and (not 1 <= len(before) <= 2
                   or not re.fullmatch(r"(?:チェスト|chest)\s*\d{1,4}(?:(?:\s*[-~〜]\s*|\s+)\d{1,4})?", before[0])
                   or len(before) == 2 and not re.fullmatch(r"(?:xxs|xs|s|m|l|xl|xxl|2xl|3xl|[1-5]l)", before[1])):
        return None
    if any(info.marker_part is not None for info in build_line_infos(item.text)):
        return None
    groups = []
    for row in rows:
        options = physical_row_options(row.raw, item.image_words, tokenise=tokenise)
        if len(options) != 1:
            return None
        groups.append(tuple(item.image_words[index] for index in options[0]))
        number = re.search(r"\d+(?:[.,]\d+)?(?=\s*%)", row.raw)
        if number is None:
            return None
        for other in rows:
            other_number = re.search(r"\d+(?:[.,]\d+)?(?=\s*%)", other.raw)
            if other_number is None:
                return None
            if number.group() != other_number.group():
                swapped = row.raw[:number.start()] + other_number.group() + row.raw[number.end():]
                if physical_row_options(swapped, item.image_words, tokenise=tokenise):
                    return None
    core = {word for group in groups for word in group}
    if len(core) != sum(map(len, groups)):
        return None
    heading_options = physical_row_options(lines[h], item.image_words, tokenise=tokenise)
    if len(heading_options) != 1:
        return None
    heading = tuple(item.image_words[index] for index in heading_options[0])
    if core.intersection(heading):
        return None
    remaining = tuple(word for word in item.image_words if word not in core and word not in heading)
    prefix = ()
    if before:
        options = _row_options("\n".join(lines[:h]), remaining, tokenise=tokenise)
        if len(options) != 1:
            return None
        prefix = tuple(remaining[index] for index in options[0])
    footer = tuple(word for word in remaining if word not in prefix)
    needed = Counter(token for word in core for token in tokenise(word.text))
    collected = Counter()
    end = h + 1
    while collected != needed and end < len(lines):
        collected.update(tokenise(lines[end]))
        if not collected <= needed:
            return None
        end += 1
    if (collected != needed
            or not _covers_row_tokens(tokenise("\n".join(lines[h + 1:end])), list(core), tokenise=tokenise)
            or not _covers_row_tokens(tokenise("\n".join(lines[end:])), list(footer), tokenise=tokenise)):
        return None
    for group in groups:
        anchor = max(group, key=lambda word: math.dist(word.vertices[0], word.vertices[1]))
        (x0, y0), (x1, y1), *_ = anchor.vertices
        length = math.hypot(x1 - x0, y1 - y0)
        nx, ny = -(y1 - y0) / length, (x1 - x0) / length
        low = min(nx * x + ny * y for word in group for x, y in word.vertices)
        high = max(nx * x + ny * y for word in group for x, y in word.vertices)
        if (any(max(nx * x + ny * y for x, y in word.vertices) >= low - 1 for word in prefix + heading)
                or any(min(nx * x + ny * y for x, y in word.vertices) <= high + 1 for word in footer)):
            return None
    forbidden = NEGATING_MODIFIERS | UNPRICED_MATERIALS | {"unknown", "olefin", "未知繊維", "未知纤维"}
    if any(token in forbidden for token in _tokens(item.text)):
        return None
    if any("%" in line or declared_part(line) or unresolved_material_tokens(line)
           or any(find_material_key(token) for token in _tokens(line)) for line in lines[:h] + lines[end:]):
        return None
    if any("".join(tokenise(hint)) in "".join(tokenise(line))
           for hint in COMPOSITION_HINTS | {"素材"} for line in lines[end:]):
        return None
    return _Region(item, tuple(groups), prefix, heading, footer, tuple(lines[end:]))


def _care(region, temperature, tokenise):
    from apps.text.parse_label import _WASH_TEMPERATURE_CAPTIONS

    captions = {tokenise(line) for line in _WASH_TEMPERATURE_CAPTIONS}
    lines = region.footer_lines
    matches = [i for i in range(len(lines) - 1)
               if tokenise(lines[i]) in captions and lines[i + 1] == str(temperature)]
    if len(matches) != 1:
        return None
    position = matches[0]
    if any(re.search(r"[\d%?？±≈~+\-−]", line) for i, line in enumerate(lines) if i != position + 1):
        return None
    options = physical_row_options(lines[position], region.footer, tokenise=tokenise)
    numbers = [word for word in region.footer if word.text.strip() == str(temperature)]
    if len(options) != 1 or len(numbers) != 1:
        return None
    caption = tuple(region.footer[index] for index in options[0])
    number = numbers[0]
    if (not vertical_care_cell(caption, number)
            or not care_cell_clear(region.item.image_words, caption, number)):
        return None
    return caption, number


def _outside_crop(word, region):
    left, top, right, bottom = region
    return (word.right <= left or word.left >= right
            or word.bottom <= top or word.top >= bottom)


def _literal_pair(info, tokenise):
    evidence = _material_evidence(info.normalized)
    ratio = re.search(r"\d+(?:[.,]\d+)?\s*%", info.raw)
    if len(evidence) != 1 or ratio is None:
        return False
    name = info.normalized[evidence[0].start:evidence[0].end]
    # A bare NOT/PURE/etc. row cannot disappear into an apparently complete
    # declaration merely because the parser recognizes one fiber within it.
    return (find_material_key(name) == info.materials[0]
            and tokenise(info.raw) in (tokenise(name) + tokenise(ratio.group()),
                                       tokenise(ratio.group()) + tokenise(name)))


def recover_composition_region(candidate, alternative, part, candidates, *, tokenise):
    """Resolve only complete physical pairs and a proved, separate care cell."""
    from apps.text.parse_label import build_line_infos

    if (part != "generic" or candidate.parser_status != "failed" or candidate.parts or candidate.conflicting_parts
            or set(candidate.unpaired_ratio_parts) != {part}
            or set(candidate.parser_warnings) - {"generic:unpaired_ratio_rows"}
            or set(candidate.rejected_composition_parts) - {part}
            or set(candidate.rejected_composition_parts.get(part, ())) - {"unpaired_material_rows"}
            or not alternative.layout_used or alternative.selected_part != part
            or set(alternative.parts) != {part} or not 2 <= len(alternative.parts[part]) <= 4
            or any(not 0 < value < 100 for value in alternative.parts[part].values())
            or sum(alternative.parts[part].values()) != 100 or not _has_explicit_complete_pairs(alternative)
            or candidate.image_key != alternative.image_key
            or {word.page for word in candidate.image_words} != {word.page for word in alternative.image_words}
            or not complete_annotation_geometry(candidate, tokenise)):
        return False
    expected = alternative.parts[part]
    rows = [info for info in build_line_infos(alternative.text) if info.materials]
    if (len(rows) != len(expected)
            or any(info.part != part or info.marker_part is not None or len(info.materials) != 1
                   or len(info.numbers) != 1 or not info.explicit_percent
                   or info.invalid_evidence or info.unresolved_materials
                   or not _literal_pair(info, tokenise) for info in rows)
            or Counter((info.materials[0], float(info.numbers[0])) for info in rows) != Counter(expected.items())):
        return False
    target = _region(alternative, rows, tokenise)
    if target is None or target.footer:
        return False
    if (set(candidate.observed_materials) != {part} or set(candidate.observed_ratios) != {part}
            or Counter(candidate.observed_materials[part]) != Counter(expected.keys())):
        return False
    wanted = Counter(expected.values())
    observed = Counter(candidate.observed_ratios[part])
    if not wanted <= observed:
        return False
    extra = list((observed - wanted).elements())
    if len(extra) > 1 or extra and extra[0] not in {30, 40, 50, 60, 70, 95}:
        return False
    for raw in candidates:
        if (raw.layout_used or raw.source != candidate.source or raw.image_key != candidate.image_key
                or raw.image_variant_key != candidate.image_variant_key
                or raw.image_words != candidate.image_words or raw.image_region != candidate.image_region
                or Counter(tokenise(raw.text)) != Counter(tokenise(candidate.text))
                or raw.observed_materials != candidate.observed_materials
                or raw.observed_ratios != candidate.observed_ratios):
            continue
        source = _region(raw, rows, tokenise)
        if source is None or any(not same_place_annotations(a, b) for a, b in zip(source.groups, target.groups)):
            continue
        if not extra:
            if (not source.footer and raw.source == alternative.source
                    and raw.image_variant_key == alternative.image_variant_key
                    and raw.image_words == alternative.image_words and raw.image_region == alternative.image_region
                    and Counter(tokenise(raw.text)) == Counter(tokenise(alternative.text))):
                return True
            continue
        temperature = int(extra[0])
        if raw.source == alternative.source or raw.image_variant_key == alternative.image_variant_key:
            continue
        if (sum(line == str(temperature) for line in source.footer_lines) != 1
                or any(re.search(r"[\d%?？±≈~+\-−]", line)
                       for line in source.footer_lines if line != str(temperature))):
            continue
        numbers = [word for word in source.footer if word.text.strip() == str(temperature)]
        if len(numbers) != 1 or not _outside_crop(numbers[0], alternative.image_region):
            continue
        for proof in candidates:
            if (proof.layout_used or proof.source != "original" or proof.image_key != raw.image_key
                    or {word.page for word in proof.image_words} != {word.page for word in raw.image_words}):
                continue
            proof_region = _region(proof, rows, tokenise)
            cell = _care(proof_region, temperature, tokenise) if proof_region is not None else None
            if cell is None:
                continue
            caption, number = cell
            if (any(not _outside_crop(word, alternative.image_region) for word in caption + (number,))
                    or not same_place_annotations((numbers[0],), (number,))
                    or any(not same_place_annotations(a, b) for a, b in zip(proof_region.groups, target.groups))):
                continue
            allowed = tuple(word for word in raw.image_words if word in caption)
            if care_cell_clear(raw.image_words, caption, number, allowed_words=allowed + (numbers[0],)):
                return True
    return False
