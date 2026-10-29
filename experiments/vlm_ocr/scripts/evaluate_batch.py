
"""사진 목록에 따라 로컬 OCR 결과를 같은 서비스 파서와 고정 핵심 토큰으로 평가한다."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import statistics
import sys


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def core_grade(text, tokens, complete):
    if not tokens:
        return {"status": "uncertain", "missing": []}
    compact = "".join(text.split())
    missing = [{"token": token, "expected": count, "observed": compact.count(token)}
               for token, count in Counter(tokens).items() if compact.count(token) < count]
    return {"status": "core_exact" if complete and not missing else "mismatch", "missing": missing}


def load_result(name, path, pid):
    # 쉼표로 여러 폴더를 주면 사진 결과가 있는 첫 폴더를 쓴다(재실행 결과를 앞에 둔다).
    folder = next((Path(p) / pid for p in path.split(",") if (Path(p) / pid / "result.json").exists()),
                  Path(path.split(",")[-1]) / pid)
    return folder, read(folder / "result.json"), (folder / "text.txt").read_text(encoding="utf-8").strip()


def evaluate(manifest, core_tokens, graded, runs, parse_label, compare, load=load_result):
    rows = []
    for item in manifest:
        pid = item["id"]
        gt = graded[item["source"]]
        if gt["sha256"] != item["sha256"]:
            raise RuntimeError(f"{pid}: 기존 조성 정답표와 사진 해시가 다릅니다.")
        row = {"id": pid, "source": item["source"], "sha256": item["sha256"],
               "source_group": gt["source_group"], "included_composition": gt["included"],
               "expected_materials": gt["answer"], "expected_part": gt["answer_part"], "engines": {}}
        for name, path in runs.items():
            folder, meta, text = load(name, path, pid)
            if meta["source_sha256"] != item["sha256"] or meta["source_name"] != item["source"]:
                raise RuntimeError(f"{name} {pid}: 다른 사진의 OCR 결과입니다.")
            complete = meta["status"] == "success" and not meta.get("truncated")
            parsed = parse_label(text)
            materials = parsed.get("materials") or {}
            exact = (bool(materials) and compare(gt["answer"], materials, tolerance=0).judgment == "success") if gt["included"] else None
            wrong = (parsed.get("status") == "success" and bool(materials) and exact is False) if gt["included"] else None
            row["engines"][name] = {
                "runtime_status": meta["status"], "truncated": meta.get("truncated", False),
                "complete_output": complete, "core": core_grade(text, core_tokens[pid], complete),
                "parser_status": parsed.get("status"), "parser_error": parsed.get("error_code") or "",
                "materials": materials, "selected_part": parsed.get("selected_part") or "",
                "part_matches": ((parsed.get("selected_part") or "") == gt["answer_part"]
                                 if gt["included"] and gt["answer_part"] else None),
                "raw_parser_exact": exact, "exact_complete": bool(exact and complete) if gt["included"] else None,
                "wrong_but_success_raw": wrong, "wrong_but_success_complete": bool(wrong and complete) if gt["included"] else None,
                "seconds_reference": meta["inference_seconds"], "peak_rss_mb": meta["peak_rss_mb"],
                "generated_tokens": meta.get("generated_tokens"), "loop_stopped": meta.get("loop_stopped", False),
                "run_folder": str(folder.parent),
            }
        rows.append(row)
    totals = {}
    for name in runs:
        all_results = [row["engines"][name] for row in rows]
        graded_results = [row["engines"][name] for row in rows if row["included_composition"]]
        tokens_graded = [e for e in all_results if e["core"]["status"] != "uncertain"]
        times = [e["seconds_reference"] for e in all_results if e["seconds_reference"] is not None]
        peaks = [e["peak_rss_mb"] for e in all_results if e["peak_rss_mb"] is not None]
        totals[name] = {
            "photos": len(all_results), "runtime_errors": sum(e["runtime_status"] != "success" for e in all_results),
            "truncated": sum(e["truncated"] for e in all_results),
            "incomplete_ids": [r["id"] for r in rows if not r["engines"][name]["complete_output"]],
            "core_evaluable": len(tokens_graded),
            "core_exact": sum(e["core"]["status"] == "core_exact" for e in all_results),
            "core_uncertain": sum(e["core"]["status"] == "uncertain" for e in all_results),
            "composition_graded": len(graded_results),
            "composition_exact": sum(e["exact_complete"] for e in graded_results),
            "raw_parser_exact": sum(e["raw_parser_exact"] for e in graded_results),
            "wrong_but_success": sum(e["wrong_but_success_complete"] for e in graded_results),
            "wrong_but_success_raw": sum(e["wrong_but_success_raw"] for e in graded_results),
            "no_materials": sum(not e["materials"] for e in graded_results),
            "excluded_but_materials_ids": [r["id"] for r in rows if not r["included_composition"] and r["engines"][name]["materials"]],
            "time_reference": {"mean_seconds": round(statistics.mean(times), 3),
                               "median_seconds": round(statistics.median(times), 3),
                               "max_seconds": max(times), "total_seconds": round(sum(times), 3)} if times else None,
            "max_process_peak_rss_mb": max(peaks) if peaks else None,
        }
    return {"totals": totals, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--core-truth", required=True, type=Path)
    parser.add_argument("--graded", required=True, type=Path)
    parser.add_argument("--photos", required=True, type=Path)
    parser.add_argument("--service-dir", required=True, type=Path)
    parser.add_argument("--run", action="append", required=True)
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
    if set(core["core_tokens"]) != {r["id"] for r in manifest}:
        raise RuntimeError("핵심 문구 기준과 사진 목록의 ID가 다릅니다.")
    source_checks = []
    for row in manifest:
        digest = hashlib.sha256((args.photos / row["source"]).read_bytes()).hexdigest()
        if digest != row["sha256"]:
            raise RuntimeError("원본 사진이 달라졌습니다.")
        source_checks.append({"id": row["id"], "sha256_matches": True})
    runs = dict(item.split("=", 1) for item in args.run)
    result = evaluate(manifest, core["core_tokens"],
                      {r["file_name"]: r for r in read(args.graded)}, runs, parse_label, compare_material_compositions)
    result.update({
        "created_at": datetime.now().astimezone().isoformat(),
        "manifest": str(args.manifest), "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "core_truth": str(args.core_truth), "core_truth_sha256": hashlib.sha256(args.core_truth.read_bytes()).hexdigest(),
        "core_criterion": core["criterion"], "source_verification": source_checks,
        "runs": runs, "service_dir": str(args.service_dir),
        "parser_path": "parse_label(text), 비율 허용오차0",
        "incomplete_policy": "출력 제한 도달 또는 실행 오류 결과는 핵심 문구 및 조성 정답으로 세지 않음. raw_parser_exact는 진단용으로 별도 기록.",
        "limitations": core.get("limitations") or [
            "핵심 토큰은 원본 사진 확인으로 작성한 초안이다. 전체 전사/CER 및 소재-숫자 공간 연결을 모두 평가하지 않는다.",
            "조성은 기존 정답표의 대표 조성과 비교한다. 부위 일치 여부는 별도로 기록한다.",
            "같은 라벨을 재촬영한 사진이 포함되므로 독립적인 의류 30개나 독립 홀드아웃으로 간주하지 않는다.",
            "실제 소재명 없는 DJ030·DJ046은 글자 평가는 포함하고 조성 평가는 제외한다.",
            "매우 희미한 DJ037은 핵심 문구 정답 보류. 기존 조성 정답표는 그대로 평가한다.",
            "이 PC의 CPU 처리 시간은 참고치이며 모델 선택은 정확도를 우선한다.",
        ],
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "totals": result["totals"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
