import json

import pytest

from apps.text.ocr_cache import OcrCacheError, OcrTextCache, image_sha256


def test_cache_round_trip_uses_image_content_hash(tmp_path) -> None:
    cache_path = tmp_path / "qa_ocr_cache.json"
    first = OcrTextCache(cache_path)
    content = b"same image bytes"

    first.put(
        content,
        "COTTON 100%",
        file_name="QA001.jpg",
        source="original",
    )
    second = OcrTextCache(cache_path)
    restored = second.get(content)

    assert restored == "COTTON 100%"
    assert len(second) == 1
    assert second.get(b"different image bytes") is None
    assert image_sha256(content) in json.loads(
        cache_path.read_text(encoding="utf-8")
    )["entries"]


def test_cache_rejects_invalid_json(tmp_path) -> None:
    cache_path = tmp_path / "qa_ocr_cache.json"
    cache_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(OcrCacheError):
        OcrTextCache(cache_path)


def test_cache_rejects_damaged_entry(tmp_path) -> None:
    content = b"image"
    cache_path = tmp_path / "qa_ocr_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": {
                    image_sha256(content): {
                        "text": 100,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    cache = OcrTextCache(cache_path)
    with pytest.raises(OcrCacheError):
        cache.get(content)


def test_legacy_cache_is_readable_and_upgraded_on_next_write(tmp_path) -> None:
    first_content = b"legacy image"
    cache_path = tmp_path / "qa_ocr_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": {
                    image_sha256(first_content): {"text": "COTTON 100%"}
                },
            }
        ),
        encoding="utf-8",
    )

    cache = OcrTextCache(cache_path)
    assert cache.get(first_content) == "COTTON 100%"
    cache.put(b"new image", "POLYESTER 100%")

    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["content_version"] == 1
    assert OcrTextCache(cache_path).get(first_content) == "COTTON 100%"


def test_cache_write_is_atomic(tmp_path) -> None:
    cache_path = tmp_path / "qa_ocr_cache.json"
    cache = OcrTextCache(cache_path)

    cache.put(b"image", "COTTON 100%")

    assert cache_path.is_file()
    assert not cache_path.with_name(cache_path.name + ".tmp").exists()
    assert not cache_path.with_name(cache_path.name + ".lock").exists()
    assert cache.write_count == 1


def test_cache_merges_writes_from_separate_instances(tmp_path) -> None:
    cache_path = tmp_path / "qa_ocr_cache.json"
    first = OcrTextCache(cache_path)
    second = OcrTextCache(cache_path)

    first.put(b"first image", "COTTON 100%")
    second.put(b"second image", "POLYESTER 100%")

    restored = OcrTextCache(cache_path)
    assert restored.get(b"first image") == "COTTON 100%"
    assert restored.get(b"second image") == "POLYESTER 100%"


def test_cache_requires_refresh_when_ocr_content_version_changes(tmp_path) -> None:
    cache_path = tmp_path / "qa_ocr_cache.json"
    OcrTextCache(cache_path, content_version=1).put(b"image", "COTTON 100%")

    with pytest.raises(OcrCacheError, match="--refresh-ocr-cache"):
        OcrTextCache(cache_path, content_version=2)

    refreshed = OcrTextCache(
        cache_path,
        content_version=2,
        reset_stale_cache=True,
    )
    assert refreshed.get(b"image") is None
    refreshed.put(b"image", "POLYESTER 100%")
    assert OcrTextCache(cache_path, content_version=2).get(b"image") == (
        "POLYESTER 100%"
    )


def test_cache_does_not_write_when_another_process_holds_lock(tmp_path) -> None:
    cache_path = tmp_path / "qa_ocr_cache.json"
    cache = OcrTextCache(cache_path, lock_timeout_seconds=0)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache._lock_path.write_text("other process", encoding="utf-8")

    try:
        with pytest.raises(OcrCacheError, match="다른 실행에서 사용 중"):
            cache.put(b"image", "COTTON 100%")
    finally:
        cache._lock_path.unlink(missing_ok=True)

    assert not cache_path.exists()
