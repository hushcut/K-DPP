import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from apps.text.rules import CARE_RULES, MATERIAL_ALIASES, MATERIAL_KOREAN, OCR_CORRECTIONS


PART_PATTERNS = {
    "outer": ["\uac89\uac10", "\uac89 \uac10", "\uc678\ud53c", "\ud45c\uba74", "\ubcf8\uccb4", "\ubab8\ud310", "\ubcf8\ud53c", "shell", "outshell", "outer", "face", "main fabric", "\u672c\u4f53", "\u9762\u6599", "表地"],
    "lining": ["\uc548\uac10", "\uc548 \uac10", "\ub0b4\ud53c", "lining", "lning", "uning", "un ing", "\u88cf\u5730", "\u91cc\u6599", "\u88e1\u6599"],
    "filling": ["\ucda9\uc804\uc7ac", "\ucda9\uc804\uc81c", "\ucda9\uc804", "\uc19c", "filling", "fill", "\u4e2d\u308f\u305f", "\u586b\u5145"],
    "pocket": ["\uc8fc\uba38\ub2c8\uac10", "\uc8fc\uba38\ub2c8", "pocket"],
    "rib": ["\ub9bd", "\ub9ac\ube0c", "rib", "リブ", "螺纹"],
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
    numbers: list[Decimal]
    invalid: bool = False


def normalize_text(text: str) -> str:
    if not text:
        return ""
    # OCR can return full-width digits/letters and half-width Katakana.
    normalized = unicodedata.normalize("NFKC", text).lower()
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
    token = unicodedata.normalize("NFKC", word).lower().strip(" .,:;/()[]{}<>|+-_=*\"'")
    token = OCR_CORRECTIONS.get(token, token)

    if not token:
        return None
    if token in NOISE_WORDS:
        return None
    # Imitation/style descriptions do not establish fiber composition.
    if token.startswith("仿") or token.endswith(("風", "調")):
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


# Capture the whole numeric token, including malformed decimals and signs.
# Never recover a valid-looking suffix from 1000%, -5%, or 92..5%.
NUMBER_CANDIDATE = re.compile(r"[+-]?(?:[0-9][0-9.,]*|[.,][0-9][0-9.,]*)(?:\s*%)?")
NUMBER_VALUE = re.compile(r"(?:[0-9]+(?:[.,][0-9]+)?|[.,][0-9]+)")
NON_COMPOSITION = re.compile(
    r"\b(?:size|style|model|sku|lot|item|date|price|wash|iron|dry|bleach|rn|ca|made)\b"
    r"|사이즈|치수|품번|호칭|제조|세탁|가슴둘레|허리둘레|身長|身丈|尺码|尺寸"
)
MEASUREMENT_UNIT = re.compile(
    r"\s*(?:°|℃|℉|\b(?:g|kg|mg|lb|lbs|oz|cm|mm|m|c|f)\b|호|년|월|일|번|원|円|元|도)"
)
INEXACT_SIGN = "+-−±∓‐‑‒–—<>≤≥≦≧~≈≃∼"
MATERIAL_WORD = re.compile(r"[a-zA-Z]+|[\uac00-\ud7a3]+|[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]+")
LABEL_CONTEXT_WORDS = {
    "fiber", "fibre", "fibers", "fibres", "content", "composition", "fabric", "material", "materials",
    "섬유", "혼용률", "혼용율", "섬유혼용률", "섬유혼용율", "소재", "함량", "조성",
    "組成", "組成表示", "纤维", "成分", "纤维成分",
}
LABEL_CONTEXT_WORDS.update(
    token for aliases in PART_PATTERNS.values() for alias in aliases
    for token in MATERIAL_WORD.findall(alias.lower())
)


def _read_numbers(line: str, allow_plain_numbers: bool) -> tuple[list[Decimal], bool]:
    numbers = []
    invalid = False
    consumed_percent_signs = 0
    for match in NUMBER_CANDIDATE.finditer(line):
        token = match.group().strip()
        has_percent = token.endswith("%")
        consumed_percent_signs += int(has_percent)
        if not has_percent and not allow_plain_numbers:
            continue
        value_text = token.removesuffix("%").strip()
        # Units, exponents and dates are not fiber ratios. Numeric tokens on
        # metadata-only lines are filtered separately in build_line_infos.
        suffix = line[match.end():]
        prefix = line[:match.start()]
        preceding = prefix.rstrip()
        if (not NUMBER_VALUE.fullmatch(value_text)
                or re.match(r"[0-9.,%]", suffix)
                or (not has_percent and re.match(r"[a-z]", suffix))
                or re.match(r"\s*%", suffix)
                or MEASUREMENT_UNIT.match(suffix)
                or (prefix and prefix[-1] in "0123456789.,")
                or (preceding and preceding[-1] in INEXACT_SIGN)
                or (suffix.strip() and suffix.strip()[0] in "±∓<>≤≥~≈≃∼")):
            invalid = True
            continue
        try:
            value = Decimal(value_text.replace(",", "."))
        except InvalidOperation:
            invalid = True
            continue
        if not value.is_finite() or not 0 < value <= 100:
            invalid = True
            continue
        numbers.append(value)
    return numbers, invalid or line.count("%") != consumed_percent_signs


def extract_numbers(line: str, allow_plain_numbers: bool) -> list[Decimal]:
    numbers, invalid = _read_numbers(line, allow_plain_numbers)
    return [] if invalid else numbers


def extract_materials(line: str) -> list[str]:
    tokens = MATERIAL_WORD.findall(line)
    found = []
    for token in tokens:
        material = find_material_key(token)
        if material:
            found.append(material)
    return found


def build_line_infos(text: str) -> list[LineInfo]:
    infos = []
    current_part = "generic"
    prepared = unicodedata.normalize("NFKC", text or "")
    split_markers = [
        "shell", "outshell", "lining", "lning", "uning", "outer",
        "\uac89\uac10", "\uc548\uac10", "\uc678\ud53c", "\ub0b4\ud53c", "\ucda9\uc804\uc7ac", "\ucda9\uc804\uc81c",
        "\u672c\u4f53", "\u9762\u6599", "\u91cc\u6599", "\u88e1\u6599",
        "表地", "裏地", "リブ", "螺纹",
    ]
    cjk_markers = [marker for marker in split_markers if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", marker)]
    # Keep an OCR-reordered leading ratio with its part, e.g. 95%面料棉5%氨纶.
    # Restrict this to a ratio-only line prefix so completed parts stay separate.
    cjk_pattern = "|".join(re.escape(marker) for marker in sorted(cjk_markers, key=len, reverse=True))
    prepared = re.sub(
        rf"(?m)^([ \t]*(?:[0-9]+(?:[.,][0-9]+)?|[.,][0-9]+)[ \t]*%[ \t]*)({cjk_pattern})",
        r"\2\1",
        prepared,
    )
    for marker in split_markers:
        # Japanese/Chinese headers may touch the material name (e.g. 表地綿).
        # Unicode word boundaries would miss both the header and the next part.
        if marker in cjk_markers:
            prepared = re.sub(rf"({re.escape(marker)})", r"\n\1\n", prepared)
        else:
            pattern = rf"(?i)(?<!^)\b({re.escape(marker)})\b"
            prepared = re.sub(pattern, r"\n\1", prepared)
    raw_lines = prepared.replace("\r", "\n").split("\n")

    for idx, raw in enumerate(raw_lines):
        normalized = normalize_text(raw)
        if not normalized:
            continue
        current_part = detect_part(normalized, current_part)
        materials = extract_materials(normalized)
        # Bare numbers are usable only next to named fibers or in a numeric
        # column. A size/year elsewhere on a label must not become a percentage.
        numeric_column = bool(re.fullmatch(r"[0-9.,%+\-\s]+", normalized))
        allow_plain = bool(materials) or numeric_column
        numbers, invalid = _read_numbers(normalized, allow_plain_numbers=allow_plain)
        if NON_COMPOSITION.search(normalized):
            numbers = []
            invalid = bool(materials)
        elif numbers or invalid:
            # A missing/unknown fiber name must not shift another fiber's ratio
            # merely because the overall number and recognized-name counts match.
            invalid = invalid or any(
                token not in LABEL_CONTEXT_WORDS and find_material_key(token) is None
                for token in MATERIAL_WORD.findall(normalized)
            )
        infos.append(LineInfo(idx, raw.strip(), normalized, current_part, materials, numbers, invalid))
    return infos


def parse_parts(text: str) -> dict[str, dict[str, Decimal]]:
    """Read explicit, complete compositions without guessing missing evidence.

    Pair only the same line or adjacent single-direction material/ratio columns
    within one part. Each completed 100% block must agree with any repeated
    translation. Empty values preserve a mentioned but invalid part so it cannot
    silently be replaced by a lower-priority lining or filling.
    """
    infos = build_line_infos(text)
    mentioned = {
        info.part for info in infos
        if info.part != "generic" or info.materials or info.numbers or info.invalid
    }
    partial = {part: defaultdict(Decimal) for part in mentioned}
    completed = {}
    invalid_parts = set()

    def add_explicit_pairs(part, materials, numbers):
        if not materials or len(materials) != len(numbers):
            invalid_parts.add(part)
            return
        for material, number in zip(materials, numbers):
            partial[part][material] += number
            total = sum(partial[part].values(), Decimal(0))
            if total > 100:
                invalid_parts.add(part)
            elif total == 100:
                composition = dict(partial[part])
                if part in completed and completed[part] != composition:
                    invalid_parts.add(part)
                else:
                    completed[part] = composition
                partial[part].clear()

    pos = 0
    while pos < len(infos):
        info = infos[pos]
        if info.invalid:
            invalid_parts.add(info.part)
            pos += 1
            continue
        if info.materials and info.numbers:
            add_explicit_pairs(info.part, info.materials, info.numbers)
            pos += 1
            continue
        if not info.materials and not info.numbers:
            pos += 1
            continue

        # Material-first and ratio-first columns are symmetric. A header,
        # unrelated line, already paired row or part boundary stops the block.
        materials_first = bool(info.materials)
        materials, numbers = [], []
        cursor = pos
        for first_block in (True, False):
            want_materials = materials_first if first_block else not materials_first
            while cursor < len(infos):
                current = infos[cursor]
                if current.part != info.part or current.invalid:
                    break
                if want_materials:
                    if not current.materials or current.numbers:
                        break
                    materials.extend(current.materials)
                else:
                    if not current.numbers or current.materials:
                        break
                    numbers.extend(current.numbers)
                cursor += 1
        add_explicit_pairs(info.part, materials, numbers)
        pos = cursor

    return {
        part: completed.get(part, {}) if part not in invalid_parts and not partial[part] else {}
        for part in mentioned
    }


def normalize_percentages(materials: dict[str, float]) -> dict[str, float | int]:
    """Validate an explicit 100% composition, preserving every supplied ratio.

    Decimal arithmetic avoids a business tolerance or a rescaling step. The
    historical function name is retained for callers; it no longer repairs data.
    """
    if not materials:
        return {}
    try:
        values = {key: Decimal(str(value)) for key, value in materials.items()}
    except (InvalidOperation, ValueError):
        return {}
    if (any(not value.is_finite() or not 0 < value <= 100 for value in values.values())
            or sum(values.values(), Decimal(0)) != 100):
        return {}
    return {key: int(value) if value == value.to_integral_value() else float(value)
            for key, value in values.items()}


def choose_representative_materials(parts: dict[str, dict[str, float]]) -> tuple[str, dict[str, float | int]]:
    priority = ["outer", "generic", "lining", "filling", "pocket", "rib", "sleeve", "color_block"]
    for part in priority:
        if part in parts:
            return part, normalize_percentages(parts[part])
    return "", {}


def parse_materials(text: str) -> dict[str, float | int]:
    _, materials = choose_representative_materials(parse_parts(text))
    return materials


def format_materials_korean(material_dict: dict[str, float | int]) -> str:
    if not material_dict:
        return ""

    parts = []
    for material, percent in sorted(material_dict.items(), key=lambda item: (-float(item[1]), item[0])):
        korean = MATERIAL_KOREAN.get(material, material)
        percent_text = str(int(percent)) if float(percent).is_integer() else format(Decimal(str(percent)).normalize(), "f")
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
