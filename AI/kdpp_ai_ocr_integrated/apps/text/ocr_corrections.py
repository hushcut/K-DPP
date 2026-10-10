"""같은 이미지 위치의 재인식으로 확인된 OCR 손상만 후보 간 해소한다."""

from __future__ import annotations

import re
import math
from collections import Counter
from dataclasses import replace
from typing import TYPE_CHECKING

from apps.text.material_extraction import (
    NEGATING_MODIFIERS, UNPRICED_MATERIALS, find_material_key, normalize_text,
)
from apps.text.ocr_layout import OcrWord

if TYPE_CHECKING:
    from apps.text.ocr_candidates import OcrCandidate


_MAX_ROW_COVERAGE_STATES = 1024


def transform_words(words: tuple[OcrWord, ...], transform: tuple[float, ...]) -> tuple[OcrWord, ...]:
    a, b, c, d, e, f = transform
    mapped = []
    for word in words:
        points = word.vertices or ((word.left, word.top), (word.right, word.top),
                                   (word.right, word.bottom), (word.left, word.bottom))
        vertices = tuple((round(a * x + b * y + c), round(d * x + e * y + f)) for x, y in points)
        xs, ys = zip(*vertices)
        mapped.append(OcrWord(word.text, min(xs), min(ys), max(xs), max(ys),
                              vertices if word.vertices else (), word.page))
    return tuple(mapped)


def _tokens(text: str) -> tuple[str, ...]:
    # Vision text may join a fiber and ratio while word boxes split them.
    return tuple(re.findall(r"[^\W\d_]+|\d+|[^\w\s]", normalize_text(text)))


def _covers_row_tokens(row: tuple[str, ...], words: list[OcrWord], *, tokenise=_tokens) -> bool:
    sequences = Counter(tokenise(word.text) for word in words)
    if Counter(token for sequence, count in sequences.items()
               for token in sequence for _ in range(count)) != Counter(row):
        return False
    # Equal token totals alone do not rule out overlapping substring matches.
    # The boxes must also form a complete, disjoint partition of the row text.
    keys = tuple(sequences)
    pending = [(0, tuple(sequences[key] for key in keys))]
    seen = set(pending)
    while pending:
        index, counts = pending.pop()
        if index == len(row):
            return not any(counts)
        for position, sequence in enumerate(keys):
            if counts[position] and row[index:index + len(sequence)] == sequence:
                remaining = list(counts)
                remaining[position] -= 1
                state = (index + len(sequence), tuple(remaining))
                if state not in seen:
                    # Repeated, differently joined annotations can make the
                    # partition ambiguous. Hold recovery instead of spending
                    # unbounded time resolving that annotation ambiguity.
                    if len(seen) >= _MAX_ROW_COVERAGE_STATES:
                        return False
                    seen.add(state)
                    pending.append(state)
    return False


def _row_words(text: str, words: tuple[OcrWord, ...], *, tokenise=_tokens) -> tuple[OcrWord, ...]:
    row = tokenise(text)
    row_tokens = Counter(row)
    word_tokens = {value: tokenise(value) for value in dict.fromkeys(word.text for word in words)}
    matches = [word for word in words if word_tokens[word.text] and any(
        row[index:index + len(word_tokens[word.text])] == word_tokens[word.text]
        for index in range(len(row) - len(word_tokens[word.text]) + 1)
    )]
    anchors = [word for word in matches if len(normalize_text(word.text).strip()) > 1
               or normalize_text(word.text).strip().isdigit()]
    if not anchors:
        return tuple(matches) if (
            len(matches) == 1 and Counter(word_tokens[matches[0].text]) == row_tokens
        ) else ()
    # A repeated token in different physical rows cannot locate this row safely.
    counts = Counter(word_tokens[word.text] for word in anchors)
    if any(count > sum(row[i:i + len(token)] == token for i in range(len(row)))
           for token, count in counts.items()):
        return ()
    margin = max(word.height for word in anchors) * 0.7
    top, bottom = min(word.top for word in anchors) - margin, max(word.bottom for word in anchors) + margin
    selected = [word for word in matches if top <= word.center_y <= bottom]
    # The parser may join a number with its isolated percent row. A unique
    # percent word stays evidence even when the printed vertical gap is large.
    percent_words = [word for word in matches if normalize_text(word.text) == "%"]
    if len(percent_words) == 1 and percent_words[0] not in selected:
        selected.append(percent_words[0])
    # A generous row margin can touch the next ratio. Assign only its percent
    # box to the nearer numeric row; retain ties so ambiguity still fails.
    numeric_anchors = [word for word in anchors if any(token.isdecimal() for token in word_tokens[word.text])]
    other_numbers = [word for word in words if word not in numeric_anchors
                     and any(token.isdecimal() for token in word_tokens[word.text])]
    if numeric_anchors and other_numbers and len(percent_words) > 1:
        selected = [word for word in selected if normalize_text(word.text) != "%"
                    or min(abs(word.center_y - anchor.center_y) for anchor in numeric_anchors)
                    <= min(abs(word.center_y - anchor.center_y) for anchor in other_numbers)]
    # Every row token needs a box, including unknown fibers, modifiers and
    # signs. Matching only the numbers could erase an unlocated OLEFIN/FAUX
    # token when a valid crop is used to release the source rejection.
    # Token counts also prevent partial/duplicate boxes from sharing evidence;
    # joined or split material/number/percent boxes keep the same token counts.
    if not _covers_row_tokens(row, selected, tokenise=tokenise):
        return ()
    return tuple(selected)


def _physical_row(text: str, words: tuple[OcrWord, ...], *, allow_quantisation: bool = False,
                  tokenise=_tokens) -> bool:
    """Prove a row's reading direction and complete token order locally."""
    if not words or len({word.page for word in words}) != 1:
        return False
    frames = []
    for word in words:
        points = word.vertices or ((word.left, word.top), (word.right, word.top),
                                   (word.right, word.bottom), (word.left, word.bottom))
        if len(points) != 4:
            return False
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        bottom_length = math.hypot(x2 - x3, y2 - y3)
        if not length or not bottom_length:
            return False
        u = (dx / length, dy / length)
        v = ((x2 - x3) / bottom_length, (y2 - y3) / bottom_length)
        short_numeric = bool(allow_quantisation and length <= 32
                             and re.fullmatch(r"[0-9%]", normalize_text(word.text).strip()))
        if u[0] * v[0] + u[1] * v[1] < math.cos(math.radians(3)) and not short_numeric:
            return False
        normal = (-u[1], u[0])
        projections = [normal[0] * x + normal[1] * y for x, y in points]
        if max(projections) - min(projections) <= 0:
            return False
        frames.append((length, u, v, points, short_numeric))
    anchor = max(frames, key=lambda frame: frame[0])
    _, direction, _, _, _ = anchor
    normal = (-direction[1], direction[0])
    projected = []
    for word, (length, u, v, points, short_numeric) in zip(words, frames):
        bottom_length = math.hypot(points[2][0] - points[3][0], points[2][1] - points[3][1])
        quantised = (short_numeric and not anchor[4] and direction[0] * u[0] + direction[1] * u[1] > 0
                     and direction[0] * v[0] + direction[1] * v[1] > 0
                     and abs(normal[0] * u[0] + normal[1] * u[1]) * length <= 1
                     and abs(normal[0] * v[0] + normal[1] * v[1]) * bottom_length <= 1)
        if (direction[0] * u[0] + direction[1] * u[1] < math.cos(math.radians(3))
                or u[0] * v[0] + u[1] * v[1] < math.cos(math.radians(3))) and not quantised:
            return False
        ys = [normal[0] * x + normal[1] * y for x, y in points]
        xs = [direction[0] * x + direction[1] * y for x, y in points]
        projected.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), word))
    for left in projected:
        for right in projected:
            if abs(left[0] - right[0]) > max(2.0, 0.55 * min(left[1], right[1])):
                return False
    reading = tuple(token for *_rest, word in sorted(projected, key=lambda row: row[2])
                    for token in tokenise(word.text))
    return reading == tokenise(text)


def _row_options(text: str, words: tuple[OcrWord, ...], *, physical: bool = False,
                 allow_quantisation: bool = False, tokenise=_tokens):
    """Bounded, disjoint word partitions; identical physical rows stay distinct."""
    row = tokenise(text)
    sequences = tuple(tokenise(word.text) for word in words)
    pending = [(0, ())]
    seen = set()
    options = {}
    while pending:
        position, chosen = pending.pop()
        signature = (position, frozenset(chosen))
        if signature in seen:
            continue
        if len(seen) >= _MAX_ROW_COVERAGE_STATES:
            return ()
        seen.add(signature)
        if position == len(row):
            selected = tuple(words[index] for index in chosen)
            if not physical or (all(len(word.vertices) == 4 for word in selected)
                                and _physical_row(text, selected, allow_quantisation=allow_quantisation,
                                                  tokenise=tokenise)):
                options[frozenset(chosen)] = chosen
            continue
        for index, sequence in enumerate(sequences):
            if sequence and index not in chosen and row[position:position + len(sequence)] == sequence:
                pending.append((position + len(sequence), (*chosen, index)))
    return tuple(options.values())


def _locate_rows(infos, words: tuple[OcrWord, ...], *, physical: bool,
                 allow_quantisation: bool = False, tokenise=_tokens):
    if not infos or len(set(words)) != len(words):
        return []
    choices = [_row_options(info.raw, words, physical=bool(
        physical and info.materials and info.numbers and info.explicit_percent
    ), allow_quantisation=allow_quantisation, tokenise=tokenise) for info in infos]
    if any(not options for options in choices):
        return []
    pending = [(0, frozenset(), ())]
    seen = set()
    solution = None
    union = None
    while pending:
        position, used, assigned = pending.pop()
        state = (position, used)
        if state in seen:
            continue
        if len(seen) >= _MAX_ROW_COVERAGE_STATES:
            return []
        seen.add(state)
        if position == len(infos):
            # Swapping two identical text rows does not change their evidence.
            # Choosing only some of several possible physical rows does.
            if union is not None and used != union:
                return []
            union, solution = used, assigned
            continue
        for choice in choices[position]:
            chosen = frozenset(choice)
            if not used.intersection(chosen):
                pending.append((position + 1, used | chosen, (*assigned, choice)))
    if solution is None:
        return []
    return [(info, tuple(words[index] for index in choice)) for info, choice in zip(infos, solution)]


def _evidence_rows(candidate: OcrCandidate, part: str, *, tokenise=_tokens):
    from apps.text.parse_label import build_line_infos, _is_metadata_line

    # Percent proximity can locate a row without locating its surrounding
    # text. A failed layout still needs its complete annotation proof, or the
    # exact same-response raw peer must supply that proof through the narrow
    # fallback below. Never bypass its provenance checks with a clearer row.
    literal_annotations = tokenise is _annotation_tokens
    if ((literal_annotations or (candidate.layout_used and candidate.parser_status != "success"))
            and not _covers_row_tokens(tokenise(candidate.text), list(candidate.image_words), tokenise=tokenise)):
        return []
    all_infos = build_line_infos(candidate.text)
    infos = [info for info in all_infos
             if info.part == part and not _is_metadata_line(info)
             and (info.materials or info.numbers or info.explicit_percent
                  or info.invalid_evidence or info.unresolved_materials)]
    rows = []
    located_words = set()
    for info in infos:
        words = _row_words(info.raw, candidate.image_words, tokenise=tokenise)
        if (not words or located_words.intersection(words)
                or ((literal_annotations or candidate.parser_status == "success" or not candidate.layout_used)
                    and info.materials and info.numbers and info.explicit_percent
                    and not _physical_row(info.raw, words, tokenise=tokenise))):
            break
        located_words.update(words)
        rows.append((info, words))
    else:
        return rows
    # A repeated token is resolvable only when all image tokens are preserved
    # and the rows collectively select one complete, non-reused physical union.
    if not _covers_row_tokens(tokenise(candidate.text), list(candidate.image_words), tokenise=tokenise):
        return []
    assigned = _locate_rows(all_infos, candidate.image_words,
                            physical=literal_annotations or candidate.parser_status == "success" or not candidate.layout_used,
                            tokenise=tokenise)
    relevant = {info.index for info in infos}
    return [(info, words) for info, words in assigned if info.index in relevant]


