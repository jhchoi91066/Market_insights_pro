# -*- coding: utf-8 -*-
"""
Amazon Market Insights Pro - FastAPI Main Application
Provides web UI and API endpoints for Amazon market analysis.
"""
import json
from typing import List
from fastapi import FastAPI, Request, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncio
import traceback
from datetime import datetime

# --- 로깅 헬퍼 함수 ---
def log_to_file(message: str):
    """디버깅 메시지를 파일에 기록합니다."""
    with open("debug_log.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} - {message}\n")
    print(message) # 콘솔에도 출력

# 분석기 모듈은 시작 시 로드해도 안전합니다.
from core.analyzer_v2 import SQLiteMarketAnalyzer

app = FastAPI(
    title="Amazon Market Insights Pro",
    description="Amazon product market analysis and competition research tool",
    version="1.1.0", # WebSocket support added
)

# --- v2 MVP 설정 ---
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# 분석기 및 캐시 인스턴스 생성
sqlite_analyzer = SQLiteMarketAnalyzer()

# Redis 캐시 매니저 import 및 초기화
from core.cache import get_cache_manager
cache_manager = get_cache_manager()

# --- WebSocket 연결 관리 ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        log_to_file(f"WebSocket 연결: {len(self.active_connections)}명 접속 중")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        log_to_file(f"WebSocket 연결 해제: {len(self.active_connections)}명 접속 중")

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

ws_manager = ConnectionManager()

# --- 동시성 제어를 위한 글로벌 락 ---
scraping_lock = asyncio.Lock()  # 한 번에 하나의 스크래핑만 허용

# -----------------------------------------------------------------------------
# WebSocket 엔드포인트
# -----------------------------------------------------------------------------
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await ws_manager.connect(websocket)
    try:
        while True:
            # 클라이언트로부터 메시지를 받을 수 있지만, 현재는 연결 유지 목적
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

# -----------------------------------------------------------------------------
# MVP 웹 페이지 라우팅
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "title": "Amazon Market Insights Pro"})

@app.post("/report", response_class=HTMLResponse)
def create_report(request: Request, keyword: str = Form(...)):
    log_to_file(f"--- 보고서 생성 시작: '{keyword}' ---")
    scraper = None # finally에서 사용하기 위해 미리 선언
    
    async def broadcast_status(status: str, progress: int, message: str):
        """Helper to broadcast status updates."""
        log_to_file(f"[{progress}%] {message}")
        update = json.dumps({
            "status": status,
            "progress": progress,
            "message": message
        })
        await ws_manager.broadcast(update)

    try:
        # 1. 캐시된 결과 확인 (가장 먼저 체크)
        await broadcast_status('caching', 0, f"Checking cache for '{keyword}'...")
        cached_result = cache_manager.get_analysis_result(keyword)
        if cached_result:
            log_to_file(f"🎯 캐시 HIT! '{keyword}' 결과를 캐시에서 반환")
            await broadcast_status('completed', 100, "Cache hit! Returning cached data.")
            return templates.TemplateResponse("report.html", {
                "request": request, 
                "report": cached_result,
                "cached": True
            })
        
        await broadcast_status('initializing', 5, f"Cache miss. Starting new analysis for '{keyword}'.")
        
        # --- 지연 로딩(Lazy Loading) 적용 ---
        await broadcast_status('loading', 10, "Loading scraper module...")
        from core.scraper import AmazonScraper
        scraper = AmazonScraper()

        # --- 브라우저 실행 ---
        await broadcast_status('browser_starting', 15, "Starting browser...")
        await scraper.start_browser()

        # 2. 기존 데이터 확인
        await broadcast_status('data_checking', 20, "Checking for existing data in database...")
        existing_count = 0
        try:
            existing_check = sqlite_analyzer.analyze_category_competition(keyword)
            existing_count = existing_check.get('competitor_count', 0) if existing_check else 0
        except Exception as e:
            log_to_file(f"기존 데이터 확인 중 오류: {e}")
        log_to_file(f"기존 데이터 {existing_count}개 확인")

        # 3. 필요시 스크래핑 실행 (동시성 제어)
        if existing_count < 30:
            await broadcast_status('scraping', 30, "Existing data is insufficient. Starting live scraping...")
            
            if scraping_lock.locked():
                await broadcast_status('waiting', 25, "Another analysis is in progress. Queued...")
            
            async with scraping_lock:
                await broadcast_status('scraping_active', 40, f"Actively scraping Amazon for '{keyword}'...")
                db_result = await scraper.scrape_and_save_to_db(keyword, max_products=100)
            
            if not db_result or not db_result.get('success'):
                error_reason = db_result.get('message', 'Unknown scraping error') if db_result else 'Scraper did not respond'
                await broadcast_status('error', 0, f"Scraping failed: {error_reason}")
                return templates.TemplateResponse("error.html", {
                    "request": request,
                    "error_message": f"Failed to collect data for '{keyword}' category.",
                    "error_reason": error_reason
                })
        else:
            await broadcast_status('analyzing', 70, "Sufficient data found in database. Skipping scraping.")

        # 4. 분석 실행
        await broadcast_status('analyzing', 80, "Analyzing market competition...")
        competition_report = sqlite_analyzer.analyze_category_competition(keyword)
        
        await broadcast_status('analyzing', 90, "Calculating market saturation...")
        saturation_report = sqlite_analyzer.calculate_market_saturation(keyword)
        
        report_data = {**competition_report, **saturation_report, 'keyword': keyword}

        # 5. 결과를 캐시에 저장 (1시간 TTL)
        await broadcast_status('caching', 95, "Saving analysis results to cache...")
        cache_manager.set_analysis_result(keyword, report_data, ttl_hours=1)

        # 6. 완료
        await broadcast_status('completed', 100, "Analysis complete! Rendering report.")

        # 7. 결과 페이지 렌더링
        return templates.TemplateResponse("report.html", {"request": request, "report": report_data})
    
    except Exception as e:
        error_trace = traceback.format_exc()
        log_to_file(f"!!! 치명적 오류 발생: {e}")
        log_to_file(error_trace)
        await broadcast_status('error', 0, f"An unexpected error occurred: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": "An unexpected error occurred while generating the analysis report.",
            "error_reason": str(e)
        })
    finally:
        if scraper:
            await scraper.close_browser()
            log_to_file("브라우저 종료 완료")
        log_to_file(f"--- 보고서 생성 종료: '{keyword}' ---")


