# -*- coding: utf-8 -*-
"""
이 스크립트는 main.py에 구현된 캐싱 기능(@lru_cache)이
정상적으로 작동하는지 검증합니다.

동일한 인자로 함수를 두 번 호출하여,
두 번째 호출 시에는 계산 과정(CACHE MISS 메시지)이 생략되는 것을 확인합니다.
"""
import os
import sys
import time

# 프로젝트 루트 디렉토리를 sys.path에 추가하여 main 모듈을 임포트할 수 있도록 함
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# main에 정의된 캐시된 함수와 분석기 인스턴스를 가져옴
from main import _get_cached_full_report, market_analyzer

def run_caching_verification():
    """캐싱 기능이 올바르게 동작하는지 테스트합니다."""
    print("\n--- 캐싱 기능 검증 스크립트 시작 ---")

    if market_analyzer.df.empty:
        print("오류: 데이터프레임이 비어있어 테스트를 진행할 수 없습니다.")
        return

    # 테스트에 사용할 파라미터 정의
    test_params = {
        'category': 'Headphones',
        'price_range': (50.0, 500.0),
        'rating_threshold': 4.5,
        'reviews_threshold': 100
    }

    # 첫 번째 호출
    print("\n[1/2] 첫 번째 분석을 요청합니다...")
    start_time = time.time()
    _get_cached_full_report(**test_params)
    end_time = time.time()
    print(f"-> 첫 번째 호출 소요 시간: {end_time - start_time:.4f} 초")

    # 두 번째 호출
    print("\n[2/2] 동일한 조건으로 두 번째 분석을 요청합니다...")
    start_time = time.time()
    _get_cached_full_report(**test_params)
    end_time = time.time()
    print(f"-> 두 번째 호출 소요 시간: {end_time - start_time:.4f} 초")
    print("\n(두 번째 호출 시 'CACHE MISS' 메시지가 출력되지 않았다면 캐싱 성공입니다.)")

    print("\n--- 모든 검증이 완료되었습니다. ---")

if __name__ == '__main__':
    run_caching_verification()
