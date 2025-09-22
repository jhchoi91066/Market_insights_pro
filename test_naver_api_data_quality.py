#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
네이버 API 데이터 품질 테스트
기존 스크래핑 데이터와 네이버 API 데이터 비교
"""

import sys
import os
from dotenv import load_dotenv
import json

# 환경 변수 로드
load_dotenv('.env.development')

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.naver_shopping_api import NaverShoppingSearchAPI
from core.analyzer_v2 import SQLiteMarketAnalyzer

def test_naver_api_data_quality():
    """네이버 API 데이터 품질 테스트"""

    print("🔍 네이버 API 데이터 품질 테스트")
    print("=" * 60)

    # 네이버 쇼핑 API 직접 테스트
    client_id = os.getenv('NAVER_CLIENT_ID')
    client_secret = os.getenv('NAVER_CLIENT_SECRET')

    if not client_id or not client_secret:
        print("❌ 네이버 API 키가 설정되지 않았습니다.")
        return

    naver_api = NaverShoppingSearchAPI(client_id, client_secret)

    # 테스트 키워드들
    test_keywords = ["키보드", "마우스", "이어폰"]

    for keyword in test_keywords:
        print(f"\n🎯 키워드: '{keyword}'")
        print("-" * 40)

        try:
            # 네이버 API에서 데이터 조회
            print(f"📡 네이버 API 호출 중...")
            products = naver_api.search_products(keyword, display=10)

            if not products:
                print(f"❌ '{keyword}' 검색 결과 없음")
                continue

            print(f"✅ 검색 결과: {len(products)}개 상품")

            # 첫 5개 상품의 상세 정보 출력
            for i, product in enumerate(products[:5], 1):
                print(f"\n📦 상품 #{i}:")
                print(f"   이름: {product.get('product_name', 'N/A')}")
                print(f"   가격: {product.get('price_display', 'N/A')} (숫자: {product.get('numeric_price', 'N/A')})")
                print(f"   평점: {product.get('product_rating', 'N/A')}")
                print(f"   리뷰: {product.get('total_reviews', 'N/A')}개")
                print(f"   월판매: {product.get('purchased_last_month', 'N/A')}개")
                print(f"   카테고리: {product.get('category', 'N/A')}")
                print(f"   브랜드: {product.get('brand', 'N/A')}")
                print(f"   이미지: {product.get('image_url', 'N/A')}")
                print(f"   링크: {product.get('product_url', 'N/A')}")

            # 데이터 품질 분석
            print(f"\n📊 데이터 품질 분석:")

            # 필수 필드 체크
            required_fields = ['product_name', 'numeric_price', 'product_rating', 'total_reviews']
            valid_products = 0

            for product in products:
                has_all_fields = all(
                    product.get(field) is not None and
                    product.get(field) != 'N/A' and
                    str(product.get(field)).strip() != ''
                    for field in required_fields
                )
                if has_all_fields:
                    valid_products += 1

            quality_percentage = (valid_products / len(products)) * 100
            print(f"   완전한 데이터: {valid_products}/{len(products)} ({quality_percentage:.1f}%)")

            # 가격 범위 분석
            prices = [p.get('numeric_price', 0) for p in products if p.get('numeric_price', 0) > 0]
            if prices:
                print(f"   가격 범위: ${min(prices):.2f} ~ ${max(prices):.2f}")
                print(f"   평균 가격: ${sum(prices)/len(prices):.2f}")

            # 평점 분석
            ratings = [p.get('product_rating', 0) for p in products if p.get('product_rating', 0) > 0]
            if ratings:
                print(f"   평점 범위: {min(ratings):.1f} ~ {max(ratings):.1f}")
                print(f"   평균 평점: {sum(ratings)/len(ratings):.2f}")

        except Exception as e:
            print(f"❌ '{keyword}' 테스트 중 오류: {str(e)}")

def compare_with_existing_data():
    """기존 데이터베이스 데이터와 비교"""

    print("\n" + "=" * 60)
    print("🔄 기존 스크래핑 데이터와 비교")
    print("=" * 60)

    # 기존 분석기 초기화
    analyzer = SQLiteMarketAnalyzer()

    # 키보드 카테고리의 기존 데이터 조회
    try:
        competition_result = analyzer.analyze_category_competition("키보드")
        products = competition_result.get('products', [])

        print(f"📦 기존 데이터베이스 상품 수: {len(products)}개")

        if products:
            print(f"\n📊 기존 데이터 샘플 (첫 3개):")
            for i, product in enumerate(products[:3], 1):
                print(f"\n상품 #{i}:")
                print(f"   이름: {product.get('product_name', 'N/A')}")
                print(f"   가격: ${product.get('numeric_price', 'N/A')}")
                print(f"   평점: {product.get('product_rating', 'N/A')}")
                print(f"   리뷰: {product.get('total_reviews', 'N/A')}개")
                print(f"   카테고리: {product.get('category', 'N/A')}")

            # 기존 데이터 품질 분석
            valid_count = sum(1 for p in products if all([
                p.get('product_name'),
                p.get('numeric_price', 0) > 0,
                p.get('product_rating', 0) > 0
            ]))

            existing_quality = (valid_count / len(products)) * 100
            print(f"\n📊 기존 데이터 품질: {valid_count}/{len(products)} ({existing_quality:.1f}%)")

    except Exception as e:
        print(f"❌ 기존 데이터 조회 중 오류: {str(e)}")

def test_naver_api_vs_scraping_recommendation():
    """네이버 API vs 스크래핑 권장사항"""

    print("\n" + "=" * 60)
    print("💡 권장사항 분석")
    print("=" * 60)

    print("🔍 네이버 API 장점:")
    print("   ✅ 실시간 데이터")
    print("   ✅ 공식 API (안정성)")
    print("   ✅ 율리미티드 호출 가능")
    print("   ✅ 구조화된 데이터")
    print("   ✅ 트렌드 데이터 통합 가능")

    print("\n🔍 네이버 API 한계:")
    print("   ⚠️ 일부 상세 정보 부족 (리뷰, 판매량 등은 추정치)")
    print("   ⚠️ API 호출 제한")
    print("   ⚠️ 키워드 검색 기반")

    print("\n🔍 기존 스크래핑 데이터:")
    print("   ✅ 더 상세한 정보 (일부)")
    print("   ❌ 정적 데이터")
    print("   ❌ 유지보수 부담")
    print("   ❌ 확장성 제한")

    print("\n💡 결론:")
    print("   🎯 네이버 API를 메인으로 사용하고,")
    print("   🎯 필요시 스크래핑으로 보완하는 하이브리드 접근")
    print("   🎯 또는 네이버 API 100% 기반으로 전환 고려")

if __name__ == "__main__":
    test_naver_api_data_quality()
    compare_with_existing_data()
    test_naver_api_vs_scraping_recommendation()