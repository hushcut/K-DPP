"""공식 모델 스냅샷을 고정된 revision으로 내려받아 로컬 추론에 사용한다."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

from huggingface_hub import HfApi, snapshot_download

ROOT = Path(__file__).resolve().parents[1]
REPOS = {"glm": "zai-org/GLM-OCR", "paddle_vl": "PaddlePaddle/PaddleOCR-VL-1.6"}


def main():
    manifest_file = ROOT / "models" / "manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.exists() else {}
    api = HfApi(token=False)
    for name, repo in REPOS.items():
        if name in manifest:
            print(json.dumps({"model": name, "phase": "already_downloaded", "revision": manifest[name]["revision"]}), flush=True)
            continue
        info = api.model_info(repo)
        if not info.sha:
            raise RuntimeError("모델 revision 확인 실패")
        target = ROOT / "models" / name
        print(json.dumps({"model": name, "phase": "download", "revision": info.sha}), flush=True)
        snapshot_download(
            repo_id=repo, revision=info.sha, token=False, local_dir=str(target),
            allow_patterns=["*.safetensors", "*.json", "*.model", "*.txt", "*.jinja", "*.tiktoken",
                            "*.vocab", "merges.*", "vocab.*", "LICENSE*", "NOTICE*"],
            max_workers=4,
        )
        weights = list(target.glob("*.safetensors"))
        if not weights:
            raise RuntimeError("가중치 파일이 없습니다")
        manifest[name] = {
            "model_id": repo, "revision": info.sha, "local_dir": str(target),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "weight_bytes": sum(path.stat().st_size for path in weights),
        }
        manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"model": name, "phase": "downloaded", "weight_bytes": manifest[name]["weight_bytes"]}), flush=True)


if __name__ == "__main__":
    main()