def _overlaps(left: OcrWord, right: OcrWord) -> bool:
    if left.page != right.page:
        return False
    width = max(0, min(left.right, right.right) - max(left.left, right.left))
    height = max(0, min(left.bottom, right.bottom) - max(left.top, right.top))
    area = min(max(1, left.right - left.left) * left.height,
               max(1, right.right - right.left) * right.height)
    return width * height / area >= 0.25


def _one_digit_gap(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) != 1:
        return False
    longer, shorter = (left, right) if len(left) > len(right) else (right, left)
    return any(longer[:i] + longer[i + 1:] == shorter for i in range(len(longer)))


def _aligned_reading(words: tuple[OcrWord, ...], other: tuple[OcrWord, ...], *, literal_cjk: bool = False) -> bool:
    for word in words:
        token = normalize_text(word.text).replace(" ", "")
        if token in {":", ".", ",", ";", "/", "|", "(", ")", "[", "]"}:
            continue
        nearby = [target for target in other if _overlaps(word, target)]
        key = find_material_key(token)
        if any(token == normalize_text(target.text).replace(" ", "")
               or (key and find_material_key(target.text) == key)
               or (token == "%" and "%" in target.text)
               or (token.rstrip("%.").isdigit()
                   and token.rstrip("%.") == normalize_text(target.text).replace(" ", "").rstrip("%."))
               for target in nearby):
            continue
        if _matching_token_parts(word, nearby, allow_change=False, literal_cjk=literal_cjk) == 0:
            continue
        return False
    return True


def _matching_token_parts(word: OcrWord, nearby: list[OcrWord], *, allow_change: bool,
                          corroborated: bool = False, numeric_artifact: bool = False,
                          literal_cjk: bool = False) -> int | None:
    """Compare joined/split word annotations without losing any component."""
    tokenise = _annotation_tokens if literal_cjk else _tokens
    if literal_cjk:
        points = word.vertices or ((word.left, word.top), (word.right, word.top))
        dx, dy = points[1][0] - points[0][0], points[1][1] - points[0][1]
        nearby = sorted(nearby, key=lambda target: dx * target.center_x + dy * target.center_y)
    remaining = [token for target in nearby for token in tokenise(target.text)]
    changes = 0
    for token in _tokens(word.text):
        if literal_cjk and _has_cjk(token):
            # Match the complete literal sequence, never individual material
            # aliases. A joined target can cover several source boxes; the
            # disjoint character-slot proof below prevents sharing a fragment.
            sequence = _annotation_tokens(token)
            positions = [index for index in range(len(remaining) - len(sequence) + 1)
                         if tuple(remaining[index:index + len(sequence)]) == sequence]
            if not positions:
                return None
            index = positions[0]
            del remaining[index:index + len(sequence)]
            continue
        if token in {":", ",", ";", "/", "|", "(", ")", "[", "]"}:
            continue
        if token in remaining:
            remaining.remove(token)
            continue
        key = find_material_key(token)
        aliases = [value for value in remaining if key and find_material_key(value) == key]
        if aliases:
            remaining.remove(aliases[0])
            continue
        if allow_change and token.isdigit():
            numbers = [value for value in remaining if value.isdigit() and (
                _one_digit_gap(token, value) or (corroborated and len(token) == len(value)
                and sum(a != b for a, b in zip(token, value)) == 1)
            )]
            if numbers:
                remaining.remove(numbers[0])
                changes += 1
                continue
        if allow_change and not key and token.isascii() and token.isalpha():
            names = [value for value in remaining if find_material_key(value) and len(token) == len(value)
                     and sum(a != b for a, b in zip(token, value)) == 1]
            if names:
                remaining.remove(names[0])
                continue
        if allow_change and numeric_artifact and not key and token.isalpha() and len(token) <= 3:
            names = [value for value in remaining if not re.search(r"\d", value)]
            if names:
                remaining.remove(names[0])
                continue
        return None
    return changes


def _numeric_components_align(source: tuple[OcrWord, ...], target: tuple[OcrWord, ...],
                              context: tuple[OcrWord, ...], *, corroborated: bool) -> bool:
    """Each source number/percent needs its own overlapping reread component."""
    slots = [(word, token, word in context) for word in target + context
             for token in _tokens(word.text) if token.isdigit() or token == "%"]
    choices = []
    for word in source:
        for token in _tokens(word.text):
            if not (token.isdigit() or token == "%"):
                continue
            options = []
            for index, (other, value, is_context) in enumerate(slots):
                if not _overlaps(word, other):
                    continue
                if token == value:
                    options.append((index, 0))
                elif not is_context and token.isdigit() and value.isdigit() and (
                    _one_digit_gap(token, value) or (corroborated and len(token) == len(value)
                    and sum(a != b for a, b in zip(token, value)) == 1)
                ):
                    options.append((index, 1))
            if not options:
                return False
            choices.append(options)
    if len(choices) > len(slots):
        return False
    choices.sort(key=len)
    pending = [(0, frozenset(), 0)]
    seen = set()
    while pending:
        position, used, changes = pending.pop()
        state = (position, used, changes)
        if state in seen:
            continue
        if len(seen) >= _MAX_ROW_COVERAGE_STATES:
            return False
        seen.add(state)
        if position == len(choices):
            return True
        for index, change in choices[position]:
            if index not in used and changes + change <= 1:
                pending.append((position + 1, used | {index}, changes + change))
    return False


def _context_words(alternative: OcrCandidate, core: tuple[OcrWord, ...], *, tokenise=_tokens) -> tuple[OcrWord, ...]:
    """Preserve complete, non-composition text in a geometrically valid reread."""
    from apps.text.ocr_candidates import _has_explicit_complete_pairs
    from apps.text.parse_label import build_line_infos, _is_metadata_line

    if not _has_explicit_complete_pairs(alternative):
        return ()
    if not _covers_row_tokens(tokenise(alternative.text), list(alternative.image_words), tokenise=tokenise):
        return ()
    context = [info.raw for info in build_line_infos(alternative.text) if _is_metadata_line(info)
               or not (info.materials or info.numbers or info.explicit_percent
                       or info.invalid_evidence or info.unresolved_materials)]
    remaining = tuple(word for word in alternative.image_words if word not in core)
    if not _covers_row_tokens(tokenise("\n".join(context)), list(remaining), tokenise=tokenise):
        return ()
    return remaining


def _annotation_tokens(text: str) -> tuple[str, ...]:
    # CJK words may be split into multiple annotations without changing any
    # character. ASCII names, numbers and punctuation remain whole tokens.
    return tuple(value for token in _tokens(text)
                 for value in (tuple(re.findall(r"[a-z]+|[^a-z]", token))
                               if token.isalpha() and not token.isascii() else (token,)))


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7a3]", text))


def _cjk_components_align(source: tuple[OcrWord, ...], target: tuple[OcrWord, ...]) -> bool:
    """Each literal CJK character needs a distinct, overlapping target slot."""
    slots = [(word, token) for word in target for token in _annotation_tokens(word.text) if _has_cjk(token)]
    choices = []
    for word in source:
        for token in _annotation_tokens(word.text):
            if not _has_cjk(token):
                continue
            options = [index for index, (other, value) in enumerate(slots)
                       if token == value and _overlaps(word, other)]
            if not options:
                return False
            choices.append(options)
    if len(choices) > len(slots):
        return False
    choices.sort(key=len)
    pending = [(0, frozenset())]
    seen = set()
    while pending:
        position, used = pending.pop()
        state = (position, used)
        if state in seen:
            continue
        if len(seen) >= _MAX_ROW_COVERAGE_STATES:
            return False
        seen.add(state)
        if position == len(choices):
            return True
        for index in choices[position]:
            if index not in used:
                pending.append((position + 1, used | {index}))
    return False


def _bounded_composition_context(candidate: OcrCandidate) -> OcrCandidate | None:
    """Locate a composition between literal metadata/care fences.

    Opaque text alone is never a fence. Complete annotations are kept on the
    candidate; this view only prevents captions beyond a proved fence from
    vetoing a coordinate-verified reread of the composition itself.
    """
    from apps.text.parse_label import build_line_infos, _is_metadata_line

    if (not candidate.image_key or not candidate.image_variant_key or not candidate.image_words
            or len(candidate.image_region) != 4 or len(set(candidate.image_words)) != len(candidate.image_words)
            or len({word.page for word in candidate.image_words}) != 1
            or not _covers_row_tokens(_annotation_tokens(candidate.text), list(candidate.image_words),
                                     tokenise=_annotation_tokens)):
        return None
    left, top, right, bottom = candidate.image_region
    if any(not (left - 2 <= word.left and word.right <= right + 2
                and top - 2 <= word.top and word.bottom <= bottom + 2) for word in candidate.image_words):
        return None
    # An explicit unknown/material declaration anywhere cannot be dismissed as
    # a brand caption merely because a metadata fence separates it.
    forbidden = NEGATING_MODIFIERS | UNPRICED_MATERIALS | {"unknown", "olefin", "未知繊維", "未知纤维"}
    if any(token in forbidden for token in _tokens(candidate.text)):
        return None
    lines = candidate.text.splitlines()
    before = re.compile(
        r"^(?:made\s+in\s+[a-z]+|designed\s+in\s+[a-z]+|중국산|한국산|구성\s*:"
        r"|composition\s*(?:[:/].*)?|안전\s*관리법\s*에\s*(?:따른|의한)\s*품질\s*표시)$"
    )
    after = re.compile(r"^(?:exclusive\s+of\s+trim(?:\s*/.*)?"
                       r"|(?:심지|자수|상표|장식).*(?:제외)\s*/?"
                       r"|(?:machine\s+wash|wash\s+with|do\s+not\s+bleach|dry\s+clean).*)$")
    composition = [i for i, line in enumerate(lines)
                   if any(not _is_metadata_line(info) and (info.materials or "%" in line)
                          for info in build_line_infos(line))]
    if not composition:
        return None
    first, last = min(composition), max(composition)
    start = max((i + 1 for i in range(first) if before.fullmatch(normalize_text(lines[i]))), default=0)
    end = min((i for i in range(last + 1, len(lines)) if after.fullmatch(normalize_text(lines[i]))), default=len(lines))
    if start == 0 and end == len(lines):
        return None
    outside = lines[:start] + lines[end:]
    # Any known fiber, ratio, explicit part or unregistered-fiber marker
    # outside the block means the fence would hide separate material evidence.
    from apps.text.material_extraction import declared_part, unresolved_material_tokens
    if any(find_material_key(token) or token in forbidden for line in outside for token in _tokens(line)):
        return None
    if any("%" in line or declared_part(line) or unresolved_material_tokens(line) for line in outside):
        return None
    return replace(candidate, text="\n".join(lines[start:end]))


