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
Authorization: Bearer <token>
```

스캔 1회가 곧 외부 OCR 호출 비용이므로 **로그인 사용자만 호출할 수 있습니다.**
토큰이 없거나 만료되면 401을 돌려줍니다.

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

### `material_details`의 프론트 사용 (2026-09-08 추가)

프론트는 `materials`의 키가 아니라 **`material_details[].display_name`(한글명)**을 편집 폼의
소재 키로 씁니다(`scan_result.dart` `displayMaterials` → `scan_draft_service.dart`).
그 키는 화면 표기뿐 아니라 **저장 전 프리뷰 탄소값**과 **옷장에 저장되는 건강도**를
구하는 데도 쓰이고, 저장 시 `/api/carbon/calculate`로 그대로 전송됩니다.

| 필드 | 프론트 사용처 |
| --- | --- |
| `display_name` | 편집 폼 소재명 · 로컬 계수/건강도 조회 키 · 저장 요청의 `materials` 키 |
| `standard_name` | 표시명 역조회에만 사용 (`displayNameFor`) |
| `original_name` | 표시명 역조회 기준 |
| `is_supported` | 현재 미사용 |

따라서 **`display_name` 값은 서버 소재 표(`BACKEND/init_data.py`의 `MATERIAL_SEEDS`)의
`name_ko`·`aliases` 안에 있어야 합니다.** 여기 없는 이름을 내려보내면 저장 요청이
400 `MATERIAL_NOT_FOUND`로 거부됩니다.

프론트의 로컬 추정기(`clothing_estimator.dart`)는 영문 표준명 기준의 계수표를 갖고 있어
한글 표시명을 되돌리는 별칭 표를 함께 둡니다. 이 표가 서버 시드를 따라오지 못하면
해당 소재가 기본계수 10.0으로 계산되고 잘못된 건강도가 옷장에 남습니다
(2026-09-08 이전의 실제 동작). **`BACKEND/tests/test_material_name_contract.py`가
두 표를 맞대어 검사**하므로 시드에 소재를 추가할 때는 프론트 별칭 표도 함께 갱신해야 합니다.

⚠️ 프론트 계수표의 **숫자**는 아직 서버 시드와 다릅니다(예: 울 25.0 vs 서버 13.9).
위 별칭 표는 이름 대응만 맞춘 것이라, 프리뷰 값과 저장 후 서버 값은 여전히 벌어집니다.
계수 정본을 어디에 둘지는 미결(`NEXT_WORK.md` D08).

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

> **이 표가 스캔 오류 계약의 단일 출처입니다** (2026-09-08 지정).
> `BACKEND/API_CONTRACT.md`의 error_code 목록은 백엔드 내부 참고용이며, 두 문서가
> 어긋나면 이 표가 우선합니다.
>
> **`error_code` 열은 백엔드 내부 규약이고 프론트 동작의 근거가 아닙니다.**
> `FRONTEND/lib`·`test` 전체에서 `error_code`/`errorCode` 검색 결과가 0건입니다.
> 프론트가 응답 본문에서 읽는 것은 `message`/`detail`/`error`/`reason`뿐이고,
> 그마저 화면 문구로 쓰이지 않습니다(`userMessage`는 enum 고정 문자열).
> **프론트 동작을 가르는 유일한 축은 HTTP 상태코드입니다.**

| HTTP | error_code | 프론트 처리 |
| --- | --- | --- |
| 400 | `BAD_REQUEST` | 사진 처리 실패 안내(다른 사진 선택 유도) |
| 401 | `AUTH_REQUIRED` | **세션 만료로 판정** — 로그아웃 후 재로그인 유도 |
| 403 | `AUTH_REQUIRED` | **권한 없음 안내만 표시(로그아웃하지 않음)** |
| 413 | `PAYLOAD_TOO_LARGE` | 사진 용량 초과 안내 (상한 10MB) |
| 415 | `UNSUPPORTED_IMAGE_FORMAT` | 지원하지 않는 이미지 안내 (JPEG/PNG/WebP만 허용) ※ |
| 422 | `MATERIAL_EXTRACTION_FAILED` | 소재 직접 입력 흐름 |
| 429 | `SCAN_DAILY_LIMIT` | **전용 분기 없음** — '사진을 분석하지 못했어요. 직접 입력해 주세요.'(`unknown`) + 소재 직접 입력 흐름 (2-5절) |
| 502 | `OCR_FAILED` | 소재 직접 입력 안내 + `다시 촬영` 버튼 제공 |
| 503 | `AI_MODULE_FAILED`·`SCAN_UNAVAILABLE` | **전용 분기 없음** — 아래 '그 외 5xx'와 같게 처리됨 (`SCAN_UNAVAILABLE` 은 2-5절) |
| 504 | `OCR_TIMEOUT` | 시간 초과 안내 + 직접 입력 유도 (**백엔드 미구현, 프론트만 준비됨**) |
| 500 · 그 외 5xx | — | 일시적 서버 문제 안내 (`statusCode >= 500` 폴백) |

**503에 대한 주의**: 프론트에 503 전용 case가 없어 `statusCode >= 500` 폴백을 타고
500·504와 **똑같은 문구**가 나옵니다. 이전 판에 적혀 있던 "서버/AI 모듈 문제 안내"는
구현되지 않은 내용이었습니다(2026-09-08 정정).

**503이 실제로 나는 경우**: 서버 기동 시 `from apps.text...` import 실패(`BACKEND/main.py` 의
`extract_label_text`·`ensure_label_parser`), 그리고 2026-10-07부터 서버 전체 하루 사진 분석 상한
(`SCAN_UNAVAILABLE`, 2-5절) 두 가지입니다. OCR 미설정·Vision 쪽 한도 초과·Vision 장애는 전부 **502 `OCR_FAILED`**로
나갑니다(`extract_label_text` 가 `run_ocr` 실행 중 모든 예외를 `except Exception`으로 잡음).

**504는 현재 백엔드가 내지 않고, 프론트에만 처리 경로가 있습니다**(403과 같은 형태).
AI 계층에는 타임아웃이 있으나(`ksw/ai-ocr-enhancement`의 `OCR_TIMEOUT_SECONDS = 20`)
develop에는 없고, 프론트 상한은 35초입니다.

`AI_REQUESTS.md` F-4 요청에 따라 2026-09-08에 프론트에 `case 504:`를 추가했습니다
(`scan_api_service.dart`, 브랜치 `jw/scan-partial-prefill`). 예고대로 새 enum은 만들지
않고 기존 `ScanApiErrorType.timeout`을 재사용하므로, 통신 시간 초과와 같은 문구
("분석이 예상보다 오래 걸렸어요. 다시 시도하거나 직접 입력해 주세요.")가 나갑니다.
즉 502·503과 후속 흐름은 같고 문구만 시간 초과에 맞게 달라집니다.

### 422 `detail`의 프론트 사용 (2026-09-08 추가)

직접 입력 폼은 `detail`의 아래 세 필드를 초기값으로 씁니다
(`scan_api_service.dart` → `scan_draft_service.dart` → `scan_result_view.dart`).

| 필드 | 폼 반영 | 현재 실제로 오는 값 |
| --- | --- | --- |
| `partial_materials` | 소재·혼용률 입력 줄 | **항상 `{}`** |
| `care_instruction` | 관리 지침 문구 | 항상 상수 `'라벨 표기법에 맞춰 관리하세요.'` |
| `raw_ocr_preview` | '인식된 라벨 원문' 카드 | AI가 읽어낸 라벨 글자 (상한 220자) |

**`partial_materials`는 이 경로에서 채워질 수 없습니다.** 422는 `materials`가 비었을
때만 나고(`main.py:951`), 실패 응답을 만드는 AI `failed_response`도 `materials`·`parts`를
`{}`로 고정합니다(develop·enhancement 공통). 즉 오늘 이 필드로 프리필되는 값은 없습니다.
프론트는 값이 오면 그대로 채우도록 배선만 해 뒀으므로, AI 파서가 부분 인식 결과를
실패 응답에 담기 시작하면 프론트 변경 없이 동작합니다.

`care_instruction`도 마찬가지로 지금은 상수입니다 — develop `failed_response`에는
`care_text` 키 자체가 없습니다. enhancement는 실패 시에도 `parse_care()`를 돌려 실제
지침을 담지만 키 이름이 `care_instruction`이라, 백엔드가 두 키를 모두 읽도록 함께
고쳤습니다(`main.py:950-956`).

**실제로 부분 인식이 일어나는 경로는 422가 아니라 200입니다.** 소재를 찾았으나 합계가
100이 아니면 `ai_success: false` + `analysis_failure_reason: "RATIO_INCOMPLETE"`로
**200**이 나가고, 프론트는 이미 그 소재를 폼에 채웁니다. 다만 프론트가 `ai_success`를
읽지 않아 화면에는 "스캔 완료!"로 표시되고, 저장 단계에서야 합계 경고를 만납니다
(미해결, 백로그).

※ **415의 WebP 허용은 백엔드 상수(`main.py:52`) 기준입니다.** AI 계층은 JPEG/PNG만 받습니다
(`ksw/ai-ocr-enhancement`의 `SUPPORTED_IMAGE_FORMATS`). 현재는 백엔드가 OCR 텍스트를
직접 다루므로 문제되지 않지만, HTTP 서비스로 전환하면 정합이 필요합니다
(`docs/AI_REQUESTS.md` F-6).

## 2-1. 인증 오류 (401 / 403)

401과 403은 **의미가 다르며 프론트 동작도 다릅니다.**

| 코드 | 의미 | 프론트 동작 |
| --- | --- | --- |
| 401 | 인증 자체가 없거나 만료됨 | 세션을 지우고 로그인 화면으로 보냄 |
| 403 | 인증은 유효하나 권한이 없음 | 안내만 표시하고 **세션은 유지** |

401만 세션 만료 경로를 타는 이유는, 403을 재로그인으로 처리하면 권한이 없는 사용자가
로그인만 반복하게 되기 때문입니다. `scan_api_service` / `carbon_api_service` /
`auth_api_models` 세 곳 모두 이 구분을 따릅니다.

> **현재 백엔드는 403을 발생시키지 않습니다.** 관리자 기능 등 권한 구분이 생길 때를 대비한
> 예약 코드이며, 프론트에만 처리 경로가 준비돼 있습니다. 백엔드에는 오류 코드 맵
> (`DEFAULT_ERROR_CODES`)에만 `403: "AUTH_REQUIRED"`로 등록돼 있습니다.

## 2-2. 로그인·가입 시도 제한 (429)

이 절의 429는 **`POST /auth/login`·`POST /auth/signup`·`POST /auth/email-code`(인증번호 요청)·`POST /auth/kakao`와 계정 관리의 재인증(2-3절)**에서 납니다. 스캔은 하루 상한에서만 429를 내고(2-5절) 탄소 계산 API는 429를 내지 않습니다.

| 항목 | 값 |
| --- | --- |
| error_code | `TOO_MANY_ATTEMPTS` |
| 잠금 기준 | 같은 이메일로 연속 **5회** 로그인 실패 |
| 잠금 시간 | **60초** |
| 실패 기록 보존 | 15분 TTL (상한 1만 건) |
| IP 기준 (로그인만) | 같은 IP에서 **15분에 30회** 로그인 실패(이메일 무관, 성공은 세지 않음) → 첫 실패부터 15분이 지날 때까지 429. IPv6는 /64 대역 단위, 공인 주소가 아니면 적용하지 않음 |
| IP 기준 (가입) | 같은 IP에서 **1시간에 20회** 가입 시도(형식 검사를 통과한 시도 — 성공·이미 가입(409) 모두 셈, 형식 오류 400은 세지 않음) → 첫 시도부터 1시간이 지날 때까지 429. 로그인 IP 기록과 따로 세고, IPv6·공인 주소 처리는 로그인과 같음 |
| 인증번호 요청 | 같은 이메일로 60초 안에 다시 요청 → `EMAIL_CODE_RESEND_TOO_SOON`, 같은 이메일 1시간 5회·24시간 10회 또는 같은 IP 1시간 20회(가입·재설정 합산) → `TOO_MANY_ATTEMPTS`. 둘 다 `detail.retry_after`(초). 상세는 `BACKEND/API_CONTRACT.md` 의 `POST /auth/email-code` |
| 카카오 로그인 | 카카오가 거부한 토큰(`SOCIAL_TOKEN_INVALID`)은 위 **로그인 IP 기록에 합산**(15분 30회, 문구도 로그인과 같음 — 카카오 계정 탈퇴 확인 포함). 새 카카오 계정은 가입 IP 기준에 세지 않음. 상세는 `BACKEND/API_CONTRACT.md` 의 `POST /auth/kakao` |

```json
{
  "status": "error",
  "error_code": "TOO_MANY_ATTEMPTS",
  "message": "로그인 시도가 너무 많습니다. 60초 후 다시 시도해 주세요."
}
```

IP 기준에 걸리면 같은 문구의 대기 시간이 "N분 후"(남은 시간을 분으로 올림)로 바뀝니다.
가입은 "가입 시도가 너무 많습니다. N분 후 다시 시도해 주세요."입니다.

프론트는 **서버가 보내는 대기 안내 문구를 그대로 표시합니다**(가입 화면도 같은 매핑). 잠금 시간이 서버 설정에
따라 달라져도 문구가 어긋나지 않게 하기 위함이며, 이 때문에 `AuthApiErrorType`에 별도
타입을 두지 않고 서버 메시지를 그대로 통과시키는 `badRequest`로 매핑합니다
(`auth_api_models.dart`의 `case 429`).

## 2-3. 계정 관리 (비밀번호 변경 / 회원 탈퇴)

둘 다 로그인 상태에서만 호출할 수 있고, 요청 본문에 비밀번호를 한 번 더 받아 재인증합니다
(카카오 계정의 탈퇴는 비밀번호 대신 카카오 로그인으로 — 아래, DECISIONS 152).
REST 관례상 탈퇴는 `DELETE`가 자연스럽지만, 프론트 공용 HTTP 헬퍼(`api_http.dart`의
`runJsonApiRequest`)가 GET/POST만 지원하므로 **POST로 통일**했습니다.

계정 종류는 로그인 응답 `user.login_methods`(`BACKEND/API_CONTRACT.md` '사용자 객체')로 나눕니다.

| `login_methods` 에 | 비밀번호 변경 | 탈퇴 확인 |
| --- | --- | --- |
| `"password"` 있음 | 보임 | 비밀번호 입력 → `{ "password": ... }` |
| `"password"` 없음(카카오 계정) | **숨김**(불러도 400 `PASSWORD_NOT_SET`) | '카카오로 확인' → 카카오 재인증 로그인(아이디·비밀번호 입력) → `{ "kakao_access_token": ... }` |

### POST /auth/password

```http
POST /auth/password
Content-Type: application/json
Authorization: Bearer <token>

