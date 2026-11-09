"""Corroborate a malformed numeric OCR cell inside a written handling section."""

from collections import Counter
from dataclasses import dataclass
import math
import re

from apps.text.headed_inline_recovery import _hull, _overlap, _unique_pair, literal_tokens
from apps.text.material_extraction import _material_evidence
from apps.text.ocr_geometry import complete_annotation_geometry, same_place_annotations
from apps.text.ocr_row_search import physical_row_options
from apps.text.single_part_table_recovery import _chain_options


@dataclass(frozen=True)
class _Band:
    core: tuple
    heading: tuple
    product: tuple
    lines: tuple


def _single_row(text, words):
    options = physical_row_options(text, words, tokenise=literal_tokens)
    return tuple(words[i] for i in options[0]) if len(options) == 1 else ()


def _bilingual_tail(aliases, percentage, words):
    """Two registered same-fiber aliases may use different printed fonts.

    Require one shared direction (within three degrees of BOTH top/bottom
    edges), a common physical row and an unobstructed, bounded bridge.
    """
    material = [word for word in aliases if _material_evidence(word.text)]
    if len(material) < 2 or not percentage:
        return False
    left, right = material[-1], percentage[0]
    directions = []
    for word in (left, right):
        a, b, c, d = word.vertices
        for p, q in ((a, b), (d, c)):
            length = math.dist(p, q)
            if not length:
                return False
            directions.append(((q[0] - p[0]) / length, (q[1] - p[1]) / length))
    ux, uy = (sum(row[i] for row in directions) for i in (0, 1))
    length = math.hypot(ux, uy)
    if not length:
        return False
    u, n = (ux / length, uy / length), (-uy / length, ux / length)
    if any(x * u[0] + y * u[1] < math.cos(math.radians(3)) for x, y in directions):
        return False
    frames = []
    for word in (left, right):
        xs = [u[0] * x + u[1] * y for x, y in word.vertices]
        ys = [n[0] * x + n[1] * y for x, y in word.vertices]
        frames.append((min(xs), max(xs), min(ys), max(ys)))
    a, b = frames
    heights = a[3] - a[2], b[3] - b[2]
    if (min(heights) <= 0 or max(heights) > 2 * min(heights)
            or not 0 < b[0] - a[1] <= 6 * max(heights)
            or abs((a[2] + a[3] - b[2] - b[3]) / 2) > .55 * min(heights)):
        return False
    chosen = aliases + percentage
    envelopes = [word.vertices for word in (left, *percentage)]
    # Only the actual end-to-end bridge is relevant. A hull of the entire
    # sloping word would wrongly include a wedge above its printed top edge.
    envelopes.append(_hull((left.vertices[1], left.vertices[2], right.vertices[0], right.vertices[3])))
    return all(word in chosen or not any(_overlap(area, word.vertices) for area in envelopes)
               for word in words)


def _band(view, part, composition):
    from apps.text.parse_label import build_line_infos, parse_label

    if not complete_annotation_geometry(view, literal_tokens):
        return None
    infos = build_line_infos(view.text)
    headings = [i for i in infos if re.sub(r"\s", "", i.normalized)
                in {"취급시주의사항", "취급주의사항", "세탁시주의사항", "careinstructions"}]
    products = [i for i in infos if re.fullmatch(r"품번\s*:\s*[a-z0-9]+(?:-[a-z0-9]+)*", i.normalized)]
    if len(headings) != 1 or len(products) != 1:
        return None
    heading, product = headings[0], products[0]
    if heading.index >= product.index:
        return None
    owners = [i for i in infos if i.marker_part is not None]
    materials = [i for i in infos if i.materials]
    if (len(owners) != 1 or owners[0].marker_part != part or owners[0].materials
            or len(materials) != 1 or materials[0].part != part
            or not owners[0].index < materials[0].index < heading.index
            or any(i.unresolved_materials or i.materials or i.explicit_percent
                   or i.marker_part is not None for i in infos
                   if heading.index < i.index < product.index)):
        return None
    name = materials[0]
    # Retain both printed aliases, but they must all name the same fiber.
    alias_text = re.sub(r"100\s*%", "", name.normalized).strip()
    evidence = _material_evidence(alias_text)
    masked = list(alias_text)
    for item in evidence:
        masked[item.start:item.end] = ' ' * (item.end - item.start)
    if (not evidence or len({item.material for item in evidence}) != 1
            or re.sub(r"[\s(),]", "", ''.join(masked))):
        return None
    # The original declaration itself must contain its explicit percentage.
    percentages = [i for i in infos if '%' in i.normalized]
    percent_rows = [i for i in percentages if name.index <= i.index < heading.index
                    and i.numbers == (100,) and i.explicit_percent]
    if len(percent_rows) != 1 or len(percentages) != 1:
        return None
    if any(i.numbers or i.materials or i.invalid_evidence or i.unresolved_materials
           for i in infos if name.index < i.index < percent_rows[0].index):
        return None
    literal_percentage = re.search(r"100\s*%", percent_rows[0].normalized).group()
    minimal = parse_label(owners[0].raw + '\n' + alias_text + ' ' + literal_percentage)
    if minimal['status'] != 'success' or minimal['parts'] != {part: composition}:
        return None
    words = view.image_words
    alias = _chain_options(alias_text, words)
    percent = _unique_pair(literal_percentage, words)
    owner = _chain_options(owners[0].raw, words)
    title = _single_row(heading.raw, words)
    identifier = _single_row(product.raw, words)
    if not all((alias, percent, owner, title, identifier)):
        return None
    tail_index = max(i for i, word in enumerate(alias) if _material_evidence(word.text))
    tail = _unique_pair(' '.join(w.text for w in alias[tail_index:]) + ' ' + literal_percentage, words)
    if not tail or set(tail) != set(alias[tail_index:] + percent):
        if not _bilingual_tail(alias, percent, words):
            return None
    core = alias + percent
    anchor = max(alias, key=lambda w: math.dist(w.vertices[0], w.vertices[1]))
    a, b, *_ = anchor.vertices
    length = math.dist(a, b)
    normal = (-(b[1] - a[1]) / length, (b[0] - a[0]) / length)
    def centers(group):
        return [sum(normal[0] * x + normal[1] * y for x, y in w.vertices) / 4 for w in group]
    if len(set(core + owner + title + identifier)) != len(core + owner + title + identifier):
        return None
    # A bowed label need not fit one global rectangular band. Every printed
    # cell must still progress down the label without overlapping another row.
    for upper, lower in ((owner, core), (core, title), (title, identifier)):
        if (max(centers(upper)) >= min(centers(lower))
                or any(_overlap(a.vertices, b.vertices) for a in upper for b in lower)):
            return None
    return _Band(core, title, identifier,
                 tuple(i.raw for i in infos if heading.index < i.index < product.index))