def _has_unclassified_context(candidate: OcrCandidate, *, bounded: bool = True) -> bool:
    """Do not discard opaque rows just because they lack a percent marker."""
    from apps.text.ocr_candidates import _is_plain_part_heading
    from apps.text.parse_label import (
        build_line_infos, _is_metadata_line, _mask_storage_caption,
        _looks_like_non_composition_number, COMPOSITION_HINTS, _CARE_PHRASES,
        _STORAGE_CAPTION_WORDS, _ORIGIN_ROW_PATTERN, declared_part,
    )

    if bounded and (view := _bounded_composition_context(candidate)) is not None:
        if not _has_unclassified_context(view, bounded=False):
            return False

    care_words = (_STORAGE_CAPTION_WORDS | {"instructions", "instruction", "machine", "cold", "warm",
                  "hot", "do", "not", "no", "low", "cool", "tumble", "line", "flat", "only",
                  "use", "please", "recommended"}
                  | {token for phrase in _CARE_PHRASES for token in _tokens(phrase) if token.isascii() and token.isalpha()})
    infos = build_line_infos(candidate.text)
    for info in infos:
        if (info.materials or info.numbers or info.explicit_percent or info.invalid_evidence
                or info.unresolved_materials or _is_metadata_line(info)
                or (info.is_standalone_marker and _is_plain_part_heading(info.normalized, info.part))):
            continue
        tokens = _annotation_tokens(info.raw)
        compact = info.normalized.replace(" ", "")
        care_tokens = _tokens(info.raw)
        complete_care = (compact in {phrase.replace(" ", "") for phrase in _CARE_PHRASES}
                         or bool(re.fullmatch(
                             r"(?:드라이클리닝(?:을)?권장합니다"
                             r"|찬물(?:을)?사용하여(?:단독)?손세탁(?:하)?십시오"
                             r"|중성세제(?:를)?사용(?:하)?십시오"
                             r"|건조기사용금지[,，]?자연건조(?:하)?십시오)[.。]*", compact))
                         or (bool(care_tokens) and all(token in care_words or token in {".", ",", ";", ":"}
                                                       for token in care_tokens)))
        metadata_caption = (
            bool(_ORIGIN_ROW_PATTERN.fullmatch(info.normalized))
            or bool(re.fullmatch(r"(?:[a-z]{1,3}\s+)?(?:www\.)?[a-z0-9][a-z0-9.-]*\.[a-z]{2,}(?:/[^\s]*)?", info.normalized))
            or bool(re.fullmatch(r"(?:repair|repar)(?:\s+[a-z]+)?|this\s+product|exclusive\s+of\s+trim"
                                 r"|a\s+part\s+la\s+garniture|[a-z]{1,3}\s+date\s+and\s+location"
                                 r"|(?:women|men)(?:'s)?|unisex", info.normalized))
            or (bool(re.fullmatch(r"f?abriqu[eé]\s+au\s+.+", info.normalized))
                and bool(_ORIGIN_ROW_PATTERN.fullmatch("made in " + info.normalized.split(" au ", 1)[1])))
        )
        # The parser splits a leading language code from an explicit fabric
        # heading. Recognize it only while it still prefixes a complete
        # composition in the original line; an isolated opaque row stays out.
        language_caption_count = info.normalized in {
            "en", "uk", "us", "fr", "de", "es", "es-mx", "cat", "pt", "it", "jp", "cn",
            "nl", "cz", "dk", "fi", "no", "pl", "sk", "se", "si", "hr", "lt", "lv", "ee",
            "kr", "ru", "tr", "el",
        } and sum(
            normalized.startswith(info.normalized + " ") and declared_part(remainder) is not None
            and any(row.materials and row.explicit_percent and not row.invalid_evidence
                    and not row.unresolved_materials for row in build_line_infos(remainder))
            and all(token.isdigit() or token in {"%", ":"} or find_material_key(token)
                    or declared_part(token) is not None for token in _tokens(remainder))
            for line in candidate.text.splitlines()
            if (normalized := normalize_text(line)).startswith(info.normalized + " ")
            if (remainder := normalized[len(info.normalized) + 1:])
        )
        language_caption = bool(language_caption_count) and language_caption_count == sum(
            row.normalized == info.normalized for row in infos
        )
        if (not tokens or info.normalized.strip(":[]() ") in COMPOSITION_HINTS
                or complete_care or metadata_caption or language_caption
                or _looks_like_non_composition_number(info.normalized)
                or not _mask_storage_caption(info.normalized).strip()
                or re.fullmatch(r"중성세제(?:를)?사용(?:하)?십시오[.。]*", compact)
                or re.fullmatch(r"제조사(?:명)?[:：].+", compact)
                or compact.startswith("(주)")):
            continue
        return True
    return False


def _literal_raw_context(candidate: OcrCandidate, candidates: list[OcrCandidate]) -> bool:
    """A shuffled layout may inherit only unchanged context from its raw input."""
    if not candidate.layout_used or not candidate.image_variant_key:
        return False
    tokens = Counter(_annotation_tokens(candidate.text))
    if not _covers_row_tokens(_annotation_tokens(candidate.text), list(candidate.image_words), tokenise=_annotation_tokens):
        return False
    return any(not peer.layout_used and peer.source == candidate.source
               and peer.image_key == candidate.image_key and peer.image_variant_key == candidate.image_variant_key
               and peer.image_region == candidate.image_region and peer.image_words == candidate.image_words
               and Counter(_annotation_tokens(peer.text)) == tokens and not _has_unclassified_context(peer)
               and _covers_row_tokens(_annotation_tokens(peer.text), list(peer.image_words), tokenise=_annotation_tokens)
               for peer in candidates)


def _same_response_metadata_recovery(candidate: OcrCandidate, alternative: OcrCandidate,
                                     part: str, target_part: str) -> bool:
    """Classify literal wash numbers only from complete same-response rows."""
    from apps.text.parse_label import build_line_infos, _is_metadata_line, _mentions_care

    if (candidate.layout_used or not alternative.layout_used
            or not candidate.image_variant_key or candidate.image_variant_key != alternative.image_variant_key
            or candidate.source != alternative.source or candidate.image_words != alternative.image_words
            or len(candidate.image_region) != 4 or candidate.image_region != alternative.image_region
            or _has_unclassified_context(alternative)):
        return False
    # Annotation segmentation may split a registered CJK name. Semantic
    # tokens remain whole for material/negation checks; every annotation
    # character, digit and sign still needs its own complete, disjoint proof.
    source_tokens = _annotation_tokens(candidate.text)
    if (Counter(source_tokens) != Counter(_annotation_tokens(alternative.text))
            or not _covers_row_tokens(source_tokens, list(candidate.image_words), tokenise=_annotation_tokens)
            or not _covers_row_tokens(_annotation_tokens(alternative.text), list(alternative.image_words),
                                      tokenise=_annotation_tokens)):
        return False
    left, top, right, bottom = alternative.image_region
    if any(not (left - 2 <= word.left and word.right <= right + 2
                and top - 2 <= word.top and word.bottom <= bottom + 2) for word in candidate.image_words):
        return False
    source_infos = build_line_infos(candidate.text)
    target_infos = build_line_infos(alternative.text)
    if any(info.marker_part == "outer_2" for info in source_infos) and "outer_2" not in alternative.parts:
        return False
    metadata_words = set()
    for index, info in enumerate(target_infos):
        if info.part != target_part or not _is_metadata_line(info):
            continue
        wash_outline = (re.search(r"(?<!\d)1(?:30|40|50|60|70|95)(?!\d)", info.normalized)
                        and re.search(r"[/\\]", info.normalized))
        care_nearby = any(_mentions_care(row.normalized) and not row.materials and not row.explicit_percent
                          for row in target_infos[index:index + 4] if row.part == target_part)
        if wash_outline or care_nearby:
            # The parser also treats general alphanumeric identifiers as
            # metadata. That alone cannot make an opaque FOO beside 30 safe.
            # AO is the preserved tub/triangle/circle glyph in this narrow
            # OCR pattern, rather than a wildcard for arbitrary label words.
            if re.search(r"\d", info.normalized) and not re.fullmatch(
                r"(?:30|40|50|60|70|95|1(?:30|40|50|60|70|95)[/\\])(?:\s+ao)?",
                info.normalized,
            ):
                continue
            words = _row_words(info.raw, alternative.image_words, tokenise=_annotation_tokens)
            if not words or not _physical_row(info.raw, words, tokenise=_annotation_tokens):
                return False
            metadata_words.update(words)
    if not metadata_words:
        return False
    retained = []
    context = []
    used = set()
    removed = False
    for info in source_infos:
        evidence = (info.part == part and not _is_metadata_line(info)
                    and (info.materials or info.numbers or info.explicit_percent
                         or info.invalid_evidence or info.unresolved_materials))
        words = _row_words(info.raw, candidate.image_words, tokenise=_annotation_tokens)
        in_wash_row = bool(words) and set(words) <= metadata_words
        compact = re.sub(r"[ \t]+", "", info.normalized)
        wash_number = (not info.materials and not info.explicit_percent and re.fullmatch(
            r"(?:30|40|50|60|70|95)|1(?:30|40|50|60|70|95)[/\\]", compact,
        ))
        if evidence:
            if not words or used.intersection(words) or info.unresolved_materials:
                return False
            used.update(words)
            if wash_number and in_wash_row:
                removed = True
                continue
            if info.invalid_evidence or (info.materials and info.numbers and info.explicit_percent
                                        and not _physical_row(info.raw, words, tokenise=_annotation_tokens)):
                return False
            retained.append(info)
        # A literal care glyph such as AO may be split away in raw text.
        # Exempt only complete boxes proved inside the physical wash row;
        # any opaque word elsewhere must pass the existing context guard.
        if not (in_wash_row and not info.materials and not info.explicit_percent
                and not info.invalid_evidence and not info.unresolved_materials
                and (not info.numbers or wash_number)):
            context.append(info.raw)
    if not removed or _has_unclassified_context(replace(candidate, text="\n".join(context))):
        return False
    targets = [info for info in target_infos if info.part == target_part and not _is_metadata_line(info)]
    target_used = set()
    for info in targets:
        if not (info.materials or info.numbers or info.explicit_percent
                or info.invalid_evidence or info.unresolved_materials):
            continue
        words = _row_words(info.raw, alternative.image_words, tokenise=_annotation_tokens)
        if (not words or target_used.intersection(words) or info.invalid_evidence or info.unresolved_materials
                or (info.materials and info.numbers and info.explicit_percent
                    and not _physical_row(info.raw, words, tokenise=_annotation_tokens))):
            return False
        target_used.update(words)
    paired = Counter(tuple(pair) for pair in candidate.paired_material_ratios.get(part, ()))
    return (paired <= Counter(alternative.parts[target_part].items())
            and Counter(material for info in retained for material in info.materials)
            == Counter(material for info in targets for material in info.materials)
            and Counter(number for info in retained for number in info.numbers)
            == Counter(number for info in targets for number in info.numbers))


def _same_response_source_recovery(candidate: OcrCandidate, alternative: OcrCandidate,
                                   part: str, candidates: list[OcrCandidate]) -> bool:
    """Reuse literal raw evidence when repeated metadata defeats layout search."""
    from apps.text.parse_label import build_line_infos, _is_metadata_line

    if (not candidate.layout_used or candidate.parser_status != "failed"
            or set(candidate.rejected_composition_parts.get(part, ())) != {"unpaired_material_rows"}
            or not candidate.image_variant_key or len(candidate.image_region) != 4
            or _has_unclassified_context(candidate)):
        return False
    source_infos = [info for info in build_line_infos(candidate.text)
                    if info.part == part and not _is_metadata_line(info)]
    if any(info.invalid_evidence or info.unresolved_materials
           or any(not float(value).is_integer() for value in info.numbers) for info in source_infos):
        return False
    source_tokens = Counter(_annotation_tokens(candidate.text))
    if not _covers_row_tokens(_annotation_tokens(candidate.text), list(candidate.image_words),
                              tokenise=_annotation_tokens):
        return False
    composition_tokens = Counter(token for info in source_infos for token in _annotation_tokens(info.raw))
    for peer in candidates:
        if (peer.layout_used or peer is candidate or peer.source != candidate.source
                or peer.image_key != candidate.image_key or peer.image_variant_key != candidate.image_variant_key
                or peer.image_region != candidate.image_region or peer.image_words != candidate.image_words
                or peer.parser_status != "failed"
                or set(peer.rejected_composition_parts.get(part, ())) != {"unpaired_material_rows"}
                or peer.observed_materials.keys() != candidate.observed_materials.keys()
                or peer.observed_ratios.keys() != candidate.observed_ratios.keys()
                or any(Counter(peer.observed_materials[key]) != Counter(candidate.observed_materials[key])
                       for key in candidate.observed_materials)
                or any(Counter(peer.observed_ratios[key]) != Counter(candidate.observed_ratios[key])
                       for key in candidate.observed_ratios)):
            continue
        peer_infos = [info for info in build_line_infos(peer.text)
                      if info.part == part and not _is_metadata_line(info)]
        if (Counter(_annotation_tokens(peer.text)) != source_tokens
                or _has_unclassified_context(peer)
                or Counter(token for info in peer_infos for token in _annotation_tokens(info.raw)) != composition_tokens
                or any(info.invalid_evidence or info.unresolved_materials
                       or any(not float(value).is_integer() for value in info.numbers) for info in peer_infos)
                or not _covers_row_tokens(_annotation_tokens(peer.text), list(peer.image_words),
                                         tokenise=_annotation_tokens)):
            continue
        # This is the same OCR input, not an extra independent supporter.
        # The existing raw proof must still check every source composition
        # word and numeric component against the physical reread.
        if same_region_recovery(peer, alternative, part, candidates):
            return True
    return False


