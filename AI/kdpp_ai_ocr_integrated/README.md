# K-DPP AI OCR 통합 모듈

K-DPP의 OCR 소재·혼용률 분석과 텍스트 관리 지침 파싱을 제공하는 AI 모듈입니다.

## 2026-10-02 AI 통합 기준

`ai-integration`의 기존 앱 코드를 기준으로 팀원 `kyh/ai`의 OCR·파서 구조와
사용자 `ksw/ai-ocr-enhancement`의 소재 안전 규칙·백엔드 검증을 결합했습니다.
프런트엔드, 탄소 계산, DB 구조 및 원래 개인 브랜치는 통합 범위에 포함하지
않습니다. 원본 커밋은 각각 `947c5f7`, `38537b0`, 파일럿은 `1974920`입니다.

- OCR 원문·배치·전처리 후보의 충돌 및 미연결 비율을 `/api/scan`까지 전달합니다.
  소재를 확정할 수 없으면 422로 반환하며, 성공 응답은 근거가 확인되고
  소재 비율 합계가 **정확히 100%**인 경우에만 제공합니다. 합계를 보정하지
  않습니다. 이 기준은 QA 결과 비교의 허용 오차와 별개입니다.
- 앱의 OCR 설정·한도 오류는 502, 시간 초과는 504, 일시 서비스 장애는 503입니다.
- 사용자 회귀 사례와 팀원 OCR 후보·서비스 테스트를 함께 유지합니다.
  생성 데이터의 정답 문구 검사와 실제 이미지 OCR 정확도는 별도 평가입니다.
- 추가 반사·노이즈·회전 보정 옵션은 기존 기본값인 **꺼짐**을 유지합니다.
  과거 실사진 보고서의 특정 옵션 결과를 기본 설정의 정확도로 사용하지 않습니다.
- 사용자 파일럿 v1.0.3 생성기는 `apps/synthetic/pilot_v1_0_3.py`와
  `configs/pilot_v1_0_3/`에 별도 보존합니다. 기존 이미지 80장과 정답표를
  재생성하거나 덮어쓰지 않습니다. 해당 폴더의 README에 실행 방법이 있습니다.
- `/api/scan` 배치 QA의 인증 방법은 `../../QA/README.md`를 참고합니다.
  서비스 계정, 로그인 토큰, 이미지·OCR 캐시·학습 모델은 Git에 포함하지 않습니다.

기존 보고서와 날짜별 결과는 당시 코드·옵션의 기록입니다. 통합된 코드의 실사진
성능은 같은 정답지·OCR 캐시 또는 별도의 실제 OCR 평가로 다시 확인해야 합니다.

## 팀 공통 규칙

- 의존성 선언은 `requirements*.txt`, 실제 설치는 실행 범위에 맞는
  `requirements-*.lock`을 사용합니다. 개발 가상환경은 `.venv`입니다.
- 코드 변경 후에는 Ruff와 pytest를 모두 통과해야 합니다.
- AI·BACKEND·QA 변경을 푸시하거나 풀 리퀘스트를 만들면 GitHub Actions가 AI Ruff와 전체 pytest를 실행합니다.
- 서비스 계정 JSON, 실제 데이터셋, 모델, OCR 캐시·출력물은 커밋하지 않습니다.
- `ruff check --fix`나 `ruff format`으로 기존 코드를 일괄 변경하지 않습니다. 검사
  결과를 검토해 필요한 변경만 적용합니다.
- Python 3.12 환경은 텍스트 OCR·개발/CI 잠금 파일에서 필요한 설치 범위를 선택합니다.

## 현재 서비스 범위

현재 DPP 서비스 흐름에서 사용하는 기능은 의류 라벨의 **소재명과 혼용률
추출**입니다.

```text
라벨 이미지 -> Google Vision OCR -> 소재/혼용률 파서 -> 소재 분석 결과
```

## 폴더 구조

```text
kdpp_ai_ocr_integrated/
  apps/
    service/                 # FastAPI 서비스 경계와 응답 형식
    text/                    # 이미지 검증, OCR, 소재/혼용률 파싱, OCR QA 계약
  scripts/
    audit_ocr_qa_dataset.py   # OCR QA 정답지 품질 감사
    run_ai_checks.py         # 문법, 테스트, 데이터 검사 실행 도구
    run_combined_batch.py    # 이미지 폴더 일괄 분석 도구
    run_qa_batch.py          # OCR/파서 단위 QA 도구
  outputs/                   # QA·평가 결과와 OCR 캐시 위치, Git 추적 제외
```

## 설치와 로컬 검증

아래 명령은 **Windows PowerShell** 기준입니다. 저장소 루트에서 AI 폴더로 이동한 뒤
이 문서의 AI 명령을 실행합니다.

```powershell
Set-Location .\AI\kdpp_ai_ocr_integrated
```

Python 3.12 가상환경을 만든 뒤 용도에 맞는 잠금 파일 하나를 선택합니다. 자격증명 파일, 모델 가중치, 실제
데이터셋은 저장소에 포함하지 않습니다.

```powershell
py -3.12 -m venv .venv
```

개발·전체 테스트 환경을 설치하고 검사하려면 다음 명령을 사용합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ci.lock
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

