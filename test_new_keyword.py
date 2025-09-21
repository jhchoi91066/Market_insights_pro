#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
새로운 키워드로 네이버 API 데이터 수집 테스트
"""

import asyncio
import sys
import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv('.env.development')

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.naver_scraper_adapter import NaverScraperAdapter

async def test_new_keyword():
    """새로운 키워드로 데이터 수집 테스트"""

    print("🚀 새로운 키워드 데이터 수집 테스트")
    print("=" * 50)

    # 스크래퍼 초기화
    scraper = NaverScraperAdapter()
    await scraper.start_browser()

    # 새로운 키워드 테스트
    test_keyword = "무선 충전기"  # 기존과 다른 새로운 키워드

    print(f"🔍 키워드: '{test_keyword}' 데이터 수집 중...")

    result = await scraper.scrape_and_save_to_db(test_keyword, max_products=10)

    print(f"📊 결과:")
    print(f"   성공: {result['success']}")
    print(f"   메시지: {result['message']}")
    print(f"   찾은 상품: {result['products_found']}개")
    print(f"   저장된 상품: {result['products_saved']}개")

    if result['success'] and result['products_saved'] > 0:
        print("✅ 새로운 상품 데이터 저장 성공!")
    elif result['success'] and result['products_saved'] == 0:
        print("⚠️ 데이터 수집은 성공했지만 새로운 상품이 저장되지 않았습니다 (중복 또는 필터링)")
    else:
        print("❌ 데이터 수집 실패")

    await scraper.close_browser()
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test_new_keyword())