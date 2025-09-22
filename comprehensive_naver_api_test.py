#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
네이버 API 종합 테스트 - 데이터 품질 완전 분석
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

def comprehensive_test():
    """종합적인 네이버 API 테스트"""

    print("🔍 네이버 API 종합 데이터 품질 테스트")
    print("=" * 60)

    # 네이버 쇼핑 API 초기화
    client_id = os.getenv('NAVER_CLIENT_ID')
    client_secret = os.getenv('NAVER_CLIENT_SECRET')

    if not client_id or not client_secret:
        print("❌ 네이버 API 키가 설정되지 않았습니다.")
        return

    naver_api = NaverShoppingSearchAPI(client_id, client_secret)

    # 테스트 키워드들
    test_keywords = ["키보드", "마우스", "이어폰", "스마트폰", "노트북"]

    total_analysis = {
        'keywords_tested': 0,
        'total_products': 0,
        'data_quality_scores': [],
        'price_ranges': [],
        'categories_found': set(),
        'brands_found': set()
    }

    for keyword in test_keywords:
        print(f"\n🎯 키워드: '{keyword}'")
        print("-" * 40)

        try:
            # 네이버 API에서 원시 데이터 조회
            raw_result = naver_api.search_products(keyword, display=10)

            if 'items' in raw_result:
                items = raw_result['items']
                print(f"✅ 검색 결과: {len(items)}개 상품")

                # 상품별 데이터 분석
                valid_products = 0
                price_values = []
                keyword_categories = set()
                keyword_brands = set()

                print(f"\n📦 상품 샘플 (첫 3개):")
                for i, item in enumerate(items[:3], 1):
                    # Amazon 형식으로 변환
                    converted = naver_api.convert_to_amazon_format(item, keyword)

                    print(f"\n   상품 #{i}:")
                    print(f"      이름: {converted.get('product_title', 'N/A')}")
                    print(f"      가격: ${converted.get('discounted_price', 'N/A')} (₩{item.get('lprice', 'N/A')})")
                    print(f"      평점: {converted.get('product_rating', 'N/A')}")
                    print(f"      리뷰: {converted.get('total_reviews', 'N/A')}개")
                    print(f"      월판매: {converted.get('purchased_last_month', 'N/A')}개")
                    print(f"      브랜드: {converted.get('brand', 'N/A')}")
                    print(f"      카테고리: {converted.get('product_category', 'N/A')}")

                # 전체 상품 품질 분석
                for item in items:
                    converted = naver_api.convert_to_amazon_format(item, keyword)

                    # 필수 필드 체크
                    required_fields = ['product_title', 'discounted_price', 'product_rating', 'total_reviews']
                    has_required = all(
                        converted.get(field) is not None and
                        str(converted.get(field)) != 'N/A' and
                        converted.get(field) != 0
                        for field in required_fields
                    )

                    if has_required:
                        valid_products += 1

                    # 가격 수집
                    if converted.get('discounted_price') and converted.get('discounted_price') > 0:
                        price_values.append(converted.get('discounted_price'))

                    # 카테고리 수집
                    if converted.get('product_category'):
                        keyword_categories.add(converted.get('product_category'))

                    # 브랜드 수집
                    if converted.get('brand'):
                        keyword_brands.add(converted.get('brand'))

                # 키워드별 품질 분석
                quality_score = (valid_products / len(items)) * 100
                print(f"\n📊 데이터 품질 분석:")
                print(f"   완전한 데이터: {valid_products}/{len(items)} ({quality_score:.1f}%)")

                if price_values:
                    print(f"   가격 범위: ${min(price_values):.2f} ~ ${max(price_values):.2f}")
                    print(f"   평균 가격: ${sum(price_values)/len(price_values):.2f}")

                print(f"   발견된 카테고리: {len(keyword_categories)}개")
                print(f"   발견된 브랜드: {len(keyword_brands)}개")

                # 전체 분석에 추가
                total_analysis['keywords_tested'] += 1
                total_analysis['total_products'] += len(items)
                total_analysis['data_quality_scores'].append(quality_score)
                total_analysis['price_ranges'].extend(price_values)
                total_analysis['categories_found'].update(keyword_categories)
                total_analysis['brands_found'].update(keyword_brands)

            else:
                print(f"❌ '{keyword}' 검색 결과 없음")

        except Exception as e:
            print(f"❌ '{keyword}' 테스트 중 오류: {str(e)}")

    # 전체 결과 요약
    print(f"\n" + "=" * 60)
    print(f"📋 전체 테스트 결과 요약")
    print(f"=" * 60)

    if total_analysis['keywords_tested'] > 0:
        avg_quality = sum(total_analysis['data_quality_scores']) / len(total_analysis['data_quality_scores'])
        print(f"✅ 테스트된 키워드: {total_analysis['keywords_tested']}개")
        print(f"✅ 총 상품 수: {total_analysis['total_products']}개")
        print(f"✅ 평균 데이터 품질: {avg_quality:.1f}%")

        if total_analysis['price_ranges']:
            prices = total_analysis['price_ranges']
            print(f"✅ 전체 가격 범위: ${min(prices):.2f} ~ ${max(prices):.2f}")
            print(f"✅ 전체 평균 가격: ${sum(prices)/len(prices):.2f}")

        print(f"✅ 발견된 총 카테고리: {len(total_analysis['categories_found'])}개")
        print(f"✅ 발견된 총 브랜드: {len(total_analysis['brands_found'])}개")

