"""Interpret printed copies only; never supply a missing primary fiber or ratio."""
from dataclasses import dataclass
from decimal import Decimal
import re

from apps.text.material_extraction import (
    ALIAS_TO_MATERIAL, _TOKEN_PATTERN, _material_evidence, declared_part,
    extract_materials, normalize_text, unresolved_material_tokens,
)
from apps.text.ratio_contract import has_exact_total


_NAME = re.compile('|'.join(re.escape(a) for a in sorted(ALIAS_TO_MATERIAL, key=len, reverse=True)) + r'(?![^\W\d_])')
_PERCENT = re.compile(r'(?<![\w.,+−-])([0-9]+(?:\.[0-9]+)?)\s*%')
_UNIT = re.compile(r'^\s*([0-9]+(?:\.[0-9]+)?)\s*%\s*')
_TAG = re.compile(r'(?<!\w)(en|uk|us|fr|de|es-mx|es|cat|pt|it|jp|cn|nl|cz|dk|fi|no|pl|sk|se|si|hr|lt|lv|ee|kr|ru|tr|el)\s*:\s*(?=\d)')
_CARE = re.compile(r'(?<![a-z])(?:wash|bleach|iron|dry|exclusive|excluant|excluyendo|excluindo)(?![a-z])|세탁|표백|건조|다림질')
_FORBIDDEN = re.compile(r'(?<!\w)(?:unknown|olefin)(?!\w)|未知|未登録')


@dataclass(frozen=True)
class TranslationRows:
    text: str
    warnings: tuple[str, ...] = ()


def _unsafe(text):
    return bool(_FORBIDDEN.search(text) or unresolved_material_tokens(text))


def _primary(line):
    match = _UNIT.match(line)
    if not match:
        return None
    name = _NAME.match(line, match.end())
    if not name:
        return None
    number = Decimal(match.group(1))
    if not 0 < number <= 100:
        return None
    return ALIAS_TO_MATERIAL[name.group()], number, name.end(), name.group()


def _known_remainder(text):
    remainder = text
    for evidence in reversed(_material_evidence(text)):
        remainder = remainder[:evidence.start] + ' ' * (evidence.end - evidence.start) + remainder[evidence.end:]
    return _TOKEN_PATTERN.search(remainder) is None


def _tagged_composition(text):
    """Require every percentage to introduce an exact registered name."""
    units = []
    for match in _PERCENT.finditer(text):
        name = _NAME.match(text, match.end() + len(text[match.end():]) - len(text[match.end():].lstrip()))
        if name is None:
            return None
        units.append((ALIAS_TO_MATERIAL[name.group()], Decimal(match.group(1))))
    if not units or len({material for material, _ in units}) != len(units):
        return None
    if (not _known_remainder(text) or not has_exact_total(number for _, number in units)
            or re.search(r'\d', _PERCENT.sub('', text))
            or set(extract_materials(text)) != {material for material, _ in units}):
        return None
    if any(not 0 < number <= 100 for _, number in units):
        return None
    if re.search(r'[+−~≈<>]|\d\s*,\s*\d', text) or _unsafe(text):
        return None
    return tuple(sorted(units))


