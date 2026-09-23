# K-DPP 공통 작업 지침

Codex와 Claude가 공유하는 프로젝트 규칙이다. 현재 커밋·검증 결과·다음 작업은 `docs/HANDOFF.md` 한 곳에 기록한다.

## 시작과 범위

- 시작할 때 `git status --short --branch`와 `git log -1`을 읽고 `docs/HANDOFF.md`의 기준점과 대조한다. 차이가 있으면 현재 저장소를 우선하고 사용자에게 알린다.
- 사용자가 지정한 영역만 수정한다. 다른 영역은 연동 확인에 필요한 범위에서 읽고, 영역을 넘는 수정이 필요하면 이유와 영향을 먼저 설명한다.
- 사용자의 기존 변경은 내 작업으로 간주하지 않는다. 충돌 표시가 범위 밖에 있으면 상태만 보고한다.

## 프로젝트 지도

- `AI/kdpp_ai_ocr_integrated/`: Google Vision 텍스트 OCR, 소재·혼용률 파서. 의존성 선언은 `requirements*.txt`, 실제 설치는 용도별 `requirements-*.lock`을 사용한다. 자세한 파일·QA 절차는 해당 `README.md`.
- `BACKEND/`: FastAPI, 인증, SQLite. `/api/scan`은 OCR·소재 결과를 반환하고 별도 `/api/carbon/calculate`가 탄소 계산·이력을 처리한다. 실행은 `BACKEND/README.md`, 응답 계약은 `BACKEND/API_CONTRACT.md`.
- `FRONTEND/`: Flutter 앱. 실행·API 주소는 `FRONTEND/README.md`.
- `QA/`: 실행 중인 백엔드 `/api/scan` 통합 배치 검사. AI의 OCR·파서 단위 QA와 측정 범위가 다르다.
- `apps/symbol/`은 잘라낸 단일 세탁기호 이미지용 실험 경로다. 전체 라벨 기호 위치 검출도 기본 제품 연결도 없다. 심볼 API는 `KDPP_ENABLE_SYMBOL_API=1`에서만 활성화한다.

## 검증과 안전

- AI 기본 검사는 `AI/kdpp_ai_ocr_integrated`에서 `.venv\Scripts\python.exe -m ruff check .`와 `.venv\Scripts\python.exe -m pytest -q`로 실행한다. 관련 테스트부터 확인한다.
- 전체 pytest는 `tests/test_backend_ai_wiring.py` 수집 중 백엔드를 import한다. `BACKEND/database.py` import는 로컬 SQLite 스키마를 변경할 수 있으므로 실행 전 `docs/CODEX_SAFETY.md`를 읽는다.
- 프론트엔드 변경은 `FRONTEND`에서 `flutter analyze`와 `flutter test`로 확인한다. 실제로 실행하지 않은 검증을 통과했다고 보고하지 않는다.
- AI 단위 QA(기본 ±3%p), 백엔드 통합 QA(기본 ±5%p), 합성 원문 파서 평가는 별도로 기록한다. 합성 점수와 저장된 OCR 캐시 결과를 최신 실사진 Vision 정확도로 표현하지 않는다.
- 서버 시작·종료, Google Vision 실호출·OCR 캐시 갱신, 모델 학습·평가는 요청받은 범위에서만 한다. 파서만 점검하면 저장된 캐시와 `--offline`을 사용한다.
- `BACKEND/k_dpp.db`, AI의 `data/`·`models/`·`outputs/`, 루트 `QA_DATASET/`은 로컬 상태다. 임의로 삭제·초기화·덮어쓰기·커밋하지 않는다. 자격증명 내용·절대 경로와 원시 내부 예외를 출력·문서화·서비스 응답에 노출하지 않는다.

## Git과 문서

- 커밋·푸시·브랜치 변경은 사용자가 명시적으로 요청한 경우에만 한다. 커밋 시 이번 작업 파일만 경로를 지정해 스테이징하고 제목·본문은 한국어로 쓴다.
- `docs/HANDOFF.md`는 공통 현재 상태만 120줄 안에 유지한다. 새 작업·세션 인계 시 실제 Git 상태와 검증 결과를 확인해 갱신하고, 압축 후 요약을 근거로 썼으면 표시한다. 인계 갱신은 커밋·푸시 권한을 포함하지 않는다.
- `docs/CODEX_SAFETY.md`는 부작용이 있는 실행·쓰기의 상세 규칙, `docs/DECISIONS.md`는 오래 유지할 정책이다. 영역별 README와 API 계약은 필요한 작업에서 읽는다.
