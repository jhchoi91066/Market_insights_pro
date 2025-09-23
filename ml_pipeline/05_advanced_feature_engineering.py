
import pandas as pd
import numpy as np
import os
import sys

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def perform_advanced_feature_engineering():
    """
    고급 피처 엔지니어링을 수행하고 새로운 데이터셋을 저장합니다.
    """
    print("🚀 고급 피처 엔지니어링 시작...")
    print("=" * 50)

    # 1. 데이터 로딩
    input_data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'naver_products_cleaned_for_ml.csv')
    output_data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'naver_products_featured_for_ml.csv')

    try:
        df = pd.read_csv(input_data_path)
        print(f"✅ 데이터 로딩 완료: {len(df)}개 행")
    except FileNotFoundError:
        print(f"❌ 입력 데이터 파일({input_data_path})을 찾을 수 없습니다!")
        print("💡 먼저 ml_pipeline/04_data_preprocessing.py를 실행하여 데이터셋을 생성해주세요.")
        return

    # 2. 상대 가격 지표 생성
    print("🔄 상대 가격 지표 생성 중...")
    # 카테고리별 평균 가격
    df['category_avg_price'] = df.groupby('category')['price'].transform('mean')
    df['price_to_category_avg_ratio'] = df['price'] / df['category_avg_price']

    # 검색 키워드별 평균 가격
    df['keyword_avg_price'] = df.groupby('search_keyword')['price'].transform('mean')
    df['price_to_keyword_avg_ratio'] = df['price'] / df['keyword_avg_price']

    print("✅ 상대 가격 지표 생성 완료")

    # 3. 상호작용 특성 생성
    print("🔄 상호작용 특성 생성 중...")
    # 가격과 평점의 상호작용
    df['price_x_rating'] = df['price'] * df['rating']
    # 평점과 리뷰 수의 상호작용
    df['rating_x_review_count'] = df['rating'] * df['review_count']
    # 가격과 리뷰 수의 상호작용
    df['price_x_review_count'] = df['price'] * df['review_count']

    print("✅ 상호작용 특성 생성 완료")

    # 4. 정제된 데이터 저장
    print(f"\n💾 새로운 특성이 추가된 데이터를 '{output_data_path}' 파일로 저장 중...")
    try:
        df.to_csv(output_data_path, index=False, encoding='utf-8-sig')
        print(f"\n✨ 성공! 고급 피처 엔지니어링이 완료되었습니다. 총 {len(df)}개 행.")
    except Exception as e:
        print(f"❌ 파일 저장 중 오류 발생: {e}")

if __name__ == "__main__":
    perform_advanced_feature_engineering()
