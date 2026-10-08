from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, StringConstraints
import asyncio
import certifi
import httpx
import ipaddress
import json
import math
import os
import re
import shutil
import ssl
import sys
import threading
import tempfile
from pathlib import Path
import hashlib
import hmac
import secrets
import database

AI_MODULE_PATH = Path(__file__).resolve().parents[1] / "AI" / "kdpp_ai_ocr_integrated"
if AI_MODULE_PATH.exists() and str(AI_MODULE_PATH) not in sys.path:
    sys.path.append(str(AI_MODULE_PATH))

try:
    from apps.text.ocr_text import run_ocr
except Exception:
    run_ocr = None

try:
    from apps.text.parse_label import parse_label
except Exception:
    parse_label = None

ACCESS_TOKEN_EXPIRE_DAYS = 30
# 계정마다 살아 있는 로그인 토큰(기기) 수 상한 — 넘으면 가장 오래된 토큰부터 지운다(add_access_token).
ACCESS_TOKENS_PER_USER_MAX = 10
DEFAULT_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "AUTH_REQUIRED",
    403: "AUTH_REQUIRED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_IMAGE_FORMAT",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_ATTEMPTS",
    502: "OCR_FAILED",
    503: "AI_MODULE_FAILED",
}
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
SCAN_IMAGE_SUFFIXES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
# 스캔 업로드 상한. 실기기 원본 사진(3~8MB)에 여유를 둔 값입니다.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
# 탄소 계산에 허용하는 의류 무게 상한(100kg).
MAX_WEIGHT_GRAMS = 100_000
MATERIAL_FACTOR_SOURCE = "K-DPP backend material carbon factor table (development estimates)"
CALCULATION_SCOPE = "material_production_estimate"
CLOTHING_TYPE_OPTIONS = [
    {
        "id": "short_sleeve_tshirt",
        "label": "반팔 티셔츠",
        "category": "상의",
        "min_weight_grams": 100,
        "max_weight_grams": 250,
        "estimated_weight_grams": 180,
    },
    {
        "id": "shirt_blouse",
        "label": "셔츠 / 블라우스",
        "category": "상의",
        "min_weight_grams": 150,
        "max_weight_grams": 350,
        "estimated_weight_grams": 240,
    },
    {
        "id": "long_sleeve_sweatshirt",
        "label": "긴팔 / 맨투맨",
        "category": "상의",
        "min_weight_grams": 350,
        "max_weight_grams": 750,
        "estimated_weight_grams": 520,
    },
    {
        "id": "knit",
        "label": "니트",
        "category": "상의",
        "min_weight_grams": 400,
        "max_weight_grams": 900,
        "estimated_weight_grams": 620,
    },
    {
        "id": "pants",
        "label": "바지",
        "category": "하의",
        "min_weight_grams": 450,
        "max_weight_grams": 900,
        "estimated_weight_grams": 680,
    },
    {
        "id": "skirt",
        "label": "스커트",
        "category": "하의",
        "min_weight_grams": 250,
        "max_weight_grams": 650,
        "estimated_weight_grams": 420,
    },
    {
        "id": "dress",
        "label": "원피스",
        "category": "상의",
        "min_weight_grams": 350,
        "max_weight_grams": 850,
        "estimated_weight_grams": 560,
    },
    {
        "id": "outer",
        "label": "아우터",
        "category": "상의",
        "min_weight_grams": 800,
        "max_weight_grams": 1800,
        "estimated_weight_grams": 1200,
    },
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def build_error_detail(message: str, error_code: str, **extra) -> dict:
    detail = {
        "message": message,
        "error_code": error_code,
    }
    detail.update(extra)
    return detail


def infer_error_code(status_code: int) -> str:
    if status_code >= 500:
        return DEFAULT_ERROR_CODES.get(status_code, "INTERNAL_SERVER_ERROR")
    return DEFAULT_ERROR_CODES.get(status_code, "UNKNOWN_ERROR")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 표·소재는 `alembic upgrade head` 로 만든다. 서버는 스키마를 바꾸지 않고 확인만 한다.
    database.assert_schema_current()
    yield


def parse_api_docs_enabled(value: str | None) -> bool:
    """K_DPP_API_DOCS 를 읽는다. 비어 있으면 켬, on·true·1 은 켬, off·false·0 은 끔.
    그 밖의 값이면 시작하지 않는다 — 배포 설정 오타로 문서가 조용히 켜진 채 남지 않게."""
    normalized = (value or "").strip().lower()
    if normalized in ("", "on", "true", "1"):
        return True
    if normalized in ("off", "false", "0"):
        return False
    raise ValueError(f"K_DPP_API_DOCS 는 on/off(true/false, 1/0) 중 하나여야 합니다: {value!r}")


# API 문서(/docs·/redoc·/openapi.json)는 기본으로 켜 둡니다(로컬 확인·팀원 Swagger). 배포 서버는
# K_DPP_API_DOCS=off 로 끕니다(DECISIONS 142) — 저장소가 공개라 숨길 정보는 없지만, 아무나 화면에서
# API 를 눌러 보는 창은 닫아 둡니다.
API_DOCS_ENABLED = parse_api_docs_enabled(os.getenv("K_DPP_API_DOCS"))

# 1. 앱 객체 생성
app = FastAPI(
    title="K-DPP Backend",
    description="K-DPP v1 탄소배출량 계산 API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if API_DOCS_ENABLED else None,
    redoc_url="/redoc" if API_DOCS_ENABLED else None,
    openapi_url="/openapi.json" if API_DOCS_ENABLED else None,
)

# 큰 본문은 엔드포인트에 닿기 전에 차단합니다. Content-Length만 믿으면
# Transfer-Encoding: chunked(길이 미표기) 요청이 그대로 통과하므로(교차 검토
# 지적), 실제 수신 바이트를 누적 계산해 상한 초과 즉시 413을 돌려줍니다.
# 실배포에서는 프록시(nginx 등)의 client_max_body_size도 함께 두어야 합니다.
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 1024 * 1024


class BodySizeLimitMiddleware:
    """요청 본문 상한 미들웨어.

    - Content-Length가 있으면 그 값으로 조기 차단합니다.
    - 길이 미표기(chunked) 요청은 상한까지만 직접 수신해 보고,
      초과하면 앱에 전달하지 않고 413을 반환합니다. 상한 이내면
      버퍼를 재생(replay)해 앱에 그대로 넘깁니다.
    """

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared_length = None
        for name, value in scope.get("headers") or []:
            if name == b"content-length":
                try:
                    declared_length = int(value)
                except ValueError:
                    declared_length = None

        if declared_length is not None:
            if declared_length > self.max_bytes:
                await self._send_413(send)
                return
            # 길이가 신고돼 있고 상한 이내면 버퍼링 없이 그대로 통과시킵니다.
            # (신고 길이를 속여 더 보내는 경우는 서버(h11)가 프로토콜
            #  위반으로 거부하므로 여기서 다시 세지 않습니다)
            await self.app(scope, receive, send)
            return

        # 길이 미표기: 상한까지만 수신하며 검사합니다.
        body_chunks: list[bytes] = []
        received_bytes = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            body_chunks.append(chunk)
            received_bytes += len(chunk)
            if received_bytes > self.max_bytes:
                await self._send_413(send)
                return
            if not message.get("more_body", False):
                break

        chunk_index = 0

        async def replay_receive():
            nonlocal chunk_index
            if chunk_index < len(body_chunks):
                chunk = body_chunks[chunk_index]
                chunk_index += 1
                return {
                    "type": "http.request",
                    "body": chunk,
                    "more_body": chunk_index < len(body_chunks),
                }
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)

    async def _send_413(self, send):
        body = json.dumps(
            {
                "status": "error",
                "error_code": "PAYLOAD_TOO_LARGE",
                "message": f"요청이 너무 큽니다. 이미지는 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB 이하로 올려 주세요.",
                "detail": None,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def parse_cors_origins(value: str | None) -> list[str]:
    """K_DPP_CORS_ORIGINS(쉼표 구분)를 허용 출처 목록으로 바꾼다. 비어 있으면 []."""
    if not value:
        return []
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


# 앱(iOS·Android)은 CORS 와 무관하고 브라우저에서 부르는 클라이언트가 없어, 기본은 어떤
# 출처도 허용하지 않습니다. Flutter 웹 등 브라우저로 확인할 때만 K_DPP_CORS_ORIGINS 에
# 출처를 적습니다(예: http://localhost:5000). 인증은 Bearer 토큰이라 쿠키는 쓰지 않습니다.
CORS_ALLOWED_ORIGINS = parse_cors_origins(os.getenv("K_DPP_CORS_ORIGINS"))

# CORS를 나중에 추가해야 바깥층이 되어 413 응답에도 CORS 헤더가 붙습니다.
app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail

    if isinstance(detail, dict):
        message = detail.get("message", "요청을 처리할 수 없습니다.")
    else:
        message = str(detail)

    error_code = infer_error_code(exc.status_code)
    if isinstance(detail, dict):
        error_code = detail.get("error_code") or error_code
        if error_code == "BAD_REQUEST" and detail.get("unknown_materials"):
            error_code = "MATERIAL_NOT_FOUND"
        if error_code == "BAD_REQUEST" and detail.get("partial_materials"):
            error_code = "MATERIAL_RATIO_INVALID"

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "error_code": error_code,
            "message": message,
            "detail": detail,
        },
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_code_handler(
    request: Request,
    exc: RequestValidationError,
):
    error_code = "VALIDATION_ERROR"
    message = "요청 형식이 올바르지 않습니다."

    for error in exc.errors():
        if "image" in error.get("loc", ()):
            error_code = "IMAGE_MISSING"
            message = "이미지 파일을 첨부해 주세요."
            break

    # exc.errors()의 각 항목에는 거부된 입력 원문이 통째로 들어 있습니다.
    # 그대로 돌려주면 큰 요청 하나가 그만큼 큰 응답으로 되돌아와(증폭) 오히려
    # 부담이 되므로, 위치와 사유만 남기고 개수도 제한합니다.
    safe_errors = [
        {key: value for key, value in error.items() if key in ("loc", "msg", "type")}
        for error in exc.errors()[:20]
    ]

    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "error_code": error_code,
            "message": message,
            "detail": safe_errors,
        },
    )


# 2. DB 세션 가져오기 함수 (DB 연결용)
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 3. 데이터 규격 정의 (Pydantic: 프런트엔드와 주고받을 형식)
# 인증 입력의 길이 상한. 상한이 없으면 본문 상한(11MB)만큼의 문자열이 가입 때 그대로
# 저장·응답되고, 로그인 실패 기록(최대 1만 칸)의 키로 메모리에 남습니다. 실제 사용자가
# 닿지 않는 안전선이라 다른 입력 상한처럼 422 로 거부합니다(계약 2-4절).
MAX_EMAIL_LENGTH = 254  # 주소 표준의 최대 길이
MAX_PASSWORD_LENGTH = 128
MAX_NICKNAME_LENGTH = 50

EmailInput = Annotated[str, StringConstraints(max_length=MAX_EMAIL_LENGTH)]
PasswordInput = Annotated[str, StringConstraints(max_length=MAX_PASSWORD_LENGTH)]
NicknameInput = Annotated[str, StringConstraints(max_length=MAX_NICKNAME_LENGTH)]


class SignupRequest(BaseModel):
    email: EmailInput
    password: PasswordInput
    nickname: NicknameInput
    # POST /auth/email-code(purpose signup)로 받은 번호. 인증번호 단계가 없는 앱 빌드는 422.
    code: str


class EmailCodeRequest(BaseModel):
    email: EmailInput
    purpose: Literal["signup", "password_reset"]


class PasswordResetRequest(BaseModel):
    email: EmailInput
    code: str
    new_password: PasswordInput


class LoginRequest(BaseModel):
    email: EmailInput
    password: PasswordInput


class ChangePasswordRequest(BaseModel):
    current_password: PasswordInput
    new_password: PasswordInput


class KakaoLoginRequest(BaseModel):
    # 카카오 SDK 로그인으로 받은 OAuthToken.accessToken.
    access_token: str
    # 새 계정일 때만 씁니다(없으면 카카오 닉네임). 이미 있는 계정이면 무시합니다.
    nickname: NicknameInput | None = None


class WithdrawRequest(BaseModel):
    # 계정에 맞는 칸 하나만 봅니다 — 비밀번호 계정은 password, 카카오 계정은 kakao_access_token
    # (탈퇴 확인 단계에서 앱이 재인증 로그인으로 받은 토큰). 맞지 않는 칸은 무시합니다.
    password: PasswordInput | None = None
    kakao_access_token: str | None = None


# 소재 계산은 입력 소재 수에 비례해 반복되므로 개수·길이를 제한하지 않으면
# 요청 1건으로 워커를 오래 점유시킬 수 있습니다. 실제 케어 라벨의 소재는
# 많아야 몇 개이고, 오류 응답이 입력을 되돌려주는 경로도 있어 상한이 곧 응답 크기 상한입니다.
MAX_MATERIAL_ENTRIES = 20
MAX_MATERIAL_NAME_LENGTH = 64
# 라벨 OCR 원문은 수천 자를 넘을 이유가 없습니다. 상한이 없으면 요청 1건이
# 본문 상한(11MB)만큼을 그대로 DB에 적재합니다.
MAX_RAW_OCR_TEXT_LENGTH = 4000
# 이력 조회는 전건을 한 번에 올리므로 상한을 둡니다. 넘치면 has_more로 알립니다.
MAX_HISTORY_ITEMS = 200

MaterialName = Annotated[str, StringConstraints(max_length=MAX_MATERIAL_NAME_LENGTH)]
MaterialRatios = Annotated[
    dict[MaterialName, float],
    Field(max_length=MAX_MATERIAL_ENTRIES),
]
RawOcrText = Annotated[str, StringConstraints(max_length=MAX_RAW_OCR_TEXT_LENGTH)]


