from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

CACHE_SCHEMA_VERSION = 1


class OcrCacheError(RuntimeError):
    """The local QA OCR cache is unreadable or cannot be updated safely."""


class OcrCacheMissError(OcrCacheError):
    """Offline QA was requested but no OCR result exists for the image."""


def image_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class OcrTextCache:
    """Persist Vision response text for repeatable, API-free QA parser runs."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._entries: dict[str, dict[str, Any]] = {}
        self.hit_count = 0
        self.miss_count = 0
        self.write_count = 0
        if self.path.is_file():
            self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise OcrCacheError(
                f"OCR 캐시 파일을 읽을 수 없습니다: {self.path}"
            ) from exc

        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != CACHE_SCHEMA_VERSION
            or not isinstance(payload.get("entries"), dict)
        ):
            raise OcrCacheError(
                f"지원하지 않는 OCR 캐시 형식입니다: {self.path}"
            )
        self._entries = payload["entries"]

    def get(self, content: bytes) -> str | None:
        digest = image_sha256(content)
        entry = self._entries.get(digest)
        if entry is None:
            self.miss_count += 1
            return None

        try:
            text = entry["text"]
            if not isinstance(text, str):
                raise TypeError("text must be a string")
        except (KeyError, TypeError, ValueError) as exc:
            raise OcrCacheError(
                f"OCR 캐시 항목이 손상되었습니다: {digest[:12]}"
            ) from exc

        self.hit_count += 1
        return text

    def put(
        self,
        content: bytes,
        text: str,
        *,
        file_name: str = "",
        source: str = "",
    ) -> None:
        if not isinstance(text, str):
            raise TypeError("OCR cache text must be a string")
        digest = image_sha256(content)
        self._entries[digest] = {
            "file_name": Path(file_name).name if file_name else "",
            "source": source,
            "text": text,
        }
        self._write()
        self.write_count += 1

    def _write(self) -> None:
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "entries": self._entries,
        }
        temporary_path = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary_path, self.path)
        except OSError as exc:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise OcrCacheError(
                f"OCR 캐시 파일을 저장할 수 없습니다: {self.path}"
            ) from exc

    def __len__(self) -> int:
        return len(self._entries)
