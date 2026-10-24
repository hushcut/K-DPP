"""여러 OCR 엔진의 글자 결과를 같은 서비스 파서(글자만 쓰는 parse_label 경로)에 넣어 소재·혼용률 판정을 비교한다.

- 서비스 코드는 읽기만 한다(--service-dir를 import 경로에 추가). 네트워크를 막고 실행하며, Vision 호출 모듈이
  import되면 중단한다.
- 정답은 서비스 QA 산출물(graded_results.json)의 대표 조성(answer, answer_part, included)을 쓴다.
- 각 OCR 실행 폴더는 <run>/<사진번호>/text.txt 형식이어야 한다.

실행 예: <서비스 .venv python> -B -I -X utf8 parser_compare.py --service-dir ... --graded ... \
          --run paddle=... --run vision=... --output results/parser_compare_20261025_01.json
"""
import argparse
import json
import socket
import sys
from pathlib import Path


def block_network():
    def blocked(*args, **kwargs):
        raise RuntimeError("이 비교는 외부 네트워크를 쓰지 않습니다.")
    socket.socket.connect = blocked
    socket.create_connection = blocked


def grade(compare, gt, materials):
    if not gt["included"]:
        return {"graded": False}
    if not materials:
        return {"graded": True, "exact": False, "tolerant_3pp": False, "reason": "no_materials"}
    exact = compare(gt["answer"], materials, tolerance=0)
    tolerant = compare(gt["answer"], materials, tolerance=3)
    return {"graded": True, "exact": exact.judgment == "success",
            "tolerant_3pp": tolerant.judgment == "success",
            "reason": "" if exact.judgment == "success" else exact.failure_reason}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-dir", required=True, type=Path)
    parser.add_argument("--graded", required=True, type=Path)
    parser.add_argument("--run", action="append", required=True, metavar="NAME=DIR")
    parser.add_argument("--ids", nargs="+", default=[f"{i:02d}" for i in range(1, 21)])
    parser.add_argument("--photo-prefix", default="KakaoTalk_20261003_141807993_")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("결과 파일이 이미 있습니다. 새 경로를 지정하세요.")

    block_network()
    sys.path.insert(0, str(args.service_dir))
    from apps.text.parse_label import parse_label
    from apps.text.qa_comparison import compare_material_compositions
    if "apps.text.ocr_text" in sys.modules:
        raise RuntimeError("Vision 호출 모듈이 import되었습니다.")

    graded = {row["file_name"]: row for row in json.loads(args.graded.read_text(encoding="utf-8"))}
    runs = dict(item.split("=", 1) for item in args.run)
    rows = []
    for pid in args.ids:
        gt = graded[f"{args.photo_prefix}{pid}.jpg"]
        row = {"id": pid, "image_id": gt["image_id"], "included": gt["included"],
               "answer": gt["answer"], "answer_part": gt["answer_part"], "engines": {}}
        for name, run_dir in runs.items():
            run = Path(run_dir) / pid
            meta = run / "result.json"
            if meta.exists():
                source_hash = json.loads(meta.read_text(encoding="utf-8"))["source_sha256"]
                if source_hash != gt["sha256"]:
                    raise RuntimeError(f"{name} {pid}: 정답표 사진과 해시가 다릅니다.")
            text = (run / "text.txt").read_text(encoding="utf-8").strip()
            result = parse_label(text)
            materials = result.get("materials") or {}
            row["engines"][name] = {
                "status": result.get("status"), "error_code": result.get("error_code") or "",
                "materials": materials, "selected_part": result.get("selected_part") or "",
                "part_matches": (result.get("selected_part") or "") == gt["answer_part"],
                **grade(compare_material_compositions, gt, materials),
            }
        live = gt["result"]
        row["engines"]["service_full_vision_20261010"] = {
            "status": live.get("status"), "error_code": live.get("error_code") or "",
            "materials": live.get("materials") or {}, "selected_part": live.get("selected_part") or "",
            "part_matches": gt.get("selected_part_matches"),
            "graded": gt["included"], "exact": gt.get("exact"), "tolerant_3pp": gt.get("tolerant_3pp"),
            "vision_calls": live.get("ocr", {}).get("external_call_count"),
            "vision_elapsed_ms": live.get("ocr", {}).get("elapsed_ms"),
        }
        rows.append(row)

    totals = {}
    for name in [*runs, "service_full_vision_20261010"]:
        graded_rows = [r["engines"][name] for r in rows if r["included"]]
        totals[name] = {
            "graded": len(graded_rows),
            "exact": sum(bool(e["exact"]) for e in graded_rows),
            "tolerant_3pp": sum(bool(e["tolerant_3pp"]) for e in graded_rows),
            "wrong_but_success": sum(e["status"] == "success" and bool(e["materials"]) and not e["exact"]
                                     for e in graded_rows),
            "no_result": sum(not e["materials"] for e in graded_rows),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "service_dir": str(args.service_dir), "graded": str(args.graded), "runs": runs,
        "path": "parse_label(text) 글자 전용 경로. 서비스 전체 경로(여러 OCR 후보, 단어 좌표)와 다르다.",
        "totals": totals, "rows": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(totals, ensure_ascii=False, indent=1))
    for r in rows:
        cells = []
        for name, e in r["engines"].items():
            mark = "-" if not r["included"] else ("O" if e["exact"] else ("~" if e["tolerant_3pp"] else "X"))
            cells.append(f"{name[:10]}:{mark}")
        print(r["id"], r["image_id"], json.dumps(r["answer"], ensure_ascii=False), " ".join(cells))


if __name__ == "__main__":
    main()
