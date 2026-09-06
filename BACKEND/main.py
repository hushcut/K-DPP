from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import BaseModel
import json
import math
import re
import shutil
import sys
import threading
import tempfile
from pathlib import Path
import hashlib
import secrets
import database
import init_data

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
    init_data.seed_materials()
    yield


# 1. 앱 객체 생성
app = FastAPI(
    title="K-DPP Backend",
    description="K-DPP v1 탄소배출량 계산 API",
    version="0.1.0",
    lifespan=lifespan,
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


# CORS를 나중에 추가해야 바깥층이 되어 413 응답에도 CORS 헤더가 붙습니다.
app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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

    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "error_code": error_code,
            "message": message,
            "detail": exc.errors(),
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
class SignupRequest(BaseModel):
    email: str
    password: str
    nickname: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class WithdrawRequest(BaseModel):
    password: str


class AnalyzeRequest(BaseModel):
    materials: dict[str, float]
    raw_ocr_text: str | None = None


class CarbonRangeRequest(BaseModel):
    materials: dict[str, float]
    min_weight_grams: float | None = None
    max_weight_grams: float | None = None
    weight_grams: float | None = None
    clothing_type: str | None = None
    category: str | None = None
    raw_ocr_text: str | None = None

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


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120000,
    ).hex()
    return f"pbkdf2_sha256$120000${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
    except ValueError:
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return secrets.compare_digest(digest, expected)


# 미가입 이메일 로그인 시에도 같은 비용의 해시 검증을 수행하기 위한 더미 해시.
DUMMY_PASSWORD_HASH = hash_password("k-dpp-timing-guard")
# 최소한의 이메일 형식 검사: 공백 없는 로컬@도메인.최상위 형태만 허용.
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

# 로그인 무차별 대입 방어: 같은 이메일로 연속 실패하면 잠시 잠급니다.
# (프로세스 메모리 기준 — 단일 서버 개발 환경에는 충분합니다)
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


def _prune_login_failures_locked() -> None:
    """오래된 실패 기록과 상한 초과분을 제거한다. 반드시 잠금 안에서 호출."""
    cutoff = utc_now() - timedelta(seconds=LOGIN_FAILURE_TTL_SECONDS)
    for key in [k for k, (_, last) in _login_failures.items() if last < cutoff]:
        del _login_failures[key]

    overflow = len(_login_failures) - LOGIN_FAILURES_MAX_ENTRIES
    if overflow > 0:
        oldest = sorted(_login_failures.items(), key=lambda kv: kv[1][1])[:overflow]
        for key, _ in oldest:
            del _login_failures[key]


def record_login_failure(email: str) -> None:
    with _login_failures_lock:
        _prune_login_failures_locked()
        count, _ = _login_failures.get(email, (0, utc_now()))
        _login_failures[email] = (count + 1, utc_now())


def clear_login_failures(email: str) -> None:
    with _login_failures_lock:
        _login_failures.pop(email, None)


def auth_user_response(user: database.User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "nickname": user.nickname,
    }


