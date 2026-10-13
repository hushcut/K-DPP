"""Separate final OCR outcomes from service, cache and budget events."""

from __future__ import annotations

from typing import Any


_ALIASES = {
    "OcrUnavailableError": "ocr_service_unavailable",
    "OcrServiceError": "ocr_service_failed",
    "OcrTimeoutError": "ocr_timeout",
    "OcrTotalTimeoutError": "ocr_total_timeout",
    "OcrQuotaExceededError": "ocr_quota_exceeded",
    "OcrConfigurationError": "ocr_not_configured",
    "OcrCacheMissError": "ocr_cache_miss",
    "OcrCompositionError": "composition_not_found",
    "InvalidImageError": "invalid_image",
    "ImageTooLargeError": "payload_too_large",
    "UnsupportedImageError": "unsupported_media_type",
    "service_unavailable": "ocr_service_unavailable",
    "service_error": "ocr_service_failed",
    "timeout": "ocr_timeout",
    "quota_exceeded": "ocr_quota_exceeded",
    "cache_miss": "ocr_cache_miss",
    "total_timeout": "ocr_total_timeout",
    "image_too_large": "payload_too_large",
}
_STAGES = {
    "ocr_service_unavailable": "ocr_service",
    "ocr_service_failed": "ocr_service",
    "ocr_timeout": "ocr_service",
    "ocr_quota_exceeded": "ocr_service",
    "ocr_total_timeout": "ocr_budget",
    "ocr_not_configured": "ocr_configuration",
    "ocr_cache_miss": "cache_incomplete",
    "ocr_text_empty": "text_recognition",
    "composition_not_found": "composition",
    "ambiguous_composition": "composition",
    "incomplete_part_composition": "composition",
    "payload_too_large": "input",
    "invalid_image": "input",
    "unsupported_media_type": "input",
    "pipeline_exception": "pipeline",
    "internal_error": "pipeline",
    "memory_error": "pipeline",
}


def safe_failure_code(value: Any, *, default: str = "pipeline_exception") -> str:
    """Return only known codes; never copy an exception message or private path."""
    if not isinstance(value, str):
        return default
    code = _ALIASES.get(value, value)
    return code if code in _STAGES else default


def failure_diagnostics(result: dict[str, Any], *, exception_code: str = "") -> dict:
    """A failed candidate does not prove that the final failure was a service error."""
    code = safe_failure_code(result.get("error_code"), default="")
    if exception_code:
        code = safe_failure_code(exception_code.partition(":")[0], default="") or code or "pipeline_exception"
    observed = {code} if code else set()
    ocr = result.get("ocr", {})
    if isinstance(ocr, dict):
        attempts = ocr.get("attempts", [])
        if isinstance(attempts, (list, tuple)):
            for attempt in attempts:
                if isinstance(attempt, dict) and attempt.get("outcome") in {"failed", "skipped"}:
                    event = safe_failure_code(attempt.get("failure_code"), default="")
                    if attempt["outcome"] == "failed" or event in {"ocr_cache_miss", "ocr_total_timeout"}:
                        observed.add(event)
        failures = ocr.get("attempt_failures", [])
        if isinstance(failures, (list, tuple)):
            for failure in failures:
                if isinstance(failure, str):
                    observed.add(safe_failure_code(failure.rsplit(":", 1)[-1], default=""))
    return {
        "failure_stage": "success" if result.get("status") == "success" else _STAGES.get(code, "unknown"),
        "service_error_codes": sorted(item for item in observed if _STAGES.get(item) == "ocr_service"),
        "cache_incomplete": "ocr_cache_miss" in observed,
        "budget_exhausted": "ocr_total_timeout" in observed,
    }
