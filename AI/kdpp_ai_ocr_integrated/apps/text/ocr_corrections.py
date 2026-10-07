"""같은 이미지 위치의 재인식으로 확인된 OCR 손상만 후보 간 해소한다."""

from __future__ import annotations

import math
import re
from collections import Counter
from decimal import Decimal
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
            or candidate.rejected_composition_parts.get(part)
            or not candidate.image_key or candidate.image_key != alternative.image_key
            or not candidate.image_variant_key or candidate.image_variant_key != alternative.image_variant_key
            or candidate.source != alternative.source
            or candidate.image_words != alternative.image_words
            or len(candidate.image_region) != 4 or candidate.image_region != alternative.image_region
            or Counter(_tokens(candidate.text)) != Counter(_tokens(alternative.text))):
        return False
    rows = _verified_layout_rows(alternative)
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
    if (any(info.invalid_evidence or info.unresolved_materials for info in source_infos)
            or Counter(candidate.observed_materials.get(part, ()))
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
        and Counter(_tokens(peer.text)) == Counter(_tokens(candidate.text))]
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
                for line, words in target_rows:
                    matching = [info for info in target_infos if _tokens(info.raw) == _tokens(line)]
                    if len(matching) == 1 and not _is_metadata_line(matching[0]):
                        located.append((matching[0].part, words))
                left, top, right, bottom = alternative.image_region
                parts = set()
                for word in source_words:
                    if not (left - 2 <= word.left and word.right <= right + 2
                            and top - 2 <= word.top and word.bottom <= bottom + 2):
                        break
                    matches = {target_part for target_part, words in located
                               if any(_overlaps(word, other) for other in words)}
                    if not matches or 'generic' in matches or not matches <= declared:
                        break
                    parts.update(matches)
                else:
                    # Keep the reasons on every located part. In particular an
                    # error aligned with lining still invalidates that lining.
                    if parts:
                        return tuple(sorted(parts))
    return ()


def _evidence_rows(candidate: OcrCandidate, part: str):
    from apps.text.parse_label import build_line_infos, _is_metadata_line

    rows = []
    for info in build_line_infos(candidate.text):
        if info.part != part or _is_metadata_line(info):
            continue
        glyph_row = re.fullmatch(r"[&?][^\W\d_]|[^\W\d_][&?]", info.normalized.strip())
        if not (info.materials or info.numbers or info.explicit_percent
                or info.invalid_evidence or info.unresolved_materials or glyph_row):
            continue
        words = _row_words(info.raw, candidate.image_words)
        if not words:
            return []
        rows.append((info, words))
    return rows


def _located_evidence_rows(candidate: OcrCandidate, part: str, candidates):
    """Locate an unanchored glyph row through a token-preserving layout peer."""
    rows = _evidence_rows(candidate, part)
    if rows or candidate.layout_used:
        return rows
    from apps.text.parse_label import build_line_infos, _is_metadata_line

    source_infos = [info for info in build_line_infos(candidate.text)
                    if info.part == part and not _is_metadata_line(info)]
    for peer in candidates or ():
        if (not peer.layout_used or peer.source != candidate.source
                or peer.image_key != candidate.image_key
                or not candidate.image_variant_key
                or peer.image_variant_key != candidate.image_variant_key
                or peer.image_region != candidate.image_region
                or peer.image_words != candidate.image_words
                or Counter(_tokens(candidate.text)) != Counter(_tokens(peer.text))
                or Counter(_tokens(peer.text)) != Counter(_tokens(
                    " ".join(word.text for word in peer.image_words)))):
            continue
        peer_infos = [info for info in build_line_infos(peer.text)
                      if info.part == part and not _is_metadata_line(info)]
        if (any(info.unresolved_materials for info in source_infos)
                or Counter(m for info in source_infos for m in info.materials)
                != Counter(m for info in peer_infos for m in info.materials)
                or Counter(n for info in source_infos for n in info.numbers)
                != Counter(n for info in peer_infos for n in info.numbers)
                or [info.marker_part for info in source_infos if info.marker_part]
                != [info.marker_part for info in peer_infos if info.marker_part]):
            continue
        rows = _evidence_rows(peer, part)
        if rows:
            return rows
    return []


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


