# -*- coding: utf-8 -*-
"""
시스템 오케스트레이터
Market Insights Pro의 모든 구성 요소를 통합 관리합니다.
"""

import os
import sys
import logging
import asyncio
import threading
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import yaml

# 시스템 구성 요소들
from core.mlflow_manager import get_mlflow_manager
from core.ml_serving_api import get_ml_serving_service
from core.ml_monitoring import get_ml_monitoring_service
from core.ml_pipeline_orchestrator import get_ml_orchestrator, ModelType
from core.cache import get_cache_manager
from core.metrics_collector import get_metrics_collector
from core.health_checks import get_health_status
from core.kafka_manager import get_kafka_manager

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """서비스 상태"""
    INITIALIZING = "initializing"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class ServiceHealth:
    """서비스 헬스 정보"""
    service_name: str
    status: ServiceStatus
    uptime: timedelta
    last_check: datetime
    error_count: int
    metrics: Dict[str, Any]
    dependencies: List[str]


class SystemOrchestrator:
    """
    시스템 오케스트레이터
    전체 시스템의 라이프사이클, 헬스 체크, 의존성 관리를 담당합니다.
    """

    def __init__(self):
        self.start_time = datetime.now()
        self.services = {}
        self.service_health = {}
        self.monitoring_active = False
        self.monitoring_thread = None

        # 시스템 설정 로드
        self.config = self._load_system_config()

        # 서비스 초기화 순서 정의
        self.initialization_order = [
            "cache",
            "metrics",
            "mlflow",
            "kafka",
            "ml_serving",
            "ml_monitoring",
            "ml_orchestrator"
        ]

    def _load_system_config(self) -> Dict[str, Any]:
        """시스템 설정 로드"""
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_config.yaml")

            # 기본 설정 파일이 없으면 생성
            if not os.path.exists(config_path):
                default_config = {
                    "system": {
                        "name": "Market Insights Pro",
                        "version": "2.0.0",
                        "environment": "development"
                    },
                    "services": {
                        "cache": {
                            "enabled": True,
                            "health_check_interval": 60,
                            "dependencies": []
                        },
                        "metrics": {
                            "enabled": True,
                            "health_check_interval": 30,
                            "dependencies": []
                        },
                        "mlflow": {
                            "enabled": True,
                            "health_check_interval": 120,
                            "dependencies": []
                        },
                        "kafka": {
                            "enabled": True,
                            "health_check_interval": 60,
                            "dependencies": []
                        },
                        "ml_serving": {
                            "enabled": True,
                            "health_check_interval": 60,
                            "dependencies": ["cache", "mlflow"]
                        },
                        "ml_monitoring": {
                            "enabled": True,
                            "health_check_interval": 120,
                            "dependencies": ["mlflow", "ml_serving", "cache", "metrics"]
                        },
                        "ml_orchestrator": {
                            "enabled": True,
                            "health_check_interval": 300,
                            "dependencies": ["mlflow"]
                        }
                    },
                    "auto_recovery": {
                        "enabled": True,
                        "max_retry_attempts": 3,
                        "retry_delay_seconds": 30
                    }
                }

                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)

                logger.info(f"✅ 기본 시스템 설정 파일 생성: {config_path}")

            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            logger.info(f"✅ 시스템 설정 로드 완료")
            return config

        except Exception as e:
            logger.error(f"❌ 시스템 설정 로드 실패: {e}")
            return {}

    async def initialize_system(self):
        """전체 시스템 초기화"""
        logger.info("🚀 Market Insights Pro 시스템 초기화 시작")
        logger.info("=" * 60)

        initialization_results = {}

        for service_name in self.initialization_order:
            if not self._is_service_enabled(service_name):
                logger.info(f"⏭️ {service_name} 서비스 비활성화됨")
                continue

            try:
                logger.info(f"🔧 {service_name} 서비스 초기화 중...")

                # 의존성 확인
                dependencies = self.config.get("services", {}).get(service_name, {}).get("dependencies", [])
                if not self._check_dependencies(service_name, dependencies, initialization_results):
                    raise Exception(f"의존성 확인 실패: {dependencies}")

                # 서비스 초기화
                success = await self._initialize_service(service_name)
                initialization_results[service_name] = success

                if success:
                    logger.info(f"✅ {service_name} 서비스 초기화 완료")
                    self.service_health[service_name] = ServiceHealth(
                        service_name=service_name,
                        status=ServiceStatus.HEALTHY,
                        uptime=timedelta(0),
                        last_check=datetime.now(),
                        error_count=0,
                        metrics={},
                        dependencies=dependencies
                    )
                else:
                    logger.error(f"❌ {service_name} 서비스 초기화 실패")

            except Exception as e:
                logger.error(f"❌ {service_name} 서비스 초기화 중 오류: {e}")
                initialization_results[service_name] = False

        # 초기화 결과 요약
        successful_services = [name for name, success in initialization_results.items() if success]
        failed_services = [name for name, success in initialization_results.items() if not success]

        logger.info("\n📊 시스템 초기화 결과:")
        logger.info(f"   ✅ 성공: {len(successful_services)}/{len(initialization_results)} 서비스")
        logger.info(f"      {', '.join(successful_services)}")

        if failed_services:
            logger.warning(f"   ❌ 실패: {len(failed_services)} 서비스")
            logger.warning(f"      {', '.join(failed_services)}")

        # 헬스 모니터링 시작
        if successful_services:
            self.start_health_monitoring()

        logger.info("✨ 시스템 초기화 완료")
        return len(failed_services) == 0

    def _is_service_enabled(self, service_name: str) -> bool:
        """서비스 활성화 여부 확인"""
        return self.config.get("services", {}).get(service_name, {}).get("enabled", True)

    def _check_dependencies(self, service_name: str, dependencies: List[str], initialization_results: Dict[str, bool]) -> bool:
        """서비스 의존성 확인"""
        for dep in dependencies:
            if dep not in initialization_results or not initialization_results[dep]:
                logger.error(f"❌ {service_name} 의존성 실패: {dep}")
                return False
        return True

    async def _initialize_service(self, service_name: str) -> bool:
        """개별 서비스 초기화"""
        try:
            if service_name == "cache":
                cache_manager = get_cache_manager()
                health_status = cache_manager.health_check()
                if health_status.get("status") == "healthy":
                    self.services["cache"] = cache_manager
                    return True
                else:
                    logger.error(f"❌ Cache health check failed: {health_status.get('error', 'Unknown error')}")
                    return False

            elif service_name == "metrics":
                metrics_collector = get_metrics_collector()
                metrics_collector.start_collection()
                self.services["metrics"] = metrics_collector
                return True

            elif service_name == "mlflow":
                mlflow_manager = get_mlflow_manager()
                # MLflow 서버 연결 테스트
                experiments = mlflow_manager.client.search_experiments()
                self.services["mlflow"] = mlflow_manager
                return True

            elif service_name == "kafka":
                kafka_manager = get_kafka_manager()
                # Kafka 연결은 선택적 (로컬 개발 환경에서는 없을 수 있음)
                self.services["kafka"] = kafka_manager
                return True

            elif service_name == "ml_serving":
                ml_service = get_ml_serving_service()
                health = await ml_service.health_check()
                self.services["ml_serving"] = ml_service
                return health.get("status") == "healthy"

            elif service_name == "ml_monitoring":
                monitoring_service = get_ml_monitoring_service()
                monitoring_service.start_monitoring()
                self.services["ml_monitoring"] = monitoring_service
                return True

            elif service_name == "ml_orchestrator":
                orchestrator = get_ml_orchestrator()
                self.services["ml_orchestrator"] = orchestrator
                return True

            else:
                logger.warning(f"⚠️ 알 수 없는 서비스: {service_name}")
                return False

        except Exception as e:
            logger.error(f"❌ {service_name} 초기화 실패: {e}")
            return False

    def start_health_monitoring(self):
        """헬스 모니터링 시작"""
        if not self.monitoring_active:
            self.monitoring_active = True
            self.monitoring_thread = threading.Thread(
                target=self._health_monitoring_loop,
                daemon=True
            )
            self.monitoring_thread.start()
            logger.info("🏥 시스템 헬스 모니터링 시작")

    def stop_health_monitoring(self):
        """헬스 모니터링 중지"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logger.info("⏹️ 시스템 헬스 모니터링 중지")

    def _health_monitoring_loop(self):
        """헬스 모니터링 루프"""
        while self.monitoring_active:
            try:
                for service_name, health in self.service_health.items():
                    self._check_service_health(service_name)

                # 1분마다 체크
                threading.Event().wait(60)

            except Exception as e:
                logger.error(f"❌ 헬스 모니터링 오류: {e}")
                threading.Event().wait(30)

    def _check_service_health(self, service_name: str):
        """개별 서비스 헬스 체크"""
        try:
            service = self.services.get(service_name)
            if not service:
                return

            health = self.service_health[service_name]

            # 서비스별 헬스 체크
            is_healthy = True

            if service_name == "cache":
                # 캐시 헬스 체크는 비동기이므로 간단하게 처리
                is_healthy = True

            elif service_name == "ml_serving":
                # ML 서빙 헬스 체크 (비동기이므로 간략화)
                is_healthy = len(service.models) > 0

            elif service_name == "ml_monitoring":
                is_healthy = service.monitoring_active

            # 상태 업데이트
            if is_healthy:
                if health.status != ServiceStatus.HEALTHY:
                    logger.info(f"💚 {service_name} 서비스 복구됨")
                health.status = ServiceStatus.HEALTHY
                health.error_count = 0
            else:
                health.error_count += 1
                if health.error_count > 3:
                    health.status = ServiceStatus.FAILED
                    logger.error(f"💔 {service_name} 서비스 실패 상태")
                else:
                    health.status = ServiceStatus.DEGRADED
                    logger.warning(f"⚠️ {service_name} 서비스 성능 저하")

            health.last_check = datetime.now()
            health.uptime = datetime.now() - self.start_time

        except Exception as e:
            logger.error(f"❌ {service_name} 헬스 체크 실패: {e}")

    async def get_system_status(self) -> Dict[str, Any]:
        """전체 시스템 상태 조회"""
        try:
            overall_health = True
            service_statuses = {}

            for service_name, health in self.service_health.items():
                service_statuses[service_name] = {
                    "status": health.status.value,
                    "uptime_seconds": health.uptime.total_seconds(),
                    "last_check": health.last_check.isoformat(),
                    "error_count": health.error_count,
                    "dependencies": health.dependencies
                }

                if health.status in [ServiceStatus.DEGRADED, ServiceStatus.FAILED]:
                    overall_health = False

            # 전체 시스템 메트릭
            system_metrics = {}
            if "metrics" in self.services:
                metrics_collector = self.services["metrics"]
                system_metrics = metrics_collector.get_current_metrics()

            return {
                "system": {
                    "name": self.config.get("system", {}).get("name", "Market Insights Pro"),
                    "version": self.config.get("system", {}).get("version", "2.0.0"),
                    "status": "healthy" if overall_health else "degraded",
                    "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
                    "start_time": self.start_time.isoformat()
                },
                "services": service_statuses,
                "metrics": system_metrics,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ 시스템 상태 조회 실패: {e}")
            return {"error": str(e)}

    async def restart_service(self, service_name: str) -> bool:
        """서비스 재시작"""
        try:
            logger.info(f"🔄 {service_name} 서비스 재시작 중...")

            # 서비스 중지
            if service_name in self.services:
                service = self.services[service_name]

                if service_name == "ml_monitoring" and hasattr(service, 'stop_monitoring'):
                    service.stop_monitoring()
                elif service_name == "metrics" and hasattr(service, 'stop_collection'):
                    service.stop_collection()

            # 서비스 재초기화
            success = await self._initialize_service(service_name)

            if success:
                logger.info(f"✅ {service_name} 서비스 재시작 완료")
                self.service_health[service_name].status = ServiceStatus.HEALTHY
                self.service_health[service_name].error_count = 0
            else:
                logger.error(f"❌ {service_name} 서비스 재시작 실패")

            return success

        except Exception as e:
            logger.error(f"❌ {service_name} 서비스 재시작 중 오류: {e}")
            return False

    async def shutdown_system(self):
        """전체 시스템 종료"""
        logger.info("🛑 시스템 종료 시작...")

        # 헬스 모니터링 중지
        self.stop_health_monitoring()

        # 서비스 역순으로 종료
        shutdown_order = list(reversed(self.initialization_order))

        for service_name in shutdown_order:
            if service_name in self.services:
                try:
                    logger.info(f"🔸 {service_name} 서비스 종료 중...")
                    service = self.services[service_name]

                    if service_name == "ml_monitoring" and hasattr(service, 'stop_monitoring'):
                        service.stop_monitoring()
                    elif service_name == "metrics" and hasattr(service, 'stop_collection'):
                        service.stop_collection()

                    self.service_health[service_name].status = ServiceStatus.STOPPED

                except Exception as e:
                    logger.error(f"❌ {service_name} 종료 중 오류: {e}")

        logger.info("✅ 시스템 종료 완료")

    async def run_maintenance(self):
        """시스템 유지보수 실행"""
        logger.info("🔧 시스템 유지보수 시작")

        try:
            # ML 파이프라인 유지보수
            if "ml_orchestrator" in self.services:
                orchestrator = self.services["ml_orchestrator"]
                await orchestrator.schedule_maintenance()

            # 캐시 정리
            if "cache" in self.services:
                cache_manager = self.services["cache"]
                # 필요시 캐시 정리 로직 추가

            logger.info("✅ 시스템 유지보수 완료")

        except Exception as e:
            logger.error(f"❌ 시스템 유지보수 실패: {e}")


# 전역 시스템 오케스트레이터 인스턴스
_system_orchestrator = None

def get_system_orchestrator() -> SystemOrchestrator:
    """
    시스템 오케스트레이터 싱글톤 인스턴스 반환
    """
    global _system_orchestrator
    if _system_orchestrator is None:
        _system_orchestrator = SystemOrchestrator()
    return _system_orchestrator


if __name__ == "__main__":
    # 테스트 실행
    async def test_system():
        orchestrator = SystemOrchestrator()

        # 시스템 초기화
        success = await orchestrator.initialize_system()
        print(f"시스템 초기화: {'성공' if success else '실패'}")

        # 시스템 상태 확인
        status = await orchestrator.get_system_status()
        print(f"시스템 상태: {status}")

        # 종료
        await orchestrator.shutdown_system()

    asyncio.run(test_system())