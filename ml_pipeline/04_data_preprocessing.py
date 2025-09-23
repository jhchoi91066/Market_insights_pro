
import pandas as pd
import numpy as np
import os
import sys

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def preprocess_data():
    """
    ML 모델 훈련을 위한 데이터 전처리 (결측치, 이상치 처리 등)
    """
    print("🚀 데이터 전처리 파이프라인 시작...")
    print("=" * 50)

    # 1. 데이터 로딩
    input_data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'naver_products_for_ml.csv')
    output_data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'naver_products_cleaned_for_ml.csv')

    try:
        df = pd.read_csv(input_data_path)
        print(f"✅ 데이터 로딩 완료: {len(df)}개 행")
    except FileNotFoundError:
        print(f"❌ 입력 데이터 파일({input_data_path})을 찾을 수 없습니다!")
        print("💡 먼저 scripts/08_generate_naver_dataset.py를 실행하여 데이터셋을 생성해주세요.")
        return

    # 2. 컬럼 이름 통일 (기존 분석 코드와 호환성 맞추기)
    column_rename_map = {
        'product_title': 'title',
        'discounted_price': 'price',
        'product_rating': 'rating',
        'total_reviews': 'review_count',
        'product_category': 'category'
    }
    df.rename(columns=column_rename_map, inplace=True)
    print("✅ 컬럼 이름 통일 완료")

    # 3. 결측치 처리
    print("\n🔄 결측치 처리 중...")
    # 범주형 컬럼의 결측치는 'Unknown'으로 채움
    for col in ['brand', 'maker', 'seller']:
        if col in df.columns:
            df[col].fillna('Unknown', inplace=True)

    # 대부분 비어있는 컬럼 제거
    cols_to_drop_if_mostly_empty = ['asin', 'highest_price_won']
    df.drop(columns=cols_to_drop_if_mostly_empty, inplace=True, errors='ignore')
    print("✅ 결측치 처리 완료 (Unknown 채우기 및 불필요 컬럼 제거)")

    # 4. 이상치 탐지 및 처리 (IQR 방식)
    print("\n📊 이상치 탐지 및 처리 중...")
    numeric_cols_for_outlier = ['price', 'review_count', 'purchased_last_month']

    for col in numeric_cols_for_outlier:
        if col in df.columns:
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR

            # 이상치를 경계값으로 대체 (Capping)
            outliers_count = df[(df[col] < lower_bound) | (df[col] > upper_bound)].shape[0]
            if outliers_count > 0:
                df[col] = np.where(df[col] < lower_bound, lower_bound, df[col])
                df[col] = np.where(df[col] > upper_bound, upper_bound, df[col])
                print(f"   - 컬럼 '{col}': {outliers_count}개의 이상치 처리 (Capping)")
            else:
                print(f"   - 컬럼 '{col}': 이상치 없음")
        else:
            print(f"   - 컬럼 '{col}': 데이터에 존재하지 않음. 건너뜀.")
    print("✅ 이상치 처리 완료")

    # 5. 정제된 데이터 저장
    print(f"\n💾 정제된 데이터를 '{output_data_path}' 파일로 저장 중...")
    try:
        df.to_csv(output_data_path, index=False, encoding='utf-8-sig')
        print(f"\n✨ 성공! 정제된 데이터셋 생성이 완료되었습니다. 총 {len(df)}개 행.")
    except Exception as e:
        print(f"❌ 파일 저장 중 오류 발생: {e}")

if __name__ == "__main__":
    preprocess_data()
