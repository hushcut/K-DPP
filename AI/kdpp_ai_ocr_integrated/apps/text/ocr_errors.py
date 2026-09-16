"""OCR 경계에서 사용하는 공개 예외 계층."""


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


class OcrTotalTimeoutError(OcrTimeoutError):
    """The request-wide OCR time budget was exhausted before another candidate."""


class OcrUnavailableError(OcrServiceError):
    """Google Vision is temporarily unavailable after retries."""