텍스트 OCR과 소재 파서만 실행할 때는 기본 의존성을 설치합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-text.lock
```

### 의존성 잠금 정책

`requirements.txt`, `requirements-dev.txt`와
`BACKEND/requirements.txt`는 직접 의존성의 허용 범위를 정하는 입력입니다.
설치에는 Python 3.12 기준의 정확한 버전을 기록한 잠금 파일을 사용합니다.

- `requirements-text.lock`: 기본 OCR 서비스와 파서만 설치합니다.
- `requirements-ci.lock`: AI 개발·전체 테스트와 백엔드 의존성을 함께 설치합니다.

잠금 파일은 `uv==0.12.18`로 Windows와 Linux에 공통인 버전을 해석해 생성했습니다.
직접 의존성이나 백엔드 요구사항을 바꾸면 해당 잠금 파일을 다시 만들고 함께 검증합니다.
기존 잠금 파일을 출력 대상으로 쓰면 기존 버전을 유지하며, 의도적으로 올릴 때만
`--upgrade-package`를 지정합니다. 잠금 파일을 손으로 고치지 않습니다.

```powershell
.\.venv\Scripts\python.exe -m pip install uv==0.12.18
.\.venv\Scripts\uv.exe pip compile requirements.txt --universal --python-version 3.12 --no-header --no-annotate -o requirements-text.lock
.\.venv\Scripts\uv.exe pip compile requirements-dev.txt ..\..\BACKEND\requirements.txt --universal --python-version 3.12 --no-header --no-annotate -o requirements-ci.lock
```

CI는 두 잠금 파일이 입력 요구사항과 맞는지 검사하고 `requirements-ci.lock`으로
설치합니다. 잠금 파일은 패키지 **버전**을 고정하며 배포 파일 해시까지 고정하지는 않습니다.

### 텍스트 OCR 운영 번들

운영 배포물은 저장소 전체를 복사하지 않고 명시된 텍스트 서비스 파일만 구성합니다.

```powershell
.\.venv\Scripts\python.exe -m scripts.build_text_runtime --output dist\text-runtime
```

생성된 `dist/text-runtime`에는 텍스트 OCR 서비스, 기본 `requirements.txt`와
`requirements-text.lock`이 포함됩니다. 배포 환경은 잠금 파일로 의존성을 설치합니다.
합성 데이터 생성, QA 스크립트, 테스트, 데이터셋과 출력물은
포함되지 않습니다. 배포 환경에서는 번들 디렉터리에서 다음 진입점을 사용합니다.

```powershell
python -m apps.service
```

pytest에는 `/api/scan`의 AI 연결 검사도 포함되므로, 전체 검증에는 백엔드 의존성이
필요합니다. 연결 검사는 테스트 수집 단계에서 백엔드를 import하지 않고, 실행 시 임시
SQLite DB를 설정한 뒤 불러옵니다. `raw_ocr_text`와 모의 OCR로 현재 스캔 응답·업로드
검증·파싱 실패를 확인하며, Google Vision 실호출이나 사용자 DB 저장을 하지 않습니다.

`GOOGLE_APPLICATION_CREDENTIALS` 또는 `--credentials`에 지정하는 Google Vision
서비스 계정 JSON은 개인 로컬 경로에서만 사용해야 하며, 저장소에 추가하면 안 됩니다.

## AI HTTP 서비스 실행

AI 폴더에서 다음 명령으로 실행합니다. 이미지 OCR은 실행 환경의
`GOOGLE_APPLICATION_CREDENTIALS`에 유효한 서비스 계정 JSON이 설정되어 있어야 합니다.
텍스트 파싱 API는 Google Vision을 호출하지 않습니다.

```powershell
.\.venv\Scripts\python.exe -m apps.service
```

기본 주소는 `http://127.0.0.1:8100`입니다. 호스트는 `KDPP_AI_HOST`, 포트는
`KDPP_AI_PORT`로 변경합니다. API 문서는 `/docs`, 스키마는 `/openapi.json`에서 확인합니다.

| 메서드·경로 | 입력·역할 |
| --- | --- |
| `GET /health` | 서비스 상태와 API 버전 확인 |
| `POST /v1/parse-text` | JSON의 `text` 필드로 이미 추출한 텍스트 파싱 |
| `POST /v1/analyze-label` | multipart의 `file` 필드로 이미지 업로드·OCR·파싱 |

