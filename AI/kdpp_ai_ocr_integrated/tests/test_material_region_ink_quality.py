"""Pixel quality may select a reread filter, but cannot replace OCR evidence."""

from collections import deque
from dataclasses import replace
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from apps.text import ocr_regions, ocr_text
from apps.text.ocr_errors import OcrUnavailableError
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_regions import (
    _material_ink_threshold, material_region_word_boxes, prepare_material_region,
)
from apps.text.ocr_text import OcrPayload, _build_payload_candidates, run_ocr_bytes
from apps.text.parse_label import parse_label


CANVAS = (800, 600)
REGION = (80, 90, 640, 430)
BOUNDS = ((150, 170, 230, 202), (370, 270, 455, 306))
EXTRA_BOUNDS = (530, 355, 600, 395)


def _word(text, bounds, *, page=0):
    left, top, right, bottom = bounds
    vertices = ((left, top), (right, top), (right, bottom), (left, bottom))
    return OcrWord(text, left, top, right, bottom, vertices, page=page)


def _readings(words):
    return _build_payload_candidates(
        "original", OcrPayload("\n".join(word.text for word in words), layout_words=tuple(words)),
        image_key="synthetic-label", image_variant_key="original-pixels",
        image_transform=(1, 0, 0, 0, 1, 0), image_region=(0, 0, *CANVAS),
    )


