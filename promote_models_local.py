"""
로컬 MLflow에서 모델을 Production 스테이지로 승격
"""
import mlflow
import os

def promote_models_to_production():
    """로컬 MLflow에서 훈련된 모델들을 Production 스테이지로 승격"""

    # 로컬 MLflow tracking URI 설정
    mlflow.set_tracking_uri("file:///Users/jinhochoi/Desktop/개발/Market_insights/mlruns")

    print("🚀 로컬 MLflow에서 모델 Production 스테이지 승격 시작...")

    # 모델 정보
    models_info = [
        {"name": "price_predictor", "version": 2, "run_id": None},
        {"name": "demand_forecaster", "version": 1, "run_id": None}
    ]

    try:
        from mlflow.tracking import MlflowClient
        client = MlflowClient()

        # 등록된 모델 목록 확인
        print("\n📋 등록된 모델 목록:")
        registered_models = client.search_registered_models()

        for rm in registered_models:
            print(f"모델명: {rm.name}")
            latest_versions = client.get_latest_versions(rm.name)
            for version in latest_versions:
                print(f"  버전 {version.version} - 스테이지: {version.current_stage}")

                # Production으로 승격할 모델 찾기
                for model_info in models_info:
                    if rm.name == model_info["name"] and int(version.version) == model_info["version"]:
                        print(f"  ⬆️ {rm.name} v{version.version}을 Production으로 승격...")

                        try:
                            client.transition_model_version_stage(
                                name=rm.name,
                                version=version.version,
                                stage="Production"
                            )
                            print(f"  ✅ {rm.name} v{version.version} Production 승격 완료!")
                        except Exception as e:
                            print(f"  ❌ 승격 실패: {e}")

        print("\n🔍 승격 후 모델 상태 확인:")
        registered_models = client.search_registered_models()

        for rm in registered_models:
            print(f"모델명: {rm.name}")
            latest_versions = client.get_latest_versions(rm.name)
            for version in latest_versions:
                print(f"  버전 {version.version} - 스테이지: {version.current_stage}")

        # Production 스테이지 모델만 확인
        print("\n🎯 Production 스테이지 모델:")
        for model_info in models_info:
            try:
                production_versions = client.get_latest_versions(
                    model_info["name"],
                    stages=["Production"]
                )

                if production_versions:
                    for version in production_versions:
                        print(f"✅ {model_info['name']}: 버전 {version.version} (Production)")
                else:
                    print(f"⚠️ {model_info['name']}: Production 스테이지에 모델 없음")
            except Exception as e:
                print(f"❌ {model_info['name']} 확인 실패: {e}")

    except Exception as e:
        print(f"❌ MLflow 클라이언트 오류: {e}")

        # 대안: 직접 파일 시스템 확인
        print("\n🔧 파일 시스템에서 직접 확인...")

        mlruns_path = "/Users/jinhochoi/Desktop/개발/Market_insights/mlruns"
        if os.path.exists(mlruns_path):
            for item in os.listdir(mlruns_path):
                experiment_path = os.path.join(mlruns_path, item)
                if os.path.isdir(experiment_path) and item.isdigit():
                    print(f"실험 ID: {item}")

                    for run_id in os.listdir(experiment_path):
                        run_path = os.path.join(experiment_path, run_id)
                        if os.path.isdir(run_path) and run_id != ".trash":
                            artifacts_path = os.path.join(run_path, "artifacts")
                            if os.path.exists(artifacts_path):
                                print(f"  런 ID: {run_id}")
                                for artifact in os.listdir(artifacts_path):
                                    print(f"    아티팩트: {artifact}")

if __name__ == "__main__":
    promote_models_to_production()