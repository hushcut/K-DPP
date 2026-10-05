from __future__ import annotations

from collections import Counter
from dataclasses import asdict, replace
from io import BytesIO
from random import Random
from types import SimpleNamespace

from PIL import Image
import pytest

from apps.service.label_analysis import analyze_ocr_result
from apps.text import ocr_text
from apps.text.ocr_cache import OcrCacheError, OcrTextCache, decode_layout_words
from apps.text.ocr_layout import OcrWord, extract_response_words, spatial_text_from_words
from apps.text.parse_label import parse_label


def word(text, x, y, width=100, height=20, tilt=-0.12, scale=1, offset=(0, 0), page=0):
    points = ((x, y + tilt * x), (x + width, y + tilt * (x + width)),
              (x + width, y + height + tilt * (x + width)), (x, y + height + tilt * x))
    vertices = tuple((round(px * scale + offset[0]), round(py * scale + offset[1])) for px, py in points)
    xs, ys = zip(*vertices)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), vertices, page)


def composition_words(**kwargs):
    return [
        word("OUTER", 20, 260, **kwargs),
        word("COTTON", 20, 300, **kwargs),
        word("51", 320, 300, 30, **kwargs),
        word("%", 355, 300, 15, **kwargs),
        word("POLYESTER", 20, 340, 140, **kwargs),
        word("46", 320, 340, 30, **kwargs),
        word("%", 355, 340, 15, **kwargs),
        word("POLYURETHANE", 20, 380, 170, **kwargs),
        word("3", 320, 380, 15, **kwargs),
        word("%", 340, 380, 15, **kwargs),
    ]


@pytest.mark.parametrize("tilt", [-0.2, -0.12, -0.06, 0.06, 0.12, 0.2])
@pytest.mark.parametrize("scale", [1, 2, 4])
@pytest.mark.parametrize("offset", [(0, 0), (137, 91)])
def test_tilted_columns_preserve_each_material_ratio(tilt, scale, offset):
    words = composition_words(tilt=tilt, scale=scale, offset=offset)
    layout = spatial_text_from_words(words)
    assert layout == "OUTER\nCOTTON 51 %\nPOLYESTER 46 %\nPOLYURETHANE 3 %"
    assert parse_label(layout)["materials"] == {"cotton": 51, "polyester": 46, "polyurethane": 3}
    assert Counter(layout.split()) == Counter(token for w in words for token in w.text.split())


@pytest.mark.parametrize("seed", range(5))
def test_layout_is_independent_of_provider_word_order(seed):
    words = composition_words()
    expected = spatial_text_from_words(words)
    Random(seed).shuffle(words)
    assert spatial_text_from_words(words) == expected


def test_small_coordinate_noise_does_not_swap_equal_total_ratios():
    words = composition_words()
    noisy = []
    for index, value in enumerate(words):
        dy = index % 3 - 1
        noisy.append(replace(value, top=value.top + dy, bottom=value.bottom + dy,
                             vertices=tuple((x, y + dy) for x, y in value.vertices)))
    assert spatial_text_from_words(noisy) == spatial_text_from_words(words)


def test_distinct_folded_regions_use_independent_geometry():
    words = composition_words() + [
        word("LINING", 20, 550, tilt=0.12),
        word("NYLON", 20, 590, tilt=0.12),
        word("80%", 320, 590, 50, tilt=0.12),
        word("COTTON", 20, 630, tilt=0.12),
        word("20%", 320, 630, 50, tilt=0.12),
    ]
    layout = spatial_text_from_words(words)
    assert layout.endswith("LINING\nNYLON 80%\nCOTTON 20%")
    assert parse_label(layout)["materials"] == {"cotton": 51, "polyester": 46, "polyurethane": 3}


def test_words_on_different_pages_are_not_joined():
    words = [word("COTTON", 20, 300, tilt=0), word("100%", 320, 300, 50, tilt=0),
             word("NYLON", 20, 300, tilt=0, page=1), word("100%", 320, 300, 50, tilt=0, page=1)]
    assert spatial_text_from_words(words) == "COTTON 100%\nNYLON 100%"


def test_axis_aligned_words_and_legacy_boxes_keep_the_previous_layout():
    words = composition_words(tilt=0)
    assert spatial_text_from_words(words) == spatial_text_from_words([replace(w, vertices=()) for w in words])


