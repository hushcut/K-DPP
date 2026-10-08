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
- `SCAN_DAILY_LIMIT`: 이 계정의 오늘 사진 분석(Vision) 횟수 소진 (429)
- `SCAN_UNAVAILABLE`: 서버 전체의 오늘 사진 분석 횟수 소진 (503)
- `MATERIAL_EXTRACTION_FAILED`: 소재 혼용률 추출 실패
- `MATERIAL_NOT_FOUND`: DB에 없는 소재
- `MATERIAL_RATIO_INVALID`: 혼용률 합계 또는 비율 오류
- `WEIGHT_MISSING`: 무게 입력 누락
- `WEIGHT_INVALID`: 무게 값 오류
- `WEIGHT_RANGE_INVALID`: 최소/최대 무게 범위 오류
- `AUTH_REQUIRED`: 인증 필요
- `INTERNAL_SERVER_ERROR`: 서버 내부 오류
- `TOO_MANY_ATTEMPTS`: 시도·요청 횟수 한도 초과(429)
- `EMAIL_CODE_RESEND_TOO_SOON`: 같은 이메일로 인증번호를 너무 빨리 다시 요청(429)
- `EMAIL_SEND_UNAVAILABLE`: 서버의 하루 인증 메일 발송 상한에 닿음(503)
- `VERIFICATION_CODE_INVALID`: 인증번호가 틀림 — 다시 입력할 기회가 남음(400)
- `VERIFICATION_CODE_RESEND_REQUIRED`: 받은 인증번호가 없거나 만료됐거나 5번 틀림 — 다시 받아야 함(400)

## POST /auth/email-code

이메일 인증번호 요청 API입니다(DECISIONS 144·147·148). 가입 전 이메일 확인과 비밀번호 찾기에 함께 씁니다.

### Request

```json
{
  "email": "user@example.com",
  "purpose": "signup"
}
```

- `purpose`: `signup`(가입) 또는 `password_reset`(비밀번호 찾기). 빠지거나 그 밖의 값이면 422 `VALIDATION_ERROR`.
- 이메일은 가입·로그인과 같이 앞뒤 공백을 지우고 소문자로 다룹니다.
- 길이 상한: `email` 254자 — 넘으면 `422 VALIDATION_ERROR`(가입·로그인과 같은 상한, 어떤 한도에도 세지 않음).

### Success Response

가입 여부와 상관없이 **같은 `purpose` 면 항상 같은 응답**입니다.

```json
{
  "status": "success",
  "message": "인증번호를 보냈습니다. 메일이 오지 않으면 주소를 확인해 주세요.",
  "expires_in": 600,
  "resend_after": 60
}
```

- `expires_in`: 번호 유효 시간(초). `resend_after`: 다시 요청할 수 있을 때까지 남은 시간(초) — 보통 60 이고,
  이번 요청으로 같은 이메일 1시간 5회·24시간 10회나 같은 IP 1시간 20회에 닿았으면 그 창이 풀릴 때까지(최대 약 24시간).
- `password_reset` 의 `message` 는 "가입된 이메일이면 인증번호를 보냈습니다. 메일이 오지 않으면 주소를 확인해 주세요."
- 새 번호를 받으면 같은 이메일·같은 용도의 이전 번호는 쓸 수 없습니다.
- 서버가 실제로 하는 일(응답에는 드러나지 않음):

  | purpose | 가입 안 된 이메일 | 가입된 이메일 |
  |---|---|---|
  | `signup` | 인증번호 메일 | '이미 가입된 이메일' 안내 메일(번호 없음, 비밀번호 찾기 안내) |
  | `password_reset` | 메일 없음 | 인증번호 메일 |

  어느 경우든 번호 기록은 똑같이 만들고 메일은 응답을 보낸 뒤 보냅니다. 그래서 이어지는 가입·재설정의 오류 응답과
  응답 시간으로도 가입 여부가 드러나지 않습니다.
