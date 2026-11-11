import json
import os
import subprocess
import sys

import pytest

from scripts.build_text_runtime import (
    MANIFEST_NAME,
    RUNTIME_FILES,
    RuntimeBundleError,
    build_runtime_bundle,
)


def test_text_runtime_bundle_contains_only_allowlisted_files(tmp_path) -> None:
    output_dir = tmp_path / "runtime"

    manifest_path = build_runtime_bundle(output_dir)

    bundled_files = {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    assert bundled_files == {*RUNTIME_FILES, MANIFEST_NAME}
    assert not (output_dir / "apps" / "symbol").exists()
    assert not (output_dir / "apps" / "synthetic").exists()
    assert not (output_dir / "scripts").exists()
    assert not (output_dir / "tests").exists()
    assert not (output_dir / "configs").exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["entrypoint"] == "python -m apps.service"
    assert manifest["files"] == list(RUNTIME_FILES)


def test_text_runtime_bundle_imports_without_repository_source(tmp_path) -> None:
    output_dir = tmp_path / "runtime"
    build_runtime_bundle(output_dir)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(output_dir)
    environment["KDPP_ENABLE_SYMBOL_API"] = "1"

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from apps.service.main import app; "
                "from apps.text.care_cell_geometry import vertical_care_cell; "
                "from apps.text.composition_region_recovery import recover_composition_region; "
                "from apps.text.main_material_recovery import recover_main_material_layout; "
                "from apps.text.multilingual_layout_recovery import recover_multilingual_outer_layout; "
                "from apps.text.ocr_row_search import physical_row_options; "
                "from apps.text.single_row_metadata_recovery import recover_fit_origin_layout; "
                "from apps.text.parse_label import parse_label; "
                "parsed = parse_label('MAIN MATERIAL: 100% POLYESTER (100% RECYCLED)'); "
                "assert parsed['status'] == 'success'; "
                "assert parsed['selected_part'] == 'outer'; "
                "assert parsed['materials'] == {'polyester': 100}; "
                "from apps.text.ocr_text import OcrPayload, _build_payload_candidates, _assess_candidates; "
                "from apps.text.ocr_layout import OcrWord; "
                "words = (OcrWord('COTTON', 10, 10, 110, 30, ((10,10),(110,10),(110,30),(10,30)), 0), "
                "OcrWord('100%', 150, 10, 190, 30, ((150,10),(190,10),(190,30),(150,30)), 0)); "
                "payload = OcrPayload('COTTON 100%', layout_text='COTTON  100%', layout_words=words); "
                "candidates = _build_payload_candidates('original', payload, image_key='one-photo', "
                "image_variant_key='one-response', image_transform=(1,0,0,0,1,0), image_region=(0,0,300,100)); "
                "assert _assess_candidates(candidates).status == 'success'; "
                "paths = app.openapi()['paths']; "
                "assert set(paths) == {'/health', '/v1/parse-text', '/v1/analyze-label'}; "
                "import sys; "
                "assert not any(name.split('.')[0] in {'torch', 'torchvision'} "
                "for name in sys.modules)"
            ),
        ],
        cwd=output_dir,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert completed.returncode == 0, completed.stderr


def test_text_runtime_bundle_does_not_overwrite_nonempty_directory(tmp_path) -> None:
    output_dir = tmp_path / "runtime"
    output_dir.mkdir()
    marker = output_dir / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(RuntimeBundleError, match="비어 있지 않습니다"):
        build_runtime_bundle(output_dir)

    assert marker.read_text(encoding="utf-8") == "keep"
