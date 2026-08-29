# K-DPP Backend API Contract

기준 브랜치: `develop(중간통합)`

이 문서는 프론트엔드, 백엔드, AI/OCR 파트가 같은 응답 구조를 기준으로 연동하기 위한 API 계약서입니다.

## 공통 규칙

- 응답은 기본적으로 `status`, `message`를 포함합니다.
- 오류 응답은 프론트 분기를 위해 `error_code`를 포함합니다.
- 탄소배출량 단위는 `kg CO2eq`입니다.
- 소재별 배출계수 단위는 `kg CO2eq/kg textile`입니다.
- 현재 소재별 배출계수는 개발용 추정값입니다. 최종 발표 전 팀 승인 출처로 교체해야 합니다.

## 공통 오류 응답

```json
{
  "status": "error",
  "error_code": "MATERIAL_EXTRACTION_FAILED",
  "message": "라벨에서 소재 혼용률을 찾지 못했습니다.",
  "detail": {
    "message": "라벨에서 소재 혼용률을 찾지 못했습니다."
  }
}
```

주요 `error_code`:

- `IMAGE_MISSING`: 이미지 파일 누락
- `UNSUPPORTED_IMAGE_FORMAT`: 지원하지 않는 이미지 형식
- `OCR_FAILED`: OCR 처리 실패
- `AI_MODULE_FAILED`: AI/OCR 모듈 로드 실패
- `MATERIAL_EXTRACTION_FAILED`: 소재 혼용률 추출 실패
- `MATERIAL_NOT_FOUND`: DB에 없는 소재
- `MATERIAL_RATIO_INVALID`: 혼용률 합계 또는 비율 오류
- `WEIGHT_MISSING`: 무게 입력 누락
- `WEIGHT_INVALID`: 무게 값 오류
- `WEIGHT_RANGE_INVALID`: 최소/최대 무게 범위 오류
- `AUTH_REQUIRED`: 인증 필요
- `INTERNAL_SERVER_ERROR`: 서버 내부 오류

## POST /auth/signup

회원가입 API입니다.

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

## POST /auth/login

로그인 API입니다.

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
  "access_token": "token-value",
  "token_type": "bearer",
  "expires_in": 2592000
}
```

## POST /auth/logout

로그아웃 API입니다.

Header:

```text
Authorization: Bearer <token>
```

## POST /api/scan

의류 라벨 이미지를 업로드하면 OCR과 라벨 파싱을 수행해 소재 혼용률을 반환합니다.

이 단계에서는 의류 무게가 정해지지 않았으므로 탄소배출량을 계산하거나 저장하지 않습니다.

테스트 목적으로 OCR을 건너뛰려면 `raw_ocr_text` form field를 함께 보낼 수 있습니다.

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
    },
    {
      "original_name": "polyester",
      "standard_name": "polyester",
      "display_name": "폴리에스터",
      "ratio": 20,
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

### Material Extraction Failure

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
    "raw_ocr_preview": "wash cold do not bleach dry flat",
    "ai_success": false
  }
}
```

## POST /api/carbon/calculate

소재 혼용률과 의류 무게를 기준으로 최종 탄소배출량을 계산하고, 로그인 사용자 이력에 저장합니다.

Header:

```text
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
  "clothing_type": "short_sleeve_tshirt",
  "category": "상의",
  "raw_ocr_text": "COTTON 80% POLYESTER 20%"
}
```

`weight_grams`가 있으면 직접 입력 무게로 보고 `min_weight_grams`, `max_weight_grams`보다 우선합니다.

### Calculation

```text
혼합 소재 계수 = Σ(소재별 탄소계수 × 혼용률)
최소 탄소배출량 = 혼합 소재 계수 × 최소 무게(kg)
최대 탄소배출량 = 혼합 소재 계수 × 최대 무게(kg)
평균 탄소배출량 = (최소 + 최대) / 2
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
  "average_carbon_footprint": 1.49,
  "carbon_footprint_min": 0.85,
  "carbon_footprint_max": 2.13,
  "min_weight_grams": 100,
  "max_weight_grams": 250,
  "weight_grams": null,
  "weight_source": "range",
  "clothing_type": "short_sleeve_tshirt",
  "category": "상의",
  "unit": "kg CO2eq",
  "source": "backend",
  "calculation_scope": "material_production_estimate",
  "calculation_basis": "소재별 탄소배출계수(kg CO2eq/kg)와 의류 무게(g)를 곱해 계산했습니다.",
  "emission_factors": [
    {
      "input_name": "cotton",
      "standard_name": "cotton",
      "display_name": "면",
      "ratio": 80,
      "carbon_factor": 8.3,
      "unit": "kg CO2eq/kg textile",
      "source": "K-DPP backend material carbon factor table (development estimates)"
    },
    {
      "input_name": "polyester",
      "standard_name": "polyester",
      "display_name": "폴리에스터",
      "ratio": 20,
      "carbon_factor": 9.5,
      "unit": "kg CO2eq/kg textile",
      "source": "K-DPP backend material carbon factor table (development estimates)"
    }
  ],
  "calculation_source": "K-DPP backend material carbon factor table (development estimates)",
  "calculation_note": "현재 소재별 배출계수는 개발용 추정값입니다. 최종 발표 전 팀 승인 출처로 교체해야 합니다.",
  "saved_result_id": 13
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
    "aliases": ["면", "코튼", "cotton", "COTTON"],
    "carbon_factor": 8.3,
    "unit": "kg CO2eq/kg textile"
  }
]
```