class AnalyzeRequest(BaseModel):
    materials: MaterialRatios
    raw_ocr_text: RawOcrText | None = None


class CarbonRangeRequest(BaseModel):
    materials: MaterialRatios
    min_weight_grams: float | None = None
    max_weight_grams: float | None = None
    weight_grams: float | None = None
    clothing_type: str | None = None
    category: str | None = None
    raw_ocr_text: RawOcrText | None = None

# 4. 소재명 매칭 및 탄소발자국 계산 함수
def normalize_email(email: str) -> str:
    return email.strip().lower()


def ensure_password_rules(password: str) -> None:
    """가입·변경에서 같은 비밀번호 규칙을 쓰도록 한곳에 모아 둔다.

    가입 때만 공백을 지우고 로그인 때는 원문을 검증하면, 공백 섞인 비밀번호로
    가입한 사용자가 영영 로그인하지 못한다. 공백 비밀번호는 아예 거부하고
    저장·검증 모두 입력 원문 그대로 사용한다.
    """
    if password != password.strip():
        raise HTTPException(status_code=400, detail="비밀번호 앞뒤에는 공백을 사용할 수 없습니다.")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상 입력해 주세요.")
    # 제어 문자·짝 없는 서로게이트는 해시(UTF-8 인코딩)·저장에서 500 을 내므로 형식 오류로 막습니다.
    if not password.isprintable():
        raise HTTPException(status_code=400, detail="비밀번호에 쓸 수 없는 문자가 있습니다.")


def nickname_rule_error(nickname: str) -> str | None:
    """닉네임(앞뒤 공백을 지운 값)이 규칙에 맞지 않으면 그 이유, 맞으면 None.
    가입·카카오 로그인(요청 닉네임과 카카오 닉네임)이 같은 규칙을 씁니다. 요청 닉네임의 상한은
    요청 모델(NicknameInput)이 먼저 422 로 막고, 여기서는 카카오에서 받아 온 닉네임에 걸립니다."""
    if len(nickname) < 2:
        return "닉네임은 2자 이상 입력해 주세요."
    if len(nickname) > MAX_NICKNAME_LENGTH:
        return f"닉네임은 {MAX_NICKNAME_LENGTH}자 이하로 입력해 주세요."
    if not nickname.isprintable():
        return "닉네임에 쓸 수 없는 문자가 있습니다."
    return None


def ensure_nickname_rules(nickname: str) -> None:
    error = nickname_rule_error(nickname)
    if error is not None:
        raise HTTPException(status_code=400, detail=error)


# PBKDF2-SHA256 반복 수(OWASP 권장값). 저장 형식에 반복 수가 들어 있어 값을 올려도
# 옛 해시는 그대로 검증되고, 로그인에 성공하면 이 값으로 다시 저장됩니다.
PASSWORD_HASH_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def password_needs_rehash(stored_hash: str) -> bool:
    """저장된 해시의 반복 수가 지금 값보다 낮으면 True."""
    try:
        _algorithm, iterations_text, _salt, _digest = stored_hash.split("$", 3)
        return int(iterations_text) < PASSWORD_HASH_ITERATIONS
    except ValueError:
        return False


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
    except ValueError:
        return False

    try:
        encoded_password = password.encode("utf-8")
    except UnicodeEncodeError:
        # 짝 없는 서로게이트 등 — 이런 비밀번호로는 가입할 수 없으므로 틀린 비밀번호입니다.
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        encoded_password,
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return secrets.compare_digest(digest, expected)


# 미가입 이메일 로그인 시에도 같은 비용의 해시 검증을 수행하기 위한 더미 해시.
DUMMY_PASSWORD_HASH = hash_password("k-dpp-timing-guard")
# 최소한의 이메일 형식 검사: 공백 없는 로컬@도메인.최상위 형태만 허용.
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def ensure_email_format(email: str) -> None:
    """가입·인증번호 요청·비밀번호 찾기의 이메일 형식 검사(정규화한 뒤의 값). 제어 문자·짝 없는
    서로게이트도 막습니다 — 각각 DB 저장·HMAC(UTF-8 인코딩)에서 500 이 나고 서버 로그 줄을 흐트러뜨려서.
    길이는 요청 모델(EmailInput)이 원문을 먼저 막지만, 소문자로 바꾸면 길어지는 글자(İ 등)가 있어
    인증번호 기록의 키가 되는 정규화한 값도 같은 상한으로 한 번 더 봅니다."""
    if (
        len(email) > MAX_EMAIL_LENGTH
        or not email.isprintable()
        or not EMAIL_PATTERN.fullmatch(email)
    ):
        raise HTTPException(status_code=400, detail="올바른 이메일을 입력해 주세요.")


# 로그인 무차별 대입 방어: 같은 이메일로 연속 실패하면 잠시 잠급니다.
# 실패 기록(아래 로그인·가입 IP 기준도)은 프로세스 메모리에 둡니다 — 서버 1대·uvicorn 워커
# 1개 전제(DECISIONS 139). 재시작하면 지워지고, 워커를 늘리면 한도가 워커 수만큼 늘어납니다.
# 아래 이메일 인증번호도 같은 전제라, 워커를 늘리면 맞는 번호도 틀렸다고 나옵니다(DECISIONS 147).
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 60
# 저횟수(1~4회) 실패 기록이 영구히 남으면 임의 이메일 반복 전송으로 메모리를
# 불릴 수 있어(교차 검토 지적), 오래된 기록과 초과분을 주기적으로 청소합니다.
LOGIN_FAILURE_TTL_SECONDS = 15 * 60
LOGIN_FAILURES_MAX_ENTRIES = 10_000
_login_failures: dict[str, tuple[int, datetime]] = {}
# 동기 엔드포인트는 스레드풀에서 병렬 실행되므로, 조회-갱신이 겹쳐
# 실패 횟수가 유실되지 않도록 잠금으로 감쌉니다(교차 검토 지적).
_login_failures_lock = threading.Lock()


def check_login_lockout(email: str) -> None:
    with _login_failures_lock:
        record = _login_failures.get(email)
        if record is None:
            return
        count, last_failure = record
        if count < LOGIN_MAX_ATTEMPTS:
            return
        unlocked_at = last_failure + timedelta(seconds=LOGIN_LOCKOUT_SECONDS)
        if utc_now() >= unlocked_at:
            # 잠금 시간이 지나면 다시 기회를 줍니다.
            _login_failures.pop(email, None)
            return

    raise HTTPException(
        status_code=429,
        detail=f"로그인 시도가 너무 많습니다. {LOGIN_LOCKOUT_SECONDS}초 후 다시 시도해 주세요.",
    )


def _prune_failure_records_locked(
    records: dict[str, tuple[int, datetime]], ttl_seconds: int
) -> None:
    """오래된 기록과 상한 초과분을 제거한다. 반드시 잠금 안에서 호출."""
    cutoff = utc_now() - timedelta(seconds=ttl_seconds)
    for key in [k for k, (_, at) in records.items() if at < cutoff]:
        del records[key]

    overflow = len(records) - LOGIN_FAILURES_MAX_ENTRIES
    if overflow > 0:
        oldest = sorted(records.items(), key=lambda kv: kv[1][1])[:overflow]
        for key, _ in oldest:
            del records[key]


def record_login_failure(email: str) -> None:
    with _login_failures_lock:
        _prune_failure_records_locked(_login_failures, LOGIN_FAILURE_TTL_SECONDS)
        count, _ = _login_failures.get(email, (0, utc_now()))
        _login_failures[email] = (count + 1, utc_now())


def clear_login_failures(email: str) -> None:
    with _login_failures_lock:
        _login_failures.pop(email, None)


# 두 번째 기준: 같은 IP 에서 이메일을 돌려 가며 찌르면 이메일별 잠금에 안 걸리고, 실패
# 한 번마다 해시(60만 회) 비용이 듭니다. 학교 와이파이처럼 여러 사람이 한 IP 를 쓰는
# 경우를 생각해 한도는 넉넉히 두고 성공한 로그인은 세지 않습니다. 해시 전에 한 번을 미리
# 세고 성공하면 되돌리므로, 동시에 몰아친 요청도 한도만큼만 해시까지 갑니다.
LOGIN_IP_MAX_FAILURES = 30
LOGIN_IP_WINDOW_SECONDS = 15 * 60
# IP(키) → (이번 창의 실패 수, 창 시작 시각)
_login_ip_failures: dict[str, tuple[int, datetime]] = {}

# 가입에도 같은 IP 기준을 둡니다(DECISIONS 142). 가입 한 번은 해시 한 번과 계정 한 줄을
# 만들고, '이미 가입된 이메일'(409) 응답은 그 이메일이 가입돼 있는지를 알려 줍니다. 그래서
# 형식 검사를 통과한 시도는 성공·409 모두 세고 되돌리지 않습니다(형식 오류 400 은 DB·해시를
# 거치지 않아 세지 않음). 로그인처럼 해시 전에 세고, 한 IP 를 여럿이 쓰는 경우를 생각해 넉넉히 둡니다.
SIGNUP_IP_MAX_ATTEMPTS = 20
SIGNUP_IP_WINDOW_SECONDS = 60 * 60
# IP(키) → (이번 창의 가입 시도 수, 창 시작 시각)
_signup_ip_attempts: dict[str, tuple[int, datetime]] = {}


def client_ip_key(host: str | None) -> str | None:
    """IP 기준의 키. IPv6 는 /64 대역으로 묶는다 — 한 가입자가 대역 안 주소를 마음대로
    바꿀 수 있어서. 공인 주소가 아니면 None(IP 기준을 건너뜀)."""
    if not host:
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if address.version == 6 and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if not address.is_global:
        # 사설·루프백 주소는 실제 사용자 주소가 아니다(개발 서버, 또는 Docker·프록시가 접속
        # 주소를 가려 모두가 게이트웨이 주소로 보이는 경우). 모두를 한 칸에 묶어 함께 막느니
        # IP 기준을 건너뛴다(로그인은 이메일 기준만, 가입은 제한 없이 남는다).
        return None
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def _reserve_ip_attempt(
    records: dict[str, tuple[int, datetime]],
    ip_key: str | None,
    max_attempts: int,
    window_seconds: int,
    action: str,
) -> None:
    """이 IP 의 이번 창 횟수가 한도에 닿았으면 429, 아니면 한 번을 미리 센다."""
    if ip_key is None:
        return
    now = utc_now()
    with _login_failures_lock:
        _prune_failure_records_locked(records, window_seconds)
        count, window_start = records.get(ip_key, (0, now))
        if count < max_attempts:
            records[ip_key] = (count + 1, window_start)
            return
        wait = window_start + timedelta(seconds=window_seconds) - now

    wait_minutes = max(1, math.ceil(wait.total_seconds() / 60))
    raise HTTPException(
        status_code=429,
        detail=f"{action} 시도가 너무 많습니다. {wait_minutes}분 후 다시 시도해 주세요.",
    )


def reserve_login_attempt_for_ip(ip_key: str | None) -> None:
    """이 IP 의 실패가 한도에 닿았으면 429, 아니면 실패 한 번을 미리 센다."""
    _reserve_ip_attempt(
        _login_ip_failures, ip_key, LOGIN_IP_MAX_FAILURES, LOGIN_IP_WINDOW_SECONDS, "로그인"
    )


def reserve_signup_attempt_for_ip(ip_key: str | None) -> None:
    """이 IP 의 가입 시도가 한도에 닿았으면 429, 아니면 한 번을 센다(되돌리지 않음)."""
    _reserve_ip_attempt(
        _signup_ip_attempts, ip_key, SIGNUP_IP_MAX_ATTEMPTS, SIGNUP_IP_WINDOW_SECONDS, "가입"
    )


def release_login_attempt_for_ip(ip_key: str | None) -> None:
    """로그인에 성공하면 미리 센 한 번을 되돌린다."""
    if ip_key is None:
        return
    with _login_failures_lock:
        record = _login_ip_failures.get(ip_key)
        if record is None:
            return
        count, window_start = record
        if count <= 1:
            del _login_ip_failures[ip_key]
        else:
            _login_ip_failures[ip_key] = (count - 1, window_start)


# --- 이메일 인증번호 (DECISIONS 144·147·148) ----------------------------------------
# 가입 전 이메일 확인과 비밀번호 찾기에 같은 6자리 번호를 씁니다. 번호·틀린 수·발송 한도는
# 위 로그인 기록처럼 프로세스 메모리에 둡니다 — 서버가 다시 켜지면 받아 둔 번호는 쓸 수 없습니다.
EMAIL_CODE_LENGTH = 6
EMAIL_CODE_PATTERN = re.compile(r"[0-9]{6}")
EMAIL_CODE_TTL_SECONDS = 10 * 60
# 번호 하나당 틀릴 수 있는 횟수. 이만큼 틀리면 그 번호를 버리고 다시 받게 합니다.
EMAIL_CODE_MAX_FAILURES = 5
# 같은 이메일로 다시 요청하기까지 기다리는 시간(두 용도 합산).
EMAIL_CODE_RESEND_SECONDS = 60
# 발송 한도(두 용도 합산). 창은 가입 IP 기준(142)처럼 그 창의 첫 요청부터 잽니다. 이메일당
# 하루 10번 × 번호당 5번이라 한 계정에 하루 50번까지만 추측할 수 있습니다(100만 가지 중).
EMAIL_CODE_EMAIL_HOURLY_MAX = 5
EMAIL_CODE_EMAIL_DAILY_MAX = 10
EMAIL_CODE_IP_HOURLY_MAX = 20
EMAIL_CODE_HOUR_SECONDS = 60 * 60
EMAIL_CODE_DAY_SECONDS = 24 * 60 * 60
# 발송 기록을 둘 이메일 수 상한. 넘치면 오래된 것을 지우지 않고(지우면 그 이메일의 한도가 풀림)
# 새 이메일의 요청을 503 으로 받지 않습니다 — IP 를 알 수 없고 하루 상한도 없는 서버에서 메모리를 묶습니다.
EMAIL_CODE_RECORDS_MAX_ENTRIES = 10_000


