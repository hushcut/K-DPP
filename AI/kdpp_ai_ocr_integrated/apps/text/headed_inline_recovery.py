"""Verify a literal headed blend against its unchanged original annotations."""

from collections import Counter
import math
import re
import unicodedata

from apps.text.material_extraction import _material_evidence, normalize_text
from apps.text.ocr_geometry import _physical_row, _row_options, complete_annotation_geometry


def literal_tokens(text):
    return tuple(re.findall(
        r"[가-힣一-龥ぁ-んァ-ンー]|[^\W\d_가-힣一-龥ぁ-んァ-ンー]+|\d+|[^\w\s]",
        unicodedata.normalize("NFKC", text).casefold(),
    ))


def _pixel_rounded_pair(text, words):
    """Keep the existing 3-degree limit plus one pixel on BOTH word edges.

    This local proof is confined to complete literal fiber/percent pairs.
    Polygon validity, provenance and image bounds are checked by the caller.
    No vertex, token, percentage or other row is repaired here.
    """
    if _physical_row(text, words, tokenise=literal_tokens):
        return True
    if not words or len(words) > 8:
        return False
    frames = []
    cosine, sine = math.cos(math.radians(3)), math.sin(math.radians(3))
    for word in words:
        a, b, c, d = word.vertices
        top, bottom = math.dist(a, b), math.dist(d, c)
        if min(top, bottom) < 16:
            return False
        u = ((b[0] - a[0]) / top, (b[1] - a[1]) / top)
        v = ((c[0] - d[0]) / bottom, (c[1] - d[1]) / bottom)
        if u[0] * v[0] + u[1] * v[1] < cosine:
            return False
        frames.append((top, bottom, u, v, word))
    anchor = max(frames, key=lambda row: row[0])
    if anchor[0] < 64:
        return False
    direction = anchor[2]
    normal = (-direction[1], direction[0])
    projected = []
    for top, bottom, u, v, word in frames:
        if any(direction[0] * edge[0] + direction[1] * edge[1] <= 0 for edge in (u, v)):
            return False
        if (abs(normal[0] * u[0] + normal[1] * u[1]) * top > sine * top + 1
                or abs(normal[0] * v[0] + normal[1] * v[1]) * bottom > sine * bottom + 1):
            return False
        ys = [normal[0] * x + normal[1] * y for x, y in word.vertices]
        xs = [direction[0] * x + direction[1] * y for x, y in word.vertices]
        projected.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), word))
    if any(abs(a[0] - b[0]) > max(2, .55 * min(a[1], b[1]))
           for a in projected for b in projected):
        return False
    return tuple(token for *_rest, word in sorted(projected, key=lambda row: row[2])
                 for token in literal_tokens(word.text)) == literal_tokens(text)


def _hull(points):
    points = sorted(set(points))
    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    lower, upper = [], []
    for chain, ordered in ((lower, points), (upper, reversed(points))):
        for point in ordered:
            while len(chain) >= 2 and cross(chain[-2], chain[-1], point) <= 0:
                chain.pop()
            chain.append(point)
    return tuple(lower[:-1] + upper[:-1])


def _overlap(left, right):
    """Use the actual convex polygons; axis-aligned boxes mix tilted rows."""
    for polygon in (left, right):
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            length = math.dist(a, b)
            if not length:
                return True  # Invalid geometry must not prove separation.
            nx, ny = -(b[1] - a[1]) / length, (b[0] - a[0]) / length
            first = [nx * x + ny * y for x, y in left]
            second = [nx * x + ny * y for x, y in right]
            if min(max(first), max(second)) - max(min(first), min(second)) <= 2:
                return False
    return True


def _pair_options(text, words):
    def isolated(selected):
        envelope = _hull(point for word in selected for point in word.vertices)
        return all(word in selected or re.fullmatch(r"[-,:;/]+", word.text.strip())
                   or not _overlap(envelope, word.vertices) for word in words)

    return [tuple(words[i] for i in indices)
            for indices in _row_options(text, words, tokenise=literal_tokens)
            if _pixel_rounded_pair(text, tuple(words[i] for i in indices))
            and isolated(tuple(words[i] for i in indices))]


def _unique_pair(text, words):
    options = _pair_options(text, words)
    return options[0] if len(options) == 1 else ()


