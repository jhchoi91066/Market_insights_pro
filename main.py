# -*- coding: utf-8 -*-
"""
이 파일은 Market Insights Pro 프로젝트의 FastAPI 서버 메인 애플리케이션입니다.
"""
from typing import List, Tuple
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import os
from functools import lru_cache

# 핵심 분석 엔진과 데이터베이스 연결 정보 불러오기
from core.analyzer import MarketAnalyzer
# from core.database import get_db_connection # 현재는 analyzer에서 직접 데이터 로드하므로 필요 없음

app = FastAPI(
    title="Market Insights Pro API",
    description="AI 기반 이커머스 시장 분석 플랫폼 API",
    version="0.1.0",
)

# MarketAnalyzer 인스턴스 초기화 (애플리케이션 시작 시 한 번만 로드)
# 실제 서비스에서는 데이터베이스에서 데이터를 로드하도록 변경될 예정
DATA_FILE_PATH = os.path.join(os.path.dirname(__file__), 'data', 'amazon_products_sales_data_cleaned.csv')
market_analyzer = MarketAnalyzer(DATA_FILE_PATH)

# -----------------------------------------------------------------------------
# 1단계: 기본 엔드포인트 (Hello World)
# -----------------------------------------------------------------------------
@app.get("/")
async def read_root():
    return {"message": "Hello World! Market Insights Pro API is running."}

# -----------------------------------------------------------------------------
# 2단계: API 엔드포인트 - 카테고리 경쟁 분석
# -----------------------------------------------------------------------------

# 2.1 데이터 모델 정의 (주문서 양식 만들기)
class CategoryAnalysisRequest(BaseModel):
    category: str = Field(..., example="Laptops", description="분석할 상품 카테고리")
    price_range: Tuple[float, float] = Field((0.0, 10000.0), example=(200.0, 1000.0), description="분석할 가격 범위 (최소, 최대)")
    num_bins: int = Field(5, ge=1, le=10, description="가격 구간을 나눌 개수 (1~10)")