def _joined_separator_recovery(candidate: OcrCandidate, alternative: OcrCandidate,
                               part: str, target_part: str, candidates: list[OcrCandidate]) -> bool:
    """Release one ambiguous alias-dot-digit only after two complete rereads."""
    from apps.text.ocr_candidates import _has_explicit_complete_pairs
    from apps.text.parse_label import build_line_infos, _is_metadata_line, _ORIGIN_ROW_PATTERN

    if candidate.parser_status != "failed":
        return False

    def composition_infos(item, selected_part):
        return [info for info in build_line_infos(item.text)
                if info.part == selected_part and not _is_metadata_line(info)
                and (info.materials or info.numbers or info.explicit_percent
                     or info.invalid_evidence or info.unresolved_materials)]

    def complete_annotations(item):
        return _covers_row_tokens(_annotation_tokens(item.text), list(item.image_words),
                                  tokenise=_annotation_tokens)

    def metadata_context(context):
        return all(_is_metadata_line(info) or _ORIGIN_ROW_PATTERN.fullmatch(info.normalized) or re.search(
            r"\(주\)|^고객센터|^howtowash", re.sub(r"\s", "", info.normalized)
        ) for info in context)

    infos = composition_infos(candidate, part)
    if not infos:
        return False
    expected = {}
    changed_info = None
    for info in infos:
        if (len(info.materials) != 1 or len(info.numbers) != 1 or not info.explicit_percent
                or info.invalid_evidence or info.unresolved_materials):
            return False
        key = info.materials[0]
        if key in expected:
            return False
        attached = re.fullmatch(r"([^\W\d_]+)\.([1-9])\s*%", info.raw.strip())
        if attached and find_material_key(attached.group(1)) == key:
            if changed_info is not None:
                return False
            changed_info = info
            expected[key] = int(attached.group(2))
        else:
            value = float(info.numbers[0])
            if not value.is_integer() or not 0 < value <= 100:
                return False
            expected[key] = int(value)
    if changed_info is None or sum(expected.values()) != 100:
        return False
    if not complete_annotations(candidate):
        return False
    source_rows = _locate_rows(infos, candidate.image_words, physical=True)
    if not source_rows:
        return False
    forbidden = NEGATING_MODIFIERS | UNPRICED_MATERIALS | {"unknown", "未知繊維", "未知纤维"}
    if any(token in forbidden for token in _tokens(candidate.text)):
        return False
    source_core = {word for _info, words in source_rows for word in words}
    context_words = [word for word in candidate.image_words if word not in source_core]
    context_proved = False
    for peer in [candidate, *candidates]:
        if (peer.image_key != candidate.image_key or peer.source != candidate.source
                or peer.image_variant_key != candidate.image_variant_key
                or peer.image_words != candidate.image_words or not complete_annotations(peer)):
            continue
        peer_infos = composition_infos(peer, part)
        if Counter(_tokens(info.raw) for info in peer_infos) != Counter(_tokens(info.raw) for info in infos):
            continue
        context = [info for info in build_line_infos(peer.text) if info not in peer_infos]
        if not metadata_context(context):
            continue
        if _covers_row_tokens(_annotation_tokens("\n".join(info.raw for info in context)), context_words,
                              tokenise=_annotation_tokens):
            context_proved = True
            break
    if not context_proved:
        return False
    cleaned_rows = []
    changed_words = 0
    for info, words in source_rows:
        cleaned = []
        for word in words:
            attached = re.fullmatch(r"([^\W\d_]+)\.([1-9])%?", normalize_text(word.text).strip())
            if info is changed_info and attached and find_material_key(attached.group(1)) == info.materials[0]:
                if int(attached.group(2)) != expected[info.materials[0]]:
                    return False
                word = replace(word, text=normalize_text(word.text).replace(".", "", 1))
                changed_words += 1
            cleaned.append(word)
        cleaned_rows.append((info, tuple(cleaned)))
    if changed_words != 1:
        return False

    def proves(item):
        if (item.image_key != candidate.image_key or not item.image_variant_key
                or len(item.image_region) != 4 or item.parts.get(target_part) != expected
                or not _has_explicit_complete_pairs(item) or not complete_annotations(item)
                or len({word.page for word in candidate.image_words + item.image_words}) != 1):
            return False
        target_infos = composition_infos(item, target_part)
        if not metadata_context([info for info in build_line_infos(item.text) if info not in target_infos]):
            return False
        if (len(target_infos) != len(infos) or any(
            len(info.materials) != 1 or len(info.numbers) != 1 or not info.explicit_percent
            or info.invalid_evidence or info.unresolved_materials
            or expected.get(info.materials[0]) != float(info.numbers[0]) for info in target_infos
        ) or len({info.materials[0] for info in target_infos}) != len(infos)):
            return False
        target_rows = _locate_rows(target_infos, item.image_words, physical=True, allow_quantisation=True)
        if not target_rows:
            return False
        by_material = {info.materials[0]: words for info, words in target_rows}
        left, top, right, bottom = item.image_region
        for info, words in cleaned_rows:
            targets = by_material[info.materials[0]]
            for word in words:
                if not (left - 2 <= word.left and word.right <= right + 2
                        and top - 2 <= word.top and word.bottom <= bottom + 2):
                    return False
                nearby = [target for target in targets if _overlaps(word, target)]
                if _matching_token_parts(word, nearby, allow_change=False) != 0:
                    return False
        return _numeric_components_align(tuple(word for _info, words in cleaned_rows for word in words),
                                         tuple(word for _info, words in target_rows for word in words),
                                         (), corroborated=False)

    if not proves(alternative):
        return False
    supporters = [item for item in candidates if proves(item)]
    # A raw/layout pair belongs to one response and supplies one confirmation.
    return (len({item.image_variant_key for item in supporters}) >= 2
            and len({item.source for item in supporters}) >= 2)


def _percent_glyph_recovery(
    candidate: OcrCandidate, alternative: OcrCandidate, part: str,
    target_part: str, candidates: list[OcrCandidate],
) -> bool:
    """Prove an out-of-range integer's trailing 96 as a reread percent glyph.

    This is a word-level proof, not invented character coordinates. Two actual
    rereads must separately observe the unchanged integer prefix and percent
    inside the source word, in the same complete physical material row.
    """
    from apps.text.ocr_candidates import _has_explicit_complete_pairs
    from apps.text.parse_label import build_line_infos, _is_metadata_line

    forbidden = NEGATING_MODIFIERS | UNPRICED_MATERIALS | {"unknown", "olefin", "未知繊維", "未知纤维"}

    def complete(item):
        return (bool(item.image_words) and len(set(item.image_words)) == len(item.image_words)
                and not _has_unclassified_context(item)
                and not any(token in forbidden for token in _tokens(item.text))
                and _covers_row_tokens(_tokens(item.text), list(item.image_words)))

    def composition_rows(item, selected_part):
        infos = [info for info in build_line_infos(item.text) if not _is_metadata_line(info)
                 and (info.materials or info.numbers or info.explicit_percent
                      or info.invalid_evidence or info.unresolved_materials)]
        if not 1 <= len(infos) <= 8 or any(info.part != selected_part for info in infos):
            return []
        rows = _locate_rows(infos, item.image_words, physical=True, allow_quantisation=True)
        if len(rows) != len(infos) or any(
            not all(len(word.vertices) == 4 for word in words)
            or not _physical_row(info.raw, words, allow_quantisation=True) for info, words in rows
        ):
            return []
        return rows

    def components(info, words, *, source=False):
        if (len(info.materials) != 1 or len(info.numbers) > 1 or info.unresolved_materials
                or (not source and len(info.numbers) != 1)):
            return None
        names = [word for word in words if len(_tokens(word.text)) == 1
                 and _tokens(word.text)[0].isalpha()
                 and find_material_key(word.text) == info.materials[0]]
        numbers = [word for word in words if re.fullmatch(r"[1-9]\d{0,4}", normalize_text(word.text).strip())]
        percents = [word for word in words if normalize_text(word.text).strip() == "%"]
        if len(names) != 1 or len(numbers) != 1 or len(percents) > 1:
            return None
        if set(words) != set(names + numbers + percents):
            return None
        # The parser deliberately excludes out-of-range values from numbers.
        # Only the complete observed source integer can supply that evidence.
        if not info.numbers and not (source and info.invalid_evidence
                                     and int(normalize_text(numbers[0].text).strip()) > 100):
            return None
        return names[0], numbers[0], tuple(percents)

    if (not candidate.image_key or not candidate.image_variant_key
            or not candidate.image_variant_key.strip() or not candidate.source or not candidate.source.strip()
            or len(candidate.image_region) != 4 or not complete(candidate)):
        return False
    source_rows = composition_rows(candidate, part)
    expected = {}
    sources = {}
    changed = False
    for info, words in source_rows:
        parsed = components(info, words, source=True)
        if parsed is None or info.materials[0] in expected:
            return False
        name, number, percents = parsed
        value = normalize_text(number.text).strip()
        if int(value) > 100:
            suffix = re.fullmatch(r"([1-9]\d{0,2})96", value)
            if not suffix or int(suffix.group(1)) > 100 or percents or info.explicit_percent:
                return False
            prefix = suffix.group(1)
            changed = True
        else:
            if not percents or not info.explicit_percent or info.invalid_evidence:
                return False
            prefix = value
        expected[info.materials[0]] = int(prefix)
        sources[info.materials[0]] = (name, number, percents, prefix, words)
    if not changed or sum(expected.values()) != 100:
        return False

    def inside(word, bounds):
        left, top, right, bottom = bounds
        return (left - 2 <= word.left and word.right <= right + 2
                and top - 2 <= word.top and word.bottom <= bottom + 2)

    def proves(item):
        if (item.image_key != candidate.image_key or not item.image_variant_key
                or not item.image_variant_key.strip() or not item.source or not item.source.strip()
                or item.image_variant_key == candidate.image_variant_key or item.source == candidate.source
                or item.parser_status != "success" or item.parts.get(target_part) != expected
                or len(item.parts) != 1 or len(item.image_region) != 4
                or len({word.page for word in candidate.image_words + item.image_words}) != 1
                or not _has_explicit_complete_pairs(item) or not complete(item)):
            return ()
        target_rows = composition_rows(item, target_part)
        if len(target_rows) != len(source_rows):
            return ()
        used_materials = set()
        core = []
        for info, words in target_rows:
            parsed = components(info, words)
            if parsed is None or not info.explicit_percent or info.invalid_evidence:
                return ()
            name, number, percents = parsed
            key = info.materials[0]
            if key not in sources or key in used_materials or len(percents) != 1:
                return ()
            old_name, old_number, old_percents, prefix, old_words = sources[key]
            if (normalize_text(number.text).strip() != prefix or float(info.numbers[0]) != expected[key]
                    or _tokens(name.text) != _tokens(old_name.text) or not _overlaps(old_name, name)
                    or any(not inside(word, item.image_region) for word in old_words)):
                return ()
            if old_percents:
                if not (_overlaps(old_number, number) and _overlaps(old_percents[0], percents[0])):
                    return ()
            else:
                # Word bounds can differ between OCR inputs. Containment and
                # the leading edge tie the complete target bundle to this
                # source word; they do not claim 100% source-polygon coverage.
                bounds = (old_number.left, old_number.top, old_number.right, old_number.bottom)
                if (not all(inside(word, bounds) and _overlaps(old_number, word)
                            for word in (number, percents[0]))
                        or abs(number.left - old_number.left) > max(2, old_number.height / 4)
                        or max(number.right, percents[0].right) - min(number.left, percents[0].left)
                        < (old_number.right - old_number.left) / 2
                        or max(number.bottom, percents[0].bottom) - min(number.top, percents[0].top)
                        < old_number.height / 2):
                    return ()
            # Both rows must also have a common reading direction. Checking
            # each row alone would accept an unrelated rotated reread.
            if not _physical_row(info.raw, (old_name, number, percents[0]), allow_quantisation=True):
                return ()
            used_materials.add(key)
            core.extend(words)
        return tuple(core)

    target_words = proves(alternative)
    if not target_words:
        return False
    supporters = []
    for item in candidates:
        other_words = proves(item)
        if (other_words and _aligned_reading(target_words, other_words)
                and _aligned_reading(other_words, target_words)):
            supporters.append(item)
    # Raw and layout views of one OCR input cannot supply two confirmations.
    return (len({item.image_variant_key for item in supporters}) >= 2
            and len({item.source for item in supporters}) >= 2)


