"""저장된 OCR 출력을 더 낮은 출력 토큰 상한에서 끊은 것으로 보고 같은 서비스 파서로 다시 평가한다. 모델은 다시 돌리지 않는다.

탐욕 생성은 상한과 무관하게 앞부분이 같으므로, 저장 출력의 앞 N토큰을 상한 N 실행의 출력으로 본다.
처리 시간은 모델별 토큰당 시간(설정별 절편을 둔 회귀)으로 줄어든 토큰만큼 뺀 추정치다.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import sys

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_batch import evaluate, load_result, read  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def per_token_seconds(samples):
    """설정별 평균을 뺀 (생성 토큰, 시간)을 묶어 토큰당 시간을 구한다."""
    centered = []
    for pairs in samples:
        mx = sum(x for x, _ in pairs) / len(pairs)
        my = sum(y for _, y in pairs) / len(pairs)
        centered += [(x - mx, y - my) for x, y in pairs]
    return sum(x * y for x, y in centered) / sum(x * x for x, _ in centered)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--core-truth", required=True, type=Path)
    parser.add_argument("--graded", required=True, type=Path)
    parser.add_argument("--service-dir", required=True, type=Path)
    parser.add_argument("--run", action="append", required=True, help="이름=결과 폴더(쉼표로 여러 개)")
    parser.add_argument("--caps", nargs="+", type=int, required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("기존 결과를 덮어쓰지 않습니다.")
    from transformers import AutoTokenizer
    def blocked(*a, **kw):
        raise RuntimeError("로컬 파서 비교에서 네트워크를 차단했습니다.")
    socket.socket.connect = blocked
    socket.create_connection = blocked
    sys.path.insert(0, str(args.service_dir))
    from apps.text.parse_label import parse_label
    from apps.text.qa_comparison import compare_material_compositions
    if "apps.text.ocr_text" in sys.modules:
        raise RuntimeError("Vision 호출 모듈이 import됐습니다.")
    manifest = read(args.manifest)
    core = read(args.core_truth)
    graded = {r["file_name"]: r for r in read(args.graded)}
    runs = dict(item.split("=", 1) for item in args.run)
    loaded = {name: {r["id"]: load_result(name, path, r["id"]) for r in manifest} for name, path in runs.items()}
    models = {name: next(iter(rows.values()))[1]["settings"]["model"] for name, rows in loaded.items()}
    slopes = {model: per_token_seconds([[(m["generated_tokens"], m["inference_seconds"]) for _, m, _ in loaded[name].values()]
                                        for name in loaded if models[name] == model])
              for model in set(models.values())}
    model_dirs = read(ROOT / "models/manifest.json")
    tokenizers = {model: AutoTokenizer.from_pretrained(model_dirs[model]["local_dir"], local_files_only=True)
                  for model in set(models.values())}
    virtual = {}
    for name, rows in loaded.items():
        model = models[name]
        for cap in args.caps:
            key = f"{name}_cap{cap}"
            virtual[key] = {}
            for pid, (folder, meta, text) in rows.items():
                ids = tokenizers[model].encode(text, add_special_tokens=False)
                cut = len(ids) > cap
                extra = max(0, (meta.get("generated_tokens") or 0) - cap)
                seconds = meta["inference_seconds"] - slopes[model] * extra
                virtual[key][pid] = (folder, {**meta, "truncated": bool(meta.get("truncated") or cut),
                                              "inference_seconds": round(seconds, 3),
                                              "generated_tokens": min(meta.get("generated_tokens") or 0, cap)},
                                     tokenizers[model].decode(ids[:cap]).strip() if cut else text)
    result = evaluate(manifest, core["core_tokens"], graded, {key: key for key in virtual},
                      parse_label, compare_material_compositions, load=lambda name, path, pid: virtual[name][pid])
    for key, total in result["totals"].items():
        secs = [row["engines"][key]["seconds_reference"] for row in result["rows"]]
        total["within_10s"] = sum(s <= 10 for s in secs)
        total["within_25s"] = sum(s <= 25 for s in secs)
    result.update({
        "created_at": datetime.now().astimezone().isoformat(),
        "manifest": str(args.manifest), "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "core_truth": str(args.core_truth), "runs": runs, "caps": args.caps,
        "per_token_seconds": {model: round(value, 4) for model, value in slopes.items()},
        "parser_path": "parse_label(text), 비율 허용오차0",
        "policy": "exact_complete는 상한에서 끊긴 출력을 미완료로 뺀 값. raw_parser_exact는 끊긴 출력도 파싱해 쓰는 마감 시간 방식의 값.",
        "limitations": [
            "모델을 다시 돌리지 않은 추정이다. 저장 텍스트를 다시 토큰화해 끊었으므로 실제 생성 토큰과 몇 개 차이가 날 수 있다.",
            "시간은 줄어든 토큰 수 × 모델별 토큰당 시간을 뺀 추정치다. 실제 상한 실행으로 확인해야 한다.",
        ],
    })
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "per_token_seconds": result["per_token_seconds"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