{ "current_password": "...", "new_password": "..." }
```

성공하면 **그 사용자의 기존 토큰을 모두 폐기하고 새 토큰 하나를 발급**합니다.
비밀번호를 바꾸는 흔한 이유가 계정 도용 의심이므로, 변경이 실제 효력을 갖게 하기
위함입니다. 프론트는 응답의 `access_token`을 반드시 저장해야 하며, 저장에 실패하면
그 기기의 세션도 더는 쓸 수 없으므로 로그인 화면으로 되돌립니다.

응답은 로그인과 같은 형태입니다(`user`, `access_token`, `token_type`, `expires_in`).

비밀번호가 없는 카카오 계정이면(본문 모양이 맞을 때 — 칸이 빠지거나 문자열이 아니면 계정과 무관하게 422) 비밀번호를 보지 않고 **400 `PASSWORD_NOT_SET`**("비밀번호로 가입한 계정이 아닙니다.")을
냅니다. 로그인 잠금 카운터에도 남지 않습니다. 앱은 이 버튼을 숨기므로 평소엔 오지 않습니다.

### POST /auth/withdraw

```http
POST /auth/withdraw
Content-Type: application/json
Authorization: Bearer <token>

{ "password": "..." }
```

카카오 계정은 비밀번호 대신 카카오 로그인으로 확인합니다.

```http
POST /auth/withdraw
Content-Type: application/json
Authorization: Bearer <token>

