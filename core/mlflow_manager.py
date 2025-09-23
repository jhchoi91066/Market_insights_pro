# -*- coding: utf-8 -*-
"""
MLflow 관리 시스템
Market Insights Pro의 ML 모델 실험 추적, 버전 관리, 배포를 담당합니다.
"""

import os
import yaml
import mlflow
import mlflow.sklearn
import mlflow.xgboost
from mlflow.tracking import MlflowClient
from mlflow.models.signature import infer_signature
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
import logging
from datetime import datetime
import joblib

logger = logging.getLogger(__name__)


class MLflowManager:
    """
    MLflow 실험 추적 및 모델 관리를 담당하는 클래스
    """

    def __init__(self, config_path: str = "mlflow_config.yaml"):
        """
        MLflow 매니저 초기화

        Args:
            config_path: MLflow 설정 파일 경로
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.client = None
        self._setup_mlflow()

    def _load_config(self) -> Dict[str, Any]:
        """설정 파일 로드"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"✅ MLflow 설정 파일 로드 완료: {self.config_path}")
            return config
        except FileNotFoundError:
            logger.error(f"❌ MLflow 설정 파일을 찾을 수 없습니다: {self.config_path}")
            # 기본 설정 반환
            return {
                "tracking_server": {
                    "backend_store_uri": "sqlite:///data/mlflow.db",
                    "default_artifact_root": "./data/mlruns"
                }
            }

    def _setup_mlflow(self):
        """MLflow 서버 설정"""
        # 추적 URI 설정
        tracking_uri = self.config["tracking_server"]["backend_store_uri"]
        mlflow.set_tracking_uri(tracking_uri)

        # 기본 아티팩트 저장소 설정
        artifact_root = self.config["tracking_server"]["default_artifact_root"]
        os.makedirs(artifact_root, exist_ok=True)
        os.makedirs("data", exist_ok=True)

        # MLflow 클라이언트 초기화
        self.client = MlflowClient()

        # 자동 로깅 설정
        if self.config.get("auto_logging", {}).get("sklearn", False):
            mlflow.sklearn.autolog()
        if self.config.get("auto_logging", {}).get("xgboost", False):
            mlflow.xgboost.autolog()

        logger.info("✅ MLflow 설정 완료")

    def create_experiment(self, experiment_name: str, description: str = "", tags: Dict[str, str] = None) -> str:
        """
        새 실험 생성

        Args:
            experiment_name: 실험 이름
            description: 실험 설명
            tags: 실험 태그

        Returns:
            experiment_id: 생성된 실험 ID
        """
        try:
            # 실험이 이미 존재하는지 확인
            existing_exp = mlflow.get_experiment_by_name(experiment_name)
            if existing_exp:
                logger.info(f"🔄 기존 실험 사용: {experiment_name}")
                return existing_exp.experiment_id

            # 새 실험 생성
            experiment_id = mlflow.create_experiment(
                name=experiment_name,
                tags=tags or {}
            )

            logger.info(f"✅ 새 실험 생성: {experiment_name} (ID: {experiment_id})")
            return experiment_id

        except Exception as e:
            logger.error(f"❌ 실험 생성 실패: {e}")
            raise

    def start_run(self, experiment_name: str, run_name: str = None, tags: Dict[str, str] = None):
        """
        MLflow 실행 시작

        Args:
            experiment_name: 실험 이름
            run_name: 실행 이름
            tags: 실행 태그
        """
        # 실험 설정
        mlflow.set_experiment(experiment_name)

        # 실행 시작
        return mlflow.start_run(
            run_name=run_name or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            tags=tags or {}
        )

    def log_model_metrics(self, model, X_test: pd.DataFrame, y_test: pd.Series,
                         model_type: str = "regression") -> Dict[str, float]:
        """
        모델 성능 메트릭 로그

        Args:
            model: 학습된 모델
            X_test: 테스트 특성
            y_test: 테스트 라벨
            model_type: 모델 타입 ('regression', 'classification')

        Returns:
            metrics: 계산된 메트릭 딕셔너리
        """
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

        # 예측
        y_pred = model.predict(X_test)

        metrics = {}

        if model_type == "regression":
            # 회귀 메트릭
            metrics["mae"] = mean_absolute_error(y_test, y_pred)
            metrics["rmse"] = np.sqrt(mean_squared_error(y_test, y_pred))
            metrics["r2_score"] = r2_score(y_test, y_pred)

        elif model_type == "classification":
            # 분류 메트릭 (향후 확장)
            from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
            metrics["accuracy"] = accuracy_score(y_test, y_pred)
            metrics["precision"] = precision_score(y_test, y_pred, average='weighted')
            metrics["recall"] = recall_score(y_test, y_pred, average='weighted')
            metrics["f1_score"] = f1_score(y_test, y_pred, average='weighted')

        # MLflow에 메트릭 로깅
        for metric_name, metric_value in metrics.items():
            mlflow.log_metric(metric_name, metric_value)

        logger.info(f"📊 모델 메트릭 로깅 완료: {metrics}")
        return metrics

    def save_model(self, model, model_name: str, X_sample: pd.DataFrame,
                   model_type: str = "sklearn", signature_input: pd.DataFrame = None):
        """
        모델을 MLflow에 저장

        Args:
            model: 저장할 모델
            model_name: 모델 이름
            X_sample: 서명 생성용 샘플 데이터
            model_type: 모델 타입 ('sklearn', 'xgboost')
            signature_input: 모델 서명용 입력 데이터
        """
        try:
            # 모델 서명 생성
            if signature_input is not None:
                signature = infer_signature(signature_input, model.predict(signature_input))
            else:
                signature = infer_signature(X_sample, model.predict(X_sample))

            # 모델 저장
            if model_type == "sklearn":
                mlflow.sklearn.log_model(
                    sk_model=model,
                    artifact_path=model_name,
                    signature=signature,
                    registered_model_name=model_name
                )
            elif model_type == "xgboost":
                mlflow.xgboost.log_model(
                    xgb_model=model,
                    artifact_path=model_name,
                    signature=signature,
                    registered_model_name=model_name
                )

            logger.info(f"✅ 모델 저장 완료: {model_name}")

        except Exception as e:
            logger.error(f"❌ 모델 저장 실패: {e}")
            raise

    def load_model(self, model_name: str, version: str = "latest", stage: str = None):
        """
        저장된 모델 로드

        Args:
            model_name: 모델 이름
            version: 모델 버전 ("latest" 또는 버전 번호)
            stage: 모델 스테이지 ("Production", "Staging" 등)

        Returns:
            model: 로드된 모델
        """
        try:
            if stage:
                # 스테이지별 모델 로드
                model_uri = f"models:/{model_name}/{stage}"
            elif version == "latest":
                # 최신 버전 로드
                latest_version = self.client.get_latest_versions(model_name, stages=["None"])[0]
                model_uri = f"models:/{model_name}/{latest_version.version}"
            else:
                # 특정 버전 로드
                model_uri = f"models:/{model_name}/{version}"

            model = mlflow.sklearn.load_model(model_uri)
            logger.info(f"✅ 모델 로드 완료: {model_name} (URI: {model_uri})")
            return model

        except Exception as e:
            logger.error(f"❌ 모델 로드 실패: {e}")
            raise

    def promote_model_to_production(self, model_name: str, version: str):
        """
        모델을 프로덕션 스테이지로 승격

        Args:
            model_name: 모델 이름
            version: 승격할 모델 버전
        """
        try:
            # 기존 프로덕션 모델을 Archived로 이동
            current_prod_models = self.client.get_latest_versions(model_name, stages=["Production"])
            for model in current_prod_models:
                self.client.transition_model_version_stage(
                    name=model_name,
                    version=model.version,
                    stage="Archived"
                )

            # 새 모델을 프로덕션으로 승격
            self.client.transition_model_version_stage(
                name=model_name,
                version=version,
                stage="Production"
            )

            logger.info(f"✅ 모델 프로덕션 승격 완료: {model_name} v{version}")

        except Exception as e:
            logger.error(f"❌ 모델 승격 실패: {e}")
            raise

    def get_model_performance_history(self, model_name: str) -> pd.DataFrame:
        """
        모델 성능 히스토리 조회

        Args:
            model_name: 모델 이름

        Returns:
            performance_df: 성능 히스토리 데이터프레임
        """
        try:
            # 실험 검색
            experiment = mlflow.get_experiment_by_name(model_name)
            if not experiment:
                logger.warning(f"⚠️ 실험을 찾을 수 없습니다: {model_name}")
                return pd.DataFrame()

            # 실행 검색
            runs = mlflow.search_runs(
                experiment_ids=[experiment.experiment_id],
                order_by=["start_time DESC"]
            )

            if runs.empty:
                logger.warning(f"⚠️ 실행 기록이 없습니다: {model_name}")
                return pd.DataFrame()

            # 성능 메트릭 추출
            performance_cols = ["run_id", "start_time", "status"]
            metric_cols = [col for col in runs.columns if col.startswith("metrics.")]
            performance_df = runs[performance_cols + metric_cols].copy()

            logger.info(f"📈 성능 히스토리 조회 완료: {model_name} ({len(performance_df)}개 실행)")
            return performance_df

        except Exception as e:
            logger.error(f"❌ 성능 히스토리 조회 실패: {e}")
            return pd.DataFrame()

    def check_model_performance_degradation(self, model_name: str, current_metrics: Dict[str, float]) -> bool:
        """
        모델 성능 저하 확인

        Args:
            model_name: 모델 이름
            current_metrics: 현재 성능 메트릭

        Returns:
            is_degraded: 성능 저하 여부
        """
        try:
            # 설정에서 임계값 가져오기
            thresholds = self.config.get("performance_thresholds", {}).get(model_name, {})
            degradation_threshold = self.config.get("retraining_triggers", {}).get("performance_degradation_threshold", 0.15)

            # 성능 히스토리 조회
            history_df = self.get_model_performance_history(model_name)
            if history_df.empty:
                return False

            # 최근 성능과 비교
            recent_runs = history_df.head(5)  # 최근 5개 실행

            is_degraded = False
            for metric_name, current_value in current_metrics.items():
                metric_col = f"metrics.{metric_name}"
                if metric_col in recent_runs.columns:
                    recent_avg = recent_runs[metric_col].mean()

                    # 성능 저하 확인 (낮을수록 좋은 메트릭: MAE, RMSE)
                    if metric_name in ["mae", "rmse", "mape"]:
                        if current_value > recent_avg * (1 + degradation_threshold):
                            logger.warning(f"⚠️ 성능 저하 감지: {metric_name} {recent_avg:.3f} → {current_value:.3f}")
                            is_degraded = True
                    # 성능 저하 확인 (높을수록 좋은 메트릭: R2, accuracy)
                    elif metric_name in ["r2_score", "accuracy", "precision", "recall", "f1_score"]:
                        if current_value < recent_avg * (1 - degradation_threshold):
                            logger.warning(f"⚠️ 성능 저하 감지: {metric_name} {recent_avg:.3f} → {current_value:.3f}")
                            is_degraded = True

            return is_degraded

        except Exception as e:
            logger.error(f"❌ 성능 저하 확인 실패: {e}")
            return False

    def start_mlflow_server(self, host: str = "0.0.0.0", port: int = 5000):
        """
        MLflow 서버 시작 (개발용)

        Args:
            host: 서버 호스트
            port: 서버 포트
        """
        tracking_uri = self.config["tracking_server"]["backend_store_uri"]
        artifact_root = self.config["tracking_server"]["default_artifact_root"]

        import subprocess

        cmd = [
            "mlflow", "server",
            "--backend-store-uri", tracking_uri,
            "--default-artifact-root", artifact_root,
            "--host", host,
            "--port", str(port)
        ]

        logger.info(f"🚀 MLflow 서버 시작: http://{host}:{port}")
        logger.info(f"📝 추적 URI: {tracking_uri}")
        logger.info(f"📁 아티팩트 경로: {artifact_root}")

        return subprocess.Popen(cmd)


# 전역 MLflow 매니저 인스턴스
_mlflow_manager = None

def get_mlflow_manager() -> MLflowManager:
    """
    MLflow 매니저 싱글톤 인스턴스 반환
    """
    global _mlflow_manager
    if _mlflow_manager is None:
        _mlflow_manager = MLflowManager()
    return _mlflow_manager


if __name__ == "__main__":
    # 테스트 코드
    print("🧪 MLflow Manager 테스트 시작...")

    manager = MLflowManager()

    # 실험 생성 테스트
    experiment_id = manager.create_experiment(
        "test_experiment",
        "테스트 실험",
        {"team": "market_insights", "test": "true"}
    )

    print(f"✅ 실험 생성 완료: {experiment_id}")
    print("🎉 MLflow Manager 테스트 완료!")