텍스트 파싱 요청 예시입니다.

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8100/v1/parse-text" -Method Post -ContentType "application/json" -Body '{"text":"COTTON 80% POLYESTER 20%"}'
```

백엔드 `/api/scan`은 포트 8000의 별도 경로이며 업로드 필드는 `image`입니다.
인증·탄소 계산·이력 저장은 [백엔드 API 계약](../../BACKEND/API_CONTRACT.md)을 따릅니다.

### 독립 AI 서비스의 요청 제한

전체 HTTP 본문은 **11MiB**, 이미지 파일 하나는 **10MiB**까지 허용합니다.
1MiB 차이는 multipart 경계·헤더·부가 필드용이며 이미지 파일 한도를 늘리지 않습니다.
두 POST API(`/v1/analyze-label`, `/v1/parse-text`)를 포함해 HTTP 요청 전체에 적용합니다.
크기 헤더가 상한을 넘으면 본문을 읽기 전에 413을 반환하고, 헤더가 없거나 작게
신고돼도 실제 수신량을 검사합니다. 전체 본문 검사가 끝나기 전에는 multipart 파서와
OCR을 실행하지 않으므로 파일 여러 개의 합산 크기도 제한됩니다.
잘못되거나 서로 충돌하는 `Content-Length`는 400 `invalid_request`, 크기 초과는
413 `payload_too_large`로 반환하며 같은 라벨 실패 응답 계약을 유지합니다.

본문은 상한 안에서 메모리에 버퍼링하고 1MiB 단위로 파서에 전달합니다. 마지막 청크를
전달하면 버퍼를 해제해 OCR 대기 동안 보유하지 않습니다. 이 제한은 요청 하나의 본문
상한이며 동시 요청 수·업로드 대기 시간·프로세스 전체 메모리 상한을 뜻하지 않습니다.
실배포의 프록시/ASGI 서버에도 업로드 크기와 수신 시간 제한을 설정해야 합니다.

## OCR 소재 분석

### 처리 방식

1. 업로드 이미지의 형식, 크기, 해상도를 먼저 검증합니다.
2. 원본 이미지를 Google Vision OCR로 읽습니다.
3. 원본 후보의 신뢰도가 부족하거나 최종 판단에 복원 가능한 누락이 남으면 방향·대비·선명도를 보정한 기본 후보를 추가로 OCR합니다.
4. 후보별 소재 구성, 혼용률 합계, 경고 수를 비교해 더 신뢰할 만한 결과를 선택합니다.
5. 최종 판단이 실패하면 관측된 단어 좌표로 소재 영역을 찾아 확대·회전 재인식을 시도합니다.
6. 파서는 소재명·혼용률·의류 부위·세탁 지침을 구조화된 응답으로 반환합니다.

원본 OCR 후보의 충돌·거절 근거까지 합친 최종 판단이 성공하고 신뢰도가 충분하면
전처리 OCR을 생략합니다. 불필요한 외부 API 호출 비용과 지연을 줄이기 위한 정책입니다.

일반 텍스트·좌표 재구성·전처리 후보가 같은 부위에 서로 다른 완성 조성을 제시하면
점수로 하나를 확정하지 않습니다. 후보 안에서 파서가 이미 확인한 조성 충돌도 유지하며,
`ocr.conflicting_parts`에 해당 부위를 기록합니다. 대표 부위가 충돌하면 소재 결과는
실패하고, 안감 등 하위 부위만 충돌하면 확인된 겉감은 유지하고 상충 부위의 값은 제외합니다.
기존 동등 섬유 규칙에 맞는 다국어 반복과, 실패 원본의 정상적인 배치 복구는 허용합니다.
`run_ocr_bytes()`·`run_ocr_with_metadata()`의 텍스트는 원문 확인용으로 보존하므로,
소재 판단에는 `analyze_ocr_result()`로 충돌 메타데이터까지 전달해야 합니다.

소재와 연결되지 않은 `%` 행은 `혼용률`, `COMPOSITION` 등의 제목이나 부위명이 붙어도
완성된 조성의 근거로 사용하지 않습니다. 세탁·제품 정보·홍보 문구는 구분합니다.
다른 후보에서 연결되지 않은 비율이 발견되면, 성공 후보가 그 값과 개수를 모두
유효한 조성에 연결한 경우에만 배치 복구로 인정합니다. 해소되지 않은 부위는
`ocr.unpaired_ratio_parts`에 기록하며 대표 소재를 확정하지 않습니다.
AI 서비스는 대표 부위의 후보 충돌을 422 실패 응답으로 반환합니다. 문자열 전용
`run_ocr()`도 `OcrCompositionError`로 자동 선택을 차단합니다. 백엔드 `/api/scan`은
이 오류도 소재 미확정으로 처리해 422를 반환합니다.

기본 실행은 원본·기본 전처리·소재 영역·소재 영역 회전까지 이미지당 최대 4개의 OCR 요청 후보를 사용합니다.
소재 영역은 `KDPP_ENABLE_MATERIAL_REGION_OCR=1`로 기본 활성화되며 `0`으로 끌 수 있습니다.
관측 소재명·비율 좌표 또는 같은 줄의 조성·혼용 제목으로 영역을 찾습니다.
소재명과 비율이 모두 누락돼도 확인된 제목 주변의 표를 재인식할 수 있지만, 제목만으로 소재를 확정하지 않습니다.
좌표 근거가 없거나 영역이 이미지 대부분을 차지하면 자르지 않습니다.
퍼센트 오독 시 등록 소재 두 개와 가까운 숫자 행으로 위치만 찾고, 그 숫자를 정답 비율로 승인하지 않습니다.
작은 글자는 안전한 크기 한도에서 확대하며 서로 다른 단어 상자의 일관된 각도가 있으면 회전합니다.
소재명이 누락됐을 때는 영역 안의 다른 글자 상자로 방향을 확인합니다.
첫 확대 후보는 유지하며, 두 번째 영역 회전 후보는 `adaptive_mild`로 대비를 보정합니다.
한글 소재가 실제로 읽힌 단일 조성에서 비율 합계 100%는 읽혔지만 일부 소재명이 누락된 경우에는 확대 뒤 `mild_contrast`를 우선합니다.
오독될 수 있는 제목의 철자나 사진 파일명으로 보정을 선택하지 않습니다.
그 외에는 불균일한 밝기·낮은 전체 대비에서 기존 `local_contrast` 입력을 유지하고, 나머지는 `mild_contrast`로 가는 획을 보존합니다.

실사진에서 확인한 폴리에스터 번역명 `POLIESTERE`, `POLYESTERI`, `POLIESTERIS`, `POLÜESTER`, `ПОЛИЭСТЕР`, `ΠΟΛΥΕΣΤΕΡΑΣ`는 완전한 단어만 인식합니다. 소재명과 비율 사이의 미등록 단어를 건너뛰어 조성을 확정하지 않습니다.

다국어 반복에서 완전한 주 조성이 읽히고 반복임을 확인하면, 읽히지 않은 번역명은 `unread_translation_rows` 경고로 남기고 그 조성을 사용합니다. `/`·`-`로 연결한 번역 묶음은 같은 소재의 등록 번역명 2개 이상과 명시 비율이 필요합니다. 언어 코드별 조성은 첫 조성이 완전하고, 합계 100%인 조성 2개 이상이 정확히 일치해야 합니다. 나머지 번역의 비율과 개수도 일치해야 하며, 다른 읽힌 소재·지원하지 않는 소재·추가 숫자·상충 비율·부위 경계를 감추지 않습니다. 완전히 읽힌 여러 번역 행의 근거와 OCR 원문 미리보기를 보존하고, 번역 누락이 있으면 파서 신뢰도를 `medium`으로 제한합니다. OCR 신뢰도는 `unknown`입니다.
세탁기호 숫자는 성공 후보에서 같은 사진·같은 위치의 세탁 온도로 확인되고 소재·비율 셀도 일치할 때만 제외합니다. 같은 OCR 응답의 언어 코드 배치 오류는 원문·좌표 후보의 모든 단어와 입력·영역이 같은 경우에만 복구합니다. 사진별 정답이나 파일명으로 판정을 바꾸지 않습니다.
2026-10-07 저장 OCR의 현재 자동 경로 재생은 소재·혼용률 완전일치 37→41/48(85.42%)이며 DJ017·DJ031·DJ044·DJ047이 복구됐습니다. 과거 수동 진단 후보 전체를 합산한 별도 평가는 38→41/48입니다. 두 평가는 실패 사진이 다르며 최신 전체 실사진 OCR 정확도가 아닙니다. 신규 Vision 호출·기존 캐시 갱신 없이 검증했으며 자세한 근거는 `outputs/dj_database_20261003_c907891/multilingual_five_20261007_v4/REPORT.md`에 기록했습니다.

별도 입력 비교용 `faint_print`는 원본 크기에서 글자 높이에 맞춘 가우시안 블렌드로 천 무늬를 줄인 뒤 배경 밝기·회색조 대비를 보정합니다. 중앙값 필터·이진화를 사용하지 않습니다. 2026-10-07 흐린 2장에 전체 소재 영역·수동 조성 행 영역을 각 1회씩 Google Vision으로 비교했지만 소재·비율 누락 및 오독이 남아 정답 복구는 0장이었습니다. 기본 자동 전처리에는 연결하지 않았으며, 불완전한 소재 결과는 기존 실패·직접 입력 흐름을 유지합니다. 결과는 `outputs/dj_database_20261003_c907891/faint_two_20261007_v4/REPORT.md`에 기록했습니다.
추가 요청 없이 기존 영역 회전 후보 자리를 사용하며, 포화되거나 지워진 획을 복원하는 기능은 아닙니다.
수동 비교용 `mild_denoise`는 약한 중앙값 필터를 섞어 무늬를 완화하며 자동 선택에는 포함하지 않습니다.
`prepare_material_region(..., enhancement=...)`에서 비교 모드를 지정할 수 있습니다. RGB 회전 모서리는 흰색이며 요청 횟수·좌표 변환 한도를 유지합니다.

기본 파서는 `POLY` 약어와 부위 없는 여러 조성을 자동 확정하지 않습니다.
해당 라벨을 실물·상품정보로 확인한 경우에만 `analyze_label_text(text, confirmed_polyester_poly=True)`로 독립 `POLY 100%` 또는 `100% POLY` 행을 폴리에스터로 해석합니다.
위 조성을 대표로 확인한 경우 `analyze_label_text(text, confirmed_first_generic=True)`를 사용할 수 있습니다.
첫 조성은 모든 소재·비율이 읽히고 합계가 정확히 100%여야 합니다. 명시 부위가 있으면 기존 부위 우선순위를 유지하며, 단독 추가 비율을 두 번째 조성으로 숨기지 않습니다.
아래 조성은 `generic_secondary`의 소재·비율·거절 근거로 남깁니다. 확인 옵션 사용은 경고에 표시하고 원문 미리보기를 보존합니다.
옵션은 기본 비활성인 사진별 텍스트 검토용이며 자동 OCR·HTTP 업로드 경로에는 전달하지 않습니다. OCR 신뢰도는 `unknown`이고, 확인 후 복구 점수는 자동 인식 점수와 따로 집계합니다.
소재·비율 개수만 맞는 다른 후보는 읽히지 않은 새 소재명을 제공할 수 없습니다. 소재명 복원은 원문과 독립 입력의 좌표 근거를 확인해야 합니다.
`candidate_count`는 같은 응답의 원문·좌표 복원 후보까지 포함하므로 OCR 요청 수와 다릅니다.
기본 전처리는 대비·선명화 결과를 JPEG 품질 92로 인코딩해 PNG 생성·전송 시간을 줄입니다.
후보 전체의 최종 판단이 실패하고 복원할 여지가 있으면 반사 보정·노이즈 완화·미세 회전을
추가하도록 설정할 수 있습니다. 개별 후보가 성공했더라도 소재·비율의 연결 누락이 남으면
다음 후보로 복원을 시도합니다. 이미 확인한 조성 충돌·미등록 소재·잘못된 수치의 근거는
다른 후보에서 해당 행이 사라졌다는 이유로 지우지 않습니다.
세 옵션의 기본값은 꺼짐이며, 소재 영역까지 함께 켜면 이미지당 최대 7개의 OCR 요청 후보를 순서대로 시도합니다.
후보 전체의 최종 안전 판단이 성공하면 추가 후보는 생략합니다.

```powershell
$env:KDPP_ENABLE_REFLECTION_OCR = "1"
$env:KDPP_ENABLE_DENOISED_OCR = "1"
$env:KDPP_ENABLE_ROTATED_OCR = "1"
```

노이즈 완화는 전체 사진을 최대 1800×2400 범위로 축소하고 3×3 중앙값 필터로 천 무늬를
줄인 뒤 대비를 보정합니다. 라벨을 자르거나 글자·숫자를 생성하지 않습니다.
2026-09-30의 실사진 89장 비교에서 기본 70장, 반사 보정·노이즈 완화 사용 시 73장이 정답지와 일치했습니다
(소재 집합 및 혼용률 ±3%p). 기존 정답 70장은 유지됐으며 독립 평가 결과는 아닙니다.
비교 방법·추가 호출 수·지연은 [전처리 실험 보고서](reports/qa_preprocessing_20260930.md)를 참고합니다.

미세 회전은 전체 이미지를 -3도 회전한 후보로 행 분할을 다시 시도합니다. 실제 기울기를
추정하는 기능은 아니며, 확장된 캔버스에도 크기 제한을 적용합니다. 글자 변경 이미지의
검수 가능한 고유 16장에서는 기본 13장→미세 회전 추가 15장으로 개선됐습니다.
이 집합에서는 반사·노이즈 완화 없이 미세 회전만 켜도 같은 결과였습니다.
중복·조성 충돌·파서 실패는 [편집 이미지 검증 보고서](reports/qa_edited_labels_20260930.md)를 참고합니다.
이 보고서는 작성 당시의 결과를 보존합니다. 2026-10-02의 후보 충돌·잔여 비율 보완 후
저장 OCR 재검증에서는 실사진 73/89·검수 가능한 편집 15/16을 유지했고, 조성이 모호해
제외한 고유 7장은 모두 안전 실패로 처리했습니다. 새로운 Vision 실호출 정확도 측정은 아닙니다.

전체 처리 시작 후 25초 예산의 남은 시간을 각 후보에 적용합니다. 후보별 설정은 원본
10초·기본 전처리 8초·반사 보정 7초·노이즈 완화 5초·미세 회전 5초·소재 영역 5초·영역 회전 5초이며, 남은 시간이 없으면 다음 후보를
생략하고 `total_timeout`을 기록합니다. 이미지 검증·전처리 시간도 남은 예산을 소모합니다.
25초는 `run_ocr_bytes()` 진입 후의 OCR 예산이며 HTTP 업로드 수신·본문 검사·multipart 파싱·최종 서비스 응답 전체를 포함하지 않습니다.
AI HTTP 경로의 동기 OCR은 작업 스레드에서 실행하며, 기다리는 동안 이벤트 루프를 막지 않습니다.
Google SDK 자동 재시도는 끄고 각 RPC에 후보·전체 예산의 남은 시간만 전달합니다.
재시도 대기와 클라이언트 준비 시간도 예산에 포함하며, 기한 이후 도착한 응답은 성공으로
사용하지 않습니다. 이 예산은 새 작업의 시작과 원격 호출 제한 시간을 제어합니다. 이미 실행 중인
동기 전처리나 제한 시간을 지키지 않는 외부 호출을 강제 종료하는 절대 시간 상한은 아닙니다.
`external_call_count`는 외부 OCR을 실행한 후보 수, `rpc_attempt_count`는 재시도를 포함한
실제 원격 호출(RPC) 시도 수, `retry_count`는 실제 시작한 추가 RPC 수입니다. 후보별 `attempts`에도
RPC 시도 수를 기록하고 QA CSV의 `ocr_rpc_attempt_count`로 내보냅니다. 캐시 적중·오프라인
실행의 RPC 시도 수는 0이며, RPC 시도 수가 청구된 요청 수를 보장하지는 않습니다.

### 라벨 분석 응답 계약

성공과 실패는 같은 기본 필드를 제공합니다. 대표 소재와 부위별 혼용률은 실제 정수·실수만
허용하며 각 값은 유한한 `0 초과 100 이하`, 각 조성의 합계는 정확히 `100%`여야 합니다.
숫자 문자열·불리언·NaN·무한대는 허용하지 않습니다. 정수·소수 표기는 유지합니다.
부위 정보가 있으면 `materials`는 `selected_part`의 조성과 같아야 합니다.
확정 가능한 조성 중 겉감 → 부위 미표시 → 겉감2 → 안감 → 충전재 → 주머니감 → 리브 → 소매 → 배색 → 자수실 순으로 선택합니다.
상위 부위의 비율이 없거나 미완성·상충이면 다음 확정 부위를 선택하며, 미확정 근거는 `parse_evidence`와 `warnings`에 보존합니다.
자수실은 `embroidery_yarn`으로 표시하며 다른 확정 부위가 있으면 대표로 선택하지 않습니다.
안감·자수실 선택 결과는 해당 부위의 조성이며 의류 전체 또는 겉감 조성으로 해석하지 않습니다.
실패 응답의 `materials`·`parts`는 빈 객체이며 `selected_part`는 빈 문자열입니다.

`confidence.ocr`·`confidence.parser`는 규칙에 따른 등급입니다. 교정된 성공 확률이나
Google Vision이 제공한 신뢰도 점수로 해석하지 않습니다.

아래는 `/v1/parse-text`에 `COTTON 80% POLYESTER 20%`를 보낸 전체 응답 예시입니다.
부위명이 없는 입력이므로 대표 부위는 `generic`, OCR 등급은 `unknown`입니다.

```json
{
  "api_version": "1.0",
  "status": "success",
  "error_code": "",
  "message": "",
  "materials": {
    "cotton": 80,
    "polyester": 20
  },
  "materials_korean": "면 80%, 폴리에스터 20%",
  "raw_ocr_preview": "COTTON 80% POLYESTER 20%",
  "confidence": {
    "ocr": "unknown",
    "parser": "high"
  },
  "warnings": [],
  "care_instruction": "",
  "care_instructions": [],
  "selected_part": "generic",
  "parts": {
    "generic": {
      "cotton": 80,
      "polyester": 20
    }
  },
  "parse_evidence": {
    "observed_ratios": {"generic": [80.0, 20.0]},
    "unpaired_ratio_parts": [],
    "composition_status": "confirmed",
    "source": "same_line",
    "ratio_total_before_normalization": 100.0,
    "explicit_percent": true
  },
  "ocr": {}
}
```

소재 구성을 신뢰할 수 없으면 임의의 100% 소재를 만들지 않고 `status: "failed"`와
오류 코드를 반환합니다. 프론트엔드는 이 경우 사용자 수동 입력 흐름을 제공해야 합니다.

| HTTP 상태 | 라벨 API의 의미 |
| --- | --- |
| 200 | 소재·혼용률 분석 성공 |
| 400 / 413 / 415 | 잘못된 이미지·크기 헤더 / 전체 본문·이미지 크기 초과 / 지원하지 않는 형식 |
| 422 | 요청 형식 오류 또는 조성 미확정·충돌 |
| 500 | 내부 처리·응답 계약 오류 |
| 502 | OCR 제공자의 처리 실패 |
| 503 | OCR 설정·사용량 한도·일시적인 가용성 오류 |
| 504 | OCR 응답 시간 초과 |

위 표는 AI 라벨 API 기준입니다. 앱의 백엔드 `/api/scan`은 조성 실패를 422,
OCR 설정·사용 한도 오류를 502, 일시 서비스 장애를 503, 시간 초과를 504로 반환합니다.

### 2026-10-04 개발 평가와 한계

| 평가 범위 | 결과 | 측정 조건 |
| --- | --- | --- |
| 합성 200장 | 181/200, 90.5% | 앞선 후보 판정 보완의 저장 OCR 재생; 새 소재 영역 전처리로 200장을 다시 평가한 수치는 아님 |
| 실사진 비교 47장 | 33/47, 70.21% | 원본 50장 중 3장 제외; 기존 OCR와 추가 전처리 29회가 포함된 캐시 평가 |

2026-10-05에는 실패 사진의 새 전처리 입력 29개만 실호출했으며, 원본 OCR는 기존 캐시를 재사용했습니다.
직전 32/47에서 DJ015가 추가 복구됐고 기존 정답의 퇴행·새 성공 오답은 없었습니다. 정답은 임시 상태이며 독립 평가 결과가 아닙니다.

두 집합은 합산하지 않습니다. 합성은 원본 10장 × 4언어 × 5환경의 변형이며 독립 실사진
200장이 아닙니다. 실사진 정답도 임시 상태이고 반복 라벨·약칭이 있으므로 실사용
80~90% 목표를 달성했다고 해석하지 않습니다. 영역 보완 후 실패 16장에서 영역 검출은
13→15장, 완전 일치 정답 후보가 있는 사진은 1→2장으로 늘었지만 최종 정답 수는 유지됐습니다.
숫자·미등록 소재·부위 검증을 풀어 점수를 올리지 않습니다. 독립 확정 정답과 별도 실사진
검증 세트가 필요하며, 과거 보고서의 점수·지연은 해당 코드·옵션·실행 범위의 기록입니다.

## OCR QA 정답지 형식

`scripts/run_qa_batch.py`는 OCR과 소재 파서 자체를 측정합니다. 백엔드
`/api/scan`까지 포함한 통합 QA는 저장소 루트의 `QA/run_qa_batch.py`를
사용합니다. 두 도구는 정답 CSV의 핵심 열, 소재 별칭 표준화, 실패 코드를
공유하지만 기본 허용 오차가 각각 `±3%p`, `±5%p`이므로 점수를 합치거나
직접 비교하지 않습니다. 통합 QA는 환경변수의 로그인 토큰으로 Bearer 인증을 지원합니다.
설정 방법은 [QA README](../../QA/README.md)를 확인합니다.

파서 규칙이나 OCR 전처리의 회귀만 확인할 때는 `scripts/run_qa_batch.py`를
사용합니다. 실제 백엔드 요청 형식과 응답 계약까지 확인할 때는 저장소 루트의
`QA/run_qa_batch.py`를 사용합니다. 두 결과는 측정 범위가 달라 각각 기록합니다.

OCR QA 정답 CSV의 필수 열은 다음과 같습니다.

```text
file_name, answer_materials, answer_ratios
```

소재명에는 `cotton`, `polyester`, `spandex`, `polyurethane`처럼 표준 영문 키를
사용합니다. 아래 두 형식을 지원합니다.

```text
cotton;polyester       / 80;20
cotton:80;polyester:20
```

정확도에 포함하는 일반 라벨의 원문 혼용률 합계는 `100%`여야 합니다.
합계에 오차가 있으면 100%로 정규화하지 않고 실패 처리합니다. OCR이 일부
숫자를 잘못 읽은 결과를 확정 혼용률처럼 사용하지 않기 위한 정책입니다. 복합/부위별
표기인 라벨은 대표 소재 정답을 별도로 적거나 `include_in_accuracy=FALSE`로 제외합니다.

원인별 실패를 분석하려면 다음 열도 기록하는 것을 권장합니다.

```text
split, source_group, capture_condition, label_layout
```

- `split`: `train`, `valid`, `test` 중 하나입니다.
- `source_group`: 같은 원본 라벨 또는 그 파생 이미지에 공통으로 부여하는 그룹입니다.
- `capture_condition`: `indoor`, `night`, `reflection`, `blur`, `wrinkle` 등의 촬영 조건입니다.
- `label_layout`: `same_line`, `alternating_lines`, `stacked`, `multi_part` 등의 라벨 배치입니다.

규칙을 변경하기 전에는 정답지 형식과 누수를 먼저 점검합니다. 이 명령은 데이터를
읽기만 하며 Google Vision을 호출하지 않습니다.

아래 예시는 저장소 루트의 `QA_DATASET/images`와 `QA_DATASET/answer_key.csv`를
준비한 경우입니다. `$dataset`을 실제 데이터셋 폴더에 맞게 변경합니다.

```powershell
$dataset = "..\..\QA_DATASET"
.\.venv\Scripts\python.exe -m scripts.audit_ocr_qa_dataset `
  --image-dir "$dataset\images" `
  --answer-key "$dataset\answer_key.csv" `
  --strict
```

