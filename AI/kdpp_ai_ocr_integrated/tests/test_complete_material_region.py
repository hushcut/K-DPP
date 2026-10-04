"""A shorter crop must remove only a completely proved metadata row."""

from dataclasses import replace
from collections import Counter
from io import BytesIO

import pytest
from PIL import Image

from apps.text import ocr_text
from apps.text.ocr_errors import OcrUnavailableError
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_regions import (
    find_complete_material_region, find_material_region, material_region_options, prepare_material_region,
)
from apps.text.ocr_text import OcrPayload, _build_payload_candidates
from apps.text.parse_label import parse_label


REGION = (200, 303, 861, 551)


def _word(text, x, y, width=45, height=28):
    points = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
    return OcrWord(text, x, y, x + width, y + height, points)


def _fixture(*, joined=False, extra=()):
    words = tuple(word for name, value, y in (
        ("Polyester", "5%", 370), ("Rayon", "21%", 415), ("Span", "4%", 457),
    ) for word in (_word(name, 255, y, 145, 27), _word(value, 755, y, 55, 24)))
    header = "1 세탁 시 주의 사항 ]"
    if joined:
        words += (_word(header, 410, 530, 270, 28),)
    else:
        words += tuple(_word(text, x, 530, width, 28) for text, x, width in (
            ("1", 410, 15), ("세탁", 430, 55), ("시", 495, 25),
            ("주의", 535, 60), ("사항", 605, 55), ("]", 670, 15),
        ))
    text = "Polyester 5%\nRayon 21%\nSpan 4%\n" + header
    if extra:
        text += "\n" + " ".join(word.text for word in extra)
        words += extra
    return _build_payload_candidates(
        "original", OcrPayload(text, layout_words=words), image_key="whole-label",
        image_variant_key="original-input", image_transform=(1, 0, 0, 0, 1, 0),
        image_region=(0, 0, 1081, 1440),
    )[0]


@pytest.mark.parametrize("joined", [False, True])
def test_complete_metadata_row_ends_crop_before_its_first_letter(joined):
    candidate = _fixture(joined=joined)
    assert find_complete_material_region([candidate], REGION) == (200, 303, 861, 528)
    for word in candidate.image_words[:6]:
        assert word.bottom + 2 <= 528


def test_duplicate_and_reordered_responses_keep_the_same_complete_region():
    candidate = _fixture()
    peer = replace(candidate, source="preprocessed", image_variant_key="processed-input")
    assert find_complete_material_region([candidate, peer, candidate], REGION) == (200, 303, 861, 528)
    assert find_complete_material_region([peer, candidate], REGION) == (200, 303, 861, 528)


@pytest.mark.parametrize("bottom", [529, 530, 558, 580])
def test_no_cut_metadata_row_does_not_request_an_additional_crop(bottom):
    assert find_complete_material_region([_fixture()], (*REGION[:3], bottom)) is None


@pytest.mark.parametrize("text", ["OLEFIN", "FAUX", "UNKNOWN", "10%", "-10%", "%魚&", "&"])
def test_reducing_region_cannot_hide_any_extra_row_or_literal_character(text):
    candidate = _fixture(extra=(_word(text, 710, 515, 75, 22),))
    assert find_complete_material_region([candidate], REGION) is None


@pytest.mark.parametrize("suffix", ["OLEFIN", "FAUX", "UNKNOWN", "Polyester 10%", "10%", "-10%", "%魚&"])
def test_metadata_heading_cannot_make_composition_or_unknown_suffix_disappear(suffix):
    candidate = _fixture(joined=True)
    header_word = candidate.image_words[-1]
    candidate = replace(
        candidate, text=candidate.text + " " + suffix,
        image_words=candidate.image_words[:-1] + (replace(header_word, text=header_word.text + " " + suffix),),
    )
    assert find_complete_material_region([candidate], REGION) is None


@pytest.mark.parametrize("defect", ["missing_frame", "missing_variant", "missing_key", "missing_header_box",
                                   "header_character_added", "header_character_missing", "nonzero_page"])
