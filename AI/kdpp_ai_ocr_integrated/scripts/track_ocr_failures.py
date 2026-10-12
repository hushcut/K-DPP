"""저장 OCR 평가 스냅샷의 소재 실패·부위 불일치·회귀를 오프라인으로 관리한다."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from apps.service.response_contract import normalize_label_response
from apps.text.qa_comparison import (
    compare_material_compositions,
    normalize_material_mapping,
    validate_tolerance,
)
from apps.text.ratio_contract import has_exact_total


class FailureSnapshotError(ValueError):
    """스냅샷의 평가 범위나 자동 판정 조건이 맞지 않는다."""


def _snapshot(rows: Any, tolerance: float) -> tuple[dict, dict, dict]:
    if not isinstance(rows, list) or not rows:
        raise FailureSnapshotError("평가 스냅샷은 비어 있지 않은 행 목록이어야 합니다.")
    states, annotations, groups = {}, {}, {}
    cases = []
    for row in rows:
        if not isinstance(row, dict):
            raise FailureSnapshotError("평가 행의 형식이 잘못됐습니다.")
        image_id = row.get("image_id")
        if (not isinstance(image_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", image_id)
                or image_id in annotations):
            raise FailureSnapshotError("사진 ID는 경로 없는 고유 식별자여야 합니다.")
        if type(row.get("included")) is not bool:
            raise FailureSnapshotError("평가 포함 여부는 불리언이어야 합니다.")
        if not isinstance(row.get("source_group"), str) or not row["source_group"]:
            raise FailureSnapshotError("사진 계열이 필요합니다.")
        if (not isinstance(row.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
            raise FailureSnapshotError("사진 내용의 SHA256이 필요합니다.")
        part = row.get("answer_part")
        if not isinstance(part, str) or (part and not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", part)):
            raise FailureSnapshotError("정답 부위의 형식이 잘못됐습니다.")
        try:
            answer = normalize_material_mapping(row["answer"], allow_unknown=False)
            result = normalize_label_response(row["result"], api_version="1.0")
        except (KeyError, TypeError, ValueError, AttributeError):
            # Validation errors may contain the input, including private OCR.
            raise FailureSnapshotError("정답 또는 AI 응답의 형식이 잘못됐습니다.") from None
        if row["included"] and (not part or not has_exact_total(answer.values())):
            raise FailureSnapshotError("평가 대상의 정답 조성·부위가 완전해야 합니다.")
        selected = result["selected_part"]
        if selected and not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", selected):
            raise FailureSnapshotError("선택 부위의 형식이 잘못됐습니다.")
        review = result["parse_evidence"].get("review", {})
        if ((isinstance(review, dict) and review.get("confirmed") is True)
                or any(warning.startswith(("manual_composition_review_confirmed:",
                                            "confirmed_representative_selection:",
                                            "confirmed_material_alias:"))
                       for warning in result["warnings"])):
            raise FailureSnapshotError("사용자 확인 결과는 자동 평가에 포함할 수 없습니다.")
        annotations[image_id] = (row["included"], row["source_group"], row["sha256"], answer, part)
        if not row["included"]:
            continue
        exact = compare_material_compositions(answer, result["materials"], tolerance=0)
        tolerant = compare_material_compositions(answer, result["materials"], tolerance=tolerance)
        success = result["status"] == "success"
        material_exact = success and exact.judgment == "success"
        part_matches = selected == part
        category = ("material_unconfirmed" if not success else exact.failure_category
                    if not material_exact else "part_mismatch" if not part_matches else "success")
        state = {
            "image_id": image_id,
            "category": category,
            "status": result["status"],
            "material_exact": material_exact,
            "material_within_tolerance": success and tolerant.judgment == "success",
            "part_matches": part_matches,
            "selected_part": selected,
            "expected_part": part,
            "_composition": normalize_material_mapping(result["materials"]),
        }
        states[image_id] = state
        groups.setdefault(row["source_group"], []).append(material_exact)
        if category != "success":
            cases.append({key: value for key, value in state.items() if key != "_composition"})
    if not states:
        raise FailureSnapshotError("평가에 포함된 사진이 하나 이상 필요합니다.")
    summary = {
        "image_count": len(rows),
        "evaluated": len(states),
        "excluded": len(rows) - len(states),
        "material_exact": sum(s["material_exact"] for s in states.values()),
        "material_within_tolerance": sum(s["material_within_tolerance"] for s in states.values()),
        "material_and_part_exact": sum(s["material_exact"] and s["part_matches"] for s in states.values()),
        "group_count": len(groups),
        "group_material_exact": sum(all(values) for values in groups.values()),
        "material_unconfirmed": sum(s["status"] == "failed" for s in states.values()),
        "successful_wrong": sum(s["status"] == "success" and not s["material_exact"] for s in states.values()),
        "part_only_mismatch": sum(s["material_exact"] and not s["part_matches"] for s in states.values()),
    }
    return {"summary": summary, "cases": cases}, states, annotations


def track_failures(current: Any, baseline: Any = None, *, tolerance: float = 3) -> dict:
    """같은 사진·정답·평가 범위의 자동 결과만 비교하며 원문·정답표를 출력하지 않는다."""
    validate_tolerance(tolerance)
    report, states, annotations = _snapshot(current, tolerance)
    report["measurement"] = "stored_evaluation_snapshot"
    report["tolerance_pp"] = tolerance
    if baseline is not None:
        previous, old_states, old_annotations = _snapshot(baseline, tolerance)
        if annotations != old_annotations:
            raise FailureSnapshotError("사진·정답·부위·제외·계열 기준이 달라 비교할 수 없습니다.")
        report["comparison"] = {
            "baseline_summary": previous["summary"],
            "material_regressions": [key for key, value in states.items()
                                     if old_states[key]["material_exact"] and not value["material_exact"]],
            "material_recoveries": [key for key, value in states.items()
                                    if not old_states[key]["material_exact"] and value["material_exact"]],
            "material_and_part_regressions": [key for key, value in states.items()
                                 if old_states[key]["material_exact"] and old_states[key]["part_matches"]
                                 and not (value["material_exact"] and value["part_matches"])],
            "material_and_part_recoveries": [key for key, value in states.items()
                                if not (old_states[key]["material_exact"] and old_states[key]["part_matches"])
                                and value["material_exact"] and value["part_matches"]],
            "changed_case_ids": [key for key, value in states.items() if value != old_states[key]],
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", required=True, help="현재 저장 OCR 평가 JSON 목록")
    parser.add_argument("--baseline", help="같은 사진·정답·평가 범위의 기준 JSON 목록")
    parser.add_argument("--output", required=True, help="새 관리 JSON 경로. 기존 파일은 덮어쓰지 않음")
    parser.add_argument("--tolerance", type=float, default=3)
    args = parser.parse_args()
    try:
        current = json.loads(Path(args.current).read_text(encoding="utf-8-sig"))
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8-sig")) if args.baseline else None
        report = track_failures(current, baseline, tolerance=args.tolerance)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf8") as file:
            json.dump(report, file, ensure_ascii=False, indent=2)
            file.write("\n")
    except (OSError, ValueError):
        raise SystemExit("실패 관리 입력을 확인해 주세요. 기준 불일치·수동 결과·기존 출력은 허용하지 않습니다.") from None
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
