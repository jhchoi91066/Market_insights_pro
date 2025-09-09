# -*- coding: utf-8 -*-
"""
Amazon Market Insights Pro - FastAPI Main Application
Provides web UI and API endpoints for Amazon market analysis.
"""
from typing import List, Tuple
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
import os
from functools import lru_cache
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
    version="1.0.0", # Amazon conversion complete
)

# --- v2 MVP 설정 ---
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# 분석기 인스턴스는 미리 생성
sqlite_analyzer = SQLiteMarketAnalyzer()

# --- 동시성 제어를 위한 글로벌 락 ---
import asyncio
scraping_lock = asyncio.Lock()  # 한 번에 하나의 스크래핑만 허용

# -----------------------------------------------------------------------------
# MVP 웹 페이지 라우팅
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "title": "Amazon Market Insights Pro"})

@app.post("/report", response_class=HTMLResponse)
async def create_report(request: Request, keyword: str = Form(...)):
    log_to_file(f"--- 보고서 생성 시작: '{keyword}' ---")
    scraper = None # finally에서 사용하기 위해 미리 선언
    try:
        # --- 지연 로딩(Lazy Loading) 적용 ---
        log_to_file("Scraper 모듈 로딩 시작")
        from core.scraper import AmazonScraper
        scraper = AmazonScraper()
        log_to_file("Scraper 모듈 로딩 완료")

        # English keywords don't require encoding handling

        # --- 브라우저 실행 ---
        log_to_file("브라우저 시작")
        await scraper.start_browser()
        log_to_file("브라우저 시작 완료")

        # 1. 기존 데이터 확인
        log_to_file("기존 데이터 확인 시작")
        existing_count = 0
        try:
            existing_check = sqlite_analyzer.analyze_category_competition(keyword)
            existing_count = existing_check.get('competitor_count', 0) if existing_check else 0
        except Exception as e:
            log_to_file(f"기존 데이터 확인 중 오류: {e}")
        log_to_file(f"기존 데이터 {existing_count}개 확인")

        # 2. 필요시 스크래핑 실행 (동시성 제어)
        if existing_count < 30:  # 더 많은 데이터 수집을 위해 기준 상향
            log_to_file("스크래핑 필요 - 작업 시작")
            
            # 동시성 제어: 한 번에 하나의 스크래핑만 허용
            try:
                # 락이 사용 중인지 확인 (논블로킹)
                if scraping_lock.locked():
                    log_to_file(f"⏰ 대기 중: 다른 분석이 진행 중입니다. '{keyword}' 대기열에 추가")
                
                async with scraping_lock:
                    log_to_file(f"🔒 스크래핑 락 획득: '{keyword}' 작업 시작")
                    db_result = await scraper.scrape_and_save_to_db(keyword, max_products=100)
                    log_to_file(f"🔓 스크래핑 락 해제: '{keyword}' 작업 완료")
            except Exception as lock_error:
                log_to_file(f"❌ 락 처리 중 오류: {lock_error}")
                raise lock_error
            
            log_to_file(f"스크래핑 작업 완료. 결과: {db_result.get('success')}")
            if not db_result or not db_result.get('success'):
                error_reason = db_result.get('message', 'Unknown scraping error') if db_result else 'Scraper did not respond'
                log_to_file(f"Scraping failed: {error_reason}")
                return templates.TemplateResponse("error.html", {
                    "request": request,
                    "error_message": f"Failed to collect data for '{keyword}' category",
                    "error_reason": error_reason
                })
        else:
            log_to_file("스크래핑 불필요 - 건너뜀")

        # 3. 분석 실행
        log_to_file("데이터 분석 시작")
        competition_report = sqlite_analyzer.analyze_category_competition(keyword)
        log_to_file("경쟁 분석 완료")
        saturation_report = sqlite_analyzer.calculate_market_saturation(keyword)
        log_to_file("시장 포화도 분석 완료")
        report_data = {**competition_report, **saturation_report, 'keyword': keyword}

        # 4. 결과 페이지 렌더링
        log_to_file("결과 페이지 렌더링")
        return templates.TemplateResponse("report.html", {"request": request, "report": report_data})
    
    except Exception as e:
        error_trace = traceback.format_exc()
        log_to_file(f"!!! 치명적 오류 발생: {e}")
        log_to_file(error_trace)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": "An unexpected error occurred while generating the analysis report.",
            "error_reason": str(e)
        })
    finally:
        if scraper:
            log_to_file("브라우저 종료 시작")
            await scraper.close_browser()
            log_to_file("브라우저 종료 완료")
        log_to_file(f"--- 보고서 생성 종료: '{keyword}' ---")
