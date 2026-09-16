"""OCR 문자열 정규화와 소재·의류 파트 토큰 추출."""

import re
import unicodedata

from apps.text.rules import MATERIAL_ALIASES, OCR_CORRECTIONS


PART_PATTERNS = {
    "outer": [
        "겉감",
        "겉 감",
        "외피",
        "표면",
        "본체",
        "몸판",
        "본피",
        "shell",
        "outshell",
        "outer",
        "face",
        "main fabric",
        "本体",
        "面料",
        "表布",
        "表層",
        "表地",
        "表素材",
        "表生地",
        "主面料",
        "外层",
        "外層",
    ],
    "lining": [
        "안감",
        "안 감",
        "내피",
        "lining",
        "lning",
        "裏地",
        "里料",
        "裡料",
        "内里",
        "內裡",
        "裏素材",
        "裏生地",
        "里布",
        "裏布",
        "内衬",
        "內襯",
        "衬里",
        "襯裡",
    ],
    "filling": [
        "충전재",
        "충전제",
        "충전",
        "솜",
        "filling",
        "fill",
        "中わた",
        "中綿",
        "填充",
        "填充物",
        "填充料",
    ],
    "pocket": [
        "주머니감", "주머니천", "주머니", "pocket", "口袋布", "袋布", "ポケット布"
    ],
    "rib": ["립", "리브", "rib", "罗纹", "羅紋"],
    "sleeve": ["소매", "sleeve", "袖子", "袖部", "袖"],
    "color_block": ["배색", "contrast", "配色", "拼接", "別布"],
}

EXCLUDED_SEGMENT_WORDS = {
    "심지",
    "보강재",
    "상표",
    "무늬",
    "밴드",
    "레이스",
    "자수",
    "장식",
    "부자재",
    "제외",
    "except",
    "excluding",
    "exclusive of decoration",
    "decoration",
    "embroidery",
    "accessory",
    "trim",
    "装饰",
    "裝飾",
    "刺绣",
    "刺繍",
    "辅料",
    "輔料",
    "配件",
    "付属",
    "附属",
    "除く",
}

_TOKEN_PATTERN = re.compile(
    r"[a-zà-ÿ]+|[가-힣]+|[一-龥]+|[ぁ-んァ-ンー]+",
    re.IGNORECASE,
)


def _normalized_alias(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().strip())


ALIAS_TO_MATERIAL = {
    _normalized_alias(alias): material
    for material, aliases in MATERIAL_ALIASES.items()
    for alias in aliases
    if alias.strip()
}

MULTIWORD_ALIASES = sorted(
    (
        (alias, material)
        for alias, material in ALIAS_TO_MATERIAL.items()
        if " " in alias
    ),
    key=lambda item: len(item[0]),
    reverse=True,
)


def _replace_token(text: str, wrong: str, correct: str) -> str:
    if wrong.isascii():
        pattern = rf"(?<![a-z]){re.escape(wrong)}(?![a-z])"
    else:
        pattern = re.escape(wrong)
    return re.sub(pattern, correct, text, flags=re.IGNORECASE)


def normalize_text(text: str) -> str:
    if not text:
        return ""

    # Normalize full-width digits/punctuation and compatibility characters
    # commonly returned from Japanese and Chinese care labels.
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("：", ":").replace("％", "%")
    normalized = normalized.replace("·", " ").replace("\u00a0", " ")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    for wrong, correct in OCR_CORRECTIONS.items():
        normalized = _replace_token(normalized, wrong.casefold(), correct.casefold())

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.split("\n")]
    return "\n".join(line for line in lines if line)


def clean_ocr_preview(text: str, max_len: int = 220) -> str:
    if not text:
        return ""
    preview = re.sub(r"\s+", " ", text).strip()
    return preview if len(preview) <= max_len else preview[:max_len] + "..."


def find_material_key(word: str) -> str | None:
    token = _normalized_alias(word.strip(" .,:;/()[]{}<>|+-_=*\"'"))
    if not token:
        return None
    corrected = OCR_CORRECTIONS.get(token, token)
    corrected = _normalized_alias(corrected)
    material = ALIAS_TO_MATERIAL.get(corrected)
    if material:
        return material

    # OCR sometimes joins a Korean part marker and its first material
    # (for example, ``배색면``). Only split a known non-ASCII marker and
    # require the remainder to be a complete material alias.
    for aliases in PART_PATTERNS.values():
        for prefix in aliases:
            normalized_prefix = _normalized_alias(prefix)
            if (
                not normalized_prefix.isascii()
                and corrected.startswith(normalized_prefix)
                and len(corrected) > len(normalized_prefix)
            ):
                material = ALIAS_TO_MATERIAL.get(corrected[len(normalized_prefix) :])
                if material:
                    return material
    return None


def _strip_excluded_segments(line: str) -> str:
    def remove_if_excluded(match: re.Match[str]) -> str:
        content = match.group(0).casefold()
        return " " if any(word in content for word in EXCLUDED_SEGMENT_WORDS) else content

    cleaned = re.sub(r"[\(\[][^\)\]]*[\)\]]", remove_if_excluded, line)
    exclusion_pattern = "|".join(
        re.escape(word)
        for word in sorted(EXCLUDED_SEGMENT_WORDS, key=len, reverse=True)
    )
    cleaned = re.sub(
        rf"(?:{exclusion_pattern}).*$",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_materials(line: str) -> list[str]:
    cleaned = _strip_excluded_segments(normalize_text(line))
    if not cleaned:
        return []

    found_by_position: list[tuple[int, str]] = []
    tokenizable = cleaned
    for alias, material in MULTIWORD_ALIASES:
        pattern = rf"(?<![a-z]){re.escape(alias)}(?![a-z])"
        for match in list(re.finditer(pattern, tokenizable)):
            found_by_position.append((match.start(), material))
            # Keep offsets while masking a compound so a partial token such
            # as ``폴리`` cannot also be read as polyester.
            tokenizable = (
                tokenizable[: match.start()]
                + " " * (match.end() - match.start())
                + tokenizable[match.end() :]
            )

    for match in _TOKEN_PATTERN.finditer(tokenizable):
        material = find_material_key(match.group())
        if material:
            found_by_position.append((match.start(), material))

    return list(
        dict.fromkeys(material for _, material in sorted(found_by_position))
    )


def detect_part(line: str, current_part: str) -> str:
    normalized = normalize_text(line)
    for part, aliases in PART_PATTERNS.items():
        if any(alias.casefold() in normalized for alias in aliases):
            return part
    return current_part
