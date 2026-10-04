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
                 for value in (tuple(token) if token.isalpha() and not token.isascii() else (token,)))


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


def _has_unclassified_context(candidate: OcrCandidate) -> bool:
    """Do not discard opaque rows just because they lack a percent marker."""
    from apps.text.ocr_candidates import _is_plain_part_heading
    from apps.text.parse_label import (
        build_line_infos, _is_metadata_line, _mask_storage_caption,
        _looks_like_non_composition_number, COMPOSITION_HINTS, _CARE_PHRASES,
        _STORAGE_CAPTION_WORDS, _ORIGIN_ROW_PATTERN, declared_part,
    )

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
            and all(token.isdigit() or token == "%" or find_material_key(token)
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
    if ((_has_unclassified_context(candidate) and not _literal_raw_context(candidate, candidates or []))
            or (_has_unclassified_context(alternative) and not _literal_raw_context(alternative, candidates or []))):
        return False
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
