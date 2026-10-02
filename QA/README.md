# K-DPP 백엔드 통합 배치 검사

의류 라벨 사진을 백엔드 `/api/scan`에 보내고 소재·혼용률 결과를 정답표와 비교하는 도구입니다.

## 현재 실행 제한

현재 백엔드의 `/api/scan`은 `Authorization: Bearer <token>` 인증이 필수입니다.
이 도구에는 인증 헤더를 전달하는 옵션이 없어 현재 백엔드에 그대로 실행하면 401을
`서버/API 실패`로 기록합니다. 현재 백엔드의 정상 통합 평가에는 인증 헤더 지원이 먼저
필요합니다. 아래 명령은 도구의 입력·옵션 사용법을 설명합니다. 인증 지원은 별도 후속 작업입니다.

OCR·파서 규칙을 지금 검사할 때는 [AI README](../AI/kdpp_ai_ocr_integrated/README.md)의
저장 캐시 기반 단위 QA를 사용합니다. 백엔드 설정·인증 요구사항은
[백엔드 README](../BACKEND/README.md)와 [API 계약](../BACKEND/API_CONTRACT.md)을 확인합니다.

## 목적

사진 폴더와 정답표를 기준으로 여러 장의 라벨 이미지를 한 번에 검사합니다.

```text
images 폴더
+ answer_key.csv
+ run_qa_batch.py
→ qa_result.csv 생성
```

앱 화면 흐름은 별도로 확인합니다. 이 도구의 점수는 백엔드 요청·응답을 포함한 소재·혼용률 일치율입니다.

## OCR QA와의 공통 기준

이 도구는 `AI/kdpp_ai_ocr_integrated/scripts/run_qa_batch.py`와 정답
CSV의 핵심 열, 소재 별칭 표준화, `failure_category` 실패 코드를 공유합니다.
예를 들어 `면`, `elastane`은 각각 `cotton`, `spandex`로 정규화합니다.

두 도구의 점수는 같은 정확도로 섞어 비교하지 않습니다.

```text
AI/kdpp_ai_ocr_integrated/scripts/run_qa_batch.py : OCR·파서 단위 QA, 기본 ±3%p
QA/run_qa_batch.py                             : /api/scan 통합 QA, 기본 ±5%p
```

정답 CSV의 소재·비율 규칙은 공유하지만, 통합 QA에는 `id` 열이 추가로 필수입니다.
복합/부위별 라벨은 대표 소재 기준 값을
`normalized_materials`, `normalized_ratios`에 기록하거나
`include_in_accuracy=FALSE`로 지정합니다.

### 통합 QA 판정 원칙

`include_in_accuracy=FALSE`는 일반 정확도 분모에서만 제외한다는 뜻입니다.
이 케이스에서도 API 연결 오류, 잘못된 응답 형식, 서버 오류는 `서버/API 실패`로
결과 CSV에 기록합니다. 복합 라벨을 정확도 수치에 섞지 않으면서 운영 장애를
숨기지 않기 위한 기준입니다.

사용 시점도 구분합니다. OCR과 소재 파서 규칙만 빠르게 확인할 때는
`AI/kdpp_ai_ocr_integrated/scripts/run_qa_batch.py`를 사용하고, 백엔드
`/api/scan` 요청·응답까지 확인할 때는 이 폴더의 `run_qa_batch.py`를 사용합니다.
두 도구는 허용 오차와 측정 범위가 달라 정확도를 하나의 숫자로 합치지 않습니다.

## 폴더 예시

```text
QA_DATASET/
  images/
    QA001.jpg
    QA002.jpg
    QA003.jpg
  answer_key.csv
  results/
```

## 정답표 양식

[`answer_key_template.csv`](answer_key_template.csv)를 복사해서 `answer_key.csv`로 사용합니다.
필수 열은 `id`, `file_name`, `answer_materials`, `answer_ratios`입니다.

기록할 수 있는 열은 다음과 같습니다.

```text
id
file_name
answer_materials
answer_ratios
case_type
include_in_accuracy
normalized_materials
normalized_ratios
shooting_pose
lighting
resolution
label_language
label_condition
notation_type
memo
```

소재와 비율은 세미콜론(`;`)으로 구분하며 순서와 개수가 같아야 합니다.
각 비율은 유한한 `0 초과 100 이하`의 숫자로 적습니다.

예시:

```csv
id,file_name,answer_materials,answer_ratios,case_type,include_in_accuracy,normalized_materials,normalized_ratios,shooting_pose,lighting,resolution,label_language,label_condition,notation_type,memo
QA001,QA001.jpg,cotton;polyester,80;20,일반 라벨,TRUE,,,손에 들고,자연광,고해상도,한글,정상,% 있음,
QA002,QA002.jpg,cotton,100,일반 라벨,TRUE,,,바닥에 두고,실내 조명,중간 해상도,한글,그림자,% 있음,
```

## 일반 라벨과 복합 라벨 기준

정확도 비교 대상의 혼용률 합계는 AI 파서의 확정 기준인 `100±0.01%p`를 따릅니다.
개별 소재 비율의 비교 허용 오차 `±5%p`와 조성 합계 기준은 서로 다른 검사입니다.

정답표는 아래 기준으로 나눕니다.

