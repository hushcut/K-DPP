"""evaluate_batch.py 채점 결과(사진 묶음별)를 엔진 비교표로 모은다.

- 조성 정답 수는 두 가지로 센다. strict는 출력 제한에 걸리지 않은 결과만, raw는 잘린 출력도 파싱해 센다(마감 정책).
- 시간은 각 실행이 기록한 사진당 추론 시간(모델 불러오기 제외)으로 10초·25초 이내 사진 수를 센다.
- 무료 엔진 합집합은 "무료 엔진 중 하나라도 맞힌 사진"이며, 실제로 고를 방법이 없는 상한선이다.

실행 예: python -X utf8 engine_table.py --eval DJ=dj.json --eval QA=qa.json --reference vision --output table.json
"""
import argparse
import json
import statistics
from pathlib import Path


def summarize(rows, engine):
    graded = [r["engines"][engine] for r in rows if r["included_composition"]]
    times = [r["engines"][engine]["seconds_reference"] for r in rows
             if r["engines"][engine]["seconds_reference"] is not None]
    peaks = [r["engines"][engine]["peak_rss_mb"] for r in rows if r["engines"][engine]["peak_rss_mb"] is not None]
    return {
        "photos": len(rows), "composition_graded": len(graded),
        "strict_exact": sum(bool(e["exact_complete"]) for e in graded),
        "raw_exact": sum(bool(e["raw_parser_exact"]) for e in graded),
        "wrong_success_raw": sum(bool(e["wrong_but_success_raw"]) for e in graded),
        "no_materials": sum(not e["materials"] for e in graded),
        "truncated": sum(bool(r["engines"][engine]["truncated"]) for r in rows),
        "time": {"median": round(statistics.median(times), 1), "max": round(max(times), 1),
                 "within_10s": sum(t <= 10 for t in times), "within_25s": sum(t <= 25 for t in times),
                 "measured": len(times)} if times else None,
        "peak_rss_gb": round(max(peaks) / 1024, 1) if peaks else None,
    }


def overlap(rows, engines, reference):
    graded = [r for r in rows if r["included_composition"]]
    hit = {e: {r["id"] for r in graded if r["engines"][e]["raw_parser_exact"]} for e in engines}
    free = [e for e in engines if e != reference]
    union = set().union(*(hit[e] for e in free)) if free else set()
    result = {"free_union_raw": len(union)}
    if reference in hit:
        result.update({"reference_raw": len(hit[reference]), "free_union_not_reference": len(union - hit[reference]),
                       "reference_not_free_union": len(hit[reference] - union),
                       "reference_or_free_union": len(union | hit[reference]),
                       "per_engine_not_reference": {e: len(hit[e] - hit[reference]) for e in free}})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval", action="append", required=True, help="묶음이름=evaluate_batch 결과 JSON")
    parser.add_argument("--reference", default="vision", help="합집합 비교 기준 엔진")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("기존 결과를 덮어쓰지 않습니다.")
    table = {}
    for item in args.eval:
        name, path = item.split("=", 1)
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        engines = list(data["runs"])
        table[name] = {"source": path, "engines": {e: summarize(data["rows"], e) for e in engines},
                       "overlap": overlap(data["rows"], engines, args.reference)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, block in table.items():
        print(f"\n[{name}]")
        print("| 엔진 | 조성 strict | 조성 raw | 틀린 성공 | 조성 못 찾음 | 잘림 | 중앙값(초) | 최대(초) | ≤10초 | ≤25초 | 최대 메모리(GB) |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        for engine, s in block["engines"].items():
            t = s["time"] or {}
            print(f"| {engine} | {s['strict_exact']}/{s['composition_graded']} | {s['raw_exact']} | "
                  f"{s['wrong_success_raw']} | {s['no_materials']} | {s['truncated']} | {t.get('median', '-')} | "
                  f"{t.get('max', '-')} | {t.get('within_10s', '-')} | {t.get('within_25s', '-')} | "
                  f"{s['peak_rss_gb'] if s['peak_rss_gb'] is not None else '-'} |")
        print("겹침:", json.dumps(block["overlap"], ensure_ascii=False))


if __name__ == "__main__":
    main()
