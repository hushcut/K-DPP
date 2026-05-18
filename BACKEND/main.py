from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import json
import shutil
import sys
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

# 1. 앱 객체 생성
app = FastAPI(
    title="K-DPP Backend",
    description="K-DPP v1 탄소배출량 계산 API",
    version="0.1.0",
)

@app.on_event("startup")
def seed_material_data():
    init_data.seed_materials()

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

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": message,
            "detail": detail,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "message": "요청 형식이 올바르지 않습니다.",
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
class AnalyzeRequest(BaseModel):
    materials: dict[str, float]
    raw_ocr_text: str | None = None

# 4. 소재명 매칭 및 탄소발자국 계산 함수
def normalize_email(email: str) -> str:
    return email.strip().lower()


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


def auth_user_response(user: database.User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "nickname": user.nickname,
    }
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


def calculate_carbon(materials: dict[str, float], db: Session) -> tuple[float, list[str]]:
    total = 0.0
    unknown_materials = []

    for name, ratio in materials.items():
        material = find_material(db, name)

        if material is None:
            unknown_materials.append(name)
            continue

        total += material.carbon_factor * (ratio / 100)

    return round(total, 2), unknown_materials


def build_analysis_response(
    materials: dict[str, float],
    db: Session,
    raw_ocr_text: str | None = None,
    care_instruction: str | None = None,
    title: str | None = None,
    category: str | None = None,
):
    for name, ratio in materials.items():
        if ratio < 0:
            raise HTTPException(status_code=400, detail=f"{name} 비율이 음수입니다.")

    total_ratio = sum(materials.values())
    if total_ratio < 99.5 or total_ratio > 100.5:
        raise HTTPException(
            status_code=400,
            detail=f"전체 비율의 합이 100이 아닙니다. 현재 합계: {round(total_ratio, 2)}",
        )

    total_carbon, unknown_materials = calculate_carbon(materials, db)

    if unknown_materials:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "DB에 등록되지 않은 소재가 있습니다.",
                "unknown_materials": unknown_materials,
            },
        )

    new_result = database.AnalysisResult(
        materials=json.dumps(materials, ensure_ascii=False),
        carbon_footprint=total_carbon,
        unit="kg CO2eq",
        raw_ocr_text=raw_ocr_text,
        unknown_materials=json.dumps(unknown_materials, ensure_ascii=False),
    )
    db.add(new_result)
    db.commit()
    db.refresh(new_result)

    response = {
        "status": "success",
        "message": "분석 완료",
        "materials": materials,
        "carbon_footprint": total_carbon,
        "unit": "kg CO2eq",
        "care_instruction": care_instruction or "30도 이하 물에서 중성세제로 손세탁하세요.",
        "saved_result_id": new_result.id,
    }

    if title:
        response["title"] = title
    if category:
        response["category"] = category

    return response


def extract_label_text(image: UploadFile, raw_ocr_text: str | None) -> str:
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
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        shutil.copyfileobj(image.file, temp_file)
        temp_path = temp_file.name

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
        raise HTTPException(
            status_code=502,
            detail={
                "message": "AI OCR 처리에 실패했습니다.",
                "error": str(exc),
            },
        ) from exc
    finally:
        Path(temp_path).unlink(missing_ok=True)


def parse_label_materials(label_text: str) -> tuple[dict[str, float], str]:
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

    if not materials:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "라벨에서 소재 혼용률을 찾지 못했습니다.",
                "raw_ocr_preview": parsed.get("raw_ocr_preview", ""),
            },
        )

    care_instruction = parsed.get("care_text") or "라벨 표기법에 맞춰 관리하세요."
    return materials, care_instruction

# --- API 엔드포인트 시작 ---

@app.post("/auth/signup", tags=["auth"])
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    email = normalize_email(request.email)
    nickname = request.nickname.strip()
    password = request.password.strip()

    if not email or "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="올바른 이메일을 입력해 주세요.")
    if len(nickname) < 2:
        raise HTTPException(status_code=400, detail="닉네임은 2자 이상 입력해 주세요.")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상 입력해 주세요.")

    existing_user = db.query(database.User).filter(database.User.email == email).first()
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")

    user = database.User(
        email=email,
        nickname=nickname,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "status": "success",
        "message": "회원가입이 완료되었습니다.",
        "user": auth_user_response(user),
    }


@app.post("/auth/login", tags=["auth"])
def login(request: LoginRequest, db: Session = Depends(get_db)):
    email = normalize_email(request.email)
    user = db.query(database.User).filter(database.User.email == email).first()

    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    return {
        "status": "success",
        "message": "로그인되었습니다.",
        "user": auth_user_response(user),
        "access_token": secrets.token_urlsafe(32),
        "token_type": "bearer",
    }
@app.get("/", tags=["system"])
def read_root():
    return {"status": "success", "message": "K-DPP 백엔드 서버가 가동 중입니다!"}

@app.post(
    "/analyze",
    tags=["v1-carbon"],
    summary="의류 혼용률 기반 탄소배출량 계산",
    description="AI/OCR 또는 프론트에서 전달한 소재 혼용률을 DB의 소재별 탄소배출계수와 매칭해 예상 탄소배출량을 계산합니다.",
)
def analyze_clothes(request: AnalyzeRequest, db: Session = Depends(get_db)):
    return build_analysis_response(
        materials=request.materials,
        db=db,
        raw_ocr_text=request.raw_ocr_text,
    )


@app.post("/api/scan", tags=["v1-scan"])
def scan_label(
    image: UploadFile = File(...),
    raw_ocr_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    label_text = extract_label_text(image, raw_ocr_text)
    materials, care_instruction = parse_label_materials(label_text)

    return build_analysis_response(
        materials=materials,
        db=db,
        raw_ocr_text=label_text,
        care_instruction=care_instruction,
        title="스캔한 의류",
        category="상의",
    )

@app.get("/history", tags=["v1-carbon"])
def get_history(db: Session = Depends(get_db)):
    # DB에 저장된 분석 결과 목록을 가져오는 API
    results = db.query(database.AnalysisResult).order_by(database.AnalysisResult.id.desc()).all()


    history = []
    for result in results:
        history.append({
            "id": result.id,
            "materials": json.loads(result.materials),
            "carbon_footprint": result.carbon_footprint,
            "unit": result.unit or "kg CO2eq",
            "unknown_materials": json.loads(result.unknown_materials or "[]"),
            "created_at": result.created_at
        })

    return {
        "status": "success",
        "history": history
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
