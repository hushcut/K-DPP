"""A bounded handling cell cannot replace a missing composition or other part."""

from dataclasses import replace
import pytest

from apps.text.bounded_care_band import recover_bounded_care_number
from apps.text.ocr_candidates import build_candidate
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import _assess_candidates
from apps.text.parse_label import parse_label


def box(text, x, y, width, height=30):
    return OcrWord(
        text,
        x,
        y,
        x + width,
        y + height,
        ((x, y), (x + width, y), (x + width, y + height), (x, y + height)),
        0,
    )


def readings(temperature=30, *, heading="취급시 주의사항", source_value=None, target_value=None):
    bad = str(temperature) + "'0" if source_value is None else source_value
    peer = str(temperature) + "0" if target_value is None else target_value

    def build(source, value, layout):
        text = f"겉감 (SHELL)\nACRYLIC 100%\n{heading}\n{value}\n품번: MODEL1234"
        words = (
            box("겉감 (SHELL)", 100, 100, 220),
            box("ACRYLIC", 100, 170, 180),
            box("100%", 400, 170, 100),
            box(heading, 100, 260, 250),
            box(value, 180, 340, 40, 20),
            box("품번: MODEL1234", 100, 430, 300),
        )
        return replace(
            build_candidate(source, text, parse_candidate=parse_label, layout_used=layout),
            image_key="same-photo",
            image_variant_key=source,
            image_region=(0, 0, 1600, 1600),
            image_words=words,
        )

    return build("original", bad, False), build("preprocessed", peer, True)


@pytest.mark.parametrize("temperature", [30, 40, 50, 60, 70, 95])
@pytest.mark.parametrize("heading", ["취급시 주의사항", "세탁시 주의사항", "CARE INSTRUCTIONS"])
def test_located_written_band_and_independent_full_reading_explain_only_the_extra_number(
    temperature, heading
):
    raw, peer = readings(temperature, heading=heading)
    assert raw.parser_status == "failed" and peer.parser_status == "success"
    assert recover_bounded_care_number(raw, peer, "outer")
    assert not recover_bounded_care_number(raw, peer, "lining")
    assert _assess_candidates([raw, peer]).status == "success"
    assert peer.parts == {"outer": {"acrylic": 100}}
    assert raw.observed_ratios == {"outer": [100.0, float(temperature)]}


@pytest.mark.parametrize("value", ["35'0", "30%", "30?0", "30.0", "-30'0", "30'5"])
def test_other_digits_percentages_or_uncertainty_signs_are_not_explained(value):
    raw, peer = readings(source_value=value)
    assert not recover_bounded_care_number(raw, peer, "outer")


def test_mixed_alias_fonts_use_a_shared_direction_without_ignoring_a_bridge_word():
    from math import cos, radians, sin
    from apps.text.bounded_care_band import _bilingual_tail

    angle = radians(4)
    points = tuple(
        (round(210 + x * cos(angle) - y * sin(angle)), round(200 + x * sin(angle) + y * cos(angle)))
        for x, y in ((0, 0), (100, 0), (100, 40), (0, 40))
    )
    xs, ys = zip(*points)
    aliases = (
        box("아크릴", 100, 200, 100, 40),
        OcrWord("ACRYLIC", min(xs), min(ys), max(xs), max(ys), points, 0),
    )
    percentage = (box("100%", 460, 210, 70, 30),)
    assert _bilingual_tail(aliases, percentage, aliases + percentage)
    assert not _bilingual_tail(aliases[-1:], percentage, aliases[-1:] + percentage)
    assert not _bilingual_tail(
        aliases, percentage, aliases + percentage + (box("UNKNOWN", 380, 220, 30, 20),)
    )


