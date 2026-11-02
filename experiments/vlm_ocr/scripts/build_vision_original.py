"""사진 목록의 Vision 원본 후보 원문을 저장 캐시에서 꺼내 evaluate_batch 형식의 결과 폴더로 만든다.

Vision 캐시 키가 서비스의 이미지 정규화(EXIF 회전·재저장) 결과 해시이므로 서비스 가상환경에서 실행한다.
새 Vision 호출은 하지 않으며 네트워크를 막는다.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-dir", required=True, type=Path)
    parser.add_argument("--photos", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--vision-cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("기존 결과를 덮어쓰지 않습니다.")
    def blocked(*a, **kw):
        raise RuntimeError("캐시 변환에서 네트워크를 차단했습니다.")
    socket.socket.connect = blocked
    socket.create_connection = blocked
    sys.path.insert(0, str(args.service_dir))
    from apps.text.ocr_image import validate_image_bytes
    if "apps.text.ocr_text" in sys.modules:
        raise RuntimeError("Vision 호출 모듈이 import됐습니다.")
    entries = json.loads(args.vision_cache.read_text(encoding="utf-8"))["entries"]
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True)
    for item in manifest:
        raw = (args.photos / item["source"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise RuntimeError(f"{item['id']}: 사진 목록의 해시와 원본이 다릅니다.")
        key = hashlib.sha256(validate_image_bytes(raw).content).hexdigest()
        entry = entries.get(key)
        if not entry or entry.get("source") != "original":
            raise RuntimeError(f"{item['id']}: Vision 원본 후보 캐시를 찾지 못했습니다.")
        out = args.output / item["id"]
        out.mkdir()
        (out / "result.json").write_text(json.dumps({
            "id": item["id"], "source_name": item["source"], "source_sha256": item["sha256"],
            "vision_cache_key": key, "status": "success", "truncated": False,
            "inference_seconds": None, "peak_rss_mb": None,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "text.txt").write_text(entry["text"] + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "photos": len(manifest), "vision_api_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
