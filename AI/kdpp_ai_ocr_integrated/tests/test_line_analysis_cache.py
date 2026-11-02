"""Analysis reuse must preserve evidence, mutation isolation and request lifetime."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import gc
import importlib
from threading import Barrier
import weakref

import pytest

from apps.service import label_analysis
from apps.text import line_analysis_cache as cache
from apps.text import ocr_text

parser = importlib.import_module("apps.text.parse_label")


@pytest.fixture
def builds(monkeypatch):
    calls = []
    original = parser._build_line_analysis

    def build(text):
        calls.append(text)
        return original(text)

    monkeypatch.setattr(parser, "_build_line_analysis", build)
    return calls


def evidence(text):
    restored, translated, warnings = {9001}, {9002}, ["existing"]
    rows = parser.build_line_infos(text, restored_indices=restored,
                                  translation_indices=translated, translation_warnings=warnings)
    return rows, restored, translated, warnings


@pytest.mark.parametrize("unproven", [False, True])
@pytest.mark.parametrize("text", [
    "COTTON 100%",
    "100% COT\nTON",
    "COTTON 95\n%\nSPANDEX 5\n%",
    "100% Cotton/Coton/Baumwolle/ji/コットン",
])
def test_cached_rows_replay_all_evidence_and_keep_callers_independent(monkeypatch, builds, text, unproven):
    if unproven:
        monkeypatch.setattr(parser, "_multilingual_restored_row_indices", lambda *_args: None)
    expected = evidence(text)
    builds.clear()
    with cache.line_analysis_scope():
        first = parser.build_line_infos(text)  # Prime without requesting any evidence outputs.
        actual = evidence(text)
        assert actual == expected
        assert first is not actual[0]
        first.clear()
        actual[1].clear()
        actual[2].clear()
        actual[3].append("changed")
        assert evidence(text) == expected
    assert builds == [text]


def test_repeated_evidence_outputs_keep_the_existing_append_semantics():
    text = "100% Cotton/Coton/Baumwolle/ji/コットン"
    expected_warnings = []
    parser.build_line_infos(text, translation_warnings=expected_warnings)
    assert expected_warnings
    actual = ["existing"]
    with cache.line_analysis_scope():
        parser.build_line_infos(text, translation_warnings=actual)
        parser.build_line_infos(text, translation_warnings=actual)
    assert actual == ["existing", *expected_warnings, *expected_warnings]


def test_only_nested_analysis_scopes_share_results(builds):
    text = "cotton 100%"
    with cache.line_analysis_scope():
        parser.parse_label(text)
        with cache.line_analysis_scope():
            parser.parse_label(text)
        parser.parse_label(text)
    assert builds == [text]
    parser.parse_label(text)
    assert builds == [text, text]


def test_unscoped_row_calls_do_not_keep_a_global_cache(builds):
    parser.build_line_infos("cotton 100%")
    parser.build_line_infos("cotton 100%")
    assert builds == ["cotton 100%", "cotton 100%"]


def test_an_inner_exception_does_not_clear_its_outer_scope(builds):
    with cache.line_analysis_scope():
        parser.build_line_infos("cotton 100%")
        with pytest.raises(ValueError), cache.line_analysis_scope():
            raise ValueError("nested failure")
        parser.build_line_infos("cotton 100%")
    assert builds == ["cotton 100%"]


def test_analysis_objects_are_released_when_an_exception_leaves_the_scope(monkeypatch):
    references = []
    original = parser._build_line_analysis

    def build(text):
        analysis = original(text)
        references.append(weakref.ref(analysis))
        return analysis

    monkeypatch.setattr(parser, "_build_line_analysis", build)
    with pytest.raises(ValueError), cache.line_analysis_scope():
        parser.build_line_infos("cotton 100%")
        assert references[0]() is not None
        raise ValueError("request failed")
    gc.collect()
    assert references[0]() is None


def empty_builder(calls):
    def build(text):
        calls.append(text)
        return cache.LineAnalysis((), frozenset(), frozenset(), ())
    return build


def test_cache_keys_preserve_the_literal_input():
    calls = []
    build = empty_builder(calls)
    with cache.line_analysis_scope():
        for text in ["COTTON 100%", "cotton 100%", "COTTON 100%"]:
            cache.reuse_line_analysis(text, build)
    assert calls == ["COTTON 100%", "cotton 100%"]


def test_entry_limit_keeps_recently_used_analyses(monkeypatch):
    monkeypatch.setattr(cache, "MAX_CACHED_LINE_ANALYSES", 2)
    calls = []
    build = empty_builder(calls)
    with cache.line_analysis_scope():
        for text in ["a", "b", "a", "c", "b"]:
            cache.reuse_line_analysis(text, build)
    assert calls == ["a", "b", "c", "b"]


def test_character_limit_bounds_retained_source_text(monkeypatch):
    monkeypatch.setattr(cache, "MAX_CACHED_TEXT_CHARACTERS", 5)
    calls = []
    build = empty_builder(calls)
    with cache.line_analysis_scope():
        for text in ["aa", "bbb", "cc", "aa"]:
            cache.reuse_line_analysis(text, build)
    assert calls == ["aa", "bbb", "cc", "aa"]


def test_oversized_input_is_not_retained_or_allowed_to_evict_small_entries(monkeypatch):
    monkeypatch.setattr(cache, "MAX_CACHED_TEXT_CHARACTERS", 5)
    calls = []
    build = empty_builder(calls)
    with cache.line_analysis_scope():
        for text in ["a", "abcdef", "abcdef", "a"]:
            cache.reuse_line_analysis(text, build)
    assert calls == ["a", "abcdef", "abcdef"]


def test_builder_failure_is_not_reused():
    calls = []
    succeeding = empty_builder(calls)

    def build(text):
        if not calls:
            calls.append("failed")
            raise ValueError("analysis failed")
        return succeeding(text)

    with cache.line_analysis_scope():
        with pytest.raises(ValueError):
            cache.reuse_line_analysis("retry", build)
        cache.reuse_line_analysis("retry", build)
        cache.reuse_line_analysis("retry", build)
    assert calls == ["failed", "retry"]


def test_simultaneous_analysis_threads_keep_separate_scopes(builds):
    barrier = Barrier(2)

    def request():
        with cache.line_analysis_scope():
            first = parser.build_line_infos("cotton 100%")
            barrier.wait(timeout=5)
            second = parser.build_line_infos("cotton 100%")
            return first, second

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: request(), range(2)))
    assert len(builds) == 2
    assert all(first == second and first is not second for first, second in results)
    assert results[0][0] is not results[1][0]


def test_shared_row_analysis_does_not_confirm_an_automatic_failure():
    text = "MATERIAL\nCOTTON 80%\nPOLYESTER 20%\nCUSTOMFIBER 60%\nPOLYESTER 40%"
    automatic = parser.parse_label(text)
    confirmed = parser.parse_label(text, confirmed_first_generic=True)
    assert automatic["status"] == "failed" and confirmed["status"] == "success"
    with cache.line_analysis_scope():
        assert parser.parse_label(text) == automatic
        assert parser.parse_label(text, confirmed_first_generic=True) == confirmed
        assert parser.parse_label(text) == automatic


@pytest.mark.parametrize("original,second,status,ocr_calls,assessments", [
    ("brand only", "cotton 100%", "success", 2, 2),
    ("brand only", ocr_text.OcrTimeoutError("temporary"), "failed", 2, 1),
    ("cotton 100%", None, "success", 1, 1),
])
def test_candidate_decisions_are_reused_only_until_candidates_change(
    monkeypatch, original, second, status, ocr_calls, assessments,
):
    monkeypatch.setattr(ocr_text, "validate_image_bytes", lambda *_args, **_kwargs: (
        ocr_text.ValidatedImage(b"original", "PNG", 100, 100)
    ))
    monkeypatch.setattr(ocr_text, "_resolve_credential_path", lambda *_args: (None, None))
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_args: object())
    monkeypatch.setattr(ocr_text, "preprocess_image_bytes", lambda _content: b"basic")
    for name in ["reflection", "denoised", "rotated", "material_region"]:
        monkeypatch.setattr(ocr_text, name + "_ocr_enabled", lambda: False)
    calls = []
    decision_inputs = []
    assess = ocr_text._assess_candidates

    def provider(_client, content, **_kwargs):
        calls.append(content)
        value = original if content == b"original" else second
        if isinstance(value, Exception):
            raise value
        assert value is not None
        return value

    def counted(candidates):
        decision_inputs.append(tuple(candidate.source for candidate in candidates))
        return assess(candidates)

    monkeypatch.setattr(ocr_text, "_run_google_ocr", provider)
    monkeypatch.setattr(ocr_text, "_assess_candidates", counted)
    result = label_analysis.analyze_label_image_bytes(b"image")
    assert result["status"] == status
    assert result["materials"] == ({"cotton": 100} if status == "success" else {})
    assert len(calls) == ocr_calls and len(decision_inputs) == assessments
    if assessments == 2:
        assert decision_inputs == [("original",), ("original", "preprocessed")]


def test_the_image_service_reuses_rows_through_final_response_assembly(monkeypatch, builds):
    def ocr(_content, **_kwargs):
        parser.parse_label("cotton 100%")
        return ocr_text.OcrResult("cotton 100%", ocr_text.OcrMetadata(
            source="original", confidence="high", candidate_count=1,
            image_format="PNG", width=100, height=100,
        ))

    monkeypatch.setattr(label_analysis, "run_ocr_bytes", ocr)
    assert label_analysis.analyze_label_image_bytes(b"image")["materials"] == {"cotton": 100}
    assert Counter(builds) == {"cotton 100%": 1}