OCR·파서 회귀 검사는 먼저 저장된 캐시로 실행합니다. 캐시가 준비되어 있어야 하며,
캐시 누락은 외부 호출 대신 오류로 기록합니다.

```powershell
.\.venv\Scripts\python.exe -m scripts.run_qa_batch `
  --image-dir "$dataset\images" `
  --answer-key "$dataset\answer_key.csv" `
  --offline `
  --strict-coverage
```

기본값은 정답 CSV의 `file_name`에 있는 이미지만 처리합니다. 폴더에 섞인
미정답 이미지를 함께 점검할 때만 `--include-unanswered`를 사용합니다.
동일한 `file_name`이 하위 폴더에 중복되면 어느 이미지를 평가할지 알 수 없으므로
실행을 중단합니다. 이때는 QA 실행 결과 폴더 전체가 아니라 정확한 `images` 폴더를
`--image-dir`에 지정합니다.
`--strict-coverage`는 이미지와 정답의 누락을 OCR 호출 전에 실패 처리하므로,
데이터셋 계약을 감사할 때 함께 사용합니다. OCR·파서에서 예상 밖 예외가 발생하면
결과 CSV와 요약 파일을 남긴 뒤 프로세스는 실패 종료합니다.

새 Vision OCR 측정이 필요하면 자격증명을 설정한 뒤 `--offline`을 빼고 실행합니다.
기본 실행은 캐시 적중을 재사용하고 누락 후보는 실제 호출하므로 비용이 발생할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m scripts.run_qa_batch `
  --image-dir "$dataset\images" `
  --answer-key "$dataset\answer_key.csv" `
  --strict-coverage
```

