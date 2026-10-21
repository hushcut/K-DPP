#!/bin/sh
# Called by Git's installed pre-commit/pre-push hooks; no network access here.
root=$(git rev-parse --show-toplevel) || exit 2
export PYTHONDONTWRITEBYTECODE=1
export PYTHONIOENCODING=utf-8
if [ -x "$root/AI/kdpp_ai_ocr_integrated/.venv/Scripts/python.exe" ]; then
    python="$root/AI/kdpp_ai_ocr_integrated/.venv/Scripts/python.exe"
elif [ -x "$root/AI/kdpp_ai_ocr_integrated/.venv/bin/python" ]; then
    python="$root/AI/kdpp_ai_ocr_integrated/.venv/bin/python"
elif command -v python >/dev/null 2>&1; then
    python=python
elif command -v python3 >/dev/null 2>&1; then
    python=python3
else
    echo 'K-DPP: Python 3.11 이상이 없어 보안 검사를 실행하지 못했습니다.' >&2
    exit 2
fi
exec "$python" "$root/scripts/security/check_secrets.py" "$@"
