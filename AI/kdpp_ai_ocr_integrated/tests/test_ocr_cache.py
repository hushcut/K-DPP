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


def test_cache_write_is_atomic(tmp_path) -> None:
    cache_path = tmp_path / "qa_ocr_cache.json"
    cache = OcrTextCache(cache_path)

    cache.put(b"image", "COTTON 100%")

    assert cache_path.is_file()
    assert not cache_path.with_name(cache_path.name + ".tmp").exists()
    assert cache.write_count == 1
