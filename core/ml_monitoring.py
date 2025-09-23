# -*- coding: utf-8 -*-
"""
ML 모니터링 시스템
Market Insights Pro의 ML 모델 성능, 데이터 품질, 시스템 안정성을 모니터링합니다.
"""

import os
import sys
import logging
import asyncio
import threading
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import pandas as pd
import numpy as np
from collections import deque, defaultdict
import json

# ML 관련 임포트
from core.mlflow_manager import get_mlflow_manager
from core.ml_serving_api import get_ml_serving_service
from core.cache import get_cache_manager
from core.metrics_collector import get_metrics_collector

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """알림 레벨"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ModelStatus(Enum):
    """모델 상태"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class PerformanceMetric:
    """성능 메트릭"""
    metric_name: str
    value: float
    threshold: float
    status: ModelStatus
    timestamp: datetime
    model_name: str


@dataclass
class DataQualityAlert:
    """데이터 품질 알림"""
    alert_id: str
    level: AlertLevel
    title: str
    description: str
    metric_name: str
    current_value: float
    expected_range: Tuple[float, float]
    timestamp: datetime
    model_name: str


@dataclass
class ModelHealthReport:
    """모델 헬스 리포트"""
    model_name: str
    overall_status: ModelStatus
    performance_metrics: List[PerformanceMetric]
    data_quality_score: float
    prediction_latency: float
    error_rate: float
    uptime_percentage: float
    last_training_time: Optional[datetime]
    alerts: List[DataQualityAlert]
    recommendations: List[str]


class DataDriftDetector:
    """데이터 드리프트 감지기"""

    def __init__(self, reference_window_size: int = 1000):
        self.reference_window_size = reference_window_size
        self.reference_data = deque(maxlen=reference_window_size)
        self.current_data = deque(maxlen=100)  # 최근 100개 요청

    def add_reference_data(self, features: Dict[str, Any]):
        """참조 데이터 추가 (학습 데이터 또는 초기 프로덕션 데이터)"""
        self.reference_data.append(features)

    def add_current_data(self, features: Dict[str, Any]):
        """현재 데이터 추가 (실시간 예측 요청)"""
        self.current_data.append(features)

    def detect_drift(self) -> Dict[str, float]:
        """드리프트 감지 (간단한 통계적 방법)"""
        if len(self.reference_data) < 100 or len(self.current_data) < 50:
            return {}

        drift_scores = {}

        # 숫자형 특성에 대한 드리프트 감지
        numeric_features = ['rating', 'review_count', 'price_to_category_avg_ratio',
                          'price_to_keyword_avg_ratio', 'rating_x_review_count']

        for feature in numeric_features:
            try:
                ref_values = [data.get(feature, 0) for data in self.reference_data]
                curr_values = [data.get(feature, 0) for data in self.current_data]

                if ref_values and curr_values:
                    ref_mean = np.mean(ref_values)
                    curr_mean = np.mean(curr_values)
                    ref_std = np.std(ref_values)

                    # 평균의 차이를 표준편차로 나눈 값 (Z-score 기반)
                    if ref_std > 0:
                        drift_score = abs(curr_mean - ref_mean) / ref_std
                        drift_scores[feature] = drift_score

            except Exception as e:
                logger.warning(f"드리프트 계산 실패 ({feature}): {e}")

        return drift_scores


