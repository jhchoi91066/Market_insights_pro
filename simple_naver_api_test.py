#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
네이버 API 간단 테스트 - 실제 데이터 구조 확인
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

def simple_test():
    """간단한 네이버 API 테스트"""

    print("🔍 네이버 API 간단 테스트")
    print("=" * 50)

    # 네이버 쇼핑 API 직접 테스트
    client_id = os.getenv('NAVER_CLIENT_ID')
    client_secret = os.getenv('NAVER_CLIENT_SECRET')

    if not client_id or not client_secret:
        print("❌ 네이버 API 키가 설정되지 않았습니다.")
        return

    naver_api = NaverShoppingSearchAPI(client_id, client_secret)

    # 키워드 테스트
    keyword = "키보드"
    print(f"\n🎯 키워드: '{keyword}'")

    try:
        # 네이버 API에서 원시 데이터 조회
        print(f"📡 네이버 API 원시 호출...")
        raw_result = naver_api.search_products(keyword, display=3)

        print(f"📦 원시 결과 타입: {type(raw_result)}")
        print(f"📦 원시 결과 키들: {raw_result.keys() if isinstance(raw_result, dict) else 'Not a dict'}")

        if isinstance(raw_result, dict) and 'items' in raw_result:
            items = raw_result['items']
            print(f"📦 검색된 상품 수: {len(items)}")

            if items:
                first_item = items[0]
                print(f"\n📦 첫 번째 상품 데이터:")
                for key, value in first_item.items():
                    print(f"   {key}: {value}")

                # Amazon 형식으로 변환 테스트
                print(f"\n🔄 Amazon 형식 변환 테스트...")
                converted = naver_api.convert_to_amazon_format(first_item, keyword)
                print(f"📦 변환된 데이터:")
                for key, value in converted.items():
                    print(f"   {key}: {value}")

        else:
            print(f"❌ 예상하지 못한 응답 구조: {raw_result}")

    except Exception as e:
        print(f"❌ 테스트 중 오류: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    simple_test()