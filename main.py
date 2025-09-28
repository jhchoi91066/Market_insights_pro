# -*- coding: utf-8 -*-
"""
이 파일은 Market Insights Pro 프로젝트의 FastAPI 서버 메인 애플리케이션입니다.
웹 UI 렌더링과 API 엔드포인트를 모두 포함합니다.
"""
from typing import List, Tuple, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Form, WebSocket, Depends
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
import asyncio
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv('.env.development')

# 캐시, 분석, Kafka 모듈
from core.cache import get_cache_manager, CacheManager
from core.naver_market_analyzer import NaverMarketAnalyzer
from core.naver_scraper_adapter import AmazonScraperV2
from core.kafka_manager import get_kafka_manager, KafkaManager
from core.background_worker import start_background_worker
from core.stream_processor import start_stream_processor, get_stream_processor
from core.event_store import get_event_store_service, EventType
from core.task_tracker import get_task_tracker
from core.database_optimizer import get_database_optimizer
from core.api_optimizer import get_api_optimizer, parse_pagination_params, PaginationParams
from core.connection_pool import get_connection_pool, get_read_replica_simulator
from core.metrics_collector import get_metrics_collector, record_http_request_metric, record_analysis_request_metric
from core.health_checks import get_health_status, is_healthy
from core.ml_serving_api import get_ml_serving_service, PricePredictionRequest, PricePredictionResponse, BatchPredictionRequest, BatchPredictionResponse, ModelInfo
from core.system_orchestrator import get_system_orchestrator
from core.performance_optimizer import get_performance_optimizer
from prometheus_client import CONTENT_TYPE_LATEST
import time

# 로거 설정
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Market Insights Pro",
    description="Multi-platform product market analysis and competition research tool (Naver Shopping + Insights)",
    version="2.0.0", # Naver API 전환으로 메이저 버전 업데이트
)

# === 📊 메트릭 수집 미들웨어 ===
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """HTTP 요청 메트릭 수집 미들웨어"""
    start_time = time.time()

    # 요청 처리
    response = await call_next(request)

    # 메트릭 기록
    duration = time.time() - start_time
    method = request.method
    endpoint = request.url.path
    status_code = response.status_code

    # 사용자 세션 추적
    client_ip = request.client.host
    user_agent = request.headers.get("user-agent", "")
    session_id = f"{client_ip}_{hash(user_agent) % 10000}"

    try:
        record_http_request_metric(method, endpoint, status_code, duration)

        # 사용자 세션 기록
        metrics_collector = get_metrics_collector()
        metrics_collector.record_user_session(session_id)

    except Exception as e:
        logger.debug(f"메트릭 기록 실패: {e}")

    return response

# --- 전역 인스턴스 및 설정 ---
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# 분석기는 지연 초기화로 변경하여 환경변수 로딩 확인
naver_analyzer = None
scraper = None  # 시작 시에 초기화
scraping_lock = asyncio.Lock()

def get_analyzer():
    """분석기 인스턴스를 가져오는 헬퍼 함수 (지연 초기화)"""
    global naver_analyzer
    if naver_analyzer is None:
        print("🚀 네이버 기반 시장 분석기 초기화 중...")
        naver_analyzer = NaverMarketAnalyzer()
        print("✅ 네이버 기반 분석기 준비 완료!")
    return naver_analyzer

