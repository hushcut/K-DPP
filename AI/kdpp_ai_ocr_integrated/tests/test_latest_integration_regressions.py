"""Safety and request behavior where the latest OCR changes meet local fixes."""

from dataclasses import replace
from io import BytesIO
import math

from PIL import Image, ImageDraw
import pytest

from apps.text import ocr_text
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_regions import (
    find_complete_material_region, find_material_region, material_region_options,
    prepare_material_region,
)
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates


def _word(text, x, y, width=100, height=20, *, angle=0, page=0):
    radians = math.radians(angle)
    cosine, sine = math.cos(radians), math.sin(radians)
    points = tuple((round(x + cosine * dx - sine * dy), round(y + sine * dx + cosine * dy))
                   for dx, dy in ((0, 0), (width, 0), (width, height), (0, height)))
    return OcrWord(text, min(x for x, _y in points), min(y for _x, y in points),
                   max(x for x, _y in points), max(y for _x, y in points), points, page)


def _candidates(text, words, *, layout="", source="original", variant="original"):
    return _build_payload_candidates(
        source, OcrPayload(text, layout_text=layout, layout_words=words),
        image_key="one-label", image_variant_key=variant,
        image_transform=(1, 0, 0, 0, 1, 0), image_region=(0, 0, 1000, 800),
    )


@pytest.mark.parametrize("unknown", ["인조", "未知繊維", "未知纤维"])
def test_east_asian_semantic_warning_survives_complete_crop_annotations(unknown):
    # The reread is numerically valid and fully located; it cannot remove the
    # original's literal unknown fiber or imitation modifier.
    source_words = (_word("Cotton", 100, 100), _word("90%", 400, 100, 50),
                    _word(unknown, 100, 150), _word("10%", 400, 150, 50))
    target_words = source_words[:2] + (_word("Polyester", 100, 150), source_words[3])
    original = _candidates(f"Cotton 90%\n{unknown} 10%", source_words)
    reread = _candidates("Cotton 90%\nPolyester 10%", target_words,
                         source="material_crop", variant="independent-crop")
    assert original[0].parser_status == "failed"
    assert reread[0].parser_status == "success"
    assert _assess_candidates(original + reread).status == "failed"


def _care_candidates(*, suffix="", page=0, unboxed=""):
    words = (_word("95", 20, 20, 35), _word("%", 60, 20, 15),
             _word("Cotton", 100, 20), _word("5", 20, 70, 30),
             _word("%", 60, 70, 15), _word("Spandex", 100, 70),
             _word("40", 20, 170, 35, page=page), _word("AO", 80, 170, 35, page=page),
             _word("HAND", 20, 220, 60, page=page), _word("WASH", 90, 220, 65, page=page))
    raw = "95% Cotton\n5% Spandex\n40\nAO\nHAND\nWASH"
    layout = "95 % Cotton\n5 % Spandex\n40 AO\nHAND WASH"
    if suffix:
        raw += " " + suffix
        layout += " " + suffix
        words += (_word(suffix, 170, 220, 110, page=page),)
    if unboxed:
        raw += unboxed
        layout += unboxed
    return _candidates(raw, words, layout=layout)


@pytest.mark.parametrize("suffix", ["인조", "未知繊維", "호박섬유", "&", "魚 &"])
def test_same_response_care_resolution_cannot_hide_literal_unknown_care_suffix(suffix):
    candidates = _care_candidates(suffix=suffix)
    assert candidates[0].parser_status == "failed"
    assert _assess_candidates(candidates).status == "failed"


def test_same_response_care_and_composition_on_different_pages_remain_unconfirmed():
    candidates = _care_candidates(page=1)
    assert candidates[0].parser_status == "failed"
    assert _assess_candidates(candidates).status == "failed"


@pytest.mark.parametrize("unboxed", ["&", "+", "魚"])
def test_same_response_care_resolution_requires_every_literal_annotation(unboxed):
    candidates = _care_candidates(unboxed=unboxed)
    assert candidates[0].parser_status == "failed"
    assert _assess_candidates(candidates).status == "failed"


