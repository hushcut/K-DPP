# K-DPP Backend

FastAPI 기반 백엔드입니다. 소재 혼용률을 받아 탄소배출량을 계산하고, 로그인 사용자의 분석 결과를 기록합니다. 로그인 토큰은 30일 동안 유효하며 로그아웃 시 서버와 앱에서 폐기됩니다.

## 주요 파일

```text
BACKEND/
  main.py              FastAPI 엔트리포인트
  database.py          SQLite/SQLAlchemy 모델과 스키마 준비
  init_data.py         소재 seed 데이터 삽입
  reset_db.py          로컬 DB 초기화 후 seed 재삽입
  API_CONTRACT.md      프론트/백엔드/API 협업 계약 문서
  requirements.txt     Python 의존성
  tests/               pytest 백엔드 테스트
```

## 처음 실행

Windows 기준입니다.

```bat
cd C:\DEV\K-DPP\BACKEND
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python init_data.py
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

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

로컬 SQLite DB를 삭제하고 테이블 생성 및 소재 seed를 다시 넣으려면:

```bat
cd C:\DEV\K-DPP\BACKEND
.venv\Scripts\activate.bat
python reset_db.py
```

서버 시작 시에도 `init_data.seed_materials()`가 실행되어 소재 seed는 보강됩니다. 다만 사용자, 토큰, 분석 기록까지 깨끗하게 지우려면 `reset_db.py`를 사용합니다.

## 테스트

테스트 도구는 `requirements.txt`에 포함되어 있습니다.

```bat
cd C:\DEV\K-DPP\BACKEND
.venv\Scripts\activate.bat
python -m pytest
```

테스트는 실제 `k_dpp.db` 대신 테스트용 SQLite DB를 잠깐 만들고 삭제합니다.

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

## 환경 파일

필요하면 `.env.example`을 참고해 로컬 전용 `.env`를 만들 수 있습니다.

```bat
copy .env.example .env
```

현재 코드는 `.env` 파일 없이도 실행됩니다. `BACKEND/.env`의 `K_DPP_DATABASE_URL` 또는 운영체제 환경변수를 지정하면 기본 `BACKEND/k_dpp.db` 대신 다른 SQLite DB를 사용할 수 있습니다.

## Git에 올리지 않는 파일

다음 파일은 로컬 환경, 인증 정보, 생성 산출물이므로 커밋하지 않습니다.

```text
BACKEND/.venv/
BACKEND/k_dpp.db
BACKEND/.pytest_k_dpp.db
BACKEND/*.db-journal
BACKEND/*.db-wal
BACKEND/*.db-shm
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
