"""같은 이미지 위치의 재인식으로 확인된 OCR 손상만 후보 간 해소한다."""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

from apps.text.material_extraction import (
    NEGATING_MODIFIERS, UNPRICED_MATERIALS, find_material_key, normalize_text,
)
from apps.text.ocr_layout import OcrWord

if TYPE_CHECKING:
    from apps.text.ocr_candidates import OcrCandidate


def transform_words(words: tuple[OcrWord, ...], transform: tuple[float, ...]) -> tuple[OcrWord, ...]:
    a, b, c, d, e, f = transform
    mapped = []
    for word in words:
        points = word.vertices or ((word.left, word.top), (word.right, word.top),
                                   (word.right, word.bottom), (word.left, word.bottom))
        vertices = tuple((round(a * x + b * y + c), round(d * x + e * y + f)) for x, y in points)
        xs, ys = zip(*vertices)
        mapped.append(OcrWord(word.text, min(xs), min(ys), max(xs), max(ys), vertices, word.page))
    return tuple(mapped)


def _tokens(text: str) -> tuple[str, ...]:
    # Vision text may join a fiber and ratio while word boxes split them.
    return tuple(re.findall(r"[^\W\d_]+|\d+|[^\w\s]", normalize_text(text)))


def _row_words(text: str, words: tuple[OcrWord, ...]) -> tuple[OcrWord, ...]:
    row = _tokens(text)
    row_numbers = Counter(token for token in row if token.isdecimal())
    matches = [word for word in words if _tokens(word.text) and any(
        row[index:index + len(_tokens(word.text))] == _tokens(word.text)
        for index in range(len(row))
    )]
    anchors = [word for word in matches if len(normalize_text(word.text).strip()) > 1
               or normalize_text(word.text).strip().isdigit()]
    if not anchors:
        return tuple(matches) if len(matches) == 1 and not row_numbers else ()
    # A repeated token in different physical rows cannot locate this row safely.
    counts = Counter(_tokens(word.text) for word in anchors)
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
    # A partial token match must not erase a ratio or reuse its box.
    located_numbers = Counter(
        token for word in selected for token in _tokens(word.text) if token.isdecimal()
    )
    if located_numbers != row_numbers:
        return ()
    return tuple(selected)


def _evidence_rows(candidate: OcrCandidate, part: str):
    from apps.text.parse_label import build_line_infos, _is_metadata_line

    rows = []
    for info in build_line_infos(candidate.text):
        if info.part != part or _is_metadata_line(info):
            continue
        if not (info.materials or info.numbers or info.explicit_percent
                or info.invalid_evidence or info.unresolved_materials):
            continue
        words = _row_words(info.raw, candidate.image_words)
        if not words:
            return []
        rows.append((info, words))
    return rows


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


def _aligned_reading(words: tuple[OcrWord, ...], other: tuple[OcrWord, ...]) -> bool:
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
        return False
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
    target_part = part
    if part == "generic" and part not in alternative.parts:
        if len(alternative.parts) != 1:
            return False
        target_part = next(iter(alternative.parts))
    if target_part not in alternative.parts:
        return False
    rows = _evidence_rows(candidate, part)
    target_rows = _evidence_rows(alternative, target_part)
    if not rows or not target_rows:
        return False
    forbidden = NEGATING_MODIFIERS | UNPRICED_MATERIALS | {"unknown", "未知繊維", "未知纤维"}
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
    supporters = []
    for item in candidates or ():
        if (item.image_key != candidate.image_key or not item.image_variant_key
                or item.parser_status != "success"
                or item.parts.get(target_part) != alternative.parts[target_part]):
            continue
        other_rows = _evidence_rows(item, target_part)
        other_words = tuple(dict.fromkeys(word for _info, words in other_rows for word in words))
        if other_words and _aligned_reading(target_words, other_words) and _aligned_reading(other_words, target_words):
            supporters.append(item)
    # Raw and layout text from one response are one input, not two confirmations.
    corroborated = (len({item.image_variant_key for item in supporters}) >= 2
                    and len({item.source for item in supporters}) >= 2)
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
        nearby = [target for target in target_words if _overlaps(word, target)]
        if not nearby:
            return False
        if any(token == normalize_text(target.text).replace(" ", "") for target in nearby):
            continue
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