{ "kakao_access_token": "..." }
```

- 계정에 맞는 칸(비밀번호 계정 `password`, 카카오 계정 `kakao_access_token`)이 없거나 `null` 이면 400 `BAD_REQUEST` 이고, 맞지 않는 칸은 무시합니다
  (두 칸 모두 문자열이나 `null` 이어야 합니다 — 다른 타입이면 계정과 무관하게 422).
  지금 앱이 보내는 `{ "password": ... }` 는 그대로 동작합니다.
- `kakao_access_token`: 탈퇴 확인 단계에서 앱이 **재인증을 강제한 카카오 로그인** —
  `UserApi.instance.loginWithKakaoAccount(prompts: [Prompt.login])`(카카오 Flutter 문서: 기존 로그인 여부와 상관없이 재인증 요청) — 으로 받은
  `OAuthToken.accessToken`. **로그인 때 받아 SDK 에 저장된 토큰을 그대로 쓰지 않습니다**(그러면 사용자 입력 없이 탈퇴됨).
  서버는 토큰이 방금 받은 것인지 알 수 없어 이 규칙을 강제하지 못합니다 — 앱이 지킵니다. 서버가 카카오에 물어
  우리 앱이 받은 토큰인지, 그리고 **이 계정의 카카오 회원번호인지** 확인합니다. 형식 규칙과 카카오 응답을 나누는 표는
  `BACKEND/API_CONTRACT.md` 의 `POST /auth/kakao` 와 같습니다.
- 카카오 계정의 검사 순서: 세션(401) → 본문 모양(422) → `kakao_access_token` 칸 없음(400) → 카카오 로그인 설정(503) → 형식(400) → 로그인 IP 한도(429)
  → 카카오 토큰 확인(400 `SOCIAL_TOKEN_INVALID`·502) → 회원번호 대조(400 `SOCIAL_ACCOUNT_MISMATCH`) → 삭제 커밋 → 연결 끊기.
  카카오에 묻는 사이 다른 기기에서 탈퇴가 먼저 끝났으면 대조 전에 401(비밀번호 계정과 같음). 본문이 JSON 으로 읽히지 않으면 FastAPI 가 세션보다 먼저 422 를 냅니다(모든 API 같음).
- 횟수 제한: 비밀번호와 달리 추측할 수 없어 **이메일 로그인 잠금 카운터(5회/60초)는 쓰지 않습니다**. 카카오에 묻기 전에 로그인 IP 기록에 한 번을 세고,
  `SOCIAL_TOKEN_INVALID` 일 때만 남기고 나머지(성공·`SOCIAL_ACCOUNT_MISMATCH`·502·서버 오류)는 되돌립니다(2-2절).
- 카카오 계정은 확인 → 계정 삭제 커밋 → 그 토큰으로 **서버가 카카오 연결 끊기**(`POST https://kapi.kakao.com/v1/user/unlink`) 순서입니다.
  연결 끊기가 실패해도 탈퇴는 성공으로 응답합니다(서버 로그만 — 그때 카카오 쪽에 연결이 남고, 다음 카카오 로그인은 새 계정).
  **앱은 카카오 연결 끊기를 따로 부르지 않습니다.**

