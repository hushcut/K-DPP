"""Google Vision 단어 좌표를 라벨의 읽기 순서로 재구성한다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OcrWord:
    text: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def height(self) -> int:
        return max(1, self.bottom - self.top)


def spatial_text_from_words(words: list[OcrWord]) -> str:
    """Reassemble OCR words into visual rows, ordered left to right."""

    if not words:
        return ""

    lines: list[list[OcrWord]] = []
    line_center_y: list[float] = []
    line_height: list[float] = []
    for word in sorted(words, key=lambda item: (item.center_y, item.left)):
        if lines:
            tolerance = max(4.0, min(line_height[-1], word.height) * 0.55)
            if abs(word.center_y - line_center_y[-1]) <= tolerance:
                lines[-1].append(word)
                count = len(lines[-1])
                line_center_y[-1] = (
                    line_center_y[-1] * (count - 1) + word.center_y
                ) / count
                line_height[-1] = max(line_height[-1], word.height)
                continue

        lines.append([word])
        line_center_y.append(word.center_y)
        line_height.append(float(word.height))

    return "\n".join(
        " ".join(word.text for word in sorted(line, key=lambda item: item.left))
        for line in lines
    )


def extract_response_layout_text(response: Any) -> str:
    """Build text from Vision word coordinates when layout annotations exist."""

    annotation = getattr(response, "full_text_annotation", None)
    pages = getattr(annotation, "pages", None) if annotation else None
    if not pages:
        return ""

    words: list[OcrWord] = []
    for page in pages:
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
                        )
                    )
    return spatial_text_from_words(words)
