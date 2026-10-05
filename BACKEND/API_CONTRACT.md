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
- `SOCIAL_TOKEN_INVALID`: 카카오가 토큰을 거부했거나(만료·잘못된 토큰) 우리 앱이 받은 토큰이 아님 — 카카오 로그인부터 다시(`/auth/kakao` 401, 탈퇴 400)
- `SOCIAL_NICKNAME_REQUIRED`: 카카오 첫 로그인인데 쓸 수 있는 닉네임이 없음 — 닉네임을 받아 다시 보냄(400)
- `SOCIAL_ACCOUNT_MISMATCH`: 탈퇴 확인에 다른 카카오 계정으로 로그인함(400)
- `SOCIAL_PROVIDER_UNAVAILABLE`: 카카오 서버가 응답하지 않음·오류(502)
- `SOCIAL_LOGIN_UNAVAILABLE`: 이 서버에 카카오 로그인이 설정되지 않음(503)
- `PASSWORD_NOT_SET`: 비밀번호가 없는 계정(카카오 계정)의 비밀번호 변경(400)

## 사용자 객체 (`user`)

가입·로그인·카카오 로그인·비밀번호 변경 응답과 `GET /history`·`GET /me/history` 의 `user` 는 모두 같은 모양입니다(DECISIONS 152).
앱 시작 때의 세션 확인·로그인 뒤 동기화도 이 `user` 를 읽으므로 같은 규칙을 따릅니다.

```json
{
  "id": 1,
  "email": "user@example.com",
  "nickname": "홍길동",
  "login_methods": ["password"]
}
```

- `login_methods`: 이 계정으로 로그인하는 방법 목록. 지금은 `["password"]`(이메일·비밀번호 계정) 또는 `["kakao"]`(카카오 계정) 둘 중 하나이고,
  나중에 `"google"` 이 더해질 수 있습니다. **목록으로 받아 '들어 있는지'로 판단하세요**(순서는 의미 없음, 모르는 값은 무시).
- `email`: 카카오 계정은 **`null`** 입니다(카카오 이메일은 받지 않음 — DECISIONS 143). 이메일 계정은 늘 문자열.
- 비밀번호 변경 버튼·탈퇴 확인 방식은 `login_methods` 에 `"password"` 가 있는지로 고릅니다(`docs/SCAN_API_CONTRACT.md` 2-3).

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
    "nickname": "홍길동",
    "login_methods": ["password"]
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
    "nickname": "홍길동",
    "login_methods": ["password"]
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

## POST /auth/kakao

카카오 로그인 API입니다(DECISIONS 140·143·152). **첫 로그인이 곧 가입**입니다 — 따로 가입 화면이나 인증번호가 없습니다.
앱이 카카오 SDK 로 로그인해 받은 카카오 액세스 토큰을 보내면, 서버가 카카오에 그 토큰이 **우리 앱이 받은 토큰인지**(`app_id`) 확인한 뒤
이메일 로그인과 같은 우리 서버 토큰을 줍니다.

### Request

```json
{
  "access_token": "카카오 SDK 로그인으로 받은 OAuthToken.accessToken",
  "nickname": "홍길동"
}
```

- `access_token`: 필수. 앞뒤 공백을 지우고 봅니다. 비었거나, 1,024자를 넘거나, 공백이 아닌 출력 가능한 ASCII 밖의 문자(가운데 공백·제어 문자·한글 등)가 있으면
  400 `BAD_REQUEST` — 카카오에 묻지 않고 횟수 제한에도 세지 않습니다. 탈퇴의 `kakao_access_token` 도 같은 규칙입니다.
- `nickname`: 선택(`null` 은 보내지 않은 것과 같음). **새 계정일 때만** 씁니다(이미 있는 계정이면 무시 — 닉네임 바꾸기가 아님). 보내면 가입과 같은 규칙(앞뒤 공백을 지우고 2자 이상, 쓸 수 없는 문자 없음)으로 늘 봅니다.
- `Authorization` 헤더는 보지 않습니다. 로그인한 상태에서 계정을 잇는 API 가 아니라, 늘 그 카카오 계정으로 로그인합니다.

### Success Response

```json
{
  "status": "success",
  "message": "카카오 계정으로 가입했습니다.",
  "user": {
    "id": 7,
    "email": null,
    "nickname": "홍길동",
    "login_methods": ["kakao"]
  },
  "access_token": "token-value",
  "token_type": "bearer",
  "expires_in": 2592000,
  "is_new_user": true
}
```