# -----------------------------------------------------------------------------
# 캐시 관리 API 엔드포인트
# -----------------------------------------------------------------------------

@app.get("/api/cache/stats")
def get_cache_statistics():
    """캐시 통계 정보 조회"""
    try:
        stats = cache_manager.get_cache_stats()
        health = cache_manager.health_check()
        return {"status": "success", "cache_health": health, "statistics": stats}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/cache/health")
def cache_health_check():
    """Redis 연결 상태 확인"""
    try:
        health = cache_manager.health_check()
        return {"status": "success", **health}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/api/cache/analysis")
def flush_analysis_cache():
    """분석 결과 캐시 전체 삭제"""
    try:
        deleted_count = cache_manager.flush_analysis_cache()
        return {"status": "success", "message": f"Deleted {deleted_count} entries.", "deleted_count": deleted_count}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# -----------------------------------------------------------------------------
# 애플리케이션 시작 이벤트 
# -----------------------------------------------------------------------------

@app.on_event("startup")
def startup_event():
    """애플리케이션 시작 시 실행"""
    log_to_file("🚀 Market Insights Pro 시작")
    try:
        health = cache_manager.health_check()
        if health['status'] == 'healthy':
            log_to_file(f"✅ Redis 연결 성공 (응답시간: {health['response_time_ms']}ms)")
        else:
            log_to_file(f"⚠️ Redis 연결 실패: {health.get('error', 'Unknown error')}")
    except Exception as e:
        log_to_file(f"❌ Redis 초기화 오류: {e}")

@app.on_event("shutdown") 
def shutdown_event():
    """애플리케이션 종료 시 실행"""
    log_to_file("🔄 Market Insights Pro 종료")

# -----------------------------------------------------------------------------
# 개발용 엔드포인트 (프로덕션에서는 제거 권장)
# -----------------------------------------------------------------------------

@app.get("/debug/cache-test")
def debug_cache_test():
    """캐시 기능 테스트용 엔드포인트"""
    try:
        test_data = {"test": True, "timestamp": datetime.now().isoformat()}
        cache_manager.set_analysis_result("debug_test", test_data, ttl_hours=1)
        retrieved = cache_manager.get_analysis_result("debug_test")
        stats = cache_manager.get_cache_stats()
        return {"status": "success", "data": retrieved, "stats": stats}
    except Exception as e:
        return {"status": "error", "message": str(e)}