def _same_response_bounded_recovery(candidate, alternative, part, candidates):
    """A failed layout may inherit a proved correction of its identical raw block."""
    if (not candidate.layout_used or candidate.parser_status != "failed" or candidate.parts
            or candidate.conflicting_parts or part != "generic"):
        return False
    view = _bounded_composition_context(candidate)
    for raw in candidates:
        if (raw.layout_used or raw.source != candidate.source or raw.image_key != candidate.image_key
                or raw.image_variant_key != candidate.image_variant_key
                or raw.image_words != candidate.image_words or raw.image_region != candidate.image_region
                or raw.observed_materials != candidate.observed_materials
                or raw.observed_ratios != candidate.observed_ratios
                or raw.rejected_composition_parts != candidate.rejected_composition_parts):
            continue
        if (Counter(_annotation_tokens(candidate.text)) == Counter(_annotation_tokens(raw.text))
                and _covers_row_tokens(_annotation_tokens(candidate.text), list(candidate.image_words),
                                       tokenise=_annotation_tokens)
                and _repeated_translation_recovery(raw, alternative, part, part, candidates)):
            return True
        if view is None:
            continue
        raw_view = _bounded_composition_context(raw)
        if (raw_view is not None
                and Counter(_annotation_tokens(view.text)) == Counter(_annotation_tokens(raw_view.text))
                and same_region_recovery(raw, alternative, part, candidates)):
            return True
    return False


def _shared_percent_recovery(candidate, alternative, part, target_part):
    """Match unchanged physical material/number rows using one printed percent.

    The percent is shared by the literal declaration, not copied into invented
    boxes. No missing digit or value is supplied from a total of 100.
    """
    if (candidate.layout_used or alternative.layout_used or part != "generic" or target_part != "generic"
            or candidate.image_variant_key == alternative.image_variant_key
            or candidate.source == alternative.source
            or _has_unclassified_context(candidate) or _has_unclassified_context(alternative)):
        return False
    expected = alternative.parts.get(target_part, {})
    if (not 1 <= len(expected) <= 2 or len(alternative.parts) != 1
            or Counter(candidate.observed_materials.get(part, ())) != Counter(expected.keys())
            or Counter(candidate.observed_ratios.get(part, ())) != Counter(expected.values())):
        return False

    def rows(item):
        if (not item.image_variant_key or len(item.image_region) != 4 or not item.image_words
                or len(set(item.image_words)) != len(item.image_words)
                or not _covers_row_tokens(_tokens(item.text), list(item.image_words))):
            return None
        left, top, right, bottom = item.image_region
        if any(not (left - 2 <= word.left and word.right <= right + 2
                    and top - 2 <= word.top and word.bottom <= bottom + 2) for word in item.image_words):
            return None
        percent = [word for word in item.image_words if normalize_text(word.text) == "%"]
        if len(percent) != 1 or not any(line.strip() == "%" for line in item.text.splitlines()):
            return None
        found = {}
        for line in item.text.splitlines():
            match = re.fullmatch(r"\s*([^\W\d_]+)\s+([1-9]\d?(?:[.,]\d+)?)\s*", normalize_text(line))
            if not match:
                continue
            key = find_material_key(match.group(1))
            if key not in expected or key in found or float(match.group(2).replace(",", ".")) != expected[key]:
                return None
            words = _row_words(line, item.image_words)
            if not words or not _physical_row(line, words, allow_quantisation=True):
                return None
            found[key] = words
        if set(found) != set(expected):
            return None
        core = tuple(word for words in found.values() for word in words) + tuple(percent)
        if len(set(core)) != len(core) or any(len(word.vertices) != 4 for word in core):
            return None
        material_words = core[:-1]
        height = max(word.height for word in material_words)
        if (not min(word.left for word in material_words) <= percent[0].center_x <= max(word.right for word in material_words)
                or not max(word.bottom for word in material_words) - height <= percent[0].top
                <= max(word.bottom for word in material_words) + 3 * height):
            return None
        # An isolated zero-only artifact outside the material column is not a
        # positive mixing ratio. Every other numeric annotation must be core.
        left, right = min(word.left for word in core), max(word.right for word in core)
        bottom = max(word.bottom for word in core)
        margin = 2 * max(word.height for word in core)
        for word in item.image_words:
            if word in core or not re.search(r"\d|%", word.text):
                continue
            if (not re.fullmatch(r"0{2,}", word.text) or word.top <= bottom
                    or not (word.right < left - margin or word.left > right + margin)):
                return None
        return core

    source, target = rows(candidate), rows(alternative)
    return bool(source and target and _aligned_reading(source, target) and _aligned_reading(target, source)
                and _numeric_components_align(source, target, (), corroborated=False)
                and _numeric_components_align(target, source, (), corroborated=False))


def _repeated_translation_recovery(candidate, alternative, part, target_part, candidates):
    """Corroborate a literal primary declaration through damaged repeat copies.

    Only one 100% fiber is supported here. Every foreign-copy box must be
    inside the reread and overlap its translation block. Unknown fibers,
    additional ratios and unreadable primary declarations remain rejected.
    """
    from apps.text.material_extraction import ALIAS_TO_MATERIAL, declared_part, unresolved_material_tokens

    if (candidate.layout_used or alternative.layout_used or part != "generic" or target_part != "generic"
            or candidate.image_variant_key == alternative.image_variant_key or candidate.source == alternative.source
            or len(alternative.parts) != 1 or len(alternative.materials) != 1
            or list(alternative.materials.values()) != [100]
            or not {"registered_translation_alternatives", "damaged_translation_fragment"}
            .issuperset(alternative.parser_warnings)
            or "registered_translation_alternatives" not in alternative.parser_warnings):
        return False
    key = next(iter(alternative.materials))
    if (set(candidate.observed_materials) != {part} or set(candidate.observed_ratios) != {part}
            or set(candidate.observed_materials[part]) != {key}
            or candidate.observed_ratios[part] != [100.0]):
        return False
    forbidden = NEGATING_MODIFIERS | UNPRICED_MATERIALS | {"unknown", "olefin", "未知繊維", "未知纤维"}

    def block(item):
        text = normalize_text(item.text)
        if (not item.image_variant_key or len(item.image_region) != 4
                or not _covers_row_tokens(_annotation_tokens(item.text), list(item.image_words), tokenise=_annotation_tokens)
                or any(token in forbidden for token in _tokens(text))
                or declared_part(text) or not re.search(r"(?m)^composition\s*/", text)):
            return None
        left, top, right, bottom = item.image_region
        if (len(set(item.image_words)) != len(item.image_words)
                or any(len(word.vertices) != 4 or not (left - 3 <= word.left and word.right <= right + 3
                       and top - 3 <= word.top and word.bottom <= bottom + 3) for word in item.image_words)
                or text.count("%") != 1):
            return None
        match = re.search(r"(?m)^100\s*%\s*([^/\n]+)\s*/", text)
        if not match or find_material_key(match.group(1).strip()) != key:
            return None
        lines = text[match.start():].splitlines()
        body = [lines[0]]
        footer = []
        for line in lines[1:]:
            if re.search(r"\d|%|wash|bleach|dry", line):
                break
            if "/" not in line and body[-1].rstrip().endswith("/"):
                footer.append(line)
                break
            body.append(line)
        joined = "".join(body)
        if unresolved_material_tokens(joined):
            return None
        names, noise = set(), 0
        aliases = sorted((alias for alias, material in ALIAS_TO_MATERIAL.items() if material == key), key=len, reverse=True)
        for clause in re.sub(r"^100\s*%\s*", "", joined).split("/"):
            compact = re.sub(r"\s", "", clause)
            if not compact:
                continue
            alias = next((alias for alias in aliases if compact.startswith(alias)), None)
            remainder = compact[len(alias):] if alias else compact
            if any(other in remainder for other, material in ALIAS_TO_MATERIAL.items()
                   if material != key and len(other) >= 3):
                return None
            if alias is None:
                if not (compact.isascii() and compact.isalpha() and len(compact) <= 3):
                    return None
                noise += len(compact)
            else:
                names.add(alias)
                suffix = compact[len(alias):]
                if suffix and (not suffix.isascii() or not suffix.isalpha() or len(suffix) > 6):
                    return None
                noise += len(suffix)
        if len(names) < 3 or noise > 6:
            return None
        primary = _row_words(match.group(0).rstrip("/ "), item.image_words, tokenise=_annotation_tokens)
        if not primary or not _physical_row(match.group(0).rstrip("/ "), primary,
                                                         allow_quantisation=True, tokenise=_annotation_tokens):
            return None
        # Repeated short fragments in the title cannot locate a copy within
        # the material list. Restrict their boxes to the printed list below
        # the independently located primary row, then require full coverage.
        height = max(word.height for word in primary)
        pool = tuple(word for word in item.image_words if word.bottom >= min(w.top for w in primary)
                     and word.top <= max(w.bottom for w in primary) + 2 * height * len(body))
        words = _row_words("\n".join(body), pool, tokenise=_annotation_tokens)
        if not words:
            return None
        if footer:
            extra = _row_words(footer[0], item.image_words)
            if (not extra or any(not _tokens(word.text) or not all(token.isalpha() for token in _tokens(word.text))
                                 for word in extra) or sum(len(word.text) for word in extra) > 6
                    or min(word.top for word in extra) - max(word.bottom for word in words)
                    < max(word.height for word in words)):
                return None
            # A cropped wash-temperature icon may be read as short letters.
            # Require an actual full-image peer locating its wash caption and
            # temperature at the same footer, never a guessed missing fiber.
            if not any(peer.image_key == item.image_key and peer.source == "original"
                       and re.search(r"wash\s+with", normalize_text(peer.text))
                       and any(word.text == "30" and all(
                           abs(other.center_y - word.center_y) <= max(word.height, other.height)
                           and abs(other.center_x - word.center_x) <= 3 * max(word.height, other.height)
                           for other in extra) for word in peer.image_words) for peer in candidates):
                return None
        return primary, words

    source, target = block(candidate), block(alternative)
    if not source or not target:
        return False
    primary, words = source
    target_primary, target_words = target
    left, top, right, bottom = alternative.image_region
    return (_aligned_reading(primary, target_primary) and _aligned_reading(target_primary, primary)
            and _numeric_components_align(primary, target_primary, (), corroborated=False)
            and all(left - 2 <= word.left and word.right <= right + 2 and top - 2 <= word.top
                    and word.bottom <= bottom + 2 and any(_overlaps(word, other) for other in target_words)
                    for word in words))


