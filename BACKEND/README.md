# K-DPP Backend

FastAPI 기반 백엔드입니다. 라벨 OCR로 소재 혼용률을 추출하고, 사용자가 선택한 의류 무게 범위와 DB 소재 계수를 기준으로 탄소배출량을 계산합니다. 로그인 사용자의 최종 계산 결과는 분석 이력에 기록됩니다.

## 주요 파일

```text
BACKEND/
  main.py              FastAPI 엔트리포인트
  database.py          SQLAlchemy 모델·DB 연결(PostgreSQL), 서버 시작 때 스키마 확인
  init_data.py         소재 표의 기대값(MATERIAL_SEEDS) — DB 에는 마이그레이션이 넣음
  API_CONTRACT.md      프론트/백엔드/API 협업 계약 문서
  requirements.txt     Python 의존성
  alembic.ini          Alembic 설정(DB 주소는 넣지 않음)
  migrations/          Alembic 리비전(스키마·소재 시드)
  compose.yaml         로컬 개발용 PostgreSQL(Docker Compose)
  docker/              PostgreSQL 첫 실행 때 테스트 DB를 만드는 스크립트
  tests/               pytest 백엔드 테스트
```

## 처음 실행

Windows 기준입니다. DB 는 PostgreSQL 이고, 로컬에서는 Docker Desktop 으로 띄웁니다.

**Python 3.10 이상이 필요합니다.** requirements.txt의 고정 버전들이 3.9 이하에서는
설치되지 않습니다(3.12에서 동작 확인). 여러 버전이 설치돼 있다면 `py -3.12 -m venv .venv`처럼
버전을 지정해 주세요.

**Docker Desktop 을 처음 설치한다면** 그 전에 두 가지가 켜져 있어야 합니다.

- BIOS(UEFI)의 가상화(Intel VT-x·AMD SVM). 작업 관리자 → 성능 → CPU 의 '가상화' 가 '사용' 이면 켜져 있습니다.
- WSL. 관리자 권한 터미널에서 `wsl --install --no-distribution` 을 실행하고 재부팅합니다.

사용자 계정에만 설치하면 `docker` 는 `%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin` 에 들어갑니다.
설치 전에 열어 둔 터미널은 `docker` 를 찾지 못하니 새로 여세요.

```bat
cd C:\DEV\K-DPP\BACKEND
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
docker compose up -d --wait
alembic upgrade head
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- `docker compose up -d --wait`: 로컬 PostgreSQL(`compose.yaml`)을 띄웁니다. 처음 한 번은 이미지를 받습니다.
- `alembic upgrade head`: 표를 만들고 소재 시드를 넣습니다. 코드를 받은 뒤 새 리비전이 있으면 다시 실행합니다.
  빼먹고 서버를 켜면 "DB 스키마가 최신이 아닙니다" 로 시작하지 않습니다.
- 주소를 따로 주지 않으면 `postgresql+psycopg://kdpp:kdpp@127.0.0.1:5432/k_dpp`(compose 의 개발용 DB)를 씁니다.

PowerShell에서 가상환경 활성화가 막히면 다음처럼 가상환경 Python을 직접 실행해도 됩니다.

```powershell
cd C:\DEV\K-DPP\BACKEND
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

서버 문서는 브라우저에서 확인합니다.

```text
http://127.0.0.1:8000/docs
```

Android Emulator의 Flutter 앱에서 백엔드를 호출할 때는 다음 주소를 사용합니다.

```text
http://10.0.2.2:8000
```

## DB 초기화

로컬 DB의 사용자·토큰·분석 기록을 모두 지우고 처음 상태(표 + 소재 시드)로 되돌리려면 볼륨째 지우고 다시 만듭니다.
**되돌릴 수 없습니다.** 배포 서버에서는 하지 마세요.

```bat
cd C:\DEV\K-DPP\BACKEND
docker compose down -v
docker compose up -d --wait
alembic upgrade head
```

서버는 소재를 넣거나 덮어쓰지 않습니다. 소재·계수는 마이그레이션으로만 바뀝니다(아래 'DB 마이그레이션').

## 테스트

테스트 도구는 `requirements.txt`에 포함되어 있습니다. 테스트는 **로컬 PostgreSQL**의
테스트 전용 DB(`k_dpp_test`)를 씁니다. 먼저 Docker Desktop을 설치하고 PostgreSQL을 띄웁니다.

```bat
cd C:\DEV\K-DPP\BACKEND
docker compose up -d --wait
.venv\Scripts\activate.bat
python -m pytest
```

- `docker compose up -d --wait` 는 PostgreSQL이 접속을 받을 때까지 기다립니다. 처음 한 번은 이미지를 받느라 시간이 걸립니다.
  `k_dpp_test` DB는 볼륨을 처음 만들 때 `docker/postgres-init/`이 만듭니다.
- 테스트를 시작할 때 `k_dpp_test`를 비우고 `alembic upgrade head`로 표·소재를 만듭니다(배포와 같은 길). 테스트마다 사용자·토큰·분석 기록 표만 비웁니다.
  실제 DB를 지우지 않도록 DB 이름이 `_test`로 끝나지 않으면 시작하지 않습니다.
- 다른 주소의 PostgreSQL을 쓰려면 환경변수 `K_DPP_TEST_DATABASE_URL`을 지정합니다(기본값 `postgresql+psycopg://kdpp:kdpp@127.0.0.1:5432/k_dpp_test`).
  Docker가 무거우면 PostgreSQL 설치판에 `k_dpp_test` DB를 만들고 이 값으로 가리켜도 됩니다.
