import re
from collections import defaultdict

from apps.text.rules import CARE_RULES, MATERIAL_ALIASES, MATERIAL_KOREAN, OCR_CORRECTIONS

TOKEN_PATTERN = r"[a-zA-Z\uac00-\ud7a3\u3040-\u30ff\u3400-\u9fff]+|\d{1,3}(?:\.\d+)?"
NEARBY_TOKEN_WINDOW = 4
MIN_VALID_TOTAL = 95.0
MAX_VALID_TOTAL = 105.0


def normalize_text(text: str) -> str:
    if not text:
        return ""
    normalized = text.lower().replace("\n", " ")
    normalized = normalized.replace("\uff1a", ":")
    normalized = normalized.replace("\uff05", "%")
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
    token = word.lower().strip(" .,:;/()[]{}%")
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


def tokenize_material_text(text: str) -> list[str]:
    return re.findall(TOKEN_PATTERN, normalize_text(text))


def is_percent_token(token: str) -> bool:
    try:
        value = float(token)
    except ValueError:
        return False
    return 0 < value <= 100


def add_candidate(
    candidates: list[tuple[int, str, float]],
    material_index: int,
    number_index: int,
    material: str,
    percent_text: str,
) -> None:
    if not is_percent_token(percent_text):
        return

    candidates.append((min(material_index, number_index), material, float(percent_text)))


def find_forward_candidates(tokens: list[str]) -> list[tuple[int, str, float]]:
    candidates: list[tuple[int, str, float]] = []

    for index, token in enumerate(tokens):
        material = find_material_key(token)
        if not material:
            continue

        for next_index in range(index + 1, min(len(tokens), index + NEARBY_TOKEN_WINDOW + 1)):
            next_token = tokens[next_index]
            if find_material_key(next_token):
                break
            if is_percent_token(next_token):
                add_candidate(candidates, index, next_index, material, next_token)
                break

    return sorted(candidates, key=lambda item: item[0])


def find_reverse_candidates(tokens: list[str]) -> list[tuple[int, str, float]]:
    candidates: list[tuple[int, str, float]] = []

    for index, token in enumerate(tokens):
        if not is_percent_token(token):
            continue
        for next_index in range(index + 1, min(len(tokens), index + NEARBY_TOKEN_WINDOW + 1)):
            next_material = find_material_key(tokens[next_index])
            if next_material:
                add_candidate(candidates, next_index, index, next_material, token)
                break

    return sorted(candidates, key=lambda item: item[0])


def collapse_candidates(candidates: list[tuple[int, str, float]]) -> dict[str, float]:
    results: dict[str, float] = defaultdict(float)
    for _, material, percent in candidates:
        results[material] += percent
    return dict(results)


def split_candidate_groups(candidates: list[tuple[int, str, float]]) -> list[list[tuple[int, str, float]]]:
    groups: list[list[tuple[int, str, float]]] = []
    current: list[tuple[int, str, float]] = []
    current_total = 0.0

    for candidate in candidates:
        percent = candidate[2]

        if current and current_total >= MIN_VALID_TOTAL:
            groups.append(current)
            current = []
            current_total = 0.0

        if current and current_total + percent > MAX_VALID_TOTAL:
            groups.append(current)
            current = []
            current_total = 0.0

        current.append(candidate)
        current_total += percent

    if current:
        groups.append(current)

    return groups


def choose_best_group(candidates: list[tuple[int, str, float]]) -> dict[str, float]:
    best_materials: dict[str, float] = {}
    best_score: tuple[int, float, int] | None = None

    for group in split_candidate_groups(candidates):
        materials = collapse_candidates(group)
        total = sum(materials.values())
        is_valid_total = MIN_VALID_TOTAL <= total <= MAX_VALID_TOTAL
        score = (1 if is_valid_total else 0, -abs(100.0 - total), -group[0][0])

        if best_score is None or score > best_score:
            best_score = score
            best_materials = materials

    return best_materials


def group_score(materials: dict[str, float], first_index: int) -> tuple[int, float, int]:
    total = sum(materials.values())
    is_valid_total = MIN_VALID_TOTAL <= total <= MAX_VALID_TOTAL
    return (1 if is_valid_total else 0, -abs(100.0 - total), -first_index)


def find_material_candidates(tokens: list[str]) -> list[tuple[int, str, float]]:
    forward = find_forward_candidates(tokens)
    reverse = find_reverse_candidates(tokens)

    if not forward:
        return reverse
    if not reverse:
        return forward

    forward_group = choose_best_group(forward)
    reverse_group = choose_best_group(reverse)
    forward_score = group_score(forward_group, forward[0][0]) if forward_group else (0, -100.0, 0)
    reverse_score = group_score(reverse_group, reverse[0][0]) if reverse_group else (0, -100.0, 0)

    return forward if forward_score >= reverse_score else reverse


def parse_materials(text: str) -> dict[str, float | int]:
    candidates = find_material_candidates(tokenize_material_text(text))
    if not candidates:
        return {}

    return normalize_percentages(choose_best_group(candidates))


def normalize_percentages(materials: dict[str, float]) -> dict[str, float | int]:
    if not materials:
        return {}

    total = sum(materials.values())
    if total < MIN_VALID_TOTAL:
        return {}

    if MIN_VALID_TOTAL <= total <= MAX_VALID_TOTAL and total != 100:
        materials = {key: value * 100 / total for key, value in materials.items()}
    elif total > 100:
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