def _mixed_translation_recovery(candidate, alternative, part, target_part, candidates):
    """Match literal mixed-fiber declarations through damaged translation copies.

    Every primary row and ratio stays unchanged. A detached wash number needs
    a full-image written care caption at the same coordinates. This proof does
    not classify care symbols or supply a missing material or percentage.
    """
    from apps.text.material_extraction import ALIAS_TO_MATERIAL, declared_part, unresolved_material_tokens
    from apps.text.parse_label import _prepare_multilingual_rows

    expected = alternative.parts.get(target_part, {})
    if (part != "generic" or target_part != "generic" or len(expected) != 2
            or len(alternative.parts) != 1 or sum(expected.values()) != 100
            or "registered_translation_alternatives" not in alternative.parser_warnings
            or set(alternative.parser_warnings) - {"registered_translation_alternatives", "damaged_translation_fragment"}):
        return False
    if candidate.layout_used:
        return any(not raw.layout_used and raw.source == candidate.source
                   and raw.image_key == candidate.image_key and raw.image_variant_key == candidate.image_variant_key
                   and raw.image_words == candidate.image_words and raw.image_region == candidate.image_region
                   and Counter(_annotation_tokens(raw.text)) == Counter(_annotation_tokens(candidate.text))
                   and _mixed_translation_recovery(raw, alternative, part, target_part, candidates)
                   for raw in candidates)
    if alternative.layout_used:
        return False
    if (candidate is not alternative and (candidate.image_variant_key == alternative.image_variant_key
                                         or candidate.source == alternative.source)):
        return False
    forbidden = NEGATING_MODIFIERS | UNPRICED_MATERIALS | {"unknown", "olefin", "未知繊維", "未知纤维"}

    def blocks(item):
        text = normalize_text(item.text)
        if (not item.image_variant_key or len(item.image_region) != 4 or declared_part(text)
                or not re.search(r"(?m)^composition\s*/", text)
                or any(token in forbidden for token in _tokens(text))
                or unresolved_material_tokens(_prepare_multilingual_rows(text))
                or not _covers_row_tokens(_annotation_tokens(item.text), list(item.image_words), tokenise=_annotation_tokens)
                or len(set(item.image_words)) != len(item.image_words)):
            return None
        left, top, right, bottom = item.image_region
        if any(len(word.vertices) != 4 or not (left - 6 <= word.left and word.right <= right + 6
               and top - 6 <= word.top and word.bottom <= bottom + 6) for word in item.image_words):
            return None
        matches = list(re.finditer(r"(?m)^([1-9]\d?(?:\.\d+)?)\s*%\s*([^/\n]+)\s*/", text))
        if len(matches) != len(expected) or text.count("%") != len(matches):
            return None
        found, primary_words, copy_words = {}, {}, {}
        for position, match in enumerate(matches):
            key = find_material_key(match.group(2).strip())
            if key not in expected or key in found or float(match.group(1)) != expected[key]:
                return None
            primary_text = match.group().rstrip("/ ")
            primary = _row_words(primary_text, item.image_words, tokenise=_annotation_tokens)
            if not primary or not _physical_row(primary_text, primary, allow_quantisation=True,
                                                tokenise=_annotation_tokens):
                return None
            end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
            body = text[match.end():end]
            stop = re.search(r"(?m)^.*(?:[0-9%]|wash|bleach|dry).*$", body)
            # A short, wide OCR artifact can enclose a separately read wash
            # number. Locate both boxes before treating that row as footer.
            artifact_stop = None
            for artifact in re.finditer(r"(?m)^[a-z]{1,3}$", body):
                boxes = _row_words(artifact.group(), item.image_words)
                if boxes and any(word.text in {"30", "40", "50", "60", "70", "95"}
                                 and any(box.left <= word.left and word.right <= box.right
                                         and box.top <= word.top and word.bottom <= box.bottom
                                         and box.right - box.left >= 3 * box.height for box in boxes)
                                 for word in item.image_words):
                    artifact_stop = artifact.start()
                    break
            body_end = min([len(body), *([stop.start()] if stop else []),
                            *([artifact_stop] if artifact_stop is not None else [])])
            body = body[:body_end]
            body = re.sub(r"(?m)^\s*구성\s*:\s*$", "", body)
            body = _prepare_multilingual_rows(body)
            # A wrap can end a Latin name immediately before a complete
            # Japanese/Korean copy without preserving its slash. Keep script
            # boundaries rather than joining two different alphabet runs.
            body = re.sub(r"(?<=[a-z])\s*(?=[\u3040-\u30ff\uac00-\ud7a3])", "/", body)
            aliases = sorted((a for a, material in ALIAS_TO_MATERIAL.items() if material == key), key=len, reverse=True)
            names, noise = {normalize_text(match.group(2).strip())}, 0
            for clause in body.replace("\n", "").split("/"):
                compact = re.sub(r"\s", "", clause)
                if not compact:
                    continue
                if compact in {"pu", "pa", "pe", "pp", "pes", "pla", "mix", "unk", "ny", "wo", "ela"}:
                    return None
                if re.search(r"[0-9%+−±<>≤≥~≈]", compact) or set(
                        find_material_key(token) for token in _tokens(compact)) - {None, key}:
                    return None
                alias = next((a for a in aliases if compact.startswith(a)), None)
                if alias:
                    names.add(alias)
                    tail = compact[len(alias):]
                else:
                    prefix = max((length for a in aliases for length in range(4, len(a) + 1)
                                  if compact.startswith(a[:length])), default=0)
                    tail = compact[prefix:] if prefix else compact
                    if not prefix and len(tail) > 3:
                        return None
                if tail and (not tail.isascii() or not tail.isalpha() or len(tail) > 3):
                    return None
                noise += len(tail)
            if len(names) < 3 or noise > 6:
                return None
            # Locate the original, unjoined body; the semantic check above may
            # join known wrap fragments, but never changes annotation text.
            original_body = text[match.start():match.end() + body_end]
            original_body = re.sub(r"(?m)^\s*구성\s*:\s*$", "", original_body)
            height = max(word.height for word in primary)
            limit = max(w.bottom for w in primary) + 2 * height * len(original_body.splitlines())
            if position + 1 < len(matches):
                next_primary = _row_words(matches[position + 1].group().rstrip("/ "), item.image_words,
                                          tokenise=_annotation_tokens)
                if not next_primary:
                    return None
                limit = min(word.top for word in next_primary)
            pool = tuple(word for word in item.image_words if word.bottom >= min(w.top for w in primary)
                         and word.center_y < limit)
            words = _row_words(original_body, pool, tokenise=_annotation_tokens)
            if not words:
                return None
            found[key], primary_words[key], copy_words[key] = expected[key], primary, words
        core = set(word for words in copy_words.values() for word in words)
        bottom = max(word.bottom for word in core)
        height = max(word.height for word in core)
        first_top = min(word.top for word in core)
        origin_bottom = -1
        for line in text.splitlines():
            if re.fullmatch(r"중국산|한국산|made\s+in\s+[a-z]+", line):
                origin = _row_words(line, item.image_words, tokenise=_annotation_tokens)
                if origin and max(word.bottom for word in origin) < first_top:
                    origin_bottom = max(origin_bottom, max(word.bottom for word in origin))
        heading_tokens = set(_annotation_tokens("composition zusamme nsetzung composición composição 구성 : /"))
        extras = [word for word in item.image_words if word not in core and re.search(r"[0-9%]", word.text)]
        for word in extras:
            if (word.text not in {"30", "40", "50", "60", "70", "95"} or word.top <= bottom
                    or word.top - bottom > 3 * height):
                return None
            if not any(peer.source == "original" and not peer.layout_used and peer.image_key == item.image_key
                       and re.search(r"wash\s+with|machine\s+wash|hand\s+wash", normalize_text(peer.text))
                       and any(other.text == word.text and _overlaps(word, other) for other in peer.image_words)
                       and any(normalize_text(caption.text) in {"wash", "washing"}
                               and word.bottom - 2 <= caption.top <= word.bottom + 6 * height
                               for caption in peer.image_words)
                       for peer in candidates):
                return None
        # Any material-looking words outside the list are still contradictory
        # evidence. Short cropped header/footer fragments need their own box.
        for word in item.image_words:
            if word in core:
                continue
            if find_material_key(word.text):
                return None
            if word.bottom < first_top and word.top >= origin_bottom:
                if set(_annotation_tokens(word.text)) - heading_tokens:
                    return None
            if word.top > bottom and not re.search(r"[0-9%]", word.text):
                captions = [w for w in item.image_words if normalize_text(w.text) in {"wash", "washing"}]
                if captions and word.center_y >= min(w.top for w in captions):
                    continue
                wide_artifact = (len(word.text) <= 3 and word.right - word.left >= 3 * word.height
                                 and any(word.left <= number.left and number.right <= word.right
                                         and word.top <= number.top and number.bottom <= word.bottom for number in extras))
                if (word.top - bottom > 3 * height or (len(word.text) > 1 and not wide_artifact)
                        or not extras or not any(abs(word.center_y - number.center_y) <= 2 * height for number in extras)):
                    return None
        return primary_words, copy_words

    source, target = blocks(candidate), blocks(alternative)
    if not source or not target:
        return False
    def covered_copy(word, words):
        # A provider may omit one foreign copy while reading its other copies.
        # The source clause must already pass the bounded translation check;
        # its box must stay inside this fiber's entire repeated block, not the
        # other fiber or a new row outside the reread.
        margin = 2
        return (any(_overlaps(word, other) for other in words)
                or (min(w.left for w in words) - margin <= word.left
                    and word.right <= max(w.right for w in words) + margin
                    and min(w.top for w in words) - margin <= word.top
                    and word.bottom <= max(w.bottom for w in words) + margin))
    return all(_aligned_reading(source[0][key], target[0][key])
               and _aligned_reading(target[0][key], source[0][key])
               and _numeric_components_align(source[0][key], target[0][key], (), corroborated=False)
               and all(covered_copy(word, target[1][key]) for word in source[1][key])
               for key in expected)