def hash_access_token(token: str) -> str:
    """DB 파일이 유출돼도 토큰 원문을 알 수 없도록 해시로만 저장한다."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user: database.User, db: Session) -> tuple[str, database.AccessToken]:
    """토큰 원문은 응답으로만 전달하고 DB에는 해시를 저장한다."""
    raw_token = secrets.token_urlsafe(32)
    access_token = database.AccessToken(
        token=hash_access_token(raw_token),
        user_id=user.id,
        expires_at=utc_now() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
    )
    db.add(access_token)
    db.commit()
    return raw_token, access_token


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


def find_material(db: Session, name: str):
    material_name = name.strip().lower()

    for material in db.query(database.Material).all():
        candidates = {
            material.name_ko.strip().lower(),
            material.name_en.strip().lower(),
            *load_aliases(material),
        }

        if material_name in candidates:
            return material

    return None


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


def extract_label_text(image: UploadFile, raw_ocr_text: str | None) -> str:
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

    suffix = Path(image.filename or "label.jpg").suffix or ".jpg"
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


def parse_label_materials(label_text: str) -> tuple[dict[str, float], str, str]:
    if parse_label is None:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "AI 라벨 파서 모듈을 불러오지 못했습니다.",
                "hint": "AI/kdpp_ai_ocr_integrated 모듈 경로를 확인하세요.",
            },
        )

    parsed = parse_label(label_text)
    materials = parsed.get("materials") or {}
    raw_ocr_preview = parsed.get("raw_ocr_preview", "")
    care_instruction = parsed.get("care_text") or "라벨 표기법에 맞춰 관리하세요."

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

@app.post("/auth/signup", tags=["auth"])
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    email = normalize_email(request.email)
    nickname = request.nickname.strip()
    password = request.password

    if not EMAIL_PATTERN.fullmatch(email or ""):
        raise HTTPException(status_code=400, detail="올바른 이메일을 입력해 주세요.")
    if len(nickname) < 2:
        raise HTTPException(status_code=400, detail="닉네임은 2자 이상 입력해 주세요.")
    ensure_password_rules(password)

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

    return {
        "status": "success",
        "message": "회원가입이 완료되었습니다.",
        "user": auth_user_response(user),
    }


@app.post("/auth/login", tags=["auth"])
def login(request: LoginRequest, db: Session = Depends(get_db)):
    email = normalize_email(request.email)
    check_login_lockout(email)

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

    clear_login_failures(email)

    raw_token, _access_token = create_access_token(user, db)

    return {
        "status": "success",
        "message": "로그인되었습니다.",
        "user": auth_user_response(user),
        "access_token": raw_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    }


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

    # 재인증도 로그인과 같은 잠금 카운터를 쓴다. 토큰만 탈취한 공격자가 이 경로로
    # 비밀번호를 무제한 추측하면 로그인 잠금이 무의미해지고, 맞히는 순간 다른 세션이
    # 모두 끊겨 계정을 통째로 빼앗기기 때문이다.
    check_login_lockout(user.email)

    # 401은 "이 세션이 더 이상 유효하지 않다"는 뜻으로만 쓴다. 프론트가 401을
    # 세션 만료로 보고 강제 로그아웃시키므로(session_expiry_handler), 비밀번호를
    # 한 번 잘못 친 것만으로 로그아웃되면 안 된다. 재인증 실패는 400으로 낸다.
    if not verify_password(request.current_password, user.password_hash):
        record_login_failure(user.email)
        raise HTTPException(status_code=400, detail="현재 비밀번호가 올바르지 않습니다.")

    clear_login_failures(user.email)

    ensure_password_rules(request.new_password)

    if request.new_password == request.current_password:
        raise HTTPException(status_code=400, detail="새 비밀번호가 기존 비밀번호와 같습니다.")

    user.password_hash = hash_password(request.new_password)
    db.query(database.AccessToken).filter(
        database.AccessToken.user_id == user.id
    ).delete(synchronize_session=False)
    db.commit()

    # 기존 토큰을 모두 지운 뒤에 발급해야 새 토큰이 함께 삭제되지 않는다.
    raw_token, _new_token = create_access_token(user, db)

    return {
        "status": "success",
        "message": "비밀번호가 변경되었습니다.",
        "user": auth_user_response(user),
        "access_token": raw_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    }


@app.post("/auth/withdraw", tags=["auth"])
def withdraw(
    request: WithdrawRequest,
    access_token: database.AccessToken = Depends(get_current_access_token),
    db: Session = Depends(get_db),
):
    """비밀번호를 확인한 뒤 계정·토큰·분석 이력을 한 트랜잭션에서 지운다.

    DELETE 메서드 대신 POST를 쓰는 이유는 프론트 공용 HTTP 헬퍼가
    GET/POST만 지원하기 때문이다(docs/SCAN_API_CONTRACT.md 참조).
    """
    user = db.query(database.User).filter(database.User.id == access_token.user_id).first()

    if user is None:
        db.delete(access_token)
        db.commit()
        raise HTTPException(status_code=401, detail="로그인이 만료되었습니다.")

    check_login_lockout(user.email)

    # 비밀번호 변경과 같은 이유로 재인증 실패는 400으로 낸다(401은 세션 만료 전용).
    if not verify_password(request.password, user.password_hash):
        record_login_failure(user.email)
        raise HTTPException(status_code=400, detail="비밀번호가 올바르지 않습니다.")

    clear_login_failures(user.email)

    user_id = user.id

    # users 행만 지우면 analysis_results·access_tokens에 고아 행이 남는다.
    # 외래키 ON DELETE가 걸려 있지 않으므로 애플리케이션에서 함께 지운다.
    db.query(database.AnalysisResult).filter(
        database.AnalysisResult.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(database.AccessToken).filter(
        database.AccessToken.user_id == user_id
    ).delete(synchronize_session=False)
    db.delete(user)
    db.commit()

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
    raw_ocr_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
    # 스캔 1회가 곧 외부 OCR 호출 비용이므로 로그인 사용자만 허용합니다.
    current_user: database.User = Depends(get_current_user),
):
    label_text = extract_label_text(image, raw_ocr_text)
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
    db.commit()
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
    results = (
        db.query(database.AnalysisResult)
        .filter(database.AnalysisResult.user_id == current_user.id)
        .order_by(database.AnalysisResult.id.desc())
        .all()
    )

    return {
        "status": "success",
        "user": auth_user_response(current_user),
        "history": [serialize_analysis_result(result) for result in results],
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
