# -*- coding: utf-8 -*-
"""
이 스크립트는 Amazon 상품 데이터셋을 분석에 적합한 형태로 전처리합니다.
주요 작업은 다음과 같습니다:
1. 데이터 로드
2. 결측치(Missing Value) 처리
3. 데이터 타입 변환
4. 불필요한 데이터 제거
5. 처리된 데이터 저장

이 스크립트를 실행하면 'data/amazon_products_sales_data_cleaned.csv' 파일의 내용이
전처리된 버전으로 덮어쓰기됩니다.
"""
import pandas as pd
import numpy as np
import os

def preprocess_data(base_dir):
    """
    데이터셋을 전처리하고 정제된 파일을 저장하는 메인 함수.
    """
    # --- 1. 데이터 로드 ---
    # 프로젝트 루트 디렉토리를 기준으로 파일 경로를 설정합니다.
    file_path = os.path.join(base_dir, 'data', 'amazon_products_sales_data_cleaned.csv')
    
    print(f"데이터를 로드합니다: {file_path}")
    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print(f"오류: 파일을 찾을 수 없습니다. 경로를 확인하세요: {file_path}")
        return

    print("\n초기 데이터 정보:")
    df.info()
    print("-" * 50)

    # --- 2. 결측치 처리 ---
    print("결측치를 처리합니다...")
    # 'buy_box_availability': NaN이 아니면(즉, 'Add to cart' 같은 값이 있으면) True, NaN이면 False로 변환합니다.
    df['buy_box_availability'] = df['buy_box_availability'].notna()
    
    # 'purchased_last_month', 'product_rating', 'total_reviews': 정보가 없는 경우 0으로 채웁니다.
    df['purchased_last_month'].fillna(0, inplace=True)
    df['product_rating'].fillna(0, inplace=True)
    df['total_reviews'].fillna(0, inplace=True)
    
    # 'sustainability_tags': 태그가 없는 경우를 'None'이라는 문자열로 명시적으로 표시합니다.
    df['sustainability_tags'].fillna('None', inplace=True)
    print("결측치 처리 완료.")
    print("-" * 50)

    # --- 3. 데이터 타입 변환 ---
    print("데이터 타입을 변환합니다...")
    # 'has_coupon': 'No Coupon'이 아니면 True로 설정하여 boolean 타입으로 만듭니다.
    df['has_coupon'] = df['has_coupon'] != 'No Coupon'
    
    # 날짜 컬럼들을 datetime 객체로 변환합니다. 변환할 수 없는 값은 NaT(Not a Time)로 처리됩니다.
    df['delivery_date'] = pd.to_datetime(df['delivery_date'], errors='coerce')
    df['data_collected_at'] = pd.to_datetime(df['data_collected_at'], errors='coerce')
    
    # 정수형이어야 할 컬럼들을 int 타입으로 변환합니다.
    df['purchased_last_month'] = df['purchased_last_month'].astype(int)
    df['total_reviews'] = df['total_reviews'].astype(int)
    print("데이터 타입 변환 완료.")
    print("-" * 50)

    # --- 4. 불필요한 데이터 제거 ---
    print("불필요한 데이터를 제거합니다...")
    # 가격 정보는 핵심 분석 요소이므로, 가격 정보가 없는 행(row)은 제거합니다.
    initial_rows = len(df)
    df.dropna(subset=['discounted_price', 'original_price'], inplace=True)
    final_rows = len(df)
    print(f"가격 정보가 없는 {initial_rows - final_rows}개의 행을 제거했습니다.")
    print("-" * 50)

    # --- 5. 처리된 데이터 저장 ---
    # 동일한 파일 경로에 정제된 데이터프레임을 저장합니다. index=False는 CSV에 불필요한 인덱스 열이 생기는 것을 방지합니다.
    print(f"전처리된 데이터를 다시 저장합니다: {file_path}")
    df.to_csv(file_path, index=False)
    
    print("\n전처리 최종 완료! 처리 후 데이터 정보:")
    df.info()

if __name__ == '__main__':
    # 이 스크립트가 직접 실행될 때 프로젝트의 루트 디렉토리 경로를 지정합니다.
    project_root = '/Users/jinhochoi/Desktop/개발/Market_insights'
    preprocess_data(project_root)
