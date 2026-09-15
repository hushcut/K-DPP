"""이미지 검증, Google Vision OCR, 후보 선택을 담당하는 OCR 경계.

원본 OCR을 우선 사용하고, 파서 신뢰도가 낮을 때만 전처리 후보를 추가로
요청한다. 비용과 지연을 제한하면서 흐림·작은 글자 라벨의 인식률을 보완한다.
"""

from __future__ import annotations

import math
import os
import re
import time
import warnings
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError

from apps.text.ocr_cache import OcrCacheMissError, OcrTextCache

LANGUAGE_HINTS = ["ko", "en", "ja", "zh-Hans", "zh-Hant"]
MIN_OCR_WIDTH = 1800
MAX_OCR_WIDTH = 3200
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_ASPECT_RATIO = 20.0
MAX_PREPROCESSED_PIXELS = 16_000_000
MAX_PREPROCESSED_DIMENSION = 8192
SUPPORTED_IMAGE_FORMATS = {"JPEG", "PNG", "MPO"}
OCR_TIMEOUT_SECONDS = 20

# Keep Pillow's own decompression-bomb protection aligned with the API limit.
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class OcrError(RuntimeError):
    """Base exception for errors raised by the OCR boundary."""


class InvalidImageError(OcrError):
    """The uploaded bytes do not contain a supported, safe image."""


class ImageTooLargeError(InvalidImageError):
    """The uploaded image exceeds the byte or pixel limit."""


class UnsupportedImageError(InvalidImageError):
    """The uploaded image format is not supported."""


class OcrConfigurationError(OcrError):
    """Google Vision credentials are missing or invalid."""


class OcrServiceError(OcrError):
    """Google Vision could not complete the OCR request."""

    def __init__(self, message: str, *, retry_count: int = 0) -> None:
        super().__init__(message)
        self.retry_count = retry_count


class OcrQuotaExceededError(OcrServiceError):
    """Google Vision rejected the request because its quota was exhausted."""


class OcrTimeoutError(OcrServiceError):
    """Google Vision did not complete the request before the deadline."""


class OcrUnavailableError(OcrServiceError):
    """Google Vision is temporarily unavailable after retries."""


@dataclass(frozen=True)
class OcrMetadata:
    source: str
    confidence: str
    candidate_count: int
    image_format: str
    width: int
    height: int
    warnings: tuple[str, ...] = ()
    attempt_failures: tuple[str, ...] = ()
    attempt_count: int = 0
    external_call_count: int = 0
    retry_count: int = 0
    elapsed_ms: int = 0
    attempts: tuple["OcrAttempt", ...] = ()


@dataclass(frozen=True)
class OcrAttempt:
    """One OCR candidate attempt without provider message or credential details."""

    source: str
    outcome: str
    elapsed_ms: int
    external_call: bool
    failure_code: str = ""
    retry_count: int = 0


@dataclass(frozen=True)
class OcrResult:
    text: str
    metadata: OcrMetadata


@dataclass(frozen=True)
class OcrPayload:
    """Raw OCR text plus a text order reconstructed from word coordinates."""

    text: str
    layout_text: str = ""
    retry_count: int = 0


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


@dataclass(frozen=True)
class OcrCandidate:
    source: str
    text: str
    materials: dict[str, float | int]
    selected_part: str
    parser_status: str
    parser_confidence: str
    score: tuple[int, int, int, int, float, int, int, int]
    layout_used: bool = False


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


def _parse_candidate(text: str) -> dict:
    from apps.text.parse_label import parse_label

    return parse_label(text)


