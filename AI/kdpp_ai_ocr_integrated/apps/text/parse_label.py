import re
import unicodedata
from collections import defaultdict

from apps.text.rules import CARE_RULES, MATERIAL_ALIASES, MATERIAL_KOREAN, OCR_CORRECTIONS

TOKEN_PATTERN = r"[a-zA-Z\uac00-\ud7a3\u3040-\u30ff\u3400-\u9fff]+|\d{1,3}(?:\.\d+)?"
NEARBY_TOKEN_WINDOW = 4
MIN_VALID_TOTAL = 95.0
MAX_VALID_TOTAL = 105.0
TEXT_LETTER_PATTERN = r"A-Za-z\uac00-\ud7a3\u3040-\u30ff\u3400-\u9fff"
MEASUREMENT_UNITS = {"cm", "mm", "m", "em", "호", "사이즈", "size", "free"}
EMBEDDED_SINGLE_CHAR_MATERIALS = {
    "면": "cotton",
    "綿": "cotton",
    "棉": "cotton",
    "毛": "wool",
}


def strip_latin_accents(text: str) -> str:
    chars: list[str] = []
    for char in text:
        if "LATIN" not in unicodedata.name(char, ""):
            chars.append(char)
            continue

        chars.extend(
            decomposed
            for decomposed in unicodedata.normalize("NFKD", char)
            if not unicodedata.combining(decomposed)
        )
    return "".join(chars)


