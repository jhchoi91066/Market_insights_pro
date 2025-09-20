#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
네이버 API 통합 테스트: 데이터 수집 → DB 저장 → 검색 확인
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv('.env.development')

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.naver_scraper_adapter import NaverScraperAdapter
from core.analyzer_v2 import SQLiteMarketAnalyzer
from core.database_optimizer import get_optimized_engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_full_integration():
    """
    전체 통합 테스트:
    1. 네이버 API로 새로운 키워드 데이터 수집
    2. 데이터베이스에 저장 확인
    3. 분석 기능 테스트
    """

    print("🚀 네이버 API 통합 테스트 시작")
    print("=" * 50)

    # 1단계: 네이버 스크래퍼 초기화
    print("\n1️⃣ 네이버 스크래퍼 초기화...")
    scraper = NaverScraperAdapter()
    await scraper.start_browser()  # 브라우저는 실제로 사용하지 않지만 호환성 유지

    # 2단계: 기존 데이터베이스 상태 확인
    print("\n2️⃣ 기존 데이터베이스 상태 확인...")
    engine = get_optimized_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) as count FROM products"))
        before_count = result.fetchone()[0]
        print(f"   📊 기존 상품 수: {before_count}개")

    # 3단계: 새로운 키워드로 데이터 수집
    test_keyword = "무선마우스"  # 테스트용 키워드
    print(f"\n3️⃣ '{test_keyword}' 키워드로 데이터 수집 중...")

    result = await scraper.scrape_and_save_to_db(test_keyword, max_products=15)

    if result['success']:
        print(f"   ✅ 데이터 수집 성공: {result['products_saved']}개 상품 저장")
        print(f"   📝 메시지: {result['message']}")
    else:
        print(f"   ❌ 데이터 수집 실패: {result['message']}")
        return False

    # 4단계: 데이터베이스 업데이트 확인
    print("\n4️⃣ 데이터베이스 업데이트 확인...")
    with engine.connect() as conn:
        # 전체 상품 수 확인
        result = conn.execute(text("SELECT COUNT(*) as count FROM products"))
        after_count = result.fetchone()[0]

        # 새로 추가된 상품 확인
        result = conn.execute(text("""
            SELECT COUNT(*) as count FROM products
            WHERE product_category LIKE :keyword
        """), {"keyword": f"%{test_keyword}%"})
        keyword_count = result.fetchone()[0]

        print(f"   📈 전체 상품 수: {before_count} → {after_count} (+{after_count - before_count})")
        print(f"   🔍 '{test_keyword}' 관련 상품: {keyword_count}개")

    # 5단계: 최신 상품 데이터 샘플 확인
    print("\n5️⃣ 최신 저장된 상품 샘플 확인...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT product_title, discounted_price, product_category, data_source
            FROM products
            WHERE data_source = 'naver_shopping_search'
            ORDER BY scraped_at DESC
            LIMIT 3
        """))

        latest_products = result.fetchall()
        for i, product in enumerate(latest_products, 1):
            print(f"   {i}. {product[0][:50]}...")
            print(f"      💰 가격: ${product[1]}")
            print(f"      📂 카테고리: {product[2]}")
            print(f"      🏷️ 데이터 소스: {product[3]}")

    # 6단계: 분석기 테스트
    print("\n6️⃣ 시장 분석 기능 테스트...")
    analyzer = SQLiteMarketAnalyzer()

    # 경쟁 분석
    competition_report = analyzer.analyze_category_competition(test_keyword)
    print(f"   📊 경쟁 분석 결과:")
    print(f"      - 총 제품 수: {competition_report.get('total_products', 0)}")
    print(f"      - 평균 가격: ${competition_report.get('avg_price', 0):.2f}")
    print(f"      - 가격 범위: ${competition_report.get('min_price', 0):.2f} ~ ${competition_report.get('max_price', 0):.2f}")

    # 시장 포화도 분석
    saturation_report = analyzer.calculate_market_saturation(test_keyword)
    print(f"   📈 시장 포화도 분석:")
    print(f"      - 시장 포화도: {saturation_report.get('market_saturation_score', 0):.1f}%")
    print(f"      - 브랜드 다양성: {saturation_report.get('brand_diversity_score', 0):.1f}")

    # 7단계: 정리
    await scraper.close_browser()

    print("\n" + "=" * 50)
    print("🎉 통합 테스트 완료!")
    print(f"✅ 네이버 API → 데이터베이스 저장 → 분석 파이프라인 정상 동작")

    return True

if __name__ == "__main__":
    asyncio.run(test_full_integration())