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
import os
import asyncio
import json

# 캐시 및 분석 모듈
from core.cache import get_cache_manager, CacheManager
from core.analyzer_v2 import SQLiteMarketAnalyzer
from core.scraper import AmazonScraper

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
PRE_WARM_KEYWORDS = ["wireless mouse", "bluetooth headphones"] # 캐시 워밍 키워드

# --- Pydantic 모델 ---
class CacheClearRequest(BaseModel):
    keyword: str

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
    global cache_manager
    try:
        cache_manager = get_cache_manager()
        print("✅ Redis Cache Manager connected.")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        cache_manager = None
    
    await scraper.start_browser()
    # 캐시 워밍 작업을 백그라운드에서 실행
    asyncio.create_task(warm_up_cache())

@app.on_event("shutdown")
async def shutdown_event():
    await scraper.close_browser()

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
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/report", response_class=HTMLResponse)
async def get_report(request: Request, keyword: str):
    try:
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
