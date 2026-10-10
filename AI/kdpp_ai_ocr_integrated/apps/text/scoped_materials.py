"""Read yarn-only labels as auxiliary evidence, never as the garment's shell."""

import re

from apps.text.material_extraction import (
    ALIAS_TO_MATERIAL, NEGATING_MODIFIERS, UNPRICED_MATERIALS,
    declared_part, extract_materials, normalize_text, unresolved_material_tokens,
)


_YARN_HEADING = re.compile(
    r"(?im)^\s*(?:(?:embroidery|자수)\s+)?yarn(?=\s*[/\n:]|\s*$)|"
    r"^\s*자수\s*실(?=\s*[/\n:]|\s*$)"
)
_LANGUAGE = re.compile(
    r"(?<!\w)(?:UK|US|IT|FR|DE|ES-MX|ES|CAT|PT|TR|EL|RU|JP|CN|NL|CZ|DK|"
    r"FI|FL|NO|PL|SK|SE|SI|HR|LT|LV|EE|KR|J[РΡ])\s*:", re.IGNORECASE
)
_CLAUSE = re.compile(r"\s*(100)\s*%\s*(?P<alias>[^\d%]+?)\s*", re.DOTALL)


def _language_material(language: str, alias: str) -> str | None:
    key = " ".join(alias.split())
    material = ALIAS_TO_MATERIAL.get(key)
    if material:
        return material
    # Complete, country-scoped names only. These cannot match a prefix of
    # another polymer or turn an arbitrary foreign word into polyester.
    if language == "RU" and key in {"полиэстер", "полизстер"}:
        return "polyester"
    if language == "EL":
        forms = ("ΠΟΛΥΕΣΤΕΡΑ", "ΠΟΛΥΕΣΤΕΡΑΣ")
        glyphs = {"Π": "ΠП", "Ο": "ΟOО", "Λ": "ΛAА", "Υ": "ΥYУ",
                  "Ε": "ΕEЕ", "Σ": "ΣZ", "Τ": "ΤTТ", "Ρ": "ΡPР", "Α": "ΑAА"}
        upper = key.upper()
        if any(len(upper) == len(form) and all(
                actual in glyphs[expected] for actual, expected in zip(upper, form)) for form in forms):
            return "polyester"
    return None


def read_yarn_materials(text: str) -> dict | None:
    """Keep complete 100%-fiber clauses and retain unreadable translations.

    This is an observation of a different material scope, not a recovery rule
    for primary composition. Unknown clauses are explicitly retained and no
    ratio or material is inferred from another translation.
    """
    heading = _YARN_HEADING.search(text)
    if heading is None:
        return None
    if extract_materials(text[:heading.start()]) or "%" in text[:heading.start()]:
        return None
    language_markers = list(_LANGUAGE.finditer(text, heading.end()))
    clauses = []
    if language_markers:
        for index, marker in enumerate(language_markers):
            end = language_markers[index + 1].start() if index + 1 < len(language_markers) else len(text)
            language = marker.group().strip(" :").upper().replace("Р", "P").replace("Ρ", "P")
            clauses.append((language, text[marker.end():end].strip()))
    else:
        clauses.append(("", text[heading.end():].lstrip(" :\n")))
    observed = []
    unconfirmed = []
    for language, clause in clauses:
        match = _CLAUSE.fullmatch(normalize_text(clause))
        material = _language_material(language, match.group("alias")) if match else None
        if material:
            observed.append({"language": language, "materials": {material: 100}, "text": clause})
        else:
            unconfirmed.append({"language": language, "text": clause})
    if not observed:
        return None
    fibers = {next(iter(item["materials"])) for item in observed}
    prefix = text[:language_markers[0].start()] if language_markers else text[:heading.end()]
    scope = "embroidery_yarn" if re.search(r"(?i)\b(?:embroidery|broderi)\b|자수", prefix) else "yarn"
    return {
        "scope": scope,
        "status": "conflicting" if len(fibers) > 1 else "partial" if unconfirmed else "observed",
        "materials": observed[0]["materials"] if len(fibers) == 1 else {},
        "observations": observed,
        "unconfirmed_clauses": unconfirmed,
        "is_primary_composition": False,
    }


def confirmed_yarn_declaration(text: str) -> tuple[str, dict] | None:
    """Read country-labelled copies as alternatives within the yarn scope.

    A damaged foreign translation is retained, never assigned a fiber. A
    literal Korean declaration can stand on its own only when an English
    declaration and a third language agree. Unknown Latin names, conflicting
    known fibers, extra ratios and uncertainty signs still block selection.
    """
    observed = read_yarn_materials(text)
    if not observed or observed["status"] == "conflicting":
        return None
    observations = observed["observations"]
    first_language = _LANGUAGE.search(text)
    heading = _YARN_HEADING.search(text)
    if first_language is None or heading is None:
        return None
    heading_tail = text[heading.end():first_language.start()]
    if ("%" in heading_tail or extract_materials(heading_tail)
            or unresolved_material_tokens(heading_tail)
            or re.search(r"(?i)\b(?:unknown|unregistered|other|others|olefin|faux|fake|imitation)\b"
                         r"|未知|未登録|미상|불명|기타", heading_tail)
            or any(row.strip(" \t:/") and "/" not in row for row in heading_tail.splitlines())
            or any(declared_part(row) not in {None, "embroidery_yarn"} for row in heading_tail.splitlines())):
        return None
    languages = {item["language"] for item in observations}
    if len(languages) < 2:
        return None
    unconfirmed = observed["unconfirmed_clauses"]
    if unconfirmed:
        if not (languages & {"UK", "US"} and len(languages) >= 3
                and ("KR" in languages or len(languages) >= 4)):
            return None
        for item in unconfirmed:
            clause = normalize_text(item["text"])
            match = _CLAUSE.fullmatch(clause)
            if match is None or item["language"] not in {"JP", "CN", "EL", "RU"}:
                return None
            alias = "".join(match.group("alias").split())
            # Only unreadable non-Latin translation text may remain auxiliary.
            # Never suppress another fiber, part, modifier or opaque Latin word.
            if (not alias.isalpha() or alias.isascii() or len(alias) < 4
                    or re.search(r"[a-z]{2,}", alias)
                    or extract_materials(match.group("alias"))
                    or declared_part(match.group("alias"))
                    or unresolved_material_tokens(match.group("alias"))
                    or any(token in clause for token in NEGATING_MODIFIERS | UNPRICED_MATERIALS)
                    or re.search(r"unknown|unregistered|other|未読|未登録|未知|미상|불명|기타", clause)):
                return None
    # Use the actually readable registered alias, not a guessed translation.
    primary = next((item for item in observations if item["language"] == "KR"), observations[0])
    observed = {**observed, "selected_language": primary["language"],
                "selection_basis": "literal_language_declaration",
                "scope_heading_text": text[:first_language.start()],
                "foreign_translations_unconfirmed": bool(unconfirmed)}
    heading = "EMBROIDERY YARN" if observed["scope"] == "embroidery_yarn" else "YARN"
    return f"{heading}\n{primary['text']}", observed
