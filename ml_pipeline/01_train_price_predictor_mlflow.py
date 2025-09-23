import pandas as pd
import xgboost as xgb
import os
import sys
import joblib
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
import mlflow
import mlflow.xgboost
import yaml

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# MLflow 매니저 임포트
from core.mlflow_manager import get_mlflow_manager

def train_price_prediction_model():
    """
    XGBoost를 사용하여 가격 예측 모델을 훈련하고 저장합니다.
    MLflow를 사용하여 실험을 추적하고 모델을 관리합니다.
    """
    print("🚀 MLflow 기반 가격 예측 모델 훈련 시작")
    print("=" * 60)

    # MLflow 매니저 초기화
    mlflow_manager = get_mlflow_manager()

    # 실험 생성 또는 기존 실험 사용
    experiment_name = "price_prediction"
    mlflow_manager.create_experiment(
        experiment_name=experiment_name,
        description="네이버 쇼핑 데이터 기반 가격 예측 모델 실험",
        tags={"team": "market_insights", "model_type": "regression", "algorithm": "xgboost"}
    )

    # MLflow 실행 시작
    run_name = f"price_prediction_run_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}"

    with mlflow_manager.start_run(experiment_name, run_name,
                                 tags={"version": "v1.0", "dataset": "naver_featured"}):

        print("\n🚀 Step 1: 데이터 준비 (Data Preparation)")
        print("=" * 50)

        # 1. 데이터 로딩
        data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'naver_products_featured_for_ml.csv')
        try:
            df = pd.read_csv(data_path)
            print(f"✅ 데이터 로딩 완료: {len(df)}개 행")

            # 데이터 정보 로깅
            mlflow.log_param("total_samples", len(df))
            mlflow.log_param("data_source", "naver_shopping_api")

        except FileNotFoundError:
            print(f"❌ 데이터 파일({data_path})을 찾을 수 없습니다!")
            print("💡 먼저 ml_pipeline/05_advanced_feature_engineering.py를 실행하여 데이터셋을 생성해주세요.")
            return

        # 2. 기본적인 전처리
        cols_to_drop = [
            'product_id', 'product_url', 'scraped_at', 'image_url',
            'original_price_won', 'data_source',
            'category_avg_price', 'keyword_avg_price'
        ]
        df.drop(columns=cols_to_drop, inplace=True, errors='ignore')

        # naver_category 컬럼들을 문자열로 변환 (원-핫 인코딩을 위해)
        for col in ['naver_category1', 'naver_category2', 'naver_category3', 'naver_category4']:
            if col in df.columns:
                df[col] = df[col].astype('str')

        print("✅ 기본적인 전처리 및 결측치 처리 완료")

        print("\n🚀 Step 2: 특성과 타겟 분리 (Feature/Target Separation)")
        print("=" * 50)

        # 1. 타겟 변수 설정 (price 컬럼)
        target = 'price'
        y = df[target]

        # 2. 특성 변수 설정 (예측에 사용하지 않을 title 컬럼 등 제외)
        features = df.drop(columns=[target, 'title'])

        # 3. 범주형 특성 원-핫 인코딩
        categorical_features = [
            'category', 'brand', 'seller', 'search_keyword', 'maker',
            'naver_category1', 'naver_category2', 'naver_category3', 'naver_category4'
        ]
        valid_categorical_features = [col for col in categorical_features if col in features.columns]

        features_encoded = pd.get_dummies(features, columns=valid_categorical_features, dummy_na=False)
        print(f"✅ 원-핫 인코딩 완료. 특성 수: {features_encoded.shape[1]}개")

        print("\n🚀 Step 3: 훈련/테스트 데이터 분리 (Train/Test Split)")
        print("=" * 50)

        X_train, X_test, y_train, y_test = train_test_split(
            features_encoded, y, test_size=0.2, random_state=42
        )
        print(f"✅ 데이터 분리 완료: 훈련용 {len(X_train)}개, 테스트용 {len(X_test)}개")

        # 데이터 분할 정보 로깅
        mlflow.log_param("training_samples", len(X_train))
        mlflow.log_param("test_samples", len(X_test))
        mlflow.log_param("num_features", X_train.shape[1])
        mlflow.log_param("test_size", 0.2)
        mlflow.log_param("random_state", 42)

        print("\n🚀 Step 4: 모델 훈련 (Model Training)")
        print("=" * 50)

        # XGBoost 모델 초기화 및 하이퍼파라미터 로깅
        model_params = {
            'objective': 'reg:squarederror',
            'n_estimators': 1000,
            'learning_rate': 0.05,
            'max_depth': 5,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'random_state': 42,
            'early_stopping_rounds': 50,
            'enable_categorical': False,  # 원-핫 인코딩을 사용하므로 비활성화
            'tree_method': 'hist'
        }

        # MLflow에 하이퍼파라미터 로깅
        mlflow.log_params(model_params)

        model = xgb.XGBRegressor(**model_params)

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

        # MLflow를 통한 모델 성능 메트릭 로깅
        metrics = mlflow_manager.log_model_metrics(model, X_test, y_test, model_type="regression")

        print("📊 모델 성능 평가:")
        print(f"   - MAE (평균 절대 오차): ${metrics['mae']:.2f}")
        print("     (모델이 예측한 가격과 실제 가격의 평균적인 차이)")
        print(f"   - RMSE (평균 제곱근 오차): ${metrics['rmse']:.2f}")
        print("   - R² (결정 계수): {:.2f}".format(metrics['r2_score']))
        print("     (모델이 데이터의 분산을 얼마나 잘 설명하는지, 1에 가까울수록 좋음)")

        # MLflow에 모델 저장
        mlflow_manager.save_model(
            model=model,
            model_name="price_predictor",
            X_sample=X_test.head(5),
            model_type="xgboost"
        )

        # 로컬에도 백업 저장
        output_dir = os.path.join(os.path.dirname(__file__), 'models')
        os.makedirs(output_dir, exist_ok=True)
        model_path = os.path.join(output_dir, f"price_predictor_mlflow_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.joblib")

        joblib.dump(model, model_path)
        print(f"\n💾 로컬 백업 저장 완료: {model_path}")

        # 성능 임계값 확인
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mlflow_config.yaml")
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            thresholds = config.get("performance_thresholds", {}).get("price_prediction", {})
            mae_threshold = thresholds.get("mae_threshold", 50.0)
            r2_threshold = thresholds.get("r2_threshold", 0.8)

            print("\n🎯 성능 임계값 확인:")
            mae_pass = metrics['mae'] <= mae_threshold
            r2_pass = metrics['r2_score'] >= r2_threshold

            print(f"   - MAE: ${metrics['mae']:.2f} <= ${mae_threshold} {'✅' if mae_pass else '❌'}")
            print(f"   - R²: {metrics['r2_score']:.2f} >= {r2_threshold} {'✅' if r2_pass else '❌'}")

            if mae_pass and r2_pass:
                print("🎉 모든 성능 임계값을 통과했습니다!")
                mlflow.log_param("performance_check", "PASSED")

                # 성능이 좋으면 Production 후보로 등록
                print("🚀 Production 스테이지로 승격 가능한 모델입니다.")
                mlflow.log_param("promotion_eligible", "YES")

            else:
                print("⚠️  일부 성능 임계값에 미달했습니다.")
                mlflow.log_param("performance_check", "FAILED")
                mlflow.log_param("promotion_eligible", "NO")

        except Exception as e:
            print(f"⚠️  성능 임계값 확인 중 오류: {e}")

        print("\n✨ MLflow 기반 가격 예측 모델 훈련이 성공적으로 완료되었습니다.")
        print(f"📈 MLflow UI에서 실험 결과를 확인하세요: http://localhost:5000")

if __name__ == "__main__":
    train_price_prediction_model()