성공하면 `users`, 그 사용자의 `access_tokens`, `analysis_results`(카카오 계정은 소셜 연결 기록도)를 **한 트랜잭션에서
모두 삭제**합니다. 외래키에 `ON DELETE`가 걸려 있지 않아 애플리케이션이 직접 지웁니다.
프론트는 서버 삭제가 성공한 뒤에만 기기의 계정 전용 옷장(`closet_items_account_*`)을
지웁니다. 같은 이메일로 다시 가입할 수 있고, 같은 카카오 계정으로 다시 로그인하면 새 계정이 됩니다.

### 오류 코드

| HTTP | 의미 | 프론트 처리 |
| --- | --- | --- |
| 400 | 재인증 실패(현재 비밀번호·탈퇴 비밀번호 불일치), 새 비밀번호 규칙 위반, 기존과 동일 | **대화상자를 닫지 않고 해당 필드에 표시**(입력 유지) |
| 401 | 토큰이 없거나 만료됨 | 세션 정리 후 로그인 화면. **탈퇴 흐름의 401도 탈퇴되지 않은 것으로 보고 기기 옷장은 남긴다**(아래 ⚠️) |
| 429 | 같은 계정으로 재인증 5회 실패 | 서버의 대기 안내 문구를 그대로 표시 |

