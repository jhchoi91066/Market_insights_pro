# -*- coding: utf-8 -*-
"""
이 파일은 Market Insights Pro 프로젝트의 FastAPI 서버 메인 애플리케이션입니다.
웹 UI 렌더링과 API 엔드포인트를 모두 포함합니다.
"""
from typing import List, Tuple
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

# 캐시, 분석, Kafka 모듈
from core.cache import get_cache_manager, CacheManager
from core.analyzer_v2 import SQLiteMarketAnalyzer
from core.amazon_scraper_v2 import AmazonScraperV2
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
from core.scraping_monitor import get_scraping_monitor, ScrapingStatus, AlertLevel
from prometheus_client import CONTENT_TYPE_LATEST
import time

# 로거 설정
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Amazon Market Insights Pro",
    description="Amazon product market analysis and competition research tool",
    version="1.2.0", # 버전 업데이트
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
sqlite_analyzer = SQLiteMarketAnalyzer()
scraper = AmazonScraperV2()
scraping_lock = asyncio.Lock()
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
                # 스크레이핑 및 분석
                await scraper.scrape_and_save_to_db(keyword, max_products=30)
                competition_report = sqlite_analyzer.analyze_category_competition(keyword)
                saturation_report = sqlite_analyzer.calculate_market_saturation(keyword)
                report_data = {**competition_report, **saturation_report}
                report_data['keyword'] = keyword

                # L2 캐시에 저장
                if cache_manager:
                    cache_manager.set_analysis_result(keyword, report_data, ttl_hours=24)
                print(f"✅ Cache warmed up for '{keyword}'.")
            except Exception as e:
                print(f"❌ Error warming up cache for '{keyword}': {e}")

# --- 이벤트 핸들러 ---
# @app.on_event("startup")  # 임시 비활성화
async def startup_event_disabled():
    global cache_manager, kafka_manager
    print("🚀 Starting Market Insights Pro...")
    
    # Redis 캐시 매니저 초기화
    try:
        cache_manager = get_cache_manager()
        print("✅ Redis Cache Manager connected.")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        cache_manager = None
    
    # Kafka 매니저 초기화 (빠른 실패)
    try:
        kafka_manager = get_kafka_manager()
        print("⚡ Kafka Manager instance created.")
    except Exception as e:
        print(f"❌ Kafka Manager creation failed: {e}")
        kafka_manager = None
    
    # 백그라운드 태스크들을 비동기로 시작 (서버 시작을 블록하지 않음)
    asyncio.create_task(initialize_background_services())

    print("✅ Market Insights Pro startup completed!")

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

    # 스크래핑 모니터링 시스템 시작
    try:
        monitor = get_scraping_monitor()
        await monitor.start_monitoring()
        print("✅ Scraping Monitoring System started.")
    except Exception as e:
        print(f"❌ Failed to start monitoring system: {e}")

async def initialize_browser():
    """브라우저를 백그라운드에서 초기화"""
    try:
        await scraper.start_browser()
        print("✅ Browser initialized successfully.")
    except Exception as e:
        print(f"❌ Browser initialization failed: {e}")

# @app.on_event("shutdown")  # 임시 비활성화
async def shutdown_event_disabled():
    await scraper.close_browser()

    # Kafka 연결 정리
    if kafka_manager:
        kafka_manager.close()
        print("🔒 Kafka Manager closed.")

    # 🔍 스크래핑 모니터링 시스템 종료
    try:
        monitor = get_scraping_monitor()
        await monitor.stop_monitoring()
        print("🔒 Scraping Monitoring System stopped.")
    except Exception as e:
        print(f"❌ Failed to stop monitoring system: {e}")

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
                return templates.TemplateResponse("report.html", {"request": request, "report": cached_report})
        
        competition_report = sqlite_analyzer.analyze_category_competition(keyword)
        saturation_report = sqlite_analyzer.calculate_market_saturation(keyword)
        report_data = {**competition_report, **saturation_report}
        report_data['keyword'] = keyword

        if cache_manager:
            cache_manager.set_analysis_result(keyword, report_data, ttl_hours=24)

        return templates.TemplateResponse("report.html", {"request": request, "report": report_data})
    except Exception as e:
        return templates.TemplateResponse("error.html", {"request": request, "error_message": f"Error generating report: {e}"})