새 OCR 캐시에는 원문·읽기 순서와 함께 단어의 사각형 꼭짓점·페이지를 저장합니다.
좌표가 있는 항목은 오프라인 실행에서도 현재 행 복원 코드로 읽기 순서를 다시 만듭니다.
여러 단어가 같은 기울기를 보이는 영역만 보정하며, 방향이 크게 다르거나 근거가
부족한 영역은 기존 방식으로 처리합니다. 소재명·비율·합계로 기울기를 선택하지 않습니다.
기존 문자열 전용 캐시도 사용할 수 있지만, 그 항목에는 새 좌표 복원 효과가 적용되지
않으므로 실제 효과를 평가하려면 별도 캐시에서 좌표를 다시 확보해야 합니다.

`--refresh-ocr-cache`는 OCR 전처리·언어 힌트 변경이나 좌표가 없는 기존 캐시를
갱신할 때 사용합니다. 캐시는 OCR 파이프라인 버전을
기록하므로, 다른 버전의 캐시를 발견하면 기본 실행은 안전하게 중단하고 이 옵션으로
새 캐시를 만들도록 안내합니다. 여러 QA 실행이 같은 캐시를 갱신해도 파일 잠금과 병합
저장으로 서로 다른 이미지 항목을 보존합니다. 같은 이미지의 갱신은 기존 값을 교체합니다.
캐시 경로는 `--ocr-cache`로 지정하며 기본값은 `outputs/qa_ocr_cache.json`입니다.
`--offline`과 `--refresh-ocr-cache`는 함께 사용할 수 없습니다.
`--tolerance`는 0 이상의 유한한 숫자만 허용하며 기본값은 `3.0`입니다.
내용 버전은 코드에서 관리하며 모든 코드·설정 변경을 자동으로 추적하지 않습니다.
실험 설정을 바꿀 때는 캐시 경로를 구분하거나 실제 OCR 재측정이 필요한지 판단합니다.
`outputs/`의 OCR 캐시에는 라벨 텍스트가 포함될 수 있으므로 커밋하지 않습니다.

