import re
from collections import defaultdict
from dataclasses import dataclass

from apps.text.rules import CARE_RULES, MATERIAL_ALIASES, MATERIAL_KOREAN, OCR_CORRECTIONS


PART_PATTERNS = {
    "outer": ["\uac89\uac10", "\uac89 \uac10", "\uc678\ud53c", "\ud45c\uba74", "\ubcf8\uccb4", "\ubab8\ud310", "\ubcf8\ud53c", "shell", "outshell", "outer", "face", "main fabric", "\u672c\u4f53", "\u9762\u6599"],
    "lining": ["\uc548\uac10", "\uc548 \uac10", "\ub0b4\ud53c", "lining", "lning", "uning", "un ing", "\u88cf\u5730", "\u91cc\u6599", "\u88e1\u6599"],
    "filling": ["\ucda9\uc804\uc7ac", "\ucda9\uc804\uc81c", "\ucda9\uc804", "\uc19c", "filling", "fill", "\u4e2d\u308f\u305f", "\u586b\u5145"],
    "pocket": ["\uc8fc\uba38\ub2c8\uac10", "\uc8fc\uba38\ub2c8", "pocket"],
    "rib": ["\ub9bd", "\ub9ac\ube0c", "rib"],
    "sleeve": ["\uc18c\ub9e4", "sleeve"],
    "color_block": ["\ubc30\uc0c9", "contrast", "\u914d\u8272"],
}

NOISE_WORDS = {
    "\uc81c\ud488", "\uc81c\ud488\uba85", "\uc81c\uc870", "\uc81c\uc870\ub144\uc6d4", "\uc81c\uc870\uad6d", "\uc218\uc785\uc790", "\ud310\ub9e4\uc790", "\ud488\ubc88", "\ud638\uce6d",
    "\uc2e0\uccb4\uce58\uc218", "\uac00\uc2b4\ub458\ub808", "\ud5c8\ub9ac\ub458\ub808", "\uac80\uc0ac", "\ud544", "\uc8fc\uc758", "\ucde8\uae09\uc8fc\uc758", "\uc138\ud0c1",
    "\uc2ec\uc9c0", "\ubcf4\uac15\uc7ac", "\uc0c1\ud45c", "\ubb34\ub2ac", "\ubc34\ub4dc", "\ub808\uc774\uc2a4", "\uc790\uc218", "\uc7a5\uc2dd", "\uc81c\uc678",
}


@dataclass
class LineInfo:
    index: int
    raw: str
    normalized: str
    part: str
    materials: list[str]
    numbers: list[float]


