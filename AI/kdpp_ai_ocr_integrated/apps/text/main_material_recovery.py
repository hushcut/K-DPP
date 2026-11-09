"""Recover only physically bounded, repeated MAIN MATERIAL declarations."""

from collections import Counter
import math
import re
import unicodedata

from apps.text.material_extraction import (
    ALIAS_TO_MATERIAL, NEGATING_MODIFIERS, UNPRICED_MATERIALS, declared_part,
    find_material_key,
)
from apps.text.ocr_geometry import complete_annotation_geometry, _covers_row_tokens, _row_options, _tokens
from apps.text.ocr_row_search import physical_row_options
from apps.text.rules import EQUIVALENT_MATERIALS


def _literal(text):
    return unicodedata.normalize("NFKC", text).casefold()


def _canonical(material):
    return EQUIVALENT_MATERIALS.get(material, material)


def _frame(group):
    anchor = max(group, key=lambda word: math.dist(word.vertices[0], word.vertices[1]))
    (x0, y0), (x1, y1), *_ = anchor.vertices
    length = math.hypot(x1 - x0, y1 - y0)
    direction = ((x1 - x0) / length, (y1 - y0) / length)
    return direction, (-direction[1], direction[0])


def _extent(group, axis):
    values = [axis[0] * x + axis[1] * y for word in group for x, y in word.vertices]
    return min(values), max(values)


def _same_direction(group, direction):
    for word in group:
        (x0, y0), (x1, y1), *_ = word.vertices
        length = math.hypot(x1 - x0, y1 - y0)
        if not length or ((x1 - x0) * direction[0] + (y1 - y0) * direction[1]) / length < math.cos(math.radians(3)):
            return False
    return True


def _isolated_row(group, words):
    _, normal = _frame(group)
    for other in words:
        if other in group:
            continue
        other_low, other_high = _extent((other,), normal)
        for word in group:
            low, high = _extent((word,), normal)
            gap = abs((low + high - other_low - other_high) / 2)
            if gap <= max(2.0, 0.55 * min(high - low, other_high - other_low)):
                return False
    return True


def _unique_physical(text, words, tokenise):
    options = physical_row_options(text, words, tokenise=tokenise)
    return tuple(words[index] for index in options[0]) if len(options) == 1 else None


def _body_pattern(material):
    aliases = [name for name, value in ALIAS_TO_MATERIAL.items() if _canonical(value) == material]
    names = "|".join(re.escape(name).replace(r"\ ", r"\s+")
                     for name in sorted(aliases, key=len, reverse=True))
    if not names:
        return None
    return re.compile(
        rf"(?P<pair>(?:100\s*%\s*(?:{names})|(?:{names})\s+100\s*%))\s*"
        r"(?P<property>\(\s*(?:100\s*%\s*(?:recycled|recycle|recyclé)|再生)\s*\))",
        re.IGNORECASE,
    )


def _bounded(words, header, boundary, contents, pattern, tokenise):
    head = _unique_physical(header, words, tokenise)
    end = _unique_physical(boundary, words, tokenise)
    if not head or not end or set(head).intersection(end):
        return None
    direction, normal = _frame(head)
    if not _same_direction(end, direction):
        return None

    def center(word):
        low, high = _extent((word,), normal)
        return (low + high) / 2

    low, high = max(map(center, head)), min(map(center, end))
    if low >= high:
        return None
    pool = tuple(word for word in words if low + 1 < center(word) < high - 1)
    choices = [(index, pattern.fullmatch(_literal("\n".join(contents[index:]))))
               for index in range(len(contents))]
    choices = [(index, match) for index, match in choices if match]
    if len(choices) != 1:
        return None
    start, match = choices[0]
    body_lines = contents[start:]
    if not 1 <= len(body_lines) <= 2:
        return None
    groups = [_unique_physical(line, pool, tokenise) for line in body_lines]
    if any(group is None for group in groups):
        return None
    if any(not _same_direction(group, direction) for group in groups):
        return None
    used = {word for group in groups for word in group}
    if (len(used) != sum(map(len, groups)) or used != set(pool)
            or not _covers_row_tokens(tokenise("\n".join(body_lines)), list(used), tokenise=tokenise)):
        return None
    # An opaque caption after MAIN in provider paragraph order may actually
    # precede its printed heading. It is never accepted inside the main block.
    extra = ()
    if start:
        text = "\n".join(contents[:start])
        if (re.search(r"\d|%", text) or declared_part(text)
                or any(find_material_key(token) for token in _tokens(text))):
            return None
        options = _row_options(text, words, tokenise=tokenise)
        if len(options) != 1:
            return None
        extra = tuple(words[index] for index in options[0])
        if any(_extent((word,), normal)[1] >= _extent(head, normal)[0] - 1 for word in extra):
            return None
    return set(head) | used | set(extra), int("%" in match.group("property"))


