# -*- coding: utf-8 -*-
"""
이 스크립트는 MarketAnalyzer 클래스의 모든 분석 메소드가
API 엔드포인트에서 사용될 때를 가정하여 올바르게 작동하는지 검증합니다.

각 메소드를 호출하고, 반환된 결과가 JSON으로 변환 가능한
파이썬 기본 객체(딕셔너리, 리스트)인지 확인합니다.
"""
import os
import sys
import json

# 프로젝트 루트 디렉토리를 sys.path에 추가하여 core 모듈을 임포트할 수 있도록 함
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from core.analyzer import MarketAnalyzer

# 데이터 파일 경로 설정
DATA_FILE_PATH = os.path.join(project_root, 'data', 'amazon_products_sales_data_cleaned.csv')

def run_verification():
    """모든 분석 메소드를 순차적으로 테스트하고 결과를 출력합니다."""
    print("\n--- MarketAnalyzer 검증 스크립트 시작 ---")

    # 1. MarketAnalyzer 인스턴스 생성
    print("\n[1/5] MarketAnalyzer 인스턴스를 생성합니다...")
    analyzer = MarketAnalyzer(DATA_FILE_PATH)
    if analyzer.df.empty:
        print("오류: 데이터프레임이 비어있어 테스트를 진행할 수 없습니다.")
        return
    print("-> 성공: MarketAnalyzer가 성공적으로 초기화되었습니다.")

    # 2. analyze_category_competition 테스트
    print("\n[2/5] 'analyze_category_competition' 메소드를 테스트합니다...")
    category_params = {
        'category': 'Laptops',
        'price_range': (200.0, 1000.0),
        'num_bins': 5
    }
    try:
        result_competition = analyzer.analyze_category_competition(**category_params)
        print("-> 성공: 결과가 성공적으로 반환되었습니다.")
        print(json.dumps(result_competition, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"-> 실패: 테스트 중 오류 발생 - {e}")

    # 3. find_price_gaps 테스트
    print("\n[3/5] 'find_price_gaps' 메소드를 테스트합니다...")
    price_gap_params = {
        'category': 'Phones',
        'bin_width': 50
    }
    try:
        result_gaps = analyzer.find_price_gaps(**price_gap_params)
        print("-> 성공: 결과가 성공적으로 반환되었습니다.")
        print(json.dumps(result_gaps, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"-> 실패: 테스트 중 오류 발생 - {e}")

    # 4. extract_success_keywords 테스트
    print("\n[4/5] 'extract_success_keywords' 메소드를 테스트합니다...")
    keyword_params = {
        'category': 'Headphones',
        'rating_threshold': 4.5,
        'reviews_threshold': 500,
        'num_keywords': 10
    }
    try:
        result_keywords = analyzer.extract_success_keywords(**keyword_params)
        print("-> 성공: 결과가 성공적으로 반환되었습니다.")
        print(json.dumps(result_keywords, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"-> 실패: 테스트 중 오류 발생 - {e}")

    # 5. calculate_market_saturation 테스트
    print("\n[5/5] 'calculate_market_saturation' 메소드를 테스트합니다...")
    saturation_params = {
        'category': 'Printers & Scanners'
    }
    try:
        result_saturation = analyzer.calculate_market_saturation(**saturation_params)
        print("-> 성공: 결과가 성공적으로 반환되었습니다.")
        print(json.dumps(result_saturation, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"-> 실패: 테스트 중 오류 발생 - {e}")

    print("\n--- 모든 검증이 완료되었습니다. ---")

if __name__ == '__main__':
    run_verification()
