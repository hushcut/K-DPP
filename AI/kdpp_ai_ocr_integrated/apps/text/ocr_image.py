"""OCR 입력 이미지 검증과 전처리 후보 생성."""

from __future__ import annotations

import math
import os
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError

from apps.text.ocr_errors import (
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedImageError,
)


MIN_OCR_WIDTH = 1800
MAX_OCR_WIDTH = 3200
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_ASPECT_RATIO = 20.0
MAX_PREPROCESSED_PIXELS = 16_000_000
MAX_PREPROCESSED_DIMENSION = 8192
SUPPORTED_IMAGE_FORMATS = {"JPEG", "PNG", "MPO"}

# Keep Pillow's own decompression-bomb protection aligned with the API limit.
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


@dataclass(frozen=True)
class ValidatedImage:
    content: bytes
    image_format: str
    width: int
    height: int


def _validate_image_dimensions(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise InvalidImageError("이미지 크기가 올바르지 않습니다.")

    if width * height >= MAX_IMAGE_PIXELS:
        raise ImageTooLargeError("이미지 해상도가 너무 큽니다.")

    aspect_ratio = max(width / height, height / width)
    if aspect_ratio > MAX_IMAGE_ASPECT_RATIO:
        raise ImageTooLargeError("이미지의 가로세로 비율이 너무 큽니다.")


def read_image_bytes(image_path: str | os.PathLike[str]) -> bytes:
    try:
        return Path(image_path).read_bytes()
    except OSError as exc:
        raise InvalidImageError(f"이미지 파일을 읽을 수 없습니다: {image_path}") from exc


def _convert_mpo_to_jpeg(content: bytes) -> bytes:
    """MPO의 첫 프레임을 Vision OCR이 받을 수 있는 JPEG로 변환한다."""

    try:
        with Image.open(BytesIO(content)) as image:
            frame = ImageOps.exif_transpose(image).convert("RGB")
            buffer = BytesIO()
            frame.save(buffer, format="JPEG", quality=95, optimize=True)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageTooLargeError(
            "MPO 이미지가 안전한 처리 범위를 넘습니다."
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError("MPO 이미지를 JPEG로 변환하지 못했습니다.") from exc
    except MemoryError as exc:
        raise ImageTooLargeError(
            "MPO 이미지를 변환할 메모리가 부족합니다."
        ) from exc

    converted = buffer.getvalue()
    if len(converted) > MAX_IMAGE_BYTES:
        raise ImageTooLargeError(
            f"변환된 MPO 이미지는 {MAX_IMAGE_BYTES // (1024 * 1024)}MB 이하여야 합니다."
        )
    return converted


def validate_image_bytes(
    content: bytes,
    *,
    declared_content_type: str | None = None,
) -> ValidatedImage:
    """OCR 호출 전에 파일 형식·용량·해상도를 검증한다."""

    if not content:
        raise InvalidImageError("이미지 파일이 비어 있습니다.")
    if len(content) > MAX_IMAGE_BYTES:
        raise ImageTooLargeError(
            f"이미지 파일은 {MAX_IMAGE_BYTES // (1024 * 1024)}MB 이하여야 합니다."
        )

    if declared_content_type:
        normalized_type = declared_content_type.split(";", 1)[0].strip().lower()
        if normalized_type not in {"image/jpeg", "image/png", "image/mpo"}:
            raise UnsupportedImageError("JPG, PNG 또는 MPO 이미지만 지원합니다.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                image_format = (image.format or "").upper()
                width, height = image.size
                _validate_image_dimensions(width, height)
                image.verify()
    except InvalidImageError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageTooLargeError(
            "안전한 처리 범위를 넘는 고해상도 이미지입니다."
        ) from exc
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise InvalidImageError("올바른 이미지 파일이 아닙니다.") from exc
    except MemoryError as exc:
        raise ImageTooLargeError(
            "이미지가 너무 커서 안전하게 처리할 수 없습니다."
        ) from exc

    if image_format not in SUPPORTED_IMAGE_FORMATS:
        raise UnsupportedImageError("JPG, PNG 또는 MPO 이미지만 지원합니다.")

    if image_format == "MPO":
        content = _convert_mpo_to_jpeg(content)

    return ValidatedImage(
        content=content,
        image_format=image_format,
        width=width,
        height=height,
    )


def _prepare_image_for_ocr(content: bytes) -> Image.Image:
    """OCR 후보가 공유하는 회전 보정·안전한 크기 조절을 적용한다."""

    with Image.open(BytesIO(content)) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        width, height = image.size
        _validate_image_dimensions(width, height)

        # 작은 글자는 키우되, 큰 이미지가 메모리를 과도하게 쓰지 않도록 상한을 둔다.
        scale = 1.0
        if width < MIN_OCR_WIDTH:
            scale = MIN_OCR_WIDTH / width
        elif width > MAX_OCR_WIDTH:
            scale = MAX_OCR_WIDTH / width

        pixel_scale = math.sqrt(MAX_PREPROCESSED_PIXELS / (width * height))
        dimension_scale = MAX_PREPROCESSED_DIMENSION / max(width, height)
        scale = min(scale, pixel_scale, dimension_scale)

        if scale != 1.0:
            resampling = getattr(Image, "Resampling", Image)
            output_width = max(1, int(width * scale))
            output_height = max(1, int(height * scale))
            image = image.resize(
                (output_width, output_height),
                resampling.LANCZOS,
            )

        return image.copy()


def _encode_preprocessed_image(
    image: Image.Image,
    *,
    image_format: str = "PNG",
) -> bytes:
    buffer = BytesIO()
    save_options: dict[str, Any] = {"format": image_format, "optimize": True}
    if image_format == "JPEG":
        # 반사 보정은 등화 처리 뒤 PNG 압축 효율이 낮다. OCR 후보 전송 지연을
        # 줄이기 위해 텍스트 가독성을 보존하는 수준으로 JPEG 압축을 사용한다.
        save_options["quality"] = 92
    image.save(buffer, **save_options)
    return buffer.getvalue()


def preprocess_image_bytes(content: bytes) -> bytes:
    """대비·선명도 보정을 적용한 기본 OCR 후보를 만든다."""

    try:
        image = _prepare_image_for_ocr(content)
        image = ImageOps.autocontrast(image.convert("L"))
        image = image.filter(
            ImageFilter.UnsharpMask(radius=1.4, percent=150, threshold=3)
        )
        return _encode_preprocessed_image(image)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageTooLargeError(
            "OCR 전처리 범위를 넘는 고해상도 이미지입니다."
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError("OCR 전처리 중 이미지 디코딩에 실패했습니다.") from exc
    except MemoryError as exc:
        raise ImageTooLargeError(
            "OCR 전처리 중 이미지가 너무 커서 메모리가 부족합니다."
        ) from exc


def preprocess_reflection_image_bytes(content: bytes) -> bytes:
    """강한 반사로 밝게 뜬 라벨을 위한 하이라이트 압축 OCR 후보를 만든다.

    완전히 포화된 픽셀을 복구하는 처리는 아니며, 남아 있는 회색 글자 대비를
    넓히기 위한 마지막 후보이다.
    """

    try:
        image = _prepare_image_for_ocr(content).convert("L")
        highlight_lut = [
            round(255 * ((value / 255) ** 1.8)) for value in range(256)
        ]
        image = image.point(highlight_lut)
        image = ImageOps.equalize(ImageOps.autocontrast(image, cutoff=1))
        image = ImageEnhance.Contrast(image).enhance(1.35)
        image = image.filter(
            ImageFilter.UnsharpMask(radius=1.8, percent=180, threshold=2)
        )
        return _encode_preprocessed_image(image, image_format="JPEG")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageTooLargeError(
            "OCR 전처리 범위를 넘는 고해상도 이미지입니다."
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError(
            "반사 보정 OCR 전처리 중 이미지 디코딩에 실패했습니다."
        ) from exc
    except MemoryError as exc:
        raise ImageTooLargeError(
            "반사 보정 OCR 전처리 중 이미지가 너무 커서 메모리가 부족합니다."
        ) from exc
