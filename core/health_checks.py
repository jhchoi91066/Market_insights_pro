"""
Market Insights Pro - 종합 헬스체크 시스템
컨테이너와 서비스 상태 모니터링
"""

import asyncio
import time
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json

import redis
import sqlite3
from kafka import KafkaProducer, KafkaConsumer
from celery import Celery

logger = logging.getLogger(__name__)

class HealthCheckStatus:
    """헬스체크 상태 정의"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"

class BaseHealthCheck:
    """기본 헬스체크 클래스"""

    def __init__(self, name: str, timeout: int = 5):
        self.name = name
        self.timeout = timeout
        self.last_check = None
        self.status = HealthCheckStatus.UNKNOWN
        self.details = {}

    async def check(self) -> Dict[str, Any]:
        """헬스체크 실행"""
        start_time = time.time()

        try:
            result = await asyncio.wait_for(
                self._perform_check(),
                timeout=self.timeout
            )

            self.status = HealthCheckStatus.HEALTHY
            self.details = result

        except asyncio.TimeoutError:
            self.status = HealthCheckStatus.UNHEALTHY
            self.details = {"error": f"Timeout after {self.timeout}s"}

        except Exception as e:
            self.status = HealthCheckStatus.UNHEALTHY
            self.details = {"error": str(e)}

        self.last_check = datetime.now()
        duration = time.time() - start_time

        return {
            "name": self.name,
            "status": self.status,
            "timestamp": self.last_check.isoformat(),
            "duration_ms": round(duration * 1000, 2),
            "details": self.details
        }

    async def _perform_check(self) -> Dict[str, Any]:
        """실제 헬스체크 로직 (서브클래스에서 구현)"""
        raise NotImplementedError

class DatabaseHealthCheck(BaseHealthCheck):
    """데이터베이스 연결 상태 확인"""

    def __init__(self, db_path: str = "data/market_insights.db"):
        super().__init__("database")
        self.db_path = db_path

    async def _perform_check(self) -> Dict[str, Any]:
        try:
            conn = sqlite3.connect(self.db_path, timeout=2)
            cursor = conn.cursor()

            # 간단한 쿼리 실행
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

            # 테이블 개수 확인
            cursor.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            )
            table_count = cursor.fetchone()[0]

            conn.close()

            return {
                "connection": "ok",
                "query_result": result[0],
                "table_count": table_count,
                "database_path": self.db_path
            }

        except Exception as e:
            raise Exception(f"Database check failed: {str(e)}")

class RedisHealthCheck(BaseHealthCheck):
    """Redis 연결 및 성능 확인"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        super().__init__("redis")
        self.redis_url = redis_url

    async def _perform_check(self) -> Dict[str, Any]:
        try:
            r = redis.from_url(self.redis_url, socket_timeout=2)

            # 기본 연결 테스트
            ping_result = r.ping()

            # 간단한 SET/GET 테스트
            test_key = "health_check_test"
            test_value = f"test_{int(time.time())}"

            r.set(test_key, test_value, ex=10)
            get_result = r.get(test_key)
            r.delete(test_key)

            # Redis 정보 수집
            info = r.info()

            return {
                "ping": ping_result,
                "set_get_test": get_result.decode() == test_value,
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0)
            }

        except Exception as e:
            raise Exception(f"Redis check failed: {str(e)}")

class KafkaHealthCheck(BaseHealthCheck):
    """Kafka 연결 및 토픽 상태 확인"""

    def __init__(self, bootstrap_servers: str = "localhost:9092"):
        super().__init__("kafka")
        self.bootstrap_servers = bootstrap_servers

    async def _perform_check(self) -> Dict[str, Any]:
        try:
            # Producer 연결 테스트
            producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                request_timeout_ms=2000,
                api_version=(0, 10, 1)
            )

            # 클러스터 메타데이터 가져오기
            metadata = producer.list_topics(timeout=2)
            producer.close()

            # Consumer 연결 테스트
            consumer = KafkaConsumer(
                bootstrap_servers=self.bootstrap_servers,
                consumer_timeout_ms=1000,
                api_version=(0, 10, 1)
            )

            topics = consumer.topics()
            consumer.close()

            return {
                "producer_connection": "ok",
                "consumer_connection": "ok",
                "available_topics": list(topics),
                "topic_count": len(topics),
                "cluster_metadata": bool(metadata)
            }

        except Exception as e:
            raise Exception(f"Kafka check failed: {str(e)}")

class CeleryHealthCheck(BaseHealthCheck):
    """Celery 워커 및 브로커 상태 확인"""

    def __init__(self, broker_url: str = "redis://localhost:6379/0"):
        super().__init__("celery")
        self.broker_url = broker_url

    async def _perform_check(self) -> Dict[str, Any]:
        try:
            from core.celery_app import app as celery_app

            # 활성 워커 확인
            inspect = celery_app.control.inspect()
            active_workers = inspect.active()
            registered_tasks = inspect.registered()

            # 브로커 연결 확인
            broker_info = celery_app.control.inspect().stats()

            return {
                "broker_connection": "ok",
                "active_workers": len(active_workers) if active_workers else 0,
                "worker_names": list(active_workers.keys()) if active_workers else [],
                "registered_tasks_count": sum(
                    len(tasks) for tasks in registered_tasks.values()
                ) if registered_tasks else 0,
                "broker_stats": bool(broker_info)
            }

        except Exception as e:
            raise Exception(f"Celery check failed: {str(e)}")