def _stroke(draw, bounds, ink):
    left, top, right, bottom = bounds
    painted = (left + 6, top + 5, left + (right - left) // 3, bottom - 6)
    draw.rectangle(painted, fill=ink)
    return painted


def _scene(*, ink=25, background=245, bounds=BOUNDS):
    image = Image.new("L", CANVAS, background)
    draw = ImageDraw.Draw(image)
    markers = tuple(_stroke(draw, box, ink) for box in bounds)
    return image, markers


def _encoded(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _threshold(image, bounds=BOUNDS):
    return _material_ink_threshold(image.crop(REGION), REGION, tuple(bounds))


@pytest.mark.parametrize("ink", [25, 160])
def test_complete_ink_observations_choose_quality_without_a_specific_black_level(ink):
    image, _markers = _scene(ink=ink)
    assert isinstance(_threshold(image), int)


@pytest.mark.parametrize("text", ["UNKNOWN", "41", "%", "-", "0.5"])
@pytest.mark.parametrize("damage", ["faint", "covered", "shadow"])
def test_every_observed_context_digit_and_sign_must_survive_the_selected_mask(text, damage):
    image, _markers = _scene()
    words = [_word("Cotton", BOUNDS[0]), _word("Span", BOUNDS[1]), _word(text, EXTRA_BOUNDS)]
    draw = ImageDraw.Draw(image)
    if damage == "faint":
        _stroke(draw, EXTRA_BOUNDS, 225)
    elif damage == "covered":
        draw.rectangle(EXTRA_BOUNDS, fill=25)
    else:
        left, top, right, bottom = EXTRA_BOUNDS
        draw.rectangle((left - 7, top - 7, right + 7, bottom + 7), fill=25)
        draw.rectangle(EXTRA_BOUNDS, fill=245)
        _stroke(draw, EXTRA_BOUNDS, 25)
    observed = material_region_word_boxes(_readings(words), REGION)
    assert EXTRA_BOUNDS in observed
    assert _threshold(image, observed) is None


def test_uniform_images_do_not_supply_evidence_of_preserved_glyphs():
    assert _threshold(Image.new("L", CANVAS, 127)) is None


def test_filter_selection_uses_same_observed_geometry_after_material_text_changes():
    image, _markers = _scene()
    replacement = ("UNKNOWN", "-0.5%")
    original = material_region_word_boxes(_readings([_word("Cotton", BOUNDS[0]), _word("Span", BOUNDS[1])]), REGION)
    renamed = material_region_word_boxes(_readings([_word(text, box) for text, box in zip(replacement, BOUNDS, strict=True)]), REGION)
    assert renamed == original == BOUNDS
    assert _threshold(image, renamed) == _threshold(image, original)
    first = prepare_material_region(_encoded(image), REGION, rotated=True, word_boxes=original)
    second = prepare_material_region(_encoded(image), REGION, rotated=True, word_boxes=renamed)
    assert (first.content, first.transform, first.region) == (second.content, second.transform, second.region)


@pytest.mark.parametrize("defect", ["no_frame", "no_input_variant", "different_image"])
def test_pixel_observations_require_a_verified_shared_image_frame(defect):
    readings = _readings([_word("Cotton", BOUNDS[0]), _word("Span", BOUNDS[1])])
    if defect == "no_frame":
        readings = [replace(readings[0], image_region=())]
    elif defect == "no_input_variant":
        readings = [replace(readings[0], image_variant_key="")]
    else:
        readings += [replace(readings[0], image_key="other-image")]
    assert material_region_word_boxes(readings, REGION) == ()


def test_partial_and_other_page_words_do_not_change_the_existing_crop_region():
    image, _markers = _scene()
    words = [_word("Cotton", BOUNDS[0]), _word("Span", BOUNDS[1]),
             _word("UNKNOWN", (60, 330, 100, 370)), _word("OTHER", EXTRA_BOUNDS, page=1)]
    observed = material_region_word_boxes(_readings(words), REGION)
    assert observed == BOUNDS
    prepared = prepare_material_region(_encoded(image), REGION, rotated=True, word_boxes=observed)
    assert prepared.region == tuple(float(value) for value in REGION)


@pytest.mark.parametrize("shift", [0, 1])
def test_two_annotations_of_one_physical_word_are_not_two_ink_observations(shift):
    image, _markers = _scene()
    left, top, right, bottom = BOUNDS[0]
    aliases = (BOUNDS[0], (left + shift, top, right + shift, bottom))
    assert _threshold(image, aliases) is None


@pytest.mark.parametrize("bad", [None, True, "boxes", {},
                                (None, BOUNDS[1]), ((150, 170, 230), BOUNDS[1]),
                                ((150.0, 170, 230, 202), BOUNDS[1]),
                                ((True, 170, 230, 202), BOUNDS[1]),
                                ((150, 170, 150, 202), BOUNDS[1]),
                                ((70, 170, 150, 202), BOUNDS[1])])
def test_unsupported_observations_use_the_existing_filter(bad):
    image, _markers = _scene()
    assert _material_ink_threshold(image.crop(REGION), REGION, bad) is None


@pytest.mark.parametrize("edge", [(80, 210, 120, 250), (600, 210, 640, 250),
                                 (500, 90, 540, 130), (500, 390, 540, 430)])
def test_complete_words_without_a_full_surrounding_margin_keep_existing_pixels(edge):
    bounds = (BOUNDS[0], edge)
    image, _markers = _scene(bounds=bounds)
    observed = material_region_word_boxes(_readings([_word("Cotton", BOUNDS[0]), _word("%", edge)]), REGION)
    assert observed == bounds
    assert _threshold(image, observed) is None
    content = _encoded(image)
    assert prepare_material_region(content, REGION, rotated=True, word_boxes=observed) == prepare_material_region(
        content, REGION, rotated=True,
    )


@pytest.mark.parametrize("defect", ["mode", "width", "height"])
def test_observation_coordinates_cannot_be_interpreted_in_a_different_pixel_frame(defect):
    image, _markers = _scene()
    crop = image.crop(REGION)
    if defect == "mode":
        crop = crop.convert("RGB")
    else:
        crop = crop.resize((crop.width + (defect == "width"), crop.height + (defect == "height")))
    assert _material_ink_threshold(crop, REGION, BOUNDS) is None


def test_excessive_annotation_count_stops_before_histogram_work(monkeypatch):
    image, _markers = _scene()
    crop = image.crop(REGION)
    monkeypatch.setattr(crop, "histogram", lambda: pytest.fail("unbounded quality work"))
    assert _material_ink_threshold(crop, REGION, BOUNDS + (BOUNDS[0],) * 255) is None


def test_pixel_workload_limit_stops_before_histogram_work(monkeypatch):
    image, _markers = _scene()
    crop = image.crop(REGION)
    monkeypatch.setattr(ocr_regions, "MAX_PREPROCESSED_PIXELS", crop.width * crop.height)
    monkeypatch.setattr(crop, "histogram", lambda: pytest.fail("quality inspection exceeded pixel budget"))
    assert _material_ink_threshold(crop, REGION, BOUNDS) is None


def _component_centers(image):
    gray = image.convert("L")
    pixels = gray.load()
    remaining = {(x, y) for y in range(gray.height) for x in range(gray.width) if pixels[x, y] < 80}
    centers = []
    while remaining:
        point = remaining.pop()
        queue = deque([point])
        component = [point]
        while queue:
            x, y = queue.popleft()
            for neighbour in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    queue.append(neighbour)
                    component.append(neighbour)
        if len(component) > 20:
            centers.append((sum(x for x, _y in component) / len(component),
                            sum(y for _x, y in component) / len(component)))
    return centers


@pytest.mark.parametrize("angle", [-90, -3, 6, 90])
def test_quality_raster_preserves_several_asymmetric_markers_in_original_coordinates(angle):
    bounds = BOUNDS + (EXTRA_BOUNDS,)
    image, markers = _scene(bounds=bounds)
    assert _threshold(image, bounds) is not None
    prepared = prepare_material_region(_encoded(image), REGION, rotated=True,
                                       rotation_degrees=angle, font_height=16, word_boxes=bounds)
    with Image.open(BytesIO(prepared.content)) as rendered:
        centers = _component_centers(rendered)
        assert rendered.width * rendered.height <= 16_000_000
    assert len(centers) == len(markers)
    a, b, c, d, e, f = prepared.transform
    mapped = [(a * x + b * y + c, d * x + e * y + f) for x, y in centers]
    expected = [((left + right) / 2, (top + bottom) / 2) for left, top, right, bottom in markers]
    for point in expected:
        closest = min(mapped, key=lambda actual: (actual[0] - point[0]) ** 2 + (actual[1] - point[1]) ** 2)
        assert closest == pytest.approx(point, abs=2)
        mapped.remove(closest)


def test_quality_changes_only_rotated_pixels_and_preserves_geometry():
    image, _markers = _scene()
    content = _encoded(image)
    plain = prepare_material_region(content, REGION)
    guarded_plain = prepare_material_region(content, REGION, word_boxes=BOUNDS)
    assert guarded_plain == plain
    legacy = prepare_material_region(content, REGION, rotated=True, rotation_degrees=-3, font_height=16)
    selected = prepare_material_region(content, REGION, rotated=True, rotation_degrees=-3,
                                       font_height=16, word_boxes=BOUNDS)
    assert selected.content != legacy.content
    assert (selected.transform, selected.region, selected.source) == (legacy.transform, legacy.region, legacy.source)
    with Image.open(BytesIO(selected.content)) as selected_image, Image.open(BytesIO(legacy.content)) as legacy_image:
        assert selected_image.size == legacy_image.size
        assert selected_image.format == "JPEG"


def _map_to_crop(words, transform):
    a, b, c, d, e, f = transform
    determinant = a * e - b * d
    mapped = []
    for word in words:
        points = tuple((round((e * (x - c) - b * (y - f)) / determinant),
                        round((-d * (x - c) + a * (y - f)) / determinant)) for x, y in word.vertices)
        mapped.append(replace(word, left=min(x for x, _y in points), top=min(y for _x, y in points),
                              right=max(x for x, _y in points), bottom=max(y for _x, y in points), vertices=points))
    return tuple(mapped)


@pytest.mark.parametrize("rotated_failure", [False, True])
def test_quality_reread_keeps_four_actual_inputs_and_independent_numeric_proof(monkeypatch, rotated_failure):
    bounds = ((150, 170, 250, 202), (450, 170, 520, 202),
              (150, 270, 250, 306), (450, 270, 520, 306))
    image, _markers = _scene(bounds=bounds)
    content = _encoded(image)
    source_words = tuple(_word(text, box) for text, box in zip(("Polyester", "58%", "Span", "41%"), bounds, strict=True))
    target_words = tuple(replace(word, text="59%") if word.text == "58%" else word for word in source_words)
    text, corrected = "Polyester 58%\nSpan 41%", "Polyester 59%\nSpan 41%"
    processed = ocr_text.preprocess_image_bytes(content)
    with Image.open(BytesIO(processed)) as prepared:
        processed_transform = (CANVAS[0] / prepared.width, 0, 0, 0, CANVAS[1] / prepared.height, 0)
    payloads = {
        content: ("original", OcrPayload(text, layout_words=source_words)),
        processed: ("preprocessed", OcrPayload(text, layout_words=_map_to_crop(source_words, processed_transform))),
    }
    crops, calls = [], []
    original_prepare = ocr_text.prepare_material_region

    def capture_crop(candidate_content, box, **kwargs):
        prepared = original_prepare(candidate_content, box, **kwargs)
        crops.append((prepared, kwargs))
        payloads[prepared.content] = (prepared.source, OcrPayload(
            corrected, layout_words=_map_to_crop(target_words, prepared.transform)))
        return prepared

    def provider(_client, candidate_content, **kwargs):
        source, payload = payloads[candidate_content]
        calls.append((source, candidate_content, kwargs["timeout_seconds"]))
        if rotated_failure and source == "material_crop_rotated":
            raise OcrUnavailableError("synthetic provider failure")
        return payload

    monkeypatch.setattr(ocr_text, "prepare_material_region", capture_crop)
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_args: object())
    monkeypatch.setattr(ocr_text, "_run_google_ocr", provider)
    monkeypatch.setattr(ocr_text, "_resolve_credential_path", lambda *_args: (None, None))
    monkeypatch.delenv("KDPP_ENABLE_MATERIAL_REGION_OCR", raising=False)
    result = run_ocr_bytes(content, enable_reflection=False, enable_denoised=False, enable_rotated=False)
    assert [source for source, _content, _timeout in calls] == [
        "original", "preprocessed", "material_crop", "material_crop_rotated",
    ]
    assert len({candidate_content for _source, candidate_content, _timeout in calls}) == 4
    assert result.metadata.attempt_count == 4
    assert all(timeout > 0 for _source, _content, timeout in calls)
    assert {tuple(box) for _crop, options in crops for box in options["word_boxes"]} == set(bounds)
    parsed = parse_label(result.text, conflicting_parts=result.metadata.conflicting_parts,
                         unpaired_ratio_parts=result.metadata.unpaired_ratio_parts,
                         rejected_composition_parts=result.metadata.rejected_composition_parts)
    if rotated_failure:
        assert parsed["status"] == "failed"
        assert len(result.metadata.attempt_failures) == 1
    else:
        assert parsed["status"] == "success"
        assert parsed["materials"] == {"polyester": 59, "spandex": 41}
