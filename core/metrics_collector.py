"""
성능 메트릭 수집 시스템
Prometheus 메트릭 생성, 시스템 자원 모니터링, 비즈니스 메트릭 추적
"""

import time
import psutil
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict, deque
import logging
import json

# Prometheus 메트릭
from prometheus_client import (
    Counter, Histogram, Gauge, Summary,
    CollectorRegistry, generate_latest,
    CONTENT_TYPE_LATEST
)

logger = logging.getLogger(__name__)

@dataclass
class MetricSnapshot:
    """메트릭 스냅샷"""
    timestamp: datetime
    system_metrics: Dict[str, float] = field(default_factory=dict)
    application_metrics: Dict[str, float] = field(default_factory=dict)
    business_metrics: Dict[str, int] = field(default_factory=dict)

class SystemMetricsCollector:
    """
    시스템 자원 메트릭 수집기
    CPU, 메모리, 디스크, 네트워크 사용량 모니터링
    """

    def __init__(self):
        self.process = psutil.Process()
        self._last_network_io = psutil.net_io_counters()
        self._last_disk_io = psutil.disk_io_counters()
        self._last_check = time.time()

    def collect_system_metrics(self) -> Dict[str, float]:
        """시스템 메트릭 수집"""
        current_time = time.time()
        time_delta = current_time - self._last_check

        metrics = {}

        try:
            # CPU 사용률
            metrics['cpu_percent'] = psutil.cpu_percent(interval=None)
            metrics['cpu_count'] = psutil.cpu_count()

            # 메모리 사용률
            memory = psutil.virtual_memory()
            metrics['memory_percent'] = memory.percent
            metrics['memory_used_gb'] = memory.used / (1024**3)
            metrics['memory_available_gb'] = memory.available / (1024**3)
            metrics['memory_total_gb'] = memory.total / (1024**3)

            # 스왑 메모리
            swap = psutil.swap_memory()
            metrics['swap_percent'] = swap.percent
            metrics['swap_used_gb'] = swap.used / (1024**3)

            # 디스크 사용률
            disk = psutil.disk_usage('/')
            metrics['disk_percent'] = disk.percent
            metrics['disk_used_gb'] = disk.used / (1024**3)
            metrics['disk_free_gb'] = disk.free / (1024**3)

            # 디스크 I/O
            if self._last_disk_io and time_delta > 0:
                current_disk_io = psutil.disk_io_counters()
                if current_disk_io:
                    metrics['disk_read_rate'] = (
                        current_disk_io.read_bytes - self._last_disk_io.read_bytes
                    ) / time_delta / (1024**2)  # MB/s
                    metrics['disk_write_rate'] = (
                        current_disk_io.write_bytes - self._last_disk_io.write_bytes
                    ) / time_delta / (1024**2)  # MB/s
                    self._last_disk_io = current_disk_io

            # 네트워크 I/O
            if self._last_network_io and time_delta > 0:
                current_network_io = psutil.net_io_counters()
                if current_network_io:
                    metrics['network_recv_rate'] = (
                        current_network_io.bytes_recv - self._last_network_io.bytes_recv
                    ) / time_delta / (1024**2)  # MB/s
                    metrics['network_sent_rate'] = (
                        current_network_io.bytes_sent - self._last_network_io.bytes_sent
                    ) / time_delta / (1024**2)  # MB/s
                    self._last_network_io = current_network_io

            # 프로세스별 메트릭
            metrics['process_cpu_percent'] = self.process.cpu_percent()
            process_memory = self.process.memory_info()
            metrics['process_memory_mb'] = process_memory.rss / (1024**2)
            metrics['process_memory_percent'] = self.process.memory_percent()

            # 로드 애버리지 (Unix 계열만)
            if hasattr(psutil, 'getloadavg'):
                load_avg = psutil.getloadavg()
                metrics['load_avg_1m'] = load_avg[0]
                metrics['load_avg_5m'] = load_avg[1]
                metrics['load_avg_15m'] = load_avg[2]

        except Exception as e:
            logger.error(f"시스템 메트릭 수집 실패: {e}")

        self._last_check = current_time
        return metrics