def repair_ocr_noise(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\uff1a", ":")
    normalized = normalized.replace("\uff05", "%")

    normalized = re.sub(r"\bcotonao0?9\b", "cotton 100", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bcoton[a-z]*0?9\b", "cotton 100", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bcotton\s+2000\b", "cotton 100", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"아크\s*[럴렐릴]", "아크릴", normalized)
    normalized = re.sub(r"스\s*판(?:\s*덱스)?", "스판덱스", normalized)

    normalized = re.sub(
        rf"(?<![{TEXT_LETTER_PATTERN}])\ub9cc\s+(100)(?!\d)",
        "\uba74 \\1",
        normalized,
    )

    # Google Vision sometimes reads a percent sign as "96" on dotted fabric labels.
    normalized = re.sub(r"\b([1-9]\d?)96\b", r"\1%", normalized)
    normalized = re.sub(r"\b1000\b", "100%", normalized)
    normalized = re.sub(r"\b[il]00\b", "100", normalized, flags=re.IGNORECASE)

    # Split glued OCR tokens such as "폴리에스터2%" or "D100%".
    normalized = re.sub(rf"([{TEXT_LETTER_PATTERN}])(\d{{1,3}})", r"\1 \2", normalized)
    normalized = re.sub(rf"(\d{{1,3}})([{TEXT_LETTER_PATTERN}])", r"\1 \2", normalized)
    normalized = re.sub(r"(\d{1,3}(?:\.\d+)?)\s*%", r"\1 ", normalized)

    return normalized


def normalize_text(text: str) -> str:
    if not text:
        return ""
    normalized = repair_ocr_noise(text).lower().replace("\n", " ")
    normalized = strip_latin_accents(normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    for wrong, correct in OCR_CORRECTIONS.items():
        normalized = re.sub(
            rf"(?<![{TEXT_LETTER_PATTERN}]){re.escape(wrong.lower())}(?![{TEXT_LETTER_PATTERN}])",
            correct.lower(),
            normalized,
        )
    return normalized


def clean_ocr_preview(text: str, max_len: int = 160) -> str:
    if not text:
        return ""
    preview = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    return preview if len(preview) <= max_len else preview[:max_len] + "..."


def find_material_key(word: str) -> str | None:
    token = strip_latin_accents(word.lower()).strip(" .,:;/()[]{}%")
    token = OCR_CORRECTIONS.get(token, token)

    if len(token) < 2 and token.isascii():
        return None

    for material_key, aliases in MATERIAL_ALIASES.items():
        for alias in aliases:
            alias = strip_latin_accents(alias.lower().strip())
            if token == alias:
                return material_key
            if len(alias) >= 4 and alias in token:
                return material_key

    for alias, material_key in EMBEDDED_SINGLE_CHAR_MATERIALS.items():
        if alias in token and (token.endswith(alias.lower()) or len(token) <= 4):
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


def is_measurement_number(tokens: list[str], index: int) -> bool:
    if index + 1 >= len(tokens):
        return False
    return tokens[index + 1].lower() in MEASUREMENT_UNITS


def is_likely_stray_number(tokens: list[str], index: int) -> bool:
    if index + 1 >= len(tokens):
        return False
    if not (is_percent_token(tokens[index]) and is_percent_token(tokens[index + 1])):
        return False
    return float(tokens[index + 1]) >= 20


def is_likely_forward_ratio(tokens: list[str], index: int) -> bool:
    for previous_index in range(index - 1, max(index - NEARBY_TOKEN_WINDOW - 1, -1), -1):
        if is_percent_token(tokens[previous_index]):
            return False

        if not find_material_key(tokens[previous_index]):
            continue

        number_before_material = previous_index - 1
        if number_before_material >= 0 and is_percent_token(tokens[number_before_material]):
            material_before_number = number_before_material - 1
            if material_before_number < 0 or not find_material_key(tokens[material_before_number]):
                return False

        return True

    return False


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
            if is_measurement_number(tokens, next_index) or is_likely_stray_number(tokens, next_index):
                continue
            if is_percent_token(next_token):
                add_candidate(candidates, index, next_index, material, next_token)
                break

    return sorted(candidates, key=lambda item: item[0])


def find_reverse_candidates(tokens: list[str]) -> list[tuple[int, str, float]]:
    candidates: list[tuple[int, str, float]] = []

    for index, token in enumerate(tokens):
        if (
            is_measurement_number(tokens, index)
            or is_likely_stray_number(tokens, index)
            or is_likely_forward_ratio(tokens, index)
        ):
            continue
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


def compact_material_mentions(tokens: list[str]) -> list[tuple[int, str]]:
    mentions: list[tuple[int, str]] = []
    for index, token in enumerate(tokens):
        material = find_material_key(token)
        if not material:
            continue
        if mentions and mentions[-1][1] == material and index - mentions[-1][0] <= 3:
            continue
        mentions.append((index, material))
    return mentions


def find_parallel_list_candidates(tokens: list[str]) -> list[tuple[int, str, float]]:
    mentions = compact_material_mentions(tokens)
    number_mentions = [
        (index, float(token))
        for index, token in enumerate(tokens)
        if is_percent_token(token) and not is_measurement_number(tokens, index)
    ]

    best_candidates: list[tuple[int, str, float]] = []
    best_score: tuple[int, int, float] | None = None

    for start in range(len(mentions)):
        material_sequence: list[tuple[int, str]] = []
        seen_materials: set[str] = set()

        for end in range(start, min(len(mentions), start + 5)):
            material_index, material = mentions[end]
            if material in seen_materials:
                break

            material_sequence.append((material_index, material))
            seen_materials.add(material)

            if len(material_sequence) < 2:
                continue

            numbers_after = [
                item for item in number_mentions if item[0] > material_sequence[-1][0]
            ]
            sequence_length = len(material_sequence)

            for number_start in range(0, len(numbers_after) - sequence_length + 1):
                number_sequence = numbers_after[number_start:number_start + sequence_length]
                total = sum(value for _, value in number_sequence)
                if not (MIN_VALID_TOTAL <= total <= MAX_VALID_TOTAL):
                    continue

                distance = number_sequence[0][0] - material_sequence[-1][0]
                score = (sequence_length, -distance, -material_sequence[0][0])
                if best_score is None or score > best_score:
                    best_score = score
                    best_candidates = [
                        (
                            min(material_item[0], number_item[0]),
                            material_item[1],
                            number_item[1],
                        )
                        for material_item, number_item in zip(material_sequence, number_sequence)
                    ]

    return best_candidates


def split_candidate_groups(candidates: list[tuple[int, str, float]]) -> list[list[tuple[int, str, float]]]:
    groups: list[list[tuple[int, str, float]]] = []
    current: list[tuple[int, str, float]] = []
    current_total = 0.0

    for candidate in candidates:
        percent = candidate[2]

        if current and current_total + percent > MAX_VALID_TOTAL:
            groups.append(current)
            current = []
            current_total = 0.0

        current.append(candidate)
        current_total += percent

    if current:
        groups.append(current)

    return groups


def choose_best_candidate_group(
    candidates: list[tuple[int, str, float]],
) -> list[tuple[int, str, float]]:
    best_group: list[tuple[int, str, float]] = []
    best_score: tuple[int, float, int, int] | None = None

    for group in split_candidate_groups(candidates):
        materials = recover_low_total_group(group)
        total = sum(materials.values())
        is_valid_total = MIN_VALID_TOTAL <= total <= MAX_VALID_TOTAL
        score = (1 if is_valid_total else 0, -abs(100.0 - total), -group[0][0], len(materials))

        if best_score is None or score > best_score:
            best_score = score
            best_group = group

    return best_group


def choose_best_group(candidates: list[tuple[int, str, float]]) -> dict[str, float]:
    return collapse_candidates(choose_best_candidate_group(candidates))


def group_score(materials: dict[str, float], first_index: int) -> tuple[int, float, int, int]:
    total = sum(materials.values())
    is_valid_total = MIN_VALID_TOTAL <= total <= MAX_VALID_TOTAL
    return (1 if is_valid_total else 0, -abs(100.0 - total), -first_index, len(materials))


def extend_candidate_group(
    base_group: list[tuple[int, str, float]],
    extra_candidates: list[tuple[int, str, float]],
) -> list[tuple[int, str, float]]:
    materials = collapse_candidates(base_group)
    total = sum(materials.values())
    extended = list(base_group)

    for candidate in sorted(extra_candidates, key=lambda item: item[0]):
        _, material, percent = candidate
        if material in materials:
            continue
        if total + percent > MAX_VALID_TOTAL:
            continue

        extended.append(candidate)
        materials[material] = percent
        total += percent

    return sorted(extended, key=lambda item: item[0])


def find_material_candidates(tokens: list[str]) -> list[tuple[int, str, float]]:
    def score_candidates(candidates: list[tuple[int, str, float]]) -> tuple[int, float, int, int]:
        group = choose_best_candidate_group(candidates)
        materials = recover_low_total_group(group) if group else {}
        return group_score(materials, candidates[0][0]) if materials else (0, -100.0, 0, 0)

    direct_sets = [
        candidates
        for candidates in [find_forward_candidates(tokens), find_reverse_candidates(tokens)]
        if candidates
    ]
    if direct_sets:
        direct_best = max(direct_sets, key=score_candidates)
        direct_score = score_candidates(direct_best)
        if direct_score[0] == 1:
            direct_group = choose_best_candidate_group(direct_best)
            reverse_candidates = find_reverse_candidates(tokens)
            extended_group = extend_candidate_group(direct_group, reverse_candidates)

            direct_materials = recover_low_total_group(direct_group)
            extended_materials = recover_low_total_group(extended_group)
            if abs(100.0 - sum(extended_materials.values())) < abs(
                100.0 - sum(direct_materials.values())
            ):
                return extended_group
            return direct_best

    parallel = find_parallel_list_candidates(tokens)
    candidate_sets = direct_sets + ([parallel] if parallel else [])
    if not candidate_sets:
        return []

    return max(candidate_sets, key=score_candidates)


def recover_low_total_group(group: list[tuple[int, str, float]]) -> dict[str, float]:
    materials = collapse_candidates(group)
    total = sum(materials.values())
    if total >= MIN_VALID_TOTAL:
        return materials

    ordered_materials: list[str] = []
    for _, material, _ in group:
        if material not in ordered_materials:
            ordered_materials.append(material)

    if len(ordered_materials) < 2:
        return materials

    first_material = ordered_materials[0]
    first_percent = materials.get(first_material, 0.0)
    other_total = total - first_percent

    # Common OCR miss: "94%" loses the leading digit and becomes "2%" or similar.
    if first_percent <= 15 and 0 < other_total <= 25:
        materials[first_material] = 100.0 - other_total

    return materials


def infer_single_material(tokens: list[str]) -> dict[str, float]:
    mentions = compact_material_mentions(tokens)
    unique_materials = []
    for _, material in mentions:
        if material not in unique_materials:
            unique_materials.append(material)

    if len(unique_materials) == 1:
        return {unique_materials[0]: 100.0}
    return {}


def parse_materials(text: str) -> dict[str, float | int]:
    tokens = tokenize_material_text(text)
    candidates = find_material_candidates(tokens)
    if not candidates:
        return normalize_percentages(infer_single_material(tokens))

    best_group = choose_best_candidate_group(candidates)
    materials = recover_low_total_group(best_group)
    if sum(materials.values()) < MIN_VALID_TOTAL:
        single_material = infer_single_material(tokens)
        if single_material:
            return normalize_percentages(single_material)

    return normalize_percentages(materials)


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
