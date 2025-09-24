"""
훈련된 모델에서 특성 이름 추출
"""
import joblib
import pickle

def extract_model_features():
    """모델에서 feature names 추출"""

    # XGBoost 가격 예측 모델 로드
    price_model_path = "/Users/jinhochoi/Desktop/개발/Market_insights/ml_pipeline/models/price_predictor_mlflow_20250924_214606.joblib"

    print("🔍 XGBoost 가격 예측 모델 특성 분석...")
    try:
        model = joblib.load(price_model_path)
        print(f"모델 타입: {type(model)}")

        # XGBoost 모델의 feature names 확인
        if hasattr(model, 'feature_names_in_'):
            feature_names = model.feature_names_in_
            print(f"\n✅ 특성 개수: {len(feature_names)}개")
            print(f"첫 10개 특성: {list(feature_names[:10])}")
            print(f"마지막 10개 특성: {list(feature_names[-10:])}")

            # 특성을 파일로 저장
            with open('/Users/jinhochoi/Desktop/개발/Market_insights/model_features.txt', 'w', encoding='utf-8') as f:
                for i, feature in enumerate(feature_names):
                    f.write(f"{i}: {feature}\n")

            print(f"\n📁 모든 특성 이름이 'model_features.txt'에 저장되었습니다.")

            # 특성 타입별 분석
            categorical_features = {}
            for feature in feature_names:
                if '_' in feature:
                    prefix = feature.split('_')[0]
                    if prefix not in categorical_features:
                        categorical_features[prefix] = []
                    categorical_features[prefix].append(feature.split('_', 1)[1])

            print(f"\n📊 범주형 특성 분석:")
            for prefix, values in categorical_features.items():
                print(f"  {prefix}: {len(values)}개 값")
                if len(values) <= 10:
                    print(f"    값들: {values}")
                else:
                    print(f"    예시: {values[:5]}... (총 {len(values)}개)")

        else:
            print("❌ 모델에 feature_names_in_ 속성이 없습니다.")

    except Exception as e:
        print(f"❌ 모델 로드 실패: {e}")

    print("\n" + "="*60)

    # Prophet 수요 예측 모델도 확인
    demand_model_path = "/Users/jinhochoi/Desktop/개발/Market_insights/ml_pipeline/models/demand_forecaster_mlflow_20250924_214648.pkl"

    print("🔍 Prophet 수요 예측 모델 분석...")
    try:
        with open(demand_model_path, 'rb') as f:
            demand_model = pickle.load(f)
        print(f"모델 타입: {type(demand_model)}")
        print("✅ Prophet 모델 로드 성공")

    except Exception as e:
        print(f"❌ Prophet 모델 로드 실패: {e}")

if __name__ == "__main__":
    extract_model_features()