def test_insufficient_or_inconsistent_angles_keep_horizontal_fallback():
    words = [word("ALPHA", 20, 300), word("BETA", 20, 340, tilt=0.12),
             word("GAMMA", 20, 380), word("DELTA", 20, 420, tilt=0.12)]
    assert spatial_text_from_words(words) == spatial_text_from_words([replace(w, vertices=()) for w in words])
    single = [word("COTTON", 20, 300), word("100%", 320, 300, 30)]
    assert spatial_text_from_words(single) == spatial_text_from_words([replace(w, vertices=()) for w in single])


def test_invalid_polygon_cannot_set_a_tilt_angle():
    words = [replace(w, vertices=((0, 0), (0, 0), (0, 0), (0, 0))) for w in composition_words()]
    assert spatial_text_from_words(words) == spatial_text_from_words([replace(w, vertices=()) for w in words])


def test_clear_opposite_tilt_is_not_overridden_by_the_majority():
    words = [word("ALPHA", 20, 300, 300, tilt=0.2),
             word("BETA", 20, 335, 300, tilt=0.2),
             word("GAMMA", 20, 370, 300, tilt=0.2),
             word("MINOR", 20, 355, 300, tilt=-0.2)]
    assert spatial_text_from_words(words) == spatial_text_from_words([replace(w, vertices=()) for w in words])


def test_close_rows_are_not_merged_across_materials():
    words = [word("COTTON", 20, 300), word("80%", 320, 300, 50),
             word("POLYESTER", 20, 325, 140), word("20%", 320, 325, 50)]
    assert spatial_text_from_words(words) == "COTTON 80%\nPOLYESTER 20%"


def test_numbers_unknown_fibers_and_metadata_are_never_deleted():
    words = composition_words() + [word("OLEFIN", 20, 420), word("10%", 320, 420, 50),
                                   word("SIZE", 20, 600, tilt=0), word("30°C", 320, 600, 50, tilt=0)]
    layout = spatial_text_from_words(words)
    assert Counter(layout.split()) == Counter(token for value in words for token in value.text.split())
    assert parse_label(layout)["status"] == "failed"


def image_bytes():
    stream = BytesIO()
    Image.new("RGB", (80, 80), "white").save(stream, format="PNG")
    return stream.getvalue()


def offline_analysis(monkeypatch, tmp_path, raw, words, legacy_layout="COTTON 46%\nPOLYESTER 3%"):
    def forbid(*_args, **_kwargs):
        raise AssertionError("Coordinate replay must not call Google Vision")
    monkeypatch.setattr(ocr_text, "_get_vision_client", forbid)
    monkeypatch.setattr(ocr_text, "_run_google_ocr", forbid)
    content = image_bytes()
    monkeypatch.setattr(ocr_text, "preprocess_image_bytes", lambda _: content)
    cache = OcrTextCache(tmp_path / "coordinates.json")
    cache.put(content, raw, layout_text=legacy_layout, layout_words=tuple(words))
    cache = OcrTextCache(cache.path)
    result = ocr_text.run_ocr_bytes(content, ocr_cache=cache, offline=True,
                                  enable_reflection=False, enable_denoised=False, enable_rotated=False)
    assert result.metadata.external_call_count == result.metadata.rpc_attempt_count == 0
    assert cache.write_count == 0
    return analyze_ocr_result(result)


def test_offline_geometry_rebuilds_layout_without_reassigning_numbers(monkeypatch, tmp_path):
    raw = "OUTER\nCOTTON\n51%\n46%\nPOLYESTER\nPOLYURETHANE\n3%"
    result = offline_analysis(monkeypatch, tmp_path, raw, composition_words())
    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 51, "polyester": 46, "polyurethane": 3}
    assert result["selected_part"] == "outer"


def test_raw_and_geometry_composition_conflicts_still_fail(monkeypatch, tmp_path):
    words = [word("COTTON", 20, 300), word("80%", 320, 300, 40),
             word("POLYESTER", 20, 340, 140), word("20%", 320, 340, 40)]
    result = offline_analysis(monkeypatch, tmp_path, "COTTON 20% POLYESTER 80%", words)
    assert result["status"] == "failed" and result["materials"] == {}


