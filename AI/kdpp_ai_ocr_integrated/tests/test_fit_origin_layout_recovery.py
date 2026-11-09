"""A fit/origin caption cannot replace or hide physical material evidence."""

from dataclasses import replace
from math import cos, radians, sin

import pytest

from apps.text.ocr_candidates import build_candidate
from apps.text.ocr_corrections import _literal_name_tokens, same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_row_search import physical_row_options
from apps.text.ocr_text import _assess_candidates
from apps.text.parse_label import parse_label
from apps.text.single_row_metadata_recovery import recover_fit_origin_layout


def box(text, x, y, width, angle=0):
    theta = radians(angle)
    vertices = tuple((round(px * cos(theta) - py * sin(theta) + 800),
                      round(px * sin(theta) + py * cos(theta) + 800))
                     for px, py in ((x, y), (x + width, y), (x + width, y + 24), (x, y + 24)))
    xs, ys = zip(*vertices)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), vertices)


def readings(*, angle=0, name="PIMACOTTON", missing_ratio=False, fit="REGULAR FIT", country="PERU",
             identifiers=("RN 12345-CA 67890", "FR 36-US M")):
    lines = [f"100% {name}", fit, f"MADE IN {country}", *identifiers]
    if missing_ratio:
        if any(line.startswith("RN ") for line in identifiers):
            shuffled = [fit, f"MADE IN {country}", name,
                        *(line + " 100 %" if line.startswith("RN ") else line for line in identifiers)]
        else:
            shuffled = [fit, f"MADE IN {country} 100 %", name, *identifiers]
    else:
        shuffled = [f"100 %\nREGULAR {name}\nFIT", f"MADE IN {country}", *identifiers]
        if fit != "REGULAR FIT":
            shuffled = [f"100 %\n{fit} {name}", f"MADE IN {country}", *identifiers]
    words = (box("100", 20, 60, 50, angle), box("%", 80, 60, 32, angle),
             box(name, 200, 60, 200, angle),
             box(fit.split(" ", 1)[0], 20, 160, 120, angle),
             box(fit.split(" ", 1)[1], 160, 160, 150, angle),
             box(f"MADE IN {country}", 20, 260, 320, angle))
    words += tuple(box(line, 20, 360 + i * 100, 450, angle) for i, line in enumerate(identifiers))
    return tuple(replace(
        build_candidate("original", "\n".join(text), parse_candidate=parse_label, layout_used=used),
        image_key="one-label", image_variant_key="one-input", image_words=words,
        image_region=(0, 0, 2400, 2400),
    ) for text, used in ((lines, False), (shuffled, True)))


def recover(raw, layout):
    return recover_fit_origin_layout(layout, raw, "generic", tokenise=_literal_name_tokens)


@pytest.mark.parametrize("angle", [-6, 0, 6, 90, -90])
@pytest.mark.parametrize("name", ["PIMACOTTON", "COTTON", "NYLON"])
@pytest.mark.parametrize("missing_ratio", [False, True])
def test_a_literal_registered_fiber_is_separate_from_its_fit_and_origin(angle, name, missing_ratio):
    raw, layout = readings(angle=angle, name=name, missing_ratio=missing_ratio)
    assert raw.parser_status == "success" and layout.parser_status == "failed"
    if missing_ratio:
        assert not layout.observed_ratios.get("generic")
    assert recover(raw, layout)
    assert same_region_recovery(layout, raw, "generic", [raw, layout])
    decision = _assess_candidates([raw, layout])
    assert decision.status == "success"
    assert decision.best.materials == {"nylon" if name == "NYLON" else "cotton": 100}
    assert decision.best.selected_part == "generic"


@pytest.mark.parametrize("fit", ["REGULAR FIT", "SLIM FIT", "RELAXED FIT", "CLASSIC FIT", "LOOSE FIT", "TAILORED FIT"])
@pytest.mark.parametrize("identifiers", [(), ("RN 12345-CA 67890",), ("FR 36-US M",)])
def test_only_registered_fit_captions_and_optional_labelled_identifiers_are_supported(fit, identifiers):
    raw, layout = readings(fit=fit, identifiers=identifiers, missing_ratio=True)
    assert recover(raw, layout)