def recover_main_material_layout(candidate, alternative, part, *, tokenise):
    """Release this layout's outer veto, preserving every other part's errors.

    Three literal GB/F/CN main declarations must agree. English/French blocks
    are closed by their own printed rib heading; the Chinese declaration is
    a complete physical row. No raw text or recycled-content note is removed.
    """
    reasons = set(candidate.rejected_composition_parts.get("outer", ()))
    if (part != "outer" or not candidate.layout_used or alternative.layout_used
            or candidate.parser_status != "failed" or alternative.parser_status != "success"
            or "outer" in candidate.parts or not reasons
            or reasons - {"unpaired_material_rows", "unresolved_material_token"}
            or alternative.selected_part != "outer" or "outer" not in alternative.parts
            or len(alternative.parts["outer"]) != 1
            or tuple(alternative.parts["outer"].values()) != (100,)
            or "outer" in alternative.rejected_composition_parts
            or "outer" in alternative.unpaired_ratio_parts
            or "outer" in candidate.conflicting_parts or "outer" in alternative.conflicting_parts
            or any("outer_2" in (item.parts.keys() | item.observed_materials.keys()
                                 | item.rejected_composition_parts.keys())
                   for item in (candidate, alternative))
            or not candidate.image_key or not candidate.image_variant_key or not candidate.source
            or candidate.image_key != alternative.image_key
            or candidate.image_variant_key != alternative.image_variant_key
            or candidate.source != alternative.source or candidate.image_region != alternative.image_region
            or candidate.image_words != alternative.image_words
            or not complete_annotation_geometry(candidate, tokenise)
            or not complete_annotation_geometry(alternative, tokenise)
            or Counter(tokenise(candidate.text)) != Counter(tokenise(alternative.text))):
        return False
    material = _canonical(next(iter(alternative.parts["outer"])))
    expected_materials = Counter({material: 3})
    if (Counter(map(_canonical, alternative.observed_materials.get("outer", ()))) != expected_materials
            or Counter(map(_canonical, candidate.observed_materials.get("outer", ()))) != expected_materials
            or Counter(alternative.observed_ratios.get("outer", ())) != Counter({100: 3})):
        return False
    forbidden = NEGATING_MODIFIERS | UNPRICED_MATERIALS | {"unknown", "olefin", "未知繊維", "未知纤维"}
    if any(token in forbidden for token in _tokens(alternative.text)):
        return False
    pattern = _body_pattern(material)
    if pattern is None:
        return False
    lines = [line.strip() for line in alternative.text.splitlines() if line.strip()]
    gb = [i for i, line in enumerate(lines) if re.fullmatch(r"gb\s*:\s*main\s+material\s*:", _literal(line))]
    fr = [i for i, line in enumerate(lines) if re.fullmatch(r"f(?:r)?\s*:\s*mati[eè]re\s+principale\s*:", _literal(line))]
    cn = [(i, re.fullmatch(r"cn\s*:\s*主料\s*:\s*(.+)", _literal(line)))
          for i, line in enumerate(lines)]
    cn = [(i, match) for i, match in cn if match]
    if len(gb) != 1 or len(fr) != 1 or len(cn) != 1 or not gb[0] < fr[0] < cn[0][0]:
        return False
    sections = []
    for start, stop, boundary_pattern in (
        (gb[0], fr[0], r"rib\s+part\s*:"),
        (fr[0], cn[0][0], r"empi[eè]cement\s+en\s+bord\s+c[oô]te\s*:"),
    ):
        ends = [i for i in range(start + 1, stop)
                if re.match(boundary_pattern, _literal(lines[i]))]
        if len(ends) != 1:
            return False
        end = ends[0]
        section = _bounded(alternative.image_words, lines[start], lines[end],
                           lines[start + 1:end], pattern, tokenise)
        if section is None:
            return False
        sections.append(section)
    cn_index, cn_match = cn[0]
    cn_body = pattern.fullmatch(cn_match.group(1))
    group = _unique_physical(lines[cn_index], alternative.image_words, tokenise)
    if cn_body is None or group is None or not _isolated_row(group, alternative.image_words):
        return False
    following = next((line for line in lines[cn_index + 1:]
                      if declared_part(line) not in (None, "outer")), None)
    end = _unique_physical(following, alternative.image_words, tokenise) if following else None
    direction, normal = _frame(group)
    if not end or not _same_direction(end, direction) or set(group).intersection(end):
        return False
    if max(sum(_extent((word,), normal)) / 2 for word in group) + 1 >= min(
            sum(_extent((word,), normal)) / 2 for word in end):
        return False
    sections.append((set(group), int("%" in cn_body.group("property"))))
    all_words = set().union(*(words for words, _count in sections))
    if len(all_words) != sum(len(words) for words, _count in sections):
        return False
    # The parser may miss a mixture ratio or count the closed property as
    # another one. Only the already printed, physically proved 100 values fit.
    available = Counter({100: 3 + sum(count for _words, count in sections)})
    return Counter(candidate.observed_ratios.get("outer", ())) <= available
