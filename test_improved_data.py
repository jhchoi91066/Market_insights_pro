#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
개선된 데이터 품질 테스트
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

async def test_improved_data():
    """개선된 데이터 품질 테스트"""

    print("🎯 개선된 데이터 품질 테스트")
    print("=" * 50)

    # 스크래퍼 초기화
    scraper = NaverScraperAdapter()
    await scraper.start_browser()

    # 새로운 키워드로 테스트 (더미 데이터와 구분하기 위해)
    test_keyword = "스마트폰 케이스"

    print(f"🔍 키워드: '{test_keyword}' 데이터 수집 중...")

    result = await scraper.scrape_and_save_to_db(test_keyword, max_products=10)

    print(f"📊 결과:")
    print(f"   성공: {result['success']}")
    print(f"   메시지: {result['message']}")
    print(f"   찾은 상품: {result['products_found']}개")
    print(f"   저장된 상품: {result['products_saved']}개")

    await scraper.close_browser()

    # 분석 결과도 확인
    if result['success'] and result['products_saved'] > 0:
        print(f"\n📈 분석 결과 미리보기:")
        from core.analyzer_v2 import SQLiteMarketAnalyzer

        analyzer = SQLiteMarketAnalyzer()
        competition_report = analyzer.analyze_category_competition(test_keyword)

        print(f"   경쟁 제품 수: {competition_report.get('competitor_count', 0)}")
        print(f"   난이도 점수: {competition_report.get('difficulty_score', 0)}")

        # TOP 3 제품 표시 (데이터 다양성 확인)
        top_products = competition_report.get('top_10_products', [])[:3]
        if top_products:
            print(f"\n   🏆 TOP 3 제품 (데이터 다양성 확인):")
            for i, product in enumerate(top_products, 1):
                print(f"      {i}. {product['product_title'][:40]}...")
                print(f"         가격: {product['discounted_price']}")
                print(f"         평점: {product['product_rating']}")
                print(f"         리뷰: {product['total_reviews']}개")
                print(f"         월 구매: {product['purchased_last_month']}개")
                print()

    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test_improved_data())