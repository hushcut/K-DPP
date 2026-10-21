"""별도 파이썬 프로세스 테스트 헬퍼.

설정·앱 객체는 main 을 import 할 때 정해지므로, 환경변수를 바꿔 보는 테스트는 새 프로세스에서
main 을 import 합니다. 자식 프로세스를 띄우는 테스트는 모두 이 헬퍼를 거칩니다.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def run_python(code, **env):
    """BACKEND 폴더에서 `python -c <code>` 를 돌린다. env 는 지금 환경변수 위에 덧붙일 값.

    자식이 쓰는 표준 입출력과 부모가 읽는 인코딩을 둘 다 UTF-8 로 고정합니다. 한국어 Windows 에서
    PYTHONUTF8 없이 PYTHONIOENCODING=utf-8 만 두면 자식은 물려받은 값대로 한글 오류를 UTF-8 로 쓰는데,
    text=True 인 부모는 로캘(cp949)로 읽다 실패합니다(#36 Windows 댓글). PYTHONUTF8 이 아니라
    PYTHONIOENCODING 만 넣어, 자식의 나머지 동작(파일을 여는 기본 인코딩 등)은 실제 서버와 같게 둡니다.
    """
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env={**os.environ, **env, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        encoding="utf-8",
        timeout=60,
    )