def normalize_text(text: str) -> str:
    if not text:
        return ""
    normalized = text.lower()
    normalized = normalized.replace("\uff1a", ":").replace("\uff05", "%")
    normalized = normalized.replace("\u00b7", " ").replace("/", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    for wrong, correct in OCR_CORRECTIONS.items():
        normalized = re.sub(rf"\b{re.escape(wrong)}\b", correct, normalized)
    return normalized


def clean_ocr_preview(text: str, max_len: int = 220) -> str:
    if not text:
        return ""
    preview = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    return preview if len(preview) <= max_len else preview[:max_len] + "..."


def find_material_key(word: str) -> str | None:
    token = word.lower().strip(" .,:;/()[]{}<>|+-_=*\"'")
    token = OCR_CORRECTIONS.get(token, token)

    if not token:
        return None
    if token in NOISE_WORDS:
        return None
    if len(token) < 2 and token.isascii():
        return None

    for material_key, aliases in MATERIAL_ALIASES.items():
        for alias in aliases:
            alias = alias.lower().strip()
            if not alias:
                continue
            if token == alias:
                return material_key
            if alias.isascii() and len(alias) >= 4 and alias in token:
                return material_key
            if not alias.isascii() and len(alias) >= 2 and alias in token and len(token) <= 8:
                return material_key
            if alias in {"綿", "棉", "毛", "麻", "絹"} and alias in token and len(token) <= 8:
                return material_key
    return None


def detect_part(line: str, current_part: str) -> str:
    for part, aliases in PART_PATTERNS.items():
        if any(alias.lower() in line for alias in aliases):
            return part
    return current_part


def extract_numbers(line: str, allow_plain_numbers: bool) -> list[float]:
    nums = []
    for match in re.finditer(r"(?<![a-z0-9])([0-9]{1,3})(?:\s*%)", line):
        value = float(match.group(1))
        if 0 < value <= 100:
            nums.append(value)

    if nums:
        return nums

    if not allow_plain_numbers:
        return []

    for match in re.finditer(r"(?<![a-z0-9])([0-9]{1,3})(?!\s*(?:cm|mm|kg|\ud638|\ub144|\uc6d4|\uc77c|\ubc88|[a-z0-9]))", line):
        value = float(match.group(1))
        if 0 < value <= 100:
            nums.append(value)

    # OCR often turns 100% into 10086, 10090, 10000, or cotton 2000.
    if not nums:
        if re.search(r"(?<![0-9])100[0-9]{2}(?![0-9])", line):
            nums.append(100.0)
        elif re.search(r"(?<![0-9])2000(?![0-9])", line):
            nums.append(100.0)
    return nums


def extract_materials(line: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z]+|[\uac00-\ud7a3]+|[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]+", line)
    found = []
    for token in tokens:
        material = find_material_key(token)
        if material:
            found.append(material)
    return list(dict.fromkeys(found))


def build_line_infos(text: str) -> list[LineInfo]:
    infos = []
    current_part = "generic"
    prepared = text or ""
    split_markers = [
        "shell", "outshell", "lining", "lning", "uning", "outer",
        "\uac89\uac10", "\uc548\uac10", "\uc678\ud53c", "\ub0b4\ud53c", "\ucda9\uc804\uc7ac", "\ucda9\uc804\uc81c",
        "\u672c\u4f53", "\u9762\u6599", "\u91cc\u6599", "\u88e1\u6599",
    ]
    for marker in split_markers:
        prepared = re.sub(rf"(?i)(?<!^)\b({re.escape(marker)})\b", r"\n\1", prepared)
    raw_lines = prepared.replace("\r", "\n").split("\n")

    for idx, raw in enumerate(raw_lines):
        normalized = normalize_text(raw)
        if not normalized:
            continue
        current_part = detect_part(normalized, current_part)
        materials = extract_materials(normalized)
        allow_plain = bool(materials) or current_part != "generic"
        numbers = extract_numbers(normalized, allow_plain_numbers=allow_plain)
        infos.append(LineInfo(idx, raw.strip(), normalized, current_part, materials, numbers))
    return infos


def _as_pair_dict(materials: list[str], numbers: list[float]) -> dict[str, float]:
    pair = defaultdict(float)
    if len(materials) == len(numbers):
        for material, number in zip(materials, numbers):
            pair[material] += number
    elif len(materials) == 1 and numbers:
        pair[materials[0]] += numbers[0]
    elif len(numbers) > 1:
        for material, number in zip(materials, numbers):
            pair[material] += number
    return dict(pair)


def _is_duplicate_composition(existing: dict[str, float], candidate: dict[str, float]) -> bool:
    if not existing or not candidate:
        return False
    if set(existing) != set(candidate):
        return False
    existing_total = sum(existing.values())
    candidate_total = sum(candidate.values())
    if not (90 <= existing_total <= 110 and 90 <= candidate_total <= 110):
        return False
    for key in candidate:
        existing_ratio = existing[key] * 100 / existing_total
        candidate_ratio = candidate[key] * 100 / candidate_total
        if abs(existing_ratio - candidate_ratio) > 15:
            return False
    return True


def add_pairs(result: dict[str, defaultdict[str, float]], part: str, materials: list[str], numbers: list[float]) -> bool:
    if not materials or not numbers:
        return False

    pair = _as_pair_dict(materials, numbers)
    if not pair:
        return False
    if any(value <= 0 or value > 100 for value in pair.values()):
        return False

    if _is_duplicate_composition(dict(result[part]), pair):
        return True

    for material, number in pair.items():
        result[part][material] += number
    return True


def parse_parts(text: str) -> dict[str, dict[str, float]]:
    infos = build_line_infos(text)
    result: dict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))

    used = set()
    for pos, info in enumerate(infos):
        if add_pairs(result, info.part, info.materials, info.numbers):
            used.add(pos)

    # Column layout: material names can be stacked first, followed by stacked ratios.
    # Example: "polyester / polyurethane / 94% / 6%".
    for pos, info in enumerate(infos):
        if pos in used or not info.materials or info.numbers:
            continue
        material_block = []
        material_positions = []
        cursor = pos
        while cursor < len(infos):
            cur = infos[cursor]
            if cursor in used or cur.part != info.part or cur.numbers or not cur.materials:
                break
            material_block.extend(cur.materials)
            material_positions.append(cursor)
            cursor += 1
        number_block = []
        number_positions = []
        while cursor < len(infos):
            cur = infos[cursor]
            if cursor in used or cur.part != info.part or cur.materials or not cur.numbers:
                break
            number_block.extend(cur.numbers)
            number_positions.append(cursor)
            cursor += 1
        if len(material_block) > 1 and len(material_block) == len(number_block):
            if add_pairs(result, info.part, material_block, number_block):
                used.update(material_positions)
                used.update(number_positions)

    for pos, info in enumerate(infos):
        if pos in used or not info.materials:
            continue
        near_numbers = []
        for next_pos in range(pos + 1, min(pos + 4, len(infos))):
            nxt = infos[next_pos]
            if nxt.materials and nxt.part != info.part:
                break
            if nxt.numbers:
                near_numbers.extend(nxt.numbers)
                used.add(next_pos)
                if len(near_numbers) >= len(info.materials):
                    break
        if add_pairs(result, info.part, info.materials, near_numbers):
            used.add(pos)

    for pos, info in enumerate(infos):
        if pos in used or not info.numbers:
            continue
        near_materials = []
        for next_pos in range(pos + 1, min(pos + 4, len(infos))):
            nxt = infos[next_pos]
            if nxt.numbers and nxt.part != info.part:
                break
            if nxt.materials:
                near_materials.extend(nxt.materials)
                used.add(next_pos)
                if len(near_materials) >= len(info.numbers):
                    break
        if add_pairs(result, info.part, near_materials, info.numbers):
            used.add(pos)

    return {part: dict(values) for part, values in result.items() if values}


