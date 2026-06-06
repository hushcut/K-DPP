# K-DPP Backend API Contract

이 문서는 프론트엔드, 백엔드, AI/OCR 파트가 같은 요청/응답 형식을 기준으로 협업하기 위한 API 계약서입니다.

현재 기준 로컬 서버 주소는 다음과 같습니다.

```text
http://127.0.0.1:8000
```

Android Emulator에서 Flutter가 백엔드를 호출할 때는 다음 주소를 사용합니다.

```text
http://10.0.2.2:8000
```

## 공통 응답 규칙

성공 응답은 가능한 한 다음 필드를 포함합니다.

```json
{
  "status": "success",
  "message": "처리 결과 메시지"
}
```

실패 응답은 FastAPI 예외 핸들러를 통해 다음 형식으로 반환합니다.

```json
{
  "status": "error",
  "message": "사용자에게 보여줄 수 있는 오류 메시지",
  "detail": "또는 상세 오류 객체"
}
```

프론트엔드와 우선 맞춰야 하는 주요 필드는 다음과 같습니다.

```text
status
message
materials
carbon_footprint
unit
care_instruction
saved_result_id
title
category
```

## POST /auth/signup

회원가입 API입니다. 이메일 중복 가입을 막고, 비밀번호는 해시로 저장합니다.

### Request

```json
{
  "email": "user@example.com",
  "password": "password123",
  "nickname": "홍길동"
}
```

### Success Response

```json
{
  "status": "success",
  "message": "회원가입이 완료되었습니다.",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "nickname": "홍길동"
  }
}
```

### Error Responses

이메일 형식이 잘못된 경우:

```json
{
  "status": "error",
  "message": "올바른 이메일을 입력해 주세요.",
  "detail": "올바른 이메일을 입력해 주세요."
}
```

이미 가입된 이메일인 경우:

```json
{
  "status": "error",
  "message": "이미 가입된 이메일입니다.",
  "detail": "이미 가입된 이메일입니다."
}
```

## POST /auth/login

로그인 API입니다. 성공 시 사용자 정보와 30일 동안 유효한 access token을 반환합니다.

### Request

```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

### Success Response

```json
{
  "status": "success",
  "message": "로그인되었습니다.",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "nickname": "홍길동"
  },
  "access_token": "temporary-token-value",
  "token_type": "bearer",
  "expires_in": 2592000
}
```

## POST /auth/logout

`Authorization: Bearer <token>` 헤더로 현재 로그인 토큰을 폐기합니다.

### Error Response

```json
{
  "status": "error",
  "message": "이메일 또는 비밀번호가 올바르지 않습니다.",
  "detail": "이메일 또는 비밀번호가 올바르지 않습니다."
}
```

## POST /analyze

기존 연동 호환을 위한 소재 계수 확인 API입니다. 최종 의류 탄소배출량은 무게가 포함된 `POST /api/carbon/calculate`를 사용합니다.

현재 성공한 분석 결과는 `analysis_results` 테이블에 저장됩니다.

### Request

```json
{
  "materials": {
    "cotton": 80,
    "polyester": 20
  },
  "raw_ocr_text": "COTTON 80% POLYESTER 20%"
}
```

### Request Rules

- `materials`는 필수입니다.
- 소재명은 `materials.name_ko`, `materials.name_en`, `materials.aliases` 중 하나와 매칭되어야 합니다.
- 소재 비율은 0 이상이어야 합니다.
- 전체 비율 합계는 OCR 오차를 고려해 `99.5 ~ 100.5` 범위까지 허용합니다.
- `raw_ocr_text`는 선택 값입니다.

### Success Response

```json
{
  "status": "success",
  "message": "분석 완료",
  "materials": {
    "cotton": 80,
    "polyester": 20
  },
  "carbon_footprint": 8.54,
  "unit": "kg CO2eq",
  "care_instruction": "30도 이하 물에 중성세제로 세탁하세요.",
  "saved_result_id": 13
}
```

### Error Responses

비율 합계가 100이 아닌 경우:

```json
{
  "status": "error",
  "message": "전체 비율의 합이 100이 아닙니다. 현재 합계: 90",
  "detail": "전체 비율의 합이 100이 아닙니다. 현재 합계: 90"
}
```

등록되지 않은 소재가 포함된 경우:

```json
{
  "status": "error",
  "message": "DB에 등록되지 않은 소재가 있습니다.",
  "detail": {
    "message": "DB에 등록되지 않은 소재가 있습니다.",
    "unknown_materials": ["unknown_fiber"]
  }
}
```

## POST /api/scan

의류 라벨 이미지를 업로드하면 백엔드가 OCR과 라벨 파싱을 수행해 소재 혼용률을 반환합니다. 이 단계에서는 의류 무게가 정해지지 않았으므로 탄소배출량을 계산하거나 저장하지 않습니다.

테스트 목적으로 OCR을 건너뛰고 싶을 때는 `raw_ocr_text` form field를 함께 보낼 수 있습니다.

### Request

Content-Type: `multipart/form-data`

```text
image: care-label.jpg
raw_ocr_text: COTTON 80% POLYESTER 20%  (optional)
```

### Success Response

```json
{
  "status": "success",
  "message": "라벨 인식 완료",
  "materials": {
    "cotton": 80,
    "polyester": 20
  },
  "care_instruction": "라벨 표기법에 맞춰 관리하세요.",
  "title": "스캔한 의류",
  "category": "상의"
}
```

## POST /api/carbon/calculate

사용자가 의류 종류 또는 실제 무게를 선택한 뒤 호출하는 최종 탄소배출량 계산 API입니다. 소재별 계수는 백엔드 DB만 사용하며, 계산 결과는 로그인 사용자 분석 이력에 저장됩니다.

`Authorization: Bearer <token>` 헤더가 필요합니다.

### Request

```json
{
  "materials": {
    "cotton": 80,
    "polyester": 20
  },
  "min_weight_grams": 100,
  "max_weight_grams": 250
}
```

직접 입력한 실제 무게는 최소·최대 무게에 같은 값을 전달합니다.

### Calculation

```text
혼합 소재 계수 = Σ(소재별 탄소계수 × 혼용률)
최소 탄소배출량 = 혼합 소재 계수 × 최소 무게(kg)
최대 탄소배출량 = 혼합 소재 계수 × 최대 무게(kg)
대표 탄소배출량 = (최소 + 최대) / 2
```

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
  "carbon_footprint_min": 0.85,
  "carbon_footprint_max": 2.13,
  "min_weight_grams": 100,
  "max_weight_grams": 250,
  "unit": "kg CO2eq",
  "saved_result_id": 13
}
```