def parse_email_delivery(value: str | None) -> str:
    """K_DPP_EMAIL_DELIVERY 를 읽는다. 비우거나 log 면 메일을 보내지 않고 번호를 서버 로그에 찍는다.
    실제 발송 서비스는 학생 팩 도메인이 정해진 뒤 고르므로(DECISIONS 144·147) 아직 받는 이름이 없다.
    그 밖의 값이면 시작하지 않는다 — 서비스 이름 오타로 메일이 안 나가고 번호가 로그로만 남지 않게."""
    normalized = (value or "").strip().lower()
    if normalized in ("", "log"):
        return "log"
    raise ValueError(
        "K_DPP_EMAIL_DELIVERY 는 비우거나 log 여야 합니다(실제 발송 서비스는 아직 없음): "
        f"{value!r}"
    )


def parse_email_daily_max(value: str | None) -> int | None:
    """K_DPP_EMAIL_DAILY_MAX 를 읽는다. 비어 있으면 상한 없음, 1 이상의 정수면 그 값.
    그 밖의 값이면 시작하지 않는다. 실제 발송을 붙일 때 이 값을 필수로 한다(발송 서비스 무료 한도)."""
    text = (value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"[0-9]+", text) and int(text) > 0:
        return int(text)
    raise ValueError(f"K_DPP_EMAIL_DAILY_MAX 는 1 이상의 정수여야 합니다: {value!r}")


EMAIL_DELIVERY = parse_email_delivery(os.getenv("K_DPP_EMAIL_DELIVERY"))
# 서버 전체 하루 상한(DECISIONS 147 ④). 넘으면 503. 하루는 UTC 날짜(한국 시각 오전 9시에 바뀜).
# 메일을 실제로 보내지 않는 요청(가입 안 된 이메일의 비밀번호 찾기)도 셉니다 — 실제 발송만 세면
# 상한 근처에서 남은 칸이 줄었는지로 그 이메일의 가입 여부를 알아낼 수 있어서.
EMAIL_DAILY_MAX = parse_email_daily_max(os.getenv("K_DPP_EMAIL_DAILY_MAX"))

# 번호는 HMAC-SHA256 값으로만 둡니다(DECISIONS 147 ⑦). 6자리는 100만 가지뿐이라 보통 해시는
# 대입으로 바로 풀리므로, 서버가 켜질 때 만든 비밀 키를 섞습니다(키도 메모리에만 있음).
_EMAIL_CODE_KEY = secrets.token_bytes(32)


@dataclass
class _EmailCode:
    digest: bytes
    expires_at: datetime
    failures: int = 0


@dataclass
class _EmailCodeSendWindow:
    last_requested_at: datetime
    hour_start: datetime
    hour_count: int
    day_start: datetime
    day_count: int


# 확인·틀린 수 증가·소모와 한도 확인·증가를 각각 한 번의 잠금 안에서 해, 동시에 몰아친
# 요청으로 틀린 횟수나 발송 한도를 넘어서지 못하게 합니다.
_email_code_lock = threading.Lock()
# (용도, 이메일) → 살아 있는 번호 하나. 새 번호를 받으면 이전 번호를 갈아 끼웁니다.
_email_codes: dict[tuple[str, str], _EmailCode] = {}
# 이메일 → 재요청 간격·1시간·24시간 창(두 용도 합산)
_email_code_senders: dict[str, _EmailCodeSendWindow] = {}
# IP(키) → (이번 1시간 창의 요청 수, 창 시작 시각)
_email_code_ip_requests: dict[str, tuple[int, datetime]] = {}
# UTC 날짜 → 그날 받아들인 요청 수(오늘 것만 남김)
_email_daily_requests: dict[date, int] = {}


def generate_email_code() -> str:
    return f"{secrets.randbelow(10 ** EMAIL_CODE_LENGTH):0{EMAIL_CODE_LENGTH}d}"


def _email_code_digest(purpose: str, email: str, code: str) -> bytes:
    # 용도·이메일을 함께 묶어, 다른 이메일이나 다른 용도의 번호로는 맞지 않게 합니다.
    message = f"{purpose}\n{email}\n{code}".encode("utf-8")
    return hmac.new(_EMAIL_CODE_KEY, message, hashlib.sha256).digest()


def _seconds_until(moment: datetime, now: datetime) -> int:
    return max(1, math.ceil((moment - now).total_seconds()))


def _wait_text(seconds: int) -> str:
    minutes = math.ceil(seconds / 60)
    if minutes < 60:
        return f"{minutes}분"
    return f"{math.ceil(seconds / 3600)}시간"


def _prune_email_code_records_locked(now: datetime) -> None:
    """만료된 번호·지난 창을 지운다. 반드시 _email_code_lock 안에서 호출.

    기록은 한도를 통과한 요청만 만들고, 발송 기록 수는 EMAIL_CODE_RECORDS_MAX_ENTRIES 로 묶습니다.
    """
    for key in [k for k, record in _email_codes.items() if record.expires_at <= now]:
        del _email_codes[key]
    day = timedelta(seconds=EMAIL_CODE_DAY_SECONDS)
    hour = timedelta(seconds=EMAIL_CODE_HOUR_SECONDS)
    resend = timedelta(seconds=EMAIL_CODE_RESEND_SECONDS)
    # 세 창(24시간·1시간·재요청 간격)이 모두 끝난 기록만 지웁니다. 24시간 창이 끝나는 순간에도
    # 그 사이 새로 시작한 1시간 창은 살아 있을 수 있습니다.
    for key in [
        k
        for k, window in _email_code_senders.items()
        if window.day_start + day <= now
        and window.hour_start + hour <= now
        and window.last_requested_at + resend <= now
    ]:
        del _email_code_senders[key]
    for key in [k for k, (_, start) in _email_code_ip_requests.items() if start + hour <= now]:
        del _email_code_ip_requests[key]
    for day_key in [d for d in _email_daily_requests if d != now.date()]:
        del _email_daily_requests[day_key]


def issue_email_code(email: str, purpose: str, ip_key: str | None) -> tuple[str, int]:
    """한도를 모두 확인한 뒤 새 번호를 만들어 같은 이메일·용도의 이전 번호를 갈아 끼운다.
    (번호, 다음 요청까지 기다릴 초)를 돌려준다.

    어느 한도에라도 걸리면 아무것도 세지 않고 429·503 을 낸다. 가입 여부는 보지 않는다 —
    가입된 이메일이든 아니든 번호 기록과 한도 계산이 똑같아야 이어지는 응답으로도 드러나지 않는다.
    """
    # 번호·HMAC 은 아무것도 세기 전에 만듭니다(여기서 실패하면 한도만 쓰고 번호는 없는 일이 없게).
    code = generate_email_code()
    digest = _email_code_digest(purpose, email, code)
    now = utc_now()
    hour = timedelta(seconds=EMAIL_CODE_HOUR_SECONDS)
    day = timedelta(seconds=EMAIL_CODE_DAY_SECONDS)
    with _email_code_lock:
        _prune_email_code_records_locked(now)

        window = _email_code_senders.get(email)
        hour_start, hour_count, day_start, day_count = now, 0, now, 0
        if window is not None:
            resend_at = window.last_requested_at + timedelta(seconds=EMAIL_CODE_RESEND_SECONDS)
            if now < resend_at:
                retry_after = _seconds_until(resend_at, now)
                raise HTTPException(
                    status_code=429,
                    detail=build_error_detail(
                        f"인증번호는 {retry_after}초 후 다시 요청할 수 있습니다.",
                        "EMAIL_CODE_RESEND_TOO_SOON",
                        retry_after=retry_after,
                    ),
                )
            if now < window.hour_start + hour:
                hour_start, hour_count = window.hour_start, window.hour_count
            if now < window.day_start + day:
                day_start, day_count = window.day_start, window.day_count

        ip_count, ip_start = 0, now
        if ip_key is not None:
            ip_count, ip_start = _email_code_ip_requests.get(ip_key, (0, now))

        # 여러 한도에 함께 걸렸으면 모두 풀리는 때를 알려 줍니다(그 전에 다시 하면 또 막힘).
        blocked_until = []
        if hour_count >= EMAIL_CODE_EMAIL_HOURLY_MAX:
            blocked_until.append(hour_start + hour)
        if day_count >= EMAIL_CODE_EMAIL_DAILY_MAX:
            blocked_until.append(day_start + day)
        if ip_key is not None and ip_count >= EMAIL_CODE_IP_HOURLY_MAX:
            blocked_until.append(ip_start + hour)
        if blocked_until:
            retry_after = _seconds_until(max(blocked_until), now)
            raise HTTPException(
                status_code=429,
                detail=build_error_detail(
                    f"인증번호 요청이 너무 많습니다. {_wait_text(retry_after)} 후 다시 시도해 주세요.",
                    "TOO_MANY_ATTEMPTS",
                    retry_after=retry_after,
                ),
            )

        today = now.date()
        requests_today = _email_daily_requests.get(today, 0)
        records_full = (
            window is None and len(_email_code_senders) >= EMAIL_CODE_RECORDS_MAX_ENTRIES
        )
        if records_full or (EMAIL_DAILY_MAX is not None and requests_today >= EMAIL_DAILY_MAX):
            raise HTTPException(
                status_code=503,
                # 503 의 기본 error_code 는 AI_MODULE_FAILED 라 직접 넣습니다.
                detail=build_error_detail(
                    "지금은 인증 메일을 보낼 수 없습니다. 나중에 다시 시도해 주세요.",
                    "EMAIL_SEND_UNAVAILABLE",
                ),
            )

        _email_code_senders[email] = _EmailCodeSendWindow(
            last_requested_at=now,
            hour_start=hour_start,
            hour_count=hour_count + 1,
            day_start=day_start,
            day_count=day_count + 1,
        )
        if ip_key is not None:
            _email_code_ip_requests[ip_key] = (ip_count + 1, ip_start)
        _email_daily_requests[today] = requests_today + 1
        _email_codes[(purpose, email)] = _EmailCode(
            digest=digest, expires_at=now + timedelta(seconds=EMAIL_CODE_TTL_SECONDS)
        )

        # 이번 요청으로 1시간·24시간·IP 한도에 닿았으면 '다시 받기'는 그 창이 풀릴 때까지 기다려야 합니다.
        next_allowed = [now + timedelta(seconds=EMAIL_CODE_RESEND_SECONDS)]
        if hour_count + 1 >= EMAIL_CODE_EMAIL_HOURLY_MAX:
            next_allowed.append(hour_start + hour)
        if day_count + 1 >= EMAIL_CODE_EMAIL_DAILY_MAX:
            next_allowed.append(day_start + day)
        if ip_key is not None and ip_count + 1 >= EMAIL_CODE_IP_HOURLY_MAX:
            next_allowed.append(ip_start + hour)
    return code, _seconds_until(max(next_allowed), now)


def ensure_email_code_format(code: str) -> str:
    """번호가 숫자 6자리인지 본다. 아니면 400 이고 틀린 횟수에 넣지 않는다(오타로 기회를 잃지 않게)."""
    code = code.strip()
    if not EMAIL_CODE_PATTERN.fullmatch(code):
        raise HTTPException(status_code=400, detail="인증번호 6자리를 입력해 주세요.")
    return code


def check_email_code(
    email: str, purpose: str, code: str, consume: bool = False
) -> _EmailCode:
    """번호를 확인한다. 틀리면 틀린 수를 늘리고 400(5번째면 번호를 버림). 맞으면 그 기록을
    돌려준다. consume=True 면 맞는 순간 같은 잠금 안에서 지워 같은 번호로 두 번 쓰지 못하게 하고,
    아니면 다 쓴 뒤 consume_email_code 로 지운다(가입은 성공했을 때만 사라짐)."""
    key = (purpose, email)
    resend_required = HTTPException(
        status_code=400,
        detail=build_error_detail(
            "인증번호가 없거나 만료되었습니다. 인증번호를 다시 받아 주세요.",
            "VERIFICATION_CODE_RESEND_REQUIRED",
        ),
    )
    with _email_code_lock:
        record = _email_codes.get(key)
        if record is not None and record.expires_at <= utc_now():
            del _email_codes[key]
            record = None
        if record is None:
            raise resend_required
        if hmac.compare_digest(record.digest, _email_code_digest(purpose, email, code)):
            if consume:
                del _email_codes[key]
            return record
        record.failures += 1
        remaining_attempts = EMAIL_CODE_MAX_FAILURES - record.failures
        if remaining_attempts <= 0:
            del _email_codes[key]
            raise resend_required
    raise HTTPException(
        status_code=400,
        detail=build_error_detail(
            f"인증번호가 올바르지 않습니다. {remaining_attempts}번 더 입력할 수 있습니다.",
            "VERIFICATION_CODE_INVALID",
            remaining_attempts=remaining_attempts,
        ),
    )


def consume_email_code(email: str, purpose: str, record: _EmailCode) -> None:
    """확인한 번호를 지운다. 그 사이 새 번호를 받았으면 새 번호는 그대로 둔다."""
    with _email_code_lock:
        if _email_codes.get((purpose, email)) is record:
            del _email_codes[(purpose, email)]


@dataclass
class OutgoingEmail:
    to: str
    purpose: str
    subject: str
    body: str
    code: str | None  # 이미 가입된 이메일로 가는 안내 메일은 번호가 없습니다.


