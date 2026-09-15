from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any

CACHE_SCHEMA_VERSION = 2
LEGACY_CACHE_SCHEMA_VERSION = 1
OCR_CACHE_CONTENT_VERSION = 1
CACHE_LOCK_TIMEOUT_SECONDS = 5.0
CACHE_LOCK_RETRY_SECONDS = 0.05
CACHE_LOCK_STALE_SECONDS = 120.0


class OcrCacheError(RuntimeError):
    """The local QA OCR cache is unreadable or cannot be updated safely."""


class OcrCacheMissError(OcrCacheError):
    """Offline QA was requested but no OCR result exists for the image."""


def image_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class OcrTextCache:
    """Persist Vision response text for repeatable, API-free QA parser runs."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        reset_stale_cache: bool = False,
        content_version: int | None = None,
        lock_timeout_seconds: float = CACHE_LOCK_TIMEOUT_SECONDS,
    ) -> None:
        self.path = Path(path)
        self._lock_path = self.path.with_name(self.path.name + ".lock")
        self._reset_stale_cache = reset_stale_cache
        self.content_version = (
            OCR_CACHE_CONTENT_VERSION
            if content_version is None
            else content_version
        )
        self._lock_timeout_seconds = lock_timeout_seconds
        self._entries: dict[str, dict[str, Any]] = {}
        self.hit_count = 0
        self.miss_count = 0
        self.write_count = 0
        if self.path.is_file():
            self._load()

    def _load(self) -> None:
        self._entries = self._read_entries()

    def _read_entries(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise OcrCacheError(
                f"OCR 캐시 파일을 읽을 수 없습니다: {self.path}"
            ) from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("entries"), dict):
            raise OcrCacheError(
                f"지원하지 않는 OCR 캐시 형식입니다: {self.path}"
            )

        schema_version = payload.get("schema_version")
        if schema_version == LEGACY_CACHE_SCHEMA_VERSION:
            return dict(payload["entries"])
        if schema_version != CACHE_SCHEMA_VERSION:
            raise OcrCacheError(
                f"지원하지 않는 OCR 캐시 형식입니다: {self.path}"
            )
        if payload.get("content_version") != self.content_version:
            if self._reset_stale_cache:
                return {}
            raise OcrCacheError(
                "OCR 파이프라인 버전이 다른 캐시입니다. "
                "--refresh-ocr-cache로 다시 생성하세요."
            )
        return dict(payload["entries"])

    def get(self, content: bytes) -> str | None:
        entry = self.get_entry(content)
        return entry["text"] if entry is not None else None

    def get_entry(self, content: bytes) -> dict[str, Any] | None:
        """Return a cached OCR payload without discarding optional layout text."""
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
        return dict(entry)

    def put(
        self,
        content: bytes,
        text: str,
        *,
        file_name: str = "",
        source: str = "",
        layout_text: str = "",
    ) -> None:
        if not isinstance(text, str):
            raise TypeError("OCR cache text must be a string")
        if not isinstance(layout_text, str):
            raise TypeError("OCR cache layout_text must be a string")
        digest = image_sha256(content)
        entry: dict[str, Any] = {
            "file_name": Path(file_name).name if file_name else "",
            "source": source,
            "text": text,
        }
        if layout_text:
            entry["layout_text"] = layout_text
        with self._exclusive_write_lock():
            latest_entries = (
                self._read_entries() if self.path.is_file() else dict(self._entries)
            )
            latest_entries[digest] = entry
            self._entries = latest_entries
            self._write_locked()
        self.write_count += 1

    @contextmanager
    def _exclusive_write_lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self._lock_timeout_seconds

        while True:
            try:
                descriptor = os.open(
                    self._lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                try:
                    lock_age = time.time() - self._lock_path.stat().st_mtime
                    if lock_age > CACHE_LOCK_STALE_SECONDS:
                        self._lock_path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    raise OcrCacheError(
                        f"OCR 캐시 잠금을 확인할 수 없습니다: {self._lock_path}"
                    ) from exc

                if time.monotonic() >= deadline:
                    raise OcrCacheError(
                        f"OCR 캐시가 다른 실행에서 사용 중입니다: {self.path}"
                    )
                time.sleep(CACHE_LOCK_RETRY_SECONDS)
            except OSError as exc:
                raise OcrCacheError(
                    f"OCR 캐시 잠금을 만들 수 없습니다: {self._lock_path}"
                ) from exc
            else:
                os.close(descriptor)
                break

        try:
            yield
        finally:
            try:
                self._lock_path.unlink(missing_ok=True)
            except OSError as exc:
                raise OcrCacheError(
                    f"OCR 캐시 잠금을 해제할 수 없습니다: {self._lock_path}"
                ) from exc

    def _write_locked(self) -> None:
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "content_version": self.content_version,
            "entries": self._entries,
        }
        temporary_path = self.path.with_name(self.path.name + ".tmp")
        try:
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
