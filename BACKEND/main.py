from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import json
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
    materials: dict[str, float]

# 4. 탄소발자국 계산 함수
def calculate_carbon(materials: dict[str, float]) -> float:
    carbon_table = {
        "cotton": 2.1,
        "polyester": 5.5,
        "nylon": 6.0,
        "wool": 8.0
    }

    total = 0.0

    for name, ratio in materials.items():
        material_name = name.lower()

        if material_name in carbon_table:
            total += carbon_table[material_name] * (ratio / 100)

    return round(total, 2)

# --- API 엔드포인트 시작 ---

@app.get("/")
def read_root():
    return {"status": "success", "message": "K-DPP 백엔드 서버가 가동 중입니다!"}

@app.post("/analyze")
def analyze_clothes(request: AnalyzeRequest, db: Session = Depends(get_db)):
    # 지금은 소재 혼용률 데이터를 받아 탄소발자국을 계산합니다.
    materials = request.materials

    # 1. 각 소재 비율이 음수인지 검사
    for name, ratio in materials.items():
        if ratio < 0:
            raise HTTPException(
                status_code=400,
                detail=f"{name} 비율이 음수입니다."
            )

    # 2. 전체 비율의 합이 100인지 검사
    total_ratio = sum(materials.values())
    if total_ratio != 100:
        raise HTTPException(
            status_code=400,
            detail="전체 비율의 합이 100이 아닙니다."
        )

    # 3. 탄소발자국 계산
    total_carbon = calculate_carbon(materials)

    # 4. DB에 분석 결과 저장
    new_result = database.AnalysisResult(
        materials=json.dumps(materials, ensure_ascii=False),
        carbon_footprint=total_carbon
    )
    db.add(new_result)
    db.commit()
    db.refresh(new_result)

    return {
        "status": "success",
        "message": "분석 완료",
        "materials": materials,
        "carbon_footprint": total_carbon,
        "care_instruction": "30도 이하 물에서 중성세제로 손세탁하세요.",
        "saved_result_id": new_result.id
    }

@app.get("/materials")
def get_materials(db: Session = Depends(get_db)):
    # DB에 저장된 소재 목록을 가져오는 API (이동재 님이 데이터를 채우면 작동)
    materials = db.query(database.Clothing).all()
    return materials