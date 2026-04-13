from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 1. DB 파일 경로 설정 (현재 폴더에 k_dpp.db 파일이 자동으로 생깁니다)
SQLALCHEMY_DATABASE_URL = "sqlite:///./k_dpp.db"

# 2. 엔진 및 세션 설정
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# 3. 의류 데이터 테이블 구조 (이동재 님이 데이터를 채울 공간)
class Clothing(Base):
    __tablename__ = "clothing"
    
    id = Column(Integer, primary_key=True, index=True)
    material_name = Column(String)  # 소재명 (예: 면, 폴리에스터)
    carbon_factor = Column(Float)   # 탄소 배출 계수
    expected_life = Column(Integer) # 기대 수명 (개월)

# 4. 분석 결과 저장 테이블
class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    materials = Column(String)          # {"cotton": 80, "polyester": 20} 형태를 문자열로 저장
    carbon_footprint = Column(Float)    # 계산된 탄소발자국 수치

# 5. 서버 실행 시 테이블이 없으면 자동으로 생성해주는 코드
Base.metadata.create_all(bind=engine)