def _ratio_column_glyph_reread(word, token, rows, target_rows, target_parts):
    """Read one damaged ratio cell only at an aligned explicit numeric box."""
    if not re.fullmatch(r"[&?]|[^\W\d_]", token) or (token.isascii() and token.isalpha()):
        return None
    source_materials = Counter(m for info, _words in rows for m in info.materials)
    target_materials = Counter(m for info, _words in target_rows for m in info.materials)
    if (len(source_materials) < 2 or source_materials != target_materials
            or any(count != 1 for count in source_materials.values())):
        return None
    source_rows = [(info, words) for info, words in rows if word in words]
    if len(source_rows) != 1:
        return None
    info, words = source_rows[0]
    if (len(info.materials) != 1 or info.numbers
            or not info.invalid_evidence or info.unresolved_materials):
        return None
    material = info.materials[0]
    # A fiber name occupies the name column; damaged ratio glyphs must stay
    # to its right on the same physical row, beside the existing percent sign.
    names = [w for w in words if find_material_key(w.text) == material]
    percents = [w for w in words if normalize_text(w.text).strip() == "%"]
    if (len(names) != 1 or len(percents) != 1 or word.left < names[0].right
            or abs(word.center_y - names[0].center_y) > max(word.height, names[0].height)
            or abs(word.center_y - percents[0].center_y) > max(word.height, percents[0].height)
            or word.right > percents[0].right):
        return None
    value = target_parts.get(material)
    for target_info, target_words in target_rows:
        if (target_info.numbers != (value,) or not target_info.explicit_percent
                or target_info.invalid_evidence or target_info.unresolved_materials):
            continue
        numbers = [w for w in target_words if normalize_text(w.text).replace(" ", "").rstrip("%") == str(value)]
        if len(numbers) != 1 or not _overlaps(word, numbers[0]):
            continue
        if target_info.materials and target_info.materials != (material,):
            continue
        target_names = [w for _i, ws in target_rows for w in ws
                        if find_material_key(w.text) == material]
        if len(target_names) == 1 and _overlaps(names[0], target_names[0]):
            return material
    return None


def _trailing_percent_period_reread(word, rows, target_rows) -> bool:
    """Ignore a detached period only after the same aligned explicit ratio."""
    source_rows = [(info, words) for info, words in rows if word in words]
    if len(source_rows) != 1:
        return False
    info, words = source_rows[0]
    if (len(info.materials) != 1 or len(info.numbers) != 1
            or not info.explicit_percent or info.invalid_evidence or info.unresolved_materials
            or not re.search(r"\d{1,3}%\.$", info.normalized.replace(" ", ""))):
        return False
    percents = [w for w in words if normalize_text(w.text).strip().endswith("%")]
    names = [w for w in words if find_material_key(w.text) == info.materials[0]]
    if (len(percents) != 1 or len(names) != 1
            or not percents[0].right - 2 <= word.left <= percents[0].right + percents[0].height
            or abs(word.center_y - percents[0].center_y) > percents[0].height / 2):
        return False
    for target_info, target_words in target_rows:
        if (target_info.materials != info.materials or target_info.numbers != info.numbers
                or not target_info.explicit_percent or target_info.invalid_evidence
                or target_info.unresolved_materials):
            continue
        if (any(find_material_key(w.text) == info.materials[0] and _overlaps(names[0], w)
                for w in target_words)
                and any(normalize_text(w.text).strip().endswith("%") and _overlaps(percents[0], w)
                        for w in target_words)):
            return True
    return False


