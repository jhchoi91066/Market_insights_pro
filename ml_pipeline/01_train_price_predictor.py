
import pandas as pd
import xgboost as xgb
import os
import sys
import joblib
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def train_price_prediction_model():
    """
    XGBoost를 사용하여 가격 예측 모델을 훈련하고 저장합니다.
    """
    print("🚀 Step 1: 데이터 준비 (Data Preparation)")
    print("=" * 50)

    # 1. 데이터 로딩
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'naver_products_featured_for_ml.csv')
    try:
        df = pd.read_csv(data_path)
        print(f"✅ 데이터 로딩 완료: {len(df)}개 행")
    except FileNotFoundError:
        print(f"❌ 데이터 파일({data_path})을 찾을 수 없습니다!")
        print("💡 먼저 ml_pipeline/05_advanced_feature_engineering.py를 실행하여 데이터셋을 생성해주세요.")
        return

    # 2. 기본적인 전처리
    # 불필요한 컬럼 제거 (전처리 스크립트에서 이미 제거된 컬럼 포함)
    cols_to_drop = [
        'product_id', 'product_url', 'scraped_at', 'image_url',
        'original_price_won', 'data_source',
        'category_avg_price', 'keyword_avg_price' # 피처 엔지니어링 과정에서 생성된 중간 컬럼
    ]
    df.drop(columns=cols_to_drop, inplace=True, errors='ignore')

    # naver_category 컬럼들을 category dtype으로 변환
    for col in ['naver_category1', 'naver_category2', 'naver_category3', 'naver_category4']:
        if col in df.columns:
            df[col] = df[col].astype('category')

    # 결측치 처리 (전처리 스크립트에서 이미 처리됨)
    # brand, maker, seller의 결측치는 'Unknown'으로 채움
    # 이 단계에서는 추가적인 결측치 처리가 필요 없음
    print("✅ 기본적인 전처리 및 결측치 처리 완료")

    print("\n🚀 Step 2: 특성과 타겟 분리 (Feature/Target Separation)")
    print("=" * 50)

    # 1. 타겟 변수 설정
    target = 'price'
    y = df[target]

    # 2. 특성 변수 설정 (예측에 사용하지 않을 title 컬럼 등 제외)
    features = df.drop(columns=[target, 'title'])

    # 3. 범주형 특성 원-핫 인코딩 (인코딩할 컬럼 명시)
    categorical_features = [
        'category', 'brand', 'seller', 'search_keyword', 'maker'
    ]
    # 일부 키워드에서는 maker가 없을 수도 있으므로, 존재하는 컬럼만 인코딩
    valid_categorical_features = [col for col in categorical_features if col in features.columns]

    features_encoded = pd.get_dummies(features, columns=valid_categorical_features, dummy_na=False)
    print(f"✅ 원-핫 인코딩 완료. 특성 수: {features_encoded.shape[1]}개")

    print("\n🚀 Step 3: 훈련/테스트 데이터 분리 (Train/Test Split)")
    print("=" * 50)

    X_train, X_test, y_train, y_test = train_test_split(
        features_encoded, y, test_size=0.2, random_state=42
    )
    print(f"✅ 데이터 분리 완료: 훈련용 {len(X_train)}개, 테스트용 {len(X_test)}개")

    print("\n🚀 Step 4: 모델 훈련 (Model Training)")
    print("=" * 50)

    # XGBoost 모델 초기화
    # n_estimators: 생성할 트리 개수, learning_rate: 학습률
    # max_depth: 트리의 최대 깊이, early_stopping_rounds: 조기 종료 조건
    model = xgb.XGBRegressor(
        objective='reg:squarederror',
        n_estimators=1000,
        learning_rate=0.05,
        max_depth=5,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        early_stopping_rounds=50,
        enable_categorical=True # 범주형 특성 자동 처리 활성화
    )

    print("🔥 XGBoost 모델 훈련 시작...")
    # 모델 훈련 (테스트셋의 성능을 모니터링하며 조기 종료)
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False
    )
    print("✅ 모델 훈련 완료!")

    print("\n🚀 Step 5: 모델 평가 및 저장 (Evaluation & Saving)")
    print("=" * 50)

    # 1. 예측 수행
    y_pred = model.predict(X_test)

    # 2. 성능 평가
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    print("📊 모델 성능 평가:")
    print(f"   - MAE (평균 절대 오차): ${mae:.2f}")
    print("     (모델이 예측한 가격과 실제 가격의 평균적인 차이)")
    print(f"   - R² (결정 계수): {r2:.2f}")
    print("     (모델이 데이터의 분산을 얼마나 잘 설명하는지, 1에 가까울수록 좋음)")

    # 3. 모델 저장
    output_dir = os.path.join(os.path.dirname(__file__), 'models')
    os.makedirs(output_dir, exist_ok=True)
    model_path = os.path.join(output_dir, "price_predictor_v1.joblib")
    
    joblib.dump(model, model_path)
    print(f"\n💾 모델 저장 완료: {model_path}")

    print("\n✨ 가격 예측 모델 훈련 파이프라인이 성공적으로 완료되었습니다.")

if __name__ == "__main__":
    train_price_prediction_model()