def literal_headed_blend_over_failed_layout(raw, layout):
    """Discard only a shuffled view of one physically proved headed blend."""
    from apps.text.parse_label import build_line_infos, _read_numbers

    if (raw.source != "original" or raw.layout_used or not layout.layout_used
            or raw.parser_status != "success" or layout.parser_status != "failed"
            or layout.parts or layout.conflicting_parts
            or raw.rejected_composition_parts or raw.unpaired_ratio_parts or raw.conflicting_parts
            or raw.selected_part != "generic" or set(raw.parts) != {"generic"}
            or len(raw.parts["generic"]) != 2
            or raw.source != layout.source or raw.image_key != layout.image_key
            or raw.image_variant_key != layout.image_variant_key
            or raw.image_region != layout.image_region or raw.image_words != layout.image_words
            or Counter(literal_tokens(raw.text)) != Counter(literal_tokens(layout.text))
            or not complete_annotation_geometry(raw, literal_tokens)
            or not complete_annotation_geometry(layout, literal_tokens)
            or set(layout.observed_materials) - {"generic"}
            or set(layout.observed_ratios) - {"generic"}
            or set(layout.rejected_composition_parts) - {"generic", "embroidery_yarn"}
            or not layout.rejected_composition_parts.get("generic")
            or set(layout.rejected_composition_parts["generic"])
            - {"invalid_composition_evidence", "unpaired_material_rows"}
            or Counter(layout.observed_materials.get("generic", ()))
            != Counter(raw.observed_materials.get("generic", ()))
            or Counter(layout.observed_ratios.get("generic", ()))
            != Counter(raw.observed_ratios.get("generic", ()))):
        return False
    infos = build_line_infos(raw.text)
    rows = [info for info in infos if info.materials or "%" in info.normalized]
    if (len(rows) != 1 or any(info.marker_part or info.unresolved_materials for info in infos)):
        return False
    info = rows[0]
    line = normalize_text(info.raw)
    materials = _material_evidence(line)
    _, invalid, explicit, numbers = _read_numbers(line, allow_plain_numbers=False)
    if (len(materials) != 2 or len(numbers) != 2 or invalid or not explicit
            or info.invalid_evidence or not all(0 < n.value < 100 for n in numbers)
            or not (materials[0].end <= numbers[0].start < numbers[0].end <= materials[1].start
                    and materials[1].end <= numbers[1].start)
            or Counter(zip(info.materials, map(float, info.numbers))) != Counter(raw.parts["generic"].items())):
        return False
    heading = line[:materials[0].start]
    if not re.fullmatch(r"\s*-?\s*(?:소재|혼용률|혼용율|composition|fabric content)\s*:\s*", heading):
        return False
    if (line[numbers[1].end:].strip()
            or not re.fullmatch(r"[\s,;/]*", line[numbers[0].end:materials[1].start])):
        return False
    pairs = [line[m.start:n.end] for m, n in zip(materials, numbers)]
    groups = [_unique_pair(heading.lstrip(" -"), raw.image_words)]
    groups.extend(_unique_pair(pair, raw.image_words) for pair in pairs)
    if not all(groups) or len({word for group in groups for word in group}) != sum(map(len, groups)):
        return False
    # A swapped literal percentage must not be an equally plausible pair.
    for i, m in enumerate(materials):
        if numbers[0].value != numbers[1].value:
            swapped = line[m.start:m.end] + " " + line[numbers[1 - i].start:numbers[1 - i].end]
            if _pair_options(swapped, raw.image_words):
                return False
    for left, right in zip(groups, groups[1:]):
        if max(w.right for w in left) > min(w.left for w in right) + 2:
            return False
        lo = max(min(w.top for w in left), min(w.top for w in right))
        hi = min(max(w.bottom for w in left), max(w.bottom for w in right))
        height = min(max(w.bottom for w in group) - min(w.top for w in group) for group in (left, right))
        if hi - lo < .5 * height:
            return False
    core = {word for group in groups for word in group}
    # Follow the proved local cells across the curved row. A single convex
    # hull around the entire row also encloses unrelated text above/below
    # its bend. The short bridges still protect every gap between cells.
    envelopes = [_hull(point for word in group for point in word.vertices) for group in groups]
    envelopes.extend(_hull(point for word in (max(left, key=lambda w: w.center_x),
                                            min(right, key=lambda w: w.center_x))
                           for point in word.vertices) for left, right in zip(groups, groups[1:]))
    # Every opaque word, number, part or extra fiber inside the composition
    # envelope remains evidence. Only literal separator punctuation is exempt.
    return all(word in core or re.fullmatch(r"[-,:;/]+", word.text.strip())
               or not any(_overlap(envelope, word.vertices) for envelope in envelopes)
               for word in raw.image_words)
