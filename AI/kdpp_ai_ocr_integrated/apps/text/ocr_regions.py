"""Locate material content from existing OCR boxes and map cropped rereads back."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math
import re
from statistics import median
from typing import TYPE_CHECKING

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

from apps.text.material_extraction import declared_part, extract_materials, normalize_text, unresolved_material_tokens
from apps.text.ocr_errors import ImageTooLargeError, InvalidImageError
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_image import (
    MAX_IMAGE_BYTES, MAX_PREPROCESSED_DIMENSION, MAX_PREPROCESSED_PIXELS,
    MAX_OCR_WIDTH, MIN_OCR_WIDTH, _encode_preprocessed_image, validate_image_bytes,
)

if TYPE_CHECKING:
    from apps.text.ocr_candidates import OcrCandidate


@dataclass(frozen=True)
class RegionImage:
    content: bytes
    source: str
    transform: tuple[float, ...]
    region: tuple[float, ...]


def _word_geometry(word: OcrWord) -> tuple[float, float] | None:
    """평행한 글자 상자에서 기울기와 실제 글자 높이를 구한다."""
    if len(word.vertices) != 4:
        return None
    points = word.vertices
    edges = [(points[1][0] - points[0][0], points[1][1] - points[0][1]),
             (points[2][0] - points[3][0], points[2][1] - points[3][1])]
    lengths = [math.hypot(x, y) for x, y in edges]
    if min(lengths) <= 0:
        return None
    thickness = abs(edges[0][0] * (points[3][1] - points[0][1])
                    - edges[0][1] * (points[3][0] - points[0][0])) / lengths[0]
    if thickness <= 0 or min(lengths) < 2 * thickness:
        return None
    angles = [math.degrees(math.atan2(y, x)) for x, y in edges]
    if abs(angles[0] - angles[1]) > 5:
        return None
    return sum(angles) / 2, thickness


def _supported_geometry(words: list[OcrWord]) -> tuple[float, float] | None:
    unique = []
    for word in sorted(words, key=lambda item: (item.left, item.top, item.right, item.bottom, item.text)):
        if any(normalize_text(word.text) == normalize_text(other.text) and word.page == other.page
               and abs(word.center_x - other.center_x) < 0.4 * min(word.right - word.left, other.right - other.left)
               and abs(word.center_y - other.center_y) < 0.4 * min(word.height, other.height)
               for other in unique):
            continue
        unique.append(word)
    values = [value for word in unique if (value := _word_geometry(word)) is not None]
    if len(values) < 2:
        return None
    angle = median(value[0] for value in values)
    supporters = [value for value in values if abs(value[0] - angle) <= 2.5]
    if len(supporters) < 2 or len(supporters) < 0.75 * len(values):
        return None
    if any(abs(value[0] - angle) > 7 or value[0] * angle < 0 and abs(value[0]) >= 2.5 for value in values):
        return None
    return round(angle * 2) / 2, median(value[1] for value in supporters)


def _fallback_material_region(
    words: list[OcrWord], width: int, height: int,
) -> tuple[int, int, int, int] | None:
    """퍼센트 손상 또는 옆 방향 글자에서 관측 근거로만 재인식 위치를 찾는다."""
    fibers = [word for word in words if extract_materials(word.text)]
    if not fibers:
        return None
    geometry = _supported_geometry(fibers)
    sideways = geometry is not None and 60 <= abs(geometry[0]) <= 120
    font_height = geometry[1] if sideways else median(word.height for word in fibers)
    ratios = [word for word in words if re.fullmatch(r"\d{1,4}(?:[.,]\d+)?%?", normalize_text(word.text))
              or normalize_text(word.text) == "%"]
    if sideways:
        nearby = [word for word in ratios if any(
            abs(word.center_x - fiber.center_x) <= 4 * font_height
            and abs(word.center_y - fiber.center_y) <= 14 * font_height for fiber in fibers)]
        if not nearby or not any("%" in normalize_text(word.text) for word in nearby):
            return None
        selected = [fiber for fiber in fibers if any(
            abs(word.center_x - fiber.center_x) <= 4 * font_height
            and abs(word.center_y - fiber.center_y) <= 14 * font_height for word in nearby)] + nearby
    else:
        paired = [(fiber, ratio) for fiber in fibers for ratio in ratios
                  if any(character.isdecimal() for character in ratio.text)
                  and abs(fiber.center_y - ratio.center_y) <= max(fiber.height, ratio.height)
                  and abs(fiber.center_x - ratio.center_x) <= 20 * font_height]
        # 서로 다른 소재와 각각의 숫자 행이 있을 때만 검출을 확장한다.
        if (len({key for fiber, _ in paired for key in extract_materials(fiber.text)}) < 2
                or len({(ratio.left, ratio.top, ratio.right, ratio.bottom) for _, ratio in paired}) < 2):
            return None
        selected = list(dict.fromkeys(word for pair in paired for word in pair))
        if max(word.bottom for word in selected) - min(word.top for word in selected) > 12 * font_height:
            return None
    left = max(0, math.floor(min(word.left for word in selected) - 2 * font_height))
    right = min(width, math.ceil(max(word.right for word in selected) + 2 * font_height))
    top = max(0, math.floor(min(word.top for word in selected) - 2.5 * font_height))
    bottom = min(height, math.ceil(max(word.bottom for word in selected) + 2.5 * font_height))
    # 영역 안의 부위 제목과 분리된 비율을 함께 포함한다.
    context = [word for word in words if top <= word.center_y <= bottom
               and left - 2 * font_height <= word.center_x <= right + 2 * font_height]
    if context:
        left = max(0, math.floor(min(left, min(word.left for word in context) - font_height)))
        right = min(width, math.ceil(max(right, max(word.right for word in context) + font_height)))
    if right - left < 128 or bottom - top < 32 or (right - left) * (bottom - top) >= width * height * 0.85:
        return None
    return left, top, right, bottom


def material_region_options(
    candidates: list[OcrCandidate], box: tuple[int, int, int, int],
) -> tuple[float | None, float]:
    """소재 상자의 글자 높이와 일관된 기울기를 전처리 옵션으로 반환한다."""
    left, top, right, bottom = box
    words = list(dict.fromkeys(word for candidate in candidates
                 if candidate.image_key and candidate.image_variant_key and len(candidate.image_region) == 4
                 for word in candidate.image_words if word.page == 0
                 and left <= word.left < word.right <= right and top <= word.top < word.bottom <= bottom
                 and extract_materials(word.text)))
    geometry = _supported_geometry(words)
    heights = [value[1] if (value := _word_geometry(word)) is not None else word.height for word in words]
    font_height = median(heights) if heights else None
    # 근거 없는 방향과 거의 수평인 글자는 기존 작은 회전 후보를 유지한다.
    angle = geometry[0] if geometry is not None and abs(geometry[0]) >= 1 else -3.0
    return font_height, angle


def find_material_region(candidates: list[OcrCandidate], width: int, height: int) -> tuple[int, int, int, int] | None:
    """Locate observed material/unknown percentage rows in original geometry."""

    # Cropping a thumbnail does not restore its missing source pixels.
    if max(width, height) < 512:
        return None
    seen = set()
    words = []
    for candidate in candidates:
        if not candidate.image_key or not candidate.image_variant_key or len(candidate.image_region) != 4:
            continue
        for word in candidate.image_words:
            key = (word.text, word.left, word.top, word.right, word.bottom, word.page)
            if key in seen or word.page != 0 or not (0 <= word.left < word.right <= width and 0 <= word.top < word.bottom <= height):
                continue
            seen.add(key)
            words.append(word)
    if not words:
        return None
    geometry = _supported_geometry([word for word in words if extract_materials(word.text)])
    if geometry is not None and 60 <= abs(geometry[0]) <= 120:
        return _fallback_material_region(words, width, height)
    care_headers = {'shrinkage', '수축률', '수축율'}
    percentages = [word for word in words if '%' in normalize_text(word.text) and not any(
        normalize_text(other.text).strip(':') in care_headers
        and abs(word.center_y - other.center_y) <= max(word.height, other.height)
        for other in words
    )]
    anchors = [word for word in words if extract_materials(word.text) or declared_part(word.text)
               or unresolved_material_tokens(word.text)
               or normalize_text(word.text).strip(':()') in {'composition', 'content', '혼용률', '혼용', '소재', '섬유'}]
    # An unreadable name alone has no composition evidence. Use its observed
    # neighbouring percentage to locate the row without accepting the name.
    for ratio in percentages:
        row = [word for word in words if abs(word.center_y-ratio.center_y) <= max(word.height, ratio.height)
               and abs(word.center_x-ratio.center_x) <= 30 * max(word.height, ratio.height)]
        names = [word for word in row if sum(character.isalpha() for character in word.text) >= 2]
        # Unknown rows are allowed as crop locations, never as valid fibers.
        anchors.extend(names)
    if not percentages or not anchors:
        return _fallback_material_region(words, width, height)
    font_height = float(median(word.height for word in anchors + percentages))
    nearby_percentages = [word for word in percentages if any(
        abs(word.center_y - anchor.center_y) <= 6 * max(font_height, anchor.height, word.height)
        for anchor in anchors
    )]
    anchors = [word for word in anchors if any(
        abs(word.center_y - ratio.center_y) <= 6 * max(font_height, word.height, ratio.height)
        for ratio in nearby_percentages
    )]
    if not nearby_percentages or not anchors:
        return _fallback_material_region(words, width, height)
    top = min(word.top for word in anchors + nearby_percentages) - 2.5 * font_height
    bottom = max(word.bottom for word in anchors + nearby_percentages) + 2.5 * font_height
    # Keep complete neighbouring rows, including separate numbers and part names.
    context = [word for word in words if top <= word.center_y <= bottom]
    left = max(0, math.floor(min(word.left for word in context) - 2 * font_height))
    right = min(width, math.ceil(max(word.right for word in context) + 2 * font_height))
    top, bottom = max(0, math.floor(top)), min(height, math.ceil(bottom))
    if right - left < 128 or bottom - top < 32 or (right-left) * (bottom-top) >= width * height * 0.85:
        return _fallback_material_region(words, width, height)
    return left, top, right, bottom


def prepare_material_region(
    content: bytes, box: tuple[int, int, int, int], *, rotated: bool = False,
    font_height: float | None = None, rotation_degrees: float | None = None,
) -> RegionImage:
    """Crop and enhance, returning an inverse affine map to original pixels."""

    validated = validate_image_bytes(content)
    if len(box) != 4 or any(type(value) is not int for value in box):
        raise InvalidImageError('소재 영역의 좌표가 올바르지 않습니다.')
    if font_height is not None and (
        type(font_height) not in {int, float} or not math.isfinite(font_height) or font_height <= 0
    ):
        raise InvalidImageError('소재 글자 높이가 올바르지 않습니다.')
    if rotation_degrees is not None and (
        type(rotation_degrees) not in {int, float} or not math.isfinite(rotation_degrees)
        or abs(rotation_degrees) > 180
    ):
        raise InvalidImageError('소재 회전 각도가 올바르지 않습니다.')
    turn_angle = (rotation_degrees if rotation_degrees is not None else -3) if rotated else 0
    left, top, right, bottom = box
    if not (0 <= left < right <= validated.width and 0 <= top < bottom <= validated.height):
        raise InvalidImageError('소재 영역의 좌표가 올바르지 않습니다.')
    try:
        with Image.open(BytesIO(validated.content)) as image:
            if image.getexif().get(274, 1) != 1:
                raise InvalidImageError('방향이 확인되지 않은 이미지의 소재 영역은 자르지 않습니다.')
            crop = image.crop(box).convert('L')
        width, height = crop.size
        # 작은 글자는 목표 48픽셀 높이까지 확대하되 기존 픽셀·크기 한도를 유지한다.
        font_scale = 48.0 / font_height if font_height is not None else 1.0
        scale = min(max(1.0, MIN_OCR_WIDTH / width, font_scale), MAX_OCR_WIDTH / width,
                    math.sqrt(MAX_PREPROCESSED_PIXELS / (width * height)),
                    MAX_PREPROCESSED_DIMENSION / max(width, height))
        prepared_width, prepared_height = max(1, int(width*scale)), max(1, int(height*scale))
        crop = crop.resize((prepared_width, prepared_height), Image.Resampling.LANCZOS)
        if rotated:
            crop = crop.rotate(turn_angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
        canvas_width, canvas_height = crop.size
        final_scale = min(1.0, math.sqrt(MAX_PREPROCESSED_PIXELS / (canvas_width*canvas_height)),
                          MAX_PREPROCESSED_DIMENSION / max(canvas_width, canvas_height))
        if final_scale < 1:
            crop = crop.resize((max(1, int(canvas_width*final_scale)), max(1, int(canvas_height*final_scale))), Image.Resampling.LANCZOS)
        output_width, output_height = crop.size
        crop = ImageOps.autocontrast(crop).filter(ImageFilter.UnsharpMask(radius=1.4, percent=150, threshold=3))
        encoded = _encode_preprocessed_image(crop, image_format='JPEG')
        if len(encoded) > MAX_IMAGE_BYTES:
            raise ImageTooLargeError('소재 영역 이미지의 용량이 안전한 범위를 넘습니다.')
        ox, oy = width / prepared_width, height / prepared_height
        sx, sy = canvas_width / output_width, canvas_height / output_height
        angle = math.radians(turn_angle)
        cosine, sine = math.cos(angle), math.sin(angle)
        transform = (
            cosine*sx*ox, -sine*sy*ox, left + (prepared_width/2-cosine*canvas_width/2+sine*canvas_height/2)*ox,
            sine*sx*oy, cosine*sy*oy, top + (prepared_height/2-sine*canvas_width/2-cosine*canvas_height/2)*oy,
        )
        return RegionImage(encoded, 'material_crop_rotated' if rotated else 'material_crop', transform, tuple(map(float, box)))
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, MemoryError) as exc:
        raise ImageTooLargeError('소재 영역 이미지가 안전한 처리 범위를 넘습니다.') from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError('소재 영역 이미지 처리에 실패했습니다.') from exc
