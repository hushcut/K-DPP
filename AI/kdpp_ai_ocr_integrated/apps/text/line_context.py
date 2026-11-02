"""소재 행과 세탁 문구를 구분하는 줄 문맥 상수·판별 함수.

``parse_label``과 ``composition_candidates``가 함께 쓴다. 두 모듈을 import하지
않는 하위 계층에 두어 둘 사이의 상호 import 없이 공유한다.
"""

import re

from apps.text.material_extraction import (
    ALIAS_TO_MATERIAL,
    PART_PATTERNS,
    _TOKEN_PATTERN,
    _material_evidence,
    normalize_text,
)
from apps.text.rules import CARE_RULES


COMPOSITION_HINTS = {
    "섬유의 조성",
    "혼용률",
    "혼용율",
    "소재",
    "composition",
    "fabric content",
    "material",
    "materials",
    "fiber content",
    "纤维成分",
    "纖維成分",
    "面料成分",
    "材质",
    "材質",
    "組成表示",
    "混用率",
    "品質表示",
}


_CARE_PHRASES = tuple(
    {alias.casefold() for aliases in CARE_RULES.values() for alias in aliases}
)


# Number safety needs broader context than the phrases used to display care
# instructions. These words alone do not imply a specific care recommendation.
_CARE_CONTEXT_PATTERN = re.compile(
    r"(?<![a-z])(?:wash(?:ing)?|rinse|bleach(?:ing)?|iron(?:ing)?|dry(?:ing)?)(?![a-z])"
    r"|세탁|표백|다림질|건조|드라이"
    r"|水洗|洗涤|洗滌|漂白|熨|烘|干洗|乾洗"
    r"|洗濯|手洗|アイロン|乾燥|ドライ"
)


def _mentions_care(line: str) -> bool:
    """Whether a row also carries care text, whose numbers are not ratios."""

    return bool(_CARE_CONTEXT_PATTERN.search(line)) or any(
        phrase in line for phrase in _CARE_PHRASES
    )


_RATIO_PAIR_DESCRIPTORS = {
    "organic",
    "recycled",
    "combed",
    "certified",
    "pure",
    "fiber",
    "fibre",
    "content",
    "blend",
    "of",
    "and",
    "유기농",
    "재생",
    "섬유",
    "함량",
    "혼방",
    "및",
}


_RATIO_PREFIX_CONTEXTS = {
    *COMPOSITION_HINTS,
    *(alias for aliases in PART_PATTERNS.values() for alias in aliases),
    "fiber",
    "fibre",
    "fabric",
    "content",
    "body",
    "組成",
    "組成表示",
    "纤维",
    "纤维成分",
    "成分",
}


_EXPLICIT_PART_HEADER_CONTEXTS = _RATIO_PREFIX_CONTEXTS | {
    "fabric",
    "재질",
}


_MATERIAL_ONLY_LINE_CONTEXTS = set(ALIAS_TO_MATERIAL) | _RATIO_PAIR_DESCRIPTORS | _EXPLICIT_PART_HEADER_CONTEXTS


def _contains_only_known_phrases(text: str, phrases: set[str]) -> bool:
    remainder = normalize_text(text)
    # Use the same normalized aliases and OCR corrections as extraction. This
    # preserves multilingual names such as bombaž that normalize to bombaz.
    if phrases is _MATERIAL_ONLY_LINE_CONTEXTS:
        for evidence in reversed(_material_evidence(remainder)):
            remainder = remainder[:evidence.start] + " " * (evidence.end - evidence.start) + remainder[evidence.end:]
    for phrase in sorted(phrases, key=len, reverse=True):
        if phrase.isascii():
            remainder = re.sub(
                rf"(?<![a-z]){re.escape(phrase.casefold())}(?![a-z])",
                " ",
                remainder,
            )
        else:
            remainder = remainder.replace(phrase.casefold(), " ")
    return _TOKEN_PATTERN.search(remainder) is None
