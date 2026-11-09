"""Geometry for a literal care caption and the number printed below it.

Callers validate the registered caption, complete annotation provenance and
region containment. These helpers neither interpret care symbols nor infer a
number from a different annotation.
"""

from __future__ import annotations

import math
import re
import unicodedata

from apps.text.ocr_geometry import _physical_row
from apps.text.ocr_layout import OcrWord


_SUPPORTED_NUMBERS = frozenset({"30", "40", "50", "60", "70", "95"})
_DIRECTION_LIMIT = math.cos(math.radians(3))


def _literal_tokens(text: str) -> tuple[str, ...]:
    # Geometry must use the supplied characters, without OCR spelling repair.
    return tuple(re.findall(
        r"[^\W\d_]+|\d+|[^\w\s]",
        unicodedata.normalize("NFKC", text).casefold(),
    ))


def _valid_quad(word: OcrWord) -> bool:
    points = word.vertices
    if len(points) != 4 or any(not math.isfinite(value) for point in points for value in point):
        return False
    edges = tuple((points[(i + 1) % 4][0] - points[i][0],
                   points[(i + 1) % 4][1] - points[i][1]) for i in range(4))
    turns = tuple(a[0] * b[1] - a[1] * b[0]
                  for a, b in zip(edges, edges[1:] + edges[:1]))
    return all(value > 0 for value in turns) or all(value < 0 for value in turns)


def _extent(words: tuple[OcrWord, ...], axis: tuple[float, float]) -> tuple[float, float]:
    values = [axis[0] * x + axis[1] * y for word in words for x, y in word.vertices]
    return min(values), max(values)


def vertical_care_cell(caption_words, number_word: OcrWord) -> bool:
    """Prove one caption row and an aligned supported bare number below it.

    ``caption_words`` is in the registered caption's literal reading order.
    Registration of that phrase is the caller's responsibility.
    """
    caption = tuple(caption_words)
    words = caption + (number_word,)
    number = unicodedata.normalize("NFKC", number_word.text).strip()
    if (not caption or number not in _SUPPORTED_NUMBERS
            or len(set(words)) != len(words) or len({word.page for word in words}) != 1
            or any(not _valid_quad(word) for word in words)):
        return False
    caption_text = " ".join(word.text for word in caption)
    if (not _physical_row(caption_text, caption, tokenise=_literal_tokens)
            or not _physical_row(number_word.text, (number_word,), tokenise=_literal_tokens)):
        return False
    anchor = max(caption, key=lambda word: math.dist(word.vertices[0], word.vertices[1]))
    (x0, y0), (x1, y1), *_ = anchor.vertices
    length = math.hypot(x1 - x0, y1 - y0)
    direction = ((x1 - x0) / length, (y1 - y0) / length)
    normal = (-direction[1], direction[0])
    for word in words:
        # Reading directions use ordered top edges. Each word's own bottom
        # edge has already passed the existing strict physical-row verifier.
        start, end = word.vertices[:2]
        dx, dy = end[0] - start[0], end[1] - start[1]
        span = math.hypot(dx, dy)
        if not span or (dx * direction[0] + dy * direction[1]) / span < _DIRECTION_LIMIT:
            return False
    caption_low, caption_high = _extent(caption, normal)
    number_low, number_high = _extent((number_word,), normal)
    gap = number_low - caption_high
    if not 1 < gap <= max(caption_high - caption_low, number_high - number_low):
        return False
    caption_left, caption_right = _extent(caption, direction)
    number_left, number_right = _extent((number_word,), direction)
    width = min(caption_right - caption_left, number_right - number_left)
    return width > 0 and min(caption_right, number_right) - max(caption_left, number_left) >= 0.5 * width


def care_cell_clear(words, caption_words, number_word: OcrWord, *, allowed_words=()) -> bool:
    """Reject any other annotation with positive area inside the cell's bbox.

    ``allowed_words`` contains only additional annotations whose same-place
    identity has already been proved by the caller, such as a reread's number.
    Boundary contact alone has zero area and is not an intrusion.
    """
    caption = tuple(caption_words)
    cell = caption + (number_word,)
    if (not caption or len({word.page for word in cell}) != 1
            or any(not _valid_quad(word) for word in cell)):
        return False
    left = min(word.left for word in cell)
    top = min(word.top for word in cell)
    right = max(word.right for word in cell)
    bottom = max(word.bottom for word in cell)
    if (not all(math.isfinite(value) for value in (left, top, right, bottom))
            or left >= right or top >= bottom):
        return False
    allowed = set(cell) | set(allowed_words)
    for word in words:
        if word.page != number_word.page:
            return False
        if word in allowed:
            continue
        if (not all(math.isfinite(value) for value in (word.left, word.top, word.right, word.bottom))
                or word.left >= word.right or word.top >= word.bottom):
            return False
        if min(right, word.right) > max(left, word.left) and min(bottom, word.bottom) > max(top, word.top):
            return False
    return True
