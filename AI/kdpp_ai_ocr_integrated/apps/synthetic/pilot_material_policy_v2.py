"""Current label-to-API key contract, independent of the parser and renderer.

Version 2 keeps ``spandex`` and ``polyurethane`` distinct in every language.
Chinese labels render them as 氨纶 and 聚氨酯 respectively.
"""

MATERIAL_LABEL_POLICY = "kdpp-fiber-labels-v2"


def normalize_label_parts(
    parts: dict[str, dict[str, int]], language: str
) -> dict[str, dict[str, int]]:
    """Return independent part dictionaries under the current label policy.

    Return new dictionaries and preserve ratios and part boundaries. Callers
    retain the input as provenance; no parser prediction is used as an answer.
    """
    del language
    return {part: dict(composition) for part, composition in parts.items()}
