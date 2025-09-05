# -*- coding: utf-8 -*-
"""
이 스크립트는 전처리된 Amazon 상품 데이터셋을 사용하여
주요 수치 데이터(가격, 평점, 리뷰 수, 구매량) 간의 상관관계를 분석합니다.

상관관계 행렬을 계산하고 결과를 출력하여 각 변수들이 서로 어떤 관계를 맺고 있는지 확인합니다.
"""
import pandas as pd
import os

def analyze_correlation(base_dir):
    """
    상관관계 분석을 수행하고 결과를 출력하는 메인 함수.
    """
    # --- 1. 데이터 로드 ---
    # 전처리 스크립트('01_preprocess_data.py')가 실행된 후의 데이터를 사용합니다.
    file_path = os.path.join(base_dir, 'data', 'amazon_products_sales_data_cleaned.csv')
    
    print(f"데이터를 로드합니다: {file_path}")
    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print(f"오류: 파일을 찾을 수 없습니다. 경로를 확인하세요: {file_path}")
        return

    # --- 2. 분석할 컬럼 선택 ---
    # 상관관계를 보고자 하는 숫자형 데이터 컬럼들을 선택합니다.
    correlation_cols = ['discounted_price', 'product_rating', 'total_reviews', 'purchased_last_month']
    df_corr = df[correlation_cols]
    print(f"분석 대상 컬럼: {correlation_cols}")

    # --- 3. 상관관계 행렬 계산 ---
    # .corr() 함수를 사용하여 컬럼 간의 피어슨 상관계수를 계산합니다.
    print("\n상관관계 행렬을 계산합니다...")
    correlation_matrix = df_corr.corr()

    # --- 4. 결과 출력 ---
    print("\n### 가격, 평점, 리뷰 수, 구매량 간의 상관관계 분석 ###\n")
    print("상관관계 계수는 -1부터 1 사이의 값을 가집니다.")
    print("- 1에 가까울수록 강한 양의 상관관계 (하나가 증가하면 다른 하나도 증가)")
    print("- -1에 가까울수록 강한 음의 상관관계 (하나가 증가하면 다른 하나는 감소)")
    print("- 0에 가까울수록 상관관계가 거의 없음\n")
    
    # 보기 좋게 출력하기 위해 Pandas 출력 옵션을 설정합니다.
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    
    print(correlation_matrix)

if __name__ == '__main__':
    project_root = '/Users/jinhochoi/Desktop/개발/Market_insights'
    analyze_correlation(project_root)
