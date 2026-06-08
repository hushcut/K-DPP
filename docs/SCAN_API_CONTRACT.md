# K-DPP Frontend Scan API Contract

이 문서는 Flutter 프론트엔드가 FastAPI 백엔드와 스캔/탄소 계산을 연동할 때 기준으로 삼는 계약입니다.

## 실행 주소

기본 스캔 주소:

```text
http://10.0.2.2:8000/api/scan
```

기본 탄소 계산 주소:

```text
http://10.0.2.2:8000/api/carbon/calculate
```

실제 Android 기기에서는 PC의 같은 Wi-Fi IP를 사용합니다.

```shell
flutter run \
  --dart-define=SCAN_API_ENDPOINT=http://192.168.0.10:8000/api/scan \
  --dart-define=CARBON_API_ENDPOINT=http://192.168.0.10:8000/api/carbon/calculate
```

ngrok 사용 시 프론트는 `ngrok-skip-browser-warning: true` 헤더를 전송합니다.

## 1. 라벨 스캔

```http
POST /api/scan
Content-Type: multipart/form-data
```

### Request

| 필드 | 형식 | 필수 | 설명 |
| --- | --- | --- | --- |
| `image` | image file | O | 의류 케어 라벨 사진 |
| `raw_ocr_text` | string | X | OCR 테스트용 원문 |

### Success Response

```json
{
  "status": "success",
  "message": "라벨 인식 완료",
  "ai_success": true,
  "analysis_failure_reason": null,
  "materials": {
    "cotton": 80,
    "polyester": 20
  },
  "material_details": [
    {
      "original_name": "cotton",
      "standard_name": "cotton",
      "display_name": "면",
      "ratio": 80,
      "is_supported": true
    }
  ],
  "care_instruction": "라벨 표기법에 맞춰 관리하세요.",
  "raw_ocr_preview": "COTTON 80% POLYESTER 20%",
  "clothing": {
    "name": "스캔한 의류",
    "category": "상의"
  },
  "title": "스캔한 의류",
  "category": "상의"
}
```

스캔 API는 탄소배출량을 계산하거나 저장하지 않습니다. 최종 계산은 사용자가 의류 종류 또는 직접 무게를 선택한 뒤 `/api/carbon/calculate`에서 수행합니다.

## 2. 스캔 오류

```json
{
  "status": "error",
  "error_code": "MATERIAL_EXTRACTION_FAILED",
  "message": "라벨에서 소재 혼용률을 찾지 못했습니다.",
  "detail": {
    "message": "라벨에서 소재 혼용률을 찾지 못했습니다.",
    "error_code": "MATERIAL_EXTRACTION_FAILED",
    "materials": {},
    "partial_materials": {},
    "care_instruction": "라벨 표기법에 맞춰 관리하세요.",
    "raw_ocr_preview": "CARE LABEL TEXT",
    "ai_success": false
  }
}
```

프론트 주요 분기:

| HTTP | error_code | 프론트 처리 |
| --- | --- | --- |
| 415 | `UNSUPPORTED_IMAGE_FORMAT` | 지원하지 않는 이미지 안내 |
| 422 | `MATERIAL_EXTRACTION_FAILED` | 소재 직접 입력 흐름 |
| 502 | `OCR_FAILED` | 라벨 글자 재촬영 안내 |
| 503 | `AI_MODULE_FAILED` | 서버/AI 모듈 문제 안내 |

## 3. 탄소 계산

```http
POST /api/carbon/calculate
Content-Type: application/json
Authorization: Bearer <token>
```

### Request

```json
{
  "materials": {
    "cotton": 80,
    "polyester": 20
  },
  "min_weight_grams": 100,
  "max_weight_grams": 250,
  "weight_grams": null,
  "clothing_type": "반팔 티셔츠",
  "category": "상의"
}
```

`weight_grams`가 있으면 직접 입력 무게로 보고 `min_weight_grams`, `max_weight_grams`보다 우선합니다.

### Success Response

```json
{
  "status": "success",
  "message": "탄소배출량 계산 완료",
  "materials": {
    "cotton": 80,
    "polyester": 20
  },
  "carbon_factor": 8.54,
  "carbon_footprint": 1.49,
  "average_carbon_footprint": 1.49,
  "carbon_footprint_min": 0.85,
  "carbon_footprint_max": 2.13,
  "min_weight_grams": 100,
  "max_weight_grams": 250,
  "weight_grams": null,
  "weight_source": "range",
  "clothing_type": "반팔 티셔츠",
  "category": "상의",
  "unit": "kg CO2eq",
  "source": "backend",
  "saved_result_id": 13
}
```

## 4. 프론트 저장 기준

- 로그인 토큰이 있으면 서버 탄소 계산을 먼저 시도합니다.
- 서버 계산 성공 시 `carbon_footprint`, `carbon_footprint_min`, `carbon_footprint_max`, `saved_result_id`를 서버값으로 저장합니다.
- 인증 만료, 네트워크 오류, 서버 오류가 발생하면 로컬 추정값으로 저장하고 사용자에게 안내합니다.
- 스캔 단계의 임시 결과는 서버 저장값으로 취급하지 않습니다.

