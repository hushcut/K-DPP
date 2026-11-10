"""Remote print never substitutes for an incomplete garment composition."""

from dataclasses import replace

import pytest

from apps.text.ocr_candidates import build_candidate
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import _assess_candidates
from apps.text.parse_label import parse_label
from apps.text.remote_background_recovery import recover_remote_background_number


def box(text, x, y, width, height=40):
    return OcrWord(
        text,
        x,
        y,
        x + width,
        y + height,
        ((x, y), (x + width, y), (x + width, y + height), (x, y + height)),
        0,
    )


def readings(fiber="COTTON", number="08"):
    core = (
        box(fiber, 600, 500, 200),
        box("100%", 850, 500, 80),
        box("MADE IN KOREA", 600, 640, 300),
    )
    crop = (500, 400, 1100, 900)
    result = []
    for source, value, x, y in [
        ("original", number, 100, 1100),
        ("preprocessed", "7" if int(number) == 5 else "5", 250, 1200),
    ]:
        words = core + (
            box(value, x, y, 20, 8),
            box("142", 80, 1050, 24, 8),
            box("Q", 620, 300, 80, 80),
            box("N", 1400, 180, 80, 80),
        )
        text = f"{fiber} 100%\nMADE IN KOREA\n" + "\n".join(w.text for w in words[len(core) :])
        for layout in (False, True):
            result.append(
                replace(
                    build_candidate(source, text, parse_candidate=parse_label, layout_used=layout),
                    image_key="same-image",
                    image_variant_key=source,
                    image_region=(0, 0, 2000, 2000),
                    image_words=words,
                )
            )
    for layout in (False, True):
        result.append(
            replace(
                build_candidate(
                    "material_crop",
                    f"{fiber} 100%\nMADE IN KOREA",
                    parse_candidate=parse_label,
                    layout_used=layout,
                ),
                image_key="same-image",
                image_variant_key="crop",
                image_region=crop,
                image_words=core,
            )
        )
    return result


def changed(item, *, text=None, words=None):
    parsed = build_candidate(
        item.source,
        item.text if text is None else text,
        parse_candidate=parse_label,
        layout_used=item.layout_used,
    )
    return replace(
        parsed,
        image_key=item.image_key,
        image_variant_key=item.image_variant_key,
        image_region=item.image_region,
        image_words=item.image_words if words is None else words,
    )


@pytest.mark.parametrize("fiber", ["COTTON", "WOOL", "ACRYLIC", "POLYESTER"])
@pytest.mark.parametrize("number", ["01", "05", "08", "30", "60", "99"])
def test_same_literal_panel_in_two_full_readings_and_crop_is_kept(fiber, number):
    candidates = readings(fiber, number)
    for source in candidates[:4]:
        assert source.parser_status == "failed"
        assert recover_remote_background_number(source, candidates[-1], "generic", candidates)
    result = _assess_candidates(candidates)
    assert result.status == "success"
    assert result.best.materials == {fiber.lower(): 100}
    assert result.best.selected_part == "generic"
    assert not recover_remote_background_number(candidates[0], candidates[-1], "outer", candidates)


@pytest.mark.parametrize(
    "extra",
    [
        "8%",
        "-20",
        "0/0",
        "0.0",
        "30?",
        "UNKNOWN",
        "OLEFIN 20%",
        "COTTON 20%",
        "LINING",
        "POLYESTER",
        "NOT COTTON",
        "nyon 20%",
    ],
)
def test_other_materials_parts_percentages_and_invalid_values_remain_evidence(extra):
    candidates = readings()
    for index in range(4):
        old = candidates[index]
        candidates[index] = changed(
            old,
            text=old.text + "\n" + extra,
            words=old.image_words + (box(extra, 90, 1400, 100, 8),),
        )
    assert not recover_remote_background_number(
        candidates[0], candidates[-1], "generic", candidates
    )
    assert _assess_candidates(candidates).status != "success"


