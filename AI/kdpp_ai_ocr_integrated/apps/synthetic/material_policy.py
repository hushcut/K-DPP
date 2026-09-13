"""Versioned label-to-API key contract, independent of the parser and renderer.

Chinese 氨纶 uses the existing K-DPP ``polyurethane`` response key. This is a
compatibility convention for fiber labels, not a claim that all polyurethane
materials are spandex. Other languages retain the two separate API keys.
"""

MATERIAL_LABEL_POLICY = "kdpp-fiber-labels-v1"


def normalize_label_parts(
    parts: dict[str, dict[str, int]], language: str
) -> dict[str, dict[str, int]]:
    """Resolve display-key collisions within each part before rendering.

    Return new dictionaries and preserve ratios and part boundaries. Callers
    retain the input as provenance; no parser prediction is used as an answer.
    """
    result = {}
    for part, composition in parts.items():
        normalized = {}
        for material, ratio in composition.items():
            key = "polyurethane" if language == "zh" and material == "spandex" else material
            normalized[key] = normalized.get(key, 0) + ratio
        result[part] = normalized
    return result