def _same_response_hyphen_recovery(candidate, alternative, part, target_part):
    """A reordered layout cannot contradict its fully located literal list.

    The raw response validates every registered repeat, both explicit 100%
    declarations and its printed exclusion boundary. Raw/layout are one OCR
    input; only their row order differs and every annotation must be retained.
    """
    from apps.text.parse_label import _prepare_multilingual_rows, _split_part_markers
    from apps.text.translation_alternatives import _prepare_repeated_hyphen_declaration

    if (not candidate.layout_used or alternative.layout_used or part != "generic" or target_part != "generic"
            or alternative.parser_status != "success"
            or not alternative.image_key or candidate.image_key != alternative.image_key
            or len(alternative.image_region) != 4 or not alternative.image_words
            or len({w.page for w in candidate.image_words + alternative.image_words}) != 1
            or not alternative.image_variant_key or candidate.image_variant_key != alternative.image_variant_key
            or candidate.source != alternative.source or candidate.image_words != alternative.image_words
            or candidate.image_region != alternative.image_region
            or alternative.parts != {"generic": alternative.materials}
            or len(alternative.materials) != 1 or list(alternative.materials.values()) != [100]
            or "registered_translation_alternatives" not in alternative.parser_warnings
            or set(alternative.parser_warnings) - {"registered_translation_alternatives", "damaged_translation_fragment"}):
        return False
    words = alternative.image_words
    left, top, right, bottom = alternative.image_region
    if (len(set(words)) != len(words) or any(len(w.vertices) != 4 or not (
            left - 2 <= w.left and w.right <= right + 2 and top - 2 <= w.top and w.bottom <= bottom + 2
            ) for w in words)
            or not _covers_row_tokens(_tokens(alternative.text), list(words))
            or not _covers_row_tokens(_tokens(candidate.text), list(words))):
        return False
    prepared = _split_part_markers(_prepare_multilingual_rows(_split_part_markers(normalize_text(alternative.text))))
    validated = _prepare_repeated_hyphen_declaration(prepared)
    if len(validated.recovered_rows) != 1:
        return False
    # Locate the literal primary row, including its first translation and
    # separators. A repeated percent elsewhere cannot supply this row.
    rows = normalize_text(alternative.text).splitlines()
    primary_rows = [row for row in rows if re.match(r"^100\s*%\s*[^\W\d_]+\s*-", row)]
    if len(primary_rows) != 1:
        return False

    def literal_options(row):
        # Repeated hyphens in other rows otherwise exhaust the bounded
        # partition search. A unique literal word locates this physical row
        # before searching; numbers alone never act as the location anchor.
        tokens = _tokens(row)
        unique = [w for w in words if len(_tokens(w.text)) == 1
                  and _tokens(w.text)[0].isalpha() and len(w.text) > 1
                  and _tokens(w.text)[0] in tokens
                  and sum(_tokens(other.text) == _tokens(w.text) for other in words) == 1]
        if not unique:
            return _row_options(row, words, physical=True, allow_quantisation=True)
        anchor = max(unique, key=lambda w: math.dist(w.vertices[0], w.vertices[1]))
        a, b = anchor.vertices[:2]
        length = math.dist(a, b)
        if not length:
            return ()
        normal = (-(b[1] - a[1]) / length, (b[0] - a[0]) / length)

        def frame(word):
            values = [normal[0] * x + normal[1] * y for x, y in word.vertices]
            return (min(values) + max(values)) / 2, max(values) - min(values)

        center, height = frame(anchor)
        pool = tuple(w for w in words if abs(frame(w)[0] - center) <= 2 + 0.55 * max(height, frame(w)[1]))
        return tuple(tuple(words.index(pool[i]) for i in option)
                     for option in _row_options(row, pool, physical=True, allow_quantisation=True))

    options = literal_options(primary_rows[0])
    if len(options) != 1:
        return False
    primary = tuple(words[i] for i in options[0])
    # The repeated percentage must also have its own complete printed row.
    repeat_rows = [row for row in rows if re.fullmatch(r"\$?\s*100\s*%\s*-\s*[^\W\d_]+", row)]
    if len(repeat_rows) != 1:
        return False
    repeats = literal_options(repeat_rows[0])
    if len(repeats) != 1 or not set(primary).isdisjoint(words[i] for i in repeats[0]):
        return False
    start, end = rows.index(primary_rows[0]), rows.index(repeat_rows[0]) + 1
    # The translations and their exclusion caption must be consecutive
    # physical rows in the primary row's reading frame, not another label.
    anchor = max(primary, key=lambda w: math.dist(w.vertices[0], w.vertices[1]))
    (x0, y0), (x1, y1), *_ = anchor.vertices
    length = math.hypot(x1 - x0, y1 - y0)
    direction = ((x1 - x0) / length, (y1 - y0) / length)
    normal = (-direction[1], direction[0])
    used, previous = set(), None
    for row in rows[start:end + 1]:
        options = literal_options(row)
        if len(options) != 1:
            return False
        located = tuple(words[i] for i in options[0])
        if used.intersection(located):
            return False
        used.update(located)
        row_anchor = max(located, key=lambda w: math.dist(w.vertices[0], w.vertices[1]))
        a, b = row_anchor.vertices[:2]
        row_length = math.dist(a, b)
        if ((b[0] - a[0]) * direction[0] + (b[1] - a[1]) * direction[1]) / row_length < 0.98:
            return False
        points = [point for w in located for point in w.vertices]
        xs = [direction[0] * x + direction[1] * y for x, y in points]
        ys = [normal[0] * x + normal[1] * y for x, y in points]
        frame = (min(xs), max(xs), (min(ys) + max(ys)) / 2, max(ys) - min(ys))
        intervals = sorted((
            min(direction[0] * x + direction[1] * y for x, y in w.vertices),
            max(direction[0] * x + direction[1] * y for x, y in w.vertices),
        ) for w in located)
        if any(b[0] - a[1] > 3 * frame[3] for a, b in zip(intervals, intervals[1:])):
            return False
        if previous and (frame[2] <= previous[2]
                         or frame[2] - previous[2] > 3 * max(frame[3], previous[3])
                         or min(frame[1], previous[1]) <= max(frame[0], previous[0])):
            return False
        previous = frame
    return True


def same_region_recovery(
    candidate: OcrCandidate, alternative: OcrCandidate, part: str,
    candidates: list[OcrCandidate] | None = None,
) -> bool:
    """Require a valid reread covering every source row, word, fiber and ratio."""
    if (candidate is alternative or alternative.parser_status != "success"
            or not candidate.image_key or candidate.image_key != alternative.image_key
            or not candidate.image_words or not alternative.image_words
            or len(alternative.image_region) != 4):
        return False
    if len({word.page for word in candidate.image_words + alternative.image_words}) != 1:
        return False
    target_part = part
    if part == "generic" and part not in alternative.parts:
        if len(alternative.parts) != 1:
            return False
        target_part = next(iter(alternative.parts))
    if target_part not in alternative.parts:
        return False
    forbidden = NEGATING_MODIFIERS | UNPRICED_MATERIALS | {"unknown", "olefin", "未知繊維", "未知纤维"}
    if any(token in forbidden for token in _tokens(candidate.text) + _tokens(alternative.text)):
        return False
    if _joined_separator_recovery(candidate, alternative, part, target_part, candidates or []):
        return True
    if _same_response_metadata_recovery(candidate, alternative, part, target_part):
        return True
    if _same_response_ratio_order_recovery(candidate, alternative, part, candidates or []):
        return True
    if _same_response_bounded_recovery(candidate, alternative, part, candidates or []):
        return True
    if _shared_percent_recovery(candidate, alternative, part, target_part):
        return True
    if _repeated_translation_recovery(candidate, alternative, part, target_part, candidates or []):
        return True
    if _mixed_translation_recovery(candidate, alternative, part, target_part, candidates or []):
        return True
    if _same_response_hyphen_recovery(candidate, alternative, part, target_part):
        return True
    if ((_has_unclassified_context(candidate) and not _literal_raw_context(candidate, candidates or []))
            or (_has_unclassified_context(alternative) and not _literal_raw_context(alternative, candidates or []))):
        return False
    if _percent_glyph_recovery(candidate, alternative, part, target_part, candidates or []):
        return True
    rows = _evidence_rows(candidate, part)
    target_rows = _evidence_rows(alternative, target_part)
    literal_cjk = False
    tokenise = _tokens
    if (any(_has_cjk(token) and find_material_key(token)
            for token in _tokens(candidate.text) + _tokens(alternative.text))
            and (not rows or not target_rows
                 or not _covers_row_tokens(_tokens(candidate.text), list(candidate.image_words))
                 or not _covers_row_tokens(_tokens(alternative.text), list(alternative.image_words)))):
        # Only the coordinate proof may split CJK names. Both complete OCR
        # texts must partition all annotations, including context and unknown
        # characters outside the selected composition rows. The failed read
        # and its correction must still be two actual OCR inputs.
        if (not candidate.image_variant_key or not alternative.image_variant_key
                or candidate.image_variant_key == alternative.image_variant_key
                or candidate.source == alternative.source):
            return False
        literal_cjk = True
        tokenise = _annotation_tokens
        rows = _evidence_rows(candidate, part, tokenise=tokenise)
        target_rows = _evidence_rows(alternative, target_part, tokenise=tokenise)
    if not rows:
        return _same_response_source_recovery(candidate, alternative, part, candidates or [])
    if not target_rows:
        return False
    if literal_cjk and any(info.invalid_evidence or info.unresolved_materials for info, _words in target_rows):
        # A complete character partition cannot turn an unpriced/negated
        # material caption into valid context merely because it has no ratio.
        return False
    # Equal digit/dot tokens can still mean .5 in the source and 5 after an
    # inferred row join. Ordinary recovery must preserve fractional values;
    # only the independently proved attached separator above may change one.
    target_pairs = {(material, float(value)) for material, value
                    in alternative.paired_material_ratios.get(target_part, [])}
    for info, _words in rows:
        for value in info.numbers:
            ratio = float(value)
            if not ratio.is_integer() and (
                not info.materials or any((material, ratio) not in target_pairs for material in info.materials)
            ):
                return False
    if any(info.unresolved_materials or re.search(r"[-+−]\s*\d", info.normalized)
           for info, _words in rows):
        return False
    source_materials = Counter(m for info, _words in rows for m in info.materials)
    target_materials = Counter(m for info, _words in target_rows for m in info.materials)
    if not target_materials >= source_materials:
        return False
    left, top, right, bottom = alternative.image_region
    source_words = tuple(dict.fromkeys(word for _info, words in rows for word in words))
    target_words = tuple(dict.fromkeys(word for _info, words in target_rows for word in words))
    context_words = _context_words(alternative, target_words, tokenise=tokenise)
    if candidate.layout_used and candidate.parser_status != "success" and context_words:
        # A bad horizontal layout can spread one physical composition row
        # over both composition and context lines. Prove all words instead of
        # choosing which repeated percentage belongs to its broken row.
        if not _covers_row_tokens(tokenise(candidate.text), list(candidate.image_words), tokenise=tokenise):
            return False
        source_words = candidate.image_words
    supporters = []
    for item in candidates or ():
        if (item.image_key != candidate.image_key or not item.image_variant_key
                or item.parser_status != "success"
                or item.parts.get(target_part) != alternative.parts[target_part]):
            continue
        other_rows = _evidence_rows(item, target_part, tokenise=tokenise)
        other_words = tuple(dict.fromkeys(word for _info, words in other_rows for word in words))
        if (other_words and _aligned_reading(target_words, other_words, literal_cjk=literal_cjk)
                and _aligned_reading(other_words, target_words, literal_cjk=literal_cjk)
                and (not literal_cjk or (_cjk_components_align(target_words, other_words)
                                        and _cjk_components_align(other_words, target_words)))):
            supporters.append(item)
    # Raw and layout text from one response are one input, not two confirmations.
    corroborated = (len({item.image_variant_key for item in supporters}) >= 2
                    and len({item.source for item in supporters}) >= 2)
    if not _numeric_components_align(source_words, target_words, context_words,
                                     corroborated=corroborated):
        return False
    if literal_cjk and not _cjk_components_align(source_words, target_words + context_words):
        return False
    if any(not (left - 2 <= word.left and word.right <= right + 2
                and top - 2 <= word.top and word.bottom <= bottom + 2) for word in source_words):
        return False
    numeric_artifact = any(re.fullmatch(r"\d{4}%?", normalize_text(word.text).replace(" ", ""))
                           and int(re.sub(r"\D", "", word.text)) > 100 for word in source_words)
    numeric_changes = 0
    for word in source_words:
        token = normalize_text(word.text).replace(" ", "")
        if token in forbidden:
            return False
        if token in {":", ",", ";", "/", "|", "(", ")", "[", "]"}:
            continue
        # Layout can place origin/trim words on a composition row. Their
        # exact text and original coordinates must still exist in the reread;
        # they cannot supply a material name or a changed percentage.
        if context_words and not re.search(r"\d|%", token) and not find_material_key(token):
            context_nearby = [target for target in context_words if _overlaps(word, target)]
            if _matching_token_parts(word, context_nearby, allow_change=False, literal_cjk=literal_cjk) == 0:
                continue
        nearby = [target for target in target_words if _overlaps(word, target)]
        if not nearby:
            return False
        if any(token == normalize_text(target.text).replace(" ", "") for target in nearby):
            continue
        matched = _matching_token_parts(word, nearby, allow_change=True,
                                        corroborated=corroborated, numeric_artifact=numeric_artifact,
                                        literal_cjk=literal_cjk)
        if matched is not None:
            numeric_changes += matched
            if numeric_changes > 1:
                return False
            continue
        if literal_cjk and _has_cjk(word.text):
            # A permissive alias lookup must not erase an unmatched sign or
            # character after the complete literal CJK comparison failed.
            return False
        # A material alias lookup may strip a trailing dot. That cannot erase
        # a decimal/separator component that the complete-token match rejected.
        if "." in _tokens(word.text):
            return False
        # OCR may join or split a percent sign without changing its value.
        old_number = re.fullmatch(r"(\d{1,4})%?", token)
        if old_number:
            numbers = [match.group(1) for target in nearby
                       if (match := re.fullmatch(r"(\d{1,3})%?", normalize_text(target.text).replace(" ", "")))]
            if old_number.group(1) in numbers:
                continue
            if any(_one_digit_gap(old_number.group(1), number) or (
                corroborated and len(old_number.group(1)) == len(number)
                and sum(a != b for a, b in zip(old_number.group(1), number)) == 1
            ) for number in numbers):
                numeric_changes += 1
                if numeric_changes > 1:
                    return False
                continue
            return False
        if token == "%" and any("%" in target.text for target in nearby):
            continue
        key = find_material_key(token)
        if key and any(find_material_key(target.text) == key for target in nearby):
            continue
        if not key and token.isascii() and token.isalpha() and any(
            find_material_key(target.text) and len(token) == len(normalize_text(target.text))
            and sum(a != b for a, b in zip(token, normalize_text(target.text))) == 1
            for target in nearby
        ):
            continue
        # A short garbled heading beside an impossible four-digit percentage
        # may be replaced only where the valid reread actually has label text.
        if numeric_artifact and not key and token.isalpha() and len(token) <= 3 and any(
            _tokens(target.text) and not re.search(r"\d", target.text) for target in nearby
        ):
            continue
        return False
    return True


