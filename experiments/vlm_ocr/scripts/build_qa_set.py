"""QA 정답지 사진의 목록·대표 조성 정답·Vision 원본 캐시 텍스트를 evaluate_batch 형식으로 만든다.

Vision 캐시 키가 서비스의 이미지 정규화(EXIF 회전·재저장) 결과 해시이므로 서비스 가상환경에서 실행한다.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import sys


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-dir", required=True, type=Path)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--answer-key", required=True, type=Path)
    parser.add_argument("--vision-cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("기존 결과를 덮어쓰지 않습니다.")
    def blocked(*a, **kw):
        raise RuntimeError("평가 자료 생성에서 네트워크를 차단했습니다.")
    socket.socket.connect = blocked
    socket.create_connection = blocked
    sys.path.insert(0, str(args.service_dir))
    from apps.text.ocr_image import validate_image_bytes
    from apps.text.qa_dataset import load_qa_answer_key
    if "apps.text.ocr_text" in sys.modules:
        raise RuntimeError("Vision 호출 모듈이 import됐습니다.")
    answers = load_qa_answer_key(args.answer_key)
    entries = json.loads(args.vision_cache.read_text(encoding="utf-8"))["entries"]
    vision_dir = args.output / "vision_original"
    vision_dir.mkdir(parents=True)
    manifest, graded, core = [], [], {}
    for file_name in sorted(answers):
        answer = answers[file_name]
        pid = Path(file_name).stem
        raw = (args.images / file_name).read_bytes()
        digest = sha256(raw)
        key = sha256(validate_image_bytes(raw).content)
        entry = entries.get(key)
        if not entry or entry.get("file_name") != file_name or entry.get("source") != "original":
            raise RuntimeError(f"{pid}: Vision 원본 후보 캐시를 찾지 못했습니다.")
        manifest.append({"id": pid, "source": file_name, "sha256": digest})
        graded.append({"image_id": pid, "file_name": file_name, "sha256": digest, "answer": answer.materials,
                       "answer_part": "", "included": answer.include_in_accuracy,
                       "source_group": answer.source_group or pid, "capture_condition": answer.capture_condition})
        core[pid] = []
        out = vision_dir / pid
        out.mkdir()
        dump(out / "result.json", {"id": pid, "source_name": file_name, "source_sha256": digest,
                                   "vision_cache_key": key, "status": "success", "truncated": False,
                                   "inference_seconds": None, "peak_rss_mb": None})
        (out / "text.txt").write_text(entry["text"] + "\n", encoding="utf-8")
    dump(args.output / "manifest.json", manifest)
    dump(args.output / "graded.json", graded)
    dump(args.output / "core_truth.json", {
        "criterion": "QA 사진은 핵심 문구 기준을 만들지 않았다. 대표 조성만 평가한다.",
        "core_tokens": core,
        "limitations": [
            "QA 정답지는 대표 조성만 있고 부위 정답이 없어 부위 일치는 평가하지 않는다.",
            "핵심 문구 기준이 없어 core 지표는 모두 uncertain이다.",
            "같은 옷을 촬영 조건만 바꿔 여러 번 찍었을 수 있어 사진들을 독립 표본으로 보지 않는다.",
            "Vision은 저장 캐시의 원본 후보 text만 사용했다. 새 Vision 호출은 없다.",
            "Vision은 EXIF 회전 후 원본 해상도로 다시 저장한 이미지를 읽었다. VLM 입력 해상도는 실행 설정을 따른다.",
            "이 PC의 CPU 처리 시간은 참고치다.",
        ],
    })
    dump(args.output / "build_info.json", {
        "created_at": datetime.now().astimezone().isoformat(),
        "service_dir": str(args.service_dir), "images": str(args.images),
        "answer_key": str(args.answer_key), "answer_key_sha256": sha256(args.answer_key.read_bytes()),
        "vision_cache": str(args.vision_cache), "vision_cache_sha256": sha256(args.vision_cache.read_bytes()),
        "photos": len(manifest), "vision_api_calls": 0,
    })
    print(json.dumps({"output": str(args.output), "photos": len(manifest)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