- 로컬·CI·시연 서버(`K_DPP_EMAIL_DELIVERY` 를 비우거나 `log`)는 메일을 보내지 않고 번호를 서버 로그에 찍습니다. 흐름과 응답은 같습니다.

### Error Response

| 상태 | `error_code` | 언제 | `detail` 추가 값 |
|---|---|---|---|
| 400 | `BAD_REQUEST` | 이메일 형식 오류("올바른 이메일을 입력해 주세요.") | — |
| 429 | `EMAIL_CODE_RESEND_TOO_SOON` | 같은 이메일로 60초 안에 다시 요청(두 용도 합산) | `retry_after`(초) |
| 429 | `TOO_MANY_ATTEMPTS` | 같은 이메일 1시간 5회·24시간 10회, 또는 같은 IP 1시간 20회를 넘음(두 용도 합산) | `retry_after`(초) |
| 503 | `EMAIL_SEND_UNAVAILABLE` | 서버 전체 하루(UTC 날짜) 요청 상한(`K_DPP_EMAIL_DAILY_MAX`)에 닿음, 또는 서버가 기억하는 이메일 수(1만)가 가득 참(새 이메일만) | — |

- 한도 창은 가입 IP 기준(DECISIONS 142)과 같이 '그 창의 첫 요청부터 1시간·24시간'입니다. IP 기준의 IPv6 /64 묶기·공인 주소가 아니면 건너뛰기도 로그인·가입과 같습니다.
- 429·503 도 가입 여부와 무관하게 똑같이 적용됩니다.

## POST /auth/signup

회원가입 API입니다. **`POST /auth/email-code`(purpose `signup`)로 받은 인증번호가 필요합니다.** 성공해도 토큰을 주지 않습니다(가입 뒤 로그인).

### Request

```json
{
  "email": "user@example.com",
  "password": "password123",
  "nickname": "홍길동",
  "code": "123456"
}
```

길이 상한: `email` 254자, `password` 128자, `nickname` 50자 — 넘으면 `422 VALIDATION_ERROR`.
로그인·비밀번호 변경·탈퇴의 이메일·비밀번호도 같은 상한입니다(아래 2026-10-05 변경 이력).

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

### Error Response

검사 순서: 형식(이메일·닉네임·비밀번호·번호, 400) → 가입 IP 한도(429, DECISIONS 142) → 인증번호 → 이미 가입(409) → 생성. 번호는 가입에 성공했을 때만 사라집니다.

| 상태 | `error_code` | 언제 | `detail` 추가 값 |
|---|---|---|---|
| 422 | `VALIDATION_ERROR` | `code` 가 없음(인증번호 단계가 없는 앱 빌드) | — |
| 400 | `BAD_REQUEST` | 이메일·닉네임·비밀번호 형식 오류, 또는 번호가 숫자 6자리가 아님("인증번호 6자리를 입력해 주세요." — 틀린 횟수에 넣지 않음) | — |
| 400 | `VERIFICATION_CODE_INVALID` | 번호가 틀림(기회가 남음) | `remaining_attempts` |
| 400 | `VERIFICATION_CODE_RESEND_REQUIRED` | 받은 번호가 없음·10분 지남·5번째로 틀림(그 번호는 버려짐) | — |
| 409 | `CONFLICT` | 이미 가입된 이메일 — 맞는 번호를 가진 사람만 봄(같은 이메일 동시 가입 등) | — |
| 429 | `TOO_MANY_ATTEMPTS` | 같은 IP 1시간 20회(DECISIONS 142, 그대로) | — |

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

## POST /auth/password-reset

비밀번호 찾기 API입니다. `POST /auth/email-code`(purpose `password_reset`)로 받은 인증번호와 새 비밀번호를 한 번에 보냅니다.

### Request

```json
{
  "email": "user@example.com",
  "code": "123456",
  "new_password": "newpassword123"
}
```