def compose_email_code_message(
    email: str, purpose: str, code: str, registered: bool
) -> OutgoingEmail | None:
    """가입 여부에 따라 보낼 메일을 고른다. 가입 안 된 이메일의 비밀번호 찾기는 None(보내지 않음)."""
    ignore_line = "직접 요청하지 않았다면 이 메일은 무시해 주세요."
    if purpose == "signup" and registered:
        return OutgoingEmail(
            to=email,
            purpose=purpose,
            subject="[K-DPP] 이미 가입된 이메일입니다",
            body=(
                "이 이메일로 K-DPP 가입 인증번호 요청이 있었지만 이미 가입된 계정이 있어 번호를 "
                "보내지 않았습니다.\n비밀번호가 기억나지 않으면 앱 로그인 화면의 '비밀번호 찾기'를 "
                f"이용해 주세요.\n{ignore_line}"
            ),
            code=None,
        )
    if purpose == "signup":
        return OutgoingEmail(
            to=email,
            purpose=purpose,
            subject="[K-DPP] 가입 인증번호",
            body=(
                f"K-DPP 가입 인증번호는 {code} 입니다.\n10분 안에 앱에 입력해 주세요.\n{ignore_line}"
            ),
            code=code,
        )
    if registered:
        return OutgoingEmail(
            to=email,
            purpose=purpose,
            subject="[K-DPP] 비밀번호 재설정 인증번호",
            body=(
                f"K-DPP 비밀번호 재설정 인증번호는 {code} 입니다.\n10분 안에 앱에 입력해 주세요.\n"
                f"{ignore_line} 비밀번호는 바뀌지 않습니다."
            ),
            code=code,
        )
    return None


def log_email(message: OutgoingEmail) -> None:
    """log 모드: 메일 대신 서버 로그에 찍는다(로컬·CI·시연은 여기서 번호를 본다)."""
    print(
        f"[email] {message.to} | {message.subject} | 인증번호 {message.code or '없음'}",
        file=sys.stderr,
        flush=True,
    )


def deliver_email(message: OutgoingEmail) -> None:
    # 실제 발송(도메인 인증된 서비스의 HTTPS API)은 서비스를 고른 뒤 EMAIL_DELIVERY 로 나눠 붙입니다.
    log_email(message)


def send_email_code_message(email: str, purpose: str, code: str) -> None:
    """응답을 보낸 뒤(BackgroundTasks) 가입 여부를 보고 메일을 고른다. 가입 여부 조회와 발송
    시간이 응답에 섞이지 않도록 DB 는 여기서만 본다. 응답은 이미 나갔으므로 실패는 로그로만."""
    try:
        db = database.SessionLocal()
        try:
            registered = (
                db.query(database.User.id).filter(database.User.email == email).first()
                is not None
            )
        finally:
            db.close()
        message = compose_email_code_message(email, purpose, code, registered)
        if message is None:
            if EMAIL_DELIVERY == "log":
                print(
                    f"[email] {email} | 가입되지 않은 이메일이라 비밀번호 찾기 메일을 보내지 않습니다.",
                    file=sys.stderr,
                    flush=True,
                )
            return
        deliver_email(message)
    except Exception as exc:  # noqa: BLE001 — 백그라운드 작업이라 올려 보낼 곳이 없습니다.
        print(f"[email] 인증 메일 처리 실패({purpose}): {exc!r}", file=sys.stderr, flush=True)


# --- 카카오 로그인 (DECISIONS 140·143·152·153) ------------------------------------------
# 앱이 카카오 SDK 로그인으로 받은 액세스 토큰을 보내면, 카카오에 그 토큰이 우리 앱이 받은
# 것인지(app_id) 묻고 회원번호로 계정을 찾습니다. 서버는 회원번호만 저장하고 카카오 토큰은
# 저장하지 않으며, 로그·예외 문구에도 남기지 않습니다.
KAKAO_PROVIDER = "kakao"
KAKAO_API_BASE = "https://kapi.kakao.com"
# 카카오 호출 한 번의 전체 시간(연결부터 응답을 다 받을 때까지). 한 요청에서 최대 두 번 부르므로
# 앱의 대기(15초) 안에 끝납니다.
KAKAO_CALL_TIMEOUT_SECONDS = 5.0
# 공백이 아닌 출력 가능한 ASCII 1,024자까지. 아니면 카카오에 묻지 않고 400(횟수 제한에도 안 셈).
KAKAO_TOKEN_PATTERN = re.compile(r"[!-~]{1,1024}")
# 카카오 오류 본문의 code. -401(무효·만료 토큰)·-2(잘못된 형식)는 토큰 거부, 그 밖(-1 일시 장애 등)은 502.
KAKAO_TOKEN_REJECTED_CODES = (-401, -2)
# 서버 전체의 카카오 동시 호출 상한(DECISIONS 156). 카카오가 느려지면 호출마다 스레드 풀(기본 40)의
# 작업자를 최대 5초 붙잡으므로, 넘치면 묻지 않고 곧바로 502 — 스캔·이메일 로그인·상태 확인 몫을 남깁니다.
KAKAO_MAX_CONCURRENT_CALLS = 10
_kakao_call_slots = threading.BoundedSemaphore(KAKAO_MAX_CONCURRENT_CALLS)


def parse_kakao_app_id(value: str | None) -> int | None:
    """K_DPP_KAKAO_APP_ID 를 읽는다. 비어 있으면 None(카카오 로그인 꺼짐 — 503), 1 이상의 정수면 그 값.
    그 밖의 값이면 시작하지 않는다 — 앱 키(문자열)를 잘못 넣으면 모든 토큰이 '다른 앱 것'으로 거부돼서."""
    text = (value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"[0-9]+", text) and int(text) > 0:
        return int(text)
    raise ValueError(f"K_DPP_KAKAO_APP_ID 는 카카오 앱 ID(숫자)여야 합니다: {value!r}")


# 카카오 개발자 콘솔의 앱 ID(비밀값 아님). 서버에 두는 카카오 비밀값은 없습니다(어드민 키를 쓰지 않음).
# 로컬·CI 는 비워 두어 카카오 로그인이 꺼진 채(503) 시작합니다.
KAKAO_APP_ID = parse_kakao_app_id(os.getenv("K_DPP_KAKAO_APP_ID"))


class KakaoTokenRejected(Exception):
    """카카오가 토큰을 거부했거나(-401·-2) 다른 앱이 받은 토큰 → SOCIAL_TOKEN_INVALID."""


class KakaoUnavailable(Exception):
    """카카오 일시 장애·5xx·시간 초과·연결 실패·예상 밖 응답 → 502. 문구에 토큰을 넣지 않는다."""


@dataclass
class KakaoTokenInfo:
    subject: str  # 카카오 회원번호(Long)를 문자열로
    app_id: int


# 호출마다 CA 묶음을 다시 읽지 않게 한 번만 만듭니다(httpx 기본값과 같은 certifi 묶음).
_KAKAO_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


async def _send_kakao_request(
    method: str, path: str, access_token: str, form: bool
) -> httpx.Response:
    headers = {"Authorization": f"Bearer {access_token}"}
    if form:
        # 카카오 문서가 이 헤더를 요구하는 API(사용자 정보·연결 끊기). 보내는 본문은 없습니다.
        headers["Content-Type"] = "application/x-www-form-urlencoded;charset=utf-8"
    async with httpx.AsyncClient(
        # 연결(TCP·TLS) 단계 제한을 전체 마감보다 짧게 둡니다. TLS 핸드셰이크가 멈춘 채 전체 마감의
        # 취소에 걸리면 httpcore 가 소켓을 닫지 않고 GC 를 기다리기 때문입니다(단계 제한은 닫음).
        timeout=httpx.Timeout(
            KAKAO_CALL_TIMEOUT_SECONDS, connect=KAKAO_CALL_TIMEOUT_SECONDS * 0.6
        ),
        verify=_KAKAO_SSL_CONTEXT,
        # 환경변수의 프록시·.netrc 를 따르지 않습니다 — 잘못된 프록시 값이 502 가 아닌 500 이 되지 않게.
        trust_env=False,
    ) as client:
        return await client.request(method, KAKAO_API_BASE + path, headers=headers)


def _call_kakao(method: str, path: str, access_token: str, form: bool = False) -> dict:
    """카카오 API 를 한 번 부르고 성공 본문(JSON 객체)을 돌려준다.

    연결부터 응답을 다 받을 때까지 KAKAO_CALL_TIMEOUT_SECONDS 를 넘으면 끊는다. httpx 의 timeout 은
    연결·읽기·쓰기·풀 단계마다 따로라 조금씩 오는 응답은 그것만으로 끝나지 않으므로, 이 호출만의
    이벤트 루프에서 전체에 마감을 건다(asyncio.run 과 달리 닫을 때 끝나지 않은 DNS 조회를 기다리지 않음).
    오류는 HTTP 상태가 아니라 본문 code 로 나눈다 — 일시 장애(-1)도 HTTP 400 으로 온다.
    """
    if not _kakao_call_slots.acquire(blocking=False):
        raise KakaoUnavailable(f"{path}: 동시 호출 상한({KAKAO_MAX_CONCURRENT_CALLS}건)")
    try:
        loop = asyncio.new_event_loop()
        try:
            response = loop.run_until_complete(
                asyncio.wait_for(
                    _send_kakao_request(method, path, access_token, form),
                    KAKAO_CALL_TIMEOUT_SECONDS,
                )
            )
        except (httpx.HTTPError, OSError) as exc:
            # OSError 에는 전체 마감의 TimeoutError 와, 응답을 읽는 중의 TLS 오류(ssl.SSLError —
            # httpcore 가 httpx 예외로 바꾸지 않음)가 들어 있습니다.
            raise KakaoUnavailable(f"{path}: {type(exc).__name__}") from None
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
    finally:
        _kakao_call_slots.release()

    try:
        body = response.json()
    except (ValueError, RecursionError):  # 깨진 JSON·UTF-8 아님 / 아주 깊게 중첩된 JSON
        body = None
    if response.status_code == 200 and isinstance(body, dict):
        return body
    code = body.get("code") if isinstance(body, dict) else None
    code = code if type(code) is int else None
    if code in KAKAO_TOKEN_REJECTED_CODES:
        raise KakaoTokenRejected(f"{path}: code {code}")
    raise KakaoUnavailable(f"{path}: HTTP {response.status_code}, code {code}")


def _kakao_member_id(body: dict, path: str) -> str:
    member_id = body.get("id")
    # bool 은 int 의 하위 형이라 type 으로 봅니다.
    if type(member_id) is not int or member_id <= 0:
        raise KakaoUnavailable(f"{path}: 회원번호가 없는 응답")
    return str(member_id)


def kakao_token_info(access_token: str) -> KakaoTokenInfo:
    """GET /v1/user/access_token_info — 토큰의 회원번호와 토큰을 받은 앱 ID. (테스트가 바꿔 끼움)"""
    path = "/v1/user/access_token_info"
    body = _call_kakao("GET", path, access_token)
    app_id = body.get("app_id")
    if type(app_id) is not int:
        raise KakaoUnavailable(f"{path}: 앱 ID 가 없는 응답")
    return KakaoTokenInfo(subject=_kakao_member_id(body, path), app_id=app_id)


def kakao_profile_nickname(access_token: str, subject: str) -> str | None:
    """GET /v2/user/me — 새 계정일 때만 부른다. 카카오 닉네임(동의 항목 '닉네임'), 없으면 None.
    토큰 정보와 회원번호가 다르면 예상 밖 응답(502). (테스트가 바꿔 끼움)"""
    path = "/v2/user/me"
    body = _call_kakao("GET", path, access_token, form=True)
    if _kakao_member_id(body, path) != subject:
        raise KakaoUnavailable(f"{path}: 토큰 정보와 회원번호가 다른 응답")
    account = body.get("kakao_account")
    profile = account.get("profile") if isinstance(account, dict) else None
    if not isinstance(profile, dict):
        return None
    # 카카오 운영 정책에 맞지 않는 닉네임은 카카오가 기본 닉네임("닉네임을 등록해주세요")으로 바꿔 줍니다.
    if profile.get("is_default_nickname") is True:
        return None
    nickname = profile.get("nickname")
    return nickname if isinstance(nickname, str) else None


def kakao_unlink(access_token: str) -> None:
    """POST /v1/user/unlink — 이 토큰의 사용자와 우리 앱의 연결을 끊는다(탈퇴 커밋 뒤). (테스트가 바꿔 끼움)"""
    _call_kakao("POST", "/v1/user/unlink", access_token, form=True)


def log_kakao_failure(action: str, exc: Exception) -> None:
    # 우리 예외의 문구엔 경로·응답 코드만 있습니다. 그 밖의 예외는 문구에 무엇이 들었는지 모르니 이름만.
    reason = str(exc) if isinstance(exc, (KakaoTokenRejected, KakaoUnavailable)) else type(exc).__name__
    print(f"[kakao] {action}: {reason}", file=sys.stderr, flush=True)


def ensure_kakao_login_enabled() -> None:
    if KAKAO_APP_ID is None:
        raise HTTPException(
            status_code=503,
            # 503 의 기본 error_code 는 AI_MODULE_FAILED 라 직접 넣습니다.
            detail=build_error_detail(
                "이 서버에서는 카카오 로그인을 쓸 수 없습니다.", "SOCIAL_LOGIN_UNAVAILABLE"
            ),
        )


def ensure_kakao_token_format(access_token: str) -> str:
    access_token = access_token.strip()
    if not KAKAO_TOKEN_PATTERN.fullmatch(access_token):
        raise HTTPException(
            status_code=400,
            detail="카카오 로그인 정보가 올바르지 않습니다. 카카오 로그인을 다시 해 주세요.",
        )
    return access_token


def verify_kakao_token(access_token: str) -> str:
    """카카오에 토큰을 물어 우리 앱이 받은 토큰이면 회원번호를 돌려준다."""
    info = kakao_token_info(access_token)
    if info.app_id != KAKAO_APP_ID:
        raise KakaoTokenRejected("다른 앱이 받은 토큰")
    return info.subject