카카오 계정 탈퇴에만 있는 응답(`error_code` 로 나눕니다 — 모두 **삭제 전에** 나므로 탈퇴는 진행되지 않은 것):

| HTTP | `error_code` | 의미 | 프론트 처리 |
| --- | --- | --- | --- |
| 400 | `SOCIAL_TOKEN_INVALID` | 카카오가 토큰을 거부했거나 다른 앱이 받은 토큰 | 대화상자 유지, 카카오 로그인부터 다시 |
| 400 | `SOCIAL_ACCOUNT_MISMATCH` | 이 계정과 다른 카카오 계정으로 로그인함 | 대화상자 유지, 가입한 카카오 계정으로 다시 |
| 502 | `SOCIAL_PROVIDER_UNAVAILABLE` | 카카오가 응답하지 않음 | 진행되지 않았다고 안내(결과를 모르는 서버 오류와 다름) |
| 503 | `SOCIAL_LOGIN_UNAVAILABLE` | 서버에 카카오 설정이 없음 | 서버 문구 |
| 429 | `TOO_MANY_ATTEMPTS` | 같은 IP 로그인 실패 한도(2-2절) | 서버 문구 그대로 |

**비밀번호 재인증도 로그인과 같은 잠금 카운터를 씁니다**(2-2절, 5회/60초 — 카카오 계정의 탈퇴 확인은 위 예외). 토큰만 탈취한 공격자가
이 경로로 비밀번호를 무제한 추측하면 로그인 잠금이 무의미해지고, 맞히는 순간
다른 세션이 모두 끊겨 계정을 통째로 빼앗기기 때문입니다. 실패는 `record_login_failure`로
기록되고 성공하면 `clear_login_failures`로 지워집니다.