## 합성 소재 라벨 데이터

실사진 QA와 별도로, 재현 가능한 파서 회귀 입력을 만들기 위한 Pillow 기반 도구입니다.
기본 설정은 난수 시드(seed)가 고정된 20개 원본 라벨과 각 4개 이미지 조건 변형(총 80장)을
생성합니다. 변형에는 언어·조명·흐림·반사뿐 아니라 소재/비율 순서, 세로 열 레이아웃,
배경 테마, JPEG 품질, 혼합 조건이 포함됩니다. 목록 파일(`manifest.csv`)에는 정답 소재·비율,
`source_group`, 언어, 조건, 레이아웃, 테마, JPEG 품질, 변환 정보, 이미지 SHA-256을
저장하며 모든 행은 `include_in_accuracy=false`로 기록됩니다.

```powershell
.\.venv\Scripts\python.exe -m scripts.generate_synthetic_labels
```

생성물은 `outputs/synthetic/`에 저장되고 Git에서 제외됩니다. 같은 난수 시드·설정·폰트 환경에서는
동일한 이미지 해시가 재생성됩니다. 합성 데이터 점수는 실제 라벨 사진의 OCR 정확도와
별도로 기록해야 합니다.

기본 설정에는 한국어·일본어·중국어가 포함됩니다. Windows는 기본 CJK 폰트를 사용하며,
Ubuntu/Debian 환경에서는 생성 전에 `sudo apt-get install fonts-noto-cjk`를 실행합니다.
AI CI는 이 폰트를 설치한 뒤 네 언어 생성 테스트를 실행합니다. 다른 운영체제에서는
Noto CJK 또는 시스템 CJK 폰트를 설치해야 합니다.

