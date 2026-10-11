"""Locate material content from existing OCR boxes and map cropped rereads back."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math
import re
from statistics import median
from typing import TYPE_CHECKING

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

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
    enhancement: str = "standard"


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
        # OCR aliases at one physical location are one observation.
        if any(word.page == other.page
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


def _composition_header_region(words, width, height):
    """소재명이 누락돼도 가까운 조성·혼용 제목으로 표 위치만 제안한다."""
    composition = [word for word in words if normalize_text(word.text).strip(":()") == "조성"]
    blending = [word for word in words if normalize_text(word.text).strip(":()") in {"혼용", "혼용률"}]
    pairs = [(first, second) for first in composition for second in blending
             if abs(first.center_y - second.center_y) <= max(first.height, second.height)
             and 0 < second.center_x - first.center_x <= 12 * max(first.height, second.height)]
    if not pairs:
        return None
    headers = list(dict.fromkeys(word for pair in pairs for word in pair))
    font_height = median(word.height for word in headers)
    if max(word.center_y for word in headers) - min(word.center_y for word in headers) > 2 * font_height:
        return None
    row = [word for word in words if abs(word.center_y - median(w.center_y for w in headers)) <= font_height
           and min(w.left for w in headers) - 6 * font_height <= word.center_x
           <= max(w.right for w in headers) + 3 * font_height]
    left = max(0, math.floor(min(word.left for word in row) - 3 * font_height))
    right = min(width, math.ceil(max(word.right for word in row) + 2 * font_height))
    top = max(0, math.floor(min(word.top for word in headers) - font_height))
    bottom = min(height, math.ceil(max(word.bottom for word in headers) + 5 * font_height))
    context = [word for word in words if top <= word.center_y <= bottom
               and left - font_height <= word.center_x <= right + font_height]
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
    if geometry is None:
        context = list(dict.fromkeys(word for candidate in candidates
                       if candidate.image_key and candidate.image_variant_key and len(candidate.image_region) == 4
                       for word in candidate.image_words if word.page == 0
                       and left <= word.left < word.right <= right and top <= word.top < word.bottom <= bottom
                       and sum(character.isalpha() for character in word.text) >= 2))
        geometry = _supported_geometry(context)
        if not words:
            words = context
    heights = [value[1] if (value := _word_geometry(word)) is not None else word.height for word in words]
    font_height = median(heights) if heights else None
    # 근거 없는 방향과 거의 수평인 글자는 기존 작은 회전 후보를 유지한다.
    angle = geometry[0] if geometry is not None and abs(geometry[0]) >= 5 else -3.0
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
    header_region = _composition_header_region(words, width, height)
    if header_region is not None and all(
        header_region[0] <= word.left < word.right <= header_region[2]
        and header_region[1] <= word.top < word.bottom <= header_region[3]
        for word in percentages
    ):
        return header_region
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


def _local_contrast(crop):
    """천 무늬와 완만한 조명 변화를 완화하고 남은 글자 대비를 넓힌다."""
    smooth = crop.filter(ImageFilter.MedianFilter(3))
    background = smooth.filter(ImageFilter.GaussianBlur(max(8, min(64, min(crop.size) / 6))))
    corrected = ImageChops.subtract(smooth, background, offset=128)
    return corrected.point([max(0, min(255, 240 + 4 * (value - 128))) for value in range(256)])



def _mild_local_contrast(crop, *, denoise=False):
    """Flatten lighting after enlargement, retaining fine printed strokes."""
    gray = crop.convert('L')
    if denoise:
        # Blend rather than replace: a one-pixel stroke survives the median.
        gray = Image.blend(gray, gray.filter(ImageFilter.MedianFilter(3)), 0.30)
    background = gray.filter(ImageFilter.GaussianBlur(max(12, min(96, min(gray.size) / 8))))
    flattened = ImageChops.subtract(gray, background, offset=128).point(
        [max(0, min(255, round(232 + 1.6 * (value - 128)))) for value in range(256)]
    )
    return Image.blend(gray, flattened, 0.65)


def _faint_print_contrast(crop, *, font_height=None):
    """Reduce fabric texture before contrast gain, retaining thin ink."""
    gray = crop.convert('L')
    height = font_height if font_height is not None else 24.0
    # The earlier mild blur amplified the remaining weave with the letters.
    # Limit smoothing relative to text height; retain 10% of the original so
    # even isolated one-pixel strokes survive rather than becoming background.
    radius = max(0.5, min(2.0, height * 0.07))
    smooth = Image.blend(gray, gray.filter(ImageFilter.GaussianBlur(radius)), 0.90)
    background = smooth.filter(ImageFilter.GaussianBlur(max(12, min(96, height * 1.5))))
    flattened = ImageChops.subtract(smooth, background, offset=128)
    # Preserve gray levels and printed gaps instead of inventing hard edges.
    return flattened.point([max(0, min(255, round(242 + 5.5 * (value - 128))))
                            for value in range(256)])


def _needs_local_contrast(crop):
    background = crop.filter(ImageFilter.GaussianBlur(max(8, min(64, min(crop.size) / 6))))
    if ImageStat.Stat(background).stddev[0] >= 12:
        return True
    histogram = crop.histogram()
    total = sum(histogram)
    cumulative, low, high = 0, None, 255
    for value, count in enumerate(histogram):
        cumulative += count
        if low is None and cumulative >= 0.05 * total:
            low = value
        if cumulative >= 0.95 * total:
            high = value
            break
    return low is not None and 8 <= high - low <= 64


def prepare_material_region(
    content: bytes, box: tuple[int, int, int, int], *, rotated: bool = False,
    font_height: float | None = None, rotation_degrees: float | None = None,
    enhancement: str = "standard",
    word_boxes: tuple[tuple[int, int, int, int], ...] = (),
) -> RegionImage:
    """Crop and enhance, returning an inverse affine map to original pixels."""

    validated = validate_image_bytes(content)
    if type(enhancement) is not str or enhancement not in {"standard", "original", "local_contrast", "adaptive", "adaptive_mild", "mild_contrast", "mild_denoise", "faint_print"}:
        raise InvalidImageError('소재 영역 전처리 방식이 올바르지 않습니다.')
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
            crop = image.crop(box).convert('RGB' if enhancement == 'original' else 'L')
        threshold = _material_ink_threshold(crop, box, word_boxes) if rotated and enhancement == "standard" else None
        if threshold is not None:
            crop = crop.point(lambda value: 255 if value > threshold else 0)
        selected = enhancement
        if selected in {'adaptive', 'adaptive_mild'}:
            if _needs_local_contrast(crop):
                selected = 'local_contrast'
            else:
                selected = 'mild_contrast' if selected == 'adaptive_mild' else 'standard'
        if selected == 'local_contrast':
            crop = _local_contrast(crop)
        elif selected == 'faint_print':
            crop = _faint_print_contrast(crop, font_height=font_height)
        width, height = crop.size
        # 작은 글자는 목표 48픽셀 높이까지 확대하되 기존 픽셀·크기 한도를 유지한다.
        font_scale = 48.0 / font_height if font_height is not None else 1.0
        scale = min(max(1.0, MIN_OCR_WIDTH / width, font_scale), MAX_OCR_WIDTH / width,
                    math.sqrt(MAX_PREPROCESSED_PIXELS / (width * height)),
                    MAX_PREPROCESSED_DIMENSION / max(width, height))
        prepared_width, prepared_height = max(1, int(width*scale)), max(1, int(height*scale))
        crop = crop.resize((prepared_width, prepared_height), Image.Resampling.LANCZOS)
        if rotated:
            fill = (255, 255, 255) if crop.mode == 'RGB' else 255
            crop = crop.rotate(turn_angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=fill)
        canvas_width, canvas_height = crop.size
        final_scale = min(1.0, math.sqrt(MAX_PREPROCESSED_PIXELS / (canvas_width*canvas_height)),
                          MAX_PREPROCESSED_DIMENSION / max(canvas_width, canvas_height))
        if final_scale < 1:
            crop = crop.resize((max(1, int(canvas_width*final_scale)), max(1, int(canvas_height*final_scale))), Image.Resampling.LANCZOS)
        output_width, output_height = crop.size
        if selected == 'standard':
            crop = ImageOps.autocontrast(crop)
            if threshold is None:
                crop = crop.filter(ImageFilter.UnsharpMask(radius=1.4, percent=150, threshold=3))
        elif selected == 'local_contrast':
            crop = crop.filter(ImageFilter.UnsharpMask(radius=1.0, percent=100, threshold=3))
        elif selected in {'mild_contrast', 'mild_denoise'}:
            crop = _mild_local_contrast(crop, denoise=selected == 'mild_denoise')
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
        return RegionImage(encoded, 'material_crop_rotated' if rotated else 'material_crop', transform, tuple(map(float, box)), selected)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, MemoryError) as exc:
        raise ImageTooLargeError('소재 영역 이미지가 안전한 처리 범위를 넘습니다.') from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError('소재 영역 이미지 처리에 실패했습니다.') from exc


def material_region_word_boxes(
    candidates: list[OcrCandidate], box: tuple[int, int, int, int],
) -> tuple[tuple[int, int, int, int], ...]:
    """Return observed complete word boxes for pixel quality checks only."""
    left, top, right, bottom = box
    framed = [candidate for candidate in candidates
              if candidate.image_key and candidate.image_variant_key and len(candidate.image_region) == 4]
    if len({candidate.image_key for candidate in framed}) != 1:
        return ()
    return tuple(dict.fromkeys((word.left, word.top, word.right, word.bottom)
                 for candidate in framed for word in candidate.image_words if word.page == 0
                 and left <= word.left < word.right <= right and top <= word.top < word.bottom <= bottom))


def _material_ink_threshold(
    crop: Image.Image, box: tuple[int, int, int, int],
    word_boxes: tuple[tuple[int, int, int, int], ...],
) -> int | None:
    """Use Otsu only when every complete observed word keeps ink and clear margins.

    This selects an image filter, never validates text or repairs percentages.
    Words already clipped by the existing region are not quality observations.
    """
    if not isinstance(word_boxes, (tuple, list)) or not 2 <= len(word_boxes) <= 256:
        return None
    left, top, right, bottom = box
    if crop.mode != 'L' or crop.size != (right-left, bottom-top):
        return None
    unique = []
    for bounds in word_boxes:
        if (not isinstance(bounds, (tuple, list)) or len(bounds) != 4 or any(type(value) is not int for value in bounds)
                or not (left <= bounds[0] < bounds[2] <= right and top <= bounds[1] < bounds[3] <= bottom)):
            return None
        x, y, r, b = bounds
        if not any(abs((x+r-ox-oright)/2) < 0.4 * min(r-x, oright-ox)
                   and abs((y+b-oy-obottom)/2) < 0.4 * min(b-y, obottom-oy)
                   for ox, oy, oright, obottom in unique):
            unique.append(bounds)
    if len(unique) < 2:
        return None
    checks = []
    inspected_pixels = crop.width * crop.height
    for x, y, r, b in word_boxes:
        padding = max(1, math.ceil(0.12 * (b-y)))
        outer = (x-left-padding, y-top-padding, r-left+padding, b-top+padding)
        if not (0 <= outer[0] < outer[2] <= crop.width and 0 <= outer[1] < outer[3] <= crop.height):
            return None
        area = (r-x)*(b-y)
        outer_area = (outer[2]-outer[0])*(outer[3]-outer[1])
        inspected_pixels += area + outer_area
        if inspected_pixels > MAX_PREPROCESSED_PIXELS:
            return None
        checks.append(((x-left, y-top, r-left, b-top), outer, area, outer_area-area))
    histogram = crop.histogram()
    total = sum(histogram)
    total_sum = sum(index*count for index, count in enumerate(histogram))
    weight = partial_sum = 0
    best_variance, threshold = 0.0, None
    for index, count in enumerate(histogram[:-1]):
        weight += count
        partial_sum += index*count
        if not weight or weight == total:
            continue
        variance = weight*(total-weight)*(partial_sum/weight-(total_sum-partial_sum)/(total-weight))**2
        if variance > best_variance:
            best_variance, threshold = variance, index
    if threshold is None:
        return None
    mask = crop.point(lambda value: 255 if value > threshold else 0)
    # Check all observations, including numeric, punctuation and unknown words;
    # physical-box deduplication supplies only the minimum observation count.
    for inner, outer, area, ring_area in checks:
        ink = mask.crop(inner).histogram()[0]
        outer_ink = mask.crop(outer).histogram()[0]
        if not 0.05 <= ink/area <= 0.55 or (outer_ink-ink)/ring_area > 0.10:
            return None
    return threshold


def find_complete_material_region(candidates: list[OcrCandidate], region: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    """End a crop before a complete care heading instead of cutting its letters."""
    from apps.text.ocr_corrections import _row_words
    from apps.text.parse_label import build_line_infos, _is_metadata_line

    left, top, right, bottom = region
    heading = re.compile(
        r"[\[(]?\s*(?:\d{1,2}\s*[.)\]:]?\s*)?"
        r"(?:세탁\s*(?:및\s*취급\s*)?시\s*주의\s*사항"
        r"|(?:wash(?:ing)?|care)\s+instructions?|washing\s+care)\s*[\])}:]*"
    )
    image_keys = {candidate.image_key for candidate in candidates if candidate.image_key}
    if len(image_keys) != 1:
        return None
    words = set()
    metadata = set()
    for candidate in candidates:
        if (not candidate.image_key or not candidate.image_variant_key
                or len(candidate.image_region) != 4 or not candidate.image_words):
            continue
        local = tuple(word for word in candidate.image_words if word.page == 0)
        words.update(word for word in local if word.left < right and word.right > left
                     and word.top < bottom and word.bottom > top)
        for info in build_line_infos(candidate.text):
            if (heading.fullmatch(info.normalized) and _is_metadata_line(info) and not (info.materials or info.numbers
                    or info.explicit_percent or info.invalid_evidence or info.unresolved_materials)):
                located = _row_words(info.raw, local)
                if located:
                    metadata.update(located)
    cut = {word for word in words if word.top < bottom < word.bottom}
    if not cut or not cut <= metadata:
        return None
    adjusted = min(word.top for word in cut) - 2
    removed = {word for word in words if word.bottom > adjusted}
    if not removed <= metadata:
        return None
    retained = words - removed
    # Keep a real gap below every retained word, including unknown text,
    # separate numbers, part markers and punctuation.
    if (not retained or adjusted - top < 32
            or max(word.bottom for word in retained) + 2 > adjusted):
        return None
    return left, top, right, adjusted