class SystemResourceHealthCheck(BaseHealthCheck):
    """시스템 리소스 상태 확인"""

    def __init__(self):
        super().__init__("system_resources")

    async def _perform_check(self) -> Dict[str, Any]:
        try:
            import psutil

            # CPU 사용률
            cpu_percent = psutil.cpu_percent(interval=1)

            # 메모리 사용률
            memory = psutil.virtual_memory()

            # 디스크 사용률
            disk = psutil.disk_usage('/')

            # 네트워크 상태
            network = psutil.net_io_counters()

            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "disk_percent": round((disk.used / disk.total) * 100, 2),
                "disk_free_gb": round(disk.free / (1024**3), 2),
                "network_bytes_sent": network.bytes_sent,
                "network_bytes_recv": network.bytes_recv
            }

        except ImportError:
            # psutil이 설치되지 않은 경우
            return {"warning": "psutil not installed, limited system info"}

        except Exception as e:
            raise Exception(f"System resource check failed: {str(e)}")

class ApplicationHealthCheck(BaseHealthCheck):
    """애플리케이션 자체 상태 확인"""

    def __init__(self):
        super().__init__("application")

    async def _perform_check(self) -> Dict[str, Any]:
        try:
            import sys
            import os
            from datetime import datetime

            # 애플리케이션 정보
            app_info = {
                "python_version": sys.version,
                "platform": sys.platform,
                "process_id": os.getpid(),
                "current_time": datetime.now().isoformat(),
                "uptime_seconds": time.time() - psutil.Process().create_time() if 'psutil' in sys.modules else "unknown"
            }

            # 환경 변수 확인
            required_env_vars = [
                "REDIS_URL", "KAFKA_BOOTSTRAP_SERVERS",
                "DATABASE_URL", "ENVIRONMENT"
            ]

            env_status = {}
            for var in required_env_vars:
                env_status[var] = os.getenv(var) is not None

            return {
                "app_info": app_info,
                "environment_variables": env_status,
                "all_env_vars_present": all(env_status.values())
            }

        except Exception as e:
            raise Exception(f"Application check failed: {str(e)}")

class HealthChecker:
    """종합 헬스체크 매니저"""

    def __init__(self):
        self.checks: List[BaseHealthCheck] = []
        self._setup_checks()

    def _setup_checks(self):
        """헬스체크 초기화"""
        import os

        # 기본 체크 추가
        self.checks.extend([
            ApplicationHealthCheck(),
            SystemResourceHealthCheck(),
        ])

        # 환경별 체크 추가
        if os.getenv("DATABASE_URL"):
            db_path = os.getenv("DATABASE_URL", "").replace("sqlite:///", "")
            self.checks.append(DatabaseHealthCheck(db_path))

        if os.getenv("REDIS_URL"):
            self.checks.append(RedisHealthCheck(os.getenv("REDIS_URL")))

        if os.getenv("KAFKA_BOOTSTRAP_SERVERS"):
            self.checks.append(KafkaHealthCheck(os.getenv("KAFKA_BOOTSTRAP_SERVERS")))

        if os.getenv("CELERY_BROKER_URL"):
            self.checks.append(CeleryHealthCheck(os.getenv("CELERY_BROKER_URL")))

    async def run_all_checks(self) -> Dict[str, Any]:
        """모든 헬스체크 실행"""
        start_time = time.time()

        # 모든 체크를 병렬로 실행
        tasks = [check.check() for check in self.checks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 집계
        check_results = []
        healthy_count = 0
        total_count = len(results)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                check_results.append({
                    "name": self.checks[i].name,
                    "status": HealthCheckStatus.UNHEALTHY,
                    "error": str(result)
                })
            else:
                check_results.append(result)
                if result["status"] == HealthCheckStatus.HEALTHY:
                    healthy_count += 1

        # 전체 상태 결정
        if healthy_count == total_count:
            overall_status = HealthCheckStatus.HEALTHY
        elif healthy_count > total_count / 2:
            overall_status = HealthCheckStatus.DEGRADED
        else:
            overall_status = HealthCheckStatus.UNHEALTHY

        total_duration = time.time() - start_time

        return {
            "overall_status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "total_duration_ms": round(total_duration * 1000, 2),
            "checks_total": total_count,
            "checks_healthy": healthy_count,
            "checks_unhealthy": total_count - healthy_count,
            "checks": check_results
        }

    async def get_simple_status(self) -> bool:
        """간단한 상태 확인 (True/False)"""
        result = await self.run_all_checks()
        return result["overall_status"] in [HealthCheckStatus.HEALTHY, HealthCheckStatus.DEGRADED]

# 전역 헬스체커 인스턴스
health_checker = HealthChecker()

async def get_health_status() -> Dict[str, Any]:
    """헬스체크 API 엔드포인트용 함수"""
    return await health_checker.run_all_checks()

async def is_healthy() -> bool:
    """간단한 헬스체크 함수"""
    return await health_checker.get_simple_status()