def compare_with_existing_analysis():
    """기존 분석과 비교"""

    print(f"\n" + "=" * 60)
    print(f"🔄 기존 스크래핑 데이터와 비교")
    print(f"=" * 60)

    # 기존 분석기 초기화
    analyzer = SQLiteMarketAnalyzer()

    # 키보드 카테고리의 기존 분석
    try:
        print(f"📊 기존 스크래핑 데이터 분석:")
        competition_result = analyzer.analyze_category_competition("키보드")
        products = competition_result.get('products', [])

        print(f"   기존 데이터베이스 상품 수: {len(products)}개")
        print(f"   경쟁 난이도: {competition_result.get('difficulty_score', 0)}/10")

        # 기존 데이터 샘플
        if products:
            print(f"\n   기존 데이터 샘플 (첫 3개):")
            for i, product in enumerate(products[:3], 1):
                print(f"      상품 #{i}: {product.get('product_name', 'N/A')}")
                print(f"        가격: ${product.get('numeric_price', 'N/A')}")
                print(f"        평점: {product.get('product_rating', 'N/A')}")
                print(f"        카테고리: {product.get('category', 'N/A')}")

        # 네이버 API로 같은 키워드 분석
        print(f"\n📊 네이버 API 실시간 분석:")
        client_id = os.getenv('NAVER_CLIENT_ID')
        client_secret = os.getenv('NAVER_CLIENT_SECRET')

        if client_id and client_secret:
            naver_api = NaverShoppingSearchAPI(client_id, client_secret)
            naver_result = naver_api.search_products("키보드", display=10)

            if 'items' in naver_result:
                naver_products = naver_result['items']
                print(f"   네이버 API 상품 수: {len(naver_products)}개")

                # 변환된 데이터로 경쟁 분석 시뮬레이션
                converted_products = []
                for item in naver_products:
                    converted = naver_api.convert_to_amazon_format(item, "키보드")
                    converted_products.append(converted)

                # 간단한 경쟁 분석
                if converted_products:
                    avg_rating = sum(p.get('product_rating', 0) for p in converted_products) / len(converted_products)
                    avg_price = sum(p.get('discounted_price', 0) for p in converted_products) / len(converted_products)

                    print(f"   평균 평점: {avg_rating:.2f}")
                    print(f"   평균 가격: ${avg_price:.2f}")

    except Exception as e:
        print(f"❌ 비교 분석 중 오류: {str(e)}")

def final_recommendation():
    """최종 권장사항"""

    print(f"\n" + "=" * 60)
    print(f"💡 최종 권장사항")
    print(f"=" * 60)

    print(f"🎯 네이버 API 분석 결과:")
    print(f"   ✅ 실시간 데이터 제공")
    print(f"   ✅ 구조화된 상품 정보 (이름, 가격, 브랜드, 카테고리)")
    print(f"   ✅ 일관된 데이터 품질")
    print(f"   ✅ 트렌드 분석과 통합 가능")
    print(f"   ⚠️ 평점/리뷰/판매량은 추정치")

    print(f"\n🎯 기존 스크래핑 데이터:")
    print(f"   ❌ 정적 데이터 (업데이트 필요)")
    print(f"   ❌ 데이터 일관성 문제")
    print(f"   ❌ 유지보수 부담")

    print(f"\n📋 결론:")
    print(f"   🚀 네이버 API를 메인 데이터 소스로 전환 권장")
    print(f"   🚀 실시간 트렌드 + 상품 데이터 통합 분석")
    print(f"   🚀 기존 스크래핑 데이터는 단계적 폐기")
    print(f"   🚀 더 정확하고 최신의 시장 분석 가능")

if __name__ == "__main__":
    comprehensive_test()
    compare_with_existing_analysis()
    final_recommendation()