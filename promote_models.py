"""
MLflow 모델을 Production 스테이지로 승격
"""
import mlflow
from mlflow.tracking import MlflowClient

def promote_models_to_production():
    """훈련된 모델들을 Production 스테이지로 승격"""

    # MLflow 설정
    mlflow.set_tracking_uri("http://localhost:5000")
    client = MlflowClient()

    models_to_promote = [
        ("price_predictor", 2),  # XGBoost 가격 예측 모델 (버전 2)
        ("demand_forecaster", 1)  # Prophet 수요 예측 모델 (버전 1)
    ]

    print("🚀 모델 Production 스테이지 승격 시작...")

    for model_name, version in models_to_promote:
        try:
            # 현재 Production 스테이지의 모델이 있다면 Archived로 변경
            current_production_models = client.get_latest_versions(
                model_name,
                stages=["Production"]
            )

            for model in current_production_models:
                print(f"📦 기존 Production 모델 {model_name} v{model.version}를 Archived로 변경...")
                client.transition_model_version_stage(
                    name=model_name,
                    version=model.version,
                    stage="Archived"
                )

            # 새 모델을 Production으로 승격
            print(f"⬆️ {model_name} v{version}을 Production 스테이지로 승격...")
            client.transition_model_version_stage(
                name=model_name,
                version=version,
                stage="Production",
                archive_existing_versions=True
            )

            print(f"✅ {model_name} v{version} Production 승격 완료!")

        except Exception as e:
            print(f"❌ {model_name} v{version} 승격 실패: {e}")

    print("\n📊 현재 모델 상태 확인...")

    # 승격 결과 확인
    for model_name, _ in models_to_promote:
        try:
            production_models = client.get_latest_versions(
                model_name,
                stages=["Production"]
            )

            if production_models:
                for model in production_models:
                    print(f"🎯 {model_name}: 버전 {model.version} (Production)")
            else:
                print(f"⚠️ {model_name}: Production 스테이지에 모델 없음")

        except Exception as e:
            print(f"❌ {model_name} 상태 확인 실패: {e}")

if __name__ == "__main__":
    promote_models_to_production()