합성 목록 파일의 `original_text`를 파서에 직접 넣어 회귀를 측정하려면 다음 명령을 사용합니다.
이 평가는 Google Vision이나 이미지 OCR을 호출하지 않으며, 결과를 실사진 QA 정확도로
해석하면 안 됩니다.

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_synthetic_labels
```

`image_results.csv`에는 이미지 행별 파서 결과를, `source_group_results.csv`에는 같은 원본의
모든 변형이 통과했는지의 그룹 점수를 저장합니다. `summary.json`의
`evaluation_type`은 항상 `synthetic_parser_only`입니다.
실사진을 AI로 편집한 이미지는 이 Pillow 생성물과 별도 데이터셋입니다.
AI 편집본도 같은 원본을 공유하므로 독립 실사진 평가로 계산하지 않습니다.

### 레이아웃·테마 대조군

기본 80장은 여러 스트레스 조건을 함께 섞어 회귀 범위를 넓히는 용도입니다. 따라서 기본
결과의 레이아웃·테마별 집계는 조건 효과의 원인으로 해석하지 않습니다. 조건 효과는 별도
대조군 설정으로 확인합니다. 이 설정은 같은 `source_group`의 소재·비율·언어를 유지한 채
기준 라벨 1장과 레이아웃 2종·테마 2종만 각각 바꾼 총 100장을 생성합니다. 모든 대조군은
`clean` 조건과 JPEG 품질 90을 사용합니다.

```powershell
.\.venv\Scripts\python.exe -m scripts.generate_synthetic_labels --config configs/synthetic_label_controls_v1.json --output outputs/synthetic/label_controls_v1
.\.venv\Scripts\python.exe -m scripts.evaluate_synthetic_labels --manifest outputs/synthetic/label_controls_v1/manifest.csv --output-dir outputs/synthetic_evaluation/label_controls_v1
```

대조군 `summary.json`의 `controlled_comparisons`는 같은 원본의 기준 라벨과 비교 대상만
짝지어 집계합니다. 이 역시 `original_text`를 파서에 넣는 검사이므로, 시각 OCR 성능의
증거가 아니라 파서 규칙의 회귀 지표입니다.

## 알려진 한계와 다음 작업

- 현재 DPP 사용자 흐름은 소재 OCR 분석만 사용합니다.
- AI 단위 QA와 `/api/scan` 통합 QA는 위에 명시한 측정 범위·허용 오차를 각각 적용합니다.
- 백엔드의 조성 실패 오류 매핑과 통합 QA의 인증 헤더 지원은 반영되어 있습니다.
- 신뢰도 등급의 보정과 독립 실사진 데이터셋 평가는 아직 완료되지 않았습니다.
