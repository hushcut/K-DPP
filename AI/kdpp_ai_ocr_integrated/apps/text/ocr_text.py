import os
import re
from dataclasses import dataclass
from io import BytesIO

try:
    from PIL import Image, ImageFilter, ImageOps
except ImportError:  # pragma: no cover - preprocessing is optional.
    Image = None
    ImageFilter = None
    ImageOps = None

LANGUAGE_HINTS = ["ko", "en", "ja", "zh-Hans", "zh-Hant"]
MIN_OCR_WIDTH = 1800
MAX_OCR_WIDTH = 3200


@dataclass
class OcrCandidate:
    source: str
    text: str
    materials: dict[str, float | int]
    score: tuple[int, float, int, int, int, int, int]


def read_image_bytes(image_path: str) -> bytes:
    with open(image_path, "rb") as image_file:
        return image_file.read()


def preprocess_image_bytes(image_path: str) -> bytes | None:
    if Image is None or ImageOps is None or ImageFilter is None:
        return None

    try:
        with Image.open(image_path) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")

            width, height = image.size
            if width <= 0 or height <= 0:
                return None

            scale = 1.0
            if width < MIN_OCR_WIDTH:
                scale = MIN_OCR_WIDTH / width
            elif width > MAX_OCR_WIDTH:
                scale = MAX_OCR_WIDTH / width

            if scale != 1.0:
                new_size = (int(width * scale), int(height * scale))
                resampling = getattr(Image, "Resampling", Image)
                image = image.resize(new_size, resampling.LANCZOS)

            image = image.convert("L")
            image = ImageOps.autocontrast(image)
            image = image.filter(ImageFilter.SHARPEN)

            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=95)
            return buffer.getvalue()
    except Exception:
        return None


def extract_response_text(response) -> str:
    if response.error.message:
        raise RuntimeError(response.error.message)

    if response.full_text_annotation and response.full_text_annotation.text:
        return response.full_text_annotation.text

    texts = response.text_annotations
    return texts[0].description if texts else ""


def parse_ocr_materials(text: str) -> dict[str, float | int]:
    try:
        from apps.text.parse_label import parse_materials

        return parse_materials(text)
    except Exception:
        return {}


def score_ocr_candidate(
    text: str,
    materials: dict[str, float | int],
    source: str,
) -> tuple[int, float, int, int, int, int, int]:
    if not text:
        return (0, -100.0, 0, 0, 0, 0, 0)

    total = sum(float(value) for value in materials.values()) if materials else 0.0
    valid_total = 1 if materials and 95 <= total <= 105 else 0
    total_closeness = -abs(100.0 - total) if materials else -100.0
    source_priority = 1 if source == "original" else 0
    explicit_percent_count = len(re.findall(r"\d{1,3}(?:\.\d+)?\s*[%％]", text))
    percent_count = len(re.findall(r"\d{1,3}(?:\.\d+)?\s*%?", text))

    return (
        valid_total,
        total_closeness,
        source_priority,
        len(materials),
        explicit_percent_count,
        percent_count,
        len(text),
    )


def score_ocr_text(text: str, source: str = "original") -> tuple[int, float, int, int, int, int, int]:
    return score_ocr_candidate(text, parse_ocr_materials(text), source)


def build_candidate(source: str, text: str) -> OcrCandidate:
    materials = parse_ocr_materials(text)
    return OcrCandidate(
        source=source,
        text=text,
        materials=materials,
        score=score_ocr_candidate(text, materials, source),
    )


def choose_best_candidate(candidates: list[OcrCandidate]) -> OcrCandidate | None:
    if not candidates:
        return None

    return max(candidates, key=lambda candidate: candidate.score)


def run_google_ocr(client, vision_module, content: bytes) -> str:
    image = vision_module.Image(content=content)
    image_context = vision_module.ImageContext(language_hints=LANGUAGE_HINTS)
    response = client.document_text_detection(
        image=image,
        image_context=image_context,
    )
    return extract_response_text(response)


def run_ocr(image_path: str, credential_path: str = "key.json") -> str:
    if credential_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credential_path

    from google.cloud import vision

    client = vision.ImageAnnotatorClient()

    original_content = read_image_bytes(image_path)
    candidates = [
        build_candidate("original", run_google_ocr(client, vision, original_content)),
    ]

    preprocessed_content = preprocess_image_bytes(image_path)
    if preprocessed_content:
        candidates.append(
            build_candidate("preprocessed", run_google_ocr(client, vision, preprocessed_content))
        )

    best_candidate = choose_best_candidate(candidates)
    return best_candidate.text if best_candidate else ""