def test_ocr_aliases_of_one_physical_word_do_not_supply_two_rotation_supporters():
    cotton = _word("Cotton", 200, 200, 140, 20, angle=6)
    translated = replace(cotton, text="Coton", left=cotton.left + 1, right=cotton.right + 1)
    original = _candidates("Cotton 100%", (cotton,))[0]
    reread = _candidates("Coton 100%", (translated,), source="preprocessed", variant="processed")[0]
    # Two OCR spellings still describe only one observed baseline.
    for candidates in ([original, reread], [reread, original]):
        assert material_region_options(candidates, (100, 100, 600, 400))[1] == -3


@pytest.mark.parametrize("magnitude", [0.5, 1.5, 2.5, 3.5, 4.5])
@pytest.mark.parametrize("sign", [-1, 1])
def test_nearly_horizontal_baselines_keep_reread_perturbation_and_font_measurement(magnitude, sign):
    words = (_word("Cotton", 200, 200, 300, 20, angle=sign * magnitude),
             _word("Spandex", 200, 280, 300, 20, angle=sign * magnitude))
    candidates = _candidates("Cotton 95%\nSpandex 5%", words)
    for readings in (candidates, list(reversed(candidates))):
        height, correction = material_region_options(readings, (100, 100, 700, 450))
        assert correction == -3
        assert height == pytest.approx(20, abs=1)


@pytest.mark.parametrize("sign", [-1, 1])
def test_five_degree_baselines_use_supported_deskew_with_font_measurement(sign):
    words = (_word("Cotton", 200, 200, 300, 20, angle=sign * 5),
             _word("Spandex", 200, 280, 300, 20, angle=sign * 5))
    height, correction = material_region_options(
        _candidates("Cotton 95%\nSpandex 5%", words), (100, 100, 700, 450),
    )
    assert correction == pytest.approx(sign * 5, abs=0.5)
    assert height == pytest.approx(20, abs=1)


def _map_to_input(words, transform):
    a, b, c, d, e, f = transform
    determinant = a * e - b * d
    mapped = []
    for word in words:
        points = tuple((round((e * (x - c) - b * (y - f)) / determinant),
                        round((-d * (x - c) + a * (y - f)) / determinant))
                       for x, y in word.vertices)
        mapped.append(replace(word, vertices=points, left=min(x for x, _y in points),
                              top=min(y for _x, y in points), right=max(x for x, _y in points),
                              bottom=max(y for _x, y in points)))
    return tuple(mapped)


def _adaptive_early_pipeline(monkeypatch, *, clock=None, observed_angle=6):
    text = "Polyester 5%\nRayon 21%\nSpan 4%"
    words = tuple(word for name, number, y in (
        ("Polyester", "5%", 300), ("Rayon", "21%", 345), ("Span", "4%", 390),
    ) for word in (_word(name, 240, y, 130, 12, angle=observed_angle), _word(number, 640, y, 55, 24)))
    initial = _candidates(text, words)
    region = find_material_region(initial, 1000, 800)
    assert region is not None
    heading = _word("1 세탁 시 주의 사항 ]", 400, region[3] - 8, 250, 24)
    words += (heading,)
    text += "\n1 세탁 시 주의 사항 ]"
    initial = _candidates(text, words)
    region = find_material_region(initial, 1000, 800)
    assert region is not None
    complete = find_complete_material_region(initial, region)
    assert complete is not None
    height, angle = material_region_options(initial, complete)
    assert height is not None
    image = Image.new("RGB", (1000, 800), "white")
    draw = ImageDraw.Draw(image)
    for word in words:
        draw.polygon(word.vertices, fill="black")
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    content = buffer.getvalue()
    processed = ocr_text.preprocess_image_bytes(content)
    frame = ocr_text.ocr_coordinate_frame(content, processed, "preprocessed")[0]
    payloads = {
        content: ("original", OcrPayload(text, layout_words=words)),
        processed: ("preprocessed", OcrPayload(text, layout_words=_map_to_input(words, frame))),
    }
    crops = []
    calls = []
    actual_prepare = prepare_material_region

    def prepare(data, box, **kwargs):
        crop = actual_prepare(data, box, **kwargs)
        crops.append((crop, kwargs))
        payloads[crop.content] = (crop.source, OcrPayload(
            "Polyester 5%\nRayon 21%\nSpan 4%", layout_words=_map_to_input(words[:6], crop.transform)))
        if clock is not None:
            clock[0] = 24.0
        return crop

    def provider(_client, data, *, timeout_seconds):
        source, payload = payloads[data]
        calls.append((source, timeout_seconds))
        if clock is not None and source == "material_crop_rotated":
            clock[0] = 25.0
        return payload

    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_args: object())
    monkeypatch.setattr(ocr_text, "_resolve_credential_path", lambda *_args: (None, None))
    monkeypatch.setattr(ocr_text, "_run_google_ocr", provider)
    monkeypatch.setattr(ocr_text, "prepare_material_region", prepare)
    if clock is not None:
        monkeypatch.setattr(ocr_text.time, "monotonic", lambda: clock[0])
    return content, calls, crops, height, angle


