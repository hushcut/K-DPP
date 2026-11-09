"""Literal footer regrouping must never discard composition evidence."""

from collections import Counter
from dataclasses import replace
import math

import pytest

from apps.text.ocr_candidates import build_candidate
from apps.text.ocr_corrections import _literal_name_tokens, same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates
from apps.text.parse_label import parse_label
from apps.text.table_care_recovery import verified_care_table_layout


def box(text, x, y, width, *, angle=0, height=20):
    theta = math.radians(angle)
    vertices = tuple((round(px * math.cos(theta) - py * math.sin(theta) + 800),
                      round(px * math.sin(theta) + py * math.cos(theta) + 800))
                     for px, py in ((x, y), (x + width, y), (x + width, y + height), (x, y + height)))
    xs, ys = zip(*vertices)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), vertices, 0)


def readings(*, ratios=(60, 35, 5), number="30", angle=0, extra=""):
    names = ["POLYESTER", "RAYON", "POLYURETHANE"]
    pairs = [f"{name} {ratio}%" for name, ratio in zip(names, ratios)]
    raw = ["品質表示"] + [line for name, ratio in zip(names, ratios) for line in (name, f"{ratio}%")]
    raw += ["手洗イ", number] + ([extra] if extra else [])
    layout = ["品質表示"] + pairs + ["手洗", "イ", number] + ([extra] if extra else [])
    words = (box("品質表示", 20, 20, 150, angle=angle),)
    words += tuple(word for i, (name, ratio) in enumerate(zip(names, ratios)) for word in (
        box(name, 20, 100 + 90 * i, 200, angle=angle),
        box(str(ratio), 300, 100 + 90 * i, 40, angle=angle),
        box("%", 350, 100 + 90 * i, 20, angle=angle)))
    words += (box("手洗", 20, 430, 80, angle=angle), box("イ", 100, 430, 30, angle=angle),
              box(number, 50, 470, 40, angle=angle))
    if extra:
        words += (box(extra, 20, 540, 200, angle=angle),)
    def candidate(text, used):
        return replace(build_candidate("material_crop", "\n".join(text),
                                       parse_candidate=parse_label, layout_used=used),
                       image_key="one-photo", image_variant_key="one-response",
                       image_region=(0, 0, 2400, 2400), image_words=words)
    return candidate(raw, False), candidate(layout, True)


def render(raw, layout):
    return verified_care_table_layout(raw, layout, tokenise=_literal_name_tokens)


@pytest.mark.parametrize("angle", [-90, -6, 0, 6, 90])
@pytest.mark.parametrize("ratios", [(60, 35, 5), (62.5, 32.5, 5), (60, 30, 10)])
def test_complete_physical_pairs_and_separate_care_cell_keep_every_token(angle, ratios):
    raw, layout = readings(angle=angle, ratios=ratios)
    assert raw.parser_status == layout.parser_status == "failed"
    text = render(raw, layout)
    assert text is not None
    assert Counter(_literal_name_tokens(text)) == Counter(_literal_name_tokens(raw.text))
    verified = replace(build_candidate(layout.source, text, parse_candidate=parse_label, layout_used=True),
                       image_key=layout.image_key, image_variant_key=layout.image_variant_key,
                       image_words=layout.image_words, image_region=layout.image_region)
    assert verified.materials == dict(zip(("polyester", "rayon", "polyurethane"), ratios))
    assert same_region_recovery(raw, verified, "generic", [raw, verified])
    assert not same_region_recovery(raw, verified, "outer", [raw, verified])
    assert _assess_candidates([raw, verified]).status == "success"
    assert raw.observed_ratios["generic"] == [*ratios, 30.0]


def test_payload_path_keeps_the_raw_response_and_uses_normal_parser_validation():
    raw, layout = readings()
    payload = OcrPayload(raw.text, layout_text=layout.text, layout_words=raw.image_words)
    candidates = _build_payload_candidates(
        raw.source, payload, image_key=raw.image_key, image_variant_key=raw.image_variant_key,
        image_transform=(1, 0, 0, 0, 1, 0), image_region=raw.image_region)
    assert len(candidates) == 2 and candidates[0].text == raw.text
    assert _assess_candidates(candidates).status == "success"
    assert candidates[1].selected_part == "generic"


@pytest.mark.parametrize("extra", ["UNKNOWN", "OLEFIN", "COTTON 5%", "OUTER COTTON 100%",
                                   "40", "30%", "?", "素材", "COMPOSITION"])
def test_no_other_footer_word_ratio_part_or_section_is_silenced(extra):
    assert render(*readings(extra=extra)) is None


@pytest.mark.parametrize("number", ["35", "30%", "-30", "30?", "30.5", "300", "3O"])
def test_only_a_literal_supported_bare_temperature_is_considered(number):
    assert render(*readings(number=number)) is None


@pytest.mark.parametrize("ratios", [(60, 35, 4), (60, 35, 30), (60, 35, 0)])
def test_incomplete_or_inconsistent_compositions_are_never_completed(ratios):
    assert render(*readings(ratios=ratios)) is None


@pytest.mark.parametrize("defect", ["image", "variant", "source", "missing_key", "words", "region",
                                    "page", "polygon", "extra_annotation", "duplicate"])
def test_same_response_complete_bounded_annotation_proof_is_required(defect):
    raw, layout = readings()
    if defect in {"image", "variant", "source", "missing_key", "region"}:
        changes = {"image": {"image_key": "other"}, "variant": {"image_variant_key": "other"},
                   "source": {"source": "original"}, "missing_key": {"image_key": ""},
                   "region": {"image_region": (0, 0, 2401, 2400)}}[defect]
        layout = replace(layout, **changes)
    else:
        words = raw.image_words
        if defect == "words":
            words = words[:-1]
        elif defect == "page":
            words = (replace(words[0], page=1),) + words[1:]
        elif defect == "polygon":
            words = (replace(words[0], vertices=()),) + words[1:]
        elif defect == "extra_annotation":
            words += (box("MYSTERY", 30, 460, 50),)
        else:
            words += (words[-1],)
        raw, layout = replace(raw, image_words=words), replace(layout, image_words=words)
    assert render(raw, layout) is None


@pytest.mark.parametrize("number_y", [100, 430, 450, 550])
def test_number_cannot_belong_to_a_fiber_row_or_overlap_or_float_away(number_y):
    raw, layout = readings()
    words = tuple(box("30", 50, number_y, 40) if word.text == "30" else word for word in raw.image_words)
    assert render(replace(raw, image_words=words), replace(layout, image_words=words)) is None


def test_a_percent_is_not_attached_to_a_different_physical_fiber():
    raw, layout = readings()
    positions = {"60": 190, "35": 100}
    words = tuple(box(word.text, 300, positions[word.text], 40) if word.text in positions else word
                  for word in raw.image_words)
    assert render(replace(raw, image_words=words), replace(layout, image_words=words)) is None


@pytest.mark.parametrize("caption", ["手洗?", "手", "UNKNOWN", "DRY CLEAN", "NOT COTTON"])
def test_an_incomplete_unknown_or_negated_caption_cannot_explain_the_number(caption):
    raw, layout = readings()
    def altered(item):
        text = item.text.replace("手洗", caption)
        words = tuple(replace(word, text=caption) if word.text == "手洗" else word for word in item.image_words)
        return replace(build_candidate(item.source, text, parse_candidate=parse_label, layout_used=item.layout_used),
                       image_key=item.image_key, image_variant_key=item.image_variant_key,
                       image_words=words, image_region=item.image_region)
    assert render(altered(raw), altered(layout)) is None
