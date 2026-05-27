import re
from collections import defaultdict

from apps.text.rules import CARE_RULES, MATERIAL_ALIASES, MATERIAL_KOREAN, OCR_CORRECTIONS


def normalize_text(text: str) -> str:
    if not text:
        return ""
    normalized = text.lower().replace("\n", " ")
    normalized = normalized.replace("\uff1a", ":")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    for wrong, correct in OCR_CORRECTIONS.items():
        normalized = re.sub(rf"\b{re.escape(wrong)}\b", correct, normalized)
    return normalized


def clean_ocr_preview(text: str, max_len: int = 160) -> str:
    if not text:
        return ""
    preview = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    return preview if len(preview) <= max_len else preview[:max_len] + "..."


def find_material_key(word: str) -> str | None:
    token = word.lower().strip(" .,:;/()[]{}")
    token = OCR_CORRECTIONS.get(token, token)

    if len(token) < 2 and token.isascii():
        return None

    for material_key, aliases in MATERIAL_ALIASES.items():
        for alias in aliases:
            alias = alias.lower().strip()
            if token == alias:
                return material_key
            if len(alias) >= 4 and alias in token:
                return material_key
    return None


def parse_materials(text: str) -> dict[str, float | int]:
    text_n = normalize_text(text)
    results = defaultdict(float)

    tokens = re.findall(r"[a-zA-Z\uac00-\ud7a3]+|\d{1,3}", text_n)
    i = 0
    while i < len(tokens) - 1:
        current = tokens[i]
        next_token = tokens[i + 1]

        current_material = find_material_key(current)
        next_material = find_material_key(next_token)

        if current_material and next_token.isdigit():
            percent = float(next_token)
            if 0 < percent <= 100:
                results[current_material] += percent
            i += 2
            continue

        if current.isdigit() and next_material:
            percent = float(current)
            if 0 < percent <= 100:
                results[next_material] += percent
            i += 2
            continue

        i += 1

    return normalize_percentages(dict(results))


def normalize_percentages(materials: dict[str, float]) -> dict[str, float | int]:
    if not materials:
        return {}

    total = sum(materials.values())
    if total > 100:
        materials = {key: value * 100 / total for key, value in materials.items()}

    normalized = {}
    for key, value in materials.items():
        rounded = round(value, 1)
        normalized[key] = int(rounded) if float(rounded).is_integer() else rounded
    return normalized


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
        "confidence": {"ocr": "low"},
        "care_text": parse_care(raw_text),
        "expected_life_months": None,
    }


def parse_label(text: str) -> dict:
    materials = parse_materials(text)
    if not materials:
        return failed_response(text)

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
    }
