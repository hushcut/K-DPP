# K-DPP OCR 실험 작업 안내 (Codex·Claude 공통)

이 저장소 폴더(`C:\K-DPP-OCR`, 브랜치 `kyh/new-ocr`)는 무료 OCR(PaddleOCR·EasyOCR)과 Google Vision을 비교하는 실험 전용이다. 한국어 존댓말로 결론부터 짧게 답한다.

## 작업 위치
- 이 폴더를 그대로 열어 작업한다. **Codex worktree(별도 작업 폴더)를 새로 만들지 않는다.** 팀 보안 훅(`scripts/security/check_secrets.py`)이 git worktree 안에서는 저장소 위치를 잘못 계산해 커밋·푸시를 막는다.
- 원격은 GitHub `origin/kyh/new-ocr`다. 작업 전 `git status --short --branch`, `git log -1`로 원격과 같은지 확인한다.
- 이 브랜치의 `AI/`·`BACKEND/`·`FRONTEND/`는 승우 브랜치(`ksw/paddleocr`) 시점의 예전 코드다. 최신 서비스 코드가 아니므로 수정하지 않는다.
- 최신 서비스 코드와 정답·Vision 캐시는 `C:\K-DPP-AI`(`kyh/ai`)에 있다. 그 폴더는 **읽기 전용**으로만 쓰고 브랜치를 바꾸지 않는다.

## 실험 폴더
| 폴더 | 내용 |
|---|---|
| `experiments/paddleocr/` | PaddleOCR 실행(`scripts/04_read_one_image.py`), 승우 인계 기록(`README.md`) |
| `experiments/easyocr/` | EasyOCR 실행(`scripts/read_one_image.py`) |
| `experiments/ocr_compare/` | 서비스 파서 비교(`scripts/parser_compare.py`), **결과 정리 문서 `OCR_엔진_비교_결과_20261025.md`** |

- 각 폴더의 `venv`(Python 3.11.9)를 쓴다. 버전은 `requirements-yohan-cpu.txt`·`versions_pip_freeze.txt`에 고정돼 있으며 확인 없이 올리지 않는다.
- PowerShell에서 `$env:PYTHONIOENCODING='utf-8'`을 먼저 설정한다. pip 설치 때는 `$env:PYTHONUTF8=1`도 설정한다. Paddle은 한글 경로의 모델을 못 읽으므로 이 폴더처럼 영문 경로를 유지한다.
- 결과는 항상 새 결과 폴더에 쓴다. 기존 결과 폴더를 덮어쓰거나 지우지 않는다.

## 데이터와 비용
- 사진, 잘린 줄 이미지, OCR 원문·캐시, 정답 내용, 모델, 결과, 가상환경은 git에 올리지 않는다(`.gitignore`·`GIT_SECURITY.md`).
- 정답(줄 글자·조성)은 사진에 적힌 그대로 쓴다. 같은 옷의 사진·변형은 학습/평가 한쪽에만 둔다. 승우 인계의 데이터 원칙을 따른다.
- **Google Vision을 새로 호출하면 비용이 생길 수 있다.** 사용자 확인 없이 호출하지 않고, 서비스 OCR 캐시를 먼저 쓴다.

## Git
- 커밋·푸시는 사용자가 요청할 때만 한다. 이번 작업 파일만 경로를 지정해 스테이징하고 메시지는 한국어로 쓴다(예: `실험: ...`).
- `GIT_SECURITY.md`를 따른다. `--no-verify`, `git add -f` 등 보안 검사 우회를 하지 않는다. 새 clone에서는 `python scripts/security/setup.py`를 한 번 실행한다.
- 커밋에 AI 공동작성자 줄을 넣지 않는다.