⚠️ **재인증 실패에 401을 쓰지 않는 이유**: 이 앱은 401을 "세션 만료"로 보고
`SessionExpiryHandler`로 강제 로그아웃합니다(2-1절). 비밀번호를 한 번 잘못 친 것만으로
로그아웃되면 안 되므로, 재인증 실패는 400으로 내립니다(카카오 탈퇴 확인 실패도 400). 로그인한 요청에서 401은 세션 유효성 판정 전용입니다
(로그인 API — `POST /auth/login`·`POST /auth/kakao` — 의 401 은 자격 거부이고 로그인 화면에서 안내합니다).

⚠️ **탈퇴의 401은 '계정이 이미 없다'는 뜻이 아닙니다**: 다른 기기의 비밀번호 변경(기존 토큰 전부 폐기)이나
만료로 토큰만 사라진 경우에도 401이 오고, 그때 계정과 분석 이력은 서버에 그대로 남습니다. 탈퇴가 그 사용자의
토큰을 모두 지우므로, 응답이 유실돼 다시 보낸 탈퇴도 같은 `get_current_access_token` 에서 **본문까지 같은**
401을 받아 서버 응답으로는 둘을 구분할 수 없습니다(`BACKEND/tests/test_withdraw_revoked_token.py`).
그래서 앱은 탈퇴됐다고 안내하지 않고, 같은 대화상자에서 앞선 시도가 결과를 모른 채 끝났으면(네트워크·시간 초과·
서버 오류) "처리됐는지 확인하지 못했다"고, 아니면 "진행되지 않았다"고 알린 뒤 다시 로그인해 탈퇴하도록 안내합니다.

