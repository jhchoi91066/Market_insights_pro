#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
네이버 API 연결 간단 테스트
"""

import os
import requests
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv('.env.development')

def test_naver_api():
    """네이버 API 간단 연결 테스트"""

    client_id = os.getenv('NAVER_CLIENT_ID')
    client_secret = os.getenv('NAVER_CLIENT_SECRET')

    print(f"🔑 Client ID: {client_id}")
    print(f"🔑 Client Secret: {client_secret[:10]}..." if client_secret else "None")

    if not client_id or not client_secret:
        print("❌ 네이버 API 키가 설정되지 않았습니다.")
        return False

    # API 요청
    headers = {
        'X-Naver-Client-Id': client_id,
        'X-Naver-Client-Secret': client_secret
    }

    params = {
        'query': '키보드',
        'start': 1,
        'display': 3
    }

    try:
        response = requests.get(
            'https://openapi.naver.com/v1/search/shop.json',
            headers=headers,
            params=params,
            timeout=10
        )

        print(f"📡 Response Status: {response.status_code}")
        print(f"📄 Response Content: {response.text[:200]}...")

        if response.status_code == 200:
            data = response.json()
            print(f"✅ 성공! 찾은 상품 수: {len(data.get('items', []))}")
            return True
        else:
            print(f"❌ API 오류: {response.text}")
            return False

    except Exception as e:
        print(f"❌ 연결 오류: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 네이버 API 연결 테스트 시작")
    print("=" * 50)

    success = test_naver_api()

    print("=" * 50)
    if success:
        print("🎉 네이버 API 연결 성공!")
    else:
        print("❌ 네이버 API 연결 실패 - API 키를 확인해주세요.")