- 이미 있는 계정이면 `"message": "로그인되었습니다."`, `"is_new_user": false`. 나머지는 `POST /auth/login` 응답과 같습니다(토큰 30일).
- 새 계정의 닉네임: 요청의 `nickname` → 없으면 카카오 닉네임(`kakao_account.profile.nickname`, 동의 항목 '닉네임'). 카카오 닉네임은 첫 로그인 때 한 번만 가져오며,
  나중에 카카오에서 바꿔도 따라가지 않습니다. 둘 다 없거나 카카오 닉네임이 규칙(2자 이상 등)에 맞지 않으면 `SOCIAL_NICKNAME_REQUIRED`.
  카카오가 기본 닉네임(`is_default_nickname: true` — 닉네임이 카카오 운영 정책에 맞지 않아 카카오가 "닉네임을 등록해주세요"로 바꾼 것)을 주면 없는 것으로 봅니다(DECISIONS 155).
- 같은 카카오 계정으로 동시에 두 번 보내도 계정은 하나입니다(늦은 쪽은 `is_new_user: false`).
- 이메일 계정과 카카오 계정은 서로 다른 계정입니다 — 같은 사람이라도 자동으로 합치지 않습니다(DECISIONS 143).
- 서버는 카카오 회원번호만 저장하고 카카오 토큰은 저장하지 않습니다.

### Error Response

검사 순서: 본문 모양(422) → 카카오 로그인 설정(503) → 형식(400) → 로그인 IP 한도(429) → 카카오 토큰 확인(401·502) → 이미 있는 계정이면 로그인 · 없으면 닉네임(400) → 계정 만들기·로그인.

| 상태 | `error_code` | 언제 | 앱 처리 |
|---|---|---|---|
| 422 | `VALIDATION_ERROR` | `access_token` 이 빠졌거나 문자열이 아님, `nickname` 이 문자열·`null` 이 아님(가장 먼저 — 앱 버그) | 서버 문구 |
| 503 | `SOCIAL_LOGIN_UNAVAILABLE` | 서버에 카카오 앱 ID(`K_DPP_KAKAO_APP_ID`)가 없음 — 로컬·CI 기본 | 서버 문구 |
| 400 | `BAD_REQUEST` | `access_token` 이 비었거나(공백만 포함)·형식 오류, `nickname` 형식 오류(닉네임 문구는 가입과 같음) | 서버 문구 |
| 429 | `TOO_MANY_ATTEMPTS` | 같은 IP 15분 30회 로그인 실패(이메일 로그인 실패와 합산 — 아래) | 서버 문구 그대로 |
| 401 | `SOCIAL_TOKEN_INVALID` | 카카오가 토큰을 거부(만료·폐기·잘못된 형식), 또는 다른 앱이 받은 토큰(`app_id` 가 다름) | 카카오 로그인부터 다시 |
| 502 | `SOCIAL_PROVIDER_UNAVAILABLE` | 카카오가 5초 안에 답하지 않음·카카오 일시 장애·예상 밖 응답, 또는 카카오 호출이 몰려 서버의 동시 호출 상한(10건)에 닿음 | 잠시 후 다시 |
| 400 | `SOCIAL_NICKNAME_REQUIRED` | 새 계정인데 쓸 수 있는 닉네임이 없음 | 닉네임을 받아 **같은 `access_token`** + `nickname` 으로 다시 |

- 이 401 은 `POST /auth/login` 의 401 처럼 **로그인 API 가 자격을 거부한 것**입니다(로그인 화면에서 안내). 세션 만료로 처리하는 401 은 `Authorization` 을 보낸 요청의 401 뿐입니다(`docs/SCAN_API_CONTRACT.md` 2-1).
- 카카오 응답을 나누는 기준(카카오 문서의 오류 코드 — HTTP 상태가 아니라 본문 `code` 로 나눔. `-1` 은 일시 장애인데 HTTP 400 으로 옴):

  | 카카오 응답 | 우리 응답 | 로그인 IP 기록 |
  |---|---|---|
  | `-401`(무효·만료 토큰)·`-2`(잘못된 형식), 또는 정상 응답인데 `app_id` 가 우리 앱이 아님 | 401 `SOCIAL_TOKEN_INVALID` | **남김** |
  | `-1`(카카오 일시 장애)·HTTP 5xx·5초 초과·연결 실패·그 밖의 예상 밖 응답·서버의 동시 호출 상한(10건, DECISIONS 156) | 502 `SOCIAL_PROVIDER_UNAVAILABLE` | 되돌림 |

  `/v2/user/me` 도 같은 표로 나눕니다(토큰 정보와 회원번호가 다르면 502).