def test_coordinate_cache_preserves_unregistered_material_rejection(monkeypatch, tmp_path):
    words = [word("OUTER", 20, 260), word("COTTON", 20, 300), word("100%", 320, 300, 50),
             word("OLEFIN", 20, 340), word("50%", 320, 340, 50)]
    result = offline_analysis(monkeypatch, tmp_path, "OUTER\nCOTTON 100%\nOLEFIN 50%", words)
    assert result["status"] == "failed" and result["materials"] == {}


def test_geometry_cannot_repair_a_decimal_to_force_a_total(monkeypatch, tmp_path):
    words = [word("POLYESTER", 20, 300, 140), word("95%", 320, 300, 50),
             word("POLYURETHANE", 20, 340, 170), word(".5%", 320, 340, 50)]
    result = offline_analysis(monkeypatch, tmp_path, "POLYESTER 95%\nPOLYURETHANE .5%", words)
    assert result["status"] == "failed" and result["materials"] == {}


def test_cache_roundtrip_retains_polygon_and_page(tmp_path):
    words = tuple(composition_words(page=1))
    cache = OcrTextCache(tmp_path / "words.json")
    cache.put(b"image", "raw", layout_words=words)
    entry = OcrTextCache(cache.path).get_entry(b"image")
    assert decode_layout_words(entry) == words
    assert decode_layout_words({"text": "legacy"}) == ()


@pytest.mark.parametrize("field,value", [("text", ""), ("text", None), ("left", True),
                                        ("page", -1), ("page", 0.5), ("right", -100), ("right", 10**400),
                                        ("vertices", None), ("vertices", [[0, 0]]),
                                        ("vertices", [[0, 0]] * 4)])
def test_corrupted_coordinate_cache_is_rejected(field, value):
    row = asdict(composition_words()[0])
    row[field] = value
    with pytest.raises(OcrCacheError):
        decode_layout_words({"layout_words_version": 1, "layout_words": [row]})


@pytest.mark.parametrize("version", [99, True, None, 1.0])
def test_unknown_coordinate_cache_version_is_rejected(version):
    with pytest.raises(OcrCacheError):
        decode_layout_words({"layout_words_version": version, "layout_words": []})


def test_invalid_coordinate_write_preserves_existing_cache(tmp_path):
    cache = OcrTextCache(tmp_path / "words.json")
    cache.put(b"image", "COTTON 100%")
    before = cache.path.read_bytes()
    broken = replace(composition_words()[0], right=-1)
    with pytest.raises(OcrCacheError):
        cache.put(b"image", "changed", layout_words=(broken,))
    assert cache.path.read_bytes() == before


@pytest.mark.parametrize("schema", [1, 2])
def test_legacy_text_cache_uses_its_original_layout_without_api(monkeypatch, tmp_path, schema):
    import hashlib
    import json
    content = image_bytes()
    payload = {"schema_version": schema, "content_version": 1,
               "entries": {hashlib.sha256(content).hexdigest(): {
                   "text": "COTTON\n100%", "layout_text": "COTTON 100%"}}}
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    def forbid(*_args, **_kwargs):
        raise AssertionError("Legacy replay must not call Google Vision")
    monkeypatch.setattr(ocr_text, "_get_vision_client", forbid)
    monkeypatch.setattr(ocr_text, "_run_google_ocr", forbid)
    result = ocr_text.run_ocr_bytes(content, ocr_cache=OcrTextCache(path), offline=True)
    assert analyze_ocr_result(result)["materials"] == {"cotton": 100}
    assert result.metadata.external_call_count == 0


def test_provider_polygon_is_retained_without_reordering_vertices():
    original = composition_words()[1]
    provider_word = SimpleNamespace(
        symbols=[SimpleNamespace(text=char) for char in original.text],
        bounding_box=SimpleNamespace(vertices=[SimpleNamespace(x=x, y=y) for x, y in original.vertices]),
    )
    paragraph = SimpleNamespace(words=[provider_word])
    response = SimpleNamespace(full_text_annotation=SimpleNamespace(
        pages=[SimpleNamespace(blocks=[SimpleNamespace(paragraphs=[paragraph])])]))
    assert extract_response_words(response) == (original,)
