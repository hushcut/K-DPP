# K-DPP

AI 기반 의류 수명 예측 및 탄소 발자국 추적 앱.

의류 케어 라벨을 촬영하면 소재 혼용률을 읽어내고, 소재별 탄소배출계수와 의류 무게를
근거로 **원료·소재 생산 단계의 탄소배출량을 추정**합니다. 추정 결과는 디지털 제품 여권(DPP)
형태의 상세 리포트로 제공되며, 등록한 옷들은 옷장에 모여 전체 탄소 현황으로 집계됩니다.

> **DPP(Digital Product Passport)** — 제품의 소재·관리 정보·환경 영향을 하나의
> 이력으로 관리하는 개념입니다.

---

## 개발 전 필수 보안 설정

이 저장소에 **커밋·푸시하는 모든 팀원**은 새 clone·새 PC마다 아래 설정을 한 번 진행합니다.
사용할 브랜치에 `scripts/security/`·`.githooks/` 등 공통 보안 구성이 반영된 최신 코드를 받은 뒤,
**저장소 루트**에서 Python 3.11 이상으로 실행합니다. Git과 설치 시 인터넷 연결이 필요합니다.

```sh
python scripts/security/setup.py
```

설치기는 Gitleaks를 내려받아 고정된 해시·버전을 확인하고, 커밋·푸시 전 검사 훅을 설치합니다.
`pre-commit·pre-push 보안 훅을 설치했습니다.` 메시지가 나오면 설치가 완료된 것입니다.
이후 같은 작업 폴더에서는 새 세션에서도 자동 검사하며, 비밀정보나 게시 금지 자료가 탐지되면
커밋·푸시를 중단합니다. 기존 훅과 충돌해 설치가 중단되면 원인을 확인하고 검사를 우회하지 않습니다.

**코드를 내려받는 것만으로 각 PC의 로컬 훅이 설치되지는 않습니다.** 훅 설치 후 공통 보안 구성이
없는 브랜치로 전환하면 커밋·푸시도 중단되므로, 해당 브랜치에 공통 보안 구성을 먼저 반영합니다.
GitHub 보안 CI는 설정이 반영된 브랜치에서 **업로드 후** 실행됩니다.