def social_token_invalid(status_code: int) -> HTTPException:
    # 로그인(/auth/kakao)은 401(자격 거부), 탈퇴 확인은 400(로그인한 요청의 401 은 세션 만료 전용).
    return HTTPException(
        status_code=status_code,
        detail=build_error_detail(
            "카카오 로그인을 확인하지 못했습니다. 카카오 로그인을 다시 해 주세요.",
            "SOCIAL_TOKEN_INVALID",
        ),
    )


def social_provider_unavailable() -> HTTPException:
    return HTTPException(
        status_code=502,
        detail=build_error_detail(
            "카카오 서버가 응답하지 않습니다. 잠시 후 다시 시도해 주세요.",
            "SOCIAL_PROVIDER_UNAVAILABLE",
        ),
    )


def resolve_kakao_nickname(access_token: str, subject: str) -> str:
    """새 카카오 계정의 닉네임 — 카카오 닉네임이 없거나 가입 규칙에 맞지 않으면 400 SOCIAL_NICKNAME_REQUIRED."""
    nickname = (kakao_profile_nickname(access_token, subject) or "").strip()
    if nickname_rule_error(nickname) is not None:
        raise HTTPException(
            status_code=400,
            detail=build_error_detail("사용할 닉네임을 입력해 주세요.", "SOCIAL_NICKNAME_REQUIRED"),
        )
    return nickname


def user_login_methods(user: database.User, db: Session) -> list[str]:
    """이 계정으로 로그인하는 방법(DECISIONS 152 ③). 비밀번호가 있으면 password, 그리고 연결된 소셜 계정."""
    methods = ["password"] if user.password_hash is not None else []
    providers = (
        db.query(database.SocialAccount.provider)
        .filter(database.SocialAccount.user_id == user.id)
        .order_by(database.SocialAccount.provider)
        .all()
    )
    methods.extend(provider for (provider,) in providers)
    return methods


def auth_user_response(user: database.User, db: Session) -> dict:
    return {
        "id": user.id,
        # 카카오 계정은 None(카카오 이메일은 받지 않음 — DECISIONS 143).
        "email": user.email,
        "nickname": user.nickname,
        "login_methods": user_login_methods(user, db),
    }