@pytest.mark.parametrize("y", [100, 300, 500])
def test_a_ratio_in_another_physical_row_cannot_use_bilingual_font_tolerance(y):
    from apps.text.bounded_care_band import _bilingual_tail

    aliases = (box("아크릴", 100, 200, 100, 40), box("ACRYLIC", 210, 200, 100, 40))
    percentage = (box("100%", 460, y, 70, 30),)
    assert not _bilingual_tail(aliases, percentage, aliases + percentage)


@pytest.mark.parametrize("extra", ["-20", "0/0", "0.0", "30?"])
def test_one_proved_care_cell_cannot_clear_a_second_invalid_numeric_row(extra):
    raw, peer = readings()
    parsed = build_candidate("original", raw.text + "\n" + extra, parse_candidate=parse_label)
    raw = replace(parsed, image_key=raw.image_key, image_variant_key=raw.image_variant_key,
                  image_region=raw.image_region, image_words=raw.image_words + (box(extra,100,600,60),))
    assert not recover_bounded_care_number(raw, peer, "outer")


@pytest.mark.parametrize(
    "defect",
    [
        "image",
        "same_variant",
        "crop",
        "nonlayout",
        "wrong_peer_digit",
        "ratio",
        "material",
        "heading",
        "product",
        "missing_geometry",
        "out_of_bounds",
        "different_page",
        "moved_cell",
        "cell_on_material",
        "product_above_cell",
        "extra_material",
        "other_part",
    ],
)
def test_missing_different_or_unclassified_evidence_cannot_be_waived(defect):
    raw, peer = readings()
    if defect == "image":
        peer = replace(peer, image_key="other")
    elif defect == "same_variant":
        peer = replace(peer, image_variant_key=raw.image_variant_key)
    elif defect == "crop":
        peer = replace(peer, source="material_crop")
    elif defect == "nonlayout":
        peer = replace(peer, layout_used=False)
    elif defect == "wrong_peer_digit":
        raw, peer = readings(target_value="400")
    elif defect == "ratio":
        raw = replace(raw, observed_ratios={"outer": [90.0, 30.0]})
    elif defect == "material":
        raw = replace(raw, observed_materials={"outer": ["cotton"]})
    elif defect in {"heading", "product"}:
        old = "취급시 주의사항" if defect == "heading" else "품번: MODEL1234"
        new = "UNKNOWN" if defect == "heading" else "CODE MODEL1234"

        def changed(item):
            return replace(
                item,
                text=item.text.replace(old, new),
                image_words=tuple(
                    replace(w, text=new) if w.text == old else w for w in item.image_words
                ),
            )

        raw, peer = changed(raw), changed(peer)
    elif defect in {"missing_geometry", "out_of_bounds", "different_page"}:
        words = list(raw.image_words)
        if defect == "missing_geometry":
            words[0] = replace(words[0], vertices=())
        elif defect == "different_page":
            words[0] = replace(words[0], page=1)
        else:
            words[0] = box(words[0].text, -100, 100, 220)
        raw = replace(raw, image_words=tuple(words))
    elif defect in {"moved_cell", "cell_on_material", "product_above_cell"}:
        item = peer if defect == "moved_cell" else raw
        words = list(item.image_words)
        if defect == "moved_cell":
            words[4] = box(words[4].text, 500, 340, 40, 20)
        elif defect == "cell_on_material":
            words[4] = box(words[4].text, 300, 170, 40, 20)
        else:
            words[5] = box(words[5].text, 100, 310, 300)
        if defect == "moved_cell":
            peer = replace(peer, image_words=tuple(words))
        else:
            raw = replace(raw, image_words=tuple(words))
    elif defect == "extra_material":
        raw = replace(
            raw,
            rejected_composition_parts={
                "outer": ("invalid_composition_evidence", "unresolved_material_token")
            },
            observed_materials={"outer": ["acrylic", "olefin"]},
        )
    else:
        peer = replace(peer, parts={"outer": {"acrylic": 100}, "lining": {"cotton": 100}})
    assert not recover_bounded_care_number(raw, peer, "outer")