새 비밀번호 규칙은 회원가입과 동일합니다(8자 이상, 앞뒤 공백 금지 —
`main.py`의 `ensure_password_rules`). 프론트도 같은 규칙으로 먼저 걸러
불필요한 왕복을 줄입니다.

### 알려진 한계 (탈퇴 동시성)

기기 A의 `/api/carbon/calculate`가 토큰 검증을 통과한 직후 기기 B에서 탈퇴가 커밋되면,
A의 이력 INSERT가 외래키 위반(`fk_analysis_results_user_id_users`)으로 실패하고 **A는 500을 받습니다**.
탈퇴가 아직 커밋 전이면 A의 INSERT는 탈퇴 커밋까지 기다렸다가 같은 이유로 실패합니다.
계정이 이미 없으니 저장하지 않는 것은 맞고, 응답 코드를 401로 바꿀지는 정하지 않았습니다.
두 요청이 거의 동시에 겹쳐야 일어납니다.

SQLite 때 있던 두 경합 — 지워진 `user_id`로 고아 행이 남는 것, 마지막 가입자가 탈퇴한 뒤
새 가입자가 같은 `users.id`를 받아 `/me/history`에 이전 계정 이력이 보이는 것 — 은 PostgreSQL에서
생기지 않습니다. 외래키가 강제되고, `id`는 시퀀스라 지운 번호를 다시 주지 않습니다.

## 2-4. 입력 상한과 조회 상한

계산 비용이 입력 소재 수에 비례해 반복되므로, 개수와 길이에 상한을 둡니다.
상한이 없으면 요청 1건이 워커를 오래 점유할 수 있습니다(무인증 `/analyze` 포함).

| 대상 | 상한 | 근거 |
| --- | --- | --- |
| `materials` 항목 수 | **20개** | 실제 케어 라벨의 소재는 몇 개를 넘지 않음 |
| 소재 이름 길이 | **64자** | 오류 응답 크기의 상한이기도 함 |
| `raw_ocr_text` 길이 | **4000자** | 라벨 OCR 원문이 넘을 이유가 없음. JSON 요청과 `/api/scan` 폼 필드 모두(2026-10-05부터 폼에도) |
| `email` 길이 (가입·로그인·`/auth/email-code`·`/auth/password-reset`) | **254자** | 주소 표준의 최대 길이. 로그인 실패 기록·인증번호 기록의 키라 메모리 상한이기도 함 |
| 비밀번호 길이 (가입·로그인·`/auth/password` 의 현재·새·`/auth/withdraw`·`/auth/password-reset` 의 새) | **128자** | 앱 입력이 닿지 않는 안전선 |
| `nickname` 길이 (가입·`/auth/kakao`) | **50자** | 저장·응답에 그대로 실리는 값. 카카오에서 받아 온 닉네임이 넘으면 422 대신 `SOCIAL_NICKNAME_REQUIRED` |
| `/history`·`/me/history` 반환 건수 | **200건** | 전건 적재를 막음. 잘리면 `has_more: true` |