### Error Responses

OCR 모듈을 불러오지 못한 경우:

```json
{
  "status": "error",
  "message": "AI OCR 모듈을 불러오지 못했습니다.",
  "detail": {
    "message": "AI OCR 모듈을 불러오지 못했습니다.",
    "hint": "AI/kdpp_ai_ocr_integrated 의존성을 설치하고 다시 실행하세요."
  }
}
```

라벨에서 소재 정보를 찾지 못한 경우:

```json
{
  "status": "error",
  "message": "라벨에서 소재 비율을 찾지 못했습니다.",
  "detail": {
    "message": "라벨에서 소재 비율을 찾지 못했습니다.",
    "raw_ocr_preview": "OCR preview text"
  }
}
```

## GET /materials

소재별 탄소배출계수 목록을 반환합니다.

### Success Response

```json
[
  {
    "id": 1,
    "name_ko": "면",
    "name_en": "cotton",
    "aliases": ["면", "코튼", "cotton", "cotton"],
    "carbon_factor": 8.3,
    "unit": "kg CO2eq/kg textile"
  },
  {
    "id": 2,
    "name_ko": "폴리에스터",
    "name_en": "polyester",
    "aliases": ["폴리에스터", "polyester", "polyester", "poly"],
    "carbon_factor": 9.5,
    "unit": "kg CO2eq/kg textile"
  }
]
```

## GET /history

로그인한 사용자의 분석 결과 목록을 최신순으로 반환합니다. `/history`와 `/me/history`는 모두 `Authorization: Bearer <token>` 헤더가 필요합니다.

### Success Response

```json
{
  "status": "success",
  "history": [
    {
      "id": 13,
      "materials": {
        "cotton": 80,
        "polyester": 20
      },
      "carbon_footprint": 8.54,
      "unit": "kg CO2eq",
      "unknown_materials": [],
      "created_at": "2026-06-04T12:00:00"
    }
  ]
}
```

## 사용자별 분석 결과 저장 정책 초안

PM 요청에 따라 `analysis_results`와 사용자를 연결하려면 다음 정책을 확정해야 합니다.

추천 정책:

- 로그인 사용자의 `/analyze`, `/api/scan` 결과만 저장합니다.
- 비로그인 사용자의 분석 결과는 저장하지 않고 응답만 반환합니다.
- `analysis_results.user_id`를 추가해 `users.id`와 연결합니다.
- 로그인 토큰은 임시 문자열이 아니라 검증 가능한 방식으로 관리합니다.

구현 후보:

1. MVP 방식: `access_tokens` 테이블을 만들고 로그인 시 토큰을 저장합니다.
2. 표준 방식: JWT를 사용하고 `Authorization: Bearer <token>` 헤더를 검증합니다.

## 프론트엔드 호출 예시

```dart
final response = await http.post(
  Uri.parse('http://10.0.2.2:8000/analyze'),
  headers: {'Content-Type': 'application/json'},
  body: jsonEncode({
    'materials': {
      'cotton': 80,
      'polyester': 20,
    },
    'raw_ocr_text': 'COTTON 80% POLYESTER 20%',
  }),
);
```
