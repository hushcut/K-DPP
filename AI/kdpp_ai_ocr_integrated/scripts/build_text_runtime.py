"""텍스트 OCR 운영에 필요한 파일만 런타임 번들로 복사한다."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "runtime-manifest.json"
RUNTIME_FILES = (
    "requirements.txt",
    "apps/__init__.py",
    "apps/service/__init__.py",
    "apps/service/__main__.py",
    "apps/service/label_analysis.py",
    "apps/service/main.py",
    "apps/service/response_contract.py",
    "apps/text/__init__.py",
    "apps/text/material_extraction.py",
    "apps/text/ocr_cache.py",
    "apps/text/ocr_candidates.py",
    "apps/text/ocr_errors.py",
    "apps/text/ocr_image.py",
    "apps/text/ocr_layout.py",
    "apps/text/ocr_text.py",
    "apps/text/parse_label.py",
    "apps/text/rules.py",
)


class RuntimeBundleError(RuntimeError):
    """런타임 번들을 안전하게 만들 수 없을 때 발생한다."""


def build_runtime_bundle(output_dir: str | Path) -> Path:
    """명시된 텍스트 서비스 파일을 빈 출력 디렉터리에 복사한다."""

    output_path = Path(output_dir).expanduser().resolve()
    if output_path.exists() and any(output_path.iterdir()):
        raise RuntimeBundleError(f"출력 디렉터리가 비어 있지 않습니다: {output_path}")

    missing = [relative for relative in RUNTIME_FILES if not (BASE_DIR / relative).is_file()]
    if missing:
        raise RuntimeBundleError(f"런타임 파일이 없습니다: {', '.join(missing)}")

    output_path.mkdir(parents=True, exist_ok=True)
    for relative in RUNTIME_FILES:
        source = BASE_DIR / relative
        destination = output_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    manifest = {
        "bundle": "kdpp-ai-text-runtime",
        "entrypoint": "python -m apps.service",
        "files": list(RUNTIME_FILES),
    }
    manifest_path = output_path / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a text-only K-DPP AI runtime bundle.",
    )
    parser.add_argument(
        "--output",
        default=str(BASE_DIR / "dist" / "text-runtime"),
        help="Empty output directory for the runtime bundle.",
    )
    args = parser.parse_args()

    manifest_path = build_runtime_bundle(args.output)
    print(f"Runtime bundle: {manifest_path.parent}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
