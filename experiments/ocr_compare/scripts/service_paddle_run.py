"""서비스 전체 판정 경로(여러 후보·좌표 재구성·안전 판정)를 Vision 대신 PaddleOCR 응답으로 실행한다.

- 서비스 코드는 고치지 않는다. `_run_google_ocr`만 PaddleOCR 작업 프로세스 호출로 바꿔 끼운다.
- PaddleOCR은 줄 단위 좌표를 낸다. Vision은 단어 단위라서, 줄을 공백으로 나누고 글자 폭에 비례해 좌표를 나눈다.
- 서비스의 시간 제한은 끄고 호출마다 시간을 기록한다. PaddleOCR 호출 한 번이 제한보다 길어 그대로 두면 판정까지 가지 못한다.
- 네트워크를 막고 실행하며 Vision 인증 정보를 쓰지 않는다. 응답은 서비스 OCR 캐시 형식으로 저장한다.
- --offline이면 PaddleOCR을 띄우지 않고 캐시만으로 다시 판정한다(Vision 캐시 사본으로 기준 수치 확인에도 쓴다).

실행 예: <서비스 .venv python> -I -X utf8 service_paddle_run.py --service-dir <서비스 코드> --items <정답표 JSON> \\
          --photos <사진 폴더> --ocr-cache <새 캐시 JSON> --output <새 결과 JSON> \\
          --paddle-python <paddleocr venv python> --paddle-worker paddleocr/scripts/21_ocr_worker.py
"""
import argparse
import base64
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import time

WORD_GAP = 0.3


def block_network():
    def blocked(*args, **kwargs):
        raise RuntimeError("이 실행은 외부 네트워크를 쓰지 않습니다.")
    socket.socket.connect = blocked
    socket.create_connection = blocked


def char_width(char):
    """글자 폭 근사값. 한글·한자는 영문·숫자보다 넓다."""
    return 1.0 if ord(char) > 0x2E7F else 0.55


def lerp(a, b, t):
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


def reading_quad(polygon, rotated, angle):
    """네 꼭짓점을 글자 읽는 방향 기준(왼쪽 위부터 시계 방향)으로 돌린다. Vision 단어 좌표와 같은 순서다."""
    shift = (1 if rotated else 0) + (2 if angle == 180 else 0)
    return polygon[shift:] + polygon[:shift]


def line_to_word_boxes(line, scale):
    """줄 하나를 (단어, 네 꼭짓점) 목록으로 나눈다. 좌표는 축소 전 이미지 기준 정수다."""
    parts = line["text"].split()
    if not parts:
        return []
    quad = [(x / scale, y / scale) for x, y in line["polygon"]]
    top_left, top_right, bottom_right, bottom_left = reading_quad(quad, line.get("rotated", False),
                                                                  line.get("textline_angle", 0))
    widths = [sum(char_width(c) for c in part) for part in parts]
    total = sum(widths) + WORD_GAP * (len(parts) - 1)
    boxes, position = [], 0.0
    for part, width in zip(parts, widths):
        start, end = position / total, (position + width) / total
        vertices = (lerp(top_left, top_right, start), lerp(top_left, top_right, end),
                    lerp(bottom_left, bottom_right, end), lerp(bottom_left, bottom_right, start))
        boxes.append((part, tuple((round(x), round(y)) for x, y in vertices)))
        position += width + WORD_GAP
    return boxes


class PaddleWorker:
    def __init__(self, python, script, log_path, worker_args=()):
        self.command = [str(Path(python).absolute()), "-X", "utf8", str(Path(script).absolute()), *worker_args]
        self.log_path = log_path
        self.process = None
        self.start()

    def start(self):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        log = open(self.log_path, "a", encoding="utf-8")
        self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                                        text=True, encoding="utf-8", errors="replace", env=env)
        log.close()
        self._read_until("@@READY")

    def _read_until(self, prefix):
        for line in self.process.stdout:
            if line.startswith(prefix):
                return line[len(prefix):].strip()
        raise RuntimeError(f"PaddleOCR 작업 프로세스가 종료됐습니다(코드 {self.process.wait()}).")

    def read(self, content):
        self.process.stdin.write(base64.b64encode(content).decode("ascii") + "\n")
        self.process.stdin.flush()
        return json.loads(self._read_until("@@RESULT "))

    def close(self):
        self.process.stdin.close()
        self.process.wait()


