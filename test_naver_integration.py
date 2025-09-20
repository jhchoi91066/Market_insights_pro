#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Naver API 통합 테스트 스크립트
시스템 전환 후 정상 작동 확인용
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv('.env.development')

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.naver_scraper_adapter import NaverScraperAdapter

async def test_naver_integration():
    """Naver API 통합 테스트"""
    print("🚀 Naver API 통합 테스트 시작")
    print("=" * 50)

    # API 키 확인
    client_id = os.getenv('NAVER_CLIENT_ID')
    client_secret = os.getenv('NAVER_CLIENT_SECRET')

    if not client_id or client_id == 'YOUR_CLIENT_ID':
        print("❌ NAVER_CLIENT_ID가 설정되지 않았습니다.")
        print("   .env.development 파일에서 YOUR_CLIENT_ID를 실제 값으로 변경해주세요.")
        return False

    if not client_secret or client_secret == 'YOUR_CLIENT_SECRET':
        print("❌ NAVER_CLIENT_SECRET이 설정되지 않았습니다.")
        print("   .env.development 파일에서 YOUR_CLIENT_SECRET을 실제 값으로 변경해주세요.")
        return False

    print("✅ API 키 설정 확인 완료")

    try:
        # Naver 스크래퍼 어댑터 초기화
        scraper = NaverScraperAdapter()
        print("✅ Naver 스크래퍼 어댑터 초기화 완료")

        # 브라우저 시작 테스트 (더미 메서드)
        browser_started = await scraper.start_browser()
        if browser_started:
            print("✅ 브라우저 시작 테스트 완료 (API 모드)")

        # 소량 데이터 수집 테스트
        test_keyword = "아이패드"
        print(f"\n🔍 테스트 키워드: '{test_keyword}'")
        print("소량 데이터 수집 테스트 (최대 5개)...")

        result = await scraper.scrape_and_save_to_db(test_keyword, max_products=5)

        print("\n📊 테스트 결과:")
        print(f"  성공: {result['success']}")
        print(f"  메시지: {result['message']}")
        print(f"  발견된 상품: {result['products_found']}")
        print(f"  저장된 상품: {result['products_saved']}")

        if 'data_source' in result:
            print(f"  데이터 소스: {result['data_source']}")

        # 메트릭 확인
        metrics = scraper.get_metrics()
        print("\n📈 스크래핑 메트릭:")
        print(f"  소요 시간: {metrics['duration_seconds']:.2f}초")
        print(f"  성공률: {metrics['success_rate']:.1f}%")
        print(f"  오류 수: {metrics['errors_count']}")

        # 브라우저 종료 테스트 (더미 메서드)
        await scraper.close_browser()
        print("✅ 브라우저 종료 테스트 완료")

        if result['success']:
            print("\n🎉 Naver API 통합 테스트 성공!")
            print("   시스템이 정상적으로 Naver Shopping API로 전환되었습니다.")
            return True
        else:
            print("\n❌ 데이터 수집 실패")
            return False

    except Exception as e:
        print(f"\n❌ 테스트 중 오류 발생: {str(e)}")
        return False

def main():
    """메인 실행 함수"""
    print("Naver API 통합 테스트")
    print("기존 Amazon 스크래퍼 → Naver API 전환 확인")
    print()

    # 비동기 테스트 실행
    success = asyncio.run(test_naver_integration())

    if success:
        print("\n✅ 모든 테스트 통과!")
        print("이제 웹 애플리케이션에서 Naver 데이터를 사용할 수 있습니다.")
    else:
        print("\n❌ 테스트 실패")
        print("API 키 설정이나 네트워크 연결을 확인해주세요.")

if __name__ == "__main__":
    main()