```text
일반 라벨:
- 소재·혼용률 합계가 100%이며 합계 오차는 0.01%p 이하
- 기준 밖의 합계는 100%로 보정하지 않고 정답지 오류로 처리

복합/부위별 라벨:
- 겉감, 안감, 충전재, 배색, 퍼 등 부위별 표기가 섞여 합계가 100%를 크게 초과
- 일반 정확도 계산에서 제외하거나 대표 소재 기준으로 단순화
```

복합/부위별 라벨 처리 방식:

```text
1. 대표 소재가 명확하지 않으면 include_in_accuracy를 FALSE로 둡니다.
2. 대표 소재가 명확하면 include_in_accuracy를 TRUE로 두고 normalized_materials / normalized_ratios에 대표 조성 정답을 적습니다.
3. 원문 소재·비율은 answer_materials / answer_ratios에 그대로 남깁니다.
4. memo에는 겉감·안감·충전재 등 원문 구조를 적습니다.
```

예시:

```csv
id,file_name,answer_materials,answer_ratios,case_type,include_in_accuracy,normalized_materials,normalized_ratios,shooting_pose,lighting,resolution,label_language,label_condition,notation_type,memo
QA007,QA007.jpg,nylon;polyester;down;feather,100;100;90;10,복합/부위별 라벨,FALSE,,,바닥에 두고,실내 조명,고해상도,일본어,정상,% 있음,겉감/안감/충전재가 섞인 확장 케이스
QA008,QA008.jpg,polyester;acrylic,100;60,복합/부위별 라벨,TRUE,polyester,100,손에 들고,실내 조명,중간 해상도,일본어,정상,% 있음,대표 소재 polyester 기준으로 1차 정확도 계산
```

## 실행 방법

**Windows PowerShell, 저장소 루트** 기준입니다. Python은 AI README의 개발 환경
설치로 준비한 가상환경을 사용합니다. 예시 데이터셋 폴더는 직접 준비하고 `$dataset`을
실제 경로에 맞게 바꿉니다. 백엔드 준비는 위 링크를 따르며 현재 인증 제한을 먼저 확인합니다.

```powershell
$dataset = ".\QA_DATASET"
.\AI\kdpp_ai_ocr_integrated\.venv\Scripts\python.exe .\QA\run_qa_batch.py `
  --answers "$dataset\answer_key.csv" `
  --images "$dataset\images" `
  --output "$dataset\results\qa_result.csv"
```

기본 요청 주소는 `http://127.0.0.1:8000/api/scan`, 업로드 필드는 `image`입니다.
주소는 `--api-url`, 업로드 필드는 `--upload-field`로 바꿉니다.

요청별 설정은 한 실행 단위로 함께 관리합니다. 필요할 때만 아래 옵션으로 제한을
바꿉니다.

| 옵션 | 기본값 | 역할 |
| --- | --- | --- |
| `--timeout` | `60` | 요청 제한 시간(초) |
| `--tolerance` | `5.0` | 소재별 혼용률 비교 허용 오차(%p) |
| `--max-image-bytes` | `10485760` | 이미지 업로드 크기 상한 |
| `--max-response-bytes` | `1048576` | 응답 읽기 크기 상한 |
| `--max-raw-response-chars` | `4000` | CSV에 남길 응답 미리보기 길이 |
| `--sleep` | `0.0` | 요청 사이의 대기 시간(초) |

`--max-response-bytes`는 네트워크에서 읽을 수 있는 응답 자체의 상한이고,
`--max-raw-response-chars`는 결과 CSV에 남길 응답 미리보기의 상한입니다. 후자가
잘리면 `raw_response_truncated=TRUE`가 기록되므로, 오류 분석 시 원문이 일부만
저장됐다는 점을 알 수 있습니다.

## 결과 판정 기준

기본 허용 오차는 `±5%p`이며 0 이상의 유한한 숫자만 허용합니다.

```text
완전 성공: 소재명과 혼용률이 허용 오차 내에서 모두 일치
소재 성공/비율 실패: 소재명은 맞지만 일부 비율이 허용 오차를 벗어남
소재 실패: 소재 누락 또는 잘못된 소재 인식
OCR 실패: 성공 응답에 소재가 없거나 알려진 조성 실패 코드의 HTTP 422
서버/API 실패: 연결·인증·서버 오류 또는 응답 계약 위반
정확도 제외: 복합/부위별 라벨 등 현재 일반 정확도 계산 대상이 아닌 케이스
```

`failure_category`는 결과를 모아 분석하기 위한 공통 코드입니다. 예를 들어
소재 누락과 추가가 함께 있으면 `material_missing_and_extra`, 혼용률만
다르면 `ratio_mismatch`, 서버 요청 문제는 `server_or_api_failure`로 기록합니다.
응답의 숫자 문자열·불리언·NaN·무한대·범위 밖 비율은 `api_contract_invalid`로 기록합니다.
현재 백엔드가 조성 충돌을 502로 반환하는 경우에는 `서버/API 실패`로 판정합니다.
422 구분은 백엔드 담당 브랜치의 후속 수정입니다.

허용 오차를 바꾸려면 실행 명령에 `--tolerance 3`처럼 추가합니다.

## QA팀 사용 방식

```text
QA 1: 사진 파일명과 촬영 조건 정리
QA 2: 정답표 작성
QA 3: 배치 테스트 실행 및 실패 사례 정리
```

결과 CSV는 Excel 또는 Google Sheets로 열어 실패 사례를 필터링합니다.
