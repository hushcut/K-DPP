from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import database  

# 1. 앱 객체 생성
app = FastAPI()

# 2. DB 세션 가져오기 함수 (DB 연결용)
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 3. 데이터 규격 정의 (Pydantic: 프런트엔드와 주고받을 형식)
class AnalyzeRequest(BaseModel):
    image_url: str
    cloth_type: str  # 예: 상의, 하의 등

# --- API 엔드포인트 시작 ---

@app.get("/")
def read_root():
    return {"status": "success", "message": "K-DPP 백엔드 서버가 가동 중입니다!"}

@app.post("/analyze")
def analyze_clothes(request: AnalyzeRequest, db: Session = Depends(get_db)):
    # 여기에 나중에 AI 모델(OCR) 로직이 들어갈 예정입니다.
    # 지금은 테스트용 가짜 데이터를 반환합니다.
    return {
        "status": "success",
        "result": {
            "material": "Cotton 100%",
            "carbon_footprint": "1.5kg CO2",
            "expected_life": "24 months"
        }
    }

@app.get("/materials")
def get_materials(db: Session = Depends(get_db)):
    # DB에 저장된 소재 목록을 가져오는 API (이동재 님이 데이터를 채우면 작동)
    materials = db.query(database.Clothing).all()
    return materials