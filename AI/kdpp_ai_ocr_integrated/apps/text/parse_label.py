import re
from collections import defaultdict

from apps.text.rules import CARE_RULES, MATERIAL_ALIASES, OCR_CORRECTIONS


def normalize_text(text: str) -> str:
    if not text:
        return ""
    normalized = text.lower().replace("\n", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    for wrong, correct in OCR_CORRECTIONS.items():
        normalized = re.sub(rf"\b{re.escape(wrong)}\b", correct, normalized)
    return normalized


def clean_ocr_preview(text: str, max_len: int = 160) -> str:
    if not text:
        return ""
    preview = re.sub(r"\s+", " ", text.replace("\n", " | ")).strip()
    return preview if len(preview) <= max_len else preview[:max_len] + "..."


def find_material_korean(word: str) -> str | None:
    token = word.lower().strip()
    token = OCR_CORRECTIONS.get(token, token)

    for korean, aliases in MATERIAL_ALIASES.items():
        for alias in aliases:
            alias = alias.lower().strip()
            if token == alias or alias in token or token in alias:
                return korean
    return None


def parse_materials(text: str) -> dict[str, float]:
    text_n = normalize_text(text)
    results = defaultdict(float)

    patterns = [
        r"(\d{1,3})\s*%\s*([a-zA-Z가-힣À-ÿА-Яа-я]+)",
        r"([a-zA-Z가-힣À-ÿА-Яа-я]+)\s*(\d{1,3})\s*%",
    ]

    for pattern in patterns:
        for left, right in re.findall(pattern, text_n):
            if left.isdigit():
                percent, material = float(left), right
            else:
                material, percent = left, float(right)

            if 0 <= percent <= 100:
                korean = find_material_korean(material)
                if korean:
                    results[korean] += percent

    return dict(results)


def format_materials(material_dict: dict[str, float]) -> str:
    if not material_dict:
        return ""

    parts = []
    for material, percent in sorted(material_dict.items(), key=lambda item: (-item[1], item[0])):
        percent_text = str(int(percent)) if float(percent).is_integer() else f"{percent:.1f}"
        parts.append(f"{material} {percent_text}%")
    return "; ".join(parts)


def parse_care(text: str) -> str:
    text_n = normalize_text(text)
    found = []

    for korean, aliases in CARE_RULES.items():
        if any(alias.lower() in text_n for alias in aliases):
            found.append(korean)

    return "; ".join(dict.fromkeys(found))


def parse_label(text: str) -> dict:
    materials = parse_materials(text)
    return {
        "materials": materials,
        "materials_korean": format_materials(materials),
        "care_text": parse_care(text),
        "raw_ocr_preview": clean_ocr_preview(text),
    }