def _score_candidate(
    text: str,
    materials: dict[str, float | int],
    selected_part: str,
    parser_status: str,
    parser_confidence: str,
    source: str,
    *,
    ratio_total_before_normalization: float | None,
    warning_count: int,
) -> tuple[int, int, int, int, float, int, int, int]:
    """파서 성공 여부를 최우선으로 OCR 후보를 정렬할 점수를 만든다.

    같은 품질이면 서비스의 소재 선택 원칙(겉감 우선), 소재 조성의 완전성,
    혼용률 합계·경고·명시적 퍼센트·원본 OCR 순서로 선택한다.
    """

    total = (
        ratio_total_before_normalization
        if ratio_total_before_normalization is not None
        else sum(float(value) for value in materials.values())
        if materials
        else 0.0
    )
    confidence_rank = {"low": 0, "medium": 1, "high": 2}.get(parser_confidence, 0)
    part_rank = {
        "outer": 7,
        "generic": 6,
        "lining": 5,
        "filling": 4,
        "pocket": 3,
        "rib": 2,
        "sleeve": 1,
        "color_block": 0,
    }.get(selected_part, 0)
    explicit_percent_count = len(re.findall(r"\d{1,3}(?:\.\d+)?\s*[%％]", text))
    source_priority = 1 if source == "original" else 0

    return (
        1 if parser_status == "success" else 0,
        part_rank,
        len(materials),
        confidence_rank,
        -abs(100.0 - total) if materials else -100.0,
        -warning_count,
        min(explicit_percent_count, 4),
        source_priority,
    )


def _build_candidate(
    source: str,
    text: str,
    *,
    layout_used: bool = False,
) -> OcrCandidate:
    parsed = _parse_candidate(text)
    materials = parsed.get("materials", {})
    selected_part = parsed.get("selected_part", "")
    parser_status = parsed.get("status", "failed")
    parser_confidence = parsed.get("confidence", {}).get("parser", "low")
    ratio_total = parsed.get("parse_evidence", {}).get(
        "ratio_total_before_normalization"
    )
    parser_warnings = parsed.get("warnings", [])
    return OcrCandidate(
        source=source,
        text=text,
        materials=materials,
        selected_part=selected_part,
        parser_status=parser_status,
        parser_confidence=parser_confidence,
        score=_score_candidate(
            text,
            materials,
            selected_part,
            parser_status,
            parser_confidence,
            source,
            ratio_total_before_normalization=ratio_total,
            warning_count=len(parser_warnings),
        ),
        layout_used=layout_used,
    )


def _extract_response_text(response: Any) -> str:
    error = getattr(response, "error", None)
    error_message = getattr(error, "message", "")
    if error_message:
        error_code = getattr(error, "code", None)
        if error_code in {7, 16}:  # PERMISSION_DENIED, UNAUTHENTICATED
            raise OcrConfigurationError(
                "Google Vision 인증 권한 또는 결제 설정을 확인해 주세요."
            )
        if error_code == 8:  # RESOURCE_EXHAUSTED
            raise OcrQuotaExceededError(
                "Google Vision OCR 사용량 한도를 초과했습니다."
            )
        if error_code == 4:  # DEADLINE_EXCEEDED
            raise OcrTimeoutError("Google Vision OCR 요청 시간이 초과되었습니다.")
        if error_code in {13, 14}:  # INTERNAL, UNAVAILABLE
            raise OcrUnavailableError(
                "Google Vision OCR 서비스를 일시적으로 사용할 수 없습니다."
            )
        raise OcrServiceError(error_message)

    if response.full_text_annotation and response.full_text_annotation.text:
        return response.full_text_annotation.text

    texts = response.text_annotations
    return texts[0].description if texts else ""


def _spatial_text_from_words(words: list[OcrWord]) -> str:
    """Reassemble OCR words into visual rows, ordered left to right.

    Vision's plain text is paragraph-order based. On care labels with a
    material column and a ratio column, that order can separate a material
    from its percentage. Grouping by overlapping vertical positions restores
    the row used by the printed label.
    """

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


def _extract_response_layout_text(response: Any) -> str:
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
                        (int(getattr(vertex, "x", 0) or 0), int(getattr(vertex, "y", 0) or 0))
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
    return _spatial_text_from_words(words)


