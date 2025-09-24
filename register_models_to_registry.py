"""
기존에 훈련된 모델들을 MLflow 모델 레지스트리에 등록하고 Production 스테이지로 승격
"""
import os
import mlflow
import mlflow.sklearn
import mlflow.pyfunc
import joblib
import pickle
from mlflow.tracking import MlflowClient
from datetime import datetime

def register_local_models_to_mlflow():
    """로컬에 저장된 모델들을 MLflow 레지스트리에 등록"""

    # MLflow 설정
    mlflow.set_tracking_uri("file:///Users/jinhochoi/Desktop/개발/Market_insights/mlruns")
    client = MlflowClient()

    models_path = "/Users/jinhochoi/Desktop/개발/Market_insights/ml_pipeline/models"

    print("🚀 모델 레지스트리 등록 시작...")

    # 1. 가격 예측 모델 등록
    print("\n1️⃣ 가격 예측 모델 등록 중...")
    try:
        price_model_file = f"{models_path}/price_predictor_mlflow_20250924_214606.joblib"

        if os.path.exists(price_model_file):
            # 새 실험 생성 또는 기존 실험 사용
            experiment_name = "price_prediction_registry"
            try:
                experiment_id = client.create_experiment(experiment_name)
            except:
                experiment_id = client.get_experiment_by_name(experiment_name).experiment_id

            mlflow.set_experiment(experiment_name)

            with mlflow.start_run(experiment_id=experiment_id):
                # 모델 로드
                model = joblib.load(price_model_file)

                # 메트릭 로깅 (이전 결과 기반)
                mlflow.log_metric("mae", 1.33)
                mlflow.log_metric("r2_score", 1.0)
                mlflow.log_metric("rmse", 1.33)

                # 모델 로깅 및 등록
                mlflow.sklearn.log_model(
                    sk_model=model,
                    artifact_path="model",
                    registered_model_name="price_predictor"
                )

                print(f"✅ 가격 예측 모델 등록 완료!")
        else:
            print(f"❌ 가격 예측 모델 파일을 찾을 수 없습니다: {price_model_file}")

    except Exception as e:
        print(f"❌ 가격 예측 모델 등록 실패: {e}")

    # 2. 수요 예측 모델 등록
    print("\n2️⃣ 수요 예측 모델 등록 중...")
    try:
        demand_model_file = f"{models_path}/demand_forecaster_mlflow_20250924_214648.pkl"

        if os.path.exists(demand_model_file):
            # 새 실험 생성 또는 기존 실험 사용
            experiment_name = "demand_forecasting_registry"
            try:
                experiment_id = client.create_experiment(experiment_name)
            except:
                experiment_id = client.get_experiment_by_name(experiment_name).experiment_id

            mlflow.set_experiment(experiment_name)

            with mlflow.start_run(experiment_id=experiment_id):
                # 모델 로드
                with open(demand_model_file, 'rb') as f:
                    model = pickle.load(f)

                # 메트릭 로깅 (이전 결과 기반)
                mlflow.log_metric("mape", 14.74)
                mlflow.log_metric("rmse", 10.2)

                # Prophet 모델을 pyfunc으로 등록 (scikit-learn이 아니므로)
                mlflow.pyfunc.log_model(
                    artifact_path="model",
                    python_model=model,
                    registered_model_name="demand_forecaster"
                )

                print(f"✅ 수요 예측 모델 등록 완료!")
        else:
            print(f"❌ 수요 예측 모델 파일을 찾을 수 없습니다: {demand_model_file}")

    except Exception as e:
        print(f"❌ 수요 예측 모델 등록 실패: {e}")

    # 3. 모델들을 Production 스테이지로 승격
    print("\n3️⃣ 모델들을 Production 스테이지로 승격...")

    models_to_promote = ["price_predictor", "demand_forecaster"]

    for model_name in models_to_promote:
        try:
            # 최신 버전 가져오기
            latest_versions = client.get_latest_versions(model_name, stages=["None"])

            if latest_versions:
                latest_version = latest_versions[0]

                # Production으로 승격
                client.transition_model_version_stage(
                    name=model_name,
                    version=latest_version.version,
                    stage="Production"
                )

                print(f"✅ {model_name} v{latest_version.version} → Production 스테이지 승격 완료!")
            else:
                print(f"⚠️ {model_name} 모델의 버전을 찾을 수 없습니다.")

        except Exception as e:
            print(f"❌ {model_name} 승격 실패: {e}")

    # 4. 최종 확인
    print("\n4️⃣ 등록 결과 확인...")
    try:
        registered_models = client.search_registered_models()

        if registered_models:
            for rm in registered_models:
                print(f"\n📦 모델명: {rm.name}")
                versions = client.get_latest_versions(rm.name)
                for version in versions:
                    print(f"   버전 {version.version} - 스테이지: {version.current_stage}")
        else:
            print("❌ 등록된 모델이 없습니다.")

    except Exception as e:
        print(f"❌ 모델 확인 실패: {e}")

if __name__ == "__main__":
    register_local_models_to_mlflow()