## GET /clothing-types

의류 종류별 기본 무게 범위를 반환합니다.

### Success Response

```json
{
  "status": "success",
  "source": "backend",
  "unit": "g",
  "items": [
    {
      "id": "short_sleeve_tshirt",
      "label": "반팔 티셔츠",
      "category": "상의",
      "min_weight_grams": 100,
      "max_weight_grams": 250,
      "estimated_weight_grams": 180
    }
  ]
}
```

## GET /history

로그인 사용자의 분석 결과 목록을 최신순으로 반환합니다.

Header:

```text
Authorization: Bearer <token>
```

### Success Response

```json
{
  "status": "success",
  "history": [
    {
      "id": 13,
      "user_id": 1,
      "materials": {
        "cotton": 80,
        "polyester": 20
      },
      "carbon_footprint": 1.49,
      "carbon_footprint_min": 0.85,
      "carbon_footprint_max": 2.13,
      "min_weight_grams": 100,
      "max_weight_grams": 250,
      "unit": "kg CO2eq",
      "unknown_materials": [],
      "created_at": "2026-06-04T12:00:00"
    }
  ]
}
```

## GET /me/history

`/history`와 동일하게 로그인 사용자의 분석 결과를 반환합니다.

## POST /analyze

기존 연동 호환용 API입니다. 소재 혼용률만 받아 탄소배출계수를 계산하고 저장합니다.

최종 의류 탄소배출량은 무게 정보가 포함된 `POST /api/carbon/calculate`를 사용합니다.


---

## 변경 이력 — 2026-08-29 백엔드 개선 (담당 이관 후 1차)

### 정책 확정
- **`POST /api/scan`은 이제 인증 필수** — `Authorization: Bearer <token>` 없으면 401.
- **401/403 의미 구분 확정**: 401 = 토큰 없음·무효·만료(재로그인으로 해결).
  403 = 권한 없음(재로그인해도 해결 안 됨) — 현재는 사용하지 않고 향후
  관리자 기능 등을 위해 예약. 프론트도 403을 세션 만료로 처리하지 않도록 분리 완료.
- Authorization 헤더를 **보냈는데** 토큰이 무효·만료면 어떤 엔드포인트든 401
  (기존에는 /analyze가 익명으로 조용히 저장해 이력이 유실됐음).

### 동작 변경
- **`POST /analyze`는 계산 전용** — 더 이상 이력을 저장하지 않으며
  `saved_result_id`는 항상 null. 이력 저장은 `/api/carbon/calculate`가 유일 경로.
  (이전에는 무게 없는 소재 계수가 실제 배출량과 같은 이력에 섞였음)
- 스캔 업로드 상한 **10MB** — 초과 시 413 `PAYLOAD_TOO_LARGE`.
- 이미지 파트에 **Content-Type 필수** (jpeg/png/webp 외·누락 시 415).
- `/api/scan` 응답: 인식된 비율 합이 99.5~100.5를 벗어나면
  `ai_success=false`, `analysis_failure_reason="RATIO_INCOMPLETE"` (200 유지).
- 이력 `created_at`은 UTC 오프셋 포함 ISO 형식(`...+00:00`)으로 직렬화.
- 무게 입력 범위: 1g ~ 100,000g. NaN/Infinity는 비율·무게 모두 400으로 거부.
- 비밀번호 앞뒤 공백은 가입 시 400으로 거부(저장·검증 모두 입력 원문 사용).
- OCR 실패 502의 `detail.error`는 고정 안내 문구(내부 예외 문자열 노출 중단).

## 변경 이력 — 2026-08-29 백엔드 개선 2차 (보안)

- **액세스 토큰 해시 저장**: DB에는 토큰의 SHA-256 해시만 저장. DB 파일이
  유출돼도 세션 탈취 불가. ⚠️ 배포 시 기존 발급 토큰은 모두 무효화되어
  사용자는 재로그인이 필요함(개발 단계라 영향 없음).
- **로그인 시도 제한**: 같은 이메일로 5회 연속 실패 시 60초 잠금 →
  `429 TOO_MANY_ATTEMPTS`. 성공 시 카운터 초기화.

## 변경 이력 — 2026-08-29 교차 검토(Codex) 반영

- 스캔 형식·용량 검사를 `raw_ocr_text` 조기 반환보다 먼저 실행 (우회 차단).
- Content-Length 기반 요청 크기 조기 차단 미들웨어 추가(11MB 초과 413).
  실배포 시 프록시 client_max_body_size 병행 권장.
- 형식이 잘못된 Authorization 헤더(`Basic ...`, 빈 Bearer)는 익명이 아니라
  401로 응답. 익명 허용은 헤더가 아예 없을 때만.
- 로그인 잠금 카운터를 잠금(Lock)으로 감싸 동시 실패 유실 방지.

## 변경 이력 — 2026-08-29 교차 검토 3차 반영

- 요청 크기 제한을 스트림 기준으로 강화: Content-Length 미표기(chunked)
  요청도 상한(11MB) 초과 시 413. (buffer-and-replay ASGI 미들웨어)
- 로그인 실패 기록에 TTL(15분)과 항목 상한(1만 건) 청소 도입 — 저횟수
  기록의 무한 잔류로 인한 메모리 증가 차단.