def _fused_decimal_reread(word, token, rows, target_parts, confirmations) -> bool:
    """Separate a name-adjacent dot only with two independent explicit rereads."""
    match = re.fullmatch(r"([^\W\d_]+)\.([1-9]\d?)", token)
    if not match:
        return False
    material = find_material_key(match.group(1))
    value = int(match.group(2))
    source_materials = Counter(m for info, _words in rows for m in info.materials)
    source_rows = [(info, words) for info, words in rows if word in words]
    if (not material or len(source_rows) != 1 or len(source_materials) < 2
            or any(count != 1 for count in source_materials.values())
            or target_parts.get(material) != value):
        return False
    info, words = source_rows[0]
    if (info.materials != (material,) or info.numbers != (Decimal("." + match.group(2)),)
            or not info.explicit_percent or info.invalid_evidence or info.unresolved_materials):
        return False
    percents = [w for w in words if normalize_text(w.text).strip() == "%"]
    if len(percents) != 1 or percents[0].left < word.right - 2:
        return False
    confirmed = []
    for item, target_rows in confirmations:
        for target_info, target_words in target_rows:
            if (target_info.materials != (material,) or target_info.numbers != (value,)
                    or not target_info.explicit_percent or target_info.invalid_evidence
                    or target_info.unresolved_materials):
                continue
            names = [w for w in target_words if find_material_key(w.text) == material]
            numbers = [w for w in target_words
                       if normalize_text(w.text).replace(" ", "").rstrip("%") == str(value)]
            signs = [w for w in target_words if normalize_text(w.text).strip().endswith("%")]
            if (len(names) == len(numbers) == len(signs) == 1
                    and _overlaps(word, names[0]) and _overlaps(word, numbers[0])
                    and numbers[0].left >= names[0].right - 2
                    and abs(numbers[0].center_y - names[0].center_y) <= max(numbers[0].height, names[0].height)
                    and _overlaps(percents[0], signs[0])):
                confirmed.append(item)
                break
    return (len({item.image_variant_key for item in confirmed}) >= 2
            and len({item.source for item in confirmed}) >= 2)


def _literal_name_tokens(text):
    import unicodedata

    return tuple(re.findall(
        r"[가-힣一-龥ぁ-んァ-ンー]|[^\W\d_가-힣一-龥ぁ-んァ-ンー]+|\d+|[^\w\s]",
        unicodedata.normalize('NFKC', text).casefold(),
    ))


def _literal_name_row_words(line, words):
    tokens = _literal_name_tokens(line)
    word_tokens = {w.text: _literal_name_tokens(w.text) for w in words}
    matches = [w for w in words if word_tokens[w.text] and any(tokens[i:i + len(word_tokens[w.text])]
               == word_tokens[w.text] for i in range(len(tokens)))]
    anchors = [w for w in matches if len(w.text.strip()) > 1 and w.text.strip() != '%'
               and sum(other.text == w.text for other in matches)
               <= sum(tokens[i:i + len(word_tokens[w.text])] == word_tokens[w.text]
                      for i in range(len(tokens)))]
    if not anchors or max(w.center_y for w in anchors) - min(w.center_y for w in anchors) > max(w.height for w in anchors):
        return ()
    margin = max(w.height for w in anchors) * 0.35
    top, bottom = min(w.top for w in anchors) - margin, max(w.bottom for w in anchors) + margin
    selected = tuple(w for w in matches if top <= w.center_y <= bottom)
    if (len({w.page for w in selected}) != 1
            or Counter(tokens) != Counter(t for w in selected for t in word_tokens[w.text])):
        return ()
    return selected


def _literal_layout_peer(candidate, candidates):
    for peer in candidates or ():
        if (not peer.layout_used or peer.source != candidate.source
                or peer.image_key != candidate.image_key
                or not candidate.image_variant_key
                or peer.image_variant_key != candidate.image_variant_key
                or peer.image_words != candidate.image_words
                or peer.image_region != candidate.image_region
                or Counter(_literal_name_tokens(peer.text)) != Counter(_literal_name_tokens(candidate.text))
                or Counter(_literal_name_tokens(peer.text)) != Counter(_literal_name_tokens(
                    " ".join(word.text for word in peer.image_words)))):
            continue
        if len(peer.image_region) != 4:
            continue
        return peer, peer.text.splitlines()
    return None, []


