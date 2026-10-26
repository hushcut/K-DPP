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


def _vertical_bands(words: list[OcrWord], slope: float = 0.0,
                    gap_ratio: float = 0.5) -> list[list[OcrWord]]:
    """Separate distant text regions so a folded tag has local angles."""
    bands: list[list[OcrWord]] = []
    bottoms: list[float] = []
    heights: list[float] = []

    def bounds(word):
        if not slope or len(word.vertices) != 4:
            return float(word.top), float(word.bottom)
        values = [y - slope * x for x, y in word.vertices]
        return min(values), max(values)

    for word in sorted(words, key=lambda item: (bounds(item)[0], item.left)):
        top, bottom = bounds(word)
        height = max(1.0, bottom - top)
        if bands:
            gap = top - bottoms[-1]
            if gap <= gap_ratio * min(heights[-1], height):
                bands[-1].append(word)
                bottoms[-1] = max(bottoms[-1], bottom)
                heights[-1] = min(heights[-1], height)
                continue
        bands.append([word])
        bottoms.append(bottom)
        heights.append(height)
    return bands


def _aligned_with_slope(word: OcrWord, slope: float, *, allow_quantisation: bool = False) -> bool:
    """Check both polygon edges, including boxes too short to set an angle."""
    if len(word.vertices) != 4:
        return False
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = word.vertices
    if min(x1 - x0, x2 - x3, y3 - y0, y2 - y1) <= 0:
        return False
    # Integer vertices can move an edge one pixel past the angular boundary,
    # especially on a short glyph. Keep the existing angular tolerance and
    # bound the additional displacement in pixels on BOTH polygon edges.
    # Extra tolerance cannot establish a flat or opposite edge's direction.
    return all(abs(dy - slope * dx) <= 0.06 * dx
               or (allow_quantisation and dy * slope > 0 and abs(dy - slope * dx) <= 0.06 * dx + 1)
               for dx, dy in ((x1 - x0, y1 - y0), (x2 - x3, y2 - y3)))


def _split_tilted_band(words: list[OcrWord], *, allow_quantisation: bool = False) -> list[tuple[list[OcrWord], float]]:
    """Split a local direction only when every other box is outside its band."""
    slopes = sorted({value for word in words if (value := _word_slope(word))})
    choices = {}
    for slope in slopes:
        compatible = [word for word in words if _aligned_with_slope(
            word, slope, allow_quantisation=allow_quantisation)]
        for region in _vertical_bands(compatible, slope, gap_ratio=2.0):
            local_slope = _band_slope(region)
            if not local_slope:
                continue

            def extent(word):
                points = word.vertices or ((word.left, word.top), (word.right, word.top),
                                           (word.right, word.bottom), (word.left, word.bottom))
                values = [y - local_slope * x for x, y in points]
                return min(values), max(values)

            low = min(extent(word)[0] for word in region)
            high = max(extent(word)[1] for word in region)
            selected = set(region)
            above, below = [], []
            for word in words:
                if word in selected:
                    continue
                start, end = extent(word)
                if end < low - 1:
                    above.append(word)
                elif start > high + 1:
                    below.append(word)
                else:
                    break
            else:
                choices[frozenset(region)] = (above, region, below, local_slope)
    # Preserve an existing partition, including ambiguity. Retry at most once
    # with pixel precision only when the strict geometry found no region.
    if not choices and not allow_quantisation:
        return _split_tilted_band(words, allow_quantisation=True)
    # Competing partitions never get selected by parser success or totals.
    if len(choices) != 1:
        return [(words, 0.0)]
    above, region, below, slope = next(iter(choices.values()))
    return [(group, _band_slope(group) if group is not region else slope)
            for group in (above, region, below) if group]


def spatial_text_from_words(words: list[OcrWord]) -> str:
    """Reassemble rows, correcting supported local tilt from word polygons."""
    pages: list[str] = []
    for page in sorted({word.page for word in words}):
        page_words = [word for word in words if word.page == page]
        if not any(_word_slope(word) for word in page_words):
            pages.append(_horizontal_rows(page_words))
            continue
        # Partition in the supported reading direction first: distant columns
        # of one tilted row can occupy disjoint horizontal bands.
        page_slope = _band_slope(page_words)
        drift = abs(page_slope) * (max(word.right for word in page_words) - min(word.left for word in page_words))
        if drift <= median(_projected_height(word, page_slope) for word in page_words):
            # Small drift already fits the local row grouping. Repartitioning
            # it could split nearby captions into artificial numeric rows.
            page_slope = 0.0
        bands = _vertical_bands(page_words, page_slope)
        regions = []
        for band in bands:
            slope = _band_slope(band)
            if (not slope and page_slope
                    and all(_aligned_with_slope(word, page_slope) for word in band)):
                slope = page_slope
            regions.extend([(band, slope)] if slope else _split_tilted_band(band))
        slopes = [slope for _band, slope in regions]
        if not any(slopes):
            pages.append(_horizontal_rows(page_words))
        else:
            pages.append("\n".join(
                _horizontal_rows(band, slope) for band, slope in regions
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
