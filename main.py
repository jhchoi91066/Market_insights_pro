# -*- coding: utf-8 -*-
"""
이 파일은 Market Insights Pro 프로젝트의 FastAPI 서버 메인 애플리케이션입니다.
웹 UI 렌더링과 API 엔드포인트를 모두 포함합니다.
"""
from typing import List, Tuple
from fastapi import FastAPI, HTTPException, Request, Form, WebSocket, Depends
from fastapi.responses import HTMLResponse, JSONResponse
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
from core.scraper import AmazonScraper
from core.kafka_manager import get_kafka_manager, KafkaManager
from core.background_worker import start_background_worker
from core.stream_processor import start_stream_processor, get_stream_processor
from core.event_store import get_event_store_service, EventType

# 로거 설정
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Amazon Market Insights Pro",
    description="Amazon product market analysis and competition research tool",
    version="1.2.0", # 버전 업데이트
)

# --- 전역 인스턴스 및 설정 ---
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
sqlite_analyzer = SQLiteMarketAnalyzer()
scraper = AmazonScraper()
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
@app.on_event("startup")
async def startup_event():
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
    
    # 브라우저 시작을 백그라운드 태스크로 이동
    asyncio.create_task(initialize_browser())
    
    # 🚀 백그라운드 Kafka 워커 시작 (핵심!)
    if kafka_manager:
        try:
            asyncio.create_task(start_background_worker())
            print("✅ Background Analysis Worker started.")
            
            # 🔥 실시간 스트림 프로세서 시작 (Week 4 추가!)
            asyncio.create_task(start_stream_processor())
            print("✅ Real-time Stream Processor started.")
        except Exception as e:
            print(f"❌ Failed to start background worker: {e}")
    
    # 캐시 워밍 작업을 백그라운드에서 실행
    asyncio.create_task(warm_up_cache())
    
    print("✅ Market Insights Pro startup completed!")

async def initialize_browser():
    """브라우저를 백그라운드에서 초기화"""
    try:
        await scraper.start_browser()
        print("✅ Browser initialized successfully.")
    except Exception as e:
        print(f"❌ Browser initialization failed: {e}")

@app.on_event("shutdown")
async def shutdown_event():
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
