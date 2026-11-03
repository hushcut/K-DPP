"""영역을 잘라 읽은 VLM 결과를 전체 사진 결과와 같은 서비스 파서로 비교한다. OCR을 새로 호출하지 않는다.

- 자른 영역을 못 찾은 사진은 전체 사진 결과로 대신한다(실제로 쓸 때도 그렇게 해야 하기 때문).
- "자른 뒤 전체": 자른 결과를 파서가 성공으로 판정하면 쓰고, 아니면 전체 사진을 읽어 쓰는 순서형 규칙이다. 시간은 두 번 읽은 합이다.
- --crop은 이름=자른 이미지 목록=결과 폴더=기준 실행 이름이다. 결과 폴더는 쉼표로 여러 개를 줄 수 있고 앞 폴더를 먼저 쓴다.
  기준 실행은 --base 이름=결과 폴더로 준다.
"""
import argparse
from datetime import datetime
import importlib
import json
from pathlib import Path
import socket
import statistics
import sys

sys.path.insert(0, str(Path(__file__).absolute().parent))
evaluate_batch = importlib.import_module("evaluate_batch")
read = evaluate_batch.read


def stats(seconds):
    return {"count": len(seconds), "median": round(statistics.median(seconds), 1), "max": round(max(seconds), 1),
            "within_10s": sum(s <= 10 for s in seconds), "within_25s": sum(s <= 25 for s in seconds),
            "total_minutes": round(sum(seconds) / 60, 1)} if seconds else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--core-truth", required=True, type=Path)
    parser.add_argument("--graded", required=True, type=Path)
    parser.add_argument("--base", action="append", required=True, help="이름=전체 사진 결과 폴더")
    parser.add_argument("--crop", action="append", required=True, help="이름=자른 이미지 목록=결과 폴더=기준 실행 이름")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("기존 결과를 덮어쓰지 않습니다.")

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
    by_id = {item["id"]: item for item in manifest}
    base = dict(item.split("=", 1) for item in args.base)
    crops = {}
    for item in args.crop:
        name, crop_manifest, folder, base_name = item.split("=")
        rows = {row["id"]: row for row in read(crop_manifest)}
        for pid, row in rows.items():
            if row["parent_sha256"] != by_id[pid]["sha256"] or row["parent_source"] != by_id[pid]["source"]:
                raise RuntimeError(f"{name} {pid}: 자른 이미지의 원본이 사진 목록과 다릅니다.")
        crops[name] = {"rows": rows, "folders": [Path(p) for p in folder.split(",")], "base": base_name}

    def load(name, path, pid):
        crop = crops.get(name)
        if crop is None:
            return evaluate_batch.load_result(name, path, pid)
        if pid not in crop["rows"]:
            return evaluate_batch.load_result(name, base[crop["base"]], pid)
        folder = next(p / pid for p in crop["folders"] if (p / pid / "result.json").exists())
        meta = read(folder / "result.json")
        if meta["source_sha256"] != crop["rows"][pid]["sha256"]:
            raise RuntimeError(f"{name} {pid}: 결과가 자른 이미지와 다릅니다.")
        meta.update(source_name=by_id[pid]["source"], source_sha256=by_id[pid]["sha256"])
        return folder, meta, (folder / "text.txt").read_text(encoding="utf-8").strip()

    runs = {**base, **{name: ",".join(map(str, crop["folders"])) for name, crop in crops.items()}}
    result = evaluate_batch.evaluate(manifest, core["core_tokens"], {r["file_name"]: r for r in read(args.graded)},
                                     runs, parse_label, compare_material_compositions, load=load)
    rows = [row for row in result["rows"] if row["included_composition"]]
    comparison = {}
    for name, crop in crops.items():
        reference = crop["base"]
        cropped = [row for row in rows if row["id"] in crop["rows"]]
        seconds = [row["engines"][name]["seconds_reference"] for row in cropped]
        same_photos = [row["engines"][reference]["seconds_reference"] for row in cropped]
        sequential = sequential_wrong = 0
        sequential_seconds = []
        for row in rows:
            whole = row["engines"][reference]
            used, spent = whole, whole["seconds_reference"]
            if row["id"] in crop["rows"]:
                first = row["engines"][name]
                used, spent = (first, first["seconds_reference"]) if first["parser_status"] == "success" else (
                    whole, first["seconds_reference"] + whole["seconds_reference"])
            sequential += bool(used["raw_parser_exact"])
            sequential_wrong += bool(used["wrong_but_success_raw"])
            sequential_seconds.append(spent)
        tokens = [row["engines"][name]["generated_tokens"] for row in cropped]
        reference_tokens = [row["engines"][reference]["generated_tokens"] for row in cropped]
        gained = [row["id"] for row in rows if row["engines"][name]["raw_parser_exact"] and not row["engines"][reference]["raw_parser_exact"]]
        lost = [row["id"] for row in rows if row["engines"][reference]["raw_parser_exact"] and not row["engines"][name]["raw_parser_exact"]]
        comparison[name] = {
            "base": reference, "graded_photos": len(rows), "cropped_photos": len(cropped),
            "exact": sum(bool(row["engines"][name]["raw_parser_exact"]) for row in rows),
            "base_exact": sum(bool(row["engines"][reference]["raw_parser_exact"]) for row in rows),
            "exact_on_cropped": sum(bool(row["engines"][name]["raw_parser_exact"]) for row in cropped),
            "base_exact_on_cropped": sum(bool(row["engines"][reference]["raw_parser_exact"]) for row in cropped),
            "wrong_success": sum(bool(row["engines"][name]["wrong_but_success_raw"]) for row in rows),
            "gained": gained, "lost": lost,
            "either_exact": sum(bool(row["engines"][name]["raw_parser_exact"] or row["engines"][reference]["raw_parser_exact"]) for row in rows),
            "sequential_exact": sequential, "sequential_wrong": sequential_wrong,
            "time_cropped": stats(seconds), "time_base_same_photos": stats(same_photos),
            "time_sequential": stats(sequential_seconds),
            "median_tokens": statistics.median(tokens) if tokens else None,
            "base_median_tokens": statistics.median(reference_tokens) if reference_tokens else None,
            "loop_stopped": sum(bool(row["engines"][name]["loop_stopped"]) for row in cropped),
            "peak_rss_mb": max((row["engines"][name]["peak_rss_mb"] or 0) for row in cropped) if cropped else None,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "created_at": datetime.now().astimezone().isoformat(), "service_dir": str(args.service_dir),
        "base": base, "crops": {name: runs[name] for name in crops},
        "comparison": comparison, "totals": result["totals"], "rows": result["rows"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(comparison, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