길이 상한: `email` 254자, `new_password` 128자 — 넘으면 `422 VALIDATION_ERROR`(번호를 쓰지 않고 틀린 횟수에도 세지 않음).

### Success Response

```json
{
  "status": "success",
  "message": "비밀번호를 다시 설정했습니다. 새 비밀번호로 로그인해 주세요."
}
```

- 성공하면 그 계정의 **로그인 토큰을 모두 지우고**(모든 기기 로그아웃) 이메일 로그인 잠금을 풉니다. 새 토큰은 주지 않습니다 — 앱은 이메일을 채운 로그인 화면으로 갑니다.
- 새 비밀번호 규칙은 가입과 같습니다(8자 이상, 앞뒤 공백 불가). 기존 비밀번호와 같아도 받습니다.
- 검사 순서: 형식(400) → 인증번호 → 저장. 번호가 틀리면 비밀번호 해시를 하지 않습니다.

### Error Response

| 상태 | `error_code` | 언제 | `detail` 추가 값 |
|---|---|---|---|
| 400 | `BAD_REQUEST` | 이메일·새 비밀번호 형식 오류, 번호가 숫자 6자리가 아님 | — |
| 400 | `VERIFICATION_CODE_INVALID` | 번호가 틀림(기회가 남음) | `remaining_attempts` |
| 400 | `VERIFICATION_CODE_RESEND_REQUIRED` | 받은 번호가 없음·10분 지남·5번째로 틀림 | — |

가입 안 된 이메일에는 번호 메일이 가지 않으므로 늘 위 두 번호 오류 중 하나입니다(가입 여부가 드러나지 않음).

### 앱 연동 메모 (이메일 인증·비밀번호 찾기)

- 가입: 이메일 → '인증번호 받기' → 번호 칸·남은 시간(`expires_in`)·'다시 받기'(`resend_after` 뒤) → 닉네임·비밀번호 → 가입. 번호는 그 이메일에만 맞으므로 이메일을 고치면 번호 칸을 비웁니다.
- 비밀번호 찾기: 로그인 화면 '비밀번호 찾기' → 이메일 → 번호 → 새 비밀번호 → 로그인 화면(이메일 채움).
- 분기는 `error_code` 로: `VERIFICATION_CODE_INVALID` → 번호 칸에 남은 기회 · `VERIFICATION_CODE_RESEND_REQUIRED` → 번호 칸을 비우고 '다시 받기' · `EMAIL_CODE_RESEND_TOO_SOON` → `retry_after` 초 기다리기 · `TOO_MANY_ATTEMPTS`·`EMAIL_SEND_UNAVAILABLE` → 서버 문구.
- 서버 `message` 는 다른 API 와 같은 '~습니다' 체입니다. 앱 문구 톤은 `error_code` 로 앱이 정할 수 있습니다.
- 로컬·시연 서버에서는 메일이 가지 않고 번호가 서버 로그에 찍힙니다.
- 서버·앱 PR 은 같은 날 머지합니다(DECISIONS 147) — 서버만 먼저 들어가면 지금 앱의 가입이 422.

## POST /api/scan

의류 라벨 이미지를 업로드하면 OCR과 라벨 파싱을 수행해 소재 혼용률을 반환합니다.

이 단계에서는 의류 무게가 정해지지 않았으므로 탄소배출량을 계산하거나 저장하지 않습니다.

테스트 목적으로 OCR을 건너뛰려면 `raw_ocr_text` form field를 함께 보낼 수 있습니다.

### Request

Content-Type: `multipart/form-data`

