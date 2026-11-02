"""process_helpers.run_python 이 로캘과 상관없이 자식이 쓴 한글을 읽는지 본다(#36 Windows 댓글)."""

import pytest

from process_helpers import run_python

# 이 프로세스가 run_python 으로 한글을 stderr 에 쓰는 자식을 띄우고, 로캘 인코딩과 읽은 것을 내놓는다.
# 로캘이 ASCII 인 프로세스도 명령줄을 그대로 받도록 소스는 ASCII 만 쓴다.
_PROBE = """
import locale, sys
sys.path.insert(0, "tests")
from process_helpers import run_python
child = run_python("import sys; print(chr(0xD55C) + chr(0xAE00), file=sys.stderr)")
print(locale.getpreferredencoding(False))
print(child.stderr.strip())
"""


def test_run_python_reads_korean_when_the_locale_is_not_utf8():
    # 실패하던 환경 흉내: 로캘 인코딩이 UTF-8 이 아니고(UTF-8 모드 꺼짐) PYTHONIOENCODING=utf-8 만 있는
    # 부모(run_python 이 넣음). 한국어 Windows 의 cp949 대신 CI(Linux)에도 있는 C 로캘(ASCII)을 쓴다.
    result = run_python(_PROBE, LC_ALL="C", LANG="C", PYTHONUTF8="0", PYTHONCOERCECLOCALE="0")
    assert result.returncode == 0, result.stderr
    encoding, *read = result.stdout.splitlines()
    if encoding.lower().replace("-", "") in ("utf8", "cp65001"):
        pytest.skip(f"로캘을 바꿔도 UTF-8 이라({encoding}) 흉내 낼 수 없는 환경")
    assert read == ["한글"]