- 횟수 제한: **`SOCIAL_TOKEN_INVALID` 만 로그인 IP 기록에 남습니다**(15분 30회, 이메일 로그인 실패와 같은 기록 — DECISIONS 139). 카카오에 묻기 전에 한 번을 세고,
  성공·`SOCIAL_NICKNAME_REQUIRED`·502·서버 오류면 되돌립니다. IPv6 /64 묶기·공인 주소가 아니면 건너뛰기도 로그인과 같습니다.
  카카오 응답을 기다리는 동안(최대 10초)은 그 요청이 한 번으로 세어져 있어, 같은 IP 에서 30건이 동시에 기다리면 31번째는 실패가 없어도 429 입니다(받아들인 한계).
  **새 카카오 계정은 가입 IP 한도(1시간 20회, DECISIONS 142)에 세지 않습니다** — 계정마다 실제 카카오 계정이 필요하고, 한 와이파이에서 여럿이 처음 로그인하는 시연을 막지 않게.
- 서버가 카카오에 묻는 것: `GET https://kapi.kakao.com/v1/user/access_token_info`(회원번호·`app_id` 확인), 새 계정이면 `GET https://kapi.kakao.com/v2/user/me`(닉네임).
  호출마다 **연결부터 응답을 다 받을 때까지 5초**가 넘으면 끊고 502 — 최대 두 번이라 앱 대기(15초) 안에 끝납니다.
- 카카오 토큰은 앱(Android·iOS)에서 12시간 유효합니다(카카오 문서). 닉네임을 받은 뒤 다시 보낼 때도 같은 토큰을 쓰고, 그사이 만료됐으면 401 → 카카오 로그인부터.

### 앱 연동 메모 (카카오 로그인)

- 버튼은 로그아웃 상태의 로그인 화면에만 둡니다. SDK 는 `kakao_flutter_sdk_user`(DECISIONS 140) — 카카오톡이 있으면 카카오톡으로, 없으면 카카오계정으로 로그인한 뒤
  받은 `OAuthToken.accessToken` 을 `access_token` 으로 보냅니다. 사용자가 카카오 화면에서 취소하면 서버를 부르지 않습니다.
- 성공하면 이메일 로그인과 똑같이 `access_token`·`user` 를 저장합니다. `is_new_user` 는 환영 안내 등에 쓸 수 있습니다(선택).
- **지금 앱에서 바꿔야 하는 곳**(10-05 develop 기준 코드에서 찾은 것):
  - `AuthUser.fromJson`(`FRONTEND/lib/services/auth_api_models.dart`)이 이메일이 비면 응답을 거부합니다 → `email` 이 `null` 인 응답을 받게.
    로그인 응답뿐 아니라 시작 때 세션 확인·로그인 뒤 동기화(`/me/history` 의 `user`, `post_login_sync_service.dart`)도 같은 함수를 씁니다.
  - **옷장의 주인을 이메일로만 정합니다**(`FRONTEND/lib/closet_provider.dart` — `setUserProfile` 은 이메일이 비면 주인을 바꾸지 않고, 그때 `_persist` 는
    공용 `closet_items` 에 저장하며, 다음 실행에서 이메일 세션을 복원하면 그 공용 옷장을 이메일 계정 옷장에 합치고, `purgeAccountData` 는 주인 이메일이 비면 건너뜀).
    `AuthUser.fromJson` 만 고치면 **카카오 사용자의 옷장이 같은 기기의 다음 이메일 사용자 옷장으로 넘어가고 탈퇴해도 남습니다.**
    → 이메일 없는 계정의 옷장 키(예: 사용자 `id`)를 정하고 저장·복원·탈퇴 정리를 모두 그 키로, 공용 옷장 합치기는 이메일 계정만.
    지금 기기에는 이름·이메일만 저장하므로(`closet_storage_service.dart`) 사용자 `id`·`login_methods` 를 세션과 함께 저장해야 합니다.
  - 기기에 저장된 사용자 정보에 `login_methods` 가 없으면(이 판 이전에 로그인) `["password"]` 로 봅니다.
  - 이메일이 비면 설정 화면에 기본값 `honggildong@kdpp.com` 이 보입니다(`closet_provider.dart` `_userEmail`) → 카카오 계정은 '카카오 계정' 등으로.
  - `AuthApiException` 이 `error_code` 를 읽지 않습니다 — 이메일 인증 화면과 같은 파싱이 필요합니다.
  - 탈퇴 대화상자는 400 이 아닌 오류를 모두 '결과를 모름'으로 봅니다(`settings_screen.dart` `_earlierAttemptUnresolved`) → 카카오 탈퇴의 502·503 은
    삭제 전에 나므로 `error_code` 로 '진행되지 않음'으로 나눕니다(본문 없는 프록시 502 와 구분하려면 상태 코드가 아니라 `error_code`).