@app.post("/api/cache/clear")
async def clear_cache(payload: CacheClearRequest):
    keyword = payload.keyword
    l1_cleared = False
    l2_cleared = False
    try:
        sqlite_analyzer.analyze_category_competition.cache_clear()
        sqlite_analyzer.calculate_market_saturation.cache_clear()
        l1_cleared = True
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

# === 📊 스크래핑 모니터링 대시보드 엔드포인트 ===
@app.get("/monitoring/dashboard")
async def get_monitoring_dashboard():
    """
    📊 스크래핑 모니터링 대시보드 데이터

    실시간 스크래핑 상태, 성능 메트릭, 품질 지표 등을 제공
    """
    try:
        monitor = get_scraping_monitor()
        dashboard_data = monitor.get_dashboard_data()

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "data": dashboard_data
            }
        )

    except Exception as e:
        logger.error(f"❌ 모니터링 대시보드 데이터 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="모니터링 데이터 조회 중 오류가 발생했습니다.")

@app.get("/monitoring/sessions")
async def get_active_sessions():
    """
    📋 활성 스크래핑 세션 목록

    현재 진행 중인 모든 스크래핑 세션의 상태를 반환
    """
    try:
        monitor = get_scraping_monitor()

        return {
            "active_sessions": list(monitor.active_sessions.values()),
            "total_active": len(monitor.active_sessions),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 활성 세션 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="활성 세션 조회 중 오류가 발생했습니다.")

@app.get("/monitoring/sessions/{session_id}")
async def get_session_details(session_id: str):
    """
    🔍 특정 세션 상세 정보

    세션 ID로 특정 스크래핑 세션의 상세 정보를 조회
    """
    try:
        monitor = get_scraping_monitor()
        session_details = monitor.get_session_details(session_id)

        if not session_details:
            raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

        return {
            "session": session_details,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 세션 상세 정보 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="세션 정보 조회 중 오류가 발생했습니다.")

@app.get("/monitoring/alerts")
async def get_monitoring_alerts():
    """
    🚨 모니터링 알림 목록

    최근 발생한 모니터링 알림들을 반환
    """
    try:
        monitor = get_scraping_monitor()

        return {
            "alerts": [
                {
                    "id": alert.id,
                    "level": alert.level.value,
                    "title": alert.title,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat(),
                    "session_id": alert.session_id,
                    "acknowledged": alert.acknowledged
                }
                for alert in monitor.alerts[-50:]  # 최근 50개
            ],
            "total_alerts": len(monitor.alerts),
            "unacknowledged_count": len([a for a in monitor.alerts if not a.acknowledged]),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 모니터링 알림 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="알림 조회 중 오류가 발생했습니다.")

@app.post("/monitoring/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """
    ✅ 알림 확인 처리

    특정 알림을 확인 처리하여 대시보드에서 제거
    """
    try:
        monitor = get_scraping_monitor()
        monitor.acknowledge_alert(alert_id)

        return {
            "status": "success",
            "message": f"알림 {alert_id}를 확인 처리했습니다.",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 알림 확인 처리 실패: {e}")
        raise HTTPException(status_code=500, detail="알림 확인 처리 중 오류가 발생했습니다.")

@app.get("/monitoring/stats")
async def get_monitoring_stats():
    """
    📈 실시간 모니터링 통계

    시스템 전반의 실시간 통계 정보를 제공
    """
    try:
        monitor = get_scraping_monitor()

        return {
            "real_time_stats": monitor.real_time_stats,
            "system_health": monitor._get_system_health(),
            "performance_summary": {
                "total_requests": len(monitor.performance_history),
                "avg_success_rate": sum(m.success_rate for m in monitor.performance_history[-10:]) / max(1, len(monitor.performance_history[-10:])),
                "recent_errors": len([a for a in monitor.alerts[-20:] if a.level in [AlertLevel.ERROR, AlertLevel.CRITICAL]])
            },
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 모니터링 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="통계 조회 중 오류가 발생했습니다.")

@app.websocket("/monitoring/ws")
async def monitoring_websocket(websocket: WebSocket):
    """
    🔄 실시간 모니터링 WebSocket

    실시간으로 모니터링 데이터를 스트리밍
    """
    await websocket.accept()
    monitor = get_scraping_monitor()
    monitor.add_websocket_client(websocket)

    try:
        # 초기 데이터 전송
        initial_data = {
            "type": "initial_data",
            "data": monitor.get_dashboard_data()
        }
        await websocket.send_text(json.dumps(initial_data, default=str))

        # 연결 유지 (실제 업데이트는 백그라운드 태스크에서 처리)
        while True:
            # 클라이언트로부터 ping 메시지 수신 대기
            try:
                message = await websocket.receive_text()
                if message == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except:
                break

    except Exception as e:
        logger.error(f"WebSocket 연결 오류: {e}")
    finally:
        monitor.remove_websocket_client(websocket)

# === 🎯 스크래핑 제어 엔드포인트 ===
@app.post("/monitoring/scraping/start")
async def start_scraping_session(
    keyword: str = Form(...),
    max_products: int = Form(20)
):
    """
    🚀 스크래핑 세션 시작

    새로운 Amazon 스크래핑 세션을 시작
    """
    try:
        monitor = get_scraping_monitor()

        # 세션 ID 생성
        session_id = f"session_{int(time.time())}"

        # 세션 시작
        session = monitor.start_session(session_id, keyword)

        # 백그라운드에서 실제 스크래핑 시작 (비동기)
        asyncio.create_task(_perform_scraping(session_id, keyword, max_products))

        return {
            "status": "success",
            "session_id": session_id,
            "keyword": keyword,
            "max_products": max_products,
            "message": f"키워드 '{keyword}'로 스크래핑 세션이 시작되었습니다.",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 스크래핑 세션 시작 실패: {e}")
        raise HTTPException(status_code=500, detail="스크래핑 세션 시작 중 오류가 발생했습니다.")

@app.post("/monitoring/scraping/stop/{session_id}")
async def stop_scraping_session(session_id: str):
    """
    🛑 스크래핑 세션 중지

    진행 중인 스크래핑 세션을 중지
    """
    try:
        monitor = get_scraping_monitor()

        if session_id not in monitor.active_sessions:
            raise HTTPException(status_code=404, detail="활성 세션을 찾을 수 없습니다.")

        # 세션 상태를 PAUSED로 변경
        session = monitor.active_sessions[session_id]
        session.status = ScrapingStatus.PAUSED

        return {
            "status": "success",
            "session_id": session_id,
            "message": f"세션 {session_id}가 일시 중지되었습니다.",
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 스크래핑 세션 중지 실패: {e}")
        raise HTTPException(status_code=500, detail="세션 중지 중 오류가 발생했습니다.")

async def _perform_scraping(session_id: str, keyword: str, max_products: int):
    """
    실제 스크래핑 수행 (백그라운드 태스크)
    """
    monitor = get_scraping_monitor()

    try:
        # 스크래핑 로직 시뮬레이션 (실제로는 Amazon 스크래퍼 v2 사용)
        for i in range(max_products):
            # 세션 상태 확인 (중지되었는지)
            if session_id in monitor.active_sessions:
                session = monitor.active_sessions[session_id]
                if session.status == ScrapingStatus.PAUSED:
                    break

                # 진행상황 업데이트
                monitor.update_session_progress(
                    session_id,
                    products_found=i + 1,
                    products_processed=i + 1,
                    products_valid=i,
                    current_page=(i // 10) + 1
                )

                # 스크래핑 딜레이 시뮬레이션
                await asyncio.sleep(2)
            else:
                break

        # 세션 완료
        monitor.complete_session(session_id, ScrapingStatus.COMPLETED)

    except Exception as e:
        logger.error(f"스크래핑 세션 {session_id} 실행 중 오류: {e}")
        monitor.complete_session(session_id, ScrapingStatus.ERROR)

# === 🎨 모니터링 대시보드 UI ===
@app.get("/monitoring", response_class=HTMLResponse)
async def monitoring_dashboard_ui(request: Request):
    """
    📊 모니터링 대시보드 웹 UI

    실시간 스크래핑 모니터링을 위한 웹 인터페이스
    """
    dashboard_html = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Market Insights Pro - 스크래핑 모니터링</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f6fa; }
            .header { background: #2c3e50; color: white; padding: 1rem; }
            .container { max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
            .stat-card { background: white; padding: 1.5rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .stat-value { font-size: 2rem; font-weight: bold; color: #3498db; }
            .stat-label { color: #7f8c8d; margin-top: 0.5rem; }
            .chart-container { background: white; padding: 1.5rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 2rem; }
            .alerts-container { background: white; padding: 1.5rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .alert-item { padding: 1rem; border-left: 4px solid #e74c3c; background: #fdf2f2; margin-bottom: 1rem; border-radius: 4px; }
            .alert-info { border-left-color: #3498db; background: #f0f8ff; }
            .alert-warning { border-left-color: #f39c12; background: #fef9e7; }
            .status-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
            .status-running { background: #27ae60; }
            .status-error { background: #e74c3c; }
            .status-completed { background: #95a5a6; }
            .refresh-btn { background: #3498db; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📊 Market Insights Pro - 스크래핑 모니터링</h1>
            <button class="refresh-btn" onclick="loadDashboardData()">새로고침</button>
        </div>

        <div class="container">
            <div class="stats-grid" id="statsGrid">
                <!-- 통계 카드들이 여기에 동적으로 추가됩니다 -->
            </div>

            <div class="chart-container">
                <h3>📈 성능 메트릭</h3>
                <canvas id="performanceChart" width="400" height="100"></canvas>
            </div>

            <div class="alerts-container">
                <h3>🚨 최근 알림</h3>
                <div id="alertsList">
                    <!-- 알림들이 여기에 동적으로 추가됩니다 -->
                </div>
            </div>
        </div>

        <script>
            let performanceChart = null;
            let ws = null;

            // 페이지 로드 시 초기화
            document.addEventListener('DOMContentLoaded', function() {
                loadDashboardData();
                connectWebSocket();

                // 30초마다 자동 새로고침
                setInterval(loadDashboardData, 30000);
            });

            // 대시보드 데이터 로드
            async function loadDashboardData() {
                try {
                    const response = await fetch('/monitoring/dashboard');
                    const result = await response.json();

                    if (result.status === 'success') {
                        updateStats(result.data.overview);
                        updatePerformanceChart(result.data.performance_metrics);
                        updateAlerts(result.data.alerts);
                    }
                } catch (error) {
                    console.error('대시보드 데이터 로드 실패:', error);
                }
            }

            // 통계 업데이트
            function updateStats(stats) {
                const statsGrid = document.getElementById('statsGrid');
                statsGrid.innerHTML = `
                    <div class="stat-card">
                        <div class="stat-value">${stats.active_sessions || 0}</div>
                        <div class="stat-label">활성 세션</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.total_products || 0}</div>
                        <div class="stat-label">총 수집 상품</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.products_today || 0}</div>
                        <div class="stat-label">오늘 수집</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${(stats.average_quality_score || 0).toFixed(1)}%</div>
                        <div class="stat-label">평균 품질 점수</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${(stats.uptime_hours || 0).toFixed(1)}h</div>
                        <div class="stat-label">시스템 가동시간</div>
                    </div>
                `;
            }

            // 성능 차트 업데이트
            function updatePerformanceChart(metrics) {
                const ctx = document.getElementById('performanceChart').getContext('2d');

                if (performanceChart) {
                    performanceChart.destroy();
                }

                const labels = metrics.map(m => new Date(m.timestamp).toLocaleTimeString());
                const successRates = metrics.map(m => m.success_rate || 0);

                performanceChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: '성공률 (%)',
                            data: successRates,
                            borderColor: '#3498db',
                            backgroundColor: 'rgba(52, 152, 219, 0.1)',
                            tension: 0.4
                        }]
                    },
                    options: {
                        responsive: true,
                        scales: {
                            y: {
                                beginAtZero: true,
                                max: 100
                            }
                        }
                    }
                });
            }

            // 알림 목록 업데이트
            function updateAlerts(alerts) {
                const alertsList = document.getElementById('alertsList');

                if (!alerts || alerts.length === 0) {
                    alertsList.innerHTML = '<p>최근 알림이 없습니다.</p>';
                    return;
                }

                alertsList.innerHTML = alerts.slice(-10).map(alert => `
                    <div class="alert-item alert-${alert.level}">
                        <strong>${alert.title}</strong>
                        <p>${alert.message}</p>
                        <small>${new Date(alert.timestamp).toLocaleString()}</small>
                    </div>
                `).join('');
            }

            // WebSocket 연결
            function connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/monitoring/ws`;

                ws = new WebSocket(wsUrl);

                ws.onmessage = function(event) {
                    const data = JSON.parse(event.data);

                    if (data.type === 'status_update') {
                        updateStats(data.stats);
                        updateAlerts(data.recent_alerts);
                    }
                };

                ws.onclose = function() {
                    // 5초 후 재연결 시도
                    setTimeout(connectWebSocket, 5000);
                };

                // 30초마다 ping 전송
                setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send('ping');
                    }
                }, 30000);
            }
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=dashboard_html)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