- 다 쓰면 `docker compose down`(데이터 유지) 또는 `docker compose down -v`(데이터까지 삭제).

현재 테스트 범위:

- cotton 80 + polyester 20 계산 성공
- 없는 소재 입력 시 400 반환
- 비율 합계가 100이 아닐 때 400 반환
- 회원가입 성공
- 중복 이메일 회원가입 실패
- 로그인 성공
- 비밀번호 틀림 실패
- 소재 목록 조회 성공
- 로그인 사용자의 분석 결과가 `/me/history`에 연결되는지 확인
- 토큰 없이 `/me/history` 호출 시 401 반환
- 토큰 없이 `/history` 호출 시 401 반환
- 로그아웃 및 만료 토큰 재사용 차단
- DB 소재 계수와 의류 무게 범위를 사용한 최소·최대 탄소배출량 계산
- 최종 계산 결과의 사용자 분석 이력 저장
- 마이그레이션: head 스키마 = 모델, 소재 시드 = `MATERIAL_SEEDS`, 되돌렸다 다시 올리기(`tests/test_migrations.py`)

## DB 마이그레이션 (Alembic)

PostgreSQL 스키마와 소재 시드는 `migrations/`의 Alembic 리비전으로 관리합니다. DB 주소는 앱과 같은
`K_DPP_DATABASE_URL`(환경변수 또는 `BACKEND/.env`)을 쓰며, PostgreSQL이 아니면 실행하지 않습니다.
주소를 주지 않으면 로컬 개발용 DB(`compose.yaml`의 `k_dpp`)를 씁니다.

```bat
cd C:\DEV\K-DPP\BACKEND
.venv\Scripts\activate.bat
alembic upgrade head
```

- 리비전: `98b9938f3cd5` 기준선(develop 표 4개) → `09f14728ed0b` 소재 시드 22종.
- 모델(`database.py`)을 바꾸면 `alembic revision --autogenerate -m "설명"`으로 리비전을 만들고 **내용을 꼭 손으로 검토**합니다.
  `alembic check`가 `No new upgrade operations detected.`면 모델과 리비전이 맞습니다.
- 소재·계수를 바꿀 때는 `init_data.py`의 `MATERIAL_SEEDS`(프런트 사본 두 파일도 함께)를 고치고, 같은 변경을 하는 새 리비전(UPDATE·INSERT)을 더합니다.
  리비전은 목록을 import 하지 않고 값을 직접 적습니다. 둘이 어긋나면 `tests/test_migrations.py`가 실패합니다.
- 서버는 표를 만들거나 바꾸지 않습니다. 시작할 때 DB 가 최신 리비전인지 확인만 하고, 아니면 멈춥니다.
- 배포 서버도 같습니다: 새 코드를 올리면 서버를 켜기 전에 `alembic upgrade head`.

## 계산 흐름

```text
POST /api/scan
  라벨 이미지 -> OCR -> 소재/혼용률

POST /api/carbon/calculate
  소재/혼용률 + 최소/최대 무게 -> DB 계수 계산 -> 사용자 이력 저장
```

**최종** 탄소배출량은 백엔드 응답만 사용합니다. 다만 프런트엔드는 저장 **전** 프리뷰와
옷장에 저장되는 건강도를 서버 왕복 없이 계산하므로, 이 표의 사본을 **두 파일**에 갖고 있습니다.

| 프런트엔드 파일 | 사본 |
| --- | --- |
| `FRONTEND/lib/utils/material_name.dart` | 한글명·별칭 → 영문 표준명 |
| `FRONTEND/lib/utils/clothing_estimator.dart` | 영문 표준명 → `carbon_factor` |

`init_data.py`의 `MATERIAL_SEEDS`를 고칠 때는 **두 파일을 함께** 갱신해야 합니다.
어긋나면 `tests/test_material_name_contract.py`가 실패합니다.

## 환경 파일

필요하면 `.env.example`을 참고해 로컬 전용 `.env`를 만들 수 있습니다.

```bat
copy .env.example .env
```

현재 코드는 `.env` 파일 없이도 실행됩니다. 이때 DB 는 로컬 PostgreSQL(`compose.yaml`) `postgresql+psycopg://kdpp:kdpp@127.0.0.1:5432/k_dpp` 입니다.
`BACKEND/.env`의 `K_DPP_DATABASE_URL` 또는 운영체제 환경변수로 다른 PostgreSQL을 가리킬 수 있습니다(SQLite는 더 지원하지 않습니다).

## Git에 올리지 않는 파일

다음 파일은 로컬 환경, 인증 정보, 생성 산출물이므로 커밋하지 않습니다.

```text
BACKEND/.venv/
BACKEND/k_dpp.db   (예전 SQLite 파일 — 지금은 쓰지 않음)
BACKEND/__pycache__/
BACKEND/.env
AI/**/key.json
*.log
```

실제 Google Vision 인증키는 `AI/kdpp_ai_ocr_integrated/key.json` 위치에 둘 수 있지만, `key.json`은 절대 GitHub에 올리지 않습니다.

## API 문서

협업용 요청/응답 예시는 다음 문서를 기준으로 맞춥니다.

```text
BACKEND/API_CONTRACT.md
```
