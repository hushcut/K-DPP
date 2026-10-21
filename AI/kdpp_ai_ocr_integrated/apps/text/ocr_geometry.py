"""OCR 단어 좌표 변환과 행·토큰의 위치 일치를 확인하는 순수 함수."""

from __future__ import annotations

import math
import re
from collections import Counter

from apps.text.material_extraction import find_material_key, normalize_text
from apps.text.ocr_layout import OcrWord


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