def hash_access_token(token: str) -> str:
    """DB 파일이 유출돼도 토큰 원문을 알 수 없도록 해시로만 저장한다."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def add_access_token(user_id: int, db: Session) -> str:
    """토큰 행을 세션에 넣고 원문을 돌려준다(커밋은 부르는 쪽). 원문은 응답으로만, DB 엔 해시만.

    성공한 로그인은 어떤 한도에도 세지 않아 토큰 행이 끝없이 늘 수 있으므로(DECISIONS 160), 넣기 전에
    그 계정의 만료 토큰을 지우고 최근 토큰을 ACCESS_TOKENS_PER_USER_MAX - 1 개만 남긴다 — 가장 오래된
    기기는 다음 요청에서 401. 부르는 쪽이 users 행을 잠근 채(SELECT … FOR UPDATE) 불러야 같은 계정의 동시
    로그인에도 개수가 정확하다 — 로그인·비밀번호 변경은 lock_user_if_password_unchanged, 카카오 기존 계정은
    sign_in_kakao_account 의 잠금, 카카오 새 계정은 방금 만든 행이라 겹치지 않는다.
    """
    tokens = database.AccessToken
    db.query(tokens).filter(
        tokens.user_id == user_id,
        or_(tokens.expires_at.is_(None), tokens.expires_at <= utc_now()),
    ).delete(synchronize_session=False)
    older_tokens = (
        select(tokens.token)
        .where(tokens.user_id == user_id)
        .order_by(tokens.created_at.desc(), tokens.token.desc())
        .offset(ACCESS_TOKENS_PER_USER_MAX - 1)
    )
    db.query(tokens).filter(
        tokens.user_id == user_id, tokens.token.in_(older_tokens)
    ).delete(synchronize_session=False)

    raw_token = secrets.token_urlsafe(32)
    db.add(
        database.AccessToken(
            token=hash_access_token(raw_token),
            user_id=user_id,
            expires_at=utc_now() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
        )
    )
    return raw_token


def lock_user_if_password_unchanged(db: Session, user_id: int, verified_hash: str) -> bool:
    """users 행을 잠그고(SELECT … FOR UPDATE) 비밀번호 해시가 방금 검증한 값 그대로인지 본다.

    비밀번호 확인(해시, 수백 ms)과 쓰기 사이에 비밀번호 찾기·변경이 끼어들면, 옛 비밀번호로 확인한
    요청이 새 비밀번호를 덮어쓰거나 재설정 뒤에도 살아 있는 토큰을 받는다. 그래서 토큰을 만들거나
    비밀번호·계정을 바꾸는 경로는 모두 이 잠금을 먼저 잡고 다시 본다 — 잠그는 순서도 users →
    access_tokens 로 같아져 서로 교착하지 않는다. 잠금은 그 요청의 commit·rollback 까지 간다.
    """
    current_hash = (
        db.query(database.User.password_hash)
        .filter(database.User.id == user_id)
        .with_for_update()
        .scalar()
    )
    return current_hash is not None and current_hash == verified_hash


def lock_user_row(db: Session, user_id: int) -> bool:
    """비밀번호와 무관하게 users 행을 잠근다(카카오 계정 — 위 함수는 해시가 NULL 이면 늘 False).
    행이 없으면(탈퇴가 먼저 커밋됨) False. 잠그는 순서는 위와 같다(users → access_tokens)."""
    return (
        db.query(database.User.id)
        .filter(database.User.id == user_id)
        .with_for_update()
        .scalar()
        is not None
    )


def delete_user_rows(db: Session, user_id: int) -> None:
    """탈퇴: 계정과 그 토큰·분석 이력·소셜 연결을 지운다(커밋은 부르는 쪽, users 행을 잠근 뒤).
    외래 키에 ON DELETE 가 없어 users 를 마지막에 지운다."""
    for model in (database.AnalysisResult, database.AccessToken, database.SocialAccount):
        db.query(model).filter(model.user_id == user_id).delete(synchronize_session=False)
    db.query(database.User).filter(database.User.id == user_id).delete(
        synchronize_session=False
    )


def read_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None

    return token.strip()


def get_optional_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> database.User | None:
    # 헤더가 아예 없을 때만 익명으로 취급합니다. 헤더를 보냈는데 토큰이
    # 무효·만료라면 401을 돌려줘야 클라이언트가 재로그인 기회를 얻고,
    # 결과가 익명(user_id=NULL)으로 저장돼 이력에서 유실되는 것을 막습니다.
    if authorization is None or not authorization.strip():
        return None

    token = read_bearer_token(authorization)
    if token is None:
        # 'Basic ...'나 빈 Bearer처럼 형식이 잘못된 헤더를 익명으로 눙치면
        # 클라이언트 버그가 조용히 숨으므로 401로 알립니다(교차 검토 지적).
        raise HTTPException(status_code=401, detail="인증 헤더 형식이 올바르지 않습니다.")

    access_token = (
        db.query(database.AccessToken)
        .filter(database.AccessToken.token == hash_access_token(token))
        .first()
    )
    if access_token is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    if access_token.expires_at is None or access_token.expires_at <= utc_now():
        db.delete(access_token)
        db.commit()
        raise HTTPException(status_code=401, detail="로그인이 만료되었습니다. 다시 로그인해 주세요.")

    user = (
        db.query(database.User).filter(database.User.id == access_token.user_id).first()
    )
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    return user


def get_current_user(
    current_user: database.User | None = Depends(get_optional_current_user),
) -> database.User:
    if current_user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    return current_user


def get_current_access_token(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> database.AccessToken:
    token = read_bearer_token(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    access_token = (
        db.query(database.AccessToken)
        .filter(database.AccessToken.token == hash_access_token(token))
        .first()
    )
    if (
        access_token is None
        or access_token.expires_at is None
        or access_token.expires_at <= utc_now()
    ):
        if access_token is not None:
            db.delete(access_token)
            db.commit()
        raise HTTPException(status_code=401, detail="로그인이 만료되었습니다.")

    return access_token


def load_aliases(material: database.Material) -> list[str]:
    try:
        aliases = json.loads(material.aliases or "[]")
    except json.JSONDecodeError:
        return []

    if not isinstance(aliases, list):
        return []

    return [str(alias).strip().lower() for alias in aliases]


# 같은 요청 안에서 소재 표를 반복해서 읽지 않도록 Session에 색인을 캐시합니다.
_MATERIAL_INDEX_KEY = "material_index"


def load_material_index(db: Session) -> dict[str, database.Material]:
    """별칭 → 소재 사전을 만들어 Session에 캐시한다.

    이전에는 소재 이름 하나마다 전체 표를 다시 조회해 비용이
    (입력 소재 수 × 전체 소재 행)으로 곱해졌다. 한 요청에서
    validate_materials·build_emission_factors·build_material_details가
    각각 같은 순회를 반복하던 것도 이 캐시로 한 번에 줄어든다.
    Session은 요청마다 새로 만들어지므로(get_db) 캐시도 함께 사라진다.
    """
    cached = db.info.get(_MATERIAL_INDEX_KEY)

    if cached is not None:
        return cached

    index: dict[str, database.Material] = {}

    for material in db.query(database.Material).all():
        candidates = {
            material.name_ko.strip().lower(),
            material.name_en.strip().lower(),
            *load_aliases(material),
        }

        for candidate in candidates:
            # 먼저 등록된 소재가 이깁니다. 전체 순회에서 첫 일치를 반환하던
            # 이전 동작과 결과가 같도록 setdefault를 씁니다.
            index.setdefault(candidate, material)

    db.info[_MATERIAL_INDEX_KEY] = index

    return index


def find_material(db: Session, name: str):
    return load_material_index(db).get(name.strip().lower())


def validate_materials(
    materials: dict[str, float],
    db: Session,
) -> tuple[float, list[str]]:
    if not materials:
        raise HTTPException(
            status_code=400,
            detail=build_error_detail(
                "소재를 1개 이상 입력해 주세요.",
                "MATERIAL_MISSING",
            ),
        )

    for name, ratio in materials.items():
        # NaN/Infinity는 모든 대소 비교가 False라 아래 검증을 전부 통과한 뒤
        # DB 저장 단계에서 500을 일으키므로 여기서 먼저 차단합니다.
        # 오류 응답에 NaN을 그대로 되돌려주면 JSON 직렬화가 실패하므로
        # 비정상 값은 None으로 바꿔 돌려줍니다.
        if not math.isfinite(ratio) or ratio < 0:
            safe_materials = {
                key: (value if isinstance(value, (int, float)) and math.isfinite(value) else None)
                for key, value in materials.items()
            }
            raise HTTPException(
                status_code=400,
                detail=build_error_detail(
                    f"{name} 비율이 올바른 숫자가 아닙니다.",
                    "MATERIAL_RATIO_INVALID",
                    materials=safe_materials,
                    partial_materials=safe_materials,
                ),
            )

    total_ratio = sum(materials.values())
    if total_ratio < 99.5 or total_ratio > 100.5:
        raise HTTPException(
            status_code=400,
            detail=build_error_detail(
                f"전체 비율의 합이 100이 아닙니다. 현재 합계: {round(total_ratio, 2)}",
                "MATERIAL_RATIO_INVALID",
                materials=materials,
                partial_materials=materials,
                total_ratio=round(total_ratio, 2),
            ),
        )

    mixed_factor = 0.0
    unknown_materials = []

    for name, ratio in materials.items():
        material = find_material(db, name)

        if material is None:
            unknown_materials.append(name)
            continue

        mixed_factor += material.carbon_factor * (ratio / total_ratio)

    return mixed_factor, unknown_materials


def calculate_carbon(materials: dict[str, float], db: Session) -> tuple[float, list[str]]:
    mixed_factor, unknown_materials = validate_materials(materials, db)
    return round(mixed_factor, 2), unknown_materials


def build_emission_factors(materials: dict[str, float], db: Session) -> list[dict]:
    emission_factors = []
    total_ratio = sum(materials.values())

    if total_ratio <= 0:
        return emission_factors

    for name, ratio in materials.items():
        material = find_material(db, name)
        if material is None:
            continue

        normalized_ratio = ratio / total_ratio * 100
        emission_factors.append(
            {
                "input_name": name,
                "standard_name": material.name_en,
                "display_name": material.name_ko,
                "ratio": round(normalized_ratio, 2),
                "carbon_factor": material.carbon_factor,
                "unit": material.unit,
                "source": MATERIAL_FACTOR_SOURCE,
            }
        )

    return emission_factors


def build_material_details(materials: dict[str, float], db: Session) -> list[dict]:
    material_details = []

    for original_name, ratio in materials.items():
        material = find_material(db, original_name)
        material_details.append(
            {
                "original_name": original_name,
                "standard_name": material.name_en if material is not None else None,
                "display_name": material.name_ko if material is not None else original_name,
                "ratio": ratio,
                "is_supported": material is not None,
            }
        )

    return material_details


def build_analysis_response(
    materials: dict[str, float],
    db: Session,
    user: database.User | None = None,
    raw_ocr_text: str | None = None,
    care_instruction: str | None = None,
    title: str | None = None,
    category: str | None = None,
):
    total_carbon, unknown_materials = calculate_carbon(materials, db)

    if unknown_materials:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "DB에 등록되지 않은 소재가 있습니다.",
                "unknown_materials": unknown_materials,
            },
        )

    # /analyze의 값은 무게를 곱하지 않은 소재 계수(kg CO2eq/kg)라서,
    # 실제 배출량(/api/carbon/calculate)과 같은 이력 테이블에 저장하면
    # 단위가 다른 값이 한 목록에 섞입니다. 계산 전용으로 두고 저장은
    # /api/carbon/calculate 한 곳에서만 합니다.
    response = {
        "status": "success",
        "message": "분석 완료",
        "materials": materials,
        "carbon_footprint": total_carbon,
        "unit": "kg CO2eq",
        "care_instruction": care_instruction or "30도 이하 물에서 중성세제로 손세탁하세요.",
        "saved_result_id": None,
    }

    if title:
        response["title"] = title
    if category:
        response["category"] = category

    return response


def serialize_analysis_result(result: database.AnalysisResult) -> dict:
    return {
        "id": result.id,
        "user_id": result.user_id,
        "materials": json.loads(result.materials),
        "carbon_footprint": result.carbon_footprint,
        "carbon_footprint_min": result.carbon_footprint_min,
        "carbon_footprint_max": result.carbon_footprint_max,
        "min_weight_grams": result.min_weight_grams,
        "max_weight_grams": result.max_weight_grams,
        "unit": result.unit or "kg CO2eq",
        "unknown_materials": json.loads(result.unknown_materials or "[]"),
        # naive UTC를 그대로 내보내면 클라이언트가 기기 시간대로 오해하므로
        # UTC 오프셋(+00:00)을 붙여 직렬화합니다.
        "created_at": (
            result.created_at.replace(tzinfo=timezone.utc).isoformat()
            if result.created_at is not None
            else None
        ),
    }


# 사진 분석(Google Vision) 하루 상한(DECISIONS 164). 스캔 한 번이 Vision 호출 1~4건이고 월 1,000건을
# 넘으면 1,000건당 $1.50 이 청구되므로, Vision 을 실제로 부르는 스캔만 부르기 직전에 세고 결과(성공·
# 422·502)와 상관없이 되돌리지 않습니다. raw_ocr_text 로 OCR 을 건너뛴 요청, 업로드 검사(413·415)나
# OCR 모듈 없음(503)으로 끝난 요청은 세지 않습니다. 하루는 한국 자정(00:00 KST)에 바뀝니다.
# 기록은 로그인 한도처럼 프로세스 메모리에 둡니다 — 재시작하면 그날 수를 0부터 다시 셉니다.
SCAN_USER_DAILY_MAX = 20
# 한국은 서머타임이 없어 UTC+9 로 고정하면 정확합니다.
KST_OFFSET = timedelta(hours=9)


def parse_scan_daily_max(value: str | None) -> int | None:
    """K_DPP_SCAN_DAILY_MAX 를 읽는다. 비어 있으면 서버 전체 상한 없음, 1 이상의 정수면 그 값.
    그 밖의 값이면 시작하지 않는다 — 배포 설정 오타로 상한이 조용히 빠지지 않게. 공백만 있는 값도
    거부한다: compose 의 `:?` 는 빈 값만 막고 `" "` 는 통과시킨다."""
    if not value:
        return None
    normalized = value.strip()
    if re.fullmatch(r"[0-9]+", normalized) and int(normalized) >= 1:
        return int(normalized)
    raise ValueError(f"K_DPP_SCAN_DAILY_MAX 는 1 이상의 정수여야 합니다: {value!r}")


# 서버 전체 하루 상한. 계정을 여럿 만들어도 Vision 청구의 최악값이 이 값으로 묶입니다(배포는
# deploy/compose.yaml 에서 필수). 로컬은 비워 두면 상한이 없습니다.
SCAN_DAILY_MAX = parse_scan_daily_max(os.getenv("K_DPP_SCAN_DAILY_MAX"))
# 한국 날짜 → {사용자 id → 그날 Vision 을 부른 스캔 수}. 오늘 것만 남깁니다.
_vision_scan_counts: dict[date, dict[int, int]] = {}
# 동시에 몰아친 스캔이 한도를 넘어 Vision 까지 가지 않게 확인과 증가를 한 잠금 안에서 합니다.
_vision_scan_lock = threading.Lock()


def reserve_vision_scan(user_id: int) -> None:
    """Vision 을 부르기 직전에 한 번을 센다. 이 사용자가 오늘 한도에 닿았으면 429, 서버 전체가
    오늘 한도에 닿았으면 503 이고 그때는 세지 않는다. 센 것은 되돌리지 않는다."""
    with _vision_scan_lock:
        # 시각을 잠금 안에서 읽어, 자정 직전에 읽은 요청이 늦게 들어와 새 날 기록을 지우지 않게 합니다.
        # 시계가 뒤로 가도 앞날 기록은 남도록 지난 날만 지웁니다.
        now = utc_now()
        today = (now + KST_OFFSET).date()
        for day in [day for day in _vision_scan_counts if day < today]:
            del _vision_scan_counts[day]
        counts = _vision_scan_counts.setdefault(today, {})
        used = counts.get(user_id, 0)
        total = sum(counts.values())
        user_full = used >= SCAN_USER_DAILY_MAX
        server_full = SCAN_DAILY_MAX is not None and total >= SCAN_DAILY_MAX
        if not user_full and not server_full:
            counts[user_id] = used + 1
            if SCAN_DAILY_MAX is not None and total + 1 == SCAN_DAILY_MAX:
                # 서버 전체 상한에 닿은 날을 운영자가 알 수 있게 그날 한 번만 남깁니다.
                reached_at = (now + KST_OFFSET).strftime("%Y-%m-%d %H:%M")
                print(
                    f"[scan] {reached_at} KST Vision 스캔이 서버 전체 하루 상한({SCAN_DAILY_MAX}번)에 닿았습니다",
                    file=sys.stderr,
                )
            return

    # 두 상한 모두 다음 한국 자정에 풀립니다.
    next_midnight = datetime.combine(today + timedelta(days=1), datetime.min.time()) - KST_OFFSET
    retry_after = max(1, math.ceil((next_midnight - now).total_seconds()))
    if user_full:
        raise HTTPException(
            status_code=429,
            detail=build_error_detail(
                f"사진 분석은 하루 {SCAN_USER_DAILY_MAX}번까지입니다. 소재를 직접 입력하거나 내일 다시 시도해 주세요.",
                "SCAN_DAILY_LIMIT",
                retry_after=retry_after,
            ),
        )
    raise HTTPException(
        status_code=503,
        detail=build_error_detail(
            "오늘은 사진 분석을 더 할 수 없습니다. 소재를 직접 입력해 주세요.",
            "SCAN_UNAVAILABLE",
            retry_after=retry_after,
        ),
    )


def validate_scan_upload(image: UploadFile) -> None:
    """스캔 업로드의 형식·크기 검사. raw_ocr_text 유무와 무관하게 항상 실행한다.

    검사를 조기 반환 뒤에 두면 raw_ocr_text를 함께 보내는 것만으로
    형식·용량 제한을 우회할 수 있으므로(교차 검토 지적) 진입 시점에 검사한다.
    """
    # Content-Type이 아예 없는 업로드도 거부해 형식 검사 우회를 막습니다.
    if image.content_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=build_error_detail(
                "JPG, PNG, WEBP 이미지 파일만 지원합니다.",
                "UNSUPPORTED_IMAGE_FORMAT",
                content_type=image.content_type,
            ),
        )

    # 파일을 쓰지 않고 크기만 세어 상한을 검사한 뒤 읽기 위치를 되돌립니다.
    total_bytes = 0
    while chunk := image.file.read(1024 * 1024):
        total_bytes += len(chunk)
        if total_bytes > MAX_UPLOAD_BYTES:
            image.file.seek(0)
            raise HTTPException(
                status_code=413,
                detail=build_error_detail(
                    f"이미지가 너무 큽니다. {MAX_UPLOAD_BYTES // (1024 * 1024)}MB 이하로 올려 주세요.",
                    "PAYLOAD_TOO_LARGE",
                ),
            )
    image.file.seek(0)


def extract_label_text(image: UploadFile, raw_ocr_text: str | None, user_id: int) -> str:
    validate_scan_upload(image)

    if raw_ocr_text and raw_ocr_text.strip():
        return raw_ocr_text.strip()

    if run_ocr is None:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "AI OCR 모듈을 불러오지 못했습니다.",
                "hint": "AI/kdpp_ai_ocr_integrated 의존성을 설치한 뒤 다시 실행하세요.",
            },
        )

    # 파서가 없으면 Vision 을 불러도 503 으로 끝나므로, 부르기(세기) 전에 같은 503 을 냅니다.
    ensure_label_parser()

    # 아래 try 의 except Exception 이 HTTPException 도 502 로 바꾸므로 그 밖에서 셉니다.
    reserve_vision_scan(user_id)

    # 임시 파일 확장자는 업로드 이름이 아니라 이미 확인한 형식에서 정합니다 — 이름이 아주 길면
    # 임시 파일을 만들지 못해 500 이 났고, 그 요청도 이미 센 뒤였습니다(OCR 은 확장자를 보지 않음).
    suffix = SCAN_IMAGE_SUFFIXES[image.content_type]
    copied_bytes = 0
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = temp_file.name
        # 크기 검사 없이 통째로 복사하면 대용량 업로드로 디스크가 고갈될 수
        # 있으므로, 청크 단위로 복사하며 상한을 넘는 즉시 중단합니다.
        while chunk := image.file.read(1024 * 1024):
            copied_bytes += len(chunk)
            if copied_bytes > MAX_UPLOAD_BYTES:
                temp_file.close()
                Path(temp_path).unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=build_error_detail(
                        f"이미지가 너무 큽니다. {MAX_UPLOAD_BYTES // (1024 * 1024)}MB 이하로 올려 주세요.",
                        "PAYLOAD_TOO_LARGE",
                    ),
                )
            temp_file.write(chunk)

    try:
        credential_path = (
            Path(__file__).resolve().parents[1]
            / "AI"
            / "kdpp_ai_ocr_integrated"
            / "key.json"
        )
        return run_ocr(
            temp_path,
            credential_path=str(credential_path) if credential_path.exists() else "",
        )
    except Exception as exc:
        # 예외 원문에는 서버 경로·계정 식별자 등이 섞일 수 있어
        # 서버 로그에만 남기고 클라이언트에는 고정 메시지만 돌려줍니다.
        print(f"[scan] OCR 실패: {exc!r}", file=sys.stderr)
        raise HTTPException(
            status_code=502,
            detail={
                "message": "AI OCR 처리에 실패했습니다.",
                "error": "라벨 이미지를 인식하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            },
        ) from exc
    finally:
        Path(temp_path).unlink(missing_ok=True)


def ensure_label_parser() -> None:
    if parse_label is None:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "AI 라벨 파서 모듈을 불러오지 못했습니다.",
                "hint": "AI/kdpp_ai_ocr_integrated 모듈 경로를 확인하세요.",
            },
        )


def parse_label_materials(label_text: str) -> tuple[dict[str, float], str, str]:
    ensure_label_parser()

    parsed = parse_label(label_text)
    materials = parsed.get("materials") or {}
    raw_ocr_preview = parsed.get("raw_ocr_preview", "")
    # AI 파서는 버전마다 관리 지침 키가 다릅니다(develop: care_text,
    # ksw/ai-ocr-enhancement: care_instruction). 한쪽만 읽으면 AI 모듈을
    # 교체하는 순간 실제 지침이 조용히 사라지고 아래 기본 문구만 남습니다.
    care_instruction = (
        parsed.get("care_text")
        or parsed.get("care_instruction")
        or "라벨 표기법에 맞춰 관리하세요."
    )

    if not materials:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "라벨에서 소재 혼용률을 찾지 못했습니다.",
                "error_code": "MATERIAL_EXTRACTION_FAILED",
                "materials": materials,
                "partial_materials": materials,
                "care_instruction": care_instruction,
                "raw_ocr_preview": raw_ocr_preview,
                "ai_success": False,
            },
        )

    return materials, care_instruction, raw_ocr_preview

# --- API 엔드포인트 시작 ---

EMAIL_CODE_SENT_MESSAGES = {
    "signup": "인증번호를 보냈습니다. 메일이 오지 않으면 주소를 확인해 주세요.",
    "password_reset": "가입된 이메일이면 인증번호를 보냈습니다. 메일이 오지 않으면 주소를 확인해 주세요.",
}


@app.post("/auth/email-code", tags=["auth"])
def request_email_code(
    request: EmailCodeRequest, http_request: Request, background_tasks: BackgroundTasks
):
    """가입·비밀번호 찾기 인증번호를 요청한다(DECISIONS 144·147·148).

    가입 여부와 상관없이 같은 용도면 늘 같은 응답이다. 이 함수는 DB 를 보지 않고, 어떤 메일을
    보낼지(번호·이미 가입 안내·보내지 않음)는 응답을 보낸 뒤 send_email_code_message 가 정한다.
    """
    email = normalize_email(request.email)
    ensure_email_format(email)
    code, resend_after = issue_email_code(
        email,
        request.purpose,
        client_ip_key(http_request.client.host if http_request.client else None),
    )
    background_tasks.add_task(send_email_code_message, email, request.purpose, code)
    return {
        "status": "success",
        "message": EMAIL_CODE_SENT_MESSAGES[request.purpose],
        "expires_in": EMAIL_CODE_TTL_SECONDS,
        "resend_after": resend_after,
    }


@app.post("/auth/signup", tags=["auth"])
def signup(request: SignupRequest, http_request: Request, db: Session = Depends(get_db)):
    email = normalize_email(request.email)
    nickname = request.nickname.strip()
    password = request.password

    ensure_email_format(email)
    ensure_nickname_rules(nickname)
    ensure_password_rules(password)
    code = ensure_email_code_format(request.code)
    # 형식을 통과한 시도부터 DB 조회·해시 전에 셉니다(번호 틀림·409 도 셈, 접속 주소는 로그인과 같음).
    reserve_signup_attempt_for_ip(
        client_ip_key(http_request.client.host if http_request.client else None)
    )
    # 번호를 409 보다 먼저 봅니다. 가입된 이메일엔 번호 대신 안내 메일이 가므로, '이미 가입'은
    # 맞는 번호를 가진 사람(메일함 주인)만 보게 됩니다(관찰 ⓖ).
    email_code = check_email_code(email, "signup", code)

    existing_user = db.query(database.User).filter(database.User.email == email).first()
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")

    user = database.User(
        email=email,
        nickname=nickname,
        password_hash=hash_password(password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # 같은 이메일로 거의 동시에 가입 요청이 들어온 경우(버튼 연타 등)
        # 늦게 커밋된 쪽을 중복 가입과 동일하게 처리합니다.
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")
    db.refresh(user)
    consume_email_code(email, "signup", email_code)

    return {
        "status": "success",
        "message": "회원가입이 완료되었습니다.",
        "user": auth_user_response(user, db),
    }


@app.post("/auth/password-reset", tags=["auth"])
def reset_password(request: PasswordResetRequest, db: Session = Depends(get_db)):
    """비밀번호 찾기: 인증번호와 새 비밀번호를 한 번에 받아 바꾼다(DECISIONS 147·148).

    성공하면 그 계정의 토큰을 모두 지우고(찾는 흔한 이유가 도용 의심 — /auth/password 와 같음)
    이메일 로그인 잠금을 푼다. 새 토큰은 주지 않는다(앱은 로그인 화면으로).
    """
    email = normalize_email(request.email)
    ensure_email_format(email)
    ensure_password_rules(request.new_password)
    code = ensure_email_code_format(request.code)
    # 맞는 순간 번호를 지워, 같은 번호로 동시에 두 번 재설정하지 못하게 합니다(뒤에서 500 이 나면 다시 받기).
    check_email_code(email, "password_reset", code, consume=True)

    # 번호가 맞을 때만 해시합니다. 첫 DB 조회 전에 해시해 그동안 DB 연결을 쥐지 않습니다.
    new_password_hash = hash_password(request.new_password)
    # users 행을 먼저 잠급니다 — 로그인·비밀번호 변경·탈퇴와 같은 순서(users → access_tokens).
    user_id = (
        db.query(database.User.id)
        .filter(database.User.email == email)
        .with_for_update()
        .scalar()
    )
    if user_id is not None:
        db.query(database.User).filter(database.User.id == user_id).update(
            {"password_hash": new_password_hash}, synchronize_session=False
        )
        db.query(database.AccessToken).filter(
            database.AccessToken.user_id == user_id
        ).delete(synchronize_session=False)
        db.commit()
    # 가입 안 된 이메일엔 번호 메일이 가지 않아, 여기까지 오려면 번호를 맞혀야 합니다(번호당 5번).
    # 그때도 해시까지 하고 같은 응답을 내 가입 여부를 드러내지 않습니다.
    clear_login_failures(email)

    return {
        "status": "success",
        "message": "비밀번호를 다시 설정했습니다. 새 비밀번호로 로그인해 주세요.",
    }


@app.post("/auth/login", tags=["auth"])
def login(request: LoginRequest, http_request: Request, db: Session = Depends(get_db)):
    email = normalize_email(request.email)
    check_login_lockout(email)
    # 배포에서는 Caddy 가 X-Forwarded-For 를 실제 접속 주소로 채우고 uvicorn
    # --proxy-headers 가 그 값을 client 로 넘깁니다(앱 포트는 밖에 열려 있지 않음).
    ip_key = client_ip_key(http_request.client.host if http_request.client else None)
    reserve_login_attempt_for_ip(ip_key)

    user = db.query(database.User).filter(database.User.email == email).first()

    if user is None:
        # 미가입 이메일이라도 해시 검증을 한 번 수행해 응답 시간을 맞춥니다.
        # (시간 차이로 가입 여부를 알아내는 것을 막기 위함)
        verify_password(request.password, DUMMY_PASSWORD_HASH)
        record_login_failure(email)
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    if not verify_password(request.password, user.password_hash):
        record_login_failure(email)
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    # 반복 수를 올리기 전에 만든 해시는 원문을 아는 지금 새로 저장합니다(토큰 발급과 한 커밋).
    # 해시는 행을 잠그기 전에 해 둡니다.
    upgraded_hash = (
        hash_password(request.password) if password_needs_rehash(user.password_hash) else None
    )

    if not lock_user_if_password_unchanged(db, user.id, user.password_hash):
        # 확인하는 동안 비밀번호가 바뀌었습니다(비밀번호 찾기·변경). 옛 비밀번호로는 토큰을 주지 않고,
        # 같은 순간 먼저 커밋된 새 비밀번호를 옛 비밀번호의 재해시로 되돌리지도 않습니다.
        db.rollback()
        record_login_failure(email)
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    clear_login_failures(email)
    release_login_attempt_for_ip(ip_key)

    if upgraded_hash is not None:
        db.query(database.User).filter(database.User.id == user.id).update(
            {"password_hash": upgraded_hash}, synchronize_session=False
        )

    # 잠근 행을 그대로 쥔 채 토큰을 만들고 한 번에 커밋합니다.
    raw_token = add_access_token(user.id, db)
    db.commit()

    return {
        "status": "success",
        "message": "로그인되었습니다.",
        "user": auth_user_response(user, db),
        "access_token": raw_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    }


@app.post("/auth/kakao", tags=["auth"])
def kakao_login(request: KakaoLoginRequest, http_request: Request, db: Session = Depends(get_db)):
    """카카오 로그인 — 첫 로그인이 곧 가입(DECISIONS 152 ②). 검사 순서는 API_CONTRACT.md 와 같다.

    로그인 IP 기록(이메일 로그인 실패와 같은 기록)에 카카오에 묻기 전에 한 번을 세고,
    SOCIAL_TOKEN_INVALID 일 때만 남긴다. 새 카카오 계정은 가입 IP 한도에 세지 않는다(152 ⑥).
    """
    ensure_kakao_login_enabled()
    access_token = ensure_kakao_token_format(request.access_token)
    nickname = None
    if request.nickname is not None:
        nickname = request.nickname.strip()
        ensure_nickname_rules(nickname)
    ip_key = client_ip_key(http_request.client.host if http_request.client else None)
    reserve_login_attempt_for_ip(ip_key)

    token_rejected = False
    try:
        subject = verify_kakao_token(access_token)
        user_payload, raw_token, is_new_user = sign_in_kakao_account(
            db, subject, access_token, nickname
        )
    except KakaoTokenRejected:
        token_rejected = True
        raise social_token_invalid(401) from None
    except KakaoUnavailable as exc:
        log_kakao_failure("로그인 실패", exc)
        raise social_provider_unavailable() from None
    finally:
        # 성공·SOCIAL_NICKNAME_REQUIRED·502·서버 오류는 미리 센 한 번을 되돌립니다.
        if not token_rejected:
            release_login_attempt_for_ip(ip_key)

    return {
        "status": "success",
        "message": "카카오 계정으로 가입했습니다." if is_new_user else "로그인되었습니다.",
        "user": user_payload,
        "access_token": raw_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        "is_new_user": is_new_user,
    }


def _integrity_constraint_name(error: IntegrityError) -> str | None:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def sign_in_kakao_account(
    db: Session, subject: str, access_token: str, nickname: str | None
) -> tuple[dict, str, bool]:
    """회원번호로 계정을 찾아 토큰을 만든다. 없으면 users·social_accounts·토큰을 한 커밋으로 만든다.
    (user 응답, 토큰 원문, 새 계정인지)를 돌려준다.

    - 같은 카카오 계정의 첫 로그인이 동시에 둘 오면 늦은 쪽은 UNIQUE(provider, subject) 에 걸려
      롤백한 뒤 다시 찾아 로그인한다(is_new_user false).
    - 찾은 계정이 잠그기 전에 탈퇴로 사라졌으면 다시 찾는다(그때는 새 계정).
    - user 응답은 행을 쥔 채 만든다 — 커밋 뒤 다시 읽는 사이에 탈퇴가 끼면 없는 행을 읽게 된다.
    """
    for _ in range(3):
        user_id = (
            db.query(database.SocialAccount.user_id)
            .filter(
                database.SocialAccount.provider == KAKAO_PROVIDER,
                database.SocialAccount.subject == subject,
            )
            .scalar()
        )
        if user_id is not None:
            user = (
                db.query(database.User)
                .filter(database.User.id == user_id)
                .with_for_update()
                .first()
            )
            if user is None:
                # 찾은 뒤 잠그기 전에 탈퇴가 커밋됐습니다(소셜 연결도 같이 지워짐) — 다시 찾습니다.
                db.rollback()
                continue
            raw_token = add_access_token(user.id, db)
            user_payload = auth_user_response(user, db)
            db.commit()
            return user_payload, raw_token, False

        # 새 계정. 닉네임을 정하는 동안(카카오 호출) DB 연결을 쥐지 않게 읽기 트랜잭션을 끝냅니다.
        db.rollback()
        if nickname is None:
            nickname = resolve_kakao_nickname(access_token, subject)
        user = database.User(email=None, password_hash=None, nickname=nickname)
        try:
            db.add(user)
            db.flush()
            db.add(
                database.SocialAccount(
                    user_id=user.id, provider=KAKAO_PROVIDER, subject=subject
                )
            )
            raw_token = add_access_token(user.id, db)
            db.flush()
        except IntegrityError as error:
            db.rollback()
            if _integrity_constraint_name(error) != "uq_social_accounts_provider_subject":
                raise
            # 같은 카카오 계정의 첫 로그인이 먼저 커밋됐습니다 — 다시 찾으면 그 계정으로 로그인합니다.
            continue
        user_payload = auth_user_response(user, db)
        db.commit()
        return user_payload, raw_token, True

    raise RuntimeError("카카오 계정을 찾지도 만들지도 못했습니다(경합이 세 번 이어짐).")


@app.post("/auth/logout", tags=["auth"])
def logout(
    access_token: database.AccessToken = Depends(get_current_access_token),
    db: Session = Depends(get_db),
):
    db.delete(access_token)
    db.commit()
    return {"status": "success", "message": "로그아웃되었습니다."}


@app.post("/auth/password", tags=["auth"])
def change_password(
    request: ChangePasswordRequest,
    access_token: database.AccessToken = Depends(get_current_access_token),
    db: Session = Depends(get_db),
):
    """현재 비밀번호를 확인한 뒤 새 비밀번호로 바꾸고 기존 세션을 모두 끊는다.

    비밀번호를 바꾸는 흔한 이유가 "남이 내 계정을 쓰는 것 같다"이므로,
    변경에 성공하면 발급돼 있던 토큰을 전부 지우고 요청한 기기에만
    새 토큰을 내준다. 그래야 변경이 실제로 효력을 갖는다.
    """
    user = db.query(database.User).filter(database.User.id == access_token.user_id).first()

    if user is None:
        # 토큰은 살아 있는데 사용자가 사라진 경우(탈퇴 직후 등)는 세션 만료로 처리한다.
        db.delete(access_token)
        db.commit()
        raise HTTPException(status_code=401, detail="로그인이 만료되었습니다.")

    if user.password_hash is None:
        # 카카오 계정 — 확인할 비밀번호가 없습니다. 이메일도 없어(None) 아래 로그인 잠금 함수를 부르지
        # 않습니다(None 하나를 모든 카카오 계정이 키로 나눠 쓰게 됨). 앱은 이 버튼을 숨깁니다.
        raise HTTPException(
            status_code=400,
            detail=build_error_detail("비밀번호로 가입한 계정이 아닙니다.", "PASSWORD_NOT_SET"),
        )

    # 재인증도 로그인과 같은 잠금 카운터를 쓴다. 토큰만 탈취한 공격자가 이 경로로
    # 비밀번호를 무제한 추측하면 로그인 잠금이 무의미해지고, 맞히는 순간 다른 세션이
    # 모두 끊겨 계정을 통째로 빼앗기기 때문이다.
    check_login_lockout(user.email)
    verified_hash = user.password_hash

    # 401은 "이 세션이 더 이상 유효하지 않다"는 뜻으로만 쓴다. 프론트가 401을
    # 세션 만료로 보고 강제 로그아웃시키므로(session_expiry_handler), 비밀번호를
    # 한 번 잘못 친 것만으로 로그아웃되면 안 된다. 재인증 실패는 400으로 낸다.
    if not verify_password(request.current_password, verified_hash):
        record_login_failure(user.email)
        raise HTTPException(status_code=400, detail="현재 비밀번호가 올바르지 않습니다.")

    clear_login_failures(user.email)

    ensure_password_rules(request.new_password)

    if request.new_password == request.current_password:
        raise HTTPException(status_code=400, detail="새 비밀번호가 기존 비밀번호와 같습니다.")

    new_password_hash = hash_password(request.new_password)
    if not lock_user_if_password_unchanged(db, user.id, verified_hash):
        # 확인하는 동안 비밀번호 찾기·다른 기기의 변경이 먼저 끝났습니다. 그쪽이 이 세션의 토큰도
        # 지웠으므로 세션 만료로 냅니다 — 옛 비밀번호로 확인한 변경이 새 비밀번호를 덮지 않게.
        db.rollback()
        raise HTTPException(status_code=401, detail="로그인이 만료되었습니다.")

    # 비밀번호 저장·기존 토큰 삭제·새 토큰 발급을 한 커밋으로 — 새 토큰은 지운 뒤에 넣어야 함께 지워지지 않는다.
    db.query(database.User).filter(database.User.id == user.id).update(
        {"password_hash": new_password_hash}, synchronize_session=False
    )
    db.query(database.AccessToken).filter(
        database.AccessToken.user_id == user.id
    ).delete(synchronize_session=False)
    raw_token = add_access_token(user.id, db)
    db.commit()

    return {
        "status": "success",
        "message": "비밀번호가 변경되었습니다.",
        "user": auth_user_response(user, db),
        "access_token": raw_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    }


@app.post("/auth/withdraw", tags=["auth"])
def withdraw(
    request: WithdrawRequest,
    http_request: Request,
    access_token: database.AccessToken = Depends(get_current_access_token),
    db: Session = Depends(get_db),
):
    """재인증(비밀번호 계정은 비밀번호, 카카오 계정은 카카오 로그인)한 뒤 계정·토큰·분석 이력·
    소셜 연결을 한 트랜잭션에서 지운다.

    DELETE 메서드 대신 POST를 쓰는 이유는 프론트 공용 HTTP 헬퍼가
    GET/POST만 지원하기 때문이다(docs/SCAN_API_CONTRACT.md 참조).
    """
    user = db.query(database.User).filter(database.User.id == access_token.user_id).first()

    if user is None:
        db.delete(access_token)
        db.commit()
        raise HTTPException(status_code=401, detail="로그인이 만료되었습니다.")

    if user.password_hash is None:
        return withdraw_kakao_account(request, http_request, user.id, db)

    if request.password is None:
        raise HTTPException(status_code=400, detail="비밀번호를 입력해 주세요.")

    check_login_lockout(user.email)
    verified_hash = user.password_hash

    # 비밀번호 변경과 같은 이유로 재인증 실패는 400으로 낸다(401은 세션 만료 전용).
    if not verify_password(request.password, verified_hash):
        record_login_failure(user.email)
        raise HTTPException(status_code=400, detail="비밀번호가 올바르지 않습니다.")

    if not lock_user_if_password_unchanged(db, user.id, verified_hash):
        # 확인하는 동안 비밀번호가 바뀌었거나(비밀번호 찾기·변경 — 이 세션의 토큰도 지워짐) 계정이 없어졌습니다.
        db.rollback()
        raise HTTPException(status_code=401, detail="로그인이 만료되었습니다.")

    clear_login_failures(user.email)

    delete_user_rows(db, user.id)
    db.commit()

    return {"status": "success", "message": "회원 탈퇴가 완료되었습니다."}


def withdraw_kakao_account(
    request: WithdrawRequest, http_request: Request, user_id: int, db: Session
) -> dict:
    """카카오 계정 탈퇴(DECISIONS 152 ④·153 ①): 카카오 토큰 확인 → users 행 잠금 → 이 계정의 회원번호와
    대조 → 삭제 커밋 → 그 토큰으로 카카오 연결 끊기(실패해도 탈퇴는 성공, 로그만).

    비밀번호와 달리 추측할 수 없어 이메일 로그인 잠금(5회/60초)은 쓰지 않는다 — 이메일이 None 이라
    쓰면 모든 카카오 계정이 한 칸을 나눠 쓴다. 로그인 IP 기록에 묻기 전에 한 번을 세고
    SOCIAL_TOKEN_INVALID 일 때만 남긴다.
    """
    if request.kakao_access_token is None:
        raise HTTPException(status_code=400, detail="카카오 로그인으로 탈퇴를 확인해 주세요.")
    ensure_kakao_login_enabled()
    kakao_token = ensure_kakao_token_format(request.kakao_access_token)
    ip_key = client_ip_key(http_request.client.host if http_request.client else None)
    reserve_login_attempt_for_ip(ip_key)

    # 카카오에 묻는 동안(최대 5초) DB 연결을 쥐지 않게 지금까지의 읽기 트랜잭션을 끝냅니다.
    db.rollback()
    token_rejected = False
    try:
        try:
            subject = verify_kakao_token(kakao_token)
        except KakaoTokenRejected:
            token_rejected = True
            raise social_token_invalid(400) from None
        except KakaoUnavailable as exc:
            log_kakao_failure("탈퇴 확인 실패", exc)
            raise social_provider_unavailable() from None

        if not lock_user_row(db, user_id):
            # 카카오에 묻는 동안 다른 기기에서 탈퇴가 먼저 끝났습니다(이 세션의 토큰도 지워짐).
            db.rollback()
            raise HTTPException(status_code=401, detail="로그인이 만료되었습니다.")
        linked_subject = (
            db.query(database.SocialAccount.subject)
            .filter(
                database.SocialAccount.user_id == user_id,
                database.SocialAccount.provider == KAKAO_PROVIDER,
            )
            .scalar()
        )
        if linked_subject != subject:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=build_error_detail(
                    "이 계정에 연결된 카카오 계정이 아닙니다. 가입한 카카오 계정으로 다시 로그인해 주세요.",
                    "SOCIAL_ACCOUNT_MISMATCH",
                ),
            )
        delete_user_rows(db, user_id)
        db.commit()
    finally:
        if not token_rejected:
            release_login_attempt_for_ip(ip_key)

    try:
        kakao_unlink(kakao_token)
    except Exception as exc:  # noqa: BLE001 — 계정은 이미 지워졌으므로 응답은 성공 그대로입니다.
        # 카카오 쪽 연결이 남습니다. 같은 카카오 계정의 다음 로그인은 새 계정입니다.
        log_kakao_failure(f"탈퇴한 사용자 {user_id} 의 카카오 연결 끊기 실패", exc)

    return {"status": "success", "message": "회원 탈퇴가 완료되었습니다."}


@app.get("/", tags=["system"])
def read_root():
    return {"status": "success", "message": "K-DPP 백엔드 서버가 가동 중입니다!"}

@app.post(
    "/analyze",
    tags=["v1-carbon"],
    summary="의류 혼용률 기반 탄소배출량 계산",
    description="AI/OCR 또는 프론트에서 전달한 소재 혼용률을 DB의 소재별 탄소배출계수와 매칭해 예상 탄소배출량을 계산합니다.",
)
def analyze_clothes(
    request: AnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: database.User | None = Depends(get_optional_current_user),
):
    return build_analysis_response(
        materials=request.materials,
        db=db,
        user=current_user,
        raw_ocr_text=request.raw_ocr_text,
    )


@app.post("/api/scan", tags=["v1-scan"])
def scan_label(
    image: UploadFile = File(...),
    # JSON 요청의 RawOcrText 와 같은 상한입니다. 폼 필드라 Form 에 직접 겁니다.
    raw_ocr_text: str | None = Form(default=None, max_length=MAX_RAW_OCR_TEXT_LENGTH),
    db: Session = Depends(get_db),
    # 스캔 1회가 곧 외부 OCR 호출 비용이므로 로그인 사용자만 허용하고, 사용자마다 하루 횟수를 셉니다.
    current_user: database.User = Depends(get_current_user),
):
    label_text = extract_label_text(image, raw_ocr_text, current_user.id)
    materials, care_instruction, raw_ocr_preview = parse_label_materials(label_text)
    title = "스캔한 의류"
    category = "상의"

    # 라벨 일부만 읽혀 합계가 100이 아니면, 이 값 그대로는 탄소 계산이
    # 거부되므로(99.5~100.5 검사) 부분 인식임을 응답에 명시합니다.
    total_ratio = sum(materials.values())
    ratio_complete = 99.5 <= total_ratio <= 100.5

    return {
        "status": "success",
        "message": "라벨 인식 완료" if ratio_complete else "라벨을 일부만 인식했습니다. 비율을 확인해 주세요.",
        "ai_success": ratio_complete,
        "analysis_failure_reason": None if ratio_complete else "RATIO_INCOMPLETE",
        "materials": materials,
        "material_details": build_material_details(materials, db),
        "care_instruction": care_instruction,
        "raw_ocr_preview": raw_ocr_preview,
        "clothing": {
            "name": title,
            "category": category,
        },
        "title": title,
        "category": category,
    }


@app.post("/api/carbon/calculate", tags=["v1-carbon"])
def calculate_carbon_range(
    request: CarbonRangeRequest,
    db: Session = Depends(get_db),
    current_user: database.User = Depends(get_current_user),
):
    if request.weight_grams is not None:
        if request.weight_grams <= 0:
            raise HTTPException(
                status_code=400,
                detail=build_error_detail(
                    "의류 무게는 0g보다 커야 합니다.",
                    "WEIGHT_INVALID",
                    weight_grams=request.weight_grams,
                ),
            )
        min_weight_grams = request.weight_grams
        max_weight_grams = request.weight_grams
        weight_source = "direct"
    else:
        if request.min_weight_grams is None or request.max_weight_grams is None:
            raise HTTPException(
                status_code=400,
                detail=build_error_detail(
                    "무게 범위 또는 직접 입력 무게를 입력해 주세요.",
                    "WEIGHT_MISSING",
                ),
            )
        min_weight_grams = request.min_weight_grams
        max_weight_grams = request.max_weight_grams
        weight_source = "range"

    # NaN·무한대는 모든 대소 비교가 False라 그대로 통과해 이력 조회까지 500으로
    # 망가뜨리므로 먼저 걸러내고, 상한으로 비현실적 입력도 차단합니다.
    if (
        not math.isfinite(min_weight_grams)
        or not math.isfinite(max_weight_grams)
        or min_weight_grams <= 0
        or max_weight_grams <= 0
        or max_weight_grams > MAX_WEIGHT_GRAMS
    ):
        raise HTTPException(
            status_code=400,
            detail=build_error_detail(
                f"의류 무게는 1g 이상 {MAX_WEIGHT_GRAMS:,}g 이하로 입력해 주세요.",
                "WEIGHT_INVALID",
                # NaN을 그대로 되돌려주면 JSON 직렬화가 실패합니다.
                min_weight_grams=min_weight_grams if math.isfinite(min_weight_grams) else None,
                max_weight_grams=max_weight_grams if math.isfinite(max_weight_grams) else None,
            ),
        )
    if min_weight_grams > max_weight_grams:
        raise HTTPException(
            status_code=400,
            detail=build_error_detail(
                "최소 무게는 최대 무게보다 클 수 없습니다.",
                "WEIGHT_RANGE_INVALID",
                min_weight_grams=min_weight_grams,
                max_weight_grams=max_weight_grams,
            ),
        )

    mixed_factor, unknown_materials = validate_materials(request.materials, db)
    if unknown_materials:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "DB에 등록되지 않은 소재가 있습니다.",
                "error_code": "MATERIAL_NOT_FOUND",
                "unknown_materials": unknown_materials,
            },
        )

    emission_factors = build_emission_factors(request.materials, db)
    carbon_min = round(mixed_factor * min_weight_grams / 1000, 2)
    carbon_max = round(mixed_factor * max_weight_grams / 1000, 2)
    carbon_midpoint = round((carbon_min + carbon_max) / 2, 2)

    result = database.AnalysisResult(
        user_id=current_user.id,
        materials=json.dumps(request.materials, ensure_ascii=False),
        carbon_footprint=carbon_midpoint,
        carbon_footprint_min=carbon_min,
        carbon_footprint_max=carbon_max,
        min_weight_grams=min_weight_grams,
        max_weight_grams=max_weight_grams,
        unit="kg CO2eq",
        raw_ocr_text=request.raw_ocr_text,
        unknown_materials="[]",
    )
    db.add(result)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _integrity_constraint_name(error) != "fk_analysis_results_user_id_users":
            raise
        # 토큰 확인 뒤 다른 기기의 탈퇴가 먼저 커밋됐습니다(탈퇴가 users 행을 쥔 동안 이 INSERT 가 기다렸다가
        # 외래 키에 걸림). 계정이 없으니 저장하지 않고 세션 만료로 냅니다(DECISIONS 161).
        raise HTTPException(status_code=401, detail="로그인이 만료되었습니다.")
    db.refresh(result)

    return {
        "status": "success",
        "message": "탄소배출량 계산 완료",
        "materials": request.materials,
        "carbon_factor": round(mixed_factor, 2),
        "carbon_footprint": carbon_midpoint,
        "average_carbon_footprint": carbon_midpoint,
        "carbon_footprint_min": carbon_min,
        "carbon_footprint_max": carbon_max,
        "min_weight_grams": min_weight_grams,
        "max_weight_grams": max_weight_grams,
        "weight_grams": request.weight_grams,
        "weight_source": weight_source,
        "clothing_type": request.clothing_type,
        "category": request.category,
        "unit": "kg CO2eq",
        "source": "backend",
        "calculation_scope": CALCULATION_SCOPE,
        "calculation_basis": "소재별 탄소배출계수(kg CO2eq/kg)와 의류 무게(g)를 곱해 계산했습니다.",
        "emission_factors": emission_factors,
        "calculation_source": MATERIAL_FACTOR_SOURCE,
        "calculation_note": "현재 소재별 배출계수는 개발용 추정값입니다. 최종 발표 전 팀 승인 출처로 교체해야 합니다.",
        "saved_result_id": result.id,
    }

@app.get("/history", tags=["v1-carbon"])
def get_history(
    current_user: database.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_user_history_response(current_user, db)


@app.get("/me/history", tags=["v1-carbon"])
def get_my_history(
    current_user: database.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_user_history_response(current_user, db)


def get_user_history_response(
    current_user: database.User,
    db: Session,
) -> dict:
    # 상한보다 1건 더 읽어, 잘렸는지를 추가 조회 없이 판단합니다.
    results = (
        db.query(database.AnalysisResult)
        .filter(database.AnalysisResult.user_id == current_user.id)
        .order_by(database.AnalysisResult.id.desc())
        .limit(MAX_HISTORY_ITEMS + 1)
        .all()
    )

    has_more = len(results) > MAX_HISTORY_ITEMS
    results = results[:MAX_HISTORY_ITEMS]

    return {
        "status": "success",
        "user": auth_user_response(current_user, db),
        "history": [serialize_analysis_result(result) for result in results],
        "has_more": has_more,
    }

@app.get("/materials", tags=["v1-carbon"])
def get_materials(db: Session = Depends(get_db)):
    # DB에 저장된 소재별 탄소배출량 표준 목록을 가져오는 API
    materials = db.query(database.Material).order_by(database.Material.id.asc()).all()
    return [
        {
            "id": material.id,
            "name_ko": material.name_ko,
            "name_en": material.name_en,
            "aliases": load_aliases(material),
            "carbon_factor": material.carbon_factor,
            "unit": material.unit,
        }
        for material in materials
    ]


@app.get("/clothing-types", tags=["v1-carbon"])
def get_clothing_types():
    return {
        "status": "success",
        "source": "backend",
        "unit": "g",
        "items": CLOTHING_TYPE_OPTIONS,
    }