def normalize_percentages(materials: dict[str, float]) -> dict[str, float | int]:
    if not materials:
        return {}

    total = sum(float(value) for value in materials.values())
    normalized_values = dict(materials)

    if len(normalized_values) == 1 and 50 <= total <= 100:
        only_key = next(iter(normalized_values))
        normalized_values[only_key] = 100.0
    elif len(normalized_values) == 2 and total < 30:
        keys = list(normalized_values.keys())
        values = [float(normalized_values[key]) for key in keys]
        if 0 < values[1] <= 15:
            normalized_values[keys[0]] = 100.0 - values[1]
        elif 0 < values[0] <= 15:
            normalized_values[keys[1]] = 100.0 - values[0]
    elif 95 <= total <= 105 or total > 100:
        normalized_values = {key: float(value) * 100 / total for key, value in normalized_values.items()}

    normalized = {}
    for key, value in normalized_values.items():
        if value <= 0:
            continue
        rounded = round(float(value), 1)
        normalized[key] = int(rounded) if float(rounded).is_integer() else rounded
    return normalized


def choose_representative_materials(parts: dict[str, dict[str, float]]) -> tuple[str, dict[str, float | int]]:
    if not parts:
        return "", {}

    priority = ["outer", "generic", "lining", "filling", "pocket", "rib", "sleeve", "color_block"]
    for part in priority:
        if part in parts:
            normalized = normalize_percentages(parts[part])
            if normalized:
                return part, normalized

    best_part = min(parts, key=lambda name: abs(sum(parts[name].values()) - 100))
    return best_part, normalize_percentages(parts[best_part])



def infer_materials_from_context(text: str) -> tuple[str, dict[str, float | int]]:
    text_n = normalize_text(text)
    if not text_n:
        return "", {}

    found_materials = []
    for line in text_n.split("\n"):
        found_materials.extend(extract_materials(line))
    found_materials = list(dict.fromkeys(found_materials))

    if len(found_materials) == 1:
        if re.search(r"(?<![0-9])100\s*%|single|only|cotona", text_n):
            return "inferred", {found_materials[0]: 100}

    has_composition_context = any(
        keyword in text_n
        for keyword in ["섬유", "혼용", "품질표시", "품질 표시", "composition", "fabric", "shell"]
    )
    if has_composition_context and re.search(r"(?<![0-9])100\s*%(?![0-9])", text_n):
        return "inferred", {"cotton": 100}

    return "", {}

