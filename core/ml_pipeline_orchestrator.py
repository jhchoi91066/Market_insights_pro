# -*- coding: utf-8 -*-
"""
ML 파이프라인 오케스트레이터
Market Insights Pro의 ML 모델 훈련/배포 파이프라인을 자동화합니다.
"""

import os
import sys
import subprocess
import yaml
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import pandas as pd
from dataclasses import dataclass
from enum import Enum

# MLflow 관련
from core.mlflow_manager import get_mlflow_manager

logger = logging.getLogger(__name__)


class PipelineStatus(Enum):
    """파이프라인 실행 상태"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelType(Enum):
    """지원하는 모델 타입"""
    PRICE_PREDICTOR = "price_predictor"
    DEMAND_FORECASTER = "demand_forecaster"
    OPPORTUNITY_RECOMMENDER = "opportunity_recommender"


@dataclass
class PipelineConfig:
    """파이프라인 설정"""
    model_type: ModelType
    script_path: str
    dependencies: List[str]
    performance_thresholds: Dict[str, float]
    auto_promote: bool = False
    schedule_interval: Optional[str] = None  # cron format


@dataclass
class PipelineRun:
    """파이프라인 실행 결과"""
    run_id: str
    model_type: ModelType
    status: PipelineStatus
    start_time: datetime
    end_time: Optional[datetime]
    metrics: Dict[str, float]
    artifacts: List[str]
    error_message: Optional[str] = None


class MLPipelineOrchestrator:
    """
    ML 파이프라인 오케스트레이터
    모델 훈련, 평가, 배포 프로세스를 자동화합니다.
    """

    def __init__(self, config_path: str = "mlflow_config.yaml"):
        """
        오케스트레이터 초기화

        Args:
            config_path: 설정 파일 경로
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.mlflow_manager = get_mlflow_manager()
        self.pipeline_configs = self._setup_pipeline_configs()
        self.active_runs: Dict[str, PipelineRun] = {}

    def _load_config(self) -> Dict[str, Any]:
        """설정 파일 로드"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"✅ 파이프라인 설정 로드 완료: {self.config_path}")
            return config
        except FileNotFoundError:
            logger.error(f"❌ 설정 파일을 찾을 수 없습니다: {self.config_path}")
            return {}

    def _setup_pipeline_configs(self) -> Dict[ModelType, PipelineConfig]:
        """파이프라인 설정 초기화"""
        ml_pipeline_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ml_pipeline")

        configs = {
            ModelType.PRICE_PREDICTOR: PipelineConfig(
                model_type=ModelType.PRICE_PREDICTOR,
                script_path=os.path.join(ml_pipeline_dir, "01_train_price_predictor_mlflow.py"),
                dependencies=["naver_products_featured_for_ml.csv"],
                performance_thresholds=self.config.get("performance_thresholds", {}).get("price_prediction", {}),
                auto_promote=True,
                schedule_interval="0 2 * * 1"  # 매주 월요일 2시
            ),
            ModelType.DEMAND_FORECASTER: PipelineConfig(
                model_type=ModelType.DEMAND_FORECASTER,
                script_path=os.path.join(ml_pipeline_dir, "02_train_demand_forecaster_mlflow.py"),
                dependencies=[],  # API 기반이므로 파일 의존성 없음
                performance_thresholds=self.config.get("performance_thresholds", {}).get("demand_forecasting", {}),
                auto_promote=True,
                schedule_interval="0 3 * * 1"  # 매주 월요일 3시
            ),
            ModelType.OPPORTUNITY_RECOMMENDER: PipelineConfig(
                model_type=ModelType.OPPORTUNITY_RECOMMENDER,
                script_path=os.path.join(ml_pipeline_dir, "03_build_opportunity_recommender.py"),
                dependencies=["naver_products_featured_for_ml.csv"],
                performance_thresholds=self.config.get("performance_thresholds", {}).get("recommendation", {}),
                auto_promote=False,
                schedule_interval="0 4 * * 1"  # 매주 월요일 4시
            )
        }

        return configs

    async def run_pipeline(self, model_type: ModelType, force: bool = False) -> PipelineRun:
        """
        특정 모델 타입의 파이프라인 실행

        Args:
            model_type: 실행할 모델 타입
            force: 강제 실행 여부

        Returns:
            PipelineRun: 파이프라인 실행 결과
        """
        config = self.pipeline_configs.get(model_type)
        if not config:
            raise ValueError(f"지원하지 않는 모델 타입: {model_type}")

        run_id = f"{model_type.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        logger.info(f"🚀 파이프라인 실행 시작: {model_type.value} (Run ID: {run_id})")

        # 파이프라인 실행 객체 생성
        pipeline_run = PipelineRun(
            run_id=run_id,
            model_type=model_type,
            status=PipelineStatus.RUNNING,
            start_time=datetime.now(),
            end_time=None,
            metrics={},
            artifacts=[]
        )

        self.active_runs[run_id] = pipeline_run

        try:
            # 1. 의존성 확인
            if not force and not self._check_dependencies(config):
                pipeline_run.status = PipelineStatus.FAILED
                pipeline_run.error_message = "의존성 확인 실패"
                return pipeline_run

            # 2. 스크립트 실행
            result = await self._execute_training_script(config)

            if result["success"]:
                # 3. 실험 결과 수집
                metrics = await self._collect_experiment_metrics(model_type)
                pipeline_run.metrics = metrics

                # 4. 성능 평가
                performance_check = self._evaluate_model_performance(config, metrics)

                # 5. 자동 승격 처리
                if config.auto_promote and performance_check:
                    await self._promote_model_to_production(model_type)

                pipeline_run.status = PipelineStatus.SUCCESS
                logger.info(f"✅ 파이프라인 완료: {model_type.value}")

            else:
                pipeline_run.status = PipelineStatus.FAILED
                pipeline_run.error_message = result.get("error", "알 수 없는 오류")
                logger.error(f"❌ 파이프라인 실패: {model_type.value}")

        except Exception as e:
            pipeline_run.status = PipelineStatus.FAILED
            pipeline_run.error_message = str(e)
            logger.error(f"❌ 파이프라인 예외 발생: {e}")

        finally:
            pipeline_run.end_time = datetime.now()

        return pipeline_run

    def _check_dependencies(self, config: PipelineConfig) -> bool:
        """파이프라인 의존성 확인"""
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

        for dependency in config.dependencies:
            dependency_path = os.path.join(data_dir, dependency)
            if not os.path.exists(dependency_path):
                logger.error(f"❌ 의존성 파일이 없습니다: {dependency_path}")
                return False

        logger.info("✅ 모든 의존성 확인 완료")
        return True

    async def _execute_training_script(self, config: PipelineConfig) -> Dict[str, Any]:
        """훈련 스크립트 실행"""
        try:
            logger.info(f"🔥 훈련 스크립트 실행: {config.script_path}")

            # 비동기로 스크립트 실행
            process = await asyncio.create_subprocess_exec(
                sys.executable, config.script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info("✅ 훈련 스크립트 실행 성공")
                return {"success": True, "stdout": stdout.decode(), "stderr": stderr.decode()}
            else:
                logger.error(f"❌ 훈련 스크립트 실행 실패: {stderr.decode()}")
                return {"success": False, "error": stderr.decode(), "stdout": stdout.decode()}

        except Exception as e:
            logger.error(f"❌ 스크립트 실행 중 예외 발생: {e}")
            return {"success": False, "error": str(e)}

    async def _collect_experiment_metrics(self, model_type: ModelType) -> Dict[str, float]:
        """실험 메트릭 수집"""
        try:
            # 최근 실험 결과에서 메트릭 수집
            experiment_name = self._get_experiment_name(model_type)
            performance_history = self.mlflow_manager.get_model_performance_history(experiment_name)

            if performance_history.empty:
                logger.warning(f"⚠️ 실험 결과를 찾을 수 없습니다: {experiment_name}")
                return {}

            # 최근 실행의 메트릭 추출
            latest_run = performance_history.iloc[0]
            metrics = {}

            for col in performance_history.columns:
                if col.startswith("metrics."):
                    metric_name = col.replace("metrics.", "")
                    metrics[metric_name] = latest_run[col]

            logger.info(f"📊 메트릭 수집 완료: {metrics}")
            return metrics

        except Exception as e:
            logger.error(f"❌ 메트릭 수집 실패: {e}")
            return {}

    def _get_experiment_name(self, model_type: ModelType) -> str:
        """모델 타입에 따른 실험 이름 반환"""
        mapping = {
            ModelType.PRICE_PREDICTOR: "price_prediction",
            ModelType.DEMAND_FORECASTER: "demand_forecasting",
            ModelType.OPPORTUNITY_RECOMMENDER: "opportunity_recommendation"
        }
        return mapping.get(model_type, model_type.value)

    def _evaluate_model_performance(self, config: PipelineConfig, metrics: Dict[str, float]) -> bool:
        """모델 성능 평가"""
        if not metrics or not config.performance_thresholds:
            logger.warning("⚠️ 성능 평가를 위한 메트릭 또는 임계값이 없습니다.")
            return False

        passed_checks = []

        for threshold_name, threshold_value in config.performance_thresholds.items():
            if threshold_name in metrics:
                metric_value = metrics[threshold_name]

                # 낮을수록 좋은 메트릭 (MAE, RMSE, MAPE)
                if threshold_name in ["mae_threshold", "rmse_threshold", "mape_threshold"]:
                    passed = metric_value <= threshold_value
                # 높을수록 좋은 메트릭 (R², accuracy, precision, recall)
                else:
                    passed = metric_value >= threshold_value

                passed_checks.append(passed)
                logger.info(f"🎯 {threshold_name}: {metric_value} {'✅' if passed else '❌'}")

        all_passed = all(passed_checks) if passed_checks else False
        logger.info(f"📈 전체 성능 평가: {'통과' if all_passed else '실패'}")

        return all_passed

    async def _promote_model_to_production(self, model_type: ModelType):
        """모델을 프로덕션 스테이지로 승격"""
        try:
            model_name = self._get_model_name(model_type)

            # 최신 모델 버전 찾기
            client = self.mlflow_manager.client
            latest_versions = client.get_latest_versions(model_name, stages=["None"])

            if latest_versions:
                latest_version = latest_versions[0].version
                self.mlflow_manager.promote_model_to_production(model_name, latest_version)
                logger.info(f"🚀 모델 프로덕션 승격 완료: {model_name} v{latest_version}")
            else:
                logger.warning(f"⚠️ 승격할 모델 버전을 찾을 수 없습니다: {model_name}")

        except Exception as e:
            logger.error(f"❌ 모델 승격 실패: {e}")

    def _get_model_name(self, model_type: ModelType) -> str:
        """모델 타입에 따른 모델 이름 반환"""
        mapping = {
            ModelType.PRICE_PREDICTOR: "price_predictor",
            ModelType.DEMAND_FORECASTER: "demand_forecaster",
            ModelType.OPPORTUNITY_RECOMMENDER: "opportunity_recommender"
        }
        return mapping.get(model_type, model_type.value)

    async def run_all_pipelines(self, force: bool = False) -> Dict[ModelType, PipelineRun]:
        """모든 파이프라인 실행"""
        logger.info("🚀 전체 파이프라인 실행 시작")

        results = {}

        # 순차적으로 실행 (병렬 실행도 가능하지만 리소스 고려)
        for model_type in ModelType:
            try:
                result = await self.run_pipeline(model_type, force)
                results[model_type] = result
            except Exception as e:
                logger.error(f"❌ {model_type.value} 파이프라인 실행 실패: {e}")

        logger.info("✅ 전체 파이프라인 실행 완료")
        return results

    def get_pipeline_status(self, run_id: str) -> Optional[PipelineRun]:
        """파이프라인 실행 상태 조회"""
        return self.active_runs.get(run_id)

    def list_active_runs(self) -> List[PipelineRun]:
        """활성 파이프라인 실행 목록"""
        return list(self.active_runs.values())

    def check_model_freshness(self, model_type: ModelType, max_age_days: int = 7) -> bool:
        """모델 신선도 확인 (재학습 필요 여부)"""
        try:
            experiment_name = self._get_experiment_name(model_type)
            performance_history = self.mlflow_manager.get_model_performance_history(experiment_name)

            if performance_history.empty:
                return False

            # 최근 실험 시간 확인
            latest_run_time = pd.to_datetime(performance_history.iloc[0]['start_time'])
            age_days = (datetime.now() - latest_run_time).days

            is_fresh = age_days <= max_age_days
            logger.info(f"🕒 {model_type.value} 모델 나이: {age_days}일 ({'신선' if is_fresh else '오래됨'})")

            return is_fresh

        except Exception as e:
            logger.error(f"❌ 모델 신선도 확인 실패: {e}")
            return False

    async def schedule_maintenance(self):
        """정기 유지보수 실행"""
        logger.info("🔧 정기 유지보수 시작")

        for model_type in ModelType:
            try:
                # 모델 신선도 확인
                if not self.check_model_freshness(model_type, max_age_days=7):
                    logger.info(f"⏰ {model_type.value} 모델 재학습 필요")
                    await self.run_pipeline(model_type, force=False)

            except Exception as e:
                logger.error(f"❌ {model_type.value} 유지보수 실패: {e}")

        logger.info("✅ 정기 유지보수 완료")


# 전역 오케스트레이터 인스턴스
_orchestrator = None

def get_ml_orchestrator() -> MLPipelineOrchestrator:
    """
    ML 파이프라인 오케스트레이터 싱글톤 인스턴스 반환
    """
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MLPipelineOrchestrator()
    return _orchestrator


if __name__ == "__main__":
    # 테스트 실행
    async def test_orchestrator():
        orchestrator = MLPipelineOrchestrator()

        # 가격 예측 모델 파이프라인 실행
        result = await orchestrator.run_pipeline(ModelType.PRICE_PREDICTOR, force=True)
        print(f"파이프라인 결과: {result}")

    asyncio.run(test_orchestrator())