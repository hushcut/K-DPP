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