def _korean_name_cells(words):
    ordered = sorted(words, key=lambda word: (word.center_x, word.center_y))
    cells = []
    consumed = set()
    boundary = 0
    for index, word in enumerate(ordered):
        token = normalize_text(word.text).replace(' ', '')
        match = re.fullmatch(r'(\d{1,3})%?', token)
        if not match:
            continue
        percent = [word] if token.endswith('%') else []
        end = index + 1
        if not percent and end < len(ordered) and normalize_text(ordered[end].text).strip() == '%':
            percent = [ordered[end]]
            end += 1
        if not percent or not 0 < int(match.group(1)) <= 100:
            return [], set()
        names = ()
        material = None
        for start in range(boundary, index):
            span = tuple(ordered[start:index])
            name = normalize_text(' '.join(w.text for w in span)).replace(' ', '')
            key = find_material_key(name)
            if key and re.fullmatch(r'[가-힣]+', name):
                material, names = key, span
                break
        if material:
            cells.append((material, int(match.group(1)), names, word, tuple(percent)))
            consumed.update(names)
        consumed.add(word)
        consumed.update(percent)
        boundary = end
    return cells, consumed


def _same_region_korean_name_recovery(candidate, alternative, part, candidates):
    """Repair garbled names only with two independent, aligned name/ratio reads."""
    if (part != 'generic' or set(alternative.parts) != {'generic'}
            or not 2 <= len(alternative.parts['generic']) <= 3
            or candidate.conflicting_parts
            or not re.search(r'(?:혼용률|혼용율|소재|조성)', normalize_text(alternative.text))
            or set(candidate.rejected_composition_parts.get(part, ()))
            - {'unpaired_material_rows', 'unresolved_material_token'}):
        return False
    from apps.text.parse_label import build_line_infos, _is_metadata_line

    def read_evidence(item):
        peer, physical = _literal_layout_peer(item, candidates)
        if peer is None:
            return [], []
        infos = build_line_infos(peer.text)
        original = build_line_infos(item.text)
        if any(info.marker_part not in (None, 'generic') or info.invalid_evidence
               or info.unresolved_materials for info in infos + original):
            return [], []
        if any(not _is_metadata_line(info) and re.search(r'[-+−]\s*\d', info.normalized)
               for info in infos + original):
            return [], []
        critical = [info for info in infos if not _is_metadata_line(info)
                    and (info.materials or info.numbers or info.explicit_percent)]
        rows = []
        for info in critical:
            matches = [line for line in physical if _tokens(line) == _tokens(info.raw)]
            if len(matches) != 1:
                return [], []
            words = _literal_name_row_words(matches[0], peer.image_words)
            if not words:
                return [], []
            rows.append(words)
        left, top, right, bottom = peer.image_region
        if any(not (left - 2 <= w.left and w.right <= right + 2
                    and top - 2 <= w.top and w.bottom <= bottom + 2) for row in rows for w in row):
            return [], []
        if (Counter(n for info in original if not _is_metadata_line(info) for n in info.numbers)
                != Counter(n for info in critical for n in info.numbers)
                or Counter(m for info in original if not _is_metadata_line(info) for m in info.materials)
                != Counter(m for info in critical for m in info.materials)):
            return [], []
        return rows, critical

    located = {}
    def evidence(item):
        key = id(item)
        if key not in located:
            located[key] = read_evidence(item)
        return located[key]

    source_rows, source_infos = evidence(candidate)
    target_rows, target_infos = evidence(alternative)
    if len(source_rows) != 1 or len(target_rows) != 1:
        return False
    source_words, target_words = source_rows[0], target_rows[0]
    cells, consumed = _korean_name_cells(target_words)
    if (len(cells) != len(alternative.parts[part])
            or dict((material, value) for material, value, *_ in cells) != alternative.parts[part]
            or Counter(n for info in source_infos for n in info.numbers)
            != Counter(n for info in target_infos for n in info.numbers)
            or not Counter(m for info in target_infos for m in info.materials)
            >= Counter(m for info in source_infos for m in info.materials)
            or _literal_name_tokens(' '.join(w.text for w in source_words)).count('%')
            != _literal_name_tokens(' '.join(w.text for w in target_words)).count('%')
            or not set(tuple(pair) for pair in candidate.paired_material_ratios.get(part, ()))
            <= set((material, value) for material, value, *_ in cells)):
        return False
    header = tuple(w for w in target_words if w not in consumed)
    if not re.fullmatch(r'(?:혼용률|혼용율|소재|조성)[\s:]*',
                        normalize_text(' '.join(w.text for w in sorted(header, key=lambda w: w.center_x)))):
        return False
    # Every repaired material cell needs genuinely different provider inputs.
    for material, value, names, number, percent in cells:
        supporters = set()
        for item in candidates or ():
            if (item.image_key != candidate.image_key or not item.image_variant_key):
                continue
            rows, _ = evidence(item)
            for row in rows:
                other_cells, _ = _korean_name_cells(row)
                for key, ratio, other_names, other_number, other_percent in other_cells:
                    if (key == material and ratio == value and _overlaps(number, other_number)
                            and all(any(_overlaps(w, other) for other in other_names) for w in names)
                            and all(any(_overlaps(w, other) for other in names) for w in other_names)
                            and all(any(_overlaps(w, other) for other in other_percent) for w in percent)):
                        supporters.add((item.image_variant_key, item.source))
        if (len({variant for variant, _ in supporters}) < 2
                or len({source for _, source in supporters}) < 2):
            return False
    ratios = tuple(w for _, _, _, number, percent in cells for w in (number, *percent))
    left, top, right, bottom = alternative.image_region
    if any(not (left - 2 <= w.left and w.right <= right + 2
                and top - 2 <= w.top and w.bottom <= bottom + 2) for w in source_words):
        return False
    forbidden = NEGATING_MODIFIERS | UNPRICED_MATERIALS | {'unknown', '未知繊維', '未知纤维'}
    for _, _, names, *_ in cells:
        damaged = ''.join(w.text for w in sorted(source_words, key=lambda w: w.center_x)
                          if any(_overlaps(w, name) for name in names))
        expected = normalize_text(' '.join(w.text for w in names)).replace(' ', '')
        # Require an ordered fragment of the observed name as well as geometry.
        lengths = [0] * (len(expected) + 1)
        for char in damaged:
            previous = lengths[:]
            for index, target_char in enumerate(expected, 1):
                lengths[index] = previous[index - 1] + 1 if char == target_char else max(previous[index], lengths[index - 1])
        if lengths[-1] < max(1, math.ceil(len(expected) * 0.4)):
            return False
    # A split, correctly registered name cannot be changed to another fiber.
    ordered = sorted(source_words, key=lambda w: (w.center_x, w.center_y))
    for index in range(len(ordered)):
        for end in range(index + 1, len(ordered) + 1):
            span = ordered[index:end]
            joined = normalize_text(' '.join(w.text for w in span)).replace(' ', '')
            known = find_material_key(joined)
            if joined in forbidden:
                return False
            in_name_cell = any(all(any(_overlaps(w, name) for name in names) for w in span)
                               for _, _, names, *_ in cells)
            if known and in_name_cell and not any(material == known and all(any(_overlaps(w, name) for name in names) for w in span)
                                                 for material, _, names, *_ in cells):
                return False
    for word in source_words:
        token = normalize_text(word.text).replace(' ', '')
        if token in forbidden:
            return False
        if re.fullmatch(r'\d{1,3}%?|%', token):
            if not any(token.rstrip('%') == normalize_text(other.text).replace(' ', '').rstrip('%')
                       and _overlaps(word, other) for other in ratios):
                return False
            continue
        if token in {':', ',', ';'}:
            if not any(normalize_text(other.text).strip() == token and _overlaps(word, other)
                       for other in target_words):
                return False
            continue
        if not re.fullmatch(r'[가-힣]+', token):
            return False
        known = find_material_key(token)
        overlaps = [material for material, _, names, *_ in cells if any(_overlaps(word, name) for name in names)]
        if len(set(overlaps)) > 1 or (known and overlaps != [known]):
            return False
        if not overlaps and not any(_overlaps(word, other) for other in header):
            return False
    # A missing material box cannot be invented from percentages alone.
    return all(any(_overlaps(name, word) and re.fullmatch(r'[가-힣]+', normalize_text(word.text).replace(' ', ''))
                   for word in source_words) for _, _, names, *_ in cells for name in names)


