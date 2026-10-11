"""Google Vision 단어 좌표를 라벨의 읽기 순서로 재구성한다."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any


@dataclass(frozen=True)
class OcrWord:
    text: str
    left: int
    top: int
    right: int
    bottom: int
    vertices: tuple[tuple[int, int], ...] = ()
    page: int = 0

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def height(self) -> int:
        return max(1, self.bottom - self.top)


def _horizontal_rows(words: list[OcrWord], slope: float = 0.0) -> str:
    """Group rows in projected coordinates without changing any word text."""
    lines: list[list[OcrWord]] = []
    line_center_y: list[float] = []
    line_height: list[float] = []
    for word in sorted(
        words, key=lambda item: (item.center_y - slope * item.center_x, item.left)
    ):
        center_y = word.center_y - slope * word.center_x
        height = _projected_height(word, slope)
        if lines:
            tolerance = max(4.0, min(line_height[-1], height) * 0.55)
            if abs(center_y - line_center_y[-1]) <= tolerance:
                lines[-1].append(word)
                count = len(lines[-1])
                line_center_y[-1] = (
                    line_center_y[-1] * (count - 1) + center_y
                ) / count
                line_height[-1] = max(line_height[-1], height)
                continue

        lines.append([word])
        line_center_y.append(center_y)
        line_height.append(height)

    return "\n".join(
        " ".join(word.text for word in sorted(line, key=lambda item: item.left))
        for line in lines
    )


def _projected_height(word: OcrWord, slope: float) -> float:
    if not slope or len(word.vertices) != 4:
        return float(word.height)
    projected = [y - slope * x for x, y in word.vertices]
    return max(1.0, max(projected) - min(projected))


def _word_slope(word: OcrWord) -> float | None:
    """Use parallel long box edges; short percentages cannot set the angle."""
    if len(word.vertices) != 4:
        return None
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = word.vertices
    top_width, bottom_width = x1 - x0, x2 - x3
    if min(top_width, bottom_width) <= 0 or min(y3 - y0, y2 - y1) <= 0:
        return None
    top_slope = (y1 - y0) / top_width
    bottom_slope = (y2 - y3) / bottom_width
    slope = (top_slope + bottom_slope) / 2
    if abs(top_slope - bottom_slope) > 0.06 or abs(slope) > 0.35:
        return None
    if min(top_width, bottom_width) < 2 * _projected_height(word, slope):
        return None
    return slope


def _band_slope(words: list[OcrWord]) -> float:
    slopes = [value for word in words if (value := _word_slope(word)) is not None]
    if len(slopes) < 2:
        return 0.0
    slope = median(slopes)
    supporting = [value for value in slopes if abs(value - slope) <= 0.04]
    # Estimate from geometry only, never from percentages, material names,
    # parser success, or a total of 100. Mixed directions keep the old layout.
    if len(supporting) < 2 or len(supporting) < 0.75 * len(slopes):
        return 0.0
    if any(
        abs(value - slope) > 0.12
        or (value * slope < 0 and abs(value) >= 0.04)
        for value in slopes
    ):
        return 0.0
    return slope if abs(slope) >= 0.015 else 0.0


def _vertical_bands(words: list[OcrWord]) -> list[list[OcrWord]]:
    """Separate distant text regions so a folded tag has local angles."""
    bands: list[list[OcrWord]] = []
    bottoms: list[int] = []
    heights: list[int] = []
    for word in sorted(words, key=lambda item: (item.top, item.left)):
        if bands:
            gap = word.top - bottoms[-1]
            if gap <= 0.5 * min(heights[-1], word.height):
                bands[-1].append(word)
                bottoms[-1] = max(bottoms[-1], word.bottom)
                heights[-1] = min(heights[-1], word.height)
                continue
        bands.append([word])
        bottoms.append(word.bottom)
        heights.append(word.height)
    return bands


def spatial_text_from_words(words: list[OcrWord]) -> str:
    """Reassemble rows, correcting supported local tilt from word polygons."""
    pages: list[str] = []
    for page in sorted({word.page for word in words}):
        page_words = [word for word in words if word.page == page]
        if not any(_word_slope(word) for word in page_words):
            pages.append(_horizontal_rows(page_words))
            continue
        bands = _vertical_bands(page_words)
        slopes = [_band_slope(band) for band in bands]
        if not any(slopes):
            pages.append(_horizontal_rows(page_words))
        else:
            pages.append("\n".join(
                _horizontal_rows(band, slope) for band, slope in zip(bands, slopes)
            ))
    return "\n".join(pages)


def extract_response_words(response: Any) -> tuple[OcrWord, ...]:
    """Retain the provider's word polygons for reproducible layout replay."""

    annotation = getattr(response, "full_text_annotation", None)
    pages = getattr(annotation, "pages", None) if annotation else None
    if not pages:
        return ()

    words: list[OcrWord] = []
    for page_index, page in enumerate(pages):
        for block in getattr(page, "blocks", ()):
            for paragraph in getattr(block, "paragraphs", ()):
                for word in getattr(paragraph, "words", ()):
                    text = "".join(
                        str(getattr(symbol, "text", ""))
                        for symbol in getattr(word, "symbols", ())
                    ).strip()
                    vertices = getattr(
                        getattr(word, "bounding_box", None),
                        "vertices",
                        (),
                    )
                    coordinates = [
                        (
                            int(getattr(vertex, "x", 0) or 0),
                            int(getattr(vertex, "y", 0) or 0),
                        )
                        for vertex in vertices
                    ]
                    if not text or not coordinates:
                        continue
                    x_values, y_values = zip(*coordinates)
                    words.append(
                        OcrWord(
                            text=text,
                            left=min(x_values),
                            top=min(y_values),
                            right=max(x_values),
                            bottom=max(y_values),
                            vertices=tuple(coordinates),
                            page=page_index,
                        )
                    )
    return tuple(words)


def extract_response_layout_text(response: Any) -> str:
    """Build text from Vision word coordinates when layout annotations exist."""
    return spatial_text_from_words(list(extract_response_words(response)))
