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
    # 동아시아 소재명이 여러 상자로 나뉘어도 모든 글자를 보존한다.
    # 숫자는 한 토큰으로 유지하여 자릿수 누락이나 숫자 재사용을 검사한다.
    return tuple(re.findall(
        r"[가-힣一-龥ぁ-んァ-ンー]|[^\W\d_가-힣一-龥ぁ-んァ-ンー]+|\d+|[^\w\s]",
        normalize_text(text),
    ))


def _row_words(text: str, words: tuple[OcrWord, ...]) -> tuple[OcrWord, ...]:
    row = _tokens(text)
    row_numbers = Counter(token for token in row if token.isdecimal())
    # 같은 단어의 정규화와 토큰 분할은 행마다 한 번만 계산한다.
    word_tokens = {value: _tokens(value) for value in dict.fromkeys(word.text for word in words)}
    matches = []
    for word in words:
        tokens = word_tokens[word.text]
        if tokens and any(
            row[index:index + len(tokens)] == tokens
            for index in range(len(row) - len(tokens) + 1)
        ):
            matches.append(word)
    anchors = [word for word in matches if len(normalize_text(word.text).strip()) > 1
               or normalize_text(word.text).strip().isdigit()]
    if not anchors:
        return tuple(matches) if len(matches) == 1 and not row_numbers else ()
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
    # 넓은 행 범위에 옆줄의 퍼센트가 섞이지 않도록 가장 가까운 숫자 행에 연결한다.
    numeric_anchors = [
        word for word in anchors if any(token.isdecimal() for token in word_tokens[word.text])
    ]
    other_numbers = [word for word in words if word not in numeric_anchors
                     and any(token.isdecimal() for token in word_tokens[word.text])]
    if numeric_anchors and other_numbers and len(percent_words) > 1:
        selected = [word for word in selected if normalize_text(word.text) != "%"
                    or min(abs(word.center_y - anchor.center_y) for anchor in numeric_anchors)
                    <= min(abs(word.center_y - anchor.center_y) for anchor in other_numbers)]
    # A partial token match must not erase a ratio or reuse its box.
    located_numbers = Counter(
        token for word in selected for token in word_tokens[word.text] if token.isdecimal()
    )
    if located_numbers != row_numbers:
        return ()
    return tuple(selected)


