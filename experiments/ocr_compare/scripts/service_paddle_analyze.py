"""서비스 경로 PaddleOCR 결과(service_paddle_run.py)를 Vision과 사진별로 비교하고 실패 원인을 나눈다.

- OCR을 새로 돌리지 않는다. 두 엔진의 서비스 OCR 캐시와 결과 JSON만 읽고 네트워크를 막는다.
- 원인 분해: 원본 후보에서 Vision이 읽은 글자에 PaddleOCR의 검출 영역·좌표 근사만 차례로 적용해 파서 정답 수를 잰다.
  Vision 글자 → 검출 영역 안의 단어만 → 줄 좌표를 글자 폭으로 나눈 단어 좌표 → 실제 PaddleOCR 글자 순서다.
- 라벨에 무엇이 적혔는지는 Vision 글자로 대신한다. 소재명 포함 여부는 서비스 소재 사전의 문자열 검색이라 대략값이다.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import socket
import statistics
import sys

sys.path.insert(0, str(Path(__file__).absolute().parent))
from service_paddle_run import line_to_word_boxes

LIMITS = {"original": 10, "preprocessed": 8, "material_crop": 5, "material_crop_rotated": 5}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def script_of(text):
    kinds = set()
    for char in text:
        code = ord(char)
        if 0xAC00 <= code <= 0xD7A3:
            kinds.add("hangul")
        elif 0x3040 <= code <= 0x30FF or 0x3400 <= code <= 0x9FFF or 0xF900 <= code <= 0xFAFF:
            kinds.add("han_kana")
        elif char.isascii() and char.isalpha():
            kinds.add("latin")
        elif char.isdigit():
            kinds.add("digit")
    return kinds


def inside(point, quad):
    signs = set()
    for (x1, y1), (x2, y2) in zip(quad, quad[1:] + quad[:1]):
        cross = (x2 - x1) * (point[1] - y1) - (y2 - y1) * (point[0] - x1)
        if cross:
            signs.add(cross > 0)
    return len(signs) == 1


def paddle_lines(entry):
    """캐시의 글자 줄과 단어 순서로 PaddleOCR 줄 영역과 글자를 복원한다."""
    words, position, quads, texts = entry["layout_words"], 0, [], []
    for line in entry["text"].split("\n"):
        count = len(line.split())
        if not count:
            continue
        first, last = words[position], words[position + count - 1]
        quads.append([first["vertices"][0], last["vertices"][1], last["vertices"][2], first["vertices"][3]])
        texts.append(line.lower().replace(" ", ""))
        position += count
    if position != len(words):
        raise RuntimeError("글자 줄과 단어 수가 맞지 않습니다.")
    return quads, texts


def center(word):
    return (word["left"] + word["right"]) / 2, (word["top"] + word["bottom"]) / 2


def assign_words(words, quads):
    """Vision 단어를 중심점이 들어가는 PaddleOCR 줄에 배정한다. 어느 줄에도 없으면 outside다."""
    groups, outside = defaultdict(list), []
    for word in words:
        point = center(word)
        index = next((i for i, quad in enumerate(quads) if inside(point, quad)), None)
        if index is None:
            outside.append(word)
        else:
            groups[index].append(word)
    return groups, outside


def apportioned(groups, quads):
    """줄에 모인 단어를 PaddleOCR 줄 좌표에서 글자 폭으로 나눈 좌표로 바꾼다(변환기와 같은 방식)."""
    rows = []
    for index, members in groups.items():
        (x0, y0), (x1, y1) = quads[index][0], quads[index][1]
        ordered = sorted(members, key=lambda w: (center(w)[0] - x0) * (x1 - x0) + (center(w)[1] - y0) * (y1 - y0))
        text = " ".join(w["text"] for w in ordered)
        for part, vertices in line_to_word_boxes({"text": text, "polygon": quads[index]}, 1.0):
            xs, ys = zip(*vertices)
            rows.append({"text": part, "left": min(xs), "top": min(ys), "right": max(xs), "bottom": max(ys),
                         "vertices": list(vertices), "page": 0})
    return rows


def has_number(number, text):
    return re.search(rf"(?<!\d){number:g}(?!\d)", text) is not None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-dir", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path, help="service_paddle_run.py 결과 폴더")
    parser.add_argument("--set", action="append", required=True, help="이름=정답표JSON=1단계평가JSON")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("기존 결과를 덮어쓰지 않습니다.")

    def blocked(*a, **kw):
        raise RuntimeError("이 분석은 외부 네트워크를 쓰지 않습니다.")
    socket.socket.connect = blocked
    socket.create_connection = blocked
    sys.path.insert(0, str(args.service_dir))
    from apps.text.ocr_layout import OcrWord, spatial_text_from_words
    from apps.text.parse_label import parse_label
    from apps.text.qa_comparison import compare_material_compositions
    from apps.text.rules import MATERIAL_ALIASES, MATERIAL_KOREAN

    def exact(text, answer):
        materials = parse_label(text).get("materials") or {}
        return bool(materials) and compare_material_compositions(answer, materials, tolerance=0).judgment == "success"

    def layout_of(rows):
        return spatial_text_from_words([OcrWord(r["text"], r["left"], r["top"], r["right"], r["bottom"],
                                                tuple(tuple(p) for p in r["vertices"]), r.get("page", 0))
                                        for r in rows]).strip() if rows else ""

    def aliases(key):
        return {a.lower().replace(" ", "") for a in [*MATERIAL_ALIASES.get(key, ()), MATERIAL_KOREAN.get(key, key), key] if a}

    def compact(entries):
        return "".join(e["text"] + "\n" + e.get("layout_text", "") for e in entries.values()).lower().replace(" ", "")

    def any_candidate(entries, answer):
        return any(exact(e["text"], answer) or exact(e.get("layout_text", ""), answer) for e in entries.values())

    report = {}
    for spec in args.set:
        name, items_path, step1_path = spec.split("=")
        items = {g["file_name"]: g for g in read(items_path) if g.get("included", True)}
        paddle = read(args.results / f"paddle_{name}.json")["rows"]
        vision = {r["file_name"]: r for r in read(args.results / f"vision_{name}_baseline.json")["rows"]}
        by_source = {r["source"]: r for r in read(step1_path)["rows"]}
        caches = {engine: defaultdict(dict) for engine in ("paddle", "vision")}
        for engine in caches:
            for entry in read(args.results / f"{engine}_{name}_cache.json")["entries"].values():
                caches[engine][entry["file_name"]][entry["source"]] = entry
        calls = [json.loads(line) for line in
                 (args.results / f"paddle_{name}.calls.jsonl").read_text(encoding="utf-8").splitlines()]
        call_source = {k: v["source"] for k, v in read(args.results / f"paddle_{name}_cache.json")["entries"].items()}

        ladder, scenario, failures = Counter(), Counter(), Counter()
        word_total, word_seen, word_read = Counter(), Counter(), Counter()
        photos = []
        for row in paddle:
            file_name, answer = row["file_name"], items[row["file_name"]]["answer"]
            p_entries, v_entries = caches["paddle"][file_name], caches["vision"][file_name]
            p_orig, v_orig = p_entries["original"], v_entries["original"]
            step1 = by_source[file_name]["engines"]
            flags = {
                "paddle_step1_text": bool(step1["paddle_default"]["raw_parser_exact"]),
                "paddle_text": exact(p_orig["text"], answer),
                "paddle_layout": exact(p_orig.get("layout_text", ""), answer),
                "paddle_any_candidate": any_candidate(p_entries, answer),
                "paddle_service": row["exact"],
                "vision_step1_text": bool(step1["vision"]["raw_parser_exact"]),
                "vision_text": exact(v_orig["text"], answer),
                "vision_layout": exact(v_orig.get("layout_text", ""), answer),
                "vision_any_candidate": any_candidate(v_entries, answer),
                "vision_service": vision[file_name]["exact"],
            }
            ladder.update(k for k, v in flags.items() if v)

            # 원인 분해
            quads, line_texts = paddle_lines(p_orig)
            v_words = v_orig.get("layout_words", [])
            groups, outside = assign_words(v_words, quads)
            inside_words = [w for members in groups.values() for w in members]
            line_of = {id(w): index for index, members in groups.items() for w in members}
            answer_names = set().union(*(aliases(key) for key in answer))
            answer_numbers = {f"{n:g}" for n in answer.values()}
            for word in v_words:
                lowered = word["text"].lower()
                index = line_of.get(id(word))
                kinds = {*(script_of(word["text"]) or {"symbol"}), "all"}
                if lowered in answer_names:
                    kinds.add("answer_name")
                if lowered in answer_numbers:
                    kinds.add("answer_number")
                if lowered == "%":
                    kinds.add("percent_sign")
                for kind in kinds:
                    word_total[kind] += 1
                    word_seen[kind] += index is not None
                    word_read[kind] += index is not None and lowered in line_texts[index]
            steps = {
                "A_vision_all": exact(layout_of(v_words), answer),
                "B_detected_only": exact(layout_of(inside_words), answer),
                "C_detected_apportioned": exact(layout_of(apportioned(groups, quads)), answer),
                "D_all_apportioned": exact(layout_of(apportioned(groups, quads) + outside), answer),
            }
            scenario.update(k for k, v in steps.items() if v)
            scenario["vision_layout_same_as_A"] += layout_of(v_words) == v_orig.get("layout_text", "").strip()

            # 실패 사진에서 정답 소재명·비율이 글자에 있는지
            p_text, v_text = compact(p_entries), compact(v_entries)
            names = {key: aliases(key) for key in answer}
            p_names = all(any(a in p_text for a in als) for als in names.values())
            v_names = all(any(a in v_text for a in als) for als in names.values())
            p_numbers = all(has_number(n, p_text) for n in answer.values())
            v_numbers = all(has_number(n, v_text) for n in answer.values())
            p_percent = all(f"{n:g}%" in p_text for n in answer.values())
            readable = all(any(script_of(a) & {"hangul", "latin"} and a in v_text for a in als) for als in names.values())
            cause = ("소재명·비율 모두 있음" if p_names and p_numbers else "소재명 없음" if p_numbers else
                     "비율 숫자 없음" if p_names else "소재명·비율 모두 없음")
            if not row["exact"]:
                failures[f"paddle_failed:{cause}"] += 1
                failures[f"paddle_failed_vision_{'ok' if vision[file_name]['exact'] else 'failed'}:{cause}"] += 1
                if v_names and not readable:
                    failures["names_only_han_kana"] += 1
                    failures[f"names_only_han_kana_vision_{'ok' if vision[file_name]['exact'] else 'failed'}"] += 1
            photos.append({"id": row["id"], "file_name": file_name, **flags, **steps,
                           "cause": None if row["exact"] else cause,
                           "paddle_names": p_names, "paddle_numbers": p_numbers, "paddle_percent": p_percent,
                           "vision_names": v_names, "vision_numbers": v_numbers, "names_in_hangul_latin": readable,
                           "paddle_lines": len(quads), "vision_words": len(v_words), "inside_words": len(inside_words),
                           "error_code": row["error_code"], "best_source": row["best_source"],
                           "paddle_seconds": row["paddle_seconds"], "paddle_calls": row["paddle_calls"]})

        by_id = {r["id"]: r for r in photos}

        def only(a, b):
            return sorted(i for i, r in by_id.items() if r[a] and not r[b])

        per_source = defaultdict(list)
        for call in calls:
            per_source[call_source.get(call["sha256"], "?")].append(call["seconds"])
        totals = [r["paddle_seconds"] for r in paddle]
        exact_totals = [r["paddle_seconds"] for r in paddle if r["exact"]]
        report[name] = {
            "photos": len(paddle), "ladder": dict(ladder), "scenario": dict(scenario),
            "vision_attempts_per_photo": round(statistics.mean(len(r["attempts"]) for r in vision.values()), 2),
            "both_exact": sum(r["paddle_service"] and r["vision_service"] for r in photos),
            "paddle_only": only("paddle_service", "vision_service"),
            "vision_only": len(only("vision_service", "paddle_service")),
            "neither": sum(not r["paddle_service"] and not r["vision_service"] for r in photos),
            "gained_from_step1": only("paddle_service", "paddle_step1_text"),
            "lost_from_step1": only("paddle_step1_text", "paddle_service"),
            "gained_from_text": only("paddle_service", "paddle_text"),
            "lost_from_text": only("paddle_text", "paddle_service"),
            "any_candidate_not_service": only("paddle_any_candidate", "paddle_service"),
            "layout_only": only("paddle_layout", "paddle_text"), "text_only": only("paddle_text", "paddle_layout"),
            "vision_layout_only": len(only("vision_layout", "vision_text")),
            "vision_text_only": len(only("vision_text", "vision_layout")),
            "word_recall": {k: {"total": word_total[k], "detected": word_seen[k], "read_same": word_read[k],
                                "detected_share": round(word_seen[k] / word_total[k], 3),
                                "read_same_of_detected": round(word_read[k] / word_seen[k], 3) if word_seen[k] else None}
                            for k in word_total},
            "failures": dict(failures),
            "time": {
                "per_source": {s: {"calls": len(v), "median": round(statistics.median(v), 1), "max": round(max(v), 1),
                                   "limit": LIMITS.get(s), "within_limit": sum(x <= LIMITS.get(s, 0) for x in v),
                                   "speedup_for_median": round(statistics.median(v) / LIMITS[s], 1) if s in LIMITS else None,
                                   "speedup_for_all": round(max(v) / LIMITS[s], 1) if s in LIMITS else None}
                               for s, v in per_source.items()},
                "total_median": round(statistics.median(totals), 1), "total_max": round(max(totals), 1),
                "total_within_25s": sum(t <= 25 for t in totals),
                "exact_total_median": round(statistics.median(exact_totals), 1),
                "exact_within_25s": sum(t <= 25 for t in exact_totals),
                "speedup_total_median": round(statistics.median(totals) / 25, 1),
                "speedup_total_all": round(max(totals) / 25, 1),
            },
            "photos_detail": photos,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, value in report.items():
        print(name, json.dumps({k: v for k, v in value.items() if k != "photos_detail"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