```text
image: care-label.jpg
raw_ocr_text: COTTON 80% POLYESTER 20%  (optional, 4000자 이하)
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

### Daily Limit (429 / 503)

Google Vision 을 부르는 스캔(`raw_ocr_text` 없이 보낸 요청)은 하루 횟수를 셉니다. 하루는
한국 자정(00:00 KST)에 바뀌고, 두 응답 모두 `detail.retry_after` 에 다음 자정까지 남은 초가 있습니다.

- 한 계정 하루 **20번**(`main.SCAN_USER_DAILY_MAX`)을 넘으면 `429 SCAN_DAILY_LIMIT`.
- 서버 전체 하루 `K_DPP_SCAN_DAILY_MAX` 번(환경변수, 비우면 없음 — 배포는 필수)을 넘으면
  `503 SCAN_UNAVAILABLE`. 둘 다 닿았으면 429 를 줍니다.
- Vision 을 부르기 직전에 세고 결과(성공·422·502)와 상관없이 되돌리지 않습니다.
  `raw_ocr_text` 로 OCR 을 건너뛴 요청과 업로드 검사(413·415)·OCR 또는 라벨 파서 모듈 없음(503
  `AI_MODULE_FAILED` — 둘 다 Vision 전에 확인)으로 끝난 요청은 세지 않습니다. 막힌 요청은 Vision 을
  부르지 않습니다.

```json
{
  "status": "error",
  "error_code": "SCAN_DAILY_LIMIT",
  "message": "사진 분석은 하루 20번까지입니다. 소재를 직접 입력하거나 내일 다시 시도해 주세요.",
  "detail": {
    "message": "사진 분석은 하루 20번까지입니다. 소재를 직접 입력하거나 내일 다시 시도해 주세요.",
    "error_code": "SCAN_DAILY_LIMIT",
    "retry_after": 30512
  }
}
```

서버 전체 상한은 `"message": "오늘은 사진 분석을 더 할 수 없습니다. 소재를 직접 입력해 주세요."`,
`"error_code": "SCAN_UNAVAILABLE"` 이고 나머지 모양은 같습니다.

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

## 변경 이력 — 2026-10-04 보안 손질 (DECISIONS 139)

- **비밀번호 해시 반복 수 12만 → 60만**(PBKDF2-HMAC-SHA256, OWASP 권장값,
  `main.PASSWORD_HASH_ITERATIONS`). 저장 형식 `pbkdf2_sha256$<반복>$<salt>$<digest>`
  는 그대로라 옛 해시도 검증되고, **로그인에 성공하면 지금 반복 수로 다시 저장**
  (같은 순간 비밀번호 변경이 먼저 커밋됐으면 덮지 않음). 요청·응답 형식은 같음.
- **CORS 기본값을 '허용 출처 없음'으로**(이전 `*`). 브라우저에서 부를 때만 환경변수
  `K_DPP_CORS_ORIGINS`(쉼표 구분)에 출처를 적는다. 허용 메서드 GET·POST, 허용 헤더
  Authorization·Content-Type. 모바일 앱은 CORS 와 무관해 바뀌는 것이 없다.
- **로그인 IP 기준 추가**: 같은 IP 에서 15분에 30회 로그인 실패(이메일 무관)면 그 창이
  끝날 때까지 `429 TOO_MANY_ATTEMPTS`("로그인 시도가 너무 많습니다. N분 후 다시 시도해
  주세요."). 해시 전에 한 번을 미리 세고 성공하면 되돌려 정상 로그인은 세지 않고, 동시에
  몰아친 요청도 한도만큼만 해시까지 간다. IPv6 는 /64 단위, 공인 주소가 아니면(개발 서버·
  프록시가 주소를 가린 경우) 적용하지 않는다. 이메일별 5회·60초 잠금은 그대로.
  두 기록 모두 프로세스 메모리 — 서버 1대·uvicorn 워커 1개 전제.
- **가입 IP 기준 추가**(DECISIONS 142): `POST /auth/signup` 도 같은 IP 에서 1시간에
  20회면 첫 시도부터 1시간이 지날 때까지 `429 TOO_MANY_ATTEMPTS`("가입 시도가 너무
  많습니다. N분 후 다시 시도해 주세요."). 형식 검사(400)를 통과한 시도를 DB 조회·해시
  전에 세고 성공·이미 가입(409)도 되돌리지 않는다 — 409 가 그 이메일의 가입 여부를
  알려 주므로. 로그인 IP 기록과 따로 세고, IPv6·공인 주소 처리는 로그인과 같다.
- **API 문서를 환경변수로 끌 수 있게**(DECISIONS 142): `K_DPP_API_DOCS=off` 면
  `/docs`·`/redoc`·`/openapi.json` 이 404. 값이 없으면 켬(로컬 기본), on·off·true·false·1·0
  밖의 값이면 서버가 시작하지 않는다. 배포 서버(`deploy/compose.yaml`)는 끈다.

## 변경 이력 — 2026-10-05 인증 입력 길이 상한

- **가입·로그인·비밀번호 변경·탈퇴 입력에 길이 상한**: 이메일 254자, 비밀번호 128자
  (변경의 현재·새 비밀번호, 탈퇴 비밀번호 포함), 닉네임 50자. 넘으면 `422 VALIDATION_ERROR`
  ("요청 형식이 올바르지 않습니다.", 입력 원문은 돌려주지 않음). 앞뒤 공백을 지우기 전
  글자 수로 센다. 이전에는 본문 상한(11MB)까지 받아 가입 때 그대로 저장·응답했고,
  로그인에 실패한 이메일은 실패 기록(최대 1만 건)의 키로 메모리에 남았다.
  422 는 핸들러 전에 나므로 해시·로그인 잠금·IP 한도에 닿지 않는다.
- **`POST /api/scan` 의 `raw_ocr_text` 폼 필드에도 4000자 상한**: JSON 요청
  (`/analyze`·`/api/carbon/calculate`)에만 걸려 있던 상한을 폼에도 건다. 넘으면 422
  `VALIDATION_ERROR`. 앱은 이 필드를 보내지 않는다.

## 변경 이력 — 2026-10-07 사진 분석 하루 상한 (DECISIONS 164)

- **`POST /api/scan` 에 하루 상한**: Google Vision 을 부르는 스캔만 세어 한 계정 하루 20번이면
  `429 SCAN_DAILY_LIMIT`, 서버 전체 하루 `K_DPP_SCAN_DAILY_MAX` 번이면 `503 SCAN_UNAVAILABLE`.
  둘 다 다음 한국 자정까지 `detail.retry_after`(초). Vision 을 부르기 직전에 세고 되돌리지 않으며,
  `raw_ocr_text` 요청·업로드 검사 실패·OCR 또는 라벨 파서 모듈 없음은 세지 않는다. 기록은 프로세스
  메모리 — 서버 1대·uvicorn 워커 1개 전제, 재시작하면 그날 수가 0 부터.
- **환경변수 `K_DPP_SCAN_DAILY_MAX`**: 비우면 서버 전체 상한 없음(로컬 기본), 1 이상의 정수가 아니면
  (공백만 있는 값 포함) 서버가 시작하지 않는다. `deploy/compose.yaml` 은 필수(`deploy/.env.example` 기본 100).
- 라벨 파서 모듈이 없으면 Vision 을 부르기 **전에** 503 `AI_MODULE_FAILED`(이전에는 Vision 을 부른 뒤).
- 업로드 파일 이름이 아주 길어도 500 이 나지 않는다 — 임시 파일 확장자를 이름이 아니라 확인한 형식
  (JPEG·PNG·WEBP)에서 정한다.
- 앱 변경 없음: 429 는 '사진을 분석하지 못했어요. 직접 입력해 주세요.', 503 은 일시적 문제 문구로
  직접 입력 시트에 넘어간다(`scan_api_service.dart` 의 상태 코드 분기).

## 변경 이력 — 이메일 인증·비밀번호 찾기 (DECISIONS 144·147·148)

- 새 `POST /auth/email-code`·`POST /auth/password-reset`, `POST /auth/signup` 에 `code` 필수.
- 번호 6자리·10분·번호당 5번 틀리면 버림 · 같은 이메일 60초 뒤 재요청 · 이메일당 1시간 5회·24시간 10회, IP당 1시간 20회(두 용도 합산) · 서버 전체 하루 발송 상한.
- 번호는 HMAC-SHA256 값으로만, 프로세스 메모리에 둡니다(키도 서버가 켜질 때 만듦). 서버가 다시 켜지면 받아 둔 번호는 쓸 수 없습니다(다시 받기).
  서버 1대·uvicorn 워커 1개 전제(DECISIONS 139 와 같음) — 워커를 늘리면 맞는 번호도 틀렸다고 나옵니다.
- 가입 여부 숨기기: 번호 요청은 늘 같은 응답, 번호 기록은 똑같이 만들고 메일 내용만 다름, 메일은 응답 뒤 발송. 그래서 가입 `409` 는 맞는 번호를 가진 사람만 볼 수 있습니다.
- 환경변수: `K_DPP_EMAIL_DELIVERY`(비움·`log` = 서버 로그, 서비스 이름 = 실제 발송, 그 밖의 값 = 서버가 시작하지 않음) · `K_DPP_EMAIL_FROM`(발송할 때 필수) · `K_DPP_EMAIL_DAILY_MAX` · 발송 API 키는 compose secret `email_api_key`. 인증 자체를 끄는 설정은 없습니다.
  지금 서버는 `log` 만 받습니다 — 실제 발송 서비스·`K_DPP_EMAIL_FROM`·`email_api_key` 는 발송 도메인이 정해진 뒤 붙입니다(그때 `K_DPP_EMAIL_DAILY_MAX` 도 필수로).
- 서버 하루 상한은 UTC 날짜(한국 시각 오전 9시에 바뀜)로, 메일이 실제로 가지 않는 요청(가입 안 된 이메일의 비밀번호 찾기)까지 받아들인 요청을 모두 셉니다 — 실제 발송만 세면 상한 근처에서 가입 여부가 드러나서. 막힌 요청(429·503)은 어떤 한도에도 세지 않습니다.
- 이메일은 요청 원문 254자까지(넘으면 422 `VALIDATION_ERROR` — 위 '인증 입력 길이 상한'과 같음, 가입·번호 요청·비밀번호 찾기 모두),
  공백을 지우고 소문자로 바꾼 값도 254자까지(`İ` 처럼 소문자가 더 긴 글자), 제어 문자가 없어야 합니다(아니면 400 `BAD_REQUEST`).
  가입 닉네임과 새 비밀번호(가입·변경·찾기)도 제어 문자면 400. 짝 없는 서로게이트는 길이 상한이 붙은 칸이라 핸들러 전에 422 입니다.
  번호는 앞뒤 공백을 지우고 봅니다.
- 비밀번호 찾기 번호는 맞는 순간 사라집니다(같은 번호로 동시에 두 번 재설정할 수 없음 — 그 뒤 서버 오류가 나면 다시 받기).
- 비밀번호 찾기·변경과 겹친 요청: 옛 비밀번호를 확인하는 동안 다른 요청이 비밀번호를 바꾸면, 그 확인으로는 로그인 토큰을 받지 못하고
  (`POST /auth/login` 401 — 틀린 비밀번호와 같은 응답) 비밀번호 변경·탈퇴도 하지 못합니다(`POST /auth/password`·`/auth/withdraw` 401
  "로그인이 만료되었습니다." — 그 세션의 토큰은 이미 지워짐). 그래서 비밀번호 찾기 뒤엔 옛 비밀번호로 만든 토큰이 남지 않습니다.
- 로컬 서버 로그 예: `[email] user@example.com | [K-DPP] 가입 인증번호 | 인증번호 123456`(이미 가입된 이메일의 가입 요청은 `인증번호 없음`).
- 알려진 한계: 남이 내 이메일로 번호를 하루 한도까지 요청하면 그날은 내가 번호를 못 받습니다(이메일 기준 한도의 본래 한계 — 로그인 이메일 잠금과 같은 성격).