def _same_response_metadata_recovery(
    candidate: OcrCandidate, alternative: OcrCandidate, part: str,
) -> bool:
    """같은 응답의 좌표 행에서 확인된 세탁 숫자만 원문의 잔여 근거에서 제외한다."""

    if (
        candidate.layout_used or not alternative.layout_used
        or alternative.parser_status != "success"
        or not candidate.image_key or candidate.image_key != alternative.image_key
        or not candidate.image_variant_key or candidate.image_variant_key != alternative.image_variant_key
        or candidate.source != alternative.source
        or not candidate.image_words or candidate.image_words != alternative.image_words
        or len(candidate.image_region) != 4 or candidate.image_region != alternative.image_region
    ):
        return False
    # 좌표 복원은 글자·숫자·퍼센트·기호를 추가하거나 버릴 수 없다.
    tokens = Counter(_tokens(candidate.text))
    if (tokens != Counter(_tokens(alternative.text))
            or tokens != Counter(_tokens(" ".join(word.text for word in candidate.image_words)))):
        return False

    from apps.text.parse_label import build_line_infos, _is_metadata_line, _mentions_care

    source_infos = build_line_infos(candidate.text)
    target_infos = build_line_infos(alternative.text)
    if any(info.marker_part == "outer_2" for info in source_infos) and "outer_2" not in alternative.parts:
        return False
    target_part = part
    if part == "generic" and part not in alternative.parts:
        if len(alternative.parts) != 1:
            return False
        target_part = next(iter(alternative.parts))
    if target_part not in alternative.parts:
        return False
    source_rows = [(info, _row_words(info.raw, candidate.image_words)) for info in source_infos
                   if info.part == part and not _is_metadata_line(info)
                   and (info.materials or info.numbers or info.explicit_percent
                        or info.invalid_evidence or info.unresolved_materials)]
    metadata_words = []
    for index, info in enumerate(target_infos):
        if info.part != target_part or not _is_metadata_line(info):
            continue
        wash_outline = (
            re.search(r"(?<!\d)1(?:30|40|50|60|70|95)(?!\d)", info.normalized)
            and re.search(r"[/\\]", info.normalized)
        )
        care_nearby = any(_mentions_care(row.normalized) and not row.materials and not row.explicit_percent
                          for row in target_infos[index:index + 4] if row.part == target_part)
        if wash_outline or care_nearby:
            metadata_words.extend(_row_words(info.raw, alternative.image_words))
    if not source_rows or not metadata_words:
        return False
    retained = []
    removed = False
    for info, words in source_rows:
        # 모든 토큰과 숫자의 좌표가 필요하다. 반복 숫자 상자의 재사용도 허용하지 않는다.
        if (not words or info.unresolved_materials
                or Counter(_tokens(info.raw)) != Counter(token for word in words for token in _tokens(word.text))):
            return False
        left, top, right, bottom = alternative.image_region
        if any(
            word.left < left - 2 or word.top < top - 2
            or word.right > right + 2 or word.bottom > bottom + 2
            for word in words
        ):
            return False
        compact = re.sub(r"[ \t]+", "", info.normalized)
        wash_number = not info.materials and not info.explicit_percent and re.fullmatch(
            r"(?:30|40|50|60|70|95)|1(?:30|40|50|60|70|95)[/\\]", compact,
        )
        if wash_number and all(word in metadata_words for word in words):
            removed = True
            continue
        if info.invalid_evidence:
            return False
        retained.append(info)
    if not removed:
        return False
    paired = Counter(tuple(pair) for pair in candidate.paired_material_ratios.get(part, ()))
    if not paired <= Counter(alternative.parts[target_part].items()):
        return False
    targets = [info for info in target_infos if info.part == target_part and not _is_metadata_line(info)]
    return (
        Counter(material for info in retained for material in info.materials)
        == Counter(material for info in targets for material in info.materials)
        and Counter(number for info in retained for number in info.numbers)
        == Counter(number for info in targets for number in info.numbers)
    )


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


def _percent_glyph_reread(word, token, rows, target_rows, target_parts) -> bool:
    """Accept 96 as a percent glyph only with an aligned, explicit reread."""
    match = re.fullmatch(r"([1-9]\d{0,2})96", token)
    if not match or not 0 < int(match.group(1)) <= 100:
        return False
    source_materials = Counter(m for info, _words in rows for m in info.materials)
    target_materials = Counter(m for info, _words in target_rows for m in info.materials)
    if (len(source_materials) < 2 or any(count != 1 for count in source_materials.values())
            or source_materials != target_materials):
        return False
    source_infos = [info for info, words in rows if word in words]
    if len(source_infos) != 1 or len(source_infos[0].materials) != 1:
        return False
    material = source_infos[0].materials[0]
    value = int(match.group(1))
    if target_parts.get(material) != value:
        return False
    for info, words in target_rows:
        if (info.materials != (material,) or info.numbers != (value,)
                or not info.explicit_percent or info.invalid_evidence):
            continue
        nearby = [target for target in words if _overlaps(word, target)]
        tokens = [normalize_text(target.text).replace(" ", "") for target in nearby]
        if str(value) + "%" in tokens or (str(value) in tokens and "%" in tokens):
            return True
    return False


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
    if _same_response_metadata_recovery(candidate, alternative, part):
        return True
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
    percent_glyph_changes = 0
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
        if _percent_glyph_reread(word, token, rows, target_rows, alternative.parts[target_part]):
            percent_glyph_changes += 1
            if numeric_changes:
                return False
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
                if numeric_changes > 1 or percent_glyph_changes:
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
