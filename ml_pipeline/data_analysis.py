#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML 파이프라인 Step 1: 데이터 탐색 및 분석 (EDA)
이해하기 쉬운 ML 학습용 스크립트
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from core.analyzer_v2 import SQLiteMarketAnalyzer

def analyze_current_data():
    """
    Step 1: 현재 데이터 탐색하기

    EDA (Exploratory Data Analysis)란?
    - 데이터의 구조와 특성을 이해하는 과정
    - 데이터에서 패턴, 이상치, 결측값 등을 찾아내는 작업
    - ML 모델을 만들기 전 반드시 거쳐야 하는 단계
    """
    print("🔍 Step 1: 데이터 탐색 및 분석 (EDA)")
    print("=" * 50)

    # 데이터 로딩 (생성된 CSV 파일에서 직접)
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'naver_products_cleaned_for_ml.csv')
    try:
        df = pd.read_csv(data_path)
    except FileNotFoundError:
        print(f"❌ 데이터 파일({data_path})을 찾을 수 없습니다!")
        print("💡 먼저 scripts/08_generate_naver_dataset.py를 실행하여 데이터셋을 생성해주세요.")
        return None

    # 컬럼 이름 통일 (기존 분석 코드와 호환성 맞추기)
    column_rename_map = {
        'product_title': 'title',
        'discounted_price': 'price',
        'product_rating': 'rating',
        'total_reviews': 'review_count',
        'product_category': 'category'
    }
    df.rename(columns=column_rename_map, inplace=True)

    print(f"📊 총 데이터 개수: {len(df)}개")
    print(f"📋 컬럼(특성): {list(df.columns)}")
    print()

    # 1. 기본 정보 확인
    print("1️⃣ 데이터 기본 정보:")
    df.info()
    print()

    # 2. 수치형 데이터 통계
    print("2️⃣ 수치형 데이터 요약 통계:")
    numeric_columns = ['price', 'rating', 'review_count']
    if all(col in df.columns for col in numeric_columns):
        print(df[numeric_columns].describe())
    print()

    # 3. 카테고리별 분석
    print("3️⃣ 검색 키워드별 상품 분포:")
    if 'search_keyword' in df.columns:
        category_counts = df['search_keyword'].value_counts()
        print(category_counts)
        print()

        # 카테고리별 평균 가격
        print("4️⃣ 검색 키워드별 평균 가격:")
        if 'price' in df.columns:
            avg_price_by_category = df.groupby('search_keyword')['price'].agg(['mean', 'std', 'count'])
            print(avg_price_by_category.round(2))

    # 4. 결측값 확인
    print("\n5️⃣ 결측값(누락된 데이터) 확인:")
    missing_data = df.isnull().sum()
    print(missing_data[missing_data > 0])
    if missing_data.sum() == 0:
        print("✅ 결측값이 없습니다!")

    # 5. 가격대별 분석
    if 'price' in df.columns:
        print("\n6️⃣ 가격대별 분석:")
        # 가격대 구간 나누기
        df['price_range'] = pd.cut(df['price'],
                                  bins=[0, 10, 30, 60, 100, float('inf')],
                                  labels=['$0-10', '$10-30', '$30-60', '$60-100', '$100+'])
        print(df['price_range'].value_counts().sort_index())

    return df