def summarize(rows):
    seconds = [r["paddle_seconds"] for r in rows if r["paddle_calls"]]
    originals = [r["original_seconds"] for r in rows if r["original_seconds"] is not None]
    return {
        "photos": len(rows), "exact": sum(r["exact"] for r in rows),
        "wrong_success": sum(r["wrong_success"] for r in rows),
        "status": dict(Counter(r["status"] for r in rows)),
        "error_codes": dict(Counter(r["error_code"] or "" for r in rows if r["status"] != "success")),
        "best_source_of_exact": dict(Counter(r["best_source"] for r in rows if r["exact"])),
        "cache_incomplete": sum(r["cache_incomplete"] for r in rows),
        "calls_per_photo": round(statistics.mean(r["paddle_calls"] for r in rows), 2),
        "time": {"median_total": round(statistics.median(seconds), 1), "max_total": round(max(seconds), 1),
                 "total_within_25s": sum(s <= 25 for s in seconds), "measured": len(seconds),
                 "median_original": round(statistics.median(originals), 1),
                 "original_within_10s": sum(s <= 10 for s in originals)} if seconds else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-dir", required=True, type=Path)
    parser.add_argument("--items", required=True, type=Path, help="image_id·file_name·answer·included를 가진 정답표 JSON")
    parser.add_argument("--photos", required=True, type=Path)
    parser.add_argument("--ocr-cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--paddle-python")
    parser.add_argument("--paddle-worker", type=Path)
    parser.add_argument("--limit", type=int, help="앞에서 몇 장만 실행한다(동작 확인용).")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("기존 결과를 덮어쓰지 않습니다.")
    if not args.offline and not (args.paddle_python and args.paddle_worker):
        raise ValueError("--offline이 아니면 PaddleOCR 작업 프로세스 경로가 필요합니다.")
    for name in ("KDPP_ENABLE_REFLECTION_OCR", "KDPP_ENABLE_DENOISED_OCR", "KDPP_ENABLE_ROTATED_OCR",
                 "KDPP_ENABLE_MATERIAL_REGION_OCR", "GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ.pop(name, None)
    block_network()
    sys.path.insert(0, str(args.service_dir))
    from apps.service.label_analysis import analyze_ocr_result
    from apps.text import ocr_text
    from apps.text.ocr_cache import OcrTextCache, image_sha256
    from apps.text.ocr_layout import OcrWord, spatial_text_from_words
    from apps.text.qa_comparison import compare_material_compositions
    if not Path(ocr_text.__file__).resolve().is_relative_to(args.service_dir.resolve()):
        raise RuntimeError("지정한 코드 폴더가 아닌 모듈을 불러왔습니다.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    calls_path = args.output.with_suffix(".calls.jsonl")
    calls = []
    worker = None
    if not args.offline:
        worker = PaddleWorker(args.paddle_python, args.paddle_worker, args.output.with_suffix(".worker.log"))

        def run_paddle(client, content, *, timeout_seconds=None):
            del client, timeout_seconds
            read = worker.read(content)
            words = []
            for line in read["lines"]:
                for text, vertices in line_to_word_boxes(line, read["scale"]):
                    xs, ys = zip(*vertices)
                    words.append(OcrWord(text, min(xs), min(ys), max(xs), max(ys), vertices))
            words = tuple(words)
            call = {"sha256": image_sha256(content), "seconds": read["seconds"], "lines": read["recognized_lines"],
                    "words": len(words), "peak_rss_mb": read["peak_rss_mb"]}
            calls.append(call)
            with calls_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(call, ensure_ascii=False) + "\n")
            return ocr_text.OcrPayload(
                text="\n".join(line["text"] for line in read["lines"]).strip(),
                layout_text=spatial_text_from_words(list(words)).strip() if words else "",
                retry_count=0, rpc_attempt_count=1, layout_words=words,
            )

        ocr_text._run_google_ocr = run_paddle
        ocr_text._resolve_credential_path = lambda path: (None, None)
        ocr_text._get_vision_client = lambda *a: object()
        ocr_text.OCR_TOTAL_TIMEOUT_SECONDS = 1e9
        for source in ocr_text.OCR_CANDIDATE_TIMEOUT_SECONDS:
            ocr_text.OCR_CANDIDATE_TIMEOUT_SECONDS[source] = 1e9

    cache = OcrTextCache(args.ocr_cache)
    items = [g for g in json.loads(args.items.read_text(encoding="utf-8-sig")) if g.get("included", True)]
    rows = []
    for item in items[:args.limit]:
        before = len(calls)
        row = {"id": item["image_id"], "file_name": item["file_name"]}
        try:
            result = ocr_text.run_ocr_bytes(ocr_text.read_image_bytes(args.photos / item["file_name"]),
                                            ocr_cache=cache, offline=args.offline, cache_label=item["file_name"])
            final = analyze_ocr_result(result)
            materials = final.get("materials") or {}
            exact = final["status"] == "success" and bool(materials) and compare_material_compositions(
                item["answer"], materials, tolerance=0).judgment == "success"
            row.update(status=final["status"], error_code=final.get("error_code"), exact=exact,
                       wrong_success=final["status"] == "success" and not exact, materials=materials,
                       best_source=result.metadata.source,
                       conflicting_parts=list(result.metadata.conflicting_parts),
                       unpaired_ratio_parts=list(result.metadata.unpaired_ratio_parts),
                       rejected_composition_parts={part: list(reasons) for part, reasons
                                                   in result.metadata.rejected_composition_parts.items()},
                       attempts=[{"source": a.source, "outcome": a.outcome, "failure_code": a.failure_code,
                                  "elapsed_ms": a.elapsed_ms} for a in result.metadata.attempts],
                       cache_incomplete=any(a.failure_code for a in result.metadata.attempts))
        except ocr_text.OcrCacheMissError as exc:
            row.update(status="ocr_error", error_code=type(exc).__name__, exact=False, wrong_success=False,
                       materials={}, best_source="", attempts=[], cache_incomplete=True)
        made = calls[before:]
        row.update(paddle_calls=len(made), paddle_seconds=round(sum(c["seconds"] for c in made), 3),
                   original_seconds=made[0]["seconds"] if made else None)
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("id", "status", "exact", "paddle_calls", "paddle_seconds")},
                         ensure_ascii=False), flush=True)
    if worker:
        worker.close()
    output = {"created_at": datetime.now().astimezone().isoformat(), "service_dir": str(args.service_dir),
              "offline": args.offline, "ocr_cache": str(args.ocr_cache),
              "peak_rss_mb": max((c["peak_rss_mb"] or 0 for c in calls), default=None),
              "summary": summarize(rows), "rows": rows}
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