def _same_cell(a, b):
    if a.page != b.page:
        return False
    intersection = max(0, min(a.right, b.right) - max(a.left, b.left)) * max(0, min(a.bottom, b.bottom) - max(a.top, b.top))
    area_a, area_b = (a.right - a.left) * (a.bottom - a.top), (b.right - b.left) * (b.bottom - b.top)
    return min(area_a, area_b) > 0 and intersection >= .75 * max(area_a, area_b)


def recover_bounded_care_number(candidate, alternative, part):
    """Use an independent full reading, never a crop silently hiding the cell."""
    if (part != 'outer' or candidate.source != 'original' or candidate.parser_status != 'failed'
            or candidate.parts or candidate.conflicting_parts
            or set(candidate.unpaired_ratio_parts) != {part}
            or candidate.rejected_composition_parts != {part: ('invalid_composition_evidence',)}
            or set(candidate.parser_warnings) != {part + ':invalid_composition_evidence'}
            or alternative.source != 'preprocessed' or not alternative.layout_used
            or alternative.parser_status != 'success' or alternative.parser_warnings
            or alternative.rejected_composition_parts or alternative.unpaired_ratio_parts
            or alternative.conflicting_parts or set(alternative.parts) != {part}
            or len(alternative.parts[part]) != 1 or tuple(alternative.parts[part].values()) != (100,)
            or not candidate.image_key or candidate.image_key != alternative.image_key
            or not candidate.image_variant_key or candidate.image_variant_key == alternative.image_variant_key
            or candidate.image_region != alternative.image_region
            or candidate.observed_materials != alternative.observed_materials
            or set(candidate.observed_ratios) != {part} or set(alternative.observed_ratios) != {part}):
        return False
    raw_ratios, ratios = Counter(candidate.observed_ratios[part]), Counter(alternative.observed_ratios[part])
    extra = list((raw_ratios - ratios).elements())
    if not ratios <= raw_ratios or len(extra) != 1 or extra[0] not in {30, 40, 50, 60, 70, 95}:
        return False
    source = _band(candidate, part, alternative.parts[part])
    target = _band(alternative, part, alternative.parts[part])
    if (source is None or target is None
            or not same_place_annotations(source.core, target.core)
            or not same_place_annotations(source.heading, target.heading)
            or not same_place_annotations(source.product, target.product)):
        return False
    temperature = str(int(extra[0]))
    from apps.text.parse_label import build_line_infos

    # Rejection reasons aggregate rows. Proving one care cell must never
    # waive a second invalid row whose zero/negative value was not retained
    # in observed_ratios.
    invalid = [row for row in build_line_infos(candidate.text) if row.invalid_evidence]
    if len(invalid) != 1 or not re.fullmatch(temperature + r"['’‘]0", invalid[0].normalized):
        return False
    bad = [w for w in candidate.image_words if re.fullmatch(temperature + r"['’‘]0", w.text)]
    peer = [w for w in alternative.image_words if w.text == temperature + '0']
    if len(bad) != 1 or len(peer) != 1 or not _same_cell(bad[0], peer[0]):
        return False
    for band, value in ((source, bad[0]), (target, peer[0])):
        if not (max(w.bottom for w in band.heading) < value.top < value.bottom
                < min(w.top for w in band.product)):
            return False
    # Both literal bands remain available to all other rejection checks. No
    # percentage, fiber or part is repaired or taken from the malformed cell.
    return True