def infer_missing_cotton_polyester_pair(text: str) -> tuple[str, dict[str, float | int]]:
    text_n = normalize_text(text)
    if not text_n:
        return "", {}

    polyester_pattern = r"(?:폴리에스터|플리에스터|리메스타|polyester|poliester|polyster)"
    has_composition_context = any(
        keyword in text_n
        for keyword in ["섬유", "혼용", "품질표시", "품질 표시", "composition", "fabric", "shell"]
    )
    has_material_context = bool(re.search(polyester_pattern, text_n)) or "면" in text_n or bool(re.search(r"\bcotton\b", text_n))
    if not (has_composition_context or has_material_context):
        return "", {}

    pattern = rf"(?<![0-9])([1-9][0-9]?)\s*%\s*.{{0,18}}?{polyester_pattern}\s*.{{0,10}}?([1-9][0-9]?)\s*%?"
    for match in re.finditer(pattern, text_n):
        first = float(match.group(1))
        second = float(match.group(2))
        if 95 <= first + second <= 105 and first >= second:
            return "inferred", {
                "cotton": int(first) if first.is_integer() else first,
                "polyester": int(second) if second.is_integer() else second,
            }

    cotton_pattern = r"(?:면|cotton|coton|algodon|algodao|pamuk|cotone|baumwolle|katoen|bawe|kapas)"
    pattern = rf"(?<![0-9])([1-9][0-9]?)\s*%\s*.{{0,10}}?{cotton_pattern}\s*.{{0,10}}?([1-9][0-9]?)\s*%?"
    for match in re.finditer(pattern, text_n):
        first = float(match.group(1))
        second = float(match.group(2))
        if 95 <= first + second <= 105 and first >= second:
            return "inferred", {
                "cotton": int(first) if first.is_integer() else first,
                "polyester": int(second) if second.is_integer() else second,
            }

    return "", {}
def parse_materials(text: str) -> dict[str, float | int]:
    _, materials = choose_representative_materials(parse_parts(text))
    inferred_part, inferred_materials = infer_missing_cotton_polyester_pair(text)
    if inferred_materials and (not materials or set(materials) in ({"polyester"}, {"cotton"})):
        return inferred_materials
    return materials


def format_materials_korean(material_dict: dict[str, float | int]) -> str:
    if not material_dict:
        return ""

    parts = []
    for material, percent in sorted(material_dict.items(), key=lambda item: (-float(item[1]), item[0])):
        korean = MATERIAL_KOREAN.get(material, material)
        percent_text = str(int(percent)) if float(percent).is_integer() else f"{float(percent):.1f}"
        parts.append(f"{korean} {percent_text}%")
    return ", ".join(parts)


def parse_care(text: str) -> str:
    text_n = normalize_text(text)
    found = []

    for korean, aliases in CARE_RULES.items():
        if any(alias.lower() in text_n for alias in aliases):
            found.append(korean)

    return "; ".join(dict.fromkeys(found))


def estimate_ocr_confidence(text: str, materials: dict[str, float | int]) -> str:
    if not text or not materials:
        return "low"

    total = sum(float(value) for value in materials.values())
    if 95 <= total <= 105 and len(clean_ocr_preview(text)) >= 15:
        return "high"
    return "medium"


def estimate_expected_life_months(materials: dict[str, float | int]) -> int | None:
    if not materials:
        return None

    base_life = {
        "cotton": 36,
        "polyester": 48,
        "nylon": 48,
        "wool": 60,
        "linen": 48,
        "silk": 30,
        "rayon": 30,
        "viscose": 30,
        "acrylic": 36,
        "spandex": 24,
        "polyurethane": 24,
        "modal": 36,
        "lyocell": 42,
        "cashmere": 60,
        "leather": 72,
        "down": 42,
        "feather": 36,
    }

    total = sum(float(value) for value in materials.values())
    if total <= 0:
        return None

    weighted = 0.0
    for material, percent in materials.items():
        weighted += base_life.get(material, 36) * (float(percent) / total)
    return int(round(weighted))


def failed_response(raw_text: str = "") -> dict:
    return {
        "status": "failed",
        "message": "\uc18c\uc7ac \ud63c\uc6a9\ub960\uc744 \uc778\uc2dd\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.",
        "materials": {},
        "materials_korean": "",
        "raw_ocr_preview": clean_ocr_preview(raw_text),
    }


def parse_label(text: str) -> dict:
    parts_raw = parse_parts(text)
    selected_part, materials = choose_representative_materials(parts_raw)
    inferred_part, inferred_materials = infer_missing_cotton_polyester_pair(text)
    if inferred_materials and (not materials or set(materials) in ({"polyester"}, {"cotton"})):
        selected_part, materials = inferred_part, inferred_materials
    if not materials:
        selected_part, materials = infer_materials_from_context(text)
    if not materials:
        return failed_response(text)

    parts = {part: normalize_percentages(values) for part, values in parts_raw.items()}

    return {
        "status": "success",
        "materials": materials,
        "materials_korean": format_materials_korean(materials),
        "raw_ocr_preview": clean_ocr_preview(text),
        "confidence": {
            "ocr": estimate_ocr_confidence(text, materials),
        },
        "care_text": parse_care(text),
        "expected_life_months": estimate_expected_life_months(materials),
        "selected_part": selected_part,
        "parts": parts,
    }