def _verified_layout_rows(candidate: OcrCandidate):
    """Keep the provider's boxes and require the same geometry-derived rows."""
    if (not candidate.layout_used or not candidate.image_words
            or not candidate.image_variant_key or len(candidate.image_region) != 4):
        return []
    left, top, right, bottom = candidate.image_region
    if any(not (left - 2 <= word.left and word.right <= right + 2
                and top - 2 <= word.top and word.bottom <= bottom + 2)
           for word in candidate.image_words):
        return []
    from dataclasses import replace
    from apps.text.ocr_layout import spatial_text_from_words

    # Temporary IDs expose the existing row grouping without changing its
    # geometry or duplicating the layout algorithm. No text is added to OCR.
    tagged = [replace(word, text=str(index)) for index, word in enumerate(candidate.image_words)]
    grouped = spatial_text_from_words(tagged).splitlines()
    lines = candidate.text.splitlines()
    if len(grouped) != len(lines):
        return []
    rows = []
    for line, ids in zip(lines, grouped):
        words = tuple(candidate.image_words[int(index)] for index in ids.split())
        if _tokens(line) != _tokens(" ".join(word.text for word in words)):
            return []
        rows.append((line, words))
    return rows

def _same_response_ratio_order_recovery(candidate, alternative, part, candidates):
    """Reassign repeated ratio boxes only to explicit, valid physical rows."""
    if (candidate.layout_used or not alternative.layout_used or part == "generic"
            or part not in alternative.parts or alternative.parser_status != "success"
            or part not in candidate.unpaired_ratio_parts
            or set(candidate.rejected_composition_parts.get(part, ())) - {"invalid_composition_evidence"}
            or not candidate.image_key or candidate.image_key != alternative.image_key
            or not candidate.image_variant_key or candidate.image_variant_key != alternative.image_variant_key
            or candidate.source != alternative.source
            or candidate.image_words != alternative.image_words
            or len(candidate.image_region) != 4 or candidate.image_region != alternative.image_region
            or Counter(_annotation_tokens(candidate.text)) != Counter(_annotation_tokens(alternative.text))
            or not _covers_row_tokens(_annotation_tokens(candidate.text), list(candidate.image_words),
                                      tokenise=_annotation_tokens)):
        return False
    rows = _verified_layout_rows(alternative)
    if not rows:
        # Mapping a scaled crop back to image coordinates can move an
        # isolated percent box across a row boundary by one rounded pixel.
        # Re-group only unchanged annotation tokens; the checked ratio rows
        # below must still exist verbatim in the provider's layout text.
        from apps.text.ocr_layout import spatial_text_from_words

        mapped_text = spatial_text_from_words(list(alternative.image_words))
        if (Counter(_annotation_tokens(mapped_text)) == Counter(_annotation_tokens(alternative.text))
                and tuple(t for t in _annotation_tokens(mapped_text) if t != "%")
                == tuple(t for t in _annotation_tokens(alternative.text) if t != "%")):
            rows = _verified_layout_rows(replace(alternative, text=mapped_text))
    if not rows:
        return False
    left, top, right, bottom = alternative.image_region
    if any(not (left - 2 <= word.left and word.right <= right + 2
                and top - 2 <= word.top and word.bottom <= bottom + 2)
           for _line, words in rows for word in words):
        return False
    from apps.text.parse_label import build_line_infos, _is_metadata_line

    source_infos = [info for info in build_line_infos(candidate.text)
                    if info.part == part and not _is_metadata_line(info)]
    identifier_indices = set()
    for info in source_infos:
        if info.unresolved_materials:
            return False
        if not info.invalid_evidence:
            continue
        # Vision can split a product identifier into a signed numeric row.
        # Exempt it only if these exact boxes belong to a labelled product
        # code in the geometry-derived view of this very same response.
        if not re.fullmatch(r"\s*-\s*\d{3,}\s*", info.normalized):
            return False
        words = _row_words(info.raw, candidate.image_words, tokenise=_annotation_tokens)
        identifier_rows = [row_words for line, row_words in rows
            if re.match(r"\s*(?:품\s*번|product\s*(?:code|number)|style\s*(?:no|number))\s*:",
                        normalize_text(line))
            and not re.search(r"%", line)
            and not any(find_material_key(token) for token in _tokens(line))]
        if not words or not any(set(words) <= set(row_words) for row_words in identifier_rows):
            return False
        identifier_indices.add(info.index)
    source_infos = [info for info in source_infos if info.index not in identifier_indices]
    if (Counter(candidate.observed_materials.get(part, ()))
            != Counter(alternative.observed_materials.get(part, ()))
            or not Counter(tuple(pair) for pair in candidate.paired_material_ratios.get(part, ()))
            <= Counter(alternative.parts[part].items())):
        return False
    required = Counter(str(int(number)) for info in source_infos for number in info.numbers
                       if number == int(number))
    if (not required or sum(required.values()) != sum(len(info.numbers) for info in source_infos)
            or any(re.search(r"[-+−]\s*\d", info.normalized) for info in source_infos)):
        return False
    located = Counter(token for word in candidate.image_words for token in _tokens(word.text)
                      if token in required)
    # A repeated value elsewhere on the label would make its origin ambiguous.
    if located != required:
        return False
    infos = build_line_infos(alternative.text)
    used_parts = set()
    for line, words in rows:
        if not any(token in required for word in words for token in _tokens(word.text)):
            continue
        matching = [info for info in infos if _tokens(info.raw) == _tokens(line)]
        if len(matching) != 1:
            return False
        info = matching[0]
        if (_is_metadata_line(info) or info.invalid_evidence
                or info.unresolved_materials or not info.explicit_percent
                or len(info.materials) != 1 or len(info.numbers) != 1):
            return False
        if info.part == "generic":
            # A damaged upper heading may also be located by an independent
            # reread. Its error remains on those parts; only the ratio's raw
            # paragraph order is resolved here.
            located_parts = located_generic_rejection_parts(alternative, candidates or [])
            if part != "lining" or not located_parts or part in located_parts:
                return False
            used_parts.update(located_parts)
        elif any(other.marker_part == info.part for other in infos):
            used_parts.add(info.part)
        else:
            return False
    return part in used_parts and len(used_parts) > 1


def located_generic_rejection_parts(candidate, candidates):
    """Preserve generic errors under parts independently located beside lining."""
    from apps.text.parse_label import build_line_infos, _is_metadata_line

    peers = [candidate] if candidate.layout_used else [peer for peer in candidates
        if peer.layout_used and peer.source == candidate.source
        and candidate.image_variant_key and peer.image_variant_key == candidate.image_variant_key
        and peer.image_key == candidate.image_key and peer.image_region == candidate.image_region
        and peer.image_words == candidate.image_words
        and Counter(_annotation_tokens(peer.text)) == Counter(_annotation_tokens(candidate.text))
        and _covers_row_tokens(_annotation_tokens(candidate.text), list(candidate.image_words),
                              tokenise=_annotation_tokens)]
    for peer in peers:
        if not peer.image_key or 'lining' not in peer.parts:
            continue
        rows = _verified_layout_rows(peer)
        infos = build_line_infos(peer.text)
        evidence = [index for index, info in enumerate(infos)
                    if info.part == 'generic' and not _is_metadata_line(info)
                    and (info.materials or info.numbers or info.explicit_percent
                         or info.invalid_evidence or info.unresolved_materials)]
        if not rows or not evidence:
            continue
        source_words = []
        for info in infos[min(evidence):max(evidence) + 1]:
            if info.part != 'generic':
                continue
            matching = [words for line, words in rows if _tokens(line) == _tokens(info.raw)]
            if len(matching) != 1:
                break
            source_words.extend(matching[0])
        else:
            for alternative in candidates:
                if (not alternative.layout_used or alternative.parser_status != 'success'
                        or alternative.selected_part != 'lining'
                        or alternative.parts.get('lining') != peer.parts['lining']
                        or alternative.image_key != peer.image_key
                        or not alternative.image_variant_key
                        or alternative.image_variant_key == peer.image_variant_key
                        or len(alternative.image_region) != 4):
                    continue
                target_rows = _verified_layout_rows(alternative)
                target_infos = build_line_infos(alternative.text)
                declared = {info.marker_part for info in target_infos if info.marker_part}
                if not {'outer', 'lining'} <= declared or not target_rows:
                    continue
                located = []
                headings = []
                for line, words in target_rows:
                    matching = [info for info in target_infos if _tokens(info.raw) == _tokens(line)]
                    if len(matching) == 1 and not _is_metadata_line(matching[0]):
                        located.append((matching[0].part, words))
                        if matching[0].marker_part:
                            headings.append((matching[0].marker_part, words))
                left, top, right, bottom = alternative.image_region
                parts = set()
                for word in source_words:
                    if not (left - 2 <= word.left and word.right <= right + 2
                            and top - 2 <= word.top and word.bottom <= bottom + 2):
                        break
                    matches = {target_part for target_part, words in located
                               if any(_overlaps(word, other) for other in words)}
                    if not matches:
                        # A damaged source word can be absent from the reread.
                        # Keep its rejection within a vertically bounded part,
                        # never below the last heading or across two columns.
                        # Both bordering headings must be physically ordered
                        # and on the same page as the missing source box.
                        for (section, first), (_next, following) in zip(headings, headings[1:]):
                            if (len({w.page for w in (*first, *following, word)}) == 1
                                    and max(w.bottom for w in first) < min(w.top for w in following)
                                    and min(w.top for w in first) <= word.top
                                    and word.bottom < min(w.top for w in following)):
                                matches.add(section)
                    if not matches or 'generic' in matches or not matches <= declared:
                        break
                    parts.update(matches)
                else:
                    # Keep the reasons on every located part. In particular an
                    # error aligned with lining still invalidates that lining.
                    if parts:
                        return tuple(sorted(parts))
    return ()
