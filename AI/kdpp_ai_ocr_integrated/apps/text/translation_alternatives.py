"""Validate explicit slash-separated copies of a printed fiber declaration.

The primary name and percentage must already be readable. Other readable
copies must agree. Only a registered-name prefix, or a short OCR fragment
between readable copies, can be treated as damaged translation text.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re

from apps.text.material_extraction import (
    ALIAS_TO_MATERIAL, declared_part, extract_materials,
    unresolved_material_tokens,
)


_NAME = re.compile(
    r"(?<!\w)(?:" + "|".join(
        re.escape(alias) for alias in sorted(ALIAS_TO_MATERIAL, key=len, reverse=True)
    ) + r")(?!\w)"
)
_PRIMARY = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*%\s*")
_STOP = re.compile(r"[0-9%]|(?<!\w)(?:wash|bleach|iron|dry)(?!\w)|세탁|표백|건조|다림질")
_UNSAFE = re.compile(
    r"[+−±∓<>≤≥~≈]|(?<!\w)(?:unknown|other|others|unregistered|olefin)(?!\w)"
    r"|未知|未登録|미상|기타|불명"
)
_HEADINGS = {"composition", "구성"}
_AMBIGUOUS_SHORT_NAMES = {"pu", "pa", "pe", "pp", "pes", "pla", "mix", "unk"}

# Letter shapes in a registered Cyrillic alias may be read as Latin letters.
# This is used only inside a corroborating translation list, never as a
# standalone material alias or a general fuzzy match.
_CYRILLIC_GLYPHS = {
    "х": "[хx]", "л": "[лn]", "о": "[оo]", "п": "[пn]", "к": "[кk]",
}


def _registered_glyph_copy(word: str, material: str) -> bool:
    return any(
        key == material and len(alias) >= 5 and any(c in _CYRILLIC_GLYPHS for c in alias)
        and re.fullmatch("".join(_CYRILLIC_GLYPHS.get(c, re.escape(c)) for c in alias), word)
        for alias, key in ALIAS_TO_MATERIAL.items()
    )


def _prepare_repeated_hyphen_declaration(text: str) -> TranslationAlternatives:
    """Keep a literal 100% primary row and validate each printed repeat.

    A long translation list must end in a second explicit, identical 100%
    declaration and the written decoration-exclusion caption. Every list
    clause must be a registered alias of the primary fiber, except one
    registered Cyrillic glyph copy surrounded by readable agreeing aliases.
    No extra digit, unknown fiber, part, or uncertainty sign is discarded.
    """
    rows = text.split("\n")
    recovered, damaged = set(), set()
    for start, row in enumerate(rows):
        primary = _PRIMARY.match(row)
        name = _NAME.match(row, primary.end()) if primary else None
        if (name is None or Decimal(primary.group(1)) != 100
                or not re.match(r"\s*-", row[name.end():])):
            continue
        end = start + 1
        while end < len(rows) and not re.fullmatch(r"exclusive\s+of\s+decoration\s*[.]?", rows[end]):
            terminal_repeat = (end + 1 < len(rows)
                               and re.fullmatch(r"exclusive\s+of\s+decoration\s*[.]?", rows[end + 1]))
            if (not rows[end].strip() or declared_part(rows[end])
                    or (_STOP.search(rows[end]) and not terminal_repeat)):
                break
            end += 1
        if end >= len(rows) or not re.fullmatch(r"exclusive\s+of\s+decoration\s*[.]?", rows[end]):
            continue
        repeat = re.fullmatch(r"\s*(\$\s*)?([0-9]+(?:\.[0-9]+)?)\s*%\s*-\s*([^\W\d_]+)\s*", rows[end - 1])
        key = ALIAS_TO_MATERIAL[name.group()]
        if (repeat is None or Decimal(repeat.group(2)) != 100
                or ALIAS_TO_MATERIAL.get(repeat.group(3)) != key):
            continue
        body = "".join(rows[start:end - 1])[name.end():]
        clauses = [c.strip() for c in body.split("-") if c.strip()]
        aliases, glyphs, valid = {name.group(), repeat.group(3)}, [], bool(clauses)
        for position, clause in enumerate(clauses):
            names = list(_NAME.finditer(clause))
            remainder = list(clause)
            for match in names:
                if ALIAS_TO_MATERIAL[match.group()] != key:
                    valid = False
                aliases.add(match.group())
                remainder[match.start():match.end()] = " " * len(match.group())
            opaque = "".join(remainder).strip()
            if not opaque and names:
                continue
            if (names or not _registered_glyph_copy(clause, key)
                    or position == 0 or position == len(clauses) - 1):
                valid = False
                break
            glyphs.append(position)
        if not valid or len(aliases) < 6 or len(glyphs) > 1:
            continue
        # Opaque evidence immediately preceding a list cannot become a title.
        before = rows[start - 1] if start else ""
        if (_UNSAFE.search(before) or unresolved_material_tokens(before)
                or (re.search(r"[^\W\d_]", before)
                    and before.strip(" :") not in _HEADINGS)):
            continue
        rows[start] = rows[start][:name.end()]
        rows[start + 1:end] = [""] * (end - start - 1)
        recovered.add(start)
        if glyphs or repeat.group(1):
            damaged.add(start)
    return TranslationAlternatives("\n".join(rows), frozenset(recovered), frozenset(damaged))


@dataclass(frozen=True)
class TranslationAlternatives:
    text: str
    recovered_rows: frozenset[int] = frozenset()
    damaged_rows: frozenset[int] = frozenset()
    rejected_rows: frozenset[int] = frozenset()


def _validate_hyphen_copies(text: str) -> set[int]:
    """Read literal hyphen-separated aliases without interpreting signed ratios.

    Only a complete primary percentage/name and at least three registered
    copies of that fiber qualify. Unknown words, additional numbers and signs
    are retained for ordinary rejection; no fuzzy fiber lookup occurs here.
    """
    rows = text.split("\n")
    rejected = set()
    for index, row in enumerate(rows):
        primary = _PRIMARY.match(row)
        name = _NAME.match(row, primary.end()) if primary else None
        if name is None or not re.match(r"\s*-", row[name.end():]):
            continue
        end = index + 1
        while end < len(rows) and rows[end].strip() and not _STOP.search(rows[end]) and not declared_part(rows[end]):
            if "-" not in rows[end] or re.search(r"exclusive|exclu", rows[end]):
                break
            end += 1
        tail = "".join(rows[index:end])[name.end():]
        clauses = [clause.strip() for clause in tail.split("-") if clause.strip()]
        key = ALIAS_TO_MATERIAL[name.group()]
        known = {name.group()}
        valid = bool(clauses)
        for clause in clauses:
            # A lone OCR bracket/quote between registered copies is punctuation,
            # not a fiber or numeric sign. Keep it in the ordinary reader.
            if clause in {"[", "]", "\"", "'"}:
                continue
            names = list(_NAME.finditer(clause))
            remainder = list(clause)
            for alias in names:
                if ALIAS_TO_MATERIAL[alias.group()] != key:
                    valid = False
                else:
                    known.add(alias.group())
                remainder[alias.start():alias.end()] = " " * len(alias.group())
            valid &= bool(names) and not "".join(remainder).strip()
        if not valid or len(known) < 3:
            if len(known) >= 3:
                rejected.add(index)
            continue
        neighbors = rows[max(0, index - 1):index] + rows[end:end + 1]
        if any(_UNSAFE.search(line) or unresolved_material_tokens(line)
               or (re.search(r"[^\W\d_]", line) and not declared_part(line)
                   and not _PRIMARY.match(line)
                   and not ("%" in line and extract_materials(line))
                   and line.strip(" :") not in _HEADINGS
                   and not re.match(r"(?:made\s+in\s+|wash\b|hand\s+wash\b|machine\s+wash\b|dry\b|exclusive\b|exclu)", line))
               for line in neighbors):
            rejected.add(index)
            continue
    # Keep every readable copy and repeated ratio in its original row. The
    # ordinary reader already supports registered glosses; this validator
    # closes the path where opaque suffixes were treated as harmless text.
    return rejected


def prepare_translation_alternatives(text: str) -> TranslationAlternatives:
    """Keep row identities and every number/part outside a validated list."""
    if "%" not in text:
        return TranslationAlternatives(text)
    hyphen = _prepare_repeated_hyphen_declaration(text)
    text = hyphen.text
    hyphen_rejections = _validate_hyphen_copies(text)
    if "/" not in text:
        return TranslationAlternatives(
            text, hyphen.recovered_rows, hyphen.damaged_rows, frozenset(hyphen_rejections),
        )
    rows = text.split("\n")
    recovered, damaged, rejected = set(hyphen.recovered_rows), set(hyphen.damaged_rows), set(hyphen_rejections)
    cursor = 0
    while cursor < len(rows):
        primary = _PRIMARY.match(rows[cursor])
        name = _NAME.match(rows[cursor], primary.end()) if primary else None
        if name is None or not re.match(r"\s*/", rows[cursor][name.end():]):
            cursor += 1
            continue
        material = ALIAS_TO_MATERIAL[name.group()]
        number = Decimal(primary.group(1))
        if not 0 < number <= 100:
            cursor += 1
            continue
        end = cursor + 1
        while end < len(rows):
            line = rows[end]
            if not line.strip() or _STOP.search(line) or declared_part(line):
                break
            if set(extract_materials(line)) - {material}:
                # A different material starts its own declaration. Keep it
                # and its later percentage for the ordinary column reader.
                break
            tail = re.search(r"[^\W\d_]+$", rows[end - 1])
            wrapped_name = tail is not None and any(
                alias.startswith(tail.group()) and alias != tail.group() and key == material
                for alias, key in ALIAS_TO_MATERIAL.items()
            )
            if ("/" not in line and not extract_materials(line)
                    and line.strip(" :") not in _HEADINGS
                    and not rows[end - 1].rstrip().endswith("/") and not wrapped_name):
                break
            end += 1
        body = "\n".join(rows[cursor:end])
        names = list(_NAME.finditer(body))
        aliases = {match.group() for match in names}
        if len(aliases) < 2:
            cursor = end
            continue
        # Multiple explicit declarations on one printed row belong to the
        # ordinary mixed-composition reader, not this one-percentage list.
        if len(re.findall(r"[0-9]+(?:\.[0-9]+)?\s*%", body)) > 1:
            cursor = end
            continue
        if (len(aliases) < 2 or {ALIAS_TO_MATERIAL[a] for a in aliases} != {material}
                or declared_part(body) or _UNSAFE.search(body)
                or unresolved_material_tokens(body)):
            rejected.add(cursor)
            cursor = end
            continue
        neighboring_rows = rows[max(0, cursor - 1):cursor] + rows[end:end + 1]
        if any(_UNSAFE.search(row) or unresolved_material_tokens(row) for row in neighboring_rows):
            rejected.add(cursor)
            cursor = end
            continue
        # Remove the one explicit primary percentage. No other digit or sign
        # can be mistaken for a translation, temperature, or decorative mark.
        remainder = list(body)
        for start, stop in [primary.span(), *(match.span() for match in names)]:
            remainder[start:stop] = " " * (stop - start)
        remaining = "".join(remainder)
        for heading in _HEADINGS:
            remaining = re.sub(rf"(?m)^\s*{heading}\s*:\s*$", "", remaining)
        if re.search(r"[0-9%.,:;=()\[\]{}\-]", remaining):
            rejected.add(cursor)
            cursor = end
            continue
        fragments = list(re.finditer(r"[^\W\d_]+", remaining))
        valid = True
        for fragment in fragments:
            word = fragment.group()
            if word in _AMBIGUOUS_SHORT_NAMES or (len(word) >= 2 and any(
                alias.startswith(word) and key != material
                for alias, key in ALIAS_TO_MATERIAL.items()
            )):
                valid = False
                break
            registered_prefix = len(word) >= 4 and any(
                alias.startswith(word) and key == material
                for alias, key in ALIAS_TO_MATERIAL.items()
            )
            # Short noise is allowed only INSIDE a repeated list, with at
            # least three distinct agreeing aliases on both sides together.
            bounded_noise = (
                len(aliases) >= 3 and word.isascii() and len(word) <= 3
                and any(match.end() < fragment.start() for match in names)
                and any(match.start() > fragment.end() for match in names)
                and re.search(r"/\s*[^/]*$", body[:fragment.start()]) is not None
            )
            # One trailing glyph may be a damaged final translation. Require
            # four distinct complete copies, a literal slash, and no remaining
            # suffix. Longer opaque names and short polymer codes stay out.
            terminal_glyph = (
                len(aliases) >= 4 and word.isascii() and len(word) == 1
                and not body[fragment.end():].strip(" /\t\n")
                and re.search(r"/\s*$", body[:fragment.start()]) is not None
            )
            if not registered_prefix and not bounded_noise and not terminal_glyph:
                valid = False
                break
        # Unknown punctuation is evidence too; allow only list delimiters and
        # the exclamation artifact, not mathematical uncertainty signs.
        if re.sub(r"[^\W\d_]+", "", remaining).strip(" \t\n/!"):
            valid = False
        if valid:
            if not fragments:
                # Fully readable alternatives already work in the ordinary
                # parser. Preserve their original rows and evidence counts.
                cursor = end
                continue
            rows[cursor] = rows[cursor][:name.end()]
            rows[cursor + 1:end] = [""] * (end - cursor - 1)
            recovered.add(cursor)
            if fragments:
                damaged.add(cursor)
        else:
            rejected.add(cursor)
        cursor = end
    return TranslationAlternatives(
        "\n".join(rows), frozenset(recovered), frozenset(damaged), frozenset(rejected),
    )