@app.post("/analyze/category")
async def analyze_category(request: CategoryAnalysisRequest):
    """
    특정 카테고리의 경쟁 강도를 분석하고 결과를 반환합니다.
    - 경쟁 제품 수
    - 가격 구간별 평균 평점
    - 판매량 기준 TOP 10 제품
    - 진입 난이도 점수
    """
    if market_analyzer.df.empty:
        raise HTTPException(status_code=500, detail="데이터 로드에 실패했습니다. 서버 로그를 확인하세요.")

    try:
        results = market_analyzer.analyze_category_competition(
            request.category,
            request.price_range,
            request.num_bins
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 중 오류 발생: {str(e)}")

# -----------------------------------------------------------------------------
# 3단계: API 엔드포인트 - 가격 공백 구간 탐색
# -----------------------------------------------------------------------------
class PriceGapAnalysisRequest(BaseModel):
    category: str = Field(..., example="Phones", description="분석할 상품 카테고리")
    bin_width: int = Field(100, ge=10, le=500, description="가격을 나눌 구간의 너비 (10~500)")

@app.post("/analyze/price-gaps")
async def analyze_price_gaps(request: PriceGapAnalysisRequest):
    """
    특정 카테고리 내에서 가격 공백 구간(기회 시장)을 탐색합니다.
    - 가격대별 제품 분포
    - 잠재적 가격 공백 구간 (제품 수가 적은 구간)
    """
    if market_analyzer.df.empty:
        raise HTTPException(status_code=500, detail="데이터 로드에 실패했습니다. 서버 로그를 확인하세요.")

    try:
        results = market_analyzer.find_price_gaps(
            request.category,
            request.bin_width
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 중 오류 발생: {str(e)}")

# -----------------------------------------------------------------------------
# 4단계: API 엔드포인트 - 성공 키워드 추출
# -----------------------------------------------------------------------------
class KeywordAnalysisRequest(BaseModel):
    category: str = Field(..., example="Headphones", description="분석할 상품 카테고리")
    rating_threshold: float = Field(4.5, ge=1.0, le=5.0, description="성공 기준으로 삼을 최소 평점")
    reviews_threshold: int = Field(100, ge=0, description="성공 기준으로 삼을 최소 리뷰 수")
    num_keywords: int = Field(20, ge=5, le=50, description="추출할 키워드 개수")

@app.post("/analyze/keywords")
async def analyze_keywords(request: KeywordAnalysisRequest):
    """
    성공적인 제품들(평점 및 리뷰 수가 높은)로부터 핵심 키워드를 추출합니다.
    """
    if market_analyzer.df.empty:
        raise HTTPException(status_code=500, detail="데이터 로드에 실패했습니다. 서버 로그를 확인하세요.")

    try:
        results = market_analyzer.extract_success_keywords(
            request.category,
            request.rating_threshold,
            request.reviews_threshold,
            request.num_keywords
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 중 오류 발생: {str(e)}")

# -----------------------------------------------------------------------------
# 5단계: API 엔드포인트 - 시장 포화도 계산
# -----------------------------------------------------------------------------
class SaturationAnalysisRequest(BaseModel):
    category: str = Field(..., example="Printers & Scanners", description="분석할 상품 카테고리")

@app.post("/analyze/saturation")
async def analyze_saturation(request: SaturationAnalysisRequest):
    """
    특정 카테고리의 시장 포화도를 계산합니다.
    (상위 10개 제품이 전체 판매량의 몇 %를 차지하는지로 측정)
    """
    if market_analyzer.df.empty:
        raise HTTPException(status_code=500, detail="데이터 로드에 실패했습니다. 서버 로그를 확인하세요.")

    try:
        results = market_analyzer.calculate_market_saturation(
            request.category
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 중 오류 발생: {str(e)}")

# -----------------------------------------------------------------------------
# 6단계: API 엔드포인트 - 종합 분석 보고서 (캐싱 적용)
# -----------------------------------------------------------------------------
class FullReportRequest(BaseModel):
    category: str = Field(..., example="Headphones", description="분석할 상품 카테고리")
    price_range: Tuple[float, float] = Field((0.0, 5000.0), example=(50.0, 500.0), description="분석할 가격 범위 (최소, 최대)")
    rating_threshold: float = Field(4.5, ge=1.0, le=5.0, description="성공 기준으로 삼을 최소 평점")
    reviews_threshold: int = Field(100, ge=0, description="성공 기준으로 삼을 최소 리뷰 수")

@lru_cache(maxsize=32)
def _get_cached_full_report(category: str, price_range: tuple, rating_threshold: float, reviews_threshold: int):
    """
    실제 분석을 수행하고 결과를 캐싱하는 내부 함수.
    lru_cache는 hashable한 인자만 받을 수 있으므로, 복잡한 Pydantic 모델 대신 기본 타입을 인자로 받습니다.
    """
    print(f"--- CACHE MISS: '{category}'에 대한 종합 분석을 새로 수행합니다. ---")
    # 각 분석 모듈을 순차적으로 호출
    competition_results = market_analyzer.analyze_category_competition(
        category,
        price_range
    )
    price_gap_results = market_analyzer.find_price_gaps(
        category
    )
    keyword_results = market_analyzer.extract_success_keywords(
        category,
        rating_threshold,
        reviews_threshold
    )
    saturation_results = market_analyzer.calculate_market_saturation(
        category
    )

    # 모든 결과를 하나의 보고서로 취합
    full_report = {
        "report_title": f"'{category}' 카테고리 종합 분석 보고서",
        "competition_analysis": competition_results,
        "price_gap_analysis": price_gap_results,
        "success_keyword_analysis": keyword_results,
        "market_saturation_analysis": saturation_results
    }
    return full_report

@app.post("/analyze/full-report")
async def analyze_full_report(request: FullReportRequest):
    """
    한 번의 요청으로 특정 카테고리에 대한 모든 분석을 수행하고 종합 보고서를 반환합니다.
    실제 계산은 캐시된 내부 함수를 호출하여 수행됩니다.
    """
    if market_analyzer.df.empty:
        raise HTTPException(status_code=500, detail="데이터 로드에 실패했습니다. 서버 로그를 확인하세요.")

    try:
        # Pydantic 모델의 필드를 캐시된 도우미 함수로 전달
        report = _get_cached_full_report(
            category=request.category,
            price_range=request.price_range,
            rating_threshold=request.rating_threshold,
            reviews_threshold=request.reviews_threshold
        )
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"종합 보고서 생성 중 오류 발생: {str(e)}")

# 서버 실행 방법 (터미널에서):
# uvicorn main:app --reload --host 0.0.0.0 --port 8000
# --reload: 코드 변경 시 서버 자동 재시작
# --host 0.0.0.0: 모든 IP에서 접속 허용 (Docker 컨테이너 내에서 필요)
# --port 8000: 8000번 포트 사용