def test_early_complete_region_keeps_adaptive_enlargement_rotation_and_four_request_ceiling(monkeypatch):
    content, calls, crops, height, angle = _adaptive_early_pipeline(monkeypatch)
    assert angle == pytest.approx(6, abs=0.5)
    result = ocr_text.run_ocr_bytes(content, enable_material_region=True,
                                  enable_reflection=False, enable_denoised=False, enable_rotated=False)
    assert [source for source, _timeout in calls] == [
        "original", "material_crop_rotated", "preprocessed", "material_crop",
    ]
    assert result.metadata.external_call_count == 4
    assert result.metadata.attempt_count == 4
    assert len(crops) == 2
    early, kwargs = crops[0]
    assert kwargs["font_height"] == pytest.approx(height)
    assert kwargs["rotation_degrees"] == pytest.approx(angle)
    baseline = prepare_material_region(content, tuple(int(value) for value in early.region), rotated=True)
    with Image.open(BytesIO(early.content)) as adaptive, Image.open(BytesIO(baseline.content)) as old:
        assert adaptive.width > old.width
    assert all(0 < timeout <= 10 for _source, timeout in calls)


@pytest.mark.parametrize("sign", [-1, 1])
def test_nearly_horizontal_early_region_keeps_enlargement_and_four_distinct_requests(monkeypatch, sign):
    content, calls, crops, height, angle = _adaptive_early_pipeline(
        monkeypatch, observed_angle=sign * 3.5,
    )
    assert angle == -3
    result = ocr_text.run_ocr_bytes(content, enable_material_region=True,
                                  enable_reflection=False, enable_denoised=False, enable_rotated=False)
    assert [source for source, _timeout in calls] == [
        "original", "material_crop_rotated", "preprocessed", "material_crop",
    ]
    assert result.metadata.external_call_count == result.metadata.attempt_count == 4
    assert len(crops) == 2
    early, kwargs = crops[0]
    assert kwargs["rotation_degrees"] == -3
    assert kwargs["font_height"] == pytest.approx(height)
    box = tuple(int(value) for value in early.region)
    expected = prepare_material_region(content, box, rotated=True,
                                       font_height=height, rotation_degrees=-3)
    assert early.content == expected.content
    unscaled = prepare_material_region(content, box, rotated=True)
    with Image.open(BytesIO(early.content)) as enlarged, Image.open(BytesIO(unscaled.content)) as baseline:
        assert enlarged.width > baseline.width
    inputs = {content, ocr_text.preprocess_image_bytes(content)}
    inputs.update(crop.content for crop, _options in crops)
    assert len(inputs) == 4


def test_adaptive_early_crop_uses_remaining_total_budget_before_any_fallback(monkeypatch):
    content, calls, crops, _height, _angle = _adaptive_early_pipeline(monkeypatch, clock=[0.0])
    result = ocr_text.run_ocr_bytes(content, enable_material_region=True,
                                  enable_reflection=False, enable_denoised=False, enable_rotated=False)
    assert [source for source, _timeout in calls] == ["original", "material_crop_rotated"]
    assert calls[1][1] == pytest.approx(1.0)
    assert len(crops) == 1
    assert result.metadata.external_call_count == 2
    assert "preprocessed:total_timeout" in result.metadata.attempt_failures
    assert all(attempt.outcome == "skipped" for attempt in result.metadata.attempts[2:])
