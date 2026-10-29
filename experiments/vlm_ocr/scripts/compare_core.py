"""기존 핵심 토큰 기준을 재현한 뒤 새 OCR의 같은 기준 결과를 기록한다."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def normalize(text):
    return "".join(text.split())


def assess(text, tokens):
    if not tokens:
        return {"status": "uncertain", "missing": []}
    compact = normalize(text)
    missing = []
    for token, count in Counter(tokens).items():
        observed = compact.count(token)
        if observed < count:
            missing.append({"token": token, "expected": count, "observed": observed})
    return {"status": "mismatch" if missing else "core_exact", "missing": missing}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", required=True, type=Path)
    parser.add_argument("--experiments-root", required=True, type=Path)
    parser.add_argument("--run", action="append", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("기존 비교 결과를 덮어쓰지 않습니다.")
    baseline_bytes = args.previous.read_bytes()
    previous = json.loads(baseline_bytes.decode("utf-8-sig"))
    tokens = previous["core_tokens_draft"]
    baseline = {}
    disagreements = []
    for name, relative in previous["runs"].items():
        correct = 0
        for pid, expected_tokens in tokens.items():
            text = (args.experiments_root / relative / pid / "text.txt").read_text(encoding="utf-8")
            result = assess(text, expected_tokens)
            expected = previous["per_photo"][pid][name]
            if result["status"] != expected:
                disagreements.append({"model": name, "id": pid, "recorded": expected, "calculated": result["status"]})
            correct += result["status"] == "core_exact"
        baseline[name] = {"core_exact": correct}
    if disagreements:
        raise RuntimeError("기존 판정 재현 불일치: " + json.dumps(disagreements, ensure_ascii=False))
    rows = []
    totals = {}
    for name, directory in (item.split("=", 1) for item in args.run):
        run = Path(directory)
        current = []
        for pid, expected_tokens in tokens.items():
            meta = json.loads((run / pid / "result.json").read_text(encoding="utf-8"))
            text = (run / pid / "text.txt").read_text(encoding="utf-8")
            result = assess(text, expected_tokens)
            result.update({"id": pid, "model": name, "runtime_status": meta["status"],
                           "truncated": meta.get("truncated", False),
                           "inference_seconds": meta["inference_seconds"]})
            if meta["status"] != "success" or meta.get("truncated"):
                result["status"] = "uncertain" if not expected_tokens else "mismatch"
            current.append(result)
        totals[name] = {
            "photos": len(current),
            **{status: sum(row["status"] == status for row in current)
               for status in ("core_exact", "mismatch", "uncertain")},
            "runtime_errors": sum(row["runtime_status"] != "success" for row in current),
            "truncated": sum(row["truncated"] for row in current),
        }
        rows.extend(current)
    output = {
        "criterion": previous["core_tokens_note"],
        "source_criterion_sha256": hashlib.sha256(baseline_bytes).hexdigest(),
        "limitations": [
            "기존 초안 핵심 토큰의 공백 무시·대소문자 구분·중복 개수 기준이다.",
            "전체 문자열 CER이나 소재와 숫자의 공간 연결 정확도를 평가하지 않는다.",
            "13번 원본은 정답 확정 보류를 유지한다.",
            "19번의 75%/76% 판독 차이는 별도 원본 대조 대상으로 남긴다. 기존 토큰 목록을 바꾸지 않았다.",
        ],
        "baseline_reproduced": baseline, "totals": totals, "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"baseline_reproduced": baseline, "totals": totals}, ensure_ascii=False))


if __name__ == "__main__":
    main()

