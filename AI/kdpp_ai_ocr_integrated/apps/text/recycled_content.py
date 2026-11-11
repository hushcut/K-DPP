"""Separate a literal recycled-content property from a fiber's mixture ratio.

The complete source annotation stays in the OCR text. Only a closed property
immediately following a named, explicitly quantified fiber is masked in the
composition-reading view. Unknown fibers and percentages remain evidence.
"""

from decimal import Decimal
import re


_PROPERTY = re.compile(
    r"\(\s*(?:(?P<ratio>\d{1,3}(?:[.,]\d{1,2})?)\s*%\s*"
    r"(?:recycled|recycle|recyclé)|再生)\s*\)", re.IGNORECASE,
)
_UNBOUND_RATIO_PROPERTY = re.compile(
    r"\(\s*\d+(?:[.,]\d+)?\s*%\s*(?:recycled|recycle|recyclé)\s*(?:\)|$)",
    re.IGNORECASE,
)
_UNCLOSED_WRAPPED_PROPERTY = re.compile(
    r"\(\s*\d+(?:[.,]\d+)?\s*%\s*(?:recycled|recycle|recyclé)[ \t]*(?=\n|$)",
    re.IGNORECASE,
)


def has_unbound_recycled_ratio(text: str) -> bool:
    """An unmasked bare property must not supply a missing mixture ratio."""
    return bool(_UNBOUND_RATIO_PROPERTY.search(text))


def unclosed_recycled_property_rows(text: str) -> set[int]:
    """Keep a missing closing bracket invalid even across OCR row breaks."""
    rows = set()
    for match in _UNCLOSED_WRAPPED_PROPERTY.finditer(text):
        first = text.count("\n", 0, match.start())
        rows.update(range(first, first + match.group().count("\n") + 1))
    return rows


def join_wrapped_recycled_property(text: str) -> str:
    """Keep all literal characters while joining only this closed caption."""
    return _PROPERTY.sub(lambda match: re.sub(r"\s+", " ", match.group()), text)


def join_following_recycled_property(text: str, pair_pattern, heading_pattern) -> str:
    """Join only a closed property immediately after its explicit fiber row.

    All words, digits and any following part heading remain in the text. The
    ordinary composition view still validates the joined row and its context.
    """
    lines = []
    for line in text.split("\n"):
        match = _PROPERTY.match(line)
        if lines and match:
            declaration = lines[-1] + " " + match.group()
            if mask_recycled_properties(declaration, pair_pattern, heading_pattern) != declaration:
                lines[-1] += " " + line
                continue
        lines.append(line)
    return "\n".join(lines)


def mask_recycled_properties(
    text: str, pair_pattern: re.Pattern[str], heading_pattern: re.Pattern[str],
) -> str:
    """Mask a bounded property only after a complete literal fiber/ratio pair."""
    spans = []
    anchors = set()
    for match in _PROPERTY.finditer(text):
        ratio = match.group("ratio")
        if ratio is not None and not 0 < Decimal(ratio.replace(",", ".")) <= 100:
            continue
        prefix = text[:match.start()].rstrip()
        for start, end in reversed(spans):
            prefix = prefix[:start] + " " * (end - start) + prefix[end:]
        anchor = None
        while pair := pair_pattern.search(prefix.rstrip()):
            if anchor is None:
                anchor = pair.start()
            if anchor in anchors:
                break
            amount = pair.group("before") or pair.group("after")
            if not 0 < Decimal(amount.replace(",", ".")) <= 100:
                break
            context = prefix[:pair.start()].strip()
            if not context or heading_pattern.fullmatch(context):
                spans.append(match.span())
                anchors.add(anchor)
                break
            # An earlier complete pair is allowed only across a printed
            # composition separator. NOT/UNKNOWN before a pair stays visible.
            if context[-1:] not in {"/", ";"}:
                break
            prefix = context[:-1].rstrip()
    masked = text
    for start, end in reversed(spans):
        masked = masked[:start] + " " * (end - start) + masked[end:]
    if spans:
        # The property cannot make an opaque suffix look like a complete
        # mixture. Only more explicitly quantified fibers (or a printed row
        # separator awaiting the next row) may follow it.
        suffix = masked[spans[-1][1]:].strip()
        if suffix:
            suffix = re.sub(r"^[/;,]\s*", "", suffix)
            pieces = re.split(r"\s*[/;]\s*|,\s*(?!\d)", suffix)
            if any(piece and pair_pattern.fullmatch(piece) is None for piece in pieces):
                return text
    return masked


def recycled_pair_pattern(aliases) -> re.Pattern[str]:
    """Bind the annotation to either printed ratio/name order, without OCR repair."""
    names = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
    return re.compile(
        rf"(?<![\w.+,\-])(?:(?P<before>\d{{1,3}}(?:[.,]\d{{1,2}})?)\s*%\s*(?:{names})"
        rf"|(?:{names})\s+(?P<after>\d{{1,3}}(?:[.,]\d{{1,2}})?)\s*%)$",
        re.IGNORECASE,
    )
