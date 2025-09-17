"""
전용 워커 시스템
작업 타입별 전문 워커 관리 및 최적화
"""

import os
import logging
import subprocess
import psutil
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)

class WorkerType(Enum):
    """
    워커 타입 정의

    각 워커는 특정 작업에 특화되어 최적화됨
    """
    SCRAPING = "scraping_worker"      # 스크래핑 전용 (IO 집약적)
    ANALYSIS = "analysis_worker"      # 분석 전용 (CPU 집약적)
    NOTIFICATIONS = "notification_worker"  # 알림 전용 (IO 집약적)
    STATISTICS = "statistics_worker"  # 통계 전용 (CPU 집약적)
    MAINTENANCE = "maintenance_worker"  # 유지보수 전용 (배치 작업)

@dataclass
class WorkerConfig:
    """
    워커 설정 클래스

    각 워커 타입별 최적화된 설정
    """
    worker_type: WorkerType
    queues: List[str]              # 처리할 큐 목록
    concurrency: int               # 동시 처리 작업 수
    prefetch_multiplier: int       # 미리 가져올 작업 배수
    max_memory_per_child: int      # 자식 프로세스당 최대 메모리 (MB)
    max_tasks_per_child: int       # 자식 프로세스당 최대 작업 수
    time_limit: int                # 작업 시간 제한 (초)
    soft_time_limit: int          # 소프트 시간 제한 (초)
    description: str              # 워커 설명
    optimization_tags: Dict[str, str]  # 최적화 태그

