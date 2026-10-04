"""Locate material content from existing OCR boxes and map cropped rereads back."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math
from statistics import median
from typing import TYPE_CHECKING

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

from apps.text.material_extraction import declared_part, extract_materials, normalize_text, unresolved_material_tokens
from apps.text.ocr_errors import ImageTooLargeError, InvalidImageError
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
        return None
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
        return None
    top = min(word.top for word in anchors + nearby_percentages) - 2.5 * font_height
    bottom = max(word.bottom for word in anchors + nearby_percentages) + 2.5 * font_height
    # Keep complete neighbouring rows, including separate numbers and part names.
    context = [word for word in words if top <= word.center_y <= bottom]
    left = max(0, math.floor(min(word.left for word in context) - 2 * font_height))
    right = min(width, math.ceil(max(word.right for word in context) + 2 * font_height))
    top, bottom = max(0, math.floor(top)), min(height, math.ceil(bottom))
    if right - left < 128 or bottom - top < 32 or (right-left) * (bottom-top) >= width * height * 0.85:
        return None
    return left, top, right, bottom


def prepare_material_region(content: bytes, box: tuple[int, int, int, int], *, rotated: bool = False) -> RegionImage:
    """Crop and enhance, returning an inverse affine map to original pixels."""

    validated = validate_image_bytes(content)
    if len(box) != 4 or any(type(value) is not int for value in box):
        raise InvalidImageError('소재 영역의 좌표가 올바르지 않습니다.')
    left, top, right, bottom = box
    if not (0 <= left < right <= validated.width and 0 <= top < bottom <= validated.height):
        raise InvalidImageError('소재 영역의 좌표가 올바르지 않습니다.')
    try:
        with Image.open(BytesIO(validated.content)) as image:
            if image.getexif().get(274, 1) != 1:
                raise InvalidImageError('방향이 확인되지 않은 이미지의 소재 영역은 자르지 않습니다.')
            crop = image.crop(box).convert('L')
        width, height = crop.size
        scale = min(max(1.0, MIN_OCR_WIDTH / width), MAX_OCR_WIDTH / width,
                    math.sqrt(MAX_PREPROCESSED_PIXELS / (width * height)),
                    MAX_PREPROCESSED_DIMENSION / max(width, height))
        prepared_width, prepared_height = max(1, int(width*scale)), max(1, int(height*scale))
        crop = crop.resize((prepared_width, prepared_height), Image.Resampling.LANCZOS)
        if rotated:
            crop = crop.rotate(-3, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
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
        angle = math.radians(-3 if rotated else 0)
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