class ModelPerformanceMonitor:
    """모델 성능 모니터"""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.prediction_history = deque(maxlen=1000)
        self.error_history = deque(maxlen=100)
        self.latency_history = deque(maxlen=1000)

    def record_prediction(self, prediction_time: float, success: bool, latency_ms: float):
        """예측 기록"""
        self.prediction_history.append({
            'timestamp': datetime.now(),
            'success': success,
            'latency_ms': latency_ms
        })

        if not success:
            self.error_history.append({
                'timestamp': datetime.now(),
                'latency_ms': latency_ms
            })

        self.latency_history.append(latency_ms)

    def get_performance_metrics(self) -> Dict[str, float]:
        """성능 메트릭 계산"""
        if not self.prediction_history:
            return {}

        total_predictions = len(self.prediction_history)
        successful_predictions = sum(1 for p in self.prediction_history if p['success'])

        metrics = {
            'success_rate': (successful_predictions / total_predictions) * 100,
            'error_rate': ((total_predictions - successful_predictions) / total_predictions) * 100,
            'avg_latency_ms': np.mean(self.latency_history) if self.latency_history else 0,
            'p95_latency_ms': np.percentile(self.latency_history, 95) if self.latency_history else 0,
            'p99_latency_ms': np.percentile(self.latency_history, 99) if self.latency_history else 0,
            'total_predictions': total_predictions
        }

        # 시간당 예측 수
        recent_hour = datetime.now() - timedelta(hours=1)
        recent_predictions = [p for p in self.prediction_history if p['timestamp'] > recent_hour]
        metrics['predictions_per_hour'] = len(recent_predictions)

        return metrics