def _resolve_credential_path(
    credential_path: str | None,
) -> tuple[str | None, int | None]:
    value = credential_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not value:
        return None, None

    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise OcrConfigurationError(f"Google Vision 서비스 계정 키를 찾을 수 없습니다: {path}")
    return str(path), path.stat().st_mtime_ns


@lru_cache(maxsize=4)
def _get_vision_client(
    resolved_credential_path: str | None,
    credential_modified_time_ns: int | None,
):
    del credential_modified_time_ns
    try:
        from google.cloud import vision
        from google.oauth2 import service_account
    except ImportError as exc:
        raise OcrConfigurationError(
            "google-cloud-vision 패키지가 설치되어 있지 않습니다."
        ) from exc

    try:
        if resolved_credential_path:
            credentials = service_account.Credentials.from_service_account_file(
                resolved_credential_path
            )
            return vision.ImageAnnotatorClient(credentials=credentials)
        return vision.ImageAnnotatorClient()
    except Exception as exc:
        raise OcrConfigurationError("Google Vision 인증 정보를 불러오지 못했습니다.") from exc


def _run_google_ocr(client: Any, content: bytes) -> OcrPayload:
    from google.api_core import exceptions as google_exceptions
    from google.api_core import retry as google_retry
    from google.cloud import vision

    image = vision.Image(content=content)
    image_context = vision.ImageContext(language_hints=LANGUAGE_HINTS)
    retry_count = 0

    def record_retry(_exc: Exception) -> None:
        nonlocal retry_count
        retry_count += 1

    retry = google_retry.Retry(
        predicate=google_retry.if_exception_type(
            google_exceptions.ServiceUnavailable,
            google_exceptions.DeadlineExceeded,
            google_exceptions.InternalServerError,
        ),
        initial=0.5,
        maximum=2.0,
        multiplier=2.0,
        deadline=OCR_TIMEOUT_SECONDS,
        on_error=record_retry,
    )

    try:
        response = client.document_text_detection(
            image=image,
            image_context=image_context,
            retry=retry,
            timeout=OCR_TIMEOUT_SECONDS,
        )
        return OcrPayload(
            text=_extract_response_text(response).strip(),
            layout_text=_extract_response_layout_text(response).strip(),
            retry_count=retry_count,
        )
    except OcrServiceError:
        raise
    except OcrConfigurationError:
        raise
    except (google_exceptions.GoogleAPIError, TimeoutError) as exc:
        cause = getattr(exc, "cause", None) or exc
        if isinstance(
            cause,
            (google_exceptions.Unauthorized, google_exceptions.Forbidden),
        ):
            raise OcrConfigurationError(
                "Google Vision 인증 권한 또는 결제 설정을 확인해 주세요."
            ) from exc
        if isinstance(cause, google_exceptions.TooManyRequests):
            raise OcrQuotaExceededError(
                "Google Vision OCR 사용량 한도를 초과했습니다.",
                retry_count=retry_count,
            ) from exc
        if isinstance(cause, (google_exceptions.DeadlineExceeded, TimeoutError)):
            raise OcrTimeoutError(
                "Google Vision OCR 요청 시간이 초과되었습니다.",
                retry_count=retry_count,
            ) from exc
        if isinstance(
            cause,
            (
                google_exceptions.ServiceUnavailable,
                google_exceptions.InternalServerError,
            ),
        ):
            raise OcrUnavailableError(
                "Google Vision OCR 서비스를 일시적으로 사용할 수 없습니다.",
                retry_count=retry_count,
            ) from exc
        raise OcrServiceError(
            "Google Vision OCR 요청에 실패했습니다.",
            retry_count=retry_count,
        ) from exc


def _coerce_ocr_payload(value: OcrPayload | str) -> OcrPayload:
    """Keep test doubles and older callers that return plain text compatible."""

    if isinstance(value, OcrPayload):
        return value
    if isinstance(value, str):
        return OcrPayload(text=value)
    raise TypeError("OCR 결과는 텍스트 또는 OcrPayload여야 합니다.")