class PrometheusMetrics:
    """
    Prometheus 메트릭 관리자
    애플리케이션 성능 지표를 Prometheus 형식으로 제공
    """

    def __init__(self):
        # 커스텀 레지스트리 사용
        self.registry = CollectorRegistry()

        # === HTTP 요청 메트릭 ===
        self.http_requests_total = Counter(
            'market_insights_http_requests_total',
            'Total HTTP requests',
            ['method', 'endpoint', 'status_code'],
            registry=self.registry
        )

        self.http_request_duration = Histogram(
            'market_insights_http_request_duration_seconds',
            'HTTP request duration',
            ['method', 'endpoint'],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=self.registry
        )

        # === 데이터베이스 메트릭 ===
        self.db_queries_total = Counter(
            'market_insights_db_queries_total',
            'Total database queries',
            ['query_type', 'table'],
            registry=self.registry
        )

        self.db_query_duration = Histogram(
            'market_insights_db_query_duration_seconds',
            'Database query duration',
            ['query_type'],
            registry=self.registry
        )

        self.db_connections_active = Gauge(
            'market_insights_db_connections_active',
            'Active database connections',
            ['connection_type'],
            registry=self.registry
        )

        # === 캐시 메트릭 ===
        self.cache_operations_total = Counter(
            'market_insights_cache_operations_total',
            'Total cache operations',
            ['operation', 'cache_type'],
            registry=self.registry
        )

        self.cache_hit_rate = Gauge(
            'market_insights_cache_hit_rate',
            'Cache hit rate',
            ['cache_type'],
            registry=self.registry
        )

        # === Celery 작업 메트릭 ===
        self.celery_tasks_total = Counter(
            'market_insights_celery_tasks_total',
            'Total Celery tasks',
            ['task_name', 'status'],
            registry=self.registry
        )

        self.celery_task_duration = Histogram(
            'market_insights_celery_task_duration_seconds',
            'Celery task duration',
            ['task_name'],
            registry=self.registry
        )

        self.celery_queue_size = Gauge(
            'market_insights_celery_queue_size',
            'Celery queue size',
            ['queue_name'],
            registry=self.registry
        )

        # === 비즈니스 메트릭 ===
        self.analysis_requests_total = Counter(
            'market_insights_analysis_requests_total',
            'Total analysis requests',
            ['keyword_category'],
            registry=self.registry
        )

        self.scraping_sessions_total = Counter(
            'market_insights_scraping_sessions_total',
            'Total scraping sessions',
            ['status'],
            registry=self.registry
        )

        self.active_users = Gauge(
            'market_insights_active_users',
            'Active users',
            registry=self.registry
        )

        # === 시스템 메트릭 ===
        self.system_cpu_percent = Gauge(
            'market_insights_system_cpu_percent',
            'System CPU usage percentage',
            registry=self.registry
        )

        self.system_memory_percent = Gauge(
            'market_insights_system_memory_percent',
            'System memory usage percentage',
            registry=self.registry
        )

        self.system_disk_percent = Gauge(
            'market_insights_system_disk_percent',
            'System disk usage percentage',
            registry=self.registry
        )

    def record_http_request(self, method: str, endpoint: str, status_code: int, duration: float):
        """HTTP 요청 메트릭 기록"""
        self.http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=str(status_code)
        ).inc()

        self.http_request_duration.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)

    def record_db_query(self, query_type: str, table: str, duration: float):
        """데이터베이스 쿼리 메트릭 기록"""
        self.db_queries_total.labels(
            query_type=query_type,
            table=table
        ).inc()

        self.db_query_duration.labels(
            query_type=query_type
        ).observe(duration)

    def update_db_connections(self, read_connections: int, write_connections: int):
        """데이터베이스 연결 수 업데이트"""
        self.db_connections_active.labels(connection_type='read').set(read_connections)
        self.db_connections_active.labels(connection_type='write').set(write_connections)

    def record_cache_operation(self, operation: str, cache_type: str):
        """캐시 작업 메트릭 기록"""
        self.cache_operations_total.labels(
            operation=operation,
            cache_type=cache_type
        ).inc()

    def update_cache_hit_rate(self, cache_type: str, hit_rate: float):
        """캐시 히트율 업데이트"""
        self.cache_hit_rate.labels(cache_type=cache_type).set(hit_rate)

    def record_celery_task(self, task_name: str, status: str, duration: float):
        """Celery 작업 메트릭 기록"""
        self.celery_tasks_total.labels(
            task_name=task_name,
            status=status
        ).inc()

        if duration > 0:
            self.celery_task_duration.labels(
                task_name=task_name
            ).observe(duration)

    def update_celery_queue_size(self, queue_name: str, size: int):
        """Celery 큐 크기 업데이트"""
        self.celery_queue_size.labels(queue_name=queue_name).set(size)

    def record_analysis_request(self, keyword_category: str):
        """분석 요청 메트릭 기록"""
        self.analysis_requests_total.labels(
            keyword_category=keyword_category
        ).inc()

    def record_scraping_session(self, status: str):
        """스크래핑 세션 메트릭 기록"""
        self.scraping_sessions_total.labels(status=status).inc()

    def update_active_users(self, count: int):
        """활성 사용자 수 업데이트"""
        self.active_users.set(count)

    def update_system_metrics(self, cpu_percent: float, memory_percent: float, disk_percent: float):
        """시스템 메트릭 업데이트"""
        self.system_cpu_percent.set(cpu_percent)
        self.system_memory_percent.set(memory_percent)
        self.system_disk_percent.set(disk_percent)

    def generate_metrics(self) -> str:
        """Prometheus 형식 메트릭 생성"""
        return generate_latest(self.registry).decode('utf-8')