def test_region_changes_require_the_complete_same_frame_metadata_words(defect):
    candidate = _fixture()
    if defect == "missing_frame":
        candidate = replace(candidate, image_region=())
    elif defect == "missing_variant":
        candidate = replace(candidate, image_variant_key="")
    elif defect == "missing_key":
        candidate = replace(candidate, image_key="")
    elif defect == "missing_header_box":
        candidate = replace(candidate, image_words=candidate.image_words[:-1])
    elif defect == "header_character_added":
        candidate = replace(candidate, image_words=candidate.image_words[:-1] +
                            (replace(candidate.image_words[-1], text="]魚"),))
    elif defect == "header_character_missing":
        candidate = replace(candidate, text=candidate.text.removesuffix(" ]"))
    else:
        candidate = replace(candidate, image_words=tuple(replace(word, page=1) for word in candidate.image_words))
    assert find_complete_material_region([candidate], REGION) is None


@pytest.mark.parametrize("bottom", [527, 528, 535, 556])
def test_care_heading_cannot_cut_a_retained_material_box_or_remove_the_gap(bottom):
    candidate = _fixture()
    words = candidate.image_words
    material = words[4]
    points = ((material.left, material.top), (material.right, material.top),
              (material.right, bottom), (material.left, bottom))
    candidate = replace(candidate, image_words=words[:4] + (replace(material, bottom=bottom, vertices=points),) + words[5:])
    assert find_complete_material_region([candidate], REGION) is None


def test_metadata_cut_is_not_proved_by_a_different_incomplete_response():
    candidate = _fixture()
    unknown = _word("OLEFIN", 720, 530, 70, 28)
    other = replace(candidate, source="preprocessed", image_variant_key="different-input",
                    text=candidate.text + "\nOLEFIN", image_words=candidate.image_words + (unknown,))
    assert find_complete_material_region([candidate, other], REGION) is None


def test_empty_or_unknown_only_regions_are_not_reduced():
    assert find_complete_material_region([], REGION) is None
    candidate = _fixture(joined=True)
    candidate = replace(candidate, text=candidate.image_words[-1].text,
                        image_words=(candidate.image_words[-1],))
    assert find_complete_material_region([candidate], REGION) is None


def _input_words(words, transform):
    a, b, c, d, e, f = transform
    determinant = a * e - b * d
    result = []
    for word in words:
        points = tuple((round((e * (x - c) - b * (y - f)) / determinant),
                        round((-d * (x - c) + a * (y - f)) / determinant))
                       for x, y in word.vertices)
        result.append(replace(word, vertices=points, left=min(x for x, _y in points),
                              right=max(x for x, _y in points), top=min(y for _x, y in points),
                              bottom=max(y for _x, y in points)))
    return tuple(result)


def _pipeline_fixture(monkeypatch, early_outcome):
    image = Image.new("RGB", (1081, 1440), "white")
    image.putpixel((255, 370), (0, 0, 0))
    stream = BytesIO()
    image.save(stream, format="JPEG")
    content = stream.getvalue()
    original = _fixture()
    located = find_material_region([original], 1081, 1440)
    region = find_complete_material_region([original], located)
    assert region is not None
    font_height, rotation_degrees = material_region_options([original], region)
    options = {"font_height": font_height, "rotation_degrees": rotation_degrees}
    rotated = prepare_material_region(content, region, rotated=True, **options)
    plain = prepare_material_region(content, region, **options)
    processed = ocr_text.preprocess_image_bytes(content)
    processed_frame = ocr_text.ocr_coordinate_frame(content, processed, "preprocessed")[0]
    clean_words = tuple(replace(word, text="75%") if word.text == "5%" else word
                        for word in original.image_words[:6])
    clean_text = "Polyester 75%\nRayon 21%\nSpan 4%"
    failed_text = "Polyester 5%\nRayon 21%\nSpan 4%"
    payloads = {
        content: ("original", OcrPayload(original.text, layout_words=original.image_words)),
        processed: ("preprocessed", OcrPayload(original.text,
                    layout_words=_input_words(original.image_words, processed_frame))),
        plain.content: ("material_crop", OcrPayload(failed_text,
                        layout_words=_input_words(original.image_words[:6], plain.transform))),
        rotated.content: ("material_crop_rotated", OcrPayload(
            clean_text if early_outcome == "success" else failed_text,
            layout_words=_input_words(clean_words if early_outcome == "success" else
                                      original.image_words[:6], rotated.transform))),
    }
    calls = []

    def provider(_client, candidate_content, **_kwargs):
        source, payload = payloads[candidate_content]
        calls.append(source)
        if source == "material_crop_rotated" and early_outcome == "provider_error":
            raise OcrUnavailableError("Synthetic provider failure", rpc_attempt_count=1)
        return payload

    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_args: object())
    monkeypatch.setattr(ocr_text, "_resolve_credential_path", lambda *_args: (None, None))
    monkeypatch.setattr(ocr_text, "_run_google_ocr", provider)
    return content, calls