- 로그아웃은 `POST /auth/logout` 그대로입니다. 기기의 카카오 SDK 토큰을 함께 지울지는 앱이 정합니다(서버는 로그인·탈퇴 확인 때 받은 토큰만 씀).
- 설정 화면(비밀번호 변경 숨김)·카카오 계정 탈퇴는 `docs/SCAN_API_CONTRACT.md` 2-3.
- 개인정보 안내 문구에 카카오에서 받는 정보(회원번호·닉네임)를 더합니다.
- 등록 값: 앱 빌드엔 카카오 **네이티브 앱 키**, 서버엔 **앱 ID** 만(`K_DPP_KAKAO_APP_ID`, 비밀값 아님). 로컬 서버는 비어 있어 503 — 실기기로 시험할 때 로컬 `BACKEND/.env` 에 앱 ID 를 넣습니다.
- 머지: 이 서버 변경은 기능을 더하기만 합니다(기존 요청 그대로, `user` 에 칸 하나). 그래서 **이메일 인증 서버·앱 PR(같은 날, DECISIONS 147)이 들어간 뒤라면**
  카카오 서버 PR 이 카카오 앱 PR 보다 먼저 들어가도 그때의 앱은 그대로 동작합니다. 이 브랜치는 이메일 인증 위에 있어, 그 전에 들어가면 지금 앱의 가입이 422 입니다.

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

## 변경 이력 — 카카오 로그인 (DECISIONS 140·143·152)

- 새 `POST /auth/kakao`(첫 로그인이 곧 가입). 모든 `user` 응답에 `login_methods`, 카카오 계정은 `email: null`.
- `POST /auth/withdraw`: 카카오 계정은 `password` 대신 `kakao_access_token`, 성공하면 서버가 카카오 연결을 끊음. `POST /auth/password`: 카카오 계정은 400 `PASSWORD_NOT_SET`
  (둘 다 `docs/SCAN_API_CONTRACT.md` 2-3). 이메일 계정의 요청·응답은 그대로입니다(`user` 칸 하나 추가) — 하나만 바뀝니다:
  탈퇴 본문에 `password` 가 없거나 `null` 이면 422 대신 400 `BAD_REQUEST`("비밀번호를 입력해 주세요."). 지금 앱은 늘 보내므로 영향이 없습니다.
- 새 `error_code`: `SOCIAL_TOKEN_INVALID`·`SOCIAL_NICKNAME_REQUIRED`·`SOCIAL_ACCOUNT_MISMATCH`·`SOCIAL_PROVIDER_UNAVAILABLE`·`SOCIAL_LOGIN_UNAVAILABLE`·`PASSWORD_NOT_SET`.
- 환경변수 `K_DPP_KAKAO_APP_ID`(카카오 앱 ID, 숫자 — 비우면 카카오 로그인이 꺼져 503, 숫자가 아니면 서버가 시작하지 않음). 서버에 두는 카카오 비밀값은 없습니다(어드민 키를 쓰지 않음).
- DB: `users.email`·`password_hash` 를 비울 수 있게 하되 **둘은 같이 있거나 같이 없습니다**(이메일 계정은 둘 다, 카카오 계정은 둘 다 없음 — 이메일 로그인·비밀번호 찾기가
  비밀번호 없는 행을 만나지 않게. 나중에 구글 계정에 이메일을 두기로 하면 그때 리비전으로 풂). 소셜 계정 연결 표(제공자·회원번호 → 사용자, 처음부터 구글도 받게)를 Alembic 리비전(`19b7eee3b75c`)으로 더합니다.
  이 리비전의 downgrade 는 이메일이 없는 사용자(카카오 계정)가 있으면 멈춥니다 — 그 계정을 지울지는 사람이 정합니다.
- 알려진 한계: 사용자가 카카오 설정에서 우리 앱과의 연결을 끊어도 서버 계정은 남습니다(카카오의 연결 끊기 알림을 받지 않음) — 지우려면 앱에서 탈퇴.
  탈퇴 확인은 앱이 재인증 로그인(`Prompt.login`)으로 받은 토큰을 보내기로 했지만, 서버는 토큰이 방금 받은 것인지 알 수 없어 그 계정의 유효한 카카오 토큰이면 받습니다
  — 우리 서버 토큰만 가진 사람은 막지만, 기기에 저장된 카카오 토큰까지 가진 사람은 못 막습니다.
  카카오 계정에는 '모든 기기 로그아웃'이 없습니다 — 비밀번호 계정은 비밀번호 변경이 다른 기기 토큰을 모두 끊지만, 카카오 계정은 비밀번호 변경이 없고
  카카오 설정에서 연결을 끊어도 우리 서버 토큰(30일)은 남습니다. 지금은 탈퇴만 모든 토큰을 지웁니다(따로 필요해지면 그때 API 를 더함).
- 확인하지 못한 것: 연결을 끊었다 다시 이었을 때 카카오 회원번호가 같은지(같으면 예전 계정으로, 다르면 새 계정으로 로그인됨) · 닉네임 동의 항목을 비즈 앱 없이 쓸 수 있는지(카카오 앱 등록 때 확인).