class MetricsCollector:
    """
    통합 메트릭 수집기
    시스템, 애플리케이션, 비즈니스 메트릭을 수집하고 관리
    """

    def __init__(self, collection_interval: int = 15):
        self.collection_interval = collection_interval
        self.system_collector = SystemMetricsCollector()
        self.prometheus_metrics = PrometheusMetrics()

        # 메트릭 히스토리 (메모리에 최근 1000개 저장)
        self.metric_history: deque = deque(maxlen=1000)

        # 수집 통계
        self.collection_stats = {
            'total_collections': 0,
            'failed_collections': 0,
            'last_collection': None,
            'last_error': None
        }

        # 실시간 비즈니스 메트릭
        self.business_counters = defaultdict(int)
        self.user_sessions = set()

        # 백그라운드 수집 스레드
        self._collecting = False
        self._collection_thread = None

    def start_collection(self):
        """메트릭 수집 시작"""
        if not self._collecting:
            self._collecting = True
            self._collection_thread = threading.Thread(
                target=self._collection_loop,
                daemon=True
            )
            self._collection_thread.start()
            logger.info(f"메트릭 수집 시작 (간격: {self.collection_interval}초)")

    def stop_collection(self):
        """메트릭 수집 중지"""
        self._collecting = False
        if self._collection_thread:
            self._collection_thread.join(timeout=5)
        logger.info("메트릭 수집 중지")

    def _collection_loop(self):
        """메트릭 수집 루프"""
        while self._collecting:
            try:
                self.collect_metrics()
                self.collection_stats['total_collections'] += 1
                self.collection_stats['last_collection'] = datetime.now()

            except Exception as e:
                self.collection_stats['failed_collections'] += 1
                self.collection_stats['last_error'] = str(e)
                logger.error(f"메트릭 수집 실패: {e}")

            time.sleep(self.collection_interval)

    def collect_metrics(self):
        """메트릭 수집 실행"""
        timestamp = datetime.now()

        # 시스템 메트릭 수집
        system_metrics = self.system_collector.collect_system_metrics()

        # Prometheus 시스템 메트릭 업데이트
        if system_metrics:
            self.prometheus_metrics.update_system_metrics(
                cpu_percent=system_metrics.get('cpu_percent', 0),
                memory_percent=system_metrics.get('memory_percent', 0),
                disk_percent=system_metrics.get('disk_percent', 0)
            )

        # 애플리케이션 메트릭 수집
        application_metrics = self._collect_application_metrics()

        # 비즈니스 메트릭 수집
        business_metrics = dict(self.business_counters)

        # 스냅샷 생성 및 저장
        snapshot = MetricSnapshot(
            timestamp=timestamp,
            system_metrics=system_metrics,
            application_metrics=application_metrics,
            business_metrics=business_metrics
        )

        self.metric_history.append(snapshot)

        logger.debug(f"메트릭 수집 완료: {len(system_metrics)} 시스템, "
                    f"{len(application_metrics)} 애플리케이션, "
                    f"{len(business_metrics)} 비즈니스")

    def _collect_application_metrics(self) -> Dict[str, float]:
        """애플리케이션 메트릭 수집"""
        metrics = {}

        try:
            # 데이터베이스 연결 풀 상태
            from core.connection_pool import get_connection_pool
            pool = get_connection_pool()
            pool_stats = pool.get_pool_stats()

            metrics['db_active_connections'] = pool_stats.get('active_connections', 0)
            metrics['db_read_connections'] = pool_stats.get('read_connections_active', 0)
            metrics['db_write_connections'] = pool_stats.get('write_connections_active', 0)
            metrics['db_total_queries'] = pool_stats.get('read_queries', 0) + pool_stats.get('write_queries', 0)

            # Prometheus에 업데이트
            self.prometheus_metrics.update_db_connections(
                read_connections=metrics['db_read_connections'],
                write_connections=metrics['db_write_connections']
            )

        except Exception as e:
            logger.debug(f"데이터베이스 메트릭 수집 실패: {e}")

        try:
            # API 캐시 통계
            from core.api_optimizer import get_api_optimizer
            api_optimizer = get_api_optimizer()
            cache_stats = api_optimizer.get_cache_stats()

            metrics['api_cache_items'] = cache_stats.get('total_items', 0)
            metrics['api_cache_valid_items'] = cache_stats.get('valid_items', 0)
            metrics['api_cache_hit_rate'] = (
                cache_stats.get('valid_items', 0) / max(cache_stats.get('total_items', 1), 1)
            )

            # Prometheus에 업데이트
            self.prometheus_metrics.update_cache_hit_rate(
                cache_type='api',
                hit_rate=metrics['api_cache_hit_rate']
            )

        except Exception as e:
            logger.debug(f"API 캐시 메트릭 수집 실패: {e}")

        try:
            # Redis 캐시 통계
            from core.cache import get_cache_manager
            cache_manager = get_cache_manager()
            if cache_manager:
                redis_info = cache_manager.get_cache_stats()
                metrics['redis_used_memory'] = redis_info.get('used_memory', 0) / (1024**2)  # MB
                metrics['redis_connected_clients'] = redis_info.get('connected_clients', 0)
                metrics['redis_hit_rate'] = redis_info.get('keyspace_hits', 0) / max(
                    redis_info.get('keyspace_hits', 0) + redis_info.get('keyspace_misses', 0), 1
                )

        except Exception as e:
            logger.debug(f"Redis 메트릭 수집 실패: {e}")

        # 활성 사용자 수 업데이트
        self.prometheus_metrics.update_active_users(len(self.user_sessions))

        return metrics

    def record_user_session(self, session_id: str):
        """사용자 세션 추가"""
        self.user_sessions.add(session_id)

        # 오래된 세션 정리 (실제로는 더 정교한 로직 필요)
        if len(self.user_sessions) > 10000:  # 임의의 한계값
            self.user_sessions = set(list(self.user_sessions)[-5000:])

    def record_business_event(self, event_type: str, count: int = 1):
        """비즈니스 이벤트 기록"""
        self.business_counters[event_type] += count

    def get_current_metrics(self) -> Dict[str, Any]:
        """현재 메트릭 조회"""
        if not self.metric_history:
            return {}

        latest = self.metric_history[-1]
        return {
            'timestamp': latest.timestamp.isoformat(),
            'system': latest.system_metrics,
            'application': latest.application_metrics,
            'business': latest.business_metrics
        }

    def get_metrics_history(self, minutes: int = 60) -> List[Dict[str, Any]]:
        """메트릭 히스토리 조회"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)

        history = [
            {
                'timestamp': snapshot.timestamp.isoformat(),
                'system': snapshot.system_metrics,
                'application': snapshot.application_metrics,
                'business': snapshot.business_metrics
            }
            for snapshot in self.metric_history
            if snapshot.timestamp >= cutoff_time
        ]

        return history

    def get_collection_stats(self) -> Dict[str, Any]:
        """수집 통계 조회"""
        stats = dict(self.collection_stats)
        if stats['last_collection']:
            stats['last_collection'] = stats['last_collection'].isoformat()

        stats['success_rate'] = (
            (stats['total_collections'] - stats['failed_collections']) /
            max(stats['total_collections'], 1)
        )

        return stats

    def export_prometheus_metrics(self) -> str:
        """Prometheus 형식 메트릭 내보내기"""
        return self.prometheus_metrics.generate_metrics()

# 전역 메트릭 수집기 인스턴스
_metrics_collector: Optional[MetricsCollector] = None

def get_metrics_collector() -> MetricsCollector:
    """메트릭 수집기 인스턴스 반환"""
    global _metrics_collector

    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
        _metrics_collector.start_collection()

    return _metrics_collector

def record_http_request_metric(method: str, endpoint: str, status_code: int, duration: float):
    """HTTP 요청 메트릭 기록 헬퍼"""
    collector = get_metrics_collector()
    collector.prometheus_metrics.record_http_request(method, endpoint, status_code, duration)

def record_analysis_request_metric(keyword: str):
    """분석 요청 메트릭 기록 헬퍼"""
    collector = get_metrics_collector()

    # 키워드 카테고리 분류 (간단한 예시)
    category = 'electronics'  # 실제로는 더 정교한 분류 로직
    if 'phone' in keyword.lower() or 'mobile' in keyword.lower():
        category = 'mobile'
    elif 'laptop' in keyword.lower() or 'computer' in keyword.lower():
        category = 'computer'
    elif 'headphone' in keyword.lower() or 'speaker' in keyword.lower():
        category = 'audio'

    collector.prometheus_metrics.record_analysis_request(category)
    collector.record_business_event('analysis_requests')

if __name__ == '__main__':
    # 테스트 실행
    collector = MetricsCollector(collection_interval=5)
    collector.start_collection()

    try:
        # 테스트 메트릭 생성
        for i in range(10):
            collector.record_user_session(f"test_user_{i}")
            collector.record_business_event('test_events', 1)
            time.sleep(1)

        # 결과 출력
        print("현재 메트릭:")
        current = collector.get_current_metrics()
        print(json.dumps(current, indent=2, default=str))

        print("\nPrometheus 메트릭:")
        print(collector.export_prometheus_metrics())

    finally:
        collector.stop_collection()