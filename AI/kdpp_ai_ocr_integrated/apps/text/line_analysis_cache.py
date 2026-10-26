"""Reuse immutable row analysis only within the current synchronous analysis."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.text.composition_candidates import LineInfo

MAX_CACHED_LINE_ANALYSES = 128
MAX_CACHED_TEXT_CHARACTERS = 100_000


@dataclass(frozen=True)
class LineAnalysis:
    infos: tuple[LineInfo, ...]
    restored_indices: frozenset[int]
    translation_indices: frozenset[int]
    translation_warnings: tuple[str, ...]


@dataclass
class _LineAnalysisCache:
    entries: OrderedDict[str, LineAnalysis] = field(default_factory=OrderedDict)
    text_characters: int = 0


_current_cache: ContextVar[_LineAnalysisCache | None] = ContextVar("line_analysis_cache", default=None)


@contextmanager
def line_analysis_scope() -> Iterator[None]:
    """Nested OCR/parser calls share one bounded cache, cleared on every exit."""
    if _current_cache.get() is not None:
        yield
        return
    token = _current_cache.set(_LineAnalysisCache())
    try:
        yield
    finally:
        _current_cache.reset(token)


def reuse_line_analysis(text: str, build: Callable[[str], LineAnalysis]) -> LineAnalysis:
    """Keep literal text keys and immutable evidence; never cache exceptions."""
    cache = _current_cache.get()
    if cache is None or len(text) > MAX_CACHED_TEXT_CHARACTERS:
        return build(text)
    analysis = cache.entries.get(text)
    if analysis is not None:
        cache.entries.move_to_end(text)
        return analysis
    analysis = build(text)
    while cache.entries and (
        len(cache.entries) >= MAX_CACHED_LINE_ANALYSES
        or cache.text_characters + len(text) > MAX_CACHED_TEXT_CHARACTERS
    ):
        removed, _ = cache.entries.popitem(last=False)
        cache.text_characters -= len(removed)
    cache.entries[text] = analysis
    cache.text_characters += len(text)
    return analysis