def _pipeline_analysis(result):
    return parse_label(result.text, conflicting_parts=result.metadata.conflicting_parts,
                       unpaired_ratio_parts=result.metadata.unpaired_ratio_parts,
                       rejected_composition_parts=result.metadata.rejected_composition_parts)


def test_proved_complete_crop_runs_before_preprocessing_and_stops_after_recovery(monkeypatch):
    content, calls = _pipeline_fixture(monkeypatch, "success")
    monkeypatch.setattr(ocr_text, "preprocess_image_bytes", lambda _content: pytest.fail(
        "A recovered complete crop needs no full-image preprocessing"))
    result = ocr_text.run_ocr_bytes(content, enable_material_region=True,
                                  enable_reflection=False, enable_denoised=False, enable_rotated=False)
    assert calls == ["original", "material_crop_rotated"]
    assert result.metadata.candidate_count == result.metadata.attempt_count == 2
    assert _pipeline_analysis(result)["materials"] == {"polyester": 75, "rayon": 21, "spandex": 4}
    assert _pipeline_analysis(result)["status"] == "success"


@pytest.mark.parametrize("early_outcome", ["failed", "provider_error"])
def test_early_crop_failure_keeps_preprocess_and_plain_fallback_without_repeating_rotated_source(
    monkeypatch, early_outcome,
):
    content, calls = _pipeline_fixture(monkeypatch, early_outcome)
    result = ocr_text.run_ocr_bytes(content, enable_material_region=True,
                                  enable_reflection=False, enable_denoised=False, enable_rotated=False)
    assert calls == ["original", "material_crop_rotated", "preprocessed", "material_crop"]
    assert max(Counter(calls).values()) == 1
    assert result.metadata.attempt_count == 4
    assert result.metadata.candidate_count == (3 if early_outcome == "provider_error" else 4)
    assert _pipeline_analysis(result)["status"] == "failed"
    if early_outcome == "provider_error":
        assert "material_crop_rotated:OcrUnavailableError" in result.metadata.attempt_failures


def test_early_crop_setup_exhausting_total_budget_adds_no_crop_or_preprocess_candidate(monkeypatch):
    content, calls = _pipeline_fixture(monkeypatch, "failed")
    clock = {"now": 0.0}
    original_prepare = ocr_text.prepare_material_region

    def expensive_crop(*args, **kwargs):
        cropped = original_prepare(*args, **kwargs)
        clock["now"] = 26.0
        return cropped

    monkeypatch.setattr(ocr_text.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(ocr_text, "prepare_material_region", expensive_crop)
    monkeypatch.setattr(ocr_text, "preprocess_image_bytes", lambda _content: pytest.fail(
        "An exhausted request must not prepare another image"))
    result = ocr_text.run_ocr_bytes(content, enable_material_region=True,
                                  enable_reflection=False, enable_denoised=False, enable_rotated=False)
    assert calls == ["original"]
    assert result.metadata.candidate_count == 1
    assert result.metadata.external_call_count == 1
    assert all(attempt.outcome == "skipped" for attempt in result.metadata.attempts[1:])
    assert "preprocessed:total_timeout" in result.metadata.attempt_failures
    assert _pipeline_analysis(result)["status"] == "failed"