인증 입력의 길이 상한(2026-10-05)은 앞뒤 공백을 지우기 전 글자 수로 셉니다. 실제 사용자가
닿지 않는 안전선이라 가입의 형식 검사(400, 한국어 문구)와 달리 아래 422 로 거부합니다 — 앱은
400·422 를 같은 '입력 확인'으로 보여 줍니다. 422 는 핸들러 전에 나므로 로그인 잠금·IP 한도에
세지 않습니다(가입이 같은 상한을 쓰므로 상한을 넘는 값으로 맞출 계정이 없음). 인증번호 요청·비밀번호
찾기도 같아서 번호·이메일 한도·IP 한도·하루 발송 상한·틀린 횟수 어디에도 남지 않습니다. 이 칸들에 온
짝 없는 서로게이트(`\ud800` 이스케이프)도 같은 422 입니다.

상한 위반은 **422 `VALIDATION_ERROR`** 입니다. 이 응답은 위치·사유만 담고
거부된 입력 원문은 돌려주지 않습니다. 큰 요청이 큰 응답으로 되돌아오는
증폭을 막기 위함이며, 오류 항목도 20개까지만 싣습니다.

`/me/history` 응답에 `has_more`가 추가됐습니다. 프론트는 현재 이 값을 쓰지 않고
전건을 받는 전제로 동작하며, 200건 상한에서는 화면 동작에 차이가 없습니다.

## 2-5. 사진 분석 하루 상한 (429 / 503)

스캔 한 번이 Google Vision 호출 1~4건이고 월 1,000건을 넘으면 요금이 나가므로(2026-10-07부터),
**Vision 을 부르는 스캔**의 하루 횟수를 셉니다.

| 항목 | 값 |
| --- | --- |
| 한 계정 | 하루 **20번** → 넘으면 `429 SCAN_DAILY_LIMIT` |
| 서버 전체 | 하루 `K_DPP_SCAN_DAILY_MAX` 번(배포 서버 기본 100, 로컬은 비우면 없음) → 넘으면 `503 SCAN_UNAVAILABLE` |
| 하루 | 한국 자정(00:00 KST)에 0 부터. 두 응답 모두 `detail.retry_after` = 다음 자정까지 초 |
| 세는 것 | Vision 을 부르기 직전에 센다. 성공·422·502 모두 세고 되돌리지 않음(키가 없는 로컬·리허설 서버의 502 도 세므로 한 계정 21번째부터 429) |
| 세지 않는 것 | `raw_ocr_text` 로 OCR 을 건너뛴 요청, 413·415, OCR·라벨 파서 모듈 없음(503 `AI_MODULE_FAILED` — Vision 전에 확인), 막힌 요청 |

**프론트 처리(앱 변경 없음)**: 429 는 전용 case 가 없어 `ScanApiErrorType.unknown`
('사진을 분석하지 못했어요. 직접 입력해 주세요.'), 503 은 '그 외 5xx'('분석 서비스에 일시적인
문제가 생겼어요. 다시 시도하거나 직접 입력해 주세요.')로 종류 선택 시트 맨 위에 보이고 소재 직접
입력으로 넘어갑니다. '오늘 횟수를 다 썼다'는 이유를 보이려면 `case 429:` 를 더하면 됩니다(선택).

받아들인 한계: 한 사람이 계정을 여럿 만들어 서버 전체 상한을 다 쓰면 그날 자정까지 모든 사용자가 503
(직접 입력)입니다. 청구 최악값은 지켜지고, 운영자가 app 을 다시 띄우면 풀립니다(`deploy/README.md` 'Vision 키').

시연처럼 한 계정으로 하루 20번 넘게 찍을 날은 계정을 나눠 씁니다. 서버 전체 상한은 배포 서버의
`deploy/.env` 에서 바꾸고 app 을 다시 띄웁니다(기록이 메모리라 다시 띄우면 그날 수가 0 부터).

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