class MLMonitoringService:
    """
    ML 모니터링 서비스
    모델 성능, 데이터 품질, 시스템 안정성을 종합적으로 모니터링합니다.
    """

    def __init__(self):
        self.mlflow_manager = get_mlflow_manager()
        self.ml_service = None  # 지연 초기화
        self.cache_manager = get_cache_manager()
        self.metrics_collector = get_metrics_collector()

        # 모니터링 상태
        self.monitoring_active = False
        self.monitoring_thread = None

        # 모델별 모니터
        self.performance_monitors: Dict[str, ModelPerformanceMonitor] = {}
        self.drift_detectors: Dict[str, DataDriftDetector] = {}

        # 알림 및 메트릭 히스토리
        self.alerts: deque = deque(maxlen=1000)
        self.health_reports: deque = deque(maxlen=100)

        # 임계값 설정
        self.thresholds = {
            'success_rate_threshold': 95.0,  # %
            'avg_latency_threshold': 1000.0,  # ms
            'p95_latency_threshold': 2000.0,  # ms
            'error_rate_threshold': 5.0,  # %
            'drift_threshold': 2.0,  # Z-score
            'data_quality_threshold': 0.8  # 0-1 점수
        }

        self._initialize_monitors()

    def _initialize_monitors(self):
        """모니터 초기화"""
        model_names = ["price_predictor", "demand_forecaster"]

        for model_name in model_names:
            self.performance_monitors[model_name] = ModelPerformanceMonitor(model_name)
            self.drift_detectors[model_name] = DataDriftDetector()

    def start_monitoring(self):
        """모니터링 시작"""
        if not self.monitoring_active:
            self.monitoring_active = True
            self.monitoring_thread = threading.Thread(
                target=self._monitoring_loop,
                daemon=True
            )
            self.monitoring_thread.start()
            logger.info("🔍 ML 모니터링 시작")

    def stop_monitoring(self):
        """모니터링 중지"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logger.info("⏹️ ML 모니터링 중지")

    def _monitoring_loop(self):
        """모니터링 루프"""
        while self.monitoring_active:
            try:
                self._check_model_health()
                self._check_data_quality()
                self._detect_anomalies()

                # 5분마다 체크
                threading.Event().wait(300)

            except Exception as e:
                logger.error(f"❌ 모니터링 루프 오류: {e}")
                threading.Event().wait(60)  # 오류 시 1분 대기

    def record_prediction_event(self, model_name: str, success: bool, latency_ms: float, features: Dict[str, Any] = None):
        """예측 이벤트 기록"""
        # 성능 모니터에 기록
        if model_name in self.performance_monitors:
            self.performance_monitors[model_name].record_prediction(
                prediction_time=datetime.now().timestamp(),
                success=success,
                latency_ms=latency_ms
            )

        # 드리프트 감지를 위한 특성 기록
        if features and model_name in self.drift_detectors:
            self.drift_detectors[model_name].add_current_data(features)

    def _check_model_health(self):
        """모델 헬스 체크"""
        for model_name, monitor in self.performance_monitors.items():
            try:
                metrics = monitor.get_performance_metrics()

                if not metrics:
                    continue

                # 성능 임계값 체크
                alerts = []

                if metrics['success_rate'] < self.thresholds['success_rate_threshold']:
                    alert = DataQualityAlert(
                        alert_id=f"low_success_rate_{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        level=AlertLevel.WARNING,
                        title="낮은 성공률 감지",
                        description=f"{model_name} 모델의 성공률이 {metrics['success_rate']:.1f}%로 임계값 {self.thresholds['success_rate_threshold']}%를 하회했습니다.",
                        metric_name="success_rate",
                        current_value=metrics['success_rate'],
                        expected_range=(self.thresholds['success_rate_threshold'], 100.0),
                        timestamp=datetime.now(),
                        model_name=model_name
                    )
                    alerts.append(alert)

                if metrics['avg_latency_ms'] > self.thresholds['avg_latency_threshold']:
                    alert = DataQualityAlert(
                        alert_id=f"high_latency_{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        level=AlertLevel.WARNING,
                        title="높은 지연시간 감지",
                        description=f"{model_name} 모델의 평균 지연시간이 {metrics['avg_latency_ms']:.1f}ms로 임계값 {self.thresholds['avg_latency_threshold']}ms를 초과했습니다.",
                        metric_name="avg_latency_ms",
                        current_value=metrics['avg_latency_ms'],
                        expected_range=(0.0, self.thresholds['avg_latency_threshold']),
                        timestamp=datetime.now(),
                        model_name=model_name
                    )
                    alerts.append(alert)

                # 알림 저장
                for alert in alerts:
                    self.alerts.append(alert)
                    logger.warning(f"⚠️ {alert.title}: {alert.description}")

            except Exception as e:
                logger.error(f"❌ {model_name} 헬스 체크 실패: {e}")

    def _check_data_quality(self):
        """데이터 품질 체크"""
        for model_name, detector in self.drift_detectors.items():
            try:
                drift_scores = detector.detect_drift()

                for feature, score in drift_scores.items():
                    if score > self.thresholds['drift_threshold']:
                        alert = DataQualityAlert(
                            alert_id=f"data_drift_{model_name}_{feature}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                            level=AlertLevel.WARNING,
                            title="데이터 드리프트 감지",
                            description=f"{model_name} 모델의 {feature} 특성에서 드리프트 점수 {score:.2f}로 임계값 {self.thresholds['drift_threshold']}를 초과했습니다.",
                            metric_name=f"drift_{feature}",
                            current_value=score,
                            expected_range=(0.0, self.thresholds['drift_threshold']),
                            timestamp=datetime.now(),
                            model_name=model_name
                        )
                        self.alerts.append(alert)
                        logger.warning(f"⚠️ {alert.title}: {alert.description}")

            except Exception as e:
                logger.error(f"❌ {model_name} 데이터 품질 체크 실패: {e}")

    def _detect_anomalies(self):
        """이상 탐지"""
        try:
            # MLflow에서 최근 실험 성능 확인
            for model_name in self.performance_monitors.keys():
                experiment_name = self._get_experiment_name(model_name)
                performance_history = self.mlflow_manager.get_model_performance_history(experiment_name)

                if not performance_history.empty:
                    # 최근 성능과 과거 성능 비교
                    latest_metrics = performance_history.iloc[0]
                    if len(performance_history) > 1:
                        previous_metrics = performance_history.iloc[1]

                        # MAE 증가 체크
                        if 'metrics.mae' in latest_metrics and 'metrics.mae' in previous_metrics:
                            mae_increase = (latest_metrics['metrics.mae'] - previous_metrics['metrics.mae']) / previous_metrics['metrics.mae'] * 100

                            if mae_increase > 20:  # 20% 이상 증가
                                alert = DataQualityAlert(
                                    alert_id=f"performance_degradation_{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                                    level=AlertLevel.ERROR,
                                    title="모델 성능 저하 감지",
                                    description=f"{model_name} 모델의 MAE가 {mae_increase:.1f}% 증가했습니다. 재훈련을 고려해주세요.",
                                    metric_name="mae_increase",
                                    current_value=mae_increase,
                                    expected_range=(-100.0, 20.0),
                                    timestamp=datetime.now(),
                                    model_name=model_name
                                )
                                self.alerts.append(alert)
                                logger.error(f"🚨 {alert.title}: {alert.description}")

        except Exception as e:
            logger.error(f"❌ 이상 탐지 실패: {e}")

    def _get_experiment_name(self, model_name: str) -> str:
        """모델명에서 실험명 추출"""
        mapping = {
            "price_predictor": "price_prediction",
            "demand_forecaster": "demand_forecasting"
        }
        return mapping.get(model_name, model_name)

    async def generate_health_report(self, model_name: str) -> ModelHealthReport:
        """모델 헬스 리포트 생성"""
        try:
            # 성능 메트릭
            monitor = self.performance_monitors.get(model_name)
            performance_metrics = []

            if monitor:
                metrics = monitor.get_performance_metrics()
                for metric_name, value in metrics.items():
                    threshold = self.thresholds.get(f"{metric_name}_threshold", 0)

                    # 상태 결정
                    if metric_name in ['success_rate']:
                        status = ModelStatus.HEALTHY if value >= threshold else ModelStatus.DEGRADED
                    elif metric_name in ['error_rate', 'avg_latency_ms', 'p95_latency_ms']:
                        status = ModelStatus.HEALTHY if value <= threshold else ModelStatus.DEGRADED
                    else:
                        status = ModelStatus.HEALTHY

                    performance_metrics.append(PerformanceMetric(
                        metric_name=metric_name,
                        value=value,
                        threshold=threshold,
                        status=status,
                        timestamp=datetime.now(),
                        model_name=model_name
                    ))

            # 전체 상태 결정
            degraded_metrics = [m for m in performance_metrics if m.status == ModelStatus.DEGRADED]
            overall_status = ModelStatus.DEGRADED if degraded_metrics else ModelStatus.HEALTHY

            # 최근 알림
            recent_alerts = [a for a in self.alerts if a.model_name == model_name and
                           a.timestamp > datetime.now() - timedelta(hours=24)]

            # 추천사항 생성
            recommendations = self._generate_recommendations(model_name, performance_metrics, recent_alerts)

            # 마지막 훈련 시간
            last_training_time = None
            try:
                experiment_name = self._get_experiment_name(model_name)
                performance_history = self.mlflow_manager.get_model_performance_history(experiment_name)
                if not performance_history.empty:
                    last_training_time = pd.to_datetime(performance_history.iloc[0]['start_time'])
            except:
                pass

            report = ModelHealthReport(
                model_name=model_name,
                overall_status=overall_status,
                performance_metrics=performance_metrics,
                data_quality_score=0.85,  # 임시값, 실제로는 계산 필요
                prediction_latency=performance_metrics[0].value if performance_metrics else 0,
                error_rate=next((m.value for m in performance_metrics if m.metric_name == 'error_rate'), 0),
                uptime_percentage=99.5,  # 임시값
                last_training_time=last_training_time,
                alerts=recent_alerts[-10:],  # 최근 10개 알림
                recommendations=recommendations
            )

            self.health_reports.append(report)
            return report

        except Exception as e:
            logger.error(f"❌ 헬스 리포트 생성 실패: {e}")
            return ModelHealthReport(
                model_name=model_name,
                overall_status=ModelStatus.UNKNOWN,
                performance_metrics=[],
                data_quality_score=0.0,
                prediction_latency=0.0,
                error_rate=0.0,
                uptime_percentage=0.0,
                last_training_time=None,
                alerts=[],
                recommendations=["헬스 리포트 생성 실패"]
            )

    def _generate_recommendations(self, model_name: str, metrics: List[PerformanceMetric], alerts: List[DataQualityAlert]) -> List[str]:
        """추천사항 생성"""
        recommendations = []

        # 성능 기반 추천
        for metric in metrics:
            if metric.status == ModelStatus.DEGRADED:
                if metric.metric_name == 'success_rate':
                    recommendations.append("모델 성공률이 낮습니다. 입력 데이터 검증 및 모델 재훈련을 고려하세요.")
                elif metric.metric_name == 'avg_latency_ms':
                    recommendations.append("평균 응답시간이 높습니다. 모델 최적화 또는 인프라 스케일링을 고려하세요.")
                elif metric.metric_name == 'error_rate':
                    recommendations.append("오류율이 높습니다. 로그를 확인하고 모델 안정성을 점검하세요.")

        # 알림 기반 추천
        for alert in alerts:
            if alert.level in [AlertLevel.WARNING, AlertLevel.ERROR]:
                if 'drift' in alert.metric_name:
                    recommendations.append("데이터 드리프트가 감지되었습니다. 새로운 데이터로 모델 재훈련을 권장합니다.")
                elif 'performance_degradation' in alert.alert_id:
                    recommendations.append("모델 성능이 저하되었습니다. 즉시 재훈련을 권장합니다.")

        # 일반적인 추천
        if not recommendations:
            recommendations.append("모델이 정상적으로 작동 중입니다. 정기적인 모니터링을 지속하세요.")

        return recommendations[:5]  # 최대 5개 추천사항

    def get_monitoring_dashboard_data(self) -> Dict[str, Any]:
        """모니터링 대시보드 데이터"""
        try:
            dashboard_data = {
                'overview': {
                    'total_models': len(self.performance_monitors),
                    'healthy_models': 0,
                    'degraded_models': 0,
                    'total_predictions_today': 0,
                    'avg_latency': 0,
                    'uptime_percentage': 99.5
                },
                'models': {},
                'recent_alerts': list(self.alerts)[-10:],
                'system_status': 'healthy'
            }

            # 모델별 상태
            for model_name, monitor in self.performance_monitors.items():
                metrics = monitor.get_performance_metrics()
                if metrics:
                    dashboard_data['models'][model_name] = {
                        'status': 'healthy' if metrics.get('success_rate', 0) > 95 else 'degraded',
                        'metrics': metrics
                    }

                    if metrics.get('success_rate', 0) > 95:
                        dashboard_data['overview']['healthy_models'] += 1
                    else:
                        dashboard_data['overview']['degraded_models'] += 1

            return dashboard_data

        except Exception as e:
            logger.error(f"❌ 대시보드 데이터 생성 실패: {e}")
            return {'error': str(e)}


# 전역 모니터링 서비스 인스턴스
_monitoring_service = None

def get_ml_monitoring_service() -> MLMonitoringService:
    """
    ML 모니터링 서비스 싱글톤 인스턴스 반환
    """
    global _monitoring_service
    if _monitoring_service is None:
        _monitoring_service = MLMonitoringService()
    return _monitoring_service


if __name__ == "__main__":
    # 테스트 실행
    async def test_monitoring():
        monitoring = MLMonitoringService()
        monitoring.start_monitoring()

        # 테스트 예측 이벤트 기록
        monitoring.record_prediction_event(
            model_name="price_predictor",
            success=True,
            latency_ms=150.0,
            features={
                'rating': 4.5,
                'review_count': 200,
                'price_to_category_avg_ratio': 1.2
            }
        )

        # 헬스 리포트 생성
        report = await monitoring.generate_health_report("price_predictor")
        print(f"헬스 리포트: {report.model_name} - {report.overall_status.value}")

        # 대시보드 데이터
        dashboard = monitoring.get_monitoring_dashboard_data()
        print(f"대시보드 데이터: {dashboard}")

        monitoring.stop_monitoring()

    asyncio.run(test_monitoring())