"""
우선순위 큐 시스템
작업 중요도에 따른 효율적인 작업 스케줄링
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class Priority(Enum):
    """
    작업 우선순위 레벨

    우선순위가 높을수록 먼저 처리됨
    """
    CRITICAL = 10    # 시스템 중요 작업 (헬스체크, 오류 복구)
    HIGH = 8        # 사용자 대면 작업 (스크래핑, 분석)
    NORMAL = 5      # 일반 작업 (보고서 생성, 캐시 업데이트)
    LOW = 3         # 백그라운드 작업 (통계, 데이터 정리)
    BATCH = 1       # 배치 작업 (대량 처리, 정리 작업)

@dataclass
class TaskInfo:
    """
    작업 정보 클래스

    각 작업의 메타데이터를 관리
    """
    task_name: str
    priority: Priority
    queue_name: str
    max_retries: int = 3
    retry_delay: int = 60
    timeout: int = 300  # 5분 기본 타임아웃
    description: str = ""
    tags: Dict[str, str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = {}

class PriorityQueueManager:
    """
    우선순위 큐 관리자

    작업 타입별 우선순위와 큐 라우팅을 중앙 관리
    """

    def __init__(self):
        """
        우선순위 큐 매니저 초기화

        작업별 우선순위와 큐 설정을 정의
        """
        self.task_configs = self._initialize_task_configs()
        self.queue_stats = {}  # 큐별 통계

    def _initialize_task_configs(self) -> Dict[str, TaskInfo]:
        """
        작업별 설정 초기화

        모든 Celery 작업의 우선순위와 큐 설정 정의
        """
        return {
            # === 🔥 CRITICAL 우선순위 ===
            'health_check': TaskInfo(
                task_name='health_check',
                priority=Priority.CRITICAL,
                queue_name='critical',
                max_retries=1,
                retry_delay=10,
                timeout=30,
                description="시스템 헬스체크",
                tags={'category': 'system', 'urgent': 'true'}
            ),

            # === 🚨 HIGH 우선순위 (사용자 대면) ===
            'scrape_product_data': TaskInfo(
                task_name='scrape_product_data',
                priority=Priority.HIGH,
                queue_name='scraping',
                max_retries=3,
                retry_delay=60,
                timeout=600,  # 10분
                description="Amazon 제품 데이터 스크래핑",
                tags={'category': 'scraping', 'user_facing': 'true'}
            ),

            'scrape_and_analyze': TaskInfo(
                task_name='scrape_and_analyze',
                priority=Priority.HIGH,
                queue_name='scraping',
                max_retries=2,
                retry_delay=120,
                timeout=900,  # 15분
                description="스크래핑 + 분석 통합 작업",
                tags={'category': 'scraping', 'user_facing': 'true', 'complex': 'true'}
            ),

            'analyze_market_data': TaskInfo(
                task_name='analyze_market_data',
                priority=Priority.HIGH,
                queue_name='analysis',
                max_retries=3,
                retry_delay=30,
                timeout=300,
                description="시장 데이터 분석",
                tags={'category': 'analysis', 'user_facing': 'true'}
            ),

            # === 📊 NORMAL 우선순위 (일반 작업) ===
            'generate_report': TaskInfo(
                task_name='generate_report',
                priority=Priority.NORMAL,
                queue_name='analysis',
                max_retries=2,
                retry_delay=60,
                timeout=180,
                description="보고서 생성",
                tags={'category': 'reporting', 'user_facing': 'false'}
            ),

            'send_notification_email': TaskInfo(
                task_name='send_notification_email',
                priority=Priority.NORMAL,
                queue_name='notifications',
                max_retries=5,
                retry_delay=30,
                timeout=60,
                description="이메일 알림 발송",
                tags={'category': 'notification', 'type': 'email'}
            ),

            'send_slack_notification': TaskInfo(
                task_name='send_slack_notification',
                priority=Priority.NORMAL,
                queue_name='notifications',
                max_retries=3,
                retry_delay=30,
                timeout=30,
                description="Slack 알림 발송",
                tags={'category': 'notification', 'type': 'slack'}
            ),

            # === 📈 LOW 우선순위 (백그라운드 작업) ===
            'update_statistics': TaskInfo(
                task_name='update_statistics',
                priority=Priority.LOW,
                queue_name='statistics',
                max_retries=2,
                retry_delay=300,  # 5분
                timeout=120,
                description="통계 데이터 업데이트",
                tags={'category': 'statistics', 'background': 'true'}
            ),

            # === 🧹 BATCH 우선순위 (배치 작업) ===
            'cleanup_old_data': TaskInfo(
                task_name='cleanup_old_data',
                priority=Priority.BATCH,
                queue_name='maintenance',
                max_retries=1,
                retry_delay=3600,  # 1시간
                timeout=1800,  # 30분
                description="오래된 데이터 정리",
                tags={'category': 'maintenance', 'batch': 'true'}
            ),
        }

    def get_task_config(self, task_name: str) -> Optional[TaskInfo]:
        """
        작업 설정 조회

        Args:
            task_name: 작업 이름

        Returns:
            TaskInfo: 작업 설정 정보 또는 None
        """
        return self.task_configs.get(task_name)

    def get_queue_priority_order(self) -> List[str]:
        """
        큐별 우선순위 순서 반환

        워커가 처리할 큐의 우선순위 순서
        """
        queue_priorities = {}

        for task_info in self.task_configs.values():
            queue_name = task_info.queue_name
            priority_value = task_info.priority.value

            if queue_name not in queue_priorities:
                queue_priorities[queue_name] = priority_value
            else:
                # 가장 높은 우선순위로 설정
                queue_priorities[queue_name] = max(
                    queue_priorities[queue_name],
                    priority_value
                )

        # 우선순위 순으로 정렬
        sorted_queues = sorted(
            queue_priorities.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return [queue_name for queue_name, _ in sorted_queues]

    def get_celery_route_config(self) -> Dict[str, Dict[str, Any]]:
        """
        Celery 라우팅 설정 생성

        우선순위 설정을 Celery 설정으로 변환
        Topic Exchange를 사용한 라우팅 키 기반 작업 분산

        Returns:
            dict: Celery task_routes 설정
        """
        routes = {}

        for task_name, task_info in self.task_configs.items():
            # 라우팅 키 패턴: 우선순위.큐.작업명
            # 예: high.scraping.scrape_product_data
            priority_name = task_info.priority.name.lower()
            routing_key = f'{priority_name}.{task_info.queue_name}.{task_name}'

            routes[f'core.tasks.{task_name}'] = {
                'queue': task_info.queue_name,
                'exchange': 'market_insights',
                'exchange_type': 'topic',
                'routing_key': routing_key,
                'priority': task_info.priority.value,
                # 추가 라우팅 옵션
                'options': {
                    'delivery_mode': 2,  # 메시지 영구 저장
                    'retry': True,
                    'retry_policy': {
                        'max_retries': task_info.max_retries,
                        'interval_start': task_info.retry_delay,
                        'interval_step': 30,
                        'interval_max': 300,
                    }
                }
            }

        return routes

    def get_task_annotations(self) -> Dict[str, Dict[str, Any]]:
        """
        Celery 작업 어노테이션 생성

        작업별 재시도, 타임아웃 등의 설정

        Returns:
            dict: Celery task_annotations 설정
        """
        annotations = {}

        for task_name, task_info in self.task_configs.items():
            annotations[f'core.tasks.{task_name}'] = {
                'max_retries': task_info.max_retries,
                'default_retry_delay': task_info.retry_delay,
                'time_limit': task_info.timeout,
                'soft_time_limit': task_info.timeout - 30,  # 30초 여유
                'rate_limit': self._get_rate_limit(task_info)
            }

        return annotations

    def _get_rate_limit(self, task_info: TaskInfo) -> str:
        """
        작업별 속도 제한 계산

        우선순위와 작업 특성에 따른 속도 제한 설정
        """
        if task_info.priority == Priority.CRITICAL:
            return '100/m'  # 분당 100개 (제한 없음에 가까움)
        elif task_info.priority == Priority.HIGH:
            if 'scraping' in task_info.tags.get('category', ''):
                return '10/m'  # 스크래핑은 엄격하게
            else:
                return '30/m'
        elif task_info.priority == Priority.NORMAL:
            return '20/m'
        elif task_info.priority == Priority.LOW:
            return '10/m'
        else:  # BATCH
            return '5/m'

    def record_task_execution(self, task_name: str, queue_name: str,
                            status: str, execution_time: float):
        """
        작업 실행 통계 기록

        Args:
            task_name: 작업 이름
            queue_name: 큐 이름
            status: 실행 상태 (success, failed, retry)
            execution_time: 실행 시간 (초)
        """
        if queue_name not in self.queue_stats:
            self.queue_stats[queue_name] = {
                'total_tasks': 0,
                'successful_tasks': 0,
                'failed_tasks': 0,
                'retry_tasks': 0,
                'total_execution_time': 0.0,
                'avg_execution_time': 0.0,
                'last_updated': None
            }

        stats = self.queue_stats[queue_name]
        stats['total_tasks'] += 1
        stats['total_execution_time'] += execution_time

        if status == 'success':
            stats['successful_tasks'] += 1
        elif status == 'failed':
            stats['failed_tasks'] += 1
        elif status == 'retry':
            stats['retry_tasks'] += 1

        # 평균 실행 시간 계산
        stats['avg_execution_time'] = stats['total_execution_time'] / stats['total_tasks']
        stats['last_updated'] = datetime.now().isoformat()

        logger.info(f"📊 작업 통계 업데이트: {queue_name}/{task_name} - {status} ({execution_time:.2f}s)")

    def get_queue_statistics(self) -> Dict[str, Any]:
        """
        큐별 통계 조회

        Returns:
            dict: 큐별 실행 통계
        """
        return {
            'queue_stats': self.queue_stats,
            'priority_order': self.get_queue_priority_order(),
            'total_queues': len(self.queue_stats),
            'generated_at': datetime.now().isoformat()
        }

    def suggest_queue_optimization(self) -> List[str]:
        """
        큐 최적화 제안

        통계를 기반으로 큐 설정 개선 제안

        Returns:
            list: 최적화 제안 목록
        """
        suggestions = []

        for queue_name, stats in self.queue_stats.items():
            total_tasks = stats['total_tasks']
            if total_tasks == 0:
                continue

            success_rate = stats['successful_tasks'] / total_tasks
            retry_rate = stats['retry_tasks'] / total_tasks
            avg_time = stats['avg_execution_time']

            # 성공률이 낮은 큐
            if success_rate < 0.8:
                suggestions.append(
                    f"🔴 {queue_name}: 성공률 낮음 ({success_rate:.1%}) - 재시도 정책 검토 필요"
                )

            # 재시도율이 높은 큐
            if retry_rate > 0.3:
                suggestions.append(
                    f"🟡 {queue_name}: 재시도율 높음 ({retry_rate:.1%}) - 작업 안정성 개선 필요"
                )

            # 실행 시간이 긴 큐
            if avg_time > 300:  # 5분 초과
                suggestions.append(
                    f"⏱️ {queue_name}: 평균 실행시간 길음 ({avg_time:.1f}s) - 성능 최적화 고려"
                )

        if not suggestions:
            suggestions.append("✅ 모든 큐가 정상적으로 작동 중입니다.")

        return suggestions

# 전역 인스턴스
priority_queue_manager = PriorityQueueManager()

def get_priority_queue_manager() -> PriorityQueueManager:
    """
    우선순위 큐 매니저 인스턴스 반환

    싱글톤 패턴으로 전역에서 동일한 인스턴스 사용
    """
    return priority_queue_manager