"""Preserve a complete physical table and its separate, literal care footer."""

from collections import Counter
import re

from apps.text.candidate_evidence import _has_explicit_complete_pairs
from apps.text.care_cell_geometry import care_cell_clear, vertical_care_cell
from apps.text.composition_region_recovery import _literal_pair, _region
from apps.text.ocr_geometry import _row_options


def verified_care_table_layout(raw, layout, *, tokenise):
    """Join only a proved caption/number footer of the SAME provider response.

    No token is removed or repaired. All material/percentage rows must already
    be explicit, unique physical pairs. The resulting text is parsed normally;
    this proof can also release its failed raw view, never a different response.
    """
    from apps.text.ocr_candidates import build_candidate
    from apps.text.parse_label import _WASH_TEMPERATURE_CAPTIONS, build_line_infos, parse_label

    if (raw.layout_used or not layout.layout_used or raw.parser_status != "failed"
            or raw.parts or raw.conflicting_parts or layout.conflicting_parts
            or set(raw.parser_warnings) - {"generic:unpaired_ratio_rows"}
            or set(layout.parser_warnings) - {"generic:unpaired_ratio_rows"}
            or set(raw.rejected_composition_parts) - {"generic"}
            or set(layout.rejected_composition_parts) - {"generic"}
            or set(raw.rejected_composition_parts.get("generic", ())) - {"unpaired_material_rows"}
            or set(layout.rejected_composition_parts.get("generic", ())) - {"unpaired_material_rows"}
            or set(raw.unpaired_ratio_parts) != {"generic"}
            or set(layout.unpaired_ratio_parts) - {"generic"}
            or not raw.image_key or not raw.image_variant_key
            or raw.image_key != layout.image_key or raw.image_variant_key != layout.image_variant_key
            or raw.source != layout.source or raw.image_region != layout.image_region
            or raw.image_words != layout.image_words
            or Counter(tokenise(raw.text)) != Counter(tokenise(layout.text))):
        return None
    rows = [row for row in build_line_infos(layout.text) if row.materials]
    if (not 2 <= len(rows) <= 4
            or any(row.part != "generic" or row.marker_part is not None
                   or len(row.materials) != 1 or len(row.numbers) != 1
                   or not row.explicit_percent or row.invalid_evidence or row.unresolved_materials
                   or not 0 < row.numbers[0] < 100 or not _literal_pair(row, tokenise)
                   for row in rows)
            or len({row.materials[0] for row in rows}) != len(rows)):
        return None
    table = build_candidate(layout.source, "\n".join(row.raw for row in rows),
                            parse_candidate=parse_label, layout_used=True)
    if not _has_explicit_complete_pairs(table) or set(table.parts) != {"generic"}:
        return None
    # Both views account for every annotation. The existing region verifier
    # rejects hidden words, other parts, negation, and ambiguous/swapped rows.
    source, target = _region(raw, rows, tokenise), _region(layout, rows, tokenise)
    if (source is None or target is None or source.footer != target.footer
            or source.groups != target.groups or not target.footer):
        return None
    footer = tokenise(" ".join(target.footer_lines))
    captions = {tokenise(text) for text in _WASH_TEMPERATURE_CAPTIONS | {"手洗イ"}}
    options = [(caption, number) for caption in captions
               for number in ("30", "40", "50", "60", "70", "95")
               if footer == caption + (number,)]
    if len(options) != 1 or tokenise(" ".join(source.footer_lines)) != footer:
        return None
    caption_tokens, number = options[0]
    located = _row_options(" ".join(caption_tokens), target.footer, tokenise=tokenise)
    numbers = [word for word in target.footer if word.text.strip() == number]
    if len(located) != 1 or len(numbers) != 1:
        return None
    caption = tuple(target.footer[i] for i in located[0])
    value = numbers[0]
    if (set(caption + (value,)) != set(target.footer)
            or not vertical_care_cell(caption, value)
            or not care_cell_clear(layout.image_words, caption, value)):
        return None
    names = Counter(table.observed_materials["generic"])
    ratios = Counter(table.observed_ratios["generic"])
    if (set(raw.observed_materials) != {"generic"} or set(raw.observed_ratios) != {"generic"}
            or Counter(raw.observed_materials["generic"]) != names
            or Counter(raw.observed_ratios["generic"]) != ratios + Counter({float(number): 1})):
        return None
    if layout.parser_status == "success":
        if (layout.parts != table.parts or layout.selected_part != "generic"
                or not _has_explicit_complete_pairs(layout)):
            return None
    elif (layout.parser_status != "failed" or layout.parts
          or layout.observed_materials != raw.observed_materials
          or layout.observed_ratios != raw.observed_ratios):
        return None
    lines = [line.strip() for line in layout.text.splitlines() if line.strip()]
    rendered = "\n".join(lines[:-len(target.footer_lines)] + [" ".join(target.footer_lines)])
    # Footer matching allows neither another digit nor a percent sign, unknown
    # caption, uncertainty sign, additional material or second number.
    if (Counter(tokenise(rendered)) != Counter(tokenise(layout.text))
            or re.search(r"[%?？±≈~+\-−]", " ".join(target.footer_lines))):
        return None
    verified = build_candidate(layout.source, rendered, parse_candidate=parse_label, layout_used=True)
    if (not _has_explicit_complete_pairs(verified) or verified.parts != table.parts
            or verified.selected_part != "generic"):
        return None
    return rendered
