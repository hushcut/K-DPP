"""BACKEND가 AI 모듈과 실제로 결합되는지 확인합니다 (CI 백엔드 잡에서 실행).

main.py는 AI 모듈 import 실패를 try/except로 삼켜 run_ocr / parse_label을 None으로 둡니다.
그러면 실사진 스캔이 전부 503(AI_MODULE_FAILED)이 되는데, pytest는 raw_ocr_text를 보내거나
스텁을 쓰기 때문에 이 경로에 들어가지 않아 결합이 끊겨도 전건 초록입니다. 그 사각지대를 메웁니다.

BACKEND/requirements.txt만 설치된 상태(배포 런타임과 같은 조건)에서 돌려야 의미가 있습니다.
"""

import sys


def main() -> int:
    import main as backend_main  # noqa: PLC0415 - sys.path 설정이 import 시점에 일어납니다.

    problems = []

    if backend_main.run_ocr is None:
        problems.append("apps.text.ocr_text.run_ocr import 실패 - 실사진 스캔이 전부 503이 됩니다")
    if backend_main.parse_label is None:
        problems.append("apps.text.parse_label.parse_label import 실패 - 소재 파싱이 전부 503이 됩니다")

    if not problems:
        # main.py가 sys.path에 AI 경로를 넣은 뒤에야 직접 import할 수 있습니다.
        from apps.text import ocr_text

        if getattr(ocr_text, "Image", None) is None:
            problems.append(
                "Pillow 미설치 - preprocess_image_bytes가 None을 반환해 OCR 전처리 후보가 "
                "조용히 비활성화됩니다(스캔당 Vision 호출이 2회에서 1회로 줄어 인식률이 달라짐)"
            )

    for problem in problems:
        print(f"[FAIL] {problem}", file=sys.stderr)
    if problems:
        print("BACKEND/requirements.txt를 확인하세요.", file=sys.stderr)
        return 1

    print("AI 모듈 결합 OK (run_ocr / parse_label / Pillow)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