def _build_payload_candidates(
    source: str,
    payload: OcrPayload,
) -> list[OcrCandidate]:
    candidates = [_build_candidate(source, payload.text)]
    if payload.layout_text and payload.layout_text != payload.text:
        candidates.append(
            _build_candidate(source, payload.layout_text, layout_used=True)
        )
    return candidates


def _attempt_failure_code(exc: Exception) -> str:
    """Return a stable, non-sensitive code for QA diagnostics."""

    if isinstance(exc, OcrQuotaExceededError):
        return "quota_exceeded"
    if isinstance(exc, OcrTimeoutError):
        return "timeout"
    if isinstance(exc, OcrUnavailableError):
        return "service_unavailable"
    if isinstance(exc, OcrCacheMissError):
        return "cache_miss"
    if isinstance(exc, ImageTooLargeError):
        return "image_too_large"
    if isinstance(exc, InvalidImageError):
        return "invalid_image"
    if isinstance(exc, OcrServiceError):
        return "service_error"
    if isinstance(exc, MemoryError):
        return "memory_error"
    return "unknown"


def run_ocr_bytes(
    content: bytes,
    credential_path: str | None = None,
    *,
    declared_content_type: str | None = None,
    ocr_cache: OcrTextCache | None = None,
    refresh_ocr_cache: bool = False,
    offline: bool = False,
    cache_label: str = "",
) -> OcrResult:
    """한 이미지에서 원본/전처리 OCR 후보 중 파서 관점의 최선 결과를 반환한다."""

    started_at = time.monotonic()
    validated = validate_image_bytes(
        content,
        declared_content_type=declared_content_type,
    )
    if offline and ocr_cache is None:
        raise OcrCacheMissError("오프라인 OCR 실행에는 캐시 파일이 필요합니다.")

    client: Any | None = None
    external_call_count = 0
    attempts: list[OcrAttempt] = []

    def run_candidate_ocr(source: str, candidate_content: bytes) -> OcrPayload:
        nonlocal client, external_call_count
        # QA 재실행에서 동일 이미지에 대한 외부 OCR 호출과 비용을 피한다.
        if ocr_cache is not None and not refresh_ocr_cache:
            cached_entry = ocr_cache.get_entry(candidate_content)
            if cached_entry is not None:
                return OcrPayload(
                    text=cached_entry["text"],
                    layout_text=str(cached_entry.get("layout_text", "")),
                )

        if offline:
            raise OcrCacheMissError(
                f"오프라인 OCR 캐시에 {source} 후보가 없습니다: {cache_label}"
            )

        if client is None:
            client = _get_vision_client(
                *_resolve_credential_path(credential_path)
            )
        external_call_count += 1
        payload = _coerce_ocr_payload(_run_google_ocr(client, candidate_content))
        if ocr_cache is not None:
            ocr_cache.put(
                candidate_content,
                payload.text,
                file_name=cache_label,
                source=source,
                layout_text=payload.layout_text,
            )
        return payload

    def run_tracked_candidate(source: str, candidate_content: bytes) -> OcrPayload:
        """Measure each candidate without exposing provider exception messages."""

        external_calls_before = external_call_count
        attempt_started_at = time.monotonic()
        try:
            payload = run_candidate_ocr(source, candidate_content)
        except (
            InvalidImageError,
            OcrCacheMissError,
            OcrServiceError,
            MemoryError,
        ) as exc:
            attempts.append(
                OcrAttempt(
                    source=source,
                    outcome="failed",
                    elapsed_ms=round((time.monotonic() - attempt_started_at) * 1000),
                    external_call=external_call_count > external_calls_before,
                    failure_code=_attempt_failure_code(exc),
                    retry_count=getattr(exc, "retry_count", 0),
                )
            )
            raise
        else:
            attempts.append(
                OcrAttempt(
                    source=source,
                    outcome="success",
                    elapsed_ms=round((time.monotonic() - attempt_started_at) * 1000),
                    external_call=external_call_count > external_calls_before,
                    retry_count=payload.retry_count,
                )
            )
            return payload

    candidates = _build_payload_candidates(
        "original",
        run_tracked_candidate("original", validated.content),
    )
    ocr_candidate_count = 1
    processing_warnings: list[str] = []
    attempt_failures: list[str] = []

    # 원본 파싱이 충분히 신뢰할 만할 때는 전처리 OCR 호출을 생략한다.
    # 어려운 사진만 재시도해 비용과 지연을 제한한다.
    original = max(candidates, key=lambda candidate: candidate.score)
    if original.parser_status != "success" or original.parser_confidence != "high":
        try:
            preprocessed = preprocess_image_bytes(validated.content)
            candidates.extend(
                _build_payload_candidates(
                    "preprocessed",
                    run_tracked_candidate("preprocessed", preprocessed),
                )
            )
            ocr_candidate_count += 1
        except (
            InvalidImageError,
            OcrCacheMissError,
            OcrServiceError,
            MemoryError,
        ) as exc:
            attempt_failures.append(f"preprocessed:{type(exc).__name__}")
            processing_warnings.append(
                "전처리 OCR에 실패하여 원본 OCR 결과를 유지했습니다."
            )
        else:
            # 기본 전처리까지 조성을 만들지 못한 경우에만 반사 보정 후보를
            # 추가한다. 성공한 후보가 있으면 불필요한 Vision 호출을 하지 않는다.
            if not any(
                candidate.parser_status == "success" for candidate in candidates
            ):
                try:
                    reflection = preprocess_reflection_image_bytes(validated.content)
                    candidates.extend(
                        _build_payload_candidates(
                            "reflection",
                            run_tracked_candidate("reflection", reflection),
                        )
                    )
                    ocr_candidate_count += 1
                except (
                    InvalidImageError,
                    OcrCacheMissError,
                    OcrServiceError,
                    MemoryError,
                ) as exc:
                    attempt_failures.append(f"reflection:{type(exc).__name__}")
                    processing_warnings.append(
                        "반사 보정 OCR에 실패하여 기존 후보를 유지했습니다."
                    )

    best = max(candidates, key=lambda candidate: candidate.score)
    ocr_confidence = (
        "high"
        if best.parser_status == "success" and best.parser_confidence == "high"
        else "medium"
        if best.text
        else "low"
    )
    result_warnings = processing_warnings
    if best.source != "original":
        if best.source == "reflection":
            result_warnings.append("반사 보정된 이미지의 OCR 결과를 사용했습니다.")
        else:
            result_warnings.append("전처리된 이미지의 OCR 결과를 사용했습니다.")
    if best.layout_used:
        result_warnings.append("OCR 좌표를 바탕으로 재구성한 줄 순서를 사용했습니다.")
    if not best.text:
        result_warnings.append("OCR에서 텍스트를 추출하지 못했습니다.")

    return OcrResult(
        text=best.text,
        metadata=OcrMetadata(
            source=best.source,
            confidence=ocr_confidence,
            candidate_count=ocr_candidate_count,
            image_format=validated.image_format,
            width=validated.width,
            height=validated.height,
            warnings=tuple(result_warnings),
            attempt_failures=tuple(attempt_failures),
            attempt_count=len(attempts),
            external_call_count=external_call_count,
            retry_count=sum(attempt.retry_count for attempt in attempts),
            elapsed_ms=round((time.monotonic() - started_at) * 1000),
            attempts=tuple(attempts),
        ),
    )


def run_ocr_with_metadata(
    image_path: str | os.PathLike[str],
    credential_path: str | None = None,
) -> OcrResult:
    return run_ocr_bytes(
        read_image_bytes(image_path),
        credential_path=credential_path,
    )


def run_ocr(
    image_path: str | os.PathLike[str],
    credential_path: str | None = None,
) -> str:
    """Compatibility wrapper for existing batch scripts."""

    return run_ocr_with_metadata(image_path, credential_path).text