class WorkerManager:
    """
    워커 관리자

    다양한 타입의 전용 워커를 생성, 관리, 모니터링
    """

    def __init__(self):
        """
        워커 매니저 초기화

        시스템 리소스를 기반으로 최적화된 워커 설정 생성
        """
        self.system_info = self._get_system_info()
        self.worker_configs = self._initialize_worker_configs()
        self.running_workers = {}  # 실행 중인 워커 프로세스
        self.worker_stats = {}     # 워커별 통계

    def _get_system_info(self) -> Dict[str, Any]:
        """
        시스템 정보 수집

        CPU, 메모리 정보를 기반으로 워커 설정 최적화

        Returns:
            dict: 시스템 정보
        """
        try:
            cpu_count = psutil.cpu_count(logical=True)
            memory_gb = psutil.virtual_memory().total / (1024**3)

            return {
                'cpu_cores': cpu_count,
                'memory_gb': round(memory_gb, 1),
                'cpu_usage': psutil.cpu_percent(interval=1),
                'memory_usage_percent': psutil.virtual_memory().percent,
                'available_memory_gb': round(psutil.virtual_memory().available / (1024**3), 1)
            }

        except Exception as e:
            logger.warning(f"⚠️ 시스템 정보 수집 실패: {e}")
            # 기본값 반환
            return {
                'cpu_cores': 4,
                'memory_gb': 8.0,
                'cpu_usage': 50.0,
                'memory_usage_percent': 60.0,
                'available_memory_gb': 3.0
            }

    def _initialize_worker_configs(self) -> Dict[WorkerType, WorkerConfig]:
        """
        워커 설정 초기화

        시스템 리소스와 작업 특성을 고려한 최적화된 설정

        Returns:
            dict: 워커 타입별 설정
        """
        cpu_cores = self.system_info['cpu_cores']
        memory_gb = self.system_info['memory_gb']

        configs = {}

        # === 🕷️ 스크래핑 워커 (IO 집약적) ===
        configs[WorkerType.SCRAPING] = WorkerConfig(
            worker_type=WorkerType.SCRAPING,
            queues=['scraping', 'critical'],  # critical 큐도 처리
            concurrency=min(4, cpu_cores),    # IO 대기로 인해 CPU 코어보다 많이 가능
            prefetch_multiplier=2,            # 스크래핑은 시간이 오래 걸리므로 적게
            max_memory_per_child=512,         # 브라우저 메모리 사용 고려
            max_tasks_per_child=50,           # 메모리 누수 방지
            time_limit=900,                   # 15분
            soft_time_limit=840,              # 14분
            description="Amazon 스크래핑 전용 워커 (IO 집약적)",
            optimization_tags={
                'type': 'io_intensive',
                'browser': 'playwright',
                'rate_limited': 'true'
            }
        )

        # === 📊 분석 워커 (CPU 집약적) ===
        configs[WorkerType.ANALYSIS] = WorkerConfig(
            worker_type=WorkerType.ANALYSIS,
            queues=['analysis'],
            concurrency=cpu_cores,            # CPU 코어 수만큼
            prefetch_multiplier=4,            # 빠른 작업이므로 많이 미리 가져옴
            max_memory_per_child=256,         # 상대적으로 적은 메모리
            max_tasks_per_child=200,          # 많은 작업 처리 가능
            time_limit=300,                   # 5분
            soft_time_limit=270,              # 4.5분
            description="시장 분석 전용 워커 (CPU 집약적)",
            optimization_tags={
                'type': 'cpu_intensive',
                'computation': 'heavy',
                'cache_friendly': 'true'
            }
        )

        # === 📧 알림 워커 (IO 집약적, 빠른 처리) ===
        configs[WorkerType.NOTIFICATIONS] = WorkerConfig(
            worker_type=WorkerType.NOTIFICATIONS,
            queues=['notifications'],
            concurrency=min(6, cpu_cores * 2),  # 빠른 작업이므로 더 많이
            prefetch_multiplier=8,            # 빠르게 많이 처리
            max_memory_per_child=128,         # 적은 메모리 사용
            max_tasks_per_child=500,          # 많은 작업 처리
            time_limit=60,                    # 1분
            soft_time_limit=50,               # 50초
            description="이메일/Slack 알림 전용 워커",
            optimization_tags={
                'type': 'io_intensive',
                'network': 'true',
                'fast_processing': 'true'
            }
        )

        # === 📈 통계 워커 (CPU 집약적, 낮은 우선순위) ===
        configs[WorkerType.STATISTICS] = WorkerConfig(
            worker_type=WorkerType.STATISTICS,
            queues=['statistics'],
            concurrency=max(1, cpu_cores // 2),  # 적은 워커로 백그라운드 처리
            prefetch_multiplier=2,            # 신중하게 처리
            max_memory_per_child=256,         # 보통 메모리
            max_tasks_per_child=100,          # 안정성 위주
            time_limit=180,                   # 3분
            soft_time_limit=150,              # 2.5분
            description="통계 처리 전용 워커 (낮은 우선순위)",
            optimization_tags={
                'type': 'cpu_intensive',
                'background': 'true',
                'low_priority': 'true'
            }
        )

        # === 🧹 유지보수 워커 (배치 작업) ===
        configs[WorkerType.MAINTENANCE] = WorkerConfig(
            worker_type=WorkerType.MAINTENANCE,
            queues=['maintenance'],
            concurrency=1,                    # 단일 워커로 안전하게
            prefetch_multiplier=1,            # 한 번에 하나씩
            max_memory_per_child=512,         # 대용량 작업 고려
            max_tasks_per_child=10,           # 적은 작업 수로 안정성 확보
            time_limit=3600,                  # 1시간
            soft_time_limit=3300,             # 55분
            description="데이터 정리 등 유지보수 전용 워커",
            optimization_tags={
                'type': 'batch',
                'long_running': 'true',
                'maintenance': 'true'
            }
        )

        logger.info(f"✅ 워커 설정 초기화 완료: {len(configs)}개 워커 타입")
        return configs

    def generate_worker_command(self, worker_type: WorkerType,
                              worker_name: Optional[str] = None) -> List[str]:
        """
        워커 실행 명령어 생성

        Args:
            worker_type: 워커 타입
            worker_name: 워커 이름 (선택적)

        Returns:
            list: 실행 명령어 리스트
        """
        config = self.worker_configs[worker_type]

        if worker_name is None:
            worker_name = f"{config.worker_type.value}_{int(time.time())}"

        # 라우팅 키 패턴 생성 (topic exchange 지원)
        routing_patterns = []
        for queue in config.queues:
            # 각 큐에 대해 다양한 우선순위의 라우팅 키 패턴 수신
            routing_patterns.extend([
                f'critical.{queue}.*',   # 긴급 작업
                f'high.{queue}.*',       # 높은 우선순위
                f'normal.{queue}.*',     # 보통 우선순위
                f'low.{queue}.*',        # 낮은 우선순위
                f'batch.{queue}.*',      # 배치 작업
            ])

        # 기본 celery worker 명령어
        command = [
            'celery',
            '-A', 'core.celery_app',
            'worker',
            '--loglevel=info',
            f'--hostname={worker_name}@%h',
            f'--queues={",".join(config.queues)}',
            f'--concurrency={config.concurrency}',
            f'--prefetch-multiplier={config.prefetch_multiplier}',
            f'--max-memory-per-child={config.max_memory_per_child * 1024}',  # KB 단위
            f'--max-tasks-per-child={config.max_tasks_per_child}',
            f'--time-limit={config.time_limit}',
            f'--soft-time-limit={config.soft_time_limit}',
            # Topic exchange와 라우팅 키 패턴 지원
            '--exchange=market_insights',
            '--exchange-type=topic',
        ]

        # 워커 타입별 추가 최적화
        if config.optimization_tags.get('type') == 'io_intensive':
            command.extend([
                '--pool=eventlet',  # IO 집약적 작업에 적합
            ])
        elif config.optimization_tags.get('type') == 'cpu_intensive':
            command.extend([
                '--pool=prefork',   # CPU 집약적 작업에 적합
            ])

        # 백그라운드 작업은 낮은 우선순위
        if config.optimization_tags.get('background') == 'true':
            command.extend([
                '--without-heartbeat',  # 하트비트 비활성화
                '--without-mingle',     # 워커 간 통신 비활성화
            ])

        return command

    def start_worker(self, worker_type: WorkerType,
                    worker_name: Optional[str] = None) -> Optional[subprocess.Popen]:
        """
        워커 시작

        Args:
            worker_type: 워커 타입
            worker_name: 워커 이름

        Returns:
            subprocess.Popen: 워커 프로세스 또는 None
        """
        try:
            command = self.generate_worker_command(worker_type, worker_name)
            config = self.worker_configs[worker_type]

            logger.info(f"🚀 워커 시작: {worker_type.value}")
            logger.info(f"   명령어: {' '.join(command)}")
            logger.info(f"   설명: {config.description}")

            # 워커 프로세스 시작
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # 실행 중인 워커 추가
            worker_id = f"{worker_type.value}_{process.pid}"
            self.running_workers[worker_id] = {
                'process': process,
                'worker_type': worker_type,
                'worker_name': worker_name or worker_id,
                'started_at': datetime.now(),
                'config': config
            }

            logger.info(f"✅ 워커 시작 완료: {worker_id} (PID: {process.pid})")
            return process

        except Exception as e:
            logger.error(f"❌ 워커 시작 실패: {worker_type.value}, 오류: {e}")
            return None

    def start_all_workers(self) -> Dict[str, bool]:
        """
        모든 워커 시작

        시스템 리소스에 맞게 모든 타입의 워커를 시작

        Returns:
            dict: 워커 타입별 시작 결과
        """
        results = {}

        for worker_type in WorkerType:
            try:
                process = self.start_worker(worker_type)
                results[worker_type.value] = process is not None

                # 워커 간 시작 지연 (리소스 충돌 방지)
                time.sleep(2)

            except Exception as e:
                logger.error(f"❌ {worker_type.value} 시작 실패: {e}")
                results[worker_type.value] = False

        success_count = sum(results.values())
        total_count = len(results)

        logger.info(f"🎯 워커 시작 완료: {success_count}/{total_count}")
        return results

    def stop_worker(self, worker_id: str) -> bool:
        """
        특정 워커 중지

        Args:
            worker_id: 워커 ID

        Returns:
            bool: 중지 성공 여부
        """
        if worker_id not in self.running_workers:
            logger.warning(f"⚠️ 워커를 찾을 수 없음: {worker_id}")
            return False

        try:
            worker_info = self.running_workers[worker_id]
            process = worker_info['process']

            logger.info(f"🛑 워커 중지 중: {worker_id}")

            # Graceful shutdown 시도
            process.terminate()

            # 10초 대기 후 강제 종료
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning(f"⚠️ Graceful shutdown 실패, 강제 종료: {worker_id}")
                process.kill()
                process.wait()

            # 워커 목록에서 제거
            del self.running_workers[worker_id]

            logger.info(f"✅ 워커 중지 완료: {worker_id}")
            return True

        except Exception as e:
            logger.error(f"❌ 워커 중지 실패: {worker_id}, 오류: {e}")
            return False

    def stop_all_workers(self) -> Dict[str, bool]:
        """
        모든 워커 중지

        Returns:
            dict: 워커별 중지 결과
        """
        results = {}
        worker_ids = list(self.running_workers.keys())

        for worker_id in worker_ids:
            results[worker_id] = self.stop_worker(worker_id)

        return results

    def get_worker_status(self) -> Dict[str, Any]:
        """
        워커 상태 조회

        Returns:
            dict: 워커 상태 정보
        """
        status = {
            'total_workers': len(self.running_workers),
            'workers': {},
            'system_info': self.system_info,
            'timestamp': datetime.now().isoformat()
        }

        for worker_id, worker_info in self.running_workers.items():
            process = worker_info['process']
            config = worker_info['config']

            # 프로세스 상태 확인
            is_running = process.poll() is None

            status['workers'][worker_id] = {
                'worker_type': worker_info['worker_type'].value,
                'worker_name': worker_info['worker_name'],
                'pid': process.pid,
                'is_running': is_running,
                'started_at': worker_info['started_at'].isoformat(),
                'queues': config.queues,
                'concurrency': config.concurrency,
                'description': config.description
            }

        return status

    def get_performance_recommendations(self) -> List[str]:
        """
        성능 최적화 권장사항

        시스템 상태를 기반으로 워커 설정 최적화 제안

        Returns:
            list: 권장사항 목록
        """
        recommendations = []
        cpu_usage = self.system_info['cpu_usage']
        memory_usage = self.system_info['memory_usage_percent']
        available_memory = self.system_info['available_memory_gb']

        # CPU 사용률 기반 권장사항
        if cpu_usage > 90:
            recommendations.append("🔴 높은 CPU 사용률 - analysis/statistics 워커 concurrency 감소 고려")
        elif cpu_usage < 30:
            recommendations.append("🟢 낮은 CPU 사용률 - 워커 concurrency 증가 가능")

        # 메모리 사용률 기반 권장사항
        if memory_usage > 85:
            recommendations.append("🔴 높은 메모리 사용률 - scraping 워커 max_memory_per_child 감소 필요")
        elif available_memory < 1.0:
            recommendations.append("⚠️ 사용 가능한 메모리 부족 - 워커 수 감소 고려")

        # 워커별 권장사항
        running_worker_types = set()
        for worker_info in self.running_workers.values():
            running_worker_types.add(worker_info['worker_type'])

        missing_critical_workers = []
        if WorkerType.SCRAPING not in running_worker_types:
            missing_critical_workers.append("scraping")
        if WorkerType.ANALYSIS not in running_worker_types:
            missing_critical_workers.append("analysis")

        if missing_critical_workers:
            recommendations.append(f"⚠️ 핵심 워커 누락: {', '.join(missing_critical_workers)}")

        if not recommendations:
            recommendations.append("✅ 워커 설정이 최적화되어 있습니다.")

        return recommendations

# 전역 인스턴스
worker_manager = WorkerManager()

def get_worker_manager() -> WorkerManager:
    """
    워커 매니저 인스턴스 반환

    Returns:
        WorkerManager: 워커 매니저 인스턴스
    """
    return worker_manager