def _same_response_translated_layout_recovery(candidate, alternative, part):
    """Only a token-preserving layout of one validated tagged 100% copy."""
    if (not candidate.layout_used or alternative.layout_used
            or candidate.source != alternative.source
            or candidate.image_variant_key != alternative.image_variant_key
            or candidate.image_words != alternative.image_words
            or candidate.image_region != alternative.image_region
            or 'multilingual_translation_rows' not in alternative.parser_warnings
            or len(alternative.parts) != 1 or part not in alternative.parts
            or len(alternative.parts[part]) != 1
            or tuple(alternative.parts[part].values()) != (100,)):
        return False
    from apps.text.multilingual_rows import _TAG
    from apps.text.material_extraction import extract_materials

    if len(list(_TAG.finditer(normalize_text(alternative.text)))) < 2:
        return False
    literal = Counter(_tokens(alternative.text))
    if (literal != Counter(_tokens(candidate.text))
            or literal != Counter(_tokens(' '.join(w.text for w in candidate.image_words)))):
        return False
    if set(extract_materials(candidate.text)) - set(alternative.parts[part]):
        return False
    return True


def _same_region_translation_care_recovery(candidate, alternative, part):
    """Discard only a located care number, retaining all fiber/ratio cells."""
    if ('multilingual_translation_rows' not in alternative.parser_warnings
            or len(alternative.parts) != 1 or part not in alternative.parts):
        return False
    from apps.text.parse_label import build_line_infos, _is_metadata_line, _mentions_care

    infos = [i for i in build_line_infos(candidate.text) if i.part == part and not _is_metadata_line(i)]
    target = build_line_infos(alternative.text)
    if any(i.invalid_evidence or i.unresolved_materials for i in infos):
        return False
    target_cells = [i for i in target if i.part == part and i.materials and i.numbers
                    and not _is_metadata_line(i)]
    target_pairs = Counter((m, float(n)) for i in target_cells for m, n in zip(i.materials, i.numbers))
    if (any(not i.explicit_percent or i.invalid_evidence or i.unresolved_materials for i in target_cells)
            or target_pairs != Counter(alternative.parts[part].items())):
        return False
    cells = [i for i in infos if i.materials and i.numbers]
    pairs = Counter((m, float(n)) for i in cells for m, n in zip(i.materials, i.numbers))
    if (not cells or any(len(i.materials) != len(i.numbers) or not i.explicit_percent for i in cells)
            or pairs != Counter(alternative.parts[part].items())):
        return False
    extra = [i for i in infos if i.numbers and not i.materials]
    if not extra or any(i.explicit_percent or not re.fullmatch(
            r'[$|☆○△□×\s]*(?:30|40|50|60|70|95)[|☆○△□×\s]*', i.normalized) for i in extra):
        return False
    metadata_words = []
    for index, info in enumerate(target):
        if (info.part == part and _is_metadata_line(info)
                and re.fullmatch(r'\|?\s*(?:30|40|50|60|70|95)\s*\|?', info.normalized)
                and any(_mentions_care(f.normalized) and not f.materials and not f.explicit_percent
                        for f in target[index+1:index+4] if f.part == part)):
            metadata_words.extend(_row_words(info.raw, alternative.image_words))
    if not metadata_words:
        return False
    left, region_top, right, bottom = alternative.image_region
    for info in extra:
        words = _row_words(info.raw, candidate.image_words)
        if any(not (left-2 <= w.left and w.right <= right+2 and region_top-2 <= w.top
                    and w.bottom <= bottom+2) for w in words):
            return False
        digits = [w for w in words if re.fullmatch(r'\$?(?:30|40|50|60|70|95)', normalize_text(w.text).strip())]
        if (not digits or Counter(t for w in words for t in _tokens(w.text)) != Counter(_tokens(info.raw))
                or not all(any(_overlaps(w, other)
                               and normalize_text(w.text).lstrip('$') == normalize_text(other.text)
                               for other in metadata_words) for w in digits)):
            return False
    top = min(w.top for w in metadata_words)
    left, region_top, right, bottom = alternative.image_region
    for info in infos:
        if not info.materials:
            continue
        words = _row_words(info.raw, candidate.image_words)
        if (not words or Counter(_tokens(info.raw)) != Counter(t for w in words for t in _tokens(w.text))
                or any(not (left-2 <= w.left and w.right <= right+2 and region_top-2 <= w.top
                            and w.bottom <= bottom+2) for w in words)):
            return False
        if info.numbers:
            # Every primary name and percentage has literal overlap, so a
            # swapped row or another image cannot supply the missing cells.
            if not _aligned_reading(words, alternative.image_words):
                return False
        else:
            # A repeated, ratio-free translation must be above the wash cell
            # and read as the same known fiber at the same original position.
            if (set(info.materials) - set(alternative.parts[part])
                    or any(w.bottom > top for w in words)
                    or not _aligned_reading(words, alternative.image_words)):
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
    if _same_response_translated_layout_recovery(candidate, alternative, part):
        return True
    if _same_region_translation_care_recovery(candidate, alternative, part):
        return True
    if _same_response_metadata_recovery(candidate, alternative, part):
        return True
    if _same_response_ratio_order_recovery(candidate, alternative, part, candidates):
        return True
    if _same_region_korean_name_recovery(candidate, alternative, part, candidates):
        return True
    target_part = part
    if part == "generic" and part not in alternative.parts:
        if len(alternative.parts) != 1:
            return False
        target_part = next(iter(alternative.parts))
    if target_part not in alternative.parts:
        return False
    rows = _located_evidence_rows(candidate, part, candidates)
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
    # A period present in the source row must have its own located evidence;
    # a dot in another physical row cannot disappear during row selection.
    if any(_tokens(info.raw).count(".") != sum(_tokens(w.text).count(".") for w in words)
           for info, words in rows):
        return False
    source_words = tuple(dict.fromkeys(word for _info, words in rows for word in words))
    target_words = tuple(dict.fromkeys(word for _info, words in target_rows for word in words))
    supporters = []
    ratio_confirmations = []
    for item in candidates or ():
        if (item.image_key != candidate.image_key or not item.image_variant_key
                or item.parser_status != "success"
                or item.parts.get(target_part) != alternative.parts[target_part]):
            continue
        other_rows = _evidence_rows(item, target_part)
        other_words = tuple(dict.fromkeys(word for _info, words in other_rows for word in words))
        if other_words and _aligned_reading(target_words, other_words) and _aligned_reading(other_words, target_words):
            supporters.append(item)
        # A different row may omit its percent sign while retaining the same
        # aligned number. The repaired row still needs an explicit percent in
        # each independent response; this never discards source evidence.
        target_values = tuple(w for w in target_words if normalize_text(w.text).strip() != "%")
        other_values = tuple(w for w in other_words if normalize_text(w.text).strip() != "%")
        if (other_values and _aligned_reading(target_values, other_values)
                and _aligned_reading(other_values, target_values)):
            ratio_confirmations.append((item, other_rows))
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
    ratio_glyph_cells = set()
    for word in source_words:
        token = normalize_text(word.text).replace(" ", "")
        if token in forbidden:
            return False
        if token in {":", ",", ";", "/", "|", "(", ")", "[", "]"}:
            continue
        if token == "." and _trailing_percent_period_reread(word, rows, target_rows):
            continue
        nearby = [target for target in target_words if _overlaps(word, target)]
        if not nearby:
            return False
        if any(token == normalize_text(target.text).replace(" ", "") for target in nearby):
            continue
        if _fused_decimal_reread(word, token, rows, alternative.parts[target_part], ratio_confirmations):
            numeric_changes += 1
            if numeric_changes > 1 or percent_glyph_changes or ratio_glyph_cells:
                return False
            continue
        ratio_cell = _ratio_column_glyph_reread(word, token, rows, target_rows, alternative.parts[target_part])
        if ratio_cell:
            ratio_glyph_cells.add(ratio_cell)
            if len(ratio_glyph_cells) > 1 or numeric_changes or percent_glyph_changes:
                return False
            continue
        if _percent_glyph_reread(word, token, rows, target_rows, alternative.parts[target_part]):
            percent_glyph_changes += 1
            if numeric_changes or ratio_glyph_cells:
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
                if numeric_changes > 1 or percent_glyph_changes or ratio_glyph_cells:
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