자세한 설치·검사 범위는 [Git 업로드 보안 규칙](GIT_SECURITY.md#8-자동-검사-운영2026-10-15-작업본),
게시 후 결과는 [보안 CI 실행 내역](https://github.com/hushcut/K-DPP/actions/workflows/secret-scan.yml)에서 확인합니다.

## 저장소 구성

4개 파트가 한 저장소에 모인 모노레포입니다. 각 폴더에 자체 README가 있습니다.

| 폴더 | 내용 | 문서 |
| --- | --- | --- |
| `FRONTEND/` | Flutter 앱 (Android·iOS) | [README](FRONTEND/README.md) |
| `BACKEND/` | FastAPI 서버 + PostgreSQL | [README](BACKEND/README.md) · [API 계약](BACKEND/API_CONTRACT.md) |
| `AI/` | OCR 소재·혼용률 분석 모듈 | [README](AI/kdpp_ai_ocr_integrated/README.md) |
| `QA/` | 라벨 데이터셋 배치 검증 도구 | [README](QA/README.md) |
| `deploy/` | 배포 묶음 — 앱 + PostgreSQL + Caddy(HTTPS) Docker Compose | [README](deploy/README.md) |
| `docs/` | 파트 간 협업 문서 | [스캔 API 계약](docs/SCAN_API_CONTRACT.md) |

키·자격증명·로컬 데이터의 업로드 금지 기준과 브랜치별 보완 항목은 [Git 업로드 보안 규칙](GIT_SECURITY.md)을 따릅니다. 규칙 문서와 실제 자동 차단 설정의 완료 여부는 구분합니다.

## 기술 스택

| 파트 | 스택 |
| --- | --- |
| 프론트엔드 | Flutter (Dart SDK `^3.11.3`) |
| 백엔드 | FastAPI · SQLAlchemy · PostgreSQL 18 · Alembic (Python 3.10+, 3.12 검증) |
| AI | Google Cloud Vision OCR · 소재/혼용률 파서 |
| CI | GitHub Actions ([ci.yml](.github/workflows/ci.yml)) |

---

## 빠르게 실행하기

### 1. 백엔드

```bash
cd BACKEND
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
docker compose up -d --wait
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

DB 는 Docker Desktop 으로 띄우는 로컬 PostgreSQL 입니다. 자세한 것은 [BACKEND/README.md](BACKEND/README.md).

API 문서는 `http://127.0.0.1:8000/docs` 에서 확인합니다.

### 2. 프론트엔드

```bash
cd FRONTEND
flutter pub get
flutter run
```

Android Emulator는 `http://10.0.2.2:8000`, iOS Simulator는 `http://127.0.0.1:8000`이
기본값으로 적용됩니다.

### 3. 실기기(USB)로 실행할 때

`adb reverse`로 기기의 8000 포트를 PC로 넘긴 뒤, 기기 기준 주소를 주입합니다.

```bash
adb reverse tcp:8000 tcp:8000
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

`API_BASE_URL` 하나만 넘기면 스캔·탄소 계산·소재 카탈로그 주소가 모두 파생됩니다
(`FRONTEND/lib/config/api_environment.dart`). 개별 주소를 덮어쓰려면
`SCAN_API_ENDPOINT`, `CARBON_API_ENDPOINT`, `MATERIALS_API_ENDPOINT`를 쓸 수 있습니다.

> **문제 해결** — 로그인이 15초쯤 멈췄다가 실패한다면 대개 `adb reverse` 터널이 끊긴
> 경우입니다. adb 데몬이 재시작되면 터널도 함께 사라집니다.
> `adb shell curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/materials`
> 로 기기에서 서버에 닿는지 먼저 확인하세요.

---

## 현재 상태

**OCR은 보류 중입니다.** Google Cloud Vision 연결이 끊겨 있어 `POST /api/scan`이
`502 OCR_FAILED`를 반환하고, 앱은 **소재 직접 입력 흐름으로 폴백**합니다. 이 폴백 경로는
정상 동작하므로 스캔 이후의 계산·저장·리포트는 그대로 확인할 수 있습니다.
자격 증명을 다시 연결하면 자동 인식이 즉시 복구됩니다.

## 테스트

```bash
cd FRONTEND && flutter analyze && flutter test
cd BACKEND && docker compose up -d --wait && .venv/Scripts/python.exe -m pytest
```

백엔드 테스트는 로컬 PostgreSQL의 테스트 전용 DB(`k_dpp_test`)를 씁니다. 준비와 다른 DB를
가리키는 법은 [BACKEND/README.md](BACKEND/README.md)의 '테스트' 절에 있습니다.

CI는 push·PR마다 세 잡을 실행합니다 — 프론트엔드 분석·테스트, 백엔드 pytest(PostgreSQL
서비스 포함), 배포 이미지 빌드. `continue-on-error`는 쓰지 않아 하나라도 실패하면 CI가
실패로 표시됩니다. 백엔드 잡은 `BACKEND` 폴더가 없으면 건너뛰지 않고 실패합니다.

---

## 브랜치 전략

| 브랜치 | 역할 |
| --- | --- |
| `main` | 릴리스·시연 기준점 |
| `develop` | 통합 기준 브랜치 |
| `<이름>/<작업명>` | 작업 단위 브랜치 (예: `jw/scan-contract-docs`) |

- 브랜치는 **레이어(프론트/백엔드)가 아니라 작업 단위**로 나눕니다. API 계약 변경처럼
  양쪽을 함께 고쳐야 하는 작업은 한 브랜치에서 다룹니다. 반쪽만 머지되면 기능이
  불완전해지기 때문입니다.
- `develop` 통합은 **PR 기반**으로만 합니다. 수동 파일 복사는 하지 않습니다.
- `main` 최신화는 팀 합의 시점에 진행합니다.

## 라이선스

[MIT](LICENSE)