def _prepare_tagged(text, allow_unread):
    # Repair only a printed country marker's Cyrillic lookalike, never names.
    text = re.sub(r'(?<!\w)jр(?=\s*:)', 'jp', text)
    tags = list(_TAG.finditer(text))
    if len(tags) < 2 or len({m.group(1) for m in tags}) < 2:
        return TranslationRows(text)
    chunks = [text[m.end():tags[i+1].start() if i+1 < len(tags) else len(text)].strip()
              for i, m in enumerate(tags)]
    compositions = [_tagged_composition(chunk) for chunk in chunks]
    complete = [c for c in compositions if c is not None]
    if compositions[0] is None or len(complete) < 2 or len(set(complete)) != 1:
        return TranslationRows(text)
    agreed = complete[0]
    required = sorted(number for _, number in agreed)
    fibers = {material for material, _ in agreed}
    unread = False
    for chunk, composition in zip(chunks, compositions):
        if declared_part(chunk):
            return TranslationRows(text)
        if composition is not None:
            continue
        # A different readable fiber, unsupported fiber, extra number, altered
        # percentage or a new Latin name cannot be excused as broken translation.
        values = sorted(Decimal(m.group(1)) for m in _PERCENT.finditer(chunk))
        if (not allow_unread or _unsafe(chunk) or values != required
                or set(extract_materials(chunk)) - fibers
                or re.search(r'[+−~≈<>]|\d\s*,\s*\d', chunk)):
            return TranslationRows(text)
        # All digit tokens must still be the explicit percentages already seen.
        remainder = _PERCENT.sub('', chunk)
        if re.search(r'\d', remainder):
            return TranslationRows(text)
        unread = True
    prefix = text[:tags[0].start()].rstrip()
    result = prefix + '\n' + chunks[0]
    warnings = ('multilingual_translation_rows', 'unread_translation_rows') if unread else ('multilingual_translation_rows',)
    return TranslationRows(result, warnings)


def _prepare_bundles(text, allow_unread):
    lines = text.splitlines()
    result, warnings = [], []
    cursor = 0
    while cursor < len(lines):
        first = _primary(lines[cursor])
        if first is None or not re.match(r'\s*[/\-]', lines[cursor][first[2]:]):
            result.append(lines[cursor])
            cursor += 1
            continue
        material, number, _, alias = first
        end = cursor + 1
        while end < len(lines):
            line = lines[end]
            if (_primary(line) is not None or declared_part(line) or _CARE.search(line)
                    or re.fullmatch(r'[\s|☆○△□×]*\d+[\s|☆○△□×]*', line)):
                break
            # A standalone title unrelated to printed alternatives ends the
            # run. Retain it in the original text for ordinary safety checks.
            if (line.rstrip(' :') not in {'composition', '구성'}
                    and '/' not in line and '-' not in line and not extract_materials(line)):
                break
            end += 1
        body = '\n'.join(lines[cursor:end])
        aliases = [m.group() for m in _TOKEN_PATTERN.finditer(body) if m.group() in ALIAS_TO_MATERIAL]
        values = [Decimal(m.group(1)) for m in _PERCENT.finditer(body)]
        remainder = _PERCENT.sub('', body)
        unread = not _known_remainder(body)
        valid = (len(set(aliases)) >= 2 and set(extract_materials(body)) == {material}
                 and values == [number] and not re.search(r'\d', remainder)
                 and not _unsafe(body) and (end >= len(lines) or not _unsafe(lines[end]))
                 and (allow_unread or not unread)
                 and not re.search(r'[+−~≈<>]|\d\s*,\s*\d', body))
        if valid:
            # Fully readable copies retain their individual evidence rows.
            if unread or end == cursor + 1:
                result.append(f'{number}% {alias}')
            else:
                result.extend(lines[cursor:end])
            warnings.append('multilingual_translation_rows')
            if unread:
                warnings.append('unread_translation_rows')
        else:
            result.extend(lines[cursor:end])
        cursor = end
    return TranslationRows('\n'.join(result), tuple(sorted(set(warnings))))


def is_unverified_translation_row(text):
    """A rejected alternative list cannot fall back to a lax same-line pair."""
    if _primary(text) is None or '/' not in text or _CARE.search(text):
        return False
    return (not _known_remainder(text) or _unsafe(text)
            or bool(re.search(r'\d', _PERCENT.sub('', text))))


def prepare_translation_rows(text, *, allow_unread=False):
    """Normalize repeated declarations with all numbers and part bounds held."""
    text = normalize_text(text)
    tagged = _prepare_tagged(text, allow_unread)
    if tagged.text != text:
        return tagged
    return _prepare_bundles(text, allow_unread)