@pytest.mark.parametrize("defect", ["image", "variant", "source", "region", "missing_variant", "missing_word",
                                   "changed_digit", "correctable_typo", "extra_material", "extra_ratio",
                                   "other_part", "other_reason"])
def test_recovery_needs_the_same_literal_response_and_preserves_other_evidence(defect):
    raw, layout = readings(missing_ratio=True)
    if defect == "image":
        raw = replace(raw, image_key="different-label")
    elif defect == "variant":
        raw = replace(raw, image_variant_key="different-input")
    elif defect == "source":
        raw = replace(raw, source="preprocessed")
    elif defect == "region":
        raw = replace(raw, image_region=(0, 0, 2399, 2400))
    elif defect == "missing_variant":
        raw = replace(raw, image_variant_key="")
    elif defect == "missing_word":
        raw = replace(raw, image_words=raw.image_words[:-1])
    elif defect == "changed_digit":
        layout = replace(layout, text=layout.text.replace("100", "10"))
    elif defect == "correctable_typo":
        layout = replace(layout, text=layout.text.replace("PIMACOTTON", "PIMAC0TTON"))
    elif defect == "extra_material":
        layout = replace(layout, observed_materials={"generic": ["cotton", "nylon"]})
    elif defect == "extra_ratio":
        layout = replace(layout, observed_ratios={"generic": [100, 5]})
    elif defect == "other_part":
        layout = replace(layout, rejected_composition_parts={"outer": ("unpaired_material_rows",)})
    else:
        layout = replace(layout, rejected_composition_parts={"generic": ("unknown_part",)})
    assert not recover(raw, layout)


@pytest.mark.parametrize("field,value", [
    ("fit", "SILK FIT"), ("fit", "UNKNOWN FIT"), ("fit", "REGULAR FIT 5%"),
    ("country", "UNKNOWN"), ("country", "COTTON"), ("country", "PERU 5%"),
    ("identifiers", ("5%",)), ("identifiers", ("OLEFIN",)),
    ("identifiers", ("LINING COTTON 100%",)), ("identifiers", ("RN 30-CA 70",)),
    ("identifiers", ("40",)), ("identifiers", ("FR 36-US M", "FR 38-US L")),
])
def test_additional_materials_ratios_parts_and_unregistered_metadata_stay_rejected(field, value):
    raw, layout = readings(**{field: value})
    assert not recover(raw, layout)


@pytest.mark.parametrize("index", range(8))
@pytest.mark.parametrize("defect", ["missing", "other_page", "crossing", "in_core"])
def test_all_material_and_metadata_words_need_complete_separate_geometry(index, defect):
    raw, layout = readings(missing_ratio=True)
    words = list(raw.image_words)
    old = words[index]
    if defect == "missing":
        words[index] = replace(old, vertices=())
    elif defect == "other_page":
        words[index] = replace(old, page=1)
    elif defect == "crossing":
        a, b, c, d = old.vertices
        words[index] = replace(old, vertices=(a, b, d, c))
    else:
        shift = 100 if index < 3 else 60 - (old.top - 800)
        points = tuple((x, y + shift) for x, y in old.vertices)
        words[index] = replace(old, top=old.top + shift, bottom=old.bottom + shift, vertices=points)
    raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert not recover(raw, layout)


def test_a_metadata_block_with_another_direction_is_not_the_same_printed_block():
    raw, layout = readings(missing_ratio=True)
    words = tuple(word if index < 3 else box(word.text, word.left - 800, word.top - 800,
                                            word.right - word.left, angle=8)
                  for index, word in enumerate(raw.image_words))
    raw, layout = (replace(item, image_words=words) for item in (raw, layout))
    assert all(len(physical_row_options(line, words, tokenise=_literal_name_tokens)) == 1
               for line in raw.text.splitlines())
    assert not recover(raw, layout)