def create_ml_features(df):
    """
    Step 2: 특성 엔지니어링 (Feature Engineering)

    특성 엔지니어링이란?
    - 원본 데이터에서 ML 모델이 더 잘 학습할 수 있는 새로운 특성을 만드는 과정
    - 예: 가격 → 가격대, 리뷰수 → 인기도 등
    """
    print("\n🛠️ Step 2: 특성 엔지니어링")
    print("=" * 50)

    # 1. 인기도 지수 만들기 (리뷰 수와 평점 조합)
    if 'review_count' in df.columns and 'rating' in df.columns:
        # 로그 변환으로 리뷰 수의 스케일 조정
        df['log_review_count'] = np.log1p(df['review_count'])  # log1p = log(1+x)

        # 인기도 지수 = 평점 × log(리뷰수+1)
        df['popularity_score'] = df['rating'] * df['log_review_count']
        print("✅ 인기도 지수 생성 완료")

    # 2. 가격 대비 품질 지수
    if 'price' in df.columns and 'rating' in df.columns:
        # 가격당 평점 (높을수록 가성비 좋음)
        df['quality_per_dollar'] = df['rating'] / (df['price'] + 1)  # +1로 0 나눗셈 방지
        print("✅ 가격 대비 품질 지수 생성 완료")

    # 3. 카테고리 인코딩 (문자를 숫자로 변환)
    if 'category' in df.columns:
        # 원-핫 인코딩: 각 카테고리를 별도 컬럼으로 만들기
        category_dummies = pd.get_dummies(df['category'], prefix='category')
        df = pd.concat([df, category_dummies], axis=1)
        print("✅ 카테고리 원-핫 인코딩 완료")

    # 4. 제목 길이 특성
    if 'title' in df.columns:
        df['title_length'] = df['title'].str.len()
        print("✅ 제목 길이 특성 생성 완료")

    print(f"\n📈 새로운 특성 포함 총 컬럼 수: {len(df.columns)}개")

    return df

def ml_ready_analysis(df):
    """
    Step 3: ML 모델링 준비

    ML 모델링이란?
    - 데이터의 패턴을 학습해서 예측이나 분류를 수행하는 과정
    - 우리의 목표: 상품의 특성(가격, 카테고리 등)으로 인기도나 성공도 예측
    """
    print("\n🤖 Step 3: ML 모델링 준비")
    print("=" * 50)

    # 1. 타겟 변수 설정 (예측하고 싶은 것)
    target_options = []

    if 'popularity_score' in df.columns:
        target_options.append('popularity_score (인기도)')
    if 'rating' in df.columns:
        target_options.append('rating (평점)')
    if 'price' in df.columns:
        target_options.append('price (가격)')

    print("🎯 예측 가능한 타겟 변수들:")
    for i, option in enumerate(target_options, 1):
        print(f"   {i}. {option}")

    # 2. 특성 변수 준비 (예측에 사용할 입력값들)
    numeric_features = df.select_dtypes(include=[np.number]).columns.tolist()

    # 타겟이 될 수 있는 변수들 제외
    exclude_columns = ['id', 'title', 'url', 'asin', 'image_url', 'category', 'price_range']
    feature_columns = [col for col in numeric_features if col not in exclude_columns]

    print(f"\n📊 ML 특성 변수 ({len(feature_columns)}개):")
    for feature in feature_columns[:10]:  # 처음 10개만 출력
        print(f"   - {feature}")
    if len(feature_columns) > 10:
        print(f"   ... 외 {len(feature_columns) - 10}개")

    # 3. 상관관계 분석 (변수들 간의 관계)
    print("\n🔗 주요 변수 간 상관관계:")
    if len(feature_columns) >= 2:
        key_features = ['price', 'rating', 'review_count', 'popularity_score', 'quality_per_dollar']
        available_features = [f for f in key_features if f in df.columns]

        if len(available_features) >= 2:
            correlation_matrix = df[available_features].corr()
            print(correlation_matrix.round(3))

            print("\n💡 상관관계 해석:")
            print("   1.0에 가까우면: 강한 양의 상관관계 (함께 증가)")
            print("  -1.0에 가까우면: 강한 음의 상관관계 (반대로 변화)")
            print("   0에 가까우면: 상관관계 없음")

    return feature_columns

def main():
    """메인 실행 함수"""
    print("🚀 Market Insights ML 파이프라인 시작!")
    print("🎓 ML 학습용 - 단계별 상세 설명 포함")
    print("=" * 60)

    # Step 1: 데이터 탐색
    df = analyze_current_data()
    if df is None:
        return

    # Step 2: 특성 엔지니어링
    df_enhanced = create_ml_features(df)

    # Step 3: ML 준비
    feature_columns = ml_ready_analysis(df_enhanced)

    print("\n✅ 데이터 분석 완료!")
    print("📝 다음 단계: ML 모델 구축 및 훈련")
    print("🎯 목표: 상품 성공도 예측 모델 만들기")

    return df_enhanced, feature_columns

if __name__ == "__main__":
    df, features = main()