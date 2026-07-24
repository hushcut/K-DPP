from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from apps.text.ocr_text import (
    OcrMetadata,
    OcrResult,
    read_image_bytes,
    run_ocr_bytes,
)
from apps.text.parse_label import parse_label

API_VERSION = "1.0"


def _merge_ocr_metadata(parsed: dict[str, Any], metadata: OcrMetadata) -> dict[str, Any]:
    result = {
        "api_version": API_VERSION,
        **parsed,
    }
    confidence = dict(result.get("confidence", {}))
    confidence["ocr"] = metadata.confidence
    result["confidence"] = confidence

    warnings = list(result.get("warnings", []))
    for warning in metadata.warnings:
        if warning not in warnings:
            warnings.append(warning)
    result["warnings"] = warnings
    result["ocr"] = {
        "source": metadata.source,
        "candidate_count": metadata.candidate_count,
        "image_format": metadata.image_format,
        "width": metadata.width,
        "height": metadata.height,
    }
    return result


def analyze_ocr_result(ocr_result: OcrResult) -> dict[str, Any]:
    return _merge_ocr_metadata(
        parse_label(ocr_result.text),
        ocr_result.metadata,
    )


def analyze_label_image_bytes(
    content: bytes,
    *,
    credential_path: str | None = None,
    declared_content_type: str | None = None,
) -> dict[str, Any]:
    ocr_result = run_ocr_bytes(
        content,
        credential_path=credential_path,
        declared_content_type=declared_content_type,
    )
    return analyze_ocr_result(ocr_result)


def analyze_label_image(
    image_path: str | os.PathLike[str],
    *,
    credential_path: str | None = None,
) -> dict[str, Any]:
    return analyze_label_image_bytes(
        read_image_bytes(Path(image_path)),
        credential_path=credential_path,
    )


def analyze_label_text(text: str) -> dict[str, Any]:
    """Parse already-extracted OCR text without claiming OCR confidence."""

    return {
        "api_version": API_VERSION,
        **parse_label(text),
    }
