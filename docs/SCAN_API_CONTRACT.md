# K-DPP Scan API Contract

이 문서는 Flutter 프론트엔드와 FastAPI 백엔드가 의류 케어 라벨 스캔 결과를 주고받기 위한 기준입니다.

## Base URL

- 백엔드 로컬 실행: `http://127.0.0.1:8000`
- Android Emulator: `http://10.0.2.2:8000`

Flutter의 기본 스캔 주소는 다음과 같습니다.

```text
http://10.0.2.2:8000/api/scan
```

실제 Android 기기나 ngrok 서버를 사용할 때는 전체 스캔 주소를 `SCAN_API_ENDPOINT`로 주입합니다.

```shell
flutter run --dart-define=SCAN_API_ENDPOINT=http://192.168.0.10:8000/api/scan
```

```shell
flutter run --dart-define=SCAN_API_ENDPOINT=https://example.ngrok-free.app/api/scan
```

Android Studio에서는 Run/Debug Configuration의 Additional run args에 같은 `--dart-define` 값을 추가합니다. ngrok 사용 시 프론트는 `ngrok-skip-browser-warning: true` 헤더를 자동으로 전송합니다.

프론트엔드 테스트의 `test/fixtures/backend_scan_*.json`은 중간통합 FastAPI의 현재 응답을 기준으로 관리합니다. 백엔드 응답 필드가 변경되면 계약 문서, fixture, 파싱 테스트를 함께 갱신합니다.

## 1. 라벨 인식

```http
POST /api/scan
Content-Type: multipart/form-data
```

### Request

| 필드 | 형식 | 필수 | 설명 |
| --- | --- | --- | --- |
| `image` | image file | O | 케어 라벨 사진 |
| `raw_ocr_text` | string | X | OCR 테스트용 원문 |

### Success Response

```json
{
  "status": "success",
  "message": "분석 완료",
  "materials": {
    "cotton": 80.0,
    "polyester": 20.0
  },
  "care_instruction": "30도 이하 물에서 중성세제로 세탁하세요.",
  "title": "홍길동 코튼 셔츠",
  "category": "상의",
  "carbon_footprint": 8.54,
  "unit": "kg CO2eq",
  "saved_result_id": 13
}
```

### Field Rules

| 필드 | 형식 | 필수 | 규칙 |
| --- | --- | --- | --- |
| `status` | string | O | 성공 시 `success` |
| `message` | string | O | 처리 결과 안내 |
| `materials` | object | O | 소재명을 key, 혼용률을 number로 반환 |
| `care_instruction` | string | O | 빈 값이면 기본 안내 문구 반환 |
| `title` | string | X | 인식하지 못하면 생략 가능 |
| `category` | string | X | `상의` 또는 `하의`, 불확실하면 생략 가능 |
| `carbon_footprint` | number | X | 현재 백엔드 호환 필드이며 최종값으로 사용하지 않음 |
| `unit` | string | X | 탄소 값이 있으면 `kg CO2eq` |
| `saved_result_id` | integer | X | 서버에 저장했을 때만 반환 |

`materials`의 합계는 `99.5 ~ 100.5` 범위를 허용합니다. 소재명은 백엔드 소재 기준표의 `name_ko`, `name_en`, `aliases` 중 하나를 사용합니다.

### Error Response

```json
{
  "status": "error",
  "message": "라벨에서 소재 혼용률을 찾지 못했습니다.",
  "detail": {
    "message": "라벨에서 소재 혼용률을 찾지 못했습니다.",
    "raw_ocr_preview": "OCR preview text"
  }
}
```

권장 HTTP 상태 코드는 다음과 같습니다.

| 상태 코드 | 의미 |
| --- | --- |
| `400` | 잘못된 입력값 또는 소재 비율 오류 |
| `401`, `403` | 인증 오류 |
| `413` | 이미지 용량 초과 |
| `415` | 지원하지 않는 이미지 형식 |
| `422` | OCR 결과에서 소재 혼용률을 찾지 못함 |
| `502` | 외부 AI/OCR 처리 실패 |
| `503` | AI/OCR 모듈 사용 불가 |
| `500` | 그 외 서버 내부 오류 |

## 2. 무게 기반 탄소 계산

라벨 인식 후 사용자가 의류 종류 또는 실제 무게를 선택한 다음 호출하는 API입니다.

```http
POST /analyze
Content-Type: application/json
```

### Target Request

```json
{
  "materials": {
    "cotton": 80.0,
    "polyester": 20.0
  },
  "weight_gram": 520.0,
  "category": "상의",
  "clothing_type": "긴팔 / 맨투맨"
}
```

### Target Success Response

```json
{
  "status": "success",
  "message": "분석 완료",
  "materials": {
    "cotton": 80.0,
    "polyester": 20.0
  },
  "weight_gram": 520.0,
  "carbon_footprint": 4.78,
  "calculation_method": "weight_based_v1",
  "unit": "kg CO2eq",
  "health": 85,
  "care_instruction": "30도 이하 물에서 중성세제로 세탁하세요.",
  "saved_result_id": 13
}
```

현재 백엔드 `/analyze`는 `weight_gram`을 받지 않습니다. 실제 의류 탄소발자국을 계산하려면 백엔드가 다음 식처럼 의류 무게를 반영하도록 확장해야 합니다.

```text
탄소발자국 = 합계((소재 비율 / 100) x 소재별 배출계수 x 의류 무게 kg)
```

프론트엔드는 백엔드 확장이 끝날 때까지 로컬 추정값을 미리보기로 사용합니다. 백엔드가 무게를 반영한 값을 반환하기 시작하면 서버 값을 최종값으로 우선 사용합니다.

서버값 우선순위는 다음 조건을 모두 만족할 때 적용합니다.

- 건강도: 서버의 `health`가 `0 ~ 100`이고 사용자가 소재와 혼용률을 수정하지 않은 경우
- 탄소발자국: 서버의 `carbon_footprint`와 `weight_gram`이 유효하고, `calculation_method`가 `weight_based_v1`이며, 사용자가 소재를 수정하지 않았고 현재 선택 무게와 서버 계산 무게가 일치하는 경우
- 위 조건을 만족하지 않으면 프론트엔드의 로컬 추정값을 미리보기와 저장값으로 사용

`calculation_method`가 없거나 다른 값이면 프론트엔드는 서버 탄소값을 최종값으로 신뢰하지 않습니다. 저장 시 계산 출처도 함께 기록하여 리포트에서 `백엔드 계산값`과 `임시 추정값`을 구분합니다.

## 3. 역할 구분

- 백엔드/AI: OCR, 소재명 정규화, 혼용률 추출, 배출계수 관리, 최종 탄소 계산
- 프론트엔드: 사진 전달, 인식 결과 수정 UI, 의류 종류/무게 선택, 입력값 검증, 결과 표시
- 사진 원본은 분석 요청에만 사용하며 프론트의 임시 촬영 파일은 분석 후 삭제합니다.