@pytest.mark.parametrize(
    "defect",
    [
        "no_full_peer",
        "layout_only_peer",
        "same_variant",
        "other_image",
        "other_region",
        "same_number",
        "same_position",
        "missing_crop_raw",
        "crop_raw_mismatch",
        "not_crop",
        "rotated_crop",
        "not_layout",
        "crop_other_image",
        "crop_different_fiber",
        "crop_different_country",
        "crop_moved_country",
        "crop_hidden_word",
        "source_missing_geometry",
        "out_of_bounds",
        "different_page",
        "digit_in_crop",
        "digit_only_below",
        "digit_only_side",
        "digit_full_font",
        "number_with_percent",
        "number_with_decimal",
        "number_zero",
        "second_number",
        "opaque_word",
        "missing_country",
        "bad_region",
    ],
)
def test_geometry_provenance_and_independent_context_are_required(defect):
    candidates = readings()
    raw, target = candidates[0], candidates[-1]
    if defect == "no_full_peer":
        candidates = [c for c in candidates if c.source != "preprocessed"]
    elif defect == "layout_only_peer":
        candidates = [c for c in candidates if c.source != "preprocessed" or c.layout_used]
    elif defect in {"same_variant", "other_image", "other_region"}:
        field, value = {
            "same_variant": ("image_variant_key", raw.image_variant_key),
            "other_image": ("image_key", "other-image"),
            "other_region": ("image_region", (0, 0, 1990, 2000)),
        }[defect]
        candidates = [
            replace(c, **{field: value}) if c.source == "preprocessed" else c for c in candidates
        ]
    elif defect in {"same_number", "same_position"}:
        for index in (2, 3):
            old = candidates[index]
            value = "08" if defect == "same_number" else "5"
            word = (
                box(value, 100, 1100, 20, 8)
                if defect == "same_position"
                else box(value, 250, 1200, 20, 8)
            )
            candidates[index] = changed(
                old,
                text=old.text.replace("5\n", value + "\n"),
                words=tuple(word if w.text == "5" else w for w in old.image_words),
            )
    elif defect == "missing_crop_raw":
        candidates = [c for c in candidates if c.source != "material_crop" or c.layout_used]
    elif defect == "crop_raw_mismatch":
        candidates[-2] = changed(candidates[-2], text="COTTON 90%\nMADE IN KOREA")
    elif defect in {"not_crop", "rotated_crop", "not_layout", "crop_other_image"}:
        field, value = {
            "not_crop": ("source", "preprocessed"),
            "rotated_crop": ("source", "material_crop_rotated"),
            "not_layout": ("layout_used", False),
            "crop_other_image": ("image_key", "different-image"),
        }[defect]
        target = replace(target, **{field: value})
    elif defect in {"crop_different_fiber", "crop_different_country", "crop_hidden_word"}:
        old, new = {
            "crop_different_fiber": ("COTTON", "WOOL"),
            "crop_different_country": ("KOREA", "JAPAN"),
            "crop_hidden_word": ("", "UNKNOWN"),
        }[defect]
        for index in (-2, -1):
            item = candidates[index]
            if old:
                candidates[index] = changed(
                    item,
                    text=item.text.replace(old, new),
                    words=tuple(
                        replace(w, text=w.text.replace(old, new)) for w in item.image_words
                    ),
                )
            else:
                candidates[index] = changed(
                    item,
                    text=item.text + "\n" + new,
                    words=item.image_words + (box(new, 600, 780, 150),),
                )
        target = candidates[-1]
    elif defect == "crop_moved_country":
        for index in (-2, -1):
            item = candidates[index]
            candidates[index] = changed(
                item,
                words=tuple(
                    box(w.text, 600, 780, 300) if "MADE" in w.text else w for w in item.image_words
                ),
            )
        target = candidates[-1]
    elif defect in {
        "source_missing_geometry",
        "different_page",
        "out_of_bounds",
        "digit_in_crop",
        "digit_only_below",
        "digit_only_side",
        "digit_full_font",
    }:
        digit = next(w for w in raw.image_words if w.text == "08")
        replacement = {
            "source_missing_geometry": replace(digit, vertices=()),
            "different_page": replace(digit, page=1),
            "out_of_bounds": box("08", -100, 1100, 20, 8),
            "digit_in_crop": box("08", 600, 800, 20, 8),
            "digit_only_below": box("08", 700, 1100, 20, 8),
            "digit_only_side": box("08", 100, 600, 20, 8),
            "digit_full_font": box("08", 100, 1100, 60, 40),
        }[defect]
        raw = changed(raw, words=tuple(replacement if w is digit else w for w in raw.image_words))
    elif defect in {"number_with_percent", "number_with_decimal", "number_zero"}:
        value = {"number_with_percent": "08%", "number_with_decimal": "8.0", "number_zero": "0"}[
            defect
        ]
        raw = changed(
            raw,
            text=raw.text.replace("08", value),
            words=tuple(replace(w, text=value) if w.text == "08" else w for w in raw.image_words),
        )
    elif defect in {"second_number", "opaque_word"}:
        extra = "7" if defect == "second_number" else "NYON"
        raw = changed(
            raw,
            text=raw.text + "\n" + extra,
            words=raw.image_words + (box(extra, 100, 1400, 50, 8),),
        )
    elif defect == "missing_country":
        raw = changed(
            raw,
            text=raw.text.replace("MADE IN KOREA", "COUNTRY"),
            words=tuple(
                replace(w, text="COUNTRY") if "MADE" in w.text else w for w in raw.image_words
            ),
        )
    elif defect == "bad_region":
        raw = replace(raw, image_region=(0, 0, 800, 800))
    assert not recover_remote_background_number(raw, target, "generic", candidates)


def test_tiny_remote_cjk_print_is_not_a_material_or_an_explicit_part():
    candidates = readings()
    for index in range(4):
        old = candidates[index]
        candidates[index] = changed(
            old,
            text=old.text + "\nもんい",
            words=old.image_words + (box("もんい", 160, 1350, 30, 8),),
        )
    assert recover_remote_background_number(candidates[0], candidates[-1], "generic", candidates)
    for word in ("綿", "裏地", "未知纤维"):
        raw = candidates[0]
        raw = changed(
            raw, text=raw.text + "\n" + word, words=raw.image_words + (box(word, 100, 1400, 30, 8),)
        )
        assert not recover_remote_background_number(raw, candidates[-1], "generic", candidates)