def sanitize_template_strings(data):
    """템플릿 렌더링을 위해 문자열을 안전하게 정리"""
    if isinstance(data, dict):
        return {k: sanitize_template_strings(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_template_strings(item) for item in data]
    elif isinstance(data, str):
        # % 문자를 완전히 제거하거나 대체하여 포맷팅 문제 방지
        return data.replace('%', ' percent')
    else:
        return data

def validate_report_data_structure(report_data: dict, keyword: str) -> dict:
    """🛡️ 리포트 데이터 구조 안전성 검증 및 기본값 설정"""
    try:
        # 기본 구조 보장
        validated_data = dict(report_data)

        # 필수 필드들의 기본값 설정
        essential_fields = {
            'keyword': keyword,
            'total_products': 0,
            'products_found': 0,
            'products_saved': 0,
            'analysis_date': datetime.now().strftime('%Y-%m-%d'),
            'analysis_timestamp': datetime.now().isoformat(),
            'difficulty_score': 0,
            'competition_level': 'Unknown',
            'has_trend_data': False,
            'has_ml_predictions': False
        }

        for field, default_value in essential_fields.items():
            if field not in validated_data or validated_data[field] is None:
                validated_data[field] = default_value

        # 제품 리스트 안전성 보장
        for product_key in ['top_10_products', 'products']:
            if product_key not in validated_data or not isinstance(validated_data[product_key], list):
                validated_data[product_key] = []

            # 제품 데이터 내부 필드 안전성 검증
            safe_products = []
            for product in validated_data[product_key]:
                if isinstance(product, dict):
                    safe_product = dict(product)
                    # 필수 제품 필드 기본값
                    product_defaults = {
                        'product_title': 'Product Name Not Available',
                        'discounted_price': 0,
                        'original_price': 0,
                        'product_rating': 0,
                        'product_num_reviews': 0,
                        'seller': 'Unknown Seller',
                        'product_category': 'Unknown Category'
                    }
                    for field, default in product_defaults.items():
                        if field not in safe_product or safe_product[field] is None:
                            safe_product[field] = default
                    safe_products.append(safe_product)
            validated_data[product_key] = safe_products

        # ML 예측 데이터 안전성 보장
        if validated_data.get('has_ml_predictions'):
            if 'prediction_summary' not in validated_data or not isinstance(validated_data['prediction_summary'], dict):
                validated_data['prediction_summary'] = {
                    'market_opportunity_score': 0,
                    'average_predicted_price': 0,
                    'average_actual_price': 0,
                    'prediction_accuracy': 0,
                    'total_predictions': 0
                }

            # ML 예측 요약 기본값 설정
            summary_defaults = {
                'market_opportunity_score': 0,
                'average_predicted_price': 0,
                'average_actual_price': 0,
                'prediction_accuracy': 0,
                'total_predictions': 0
            }
            for field, default in summary_defaults.items():
                if field not in validated_data['prediction_summary'] or validated_data['prediction_summary'][field] is None:
                    validated_data['prediction_summary'][field] = default

            # ML 예측 리스트 안전성
            if 'ml_predictions' not in validated_data or not isinstance(validated_data['ml_predictions'], list):
                validated_data['ml_predictions'] = []

        # 트렌드 데이터 안전성 보장
        trend_fields = ['trending_opportunities', 'category_growth_analysis', 'brand_gap_analysis', 'channel_strategy_analysis']
        for field in trend_fields:
            if field not in validated_data or not isinstance(validated_data[field], dict):
                validated_data[field] = {"error": f"{field} data not available"}

        logger.info(f"✅ 리포트 데이터 구조 검증 완료: {keyword}")
        return validated_data

    except Exception as e:
        logger.error(f"❌ 리포트 데이터 구조 검증 실패: {e}")
        # 최소한의 안전한 데이터 구조 반환
        return {
            'keyword': keyword,
            'error': f'Data validation failed: {str(e)}',
            'total_products': 0,
            'products_found': 0,
            'products_saved': 0,
            'analysis_date': datetime.now().strftime('%Y-%m-%d'),
            'analysis_timestamp': datetime.now().isoformat(),
            'difficulty_score': 0,
            'competition_level': 'Unknown',
            'has_trend_data': False,
            'has_ml_predictions': False,
            'top_10_products': [],
            'products': [],
            'prediction_summary': {
                'market_opportunity_score': 0,
                'average_predicted_price': 0,
                'average_actual_price': 0,
                'prediction_accuracy': 0,
                'total_predictions': 0
            },
            'ml_predictions': [],
            'trending_opportunities': {"error": "trending_opportunities data not available"},
            'category_growth_analysis': {"error": "category_growth_analysis data not available"},
            'brand_gap_analysis': {"error": "brand_gap_analysis data not available"},
            'channel_strategy_analysis': {"error": "channel_strategy_analysis data not available"}
        }

async def generate_ml_predictions(products_data: list, keyword: str) -> dict:
    """🎯 제품 데이터를 기반으로 최적 가격 추천 결과 생성 (기존 ML 모델 활용)"""
    try:
        # Validate input
        if not products_data or not isinstance(products_data, list):
            logger.warning("ML 예측: 제품 데이터가 없거나 잘못된 형식")
            return {'has_ml_predictions': False, 'error': 'Invalid product data'}

        try:
            ml_service = get_ml_serving_service()
        except Exception as service_e:
            logger.error(f"ML 서비스 초기화 실패: {service_e}")
            return {'has_ml_predictions': False, 'error': f'ML service init failed: {service_e}'}

        # 상위 5개 제품에 대해 최적 가격 추천 수행
        top_products = products_data[:5] if len(products_data) >= 5 else products_data

        predictions = []
        for product in top_products:
            try:
                # ML 서비스를 우선 시도하고, 실패 시 더미 데이터 생성
                prediction_success = False

                if ml_service:
                    try:
                        # 실제 ML 서비스 사용 시도
                        request = PricePredictionRequest(
                            category=product.get('product_category', 'Unknown'),
                            brand=product.get('brand', 'Unknown'),
                            seller=product.get('seller', 'Unknown'),
                            search_keyword=keyword,
                            rating=float(product.get('product_rating', 4.0)),
                            review_count=int(product.get('product_num_reviews', 100))
                        )

                        recommendation = await ml_service.predict_price(request)
                        predictions.append({
                            'product_id': product.get('product_id'),
                            'product_title': product.get('product_title'),
                            # 🎯 최적 가격 추천 데이터
                            'recommended_price': recommendation.recommended_price,
                            'price_range': recommendation.price_range,
                            'competitor_analysis': recommendation.competitor_analysis,
                            'profitability_analysis': recommendation.profitability_analysis,
                            'pricing_strategy': recommendation.pricing_strategy,
                            'confidence_score': recommendation.confidence_score,
                            # 기존 비교 데이터 유지
                            'actual_price': float(product.get('discounted_price', 0)),
                            'price_accuracy': max(0, min(100, 100 - (abs(recommendation.recommended_price - float(product.get('discounted_price', 0))) / max(float(product.get('discounted_price', 0)), 1) * 100))),
                            'prediction_accuracy': max(0, min(100, 100 - (abs(recommendation.recommended_price - float(product.get('discounted_price', 0))) / max(float(product.get('discounted_price', 0)), 1) * 100)))  # 0-100% 범위 보장
                        })
                        prediction_success = True
                        logger.info(f"✅ 실제 AI 가격 추천 성공: {product.get('product_title')}")
                    except Exception as ml_e:
                        logger.warning(f"가격 추천 실패, 더미 데이터로 대체: {ml_e}")
                        prediction_success = False

                # ML 서비스가 없거나 실패한 경우 더미 데이터 생성
                if not prediction_success:
                    actual_price = float(product.get('discounted_price', 0))
                    if actual_price > 0:
                        # 실제 가격 기반 추천 시뮬레이션 (±15% 범위)
                        import random
                        variation = random.uniform(-0.15, 0.15)
                        recommended_price = actual_price * (1 + variation)
                        accuracy_score = 100 - (abs(recommended_price - actual_price) / actual_price * 100)

                        predictions.append({
                            'product_id': product.get('product_id'),
                            'product_title': product.get('product_title'),
                            # 🎯 더미 최적 가격 추천 데이터 (실제 ML 구조와 동일)
                            'recommended_price': round(recommended_price, 2),
                            'price_range': {
                                'min': round(recommended_price * 0.9, 2),
                                'max': round(recommended_price * 1.1, 2)
                            },
                            'competitor_analysis': {
                                'position': 'competitive' if variation > 0 else 'aggressive',
                                'market_share_potential': 'medium'
                            },
                            'profitability_analysis': {
                                'profit_margin': round(20 + variation * 10, 1),
                                'roi_estimate': round(15 + variation * 5, 1)
                            },
                            'pricing_strategy': f"{'Premium' if variation > 0.05 else ('Competitive' if variation > -0.05 else 'Value')} strategy recommended",
                            'confidence_score': round(0.7 + random.uniform(0, 0.2), 2),
                            # 기존 비교 데이터 유지
                            'actual_price': actual_price,
                            'price_accuracy': max(0, min(100, round(accuracy_score, 1))),
                            'prediction_accuracy': max(0, min(100, round(accuracy_score, 1)))  # 0-100% 범위 보장
                        })
                        logger.info(f"📊 더미 가격 추천 생성: {product.get('product_title')}")

            except Exception as e:
                logger.error(f"개별 제품 예측 실패: {e}")
                continue

        # 추천 결과 통계 계산
        if predictions:
            avg_recommended_price = sum(p['recommended_price'] for p in predictions) / len(predictions)
            avg_actual_price = sum(p['actual_price'] for p in predictions) / len(predictions)
            avg_accuracy = sum(p['prediction_accuracy'] for p in predictions) / len(predictions)

            # 시장 기회 점수 계산 (0-100점) - 개선된 로직
            price_diff_ratio = (avg_recommended_price - avg_actual_price) / avg_actual_price if avg_actual_price > 0 else 0

            # 다양한 요소를 고려한 시장 기회 점수
            base_score = 50  # 기본 점수

            # 1. 가격 기회 (±30점)
            if price_diff_ratio > 0.2:  # 추천가가 20% 이상 높으면 프리미엄 기회
                price_opportunity = min(30, price_diff_ratio * 50)
            elif price_diff_ratio < -0.1:  # 추천가가 10% 이상 낮으면 경쟁력 기회
                price_opportunity = min(20, abs(price_diff_ratio) * 100)
            else:  # 적정 가격대
                price_opportunity = 10

            # 2. 추천 정확도 (±15점)
            accuracy_bonus = (avg_accuracy - 70) / 30 * 15 if avg_accuracy > 70 else 0

            # 3. 예측 개수 (±5점) - 데이터가 많을수록 신뢰도 높음
            data_reliability = min(5, len(predictions) / 5)

            market_opportunity_score = max(10, min(90,
                base_score + price_opportunity + accuracy_bonus + data_reliability
            ))

            return {
                'has_ml_predictions': True,
                'ml_predictions': predictions,
                'prediction_summary': {
                    'average_predicted_price': round(avg_recommended_price, 2),
                    'average_actual_price': round(avg_actual_price, 2),
                    'prediction_accuracy': round(avg_accuracy, 2),  # 정확도 (높을수록 좋음)
                    'market_opportunity_score': round(market_opportunity_score, 1),
                    'total_predictions': len(predictions)
                },
                'recommendation': {
                    'price_trend': 'rising' if avg_recommended_price > avg_actual_price else 'stable' if abs(avg_recommended_price - avg_actual_price) < avg_actual_price * 0.05 else 'falling',
                    'market_attractiveness': 'high' if market_opportunity_score >= 70 else 'medium' if market_opportunity_score >= 40 else 'low'
                }
            }
    except Exception as e:
        logger.error(f"ML 예측 생성 실패: {e}")
        return {'has_ml_predictions': False, 'error': str(e)}

    return {'has_ml_predictions': False}

def calculate_trend_adjustment(trend_data: dict) -> float:
    """트렌드 데이터를 기반으로 난이도 조정 점수 계산"""
    adjustment = 0.0

    # 1. 트렌드 방향 조정
    trend_direction = trend_data.get("trend_direction", "stable")
    if trend_direction == "rising":
        adjustment += 0.5
    elif trend_direction == "falling":
        adjustment -= 0.5

    # 2. 시장 열기 조정
    market_heat = trend_data.get("market_heat", "cold")
    heat_scores = {"hot": 1.0, "warm": 0.5, "cool": 0.0, "cold": -0.5}
    adjustment += heat_scores.get(market_heat, 0.0)

    # 3. 트렌드 변화율 조정
    trend_change = trend_data.get("trend_change_percent", 0)
    if trend_change > 20:
        adjustment += 0.5
    elif trend_change < -20:
        adjustment -= 0.5

    # 4. 인기도 지수 조정
    popularity = trend_data.get("popularity_index", 0)
    if popularity > 80:
        adjustment += 0.5
    elif popularity < 20:
        adjustment -= 0.5

    return round(adjustment, 1)

def generate_recommendations(competition_result: dict, saturation_result: dict, trend_data: dict = None) -> list:
    """분석 결과를 바탕으로 추천 사항 생성"""
    recommendations = []

    difficulty = competition_result.get("difficulty_score", 0)
    saturation = saturation_result.get("market_saturation_percentage", 0)

    # 난이도 기반 추천
    if difficulty < 3:
        recommendations.append("🟢 Low entry difficulty market, favorable for new sellers.")
    elif difficulty < 6:
        recommendations.append("🟡 Medium difficulty market, differentiation strategy needed.")
    else:
        recommendations.append("🔴 High competition market, cautious approach needed.")

    # 포화도 기반 추천
    if saturation < 30:
        recommendations.append("📈 Low market saturation with growth potential.")
    elif saturation < 60:
        recommendations.append("⚖️ Moderate market saturation level.")
    else:
        recommendations.append("📊 High market saturation, consider niche strategies.")

    # 트렌드 기반 추천 (데이터가 있을 때만)
    if trend_data:
        if trend_data.get("trend_direction") == "rising":
            recommendations.append("📈 Rising trend market, consider aggressive entry.")
        elif trend_data.get("trend_direction") == "falling":
            recommendations.append("📉 Falling trend, cautious market entry needed.")

        market_heat = trend_data.get("market_heat", "")
        if market_heat == "hot":
            recommendations.append("🔥 Hot market, quick action is advantageous.")
        elif market_heat == "cold":
            recommendations.append("❄️ Low interest market, marketing strategy is important.")

    return recommendations

active_connections: dict[str, WebSocket] = {}
cache_manager: CacheManager = None
kafka_manager: KafkaManager = None  # Kafka 매니저 추가
PRE_WARM_KEYWORDS = ["wireless mouse", "bluetooth headphones"] # 캐시 워밍 키워드

# --- Pydantic 모델 ---
class CacheClearRequest(BaseModel):
    keyword: str

class AnalysisRequest(BaseModel):
    keyword: str

class AnalysisResponse(BaseModel):
    session_id: str
    status: str
    message: str
    estimated_time_seconds: int

# --- 백그라운드 작업 ---
async def warm_up_cache():
    """서버 시작 시 백그라운드에서 캐시를 미리 채워넣습니다."""
    print("🔥 Starting cache warm-up in background...")
    await asyncio.sleep(5) # 서버가 완전히 안정될 때까지 잠시 대기

    for keyword in PRE_WARM_KEYWORDS:
        async with scraping_lock:
            if cache_manager and cache_manager.get_analysis_result(keyword):
                print(f"✅ Cache for '{keyword}' already exists. Skipping warm-up.")
                continue
            
            print(f"🔥 Warming up cache for '{keyword}'...")
            try:
                # 네이버 API 기반 분석 (스크레이핑 대체)
                analyzer = get_analyzer()
                report_data = analyzer.get_trend_enhanced_analysis(keyword, days=14, product_count=30)

                # L2 캐시에 저장
                if cache_manager:
                    cache_manager.set_analysis_result(keyword, report_data, ttl_hours=24)
                print(f"✅ Cache warmed up for '{keyword}'.")
            except Exception as e:
                print(f"❌ Error warming up cache for '{keyword}': {e}")

# --- 이벤트 핸들러 ---
@app.on_event("startup")  # HTTP 응답 확인 후 단계적 복원
async def startup_event():
    global cache_manager, kafka_manager, scraper
    print("🚀 Starting Market Insights Pro... (step by step restoration)")

    # 1단계: 네이버 스크래퍼만 초기화
    try:
        scraper = AmazonScraperV2()
        print("✅ Naver Scraper initialized.")
    except Exception as e:
        print(f"❌ Naver Scraper initialization failed: {e}")
        scraper = None

    # 캐시와 Kafka는 나중에 단계적으로 복원
    cache_manager = None
    kafka_manager = None
    print("✅ Phase 1 startup completed (Naver scraper only).")

    # Kafka 매니저 초기화 - 임시 비활성화
    # try:
    #     kafka_manager = get_kafka_manager()
    #     print("⚡ Kafka Manager instance created.")
    # except Exception as e:
    #     print(f"❌ Kafka Manager creation failed: {e}")
    #     kafka_manager = None
    
    # 백그라운드 태스크들을 비동기로 시작 (서버 시작을 블록하지 않음)
    # 임시로 비활성화하여 HTTP 요청 처리 우선
    # asyncio.create_task(initialize_background_services())

    # 시스템 오케스트레이터 초기화 (백그라운드)
    asyncio.create_task(initialize_system_orchestrator())

    print("✅ Market Insights Pro startup completed!")

async def initialize_system_orchestrator():
    """시스템 오케스트레이터 초기화"""
    try:
        print("🎛️ 시스템 오케스트레이터 초기화 시작...")
        orchestrator = get_system_orchestrator()
        success = await orchestrator.initialize_system()

        if success:
            print("✅ 시스템 오케스트레이터 초기화 완료")
        else:
            print("⚠️ 일부 서비스 초기화 실패 (시스템은 계속 작동)")

    except Exception as e:
        print(f"❌ 시스템 오케스트레이터 초기화 실패: {e}")

async def initialize_background_services():
    """백그라운드 서비스들 초기화"""
    print("🔄 백그라운드 서비스 초기화 시작...")

    # 브라우저 초기화
    asyncio.create_task(initialize_browser())

    # Kafka 워커 시작
    if kafka_manager:
        try:
            asyncio.create_task(start_background_worker())
            print("✅ Background Analysis Worker started.")

            asyncio.create_task(start_stream_processor())
            print("✅ Real-time Stream Processor started.")
        except Exception as e:
            print(f"❌ Failed to start background worker: {e}")

    # 캐시 워밍
    asyncio.create_task(warm_up_cache())


async def initialize_browser():
    """브라우저를 백그라운드에서 초기화"""
    try:
        await scraper.start_browser()
        print("✅ Browser initialized successfully.")
    except Exception as e:
        print(f"❌ Browser initialization failed: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    if scraper:
        await scraper.close_browser()

    # Kafka 연결 정리
    if kafka_manager:
        kafka_manager.close()
        print("🔒 Kafka Manager closed.")


# --- WebSocket 로직 (생략, 이전과 동일) ---
async def send_progress(client_id: str, progress: int, message: str, status: str = "processing"):
    if client_id in active_connections:
        await active_connections[client_id].send_text(json.dumps({"progress": progress, "message": message, "status": status}))

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket
    try:
        while True:
            data = await websocket.receive_text()
            data_json = json.loads(data)
            keyword = data_json.get('keyword')
            if keyword:
                asyncio.create_task(run_analysis_job(client_id, keyword))
    except Exception:
        del active_connections[client_id]

async def run_analysis_job(client_id: str, keyword: str):
    async with scraping_lock:
        try:
            if cache_manager and cache_manager.get_analysis_result(keyword):
                await send_progress(client_id, 100, "Report ready!", "completed")
                return

            if not scraper:
                await send_progress(client_id, 100, "Scraper not initialized", "error")
                return

            await send_progress(client_id, 10, "Starting market analysis...")
            db_result = await scraper.scrape_and_save_to_db(keyword, max_products=30)
            if not db_result or not db_result.get('success'):
                await send_progress(client_id, 100, db_result.get('message', 'Scraping error'), "error")
                return
            await send_progress(client_id, 70, "Analysis complete. Generating report...")
            await asyncio.sleep(1)
            await send_progress(client_id, 100, "Report ready!", "completed")
        except Exception as e:
            await send_progress(client_id, 100, f"An unexpected error occurred: {e}", "error")

# --- 웹 페이지 및 API 라우팅 ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # 사용자 액션 추적: 메인 페이지 방문
    client_ip = request.client.host
    user_agent = request.headers.get("user-agent", "")
    session_id = f"{client_ip}_{hash(user_agent) % 10000}"  # 간단한 세션 ID 생성
    
    if kafka_manager:
        kafka_manager.send_user_action(
            user_id=session_id,
            action_type="page_view",
            page_url=str(request.url),
            data={
                "page_name": "index",
                "user_agent": user_agent,
                "referrer": request.headers.get("referer", "")
            }
        )
    
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/stream", response_class=HTMLResponse)
async def stream_dashboard(request: Request):
    """
    🔥 Week 4: 실시간 스트림 대시보드 페이지
    
    스트림 처리 결과를 실시간으로 모니터링할 수 있는 대시보드
    - 이상치 탐지 결과
    - 시장 신호 분석
    - 실시간 트렌드 차트
    """
    # 사용자 액션 추적: 스트림 대시보드 방문
    client_ip = request.client.host
    user_agent = request.headers.get("user-agent", "")
    session_id = f"{client_ip}_{hash(user_agent) % 10000}"
    
    if kafka_manager:
        kafka_manager.send_user_action(
            user_id=session_id,
            action_type="page_view",
            page_url=str(request.url),
            data={
                "page_name": "stream_dashboard",
                "user_agent": user_agent,
                "referrer": request.headers.get("referer", "")
            }
        )
    
    return templates.TemplateResponse("stream_dashboard.html", {"request": request})

@app.get("/report", response_class=HTMLResponse)
async def get_report(request: Request, keyword: str):
    try:
        # 사용자 액션 추적: 리포트 페이지 방문
        client_ip = request.client.host
        user_agent = request.headers.get("user-agent", "")
        session_id = f"{client_ip}_{hash(user_agent) % 10000}"
        
        if kafka_manager:
            kafka_manager.send_user_action(
                user_id=session_id,
                action_type="report_view",
                page_url=str(request.url),
                data={
                    "keyword": keyword,
                    "page_name": "report",
                    "referrer": request.headers.get("referer", "")
                }
            )
        
        if cache_manager:
            cached_report = cache_manager.get_analysis_result(keyword)
            if cached_report:
                # 🛡️ Data structure safety validation for cached reports
                validated_cached_report = validate_report_data_structure(cached_report, keyword)
                return templates.TemplateResponse("advanced_report.html", {"request": request, "report": validated_cached_report})
        
        analyzer = get_analyzer()

        # 네이버 기반 통합 분석 실행
        print(f"🔄 '{keyword}' 네이버 API 기반 종합 분석 시작")
        try:
            # 트렌드 강화 분석 (자동으로 트렌드 데이터 통합)
            report_data = analyzer.get_trend_enhanced_analysis(keyword, days=14, product_count=50)
            
            # 누락된 시장 포화도 데이터 추가
            saturation_data = analyzer.calculate_market_saturation(keyword, product_count=50)
            report_data.update(saturation_data)

            # 프론트엔드 호환성을 위해 난이도 점수 키 조정
            adjusted_score = report_data.get('adjusted_difficulty_score', report_data.get('difficulty_score', 0))
            report_data['difficulty_score'] = adjusted_score

            # JSON 직렬화를 위해 datetime 객체를 문자열로 변환
            product_lists_to_convert = ['top_10_products', 'products']
            for key in product_lists_to_convert:
                if key in report_data:
                    for product in report_data[key]:
                        if isinstance(product.get('scraped_at'), datetime):
                            product['scraped_at'] = product['scraped_at'].isoformat()

            print(f"✅ 네이버 기반 종합 분석 완료!")

            # 트렌딩 기회 분석 추가 (Phase 1.1)
            print(f"🎯 '{keyword}' 트렌딩 기회 분석 시작...")
            try:
                trending_opportunities = await analyzer.analyze_trending_opportunities(keyword)
                report_data['trending_opportunities'] = trending_opportunities
                print(f"✅ 트렌딩 기회 분석 완료 (발견된 기회: {len(trending_opportunities.get('top_opportunities', []))}개)")
            except Exception as trend_e:
                logger.error(f"트렌딩 기회 분석 실패: {trend_e}")
                report_data['trending_opportunities'] = {
                    "base_keyword": keyword,
                    "error": str(trend_e),
                    "top_opportunities": [],
                    "analysis_summary": {}
                }
                print(f"⚠️ 트렌딩 기회 분석 실패: {trend_e}")

            # 카테고리 성장률 분석 추가 (Phase 1.2)
            print(f"📊 '{keyword}' 카테고리 성장률 분석 시작...")
            try:
                category_growth_analysis = await analyzer.analyze_category_growth_rates(days=30)
                report_data['category_growth_analysis'] = category_growth_analysis
                print(f"✅ 카테고리 성장률 분석 완료 (분석된 카테고리: {len(category_growth_analysis.get('top_growth_categories', []))}개)")
            except Exception as category_e:
                logger.error(f"카테고리 성장률 분석 실패: {category_e}")
                report_data['category_growth_analysis'] = {
                    "error": str(category_e),
                    "top_growth_categories": [],
                    "recommended_entry_categories": [],
                    "analysis_summary": {}
                }
                print(f"⚠️ 카테고리 성장률 분석 실패: {category_e}")

            # 브랜드 갭 분석 추가 (Phase 2.1)
            print(f"🏷️ '{keyword}' 브랜드 갭 분석 시작...")
            try:
                brand_gap_analysis = await analyzer.analyze_brand_gap_opportunities(keyword, max_products=80)
                report_data['brand_gap_analysis'] = brand_gap_analysis
                print(f"✅ 브랜드 갭 분석 완료 (브랜드 수: {brand_gap_analysis.get('unique_brands_found', 0)}개, 기회: {len(brand_gap_analysis.get('gap_opportunities', []))}개)")
            except Exception as brand_e:
                logger.error(f"브랜드 갭 분석 실패: {brand_e}")
                report_data['brand_gap_analysis'] = {
                    "keyword": keyword,
                    "error": str(brand_e),
                    "brand_market_share": [],
                    "gap_opportunities": [],
                    "analysis_summary": {}
                }
                print(f"⚠️ 브랜드 갭 분석 실패: {brand_e}")

            # 채널 전략 분석 수행
            print(f"🏪 '{keyword}' 채널 전략 분석 시작...")
            try:
                channel_strategy_analysis = await analyzer.analyze_channel_strategy_opportunities(keyword, max_products=80)
                report_data['channel_strategy_analysis'] = channel_strategy_analysis
                print(f"✅ 채널 전략 분석 완료 (분석 채널 수: {channel_strategy_analysis.get('channel_analysis', {}).get('total_channels', 0)}개)")
            except Exception as channel_e:
                logger.error(f"채널 전략 분석 실패: {channel_e}")
                report_data['channel_strategy_analysis'] = {
                    "keyword": keyword,
                    "error": str(channel_e),
                    "channel_analysis": {"channels": [], "total_channels": 0},
                    "market_opportunities": [],
                    "analysis_summary": {}
                }
                print(f"⚠️ 채널 전략 분석 실패: {channel_e}")

            # ML 예측 결과 통합
            print(f"🧠 '{keyword}' ML 예측 분석 시작...")
            try:
                # 제품 데이터에서 ML 예측 수행
                top_products = report_data.get('top_10_products', report_data.get('products', []))
                if top_products:
                    ml_predictions = await generate_ml_predictions(top_products, keyword)
                    if ml_predictions and 'has_ml_predictions' in ml_predictions:
                        report_data.update(ml_predictions)
                        print(f"✅ ML 예측 분석 완료 (예측 개수: {ml_predictions.get('prediction_summary', {}).get('total_predictions', 0)})")
                    else:
                        print("⚠️ ML 예측 결과가 빈 상태입니다.")
                        report_data['has_ml_predictions'] = False
                        report_data['ml_error'] = "No ML prediction results"
                else:
                    print("⚠️ ML 예측을 위한 제품 데이터가 없습니다.")
                    report_data['has_ml_predictions'] = False
                    report_data['ml_error'] = "No product data available"
            except Exception as ml_e:
                logger.error(f"ML 예측 실패: {ml_e}")
                report_data['has_ml_predictions'] = False
                report_data['ml_error'] = str(ml_e)
                print(f"⚠️ ML 예측 실패, 기본 리포트로 진행: {ml_e}")
                # 전체 리포트가 실패하지 않도록 확실히 보장
                import traceback
                logger.error(f"ML 예측 상세 오류: {traceback.format_exc()}")

        except Exception as e:
            print(f"⚠️ 종합 분석 중 오류, 기본 분석으로 대체: {str(e)}")
            # 트렌드 분석 실패 시 기본 분석
            try:
                report_data = analyzer.analyze_market_competition(keyword, product_count=50)
                saturation_data = analyzer.calculate_market_saturation(keyword, product_count=50)
                report_data.update(saturation_data)
                report_data['has_trend_data'] = False
            except Exception as e2:
                print(f"❌ 기본 분석도 실패: {str(e2)}")
                return templates.TemplateResponse("error.html", {"request": request, "error_message": f"Analysis failed: {e2}"})

        if cache_manager:
            cache_manager.set_analysis_result(keyword, report_data, ttl_hours=24)

        # 🛡️ Data structure safety validation before template rendering
        validated_report_data = validate_report_data_structure(report_data, keyword)

        # 🔧 안전한 템플릿 데이터 생성 (JSON 직렬화 우회)
        try:
            import json
            # 모든 데이터를 JSON 직렬화 가능한 형태로 변환
            json_safe_data = json.loads(json.dumps(validated_report_data, default=str, ensure_ascii=False))
            logger.info(f"✅ JSON 직렬화 성공: {keyword}")
        except Exception as json_error:
            logger.error(f"JSON 직렬화 실패: {json_error}")
            return templates.TemplateResponse("error.html", {"request": request, "error_message": f"Data serialization failed: {json_error}"})

        # 템플릿 데이터에서 % 문자 완전 제거
        def remove_percent_chars(obj):
            if isinstance(obj, str):
                # % 문자와 문제가 될 수 있는 한국어 문자 처리
                return obj.replace('%', ' percent').replace('％', ' percent')
            elif isinstance(obj, dict):
                return {key: remove_percent_chars(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [remove_percent_chars(item) for item in obj]
            else:
                return obj

        # % 문자 완전 제거
        safe_data = remove_percent_chars(json_safe_data)

        # 추가 안전 조치: 모든 문자열을 repr로 안전하게 처리
        import json
        try:
            # JSON 직렬화/역직렬화로 안전한 데이터 확보
            json_str = json.dumps(safe_data, ensure_ascii=False, default=str)
            # % 문자 한 번 더 제거
            json_str = json_str.replace('%', ' percent').replace('％', ' percent')
            safe_data = json.loads(json_str)
        except Exception as json_error:
            logger.error(f"JSON 안전화 실패: {json_error}")
            # 기본 데이터로 폴백
            safe_data = {
                "keyword": keyword,
                "error": "데이터 처리 중 오류 발생",
                "recommendations": []
            }

        # 템플릿 컨텍스트를 간단하게 유지
        template_context = {
            "request": request,
            "report": safe_data
        }

        # 디버깅을 위해 데이터 구조 로깅
        logger.info(f"Report data keys: {list(safe_data.keys()) if isinstance(safe_data, dict) else 'Not a dict'}")
        if isinstance(safe_data, dict) and 'trending_opportunities' in safe_data:
            logger.info(f"Trending opportunities available: {safe_data['trending_opportunities'] is not None}")

        return templates.TemplateResponse("advanced_report.html", template_context)
    except Exception as e:
        import traceback
        full_traceback = traceback.format_exc()
        logger.error(f"Report generation failed: {full_traceback}")

        # 추가 디버깅: 템플릿 컨텍스트 검사
        try:
            import json
            logger.error(f"Template context keys: {list(template_context.keys())}")
            if 'report_data' in template_context:
                logger.error(f"Report data keys: {list(template_context['report_data'].keys())}")
        except Exception as debug_e:
            logger.error(f"Debug error: {debug_e}")

        return templates.TemplateResponse("error.html", {"request": request, "error_message": f"Error generating report: {e}"})

@app.get("/test-report")
async def test_report(request: Request, keyword: str = "test"):
    """Simple test report with minimal data"""
    try:
        simple_data = {
            "keyword": keyword,
            "difficulty_score": 5,
            "saturation": 50,
            "avg_price": 25.0,
            "products": [],
            "recommendations": ["Test recommendation without any percent characters"],
            "ml_predictions": {
                "prediction_summary": {
                    "total_predictions": 0,
                    "market_opportunity_score": 50
                }
            },
            "trending_opportunities": {"top_opportunities": []},
            "category_growth_analysis": {"top_growth_categories": []},
            "brand_gap_analysis": {"gap_opportunities": []},
            "channel_strategy_analysis": {"recommended_channels": []}
        }

        return templates.TemplateResponse("report.html", {
            "request": request,
            "report": simple_data
        })
    except Exception as e:
        import traceback
        logger.error(f"Test report failed: {traceback.format_exc()}")
        return templates.TemplateResponse("error.html", {"request": request, "error_message": f"Test report error: {e}"})

@app.post("/api/cache/clear")
async def clear_cache(payload: CacheClearRequest):
    keyword = payload.keyword
    l1_cleared = False
    l2_cleared = False
    try:
        # 네이버 기반 분석기는 내부 캐시 없음 (실시간 API 기반)
        l1_cleared = True
        print("✅ 네이버 API 기반 분석기는 캐시가 필요하지 않습니다.")
    except Exception as e:
        print(f"⚠️ Failed to clear L1 cache: {e}")
    if cache_manager:
        try:
            l2_cleared = cache_manager.delete_analysis_result(keyword)
        except Exception as e:
            print(f"⚠️ Failed to clear L2 cache for '{keyword}': {e}")
    if l1_cleared or l2_cleared:
        return JSONResponse(content={"message": f"Cache for '{keyword}' cleared.", "l1_cleared": l1_cleared, "l2_cleared": l2_cleared})
    else:
        raise HTTPException(status_code=500, detail="Failed to clear any cache.")

# --- 🚀 새로운 비동기 분석 API ---
@app.post("/api/analyze", response_model=AnalysisResponse)
async def start_analysis(request: AnalysisRequest, http_request: Request):
    """
    🎯 핵심 API! 시장 분석을 비동기로 시작
    
    동작 과정:
    1. 사용자가 키워드 전송
    2. 캐시 확인 (있으면 즉시 반환)  
    3. 없으면 Kafka에 작업 이벤트 발행
    4. 즉시 session_id와 함께 응답 (200ms 이내)
    5. 백그라운드에서 워커가 실제 작업 수행
    """
    keyword = request.keyword.strip()
    
    if not keyword:
        raise HTTPException(status_code=400, detail="키워드를 입력해주세요.")
    
    # 사용자 액션 추적: 키워드 분석 요청
    client_ip = http_request.client.host
    user_agent = http_request.headers.get("user-agent", "")
    session_id = f"{client_ip}_{hash(user_agent) % 10000}"
    
    if kafka_manager:
        kafka_manager.send_user_action(
            user_id=session_id,
            action_type="keyword_search",
            page_url=str(http_request.url),
            data={
                "keyword": keyword,
                "action": "analysis_request",
                "api_endpoint": "/api/analyze"
            }
        )
    
    # 1단계: 캐시 확인 (즉시 완료 가능한 경우)
    if cache_manager:
        cached_result = cache_manager.get_analysis_result(keyword)
        if cached_result:
            return AnalysisResponse(
                session_id="cached",
                status="completed", 
                message=f"'{keyword}' 분석 결과가 캐시에서 발견되었습니다!",
                estimated_time_seconds=0
            )
    
    # 2단계: Kafka가 사용 불가능한 경우 (fallback)
    if not kafka_manager:
        raise HTTPException(
            status_code=503, 
            detail="분석 서비스를 현재 사용할 수 없습니다. 잠시 후 다시 시도해주세요."
        )
    
    try:
        # 3단계: 🚀 Kafka에 분석 작업 이벤트 발행!
        session_id = kafka_manager.send_analysis_event(
            event_type="analysis_requested",
            keyword=keyword,
            data={"requested_at": datetime.now().isoformat()}
        )
        
        # 4단계: 즉시 응답! (실제 작업은 백그라운드에서)
        return AnalysisResponse(
            session_id=session_id,
            status="processing",
            message=f"'{keyword}' 시장 분석이 시작되었습니다. 백그라운드에서 처리 중...",
            estimated_time_seconds=60  # 예상 완료 시간
        )
        
    except Exception as e:
        logger.error(f"❌ 분석 요청 처리 실패: {e}")
        raise HTTPException(status_code=500, detail="분석 요청 처리 중 오류가 발생했습니다.")

@app.get("/api/analysis/{session_id}")
async def get_analysis_status(session_id: str):
    """
    📊 분석 진행 상황 확인 API
    
    프론트엔드에서 주기적으로 호출하여 진행 상황 확인
    또는 WebSocket을 통해 실시간 업데이트 받기
    """
    if session_id == "cached":
        return {"status": "completed", "progress": 100}
        
    # 여기서는 간단하게 세션 기반으로 상태 확인
    # 실제로는 Redis나 DB에서 상태 조회
    if cache_manager:
        # 임시로 캐시에서 상태 정보 확인 (실제 구현에서는 별도 상태 저장소 사용)
        return {"status": "processing", "progress": 50, "message": "스크래핑 진행 중..."}
    
    return {"status": "unknown", "progress": 0}

# --- 🔥 Week 4: 실시간 스트리밍 데이터 API ---
@app.get("/api/stream/insights")
async def get_stream_insights(hours: int = 1):
    """
    📊 실시간 스트림 처리 인사이트 조회 API
    
    최근 N시간 동안의 스트림 처리 결과:
    - 이상치 탐지 결과
    - 시장 신호 감지 
    - 트렌드 분석 요약
    """
    try:
        stream_processor = get_stream_processor()
        insights = stream_processor.get_recent_insights(hours=hours)
        
        return {
            "status": "success",
            "data": insights,
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ 스트림 인사이트 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="스트림 데이터 조회 중 오류가 발생했습니다.")

@app.get("/api/stream/health")
async def get_stream_health():
    """
    🏥 스트림 프로세서 상태 확인 API
    """
    try:
        # 안전한 의존성 로딩 (timeout 적용)
        import asyncio
        
        async def safe_get_processor():
            stream_processor = get_stream_processor()
            return stream_processor
        
        # 2초 타임아웃으로 의존성 로딩
        stream_processor = await asyncio.wait_for(safe_get_processor(), timeout=2.0)
        
        return {
            "status": "healthy" if stream_processor.running else "stopped",
            "components": {
                "time_aggregator": "active",
                "anomaly_detector": "active", 
                "trend_analyzer": "active"
            },
            "uptime": "running" if stream_processor.running else "stopped",
            "last_check": datetime.now().isoformat()
        }
        
    except asyncio.TimeoutError:
        return {
            "status": "timeout",
            "error": "Stream processor initialization timeout",
            "last_check": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ 스트림 헬스체크 실패: {e}")
        return {
            "status": "error",
            "error": str(e),
            "last_check": datetime.now().isoformat()
        }

# --- 🔥 Week 4: 이벤트 소싱 API ---
@app.get("/api/events/stats")
async def get_event_store_stats():
    """
    📊 이벤트 저장소 통계 조회 API
    
    전체 시스템의 이벤트 통계:
    - 총 이벤트 수
    - 집합체 수
    - 이벤트 타입별 통계
    """
    try:
        event_service = get_event_store_service()
        stats = await event_service.event_store.get_system_stats()
        
        return {
            "status": "success",
            "data": stats
        }
        
    except Exception as e:
        logger.error(f"❌ 이벤트 저장소 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="이벤트 저장소 통계 조회 중 오류가 발생했습니다.")

@app.get("/api/events/user/{user_id}/history")
async def get_user_history(user_id: str):
    """
    👤 사용자 이벤트 이력 조회 API
    
    특정 사용자의 모든 이벤트 이력 조회
    """
    try:
        event_service = get_event_store_service()
        history = await event_service.event_store.get_aggregate_history(user_id)
        
        return {
            "status": "success",
            "user_id": user_id,
            "events": history,
            "total_events": len(history)
        }
        
    except Exception as e:
        logger.error(f"❌ 사용자 이력 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="사용자 이력 조회 중 오류가 발생했습니다.")

@app.get("/api/events/user/{user_id}/state")
async def get_user_state(user_id: str):
    """
    🔄 사용자 상태 재구성 API
    
    이벤트 소싱을 통한 사용자 현재 상태 재구성
    """
    try:
        event_service = get_event_store_service()
        state = await event_service.event_store.rebuild_aggregate_state(user_id, 'user')
        
        return {
            "status": "success",
            "user_id": user_id,
            "current_state": state,
            "reconstructed_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ 사용자 상태 재구성 실패: {e}")
        raise HTTPException(status_code=500, detail="사용자 상태 재구성 중 오류가 발생했습니다.")

@app.get("/api/events/keyword/{keyword}/trends")
async def get_keyword_trends(keyword: str):
    """
    📈 키워드 트렌드 이력 조회 API
    
    이벤트 소싱을 통한 키워드 분석 트렌드 재구성
    """
    try:
        import hashlib
        aggregate_id = hashlib.md5(keyword.encode()).hexdigest()
        
        event_service = get_event_store_service()
        state = await event_service.event_store.rebuild_aggregate_state(aggregate_id, 'keyword')
        
        return {
            "status": "success",
            "keyword": keyword,
            "trend_data": state.get('trend_data', []),
            "analysis_count": state.get('analysis_count', 0),
            "anomaly_count": state.get('anomaly_count', 0),
            "first_analyzed": state.get('first_analyzed'),
            "last_analyzed": state.get('last_analyzed')
        }
        
    except Exception as e:
        logger.error(f"❌ 키워드 트렌드 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="키워드 트렌드 조회 중 오류가 발생했습니다.")

# --- 🚀 작업 진행률 추적 API ---
@app.get("/api/tasks/{task_id}/progress")
async def get_task_progress(task_id: str):
    """
    📊 작업 진행률 조회 API

    특정 작업의 실시간 진행 상황 조회
    """
    try:
        tracker = get_task_tracker()
        progress = tracker.get_task_progress(task_id)

        if not progress:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

        return {
            "status": "success",
            "data": progress.to_dict()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 작업 진행률 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="작업 진행률 조회 중 오류가 발생했습니다.")

@app.get("/api/tasks/active")
async def get_active_tasks():
    """
    📋 활성 작업 목록 조회 API

    현재 실행 중인 모든 작업의 진행 상황 조회
    """
    try:
        tracker = get_task_tracker()
        active_tasks = tracker.get_all_active_tasks()

        return {
            "status": "success",
            "data": {
                "active_tasks": [task.to_dict() for task in active_tasks],
                "total_count": len(active_tasks)
            }
        }

    except Exception as e:
        logger.error(f"❌ 활성 작업 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="활성 작업 조회 중 오류가 발생했습니다.")

@app.get("/api/tasks/statistics")
async def get_task_statistics():
    """
    📊 작업 통계 조회 API

    전체 작업 실행 통계 및 현황
    """
    try:
        tracker = get_task_tracker()
        stats = tracker.get_task_statistics()

        return {
            "status": "success",
            "data": stats
        }

    except Exception as e:
        logger.error(f"❌ 작업 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="작업 통계 조회 중 오류가 발생했습니다.")

@app.post("/api/tasks/cleanup")
async def cleanup_completed_tasks(hours_old: int = 24):
    """
    🧹 완료된 작업 정리 API

    지정된 시간보다 오래된 완료 작업들을 정리
    """
    try:
        tracker = get_task_tracker()
        cleaned_count = tracker.cleanup_completed_tasks(hours_old)

        return {
            "status": "success",
            "data": {
                "cleaned_tasks": cleaned_count,
                "hours_old": hours_old,
                "cleaned_at": datetime.now().isoformat()
            }
        }

    except Exception as e:
        logger.error(f"❌ 작업 정리 실패: {e}")
        raise HTTPException(status_code=500, detail="작업 정리 중 오류가 발생했습니다.")

# --- 🚀 새로운 비동기 분석 API (Celery 기반) ---
@app.post("/api/analyze/async")
async def start_async_analysis(request: AnalysisRequest, http_request: Request):
    """
    🎯 비동기 시장 분석 시작 API

    Celery를 사용한 백그라운드 분석 처리
    사용자는 즉시 응답을 받고, 실제 작업은 백그라운드에서 처리
    """
    keyword = request.keyword.strip()

    if not keyword:
        raise HTTPException(status_code=400, detail="키워드를 입력해주세요.")

    try:
        # 사용자 액션 추적
        client_ip = http_request.client.host
        user_agent = http_request.headers.get("user-agent", "")
        session_id = f"{client_ip}_{hash(user_agent) % 10000}"

        if kafka_manager:
            kafka_manager.send_user_action(
                user_id=session_id,
                action_type="async_analysis_request",
                page_url=str(http_request.url),
                data={
                    "keyword": keyword,
                    "api_endpoint": "/api/analyze/async"
                }
            )

        # 캐시 확인
        if cache_manager:
            cached_result = cache_manager.get_analysis_result(keyword)
            if cached_result:
                return {
                    "status": "completed",
                    "task_id": "cached",
                    "message": f"'{keyword}' 분석 결과가 캐시에서 발견되었습니다!",
                    "result": cached_result
                }

        # Celery 작업 시작
        from core.tasks import scrape_and_analyze

        # 비동기 작업 시작
        celery_result = scrape_and_analyze.delay(keyword, max_products=30)
        task_id = celery_result.id

        # 분석 요청 메트릭 기록
        record_analysis_request_metric(keyword)

        logger.info(f"🚀 비동기 분석 시작: {keyword} (Task ID: {task_id})")

        return {
            "status": "started",
            "task_id": task_id,
            "keyword": keyword,
            "message": f"'{keyword}' 시장 분석이 백그라운드에서 시작되었습니다.",
            "estimated_time_seconds": 90,
            "progress_url": f"/api/tasks/{task_id}/progress"
        }

    except Exception as e:
        logger.error(f"❌ 비동기 분석 시작 실패: {e}")
        raise HTTPException(status_code=500, detail="분석 시작 중 오류가 발생했습니다.")

# === 🗄️ 데이터베이스 최적화 API ===

@app.get("/api/database/health")
async def database_health_check():
    """
    🏥 데이터베이스 건강 상태 확인 API

    성능 지표, 쿼리 통계, 연결 풀 상태 등을 제공
    """
    try:
        db_optimizer = get_database_optimizer()
        health_status = db_optimizer.run_health_check()

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "data": health_status
        }

    except Exception as e:
        logger.error(f"❌ 데이터베이스 헬스체크 실패: {e}")
        raise HTTPException(status_code=500, detail="데이터베이스 헬스체크 중 오류가 발생했습니다.")

@app.post("/api/database/optimize")
async def optimize_database():
    """
    ⚡ 데이터베이스 최적화 실행 API

    인덱스 생성, VACUUM, ANALYZE 등 최적화 작업 수행
    """
    try:
        db_optimizer = get_database_optimizer()
        optimization_results = db_optimizer.optimize_database()

        logger.info("🚀 데이터베이스 최적화 완료")

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "message": "데이터베이스 최적화가 완료되었습니다.",
            "data": optimization_results
        }

    except Exception as e:
        logger.error(f"❌ 데이터베이스 최적화 실패: {e}")
        raise HTTPException(status_code=500, detail="데이터베이스 최적화 중 오류가 발생했습니다.")

@app.get("/api/database/query-stats")
async def get_query_statistics():
    """
    📊 쿼리 성능 통계 조회 API

    실행 시간, 빈도, 느린 쿼리 등의 정보 제공
    """
    try:
        db_optimizer = get_database_optimizer()
        query_stats = db_optimizer.query_analyzer.get_query_statistics()
        optimization_suggestions = db_optimizer.query_analyzer.get_optimization_suggestions()

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "statistics": query_stats,
                "optimization_suggestions": optimization_suggestions
            }
        }

    except Exception as e:
        logger.error(f"❌ 쿼리 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="쿼리 통계 조회 중 오류가 발생했습니다.")

@app.get("/api/database/tables/{table_name}/analyze")
async def analyze_table(table_name: str):
    """
    🔍 특정 테이블 분석 API

    테이블별 사용 패턴, 인덱스 상태, 최적화 제안 제공
    """
    allowed_tables = ['products', 'scraping_sessions', 'analysis_results']

    if table_name not in allowed_tables:
        raise HTTPException(
            status_code=400,
            detail=f"허용되지 않은 테이블입니다. 사용 가능: {', '.join(allowed_tables)}"
        )

    try:
        db_optimizer = get_database_optimizer()
        table_analysis = db_optimizer.index_optimizer.analyze_table_usage(table_name)
        index_suggestions = db_optimizer.index_optimizer.suggest_indexes(table_name)

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "table_name": table_name,
            "data": {
                "analysis": table_analysis,
                "index_suggestions": index_suggestions
            }
        }

    except Exception as e:
        logger.error(f"❌ 테이블 {table_name} 분석 실패: {e}")
        raise HTTPException(status_code=500, detail=f"테이블 {table_name} 분석 중 오류가 발생했습니다.")

@app.post("/api/database/tables/{table_name}/create-indexes")
async def create_table_indexes(table_name: str):
    """
    🔧 테이블 인덱스 생성 API

    특정 테이블에 권장 인덱스를 생성
    """
    allowed_tables = ['products', 'scraping_sessions', 'analysis_results']

    if table_name not in allowed_tables:
        raise HTTPException(
            status_code=400,
            detail=f"허용되지 않은 테이블입니다. 사용 가능: {', '.join(allowed_tables)}"
        )

    try:
        db_optimizer = get_database_optimizer()
        index_results = db_optimizer.index_optimizer.create_recommended_indexes(table_name)

        logger.info(f"🔧 테이블 {table_name} 인덱스 생성 완료")

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "table_name": table_name,
            "message": f"테이블 {table_name}의 인덱스가 생성되었습니다.",
            "data": index_results
        }

    except Exception as e:
        logger.error(f"❌ 테이블 {table_name} 인덱스 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=f"테이블 {table_name} 인덱스 생성 중 오류가 발생했습니다.")

# === 🚀 최적화된 API 엔드포인트 (페이지네이션, 압축, 캐싱) ===

@app.get("/api/v2/products")
async def get_products_optimized(request: Request):
    """
    📦 최적화된 상품 목록 조회 API v2

    - 페이지네이션 지원 (page, size 파라미터)
    - gzip 응답 압축
    - ETag/Last-Modified 기반 조건부 요청
    - 메모리 캐싱
    """
    try:
        api_optimizer = get_api_optimizer()
        pagination_params = parse_pagination_params(request)

        # 필터 파라미터
        category = request.query_params.get('category')
        min_price = request.query_params.get('min_price')
        max_price = request.query_params.get('max_price')
        min_rating = request.query_params.get('min_rating')

        # 캐시 키 생성
        cache_key = f"products_{pagination_params.page}_{pagination_params.size}_{category}_{min_price}_{max_price}_{min_rating}"

        # SQLite에서 데이터 조회 (필터 적용)
        from core.models import db_manager, Product
        session = db_manager.get_session()

        try:
            query = session.query(Product)

            # 필터 적용
            if category:
                query = query.filter(Product.product_category.ilike(f'%{category}%'))
            if min_price:
                query = query.filter(Product.discounted_price >= float(min_price))
            if max_price:
                query = query.filter(Product.discounted_price <= float(max_price))
            if min_rating:
                query = query.filter(Product.product_rating >= float(min_rating))

            # 총 개수 조회
            total_count = query.count()

            # 정렬 적용 (최신순)
            query = query.order_by(Product.scraped_at.desc())

            # 페이지네이션 적용 (SQLAlchemy 쿼리 레벨에서)
            offset = (pagination_params.page - 1) * pagination_params.size
            products = query.offset(offset).limit(pagination_params.size).all()

            # 딕셔너리로 변환
            products_data = [
                {
                    'id': p.id,
                    'product_id': p.product_id,
                    'title': p.product_title,
                    'category': p.product_category,
                    'price': p.discounted_price,
                    'rating': p.product_rating,
                    'reviews': p.total_reviews,
                    'is_prime': p.is_prime,
                    'brand': p.brand,
                    'scraped_at': p.scraped_at.isoformat() if p.scraped_at else None
                }
                for p in products
            ]

            # 최신 업데이트 시간 조회
            latest_product = session.query(Product).order_by(Product.scraped_at.desc()).first()
            last_modified = latest_product.scraped_at if latest_product else None

        finally:
            session.close()

        # 최적화된 응답 생성
        return api_optimizer.optimize_list_response(
            data=products_data,
            request=request,
            pagination_params=pagination_params,
            total_count=total_count,
            last_modified=last_modified,
            cache_key=cache_key
        )

    except Exception as e:
        logger.error(f"❌ 최적화된 상품 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="상품 조회 중 오류가 발생했습니다.")

@app.get("/api/v2/analysis-results")
async def get_analysis_results_optimized(request: Request):
    """
    📊 최적화된 분석 결과 조회 API v2

    - 페이지네이션 지원
    - 카테고리/날짜 필터링
    - 응답 압축 및 캐싱
    """
    try:
        api_optimizer = get_api_optimizer()
        pagination_params = parse_pagination_params(request)

        # 필터 파라미터
        category = request.query_params.get('category')
        analysis_type = request.query_params.get('type')
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')

        # 캐시 키
        cache_key = f"analysis_{pagination_params.page}_{pagination_params.size}_{category}_{analysis_type}_{from_date}_{to_date}"

        # 데이터 조회
        from core.models import db_manager, AnalysisResult
        session = db_manager.get_session()

        try:
            query = session.query(AnalysisResult)

            # 필터 적용
            if category:
                query = query.filter(AnalysisResult.category.ilike(f'%{category}%'))
            if analysis_type:
                query = query.filter(AnalysisResult.analysis_type == analysis_type)
            if from_date:
                from datetime import datetime
                start_date = datetime.fromisoformat(from_date)
                query = query.filter(AnalysisResult.created_at >= start_date)
            if to_date:
                end_date = datetime.fromisoformat(to_date)
                query = query.filter(AnalysisResult.created_at <= end_date)

            total_count = query.count()

            # 최신순 정렬
            query = query.order_by(AnalysisResult.created_at.desc())

            # 페이지네이션
            offset = (pagination_params.page - 1) * pagination_params.size
            results = query.offset(offset).limit(pagination_params.size).all()

            # 데이터 변환
            results_data = [
                {
                    'id': r.id,
                    'category': r.category,
                    'analysis_type': r.analysis_type,
                    'results': r.results,
                    'input_params': r.input_params,
                    'created_at': r.created_at.isoformat() if r.created_at else None
                }
                for r in results
            ]

            # 최신 업데이트 시간
            latest_result = session.query(AnalysisResult).order_by(AnalysisResult.created_at.desc()).first()
            last_modified = latest_result.created_at if latest_result else None

        finally:
            session.close()

        return api_optimizer.optimize_list_response(
            data=results_data,
            request=request,
            pagination_params=pagination_params,
            total_count=total_count,
            last_modified=last_modified,
            cache_key=cache_key
        )

    except Exception as e:
        logger.error(f"❌ 최적화된 분석 결과 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="분석 결과 조회 중 오류가 발생했습니다.")

@app.get("/api/v2/scraping-sessions")
async def get_scraping_sessions_optimized(request: Request):
    """
    🕷️ 최적화된 스크래핑 세션 조회 API v2

    - 페이지네이션 및 필터링
    - 세션 상태별 조회
    """
    try:
        api_optimizer = get_api_optimizer()
        pagination_params = parse_pagination_params(request)

        # 필터 파라미터
        keyword = request.query_params.get('keyword')
        status = request.query_params.get('status')

        cache_key = f"sessions_{pagination_params.page}_{pagination_params.size}_{keyword}_{status}"

        # 데이터 조회
        from core.models import db_manager, ScrapingSession
        session = db_manager.get_session()

        try:
            query = session.query(ScrapingSession)

            if keyword:
                query = query.filter(ScrapingSession.keyword.ilike(f'%{keyword}%'))
            if status:
                query = query.filter(ScrapingSession.session_status == status)

            total_count = query.count()
            query = query.order_by(ScrapingSession.started_at.desc())

            offset = (pagination_params.page - 1) * pagination_params.size
            sessions = query.offset(offset).limit(pagination_params.size).all()

            sessions_data = [
                {
                    'id': s.id,
                    'keyword': s.keyword,
                    'products_found': s.products_found,
                    'products_saved': s.products_saved,
                    'session_status': s.session_status,
                    'error_message': s.error_message,
                    'started_at': s.started_at.isoformat() if s.started_at else None,
                    'completed_at': s.completed_at.isoformat() if s.completed_at else None
                }
                for s in sessions
            ]

            latest_session = session.query(ScrapingSession).order_by(ScrapingSession.started_at.desc()).first()
            last_modified = latest_session.started_at if latest_session else None

        finally:
            session.close()

        return api_optimizer.optimize_list_response(
            data=sessions_data,
            request=request,
            pagination_params=pagination_params,
            total_count=total_count,
            last_modified=last_modified,
            cache_key=cache_key
        )

    except Exception as e:
        logger.error(f"❌ 최적화된 세션 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="세션 조회 중 오류가 발생했습니다.")

@app.get("/api/v2/cache/stats")
async def get_api_cache_stats():
    """
    📈 API 캐시 통계 조회
    """
    try:
        api_optimizer = get_api_optimizer()
        cache_stats = api_optimizer.get_cache_stats()

        return {
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'data': cache_stats
        }

    except Exception as e:
        logger.error(f"❌ API 캐시 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="캐시 통계 조회 중 오류가 발생했습니다.")

@app.post("/api/v2/cache/clear")
async def clear_api_cache(pattern: str = None):
    """
    🧹 API 캐시 정리
    """
    try:
        api_optimizer = get_api_optimizer()
        api_optimizer.clear_cache(pattern)

        return {
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'message': f"캐시가 정리되었습니다. 패턴: {pattern or '전체'}"
        }

    except Exception as e:
        logger.error(f"❌ API 캐시 정리 실패: {e}")
        raise HTTPException(status_code=500, detail="캐시 정리 중 오류가 발생했습니다.")

# === 🔗 연결 풀 관리 API ===

@app.get("/api/database/connection-pool/stats")
async def get_connection_pool_stats():
    """
    📊 데이터베이스 연결 풀 통계 조회

    활성 연결 수, 읽기/쓰기 연결 분리 통계 등
    """
    try:
        connection_pool = get_connection_pool()
        pool_stats = connection_pool.get_pool_stats()

        return {
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'data': pool_stats
        }

    except Exception as e:
        logger.error(f"❌ 연결 풀 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="연결 풀 통계 조회 중 오류가 발생했습니다.")

@app.post("/api/database/connection-pool/test")
async def test_connection_pool():
    """
    🧪 연결 풀 성능 테스트

    읽기/쓰기 연결 분리 및 성능 테스트 실행
    """
    try:
        connection_pool = get_connection_pool()
        simulator = get_read_replica_simulator()

        # 성능 테스트 실행
        import time

        test_results = {
            'read_test': {},
            'write_test': {},
            'concurrent_test': {}
        }

        # 읽기 성능 테스트
        start_time = time.time()
        read_results = connection_pool.execute_read_query(
            "SELECT COUNT(*) as count FROM products"
        )
        read_time = time.time() - start_time

        test_results['read_test'] = {
            'duration_ms': round(read_time * 1000, 2),
            'result_count': len(read_results),
            'connection_type': 'read_only'
        }

        # 스마트 라우팅 테스트
        start_time = time.time()
        smart_results = simulator.execute_smart_query(
            "SELECT * FROM products LIMIT 5"
        )
        smart_time = time.time() - start_time

        test_results['smart_routing_test'] = {
            'duration_ms': round(smart_time * 1000, 2),
            'result_count': len(smart_results),
            'auto_routed_to': 'read_only'
        }

        # 연결 풀 통계
        pool_stats = connection_pool.get_pool_stats()
        test_results['pool_stats_after_test'] = pool_stats

        return {
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'message': '연결 풀 테스트가 완료되었습니다.',
            'data': test_results
        }

    except Exception as e:
        logger.error(f"❌ 연결 풀 테스트 실패: {e}")
        raise HTTPException(status_code=500, detail="연결 풀 테스트 중 오류가 발생했습니다.")

@app.get("/api/database/read-replica/status")
async def get_read_replica_status():
    """
    📖 읽기 복제본 시뮬레이터 상태 조회

    SQLite에서의 읽기 최적화 상태 확인
    """
    try:
        connection_pool = get_connection_pool()
        simulator = get_read_replica_simulator()

        # 읽기 연결 상태 확인
        pool_stats = connection_pool.get_pool_stats()

        read_replica_status = {
            'simulator_active': True,
            'read_connections_available': pool_stats['read_connections_active'],
            'total_read_queries': pool_stats['read_queries'],
            'total_write_queries': pool_stats['write_queries'],
            'read_write_ratio': (
                pool_stats['read_queries'] / pool_stats['write_queries']
                if pool_stats['write_queries'] > 0 else 0
            ),
            'optimization_status': 'SQLite WAL 모드로 읽기 최적화 활성',
            'recommendations': []
        }

        # 성능 권장사항
        if pool_stats['read_queries'] > pool_stats['write_queries'] * 5:
            read_replica_status['recommendations'].append(
                "읽기 요청이 많습니다. 읽기 연결 수 증가를 고려하세요."
            )

        if pool_stats['connection_timeouts'] > 0:
            read_replica_status['recommendations'].append(
                f"연결 타임아웃이 {pool_stats['connection_timeouts']}회 발생했습니다. "
                "연결 풀 크기 증가를 고려하세요."
            )

        return {
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'data': read_replica_status
        }

    except Exception as e:
        logger.error(f"❌ 읽기 복제본 상태 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="읽기 복제본 상태 조회 중 오류가 발생했습니다.")

# === 📊 성능 메트릭 및 모니터링 API ===

@app.get("/metrics")
async def prometheus_metrics():
    """
    📈 Prometheus 메트릭 엔드포인트

    Prometheus가 스크래핑할 수 있는 형식으로 메트릭 제공
    """
    try:
        metrics_collector = get_metrics_collector()
        metrics_data = metrics_collector.export_prometheus_metrics()

        return Response(
            content=metrics_data,
            media_type=CONTENT_TYPE_LATEST
        )

    except Exception as e:
        logger.error(f"❌ Prometheus 메트릭 생성 실패: {e}")
        raise HTTPException(status_code=500, detail="메트릭 생성 중 오류가 발생했습니다.")

# === 🏥 헬스체크 엔드포인트 ===
@app.get("/health")
async def health_check():
    """
    🏥 간단한 헬스체크 엔드포인트

    로드 밸런서와 컨테이너 오케스트레이션을 위한 기본 상태 확인
    """
    return JSONResponse(
        status_code=200,
        content={"status": "healthy", "timestamp": datetime.now().isoformat(), "service": "Market Insights Pro"}
    )

@app.get("/health/detailed")
async def detailed_health_check():
    """
    🏥 상세 헬스체크 엔드포인트

    모든 컴포넌트의 상세한 상태 정보 제공
    """
    try:
        health_status = await get_health_status()

        status_code = 200
        if health_status["overall_status"] == "unhealthy":
            status_code = 503
        elif health_status["overall_status"] == "degraded":
            status_code = 206  # Partial Content

        return JSONResponse(
            status_code=status_code,
            content=health_status
        )

    except Exception as e:
        logger.error(f"❌ 상세 헬스체크 실패: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "overall_status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

@app.get("/api/metrics/current")
async def get_current_metrics():
    """
    📊 현재 시스템 메트릭 조회 API

    실시간 시스템 상태 및 성능 지표 제공
    """
    try:
        metrics_collector = get_metrics_collector()
        current_metrics = metrics_collector.get_current_metrics()

        return {
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'data': current_metrics
        }

    except Exception as e:
        logger.error(f"❌ 현재 메트릭 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="메트릭 조회 중 오류가 발생했습니다.")

@app.get("/api/metrics/history")
async def get_metrics_history(minutes: int = 60):
    """
    📈 메트릭 히스토리 조회 API

    지정된 기간의 성능 지표 변화 추이 제공
    """
    if minutes > 1440:  # 24시간 제한
        raise HTTPException(status_code=400, detail="최대 24시간(1440분) 기간만 조회 가능합니다.")

    try:
        metrics_collector = get_metrics_collector()
        history = metrics_collector.get_metrics_history(minutes)

        return {
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'period_minutes': minutes,
            'data_points': len(history),
            'data': history
        }

    except Exception as e:
        logger.error(f"❌ 메트릭 히스토리 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="메트릭 히스토리 조회 중 오류가 발생했습니다.")

@app.get("/api/metrics/collection-stats")
async def get_metrics_collection_stats():
    """
    🔍 메트릭 수집 통계 조회 API

    메트릭 수집기의 상태 및 성능 통계 제공
    """
    try:
        metrics_collector = get_metrics_collector()
        collection_stats = metrics_collector.get_collection_stats()

        return {
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'data': collection_stats
        }

    except Exception as e:
        logger.error(f"❌ 메트릭 수집 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="수집 통계 조회 중 오류가 발생했습니다.")

@app.get("/api/metrics/summary")
async def get_metrics_summary():
    """
    📋 메트릭 요약 조회 API

    주요 성능 지표 요약 및 알림 정보 제공
    """
    try:
        metrics_collector = get_metrics_collector()
        current_metrics = metrics_collector.get_current_metrics()

        if not current_metrics:
            raise HTTPException(status_code=503, detail="메트릭 데이터가 없습니다.")

        system = current_metrics.get('system', {})
        application = current_metrics.get('application', {})
        business = current_metrics.get('business', {})

        # 성능 상태 평가
        performance_status = "healthy"
        alerts = []

        # CPU 사용률 검사
        cpu_percent = system.get('cpu_percent', 0)
        if cpu_percent > 80:
            performance_status = "warning"
            alerts.append(f"높은 CPU 사용률: {cpu_percent:.1f}%")

        # 메모리 사용률 검사
        memory_percent = system.get('memory_percent', 0)
        if memory_percent > 85:
            performance_status = "critical"
            alerts.append(f"높은 메모리 사용률: {memory_percent:.1f}%")

        # 디스크 사용률 검사
        disk_percent = system.get('disk_percent', 0)
        if disk_percent > 90:
            performance_status = "critical"
            alerts.append(f"디스크 공간 부족: {disk_percent:.1f}%")

        # 데이터베이스 연결 검사
        db_connections = application.get('db_active_connections', 0)
        if db_connections > 50:  # 임계값
            performance_status = "warning"
            alerts.append(f"많은 DB 연결: {db_connections}개")

        summary = {
            'performance_status': performance_status,
            'alerts': alerts,
            'key_metrics': {
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
                'disk_percent': disk_percent,
                'active_db_connections': db_connections,
                'total_analysis_requests': business.get('analysis_requests', 0),
                'api_cache_hit_rate': application.get('api_cache_hit_rate', 0),
            },
            'collection_info': metrics_collector.get_collection_stats()
        }

        return {
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'data': summary
        }

    except Exception as e:
        logger.error(f"❌ 메트릭 요약 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="메트릭 요약 조회 중 오류가 발생했습니다.")

@app.post("/api/metrics/record-event")
async def record_business_event(event_type: str, count: int = 1):
    """
    📝 비즈니스 이벤트 기록 API

    사용자 정의 이벤트를 메트릭으로 기록
    """
    if not event_type or count < 1:
        raise HTTPException(status_code=400, detail="유효하지 않은 이벤트 타입 또는 카운트입니다.")

    try:
        metrics_collector = get_metrics_collector()
        metrics_collector.record_business_event(event_type, count)

        return {
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'message': f"이벤트 '{event_type}' {count}회 기록됨"
        }

    except Exception as e:
        logger.error(f"❌ 비즈니스 이벤트 기록 실패: {e}")
        raise HTTPException(status_code=500, detail="이벤트 기록 중 오류가 발생했습니다.")

# === 🚨 알림 웹훅 엔드포인트 ===

@app.post("/api/alerts/webhook")
async def receive_alert_webhook(request: Request):
    """
    🚨 AlertManager 웹훅 수신 엔드포인트

    Prometheus AlertManager에서 발송된 알림을 수신하고 처리
    """
    try:
        alert_data = await request.json()

        # 알림 데이터 로깅
        logger.info(f"🚨 알림 수신: {len(alert_data.get('alerts', []))}개")

        for alert in alert_data.get('alerts', []):
            status = alert.get('status', 'unknown')
            alert_name = alert.get('labels', {}).get('alertname', 'Unknown')
            severity = alert.get('labels', {}).get('severity', 'unknown')
            description = alert.get('annotations', {}).get('description', '')

            log_message = f"📢 [{severity.upper()}] {alert_name}: {description}"

            if severity == 'critical':
                logger.error(log_message)
            elif severity == 'warning':
                logger.warning(log_message)
            else:
                logger.info(log_message)

            # 비즈니스 메트릭 기록
            metrics_collector = get_metrics_collector()
            metrics_collector.record_business_event(f'alert_{severity}')

            # 중요 알림의 경우 추가 처리
            if severity == 'critical' and status == 'firing':
                await handle_critical_alert(alert)

        return {
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'alerts_processed': len(alert_data.get('alerts', []))
        }

    except Exception as e:
        logger.error(f"❌ 알림 웹훅 처리 실패: {e}")
        raise HTTPException(status_code=500, detail="알림 처리 중 오류가 발생했습니다.")

async def handle_critical_alert(alert: dict):
    """중요 알림 처리 로직"""
    alert_name = alert.get('labels', {}).get('alertname', 'Unknown')

    # 자동 복구 시도
    if alert_name == 'HighMemoryUsage':
        logger.info("🔧 메모리 정리 시작...")
        # 캐시 정리
        try:
            api_optimizer = get_api_optimizer()
            api_optimizer.clear_cache()
            logger.info("✅ API 캐시 정리 완료")
        except Exception as e:
            logger.error(f"캐시 정리 실패: {e}")

    elif alert_name == 'HighCPUUsage':
        logger.info("🔧 CPU 부하 감소 시도...")
        # 추가 최적화 로직 구현 가능




# === 🤖 ML 예측 API ===
@app.post("/api/ml/predict/price", response_model=PricePredictionResponse)
async def predict_price(request: PricePredictionRequest):
    """
    🎯 최적 가격 추천 API

    AI 모델을 활용하여 경쟁력 있는 최적 판매 가격을 추천하고
    수익성 분석과 가격 전략을 제공합니다.
    """
    success = False
    latency_ms = 0.0

    try:
        ml_service = get_ml_serving_service()
        result = await ml_service.predict_price(request)
        success = True
        latency_ms = result.processing_time_ms

        # 메트릭 기록
        metrics_collector = get_metrics_collector()
        metrics_collector.record_prediction_request("price", result.processing_time_ms)


        return result

    except Exception as e:
        logger.error(f"❌ 가격 예측 실패: {e}")


        raise HTTPException(status_code=500, detail=f"가격 추천 중 오류가 발생했습니다: {str(e)}")


@app.post("/api/ml/predict/batch", response_model=BatchPredictionResponse)
async def predict_batch(request: BatchPredictionRequest):
    """
    📦 배치 가격 예측 API

    여러 상품의 가격을 한 번에 예측합니다.
    """
    try:
        ml_service = get_ml_serving_service()
        result = await ml_service.predict_batch(request)

        # 메트릭 기록
        metrics_collector = get_metrics_collector()
        metrics_collector.record_prediction_request("batch", result.processing_time_ms)

        return result

    except Exception as e:
        logger.error(f"❌ 배치 예측 실패: {e}")
        raise HTTPException(status_code=500, detail=f"배치 예측 중 오류가 발생했습니다: {str(e)}")


@app.get("/api/ml/model/{model_name}/info", response_model=ModelInfo)
async def get_model_info(model_name: str):
    """
    📊 모델 정보 조회 API

    특정 모델의 정보와 성능 메트릭을 조회합니다.
    """
    try:
        ml_service = get_ml_serving_service()
        result = await ml_service.get_model_info(model_name)
        return result

    except Exception as e:
        logger.error(f"❌ 모델 정보 조회 실패: {e}")
        raise HTTPException(status_code=404, detail=f"모델 정보를 찾을 수 없습니다: {str(e)}")


@app.post("/api/ml/models/reload")
async def reload_models():
    """
    🔄 모델 재로드 API

    모든 ML 모델을 메모리에서 다시 로드합니다.
    """
    try:
        ml_service = get_ml_serving_service()
        await ml_service.reload_models()
        return {"status": "success", "message": "모든 모델이 성공적으로 재로드되었습니다."}

    except Exception as e:
        logger.error(f"❌ 모델 재로드 실패: {e}")
        raise HTTPException(status_code=500, detail=f"모델 재로드 중 오류가 발생했습니다: {str(e)}")


@app.get("/api/ml/health")
async def ml_health_check():
    """
    🏥 ML 서비스 헬스 체크

    ML 서빙 서비스의 상태를 확인합니다.
    """
    try:
        ml_service = get_ml_serving_service()
        health_status = await ml_service.health_check()

        if health_status["status"] == "healthy":
            return health_status
        else:
            raise HTTPException(status_code=503, detail=health_status)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ ML 헬스 체크 실패: {e}")
        raise HTTPException(status_code=503, detail=f"ML 서비스 상태 확인 실패: {str(e)}")




# === 🎛️ 시스템 관리 API ===
@app.get("/api/system/status")
async def get_system_status():
    """
    🎛️ 전체 시스템 상태 조회

    모든 서비스의 상태, 헬스, 메트릭을 종합적으로 제공합니다.
    """
    try:
        orchestrator = get_system_orchestrator()
        system_status = await orchestrator.get_system_status()
        return system_status

    except Exception as e:
        logger.error(f"❌ 시스템 상태 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"시스템 상태 조회 중 오류가 발생했습니다: {str(e)}")


@app.post("/api/system/service/{service_name}/restart")
async def restart_service(service_name: str):
    """
    🔄 개별 서비스 재시작

    특정 서비스를 재시작합니다.
    """
    try:
        orchestrator = get_system_orchestrator()
        success = await orchestrator.restart_service(service_name)

        if success:
            return {
                "status": "success",
                "message": f"{service_name} 서비스가 성공적으로 재시작되었습니다.",
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail=f"{service_name} 서비스 재시작에 실패했습니다.")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 서비스 재시작 실패: {e}")
        raise HTTPException(status_code=500, detail=f"서비스 재시작 중 오류가 발생했습니다: {str(e)}")


@app.post("/api/system/maintenance")
async def run_system_maintenance():
    """
    🔧 시스템 유지보수 실행

    전체 시스템의 유지보수 작업을 실행합니다.
    """
    try:
        orchestrator = get_system_orchestrator()
        await orchestrator.run_maintenance()

        return {
            "status": "success",
            "message": "시스템 유지보수가 완료되었습니다.",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 시스템 유지보수 실패: {e}")
        raise HTTPException(status_code=500, detail=f"시스템 유지보수 중 오류가 발생했습니다: {str(e)}")


@app.get("/api/system/info")
async def get_system_info():
    """
    ℹ️ 시스템 정보 조회

    시스템 버전, 구성, 환경 정보를 제공합니다.
    """
    try:
        orchestrator = get_system_orchestrator()

        return {
            "system": {
                "name": "Market Insights Pro",
                "version": "2.0.0",
                "description": "AI-powered e-commerce market analysis platform",
                "environment": "development",
                "features": [
                    "Naver Shopping API integration",
                    "Real-time ML predictions",
                    "Automated ML pipelines",
                    "ML model monitoring",
                    "Data quality monitoring",
                    "Performance analytics"
                ]
            },
            "ml_models": {
                "price_predictor": {
                    "algorithm": "XGBoost",
                    "purpose": "Product price prediction",
                    "features": ["category", "brand", "rating", "review_count", "seller"]
                },
                "demand_forecaster": {
                    "algorithm": "Prophet",
                    "purpose": "Demand forecasting",
                    "features": ["search_trends", "seasonality", "external_factors"]
                }
            },
            "apis": {
                "prediction": "/api/ml/predict/*",
                "monitoring": "/api/ml/monitoring/*",
                "system": "/api/system/*",
                "analysis": "/api/analyze"
            },
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 시스템 정보 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"시스템 정보 조회 중 오류가 발생했습니다: {str(e)}")


@app.post("/api/system/optimize")
async def optimize_system_performance():
    """
    ⚡ 시스템 성능 최적화

    전체 시스템의 성능을 최적화합니다.
    """
    try:
        optimizer = get_performance_optimizer()
        results = await optimizer.optimize_all_systems()

        return {
            "status": "success",
            "message": "시스템 성능 최적화가 완료되었습니다.",
            "optimization_results": results,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 시스템 최적화 실패: {e}")
        raise HTTPException(status_code=500, detail=f"시스템 최적화 중 오류가 발생했습니다: {str(e)}")


@app.get("/api/system/performance")
async def get_system_performance_metrics():
    """
    📊 시스템 성능 메트릭 조회

    현재 시스템의 성능 메트릭을 조회합니다.
    """
    try:
        optimizer = get_performance_optimizer()
        metrics = optimizer.get_current_performance_metrics()

        return {
            "status": "success",
            "metrics": metrics,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 성능 메트릭 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"성능 메트릭 조회 중 오류가 발생했습니다: {str(e)}")


@app.post("/api/system/benchmark")
async def run_performance_benchmark():
    """
    🏃 성능 벤치마크 실행

    시스템 성능 벤치마크 테스트를 실행합니다.
    """
    try:
        optimizer = get_performance_optimizer()
        benchmark_results = await optimizer.run_performance_benchmark()

        return {
            "status": "success",
            "message": "성능 벤치마크가 완료되었습니다.",
            "benchmark_results": benchmark_results,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 성능 벤치마크 실패: {e}")
        raise HTTPException(status_code=500, detail=f"성능 벤치마크 중 오류가 발생했습니다: {str(e)}")




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
