"""
작업 진행률 추적 시스템
실시간으로 작업 진행 상황을 추적하고 사용자에게 업데이트 제공
"""

import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from core.cache import get_cache_manager

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """
    작업 상태 정의
    """
    PENDING = "pending"          # 대기 중
    STARTED = "started"          # 시작됨
    PROGRESS = "progress"        # 진행 중
    SUCCESS = "success"          # 성공
    FAILURE = "failure"          # 실패
    RETRY = "retry"             # 재시도
    REVOKED = "revoked"         # 취소됨

@dataclass
class TaskProgress:
    """
    작업 진행 정보 클래스
    """
    task_id: str
    task_name: str
    status: TaskStatus
    current: int = 0             # 현재 진행량
    total: int = 100             # 전체 작업량
    message: str = ""            # 진행 메시지
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.updated_at is None:
            self.updated_at = datetime.now().isoformat()

    @property
    def progress_percentage(self) -> float:
        """진행률 백분율 계산"""
        if self.total <= 0:
            return 0.0
        return min(100.0, (self.current / self.total) * 100)

    @property
    def is_completed(self) -> bool:
        """작업 완료 여부"""
        return self.status in [TaskStatus.SUCCESS, TaskStatus.FAILURE, TaskStatus.REVOKED]

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        data = asdict(self)
        data['status'] = self.status.value
        data['progress_percentage'] = self.progress_percentage
        data['is_completed'] = self.is_completed
        return data

class TaskTracker:
    """
    작업 추적 관리자

    Redis를 사용하여 작업 진행 상황을 저장하고 실시간 업데이트 제공
    """

    def __init__(self):
        """
        작업 추적기 초기화
        """
        self.cache_manager = None
        self.websocket_callbacks: Dict[str, List[Callable]] = {}  # 작업별 WebSocket 콜백
        self.task_cache_prefix = "task_progress"
        self.task_ttl = 3600  # 1시간

        # Redis 연결 초기화
        self._initialize_cache()

    def _initialize_cache(self):
        """Redis 캐시 연결 초기화"""
        try:
            self.cache_manager = get_cache_manager()
            logger.info("✅ TaskTracker Redis 연결 성공")
        except Exception as e:
            logger.warning(f"⚠️ TaskTracker Redis 연결 실패: {e}")
            self.cache_manager = None

    def _get_cache_key(self, task_id: str) -> str:
        """캐시 키 생성"""
        return f"{self.task_cache_prefix}:{task_id}"

    def create_task(self, task_id: str, task_name: str,
                   total: int = 100, metadata: Dict[str, Any] = None) -> TaskProgress:
        """
        새 작업 추적 생성

        Args:
            task_id: 작업 ID (Celery task ID)
            task_name: 작업 이름
            total: 전체 작업량
            metadata: 추가 메타데이터

        Returns:
            TaskProgress: 생성된 작업 정보
        """
        progress = TaskProgress(
            task_id=task_id,
            task_name=task_name,
            status=TaskStatus.PENDING,
            total=total,
            started_at=datetime.now().isoformat(),
            metadata=metadata or {}
        )

        self._save_progress(progress)

        logger.info(f"📋 작업 추적 생성: {task_name} ({task_id})")
        return progress

    def start_task(self, task_id: str, message: str = "작업을 시작합니다") -> bool:
        """
        작업 시작 표시

        Args:
            task_id: 작업 ID
            message: 시작 메시지

        Returns:
            bool: 업데이트 성공 여부
        """
        progress = self._load_progress(task_id)
        if not progress:
            logger.warning(f"⚠️ 작업을 찾을 수 없음: {task_id}")
            return False

        progress.status = TaskStatus.STARTED
        progress.message = message
        progress.started_at = datetime.now().isoformat()
        progress.updated_at = datetime.now().isoformat()

        self._save_progress(progress)
        self._notify_websockets(task_id, progress)

        logger.info(f"🚀 작업 시작: {progress.task_name} ({task_id})")
        return True

    def update_progress(self, task_id: str, current: int,
                       message: str = "", metadata: Dict[str, Any] = None) -> bool:
        """
        작업 진행률 업데이트

        Args:
            task_id: 작업 ID
            current: 현재 진행량
            message: 진행 메시지
            metadata: 추가 메타데이터

        Returns:
            bool: 업데이트 성공 여부
        """
        progress = self._load_progress(task_id)
        if not progress:
            logger.warning(f"⚠️ 작업을 찾을 수 없음: {task_id}")
            return False

        progress.status = TaskStatus.PROGRESS
        progress.current = current
        if message:
            progress.message = message
        if metadata:
            progress.metadata.update(metadata)
        progress.updated_at = datetime.now().isoformat()

        self._save_progress(progress)
        self._notify_websockets(task_id, progress)

        logger.debug(f"📊 진행률 업데이트: {progress.task_name} ({current}/{progress.total})")
        return True

    def complete_task(self, task_id: str, success: bool = True,
                     message: str = "", error_message: str = "",
                     result_data: Dict[str, Any] = None) -> bool:
        """
        작업 완료 처리

        Args:
            task_id: 작업 ID
            success: 성공 여부
            message: 완료 메시지
            error_message: 오류 메시지 (실패시)
            result_data: 결과 데이터

        Returns:
            bool: 업데이트 성공 여부
        """
        progress = self._load_progress(task_id)
        if not progress:
            logger.warning(f"⚠️ 작업을 찾을 수 없음: {task_id}")
            return False

        progress.status = TaskStatus.SUCCESS if success else TaskStatus.FAILURE
        progress.current = progress.total  # 100% 완료
        progress.message = message or ("작업이 완료되었습니다" if success else "작업이 실패했습니다")
        progress.completed_at = datetime.now().isoformat()
        progress.updated_at = datetime.now().isoformat()

        if not success and error_message:
            progress.error_message = error_message

        if result_data:
            progress.metadata.update(result_data)

        self._save_progress(progress)
        self._notify_websockets(task_id, progress)

        status_icon = "✅" if success else "❌"
        logger.info(f"{status_icon} 작업 완료: {progress.task_name} ({task_id})")
        return True

    def retry_task(self, task_id: str, retry_count: int,
                  message: str = "") -> bool:
        """
        작업 재시도 표시

        Args:
            task_id: 작업 ID
            retry_count: 재시도 횟수
            message: 재시도 메시지

        Returns:
            bool: 업데이트 성공 여부
        """
        progress = self._load_progress(task_id)
        if not progress:
            return False

        progress.status = TaskStatus.RETRY
        progress.message = message or f"재시도 중... ({retry_count}번째)"
        progress.metadata['retry_count'] = retry_count
        progress.updated_at = datetime.now().isoformat()

        self._save_progress(progress)
        self._notify_websockets(task_id, progress)

        logger.info(f"🔄 작업 재시도: {progress.task_name} ({retry_count}번째)")
        return True

    def get_task_progress(self, task_id: str) -> Optional[TaskProgress]:
        """
        작업 진행 상황 조회

        Args:
            task_id: 작업 ID

        Returns:
            TaskProgress: 작업 진행 정보 또는 None
        """
        return self._load_progress(task_id)

    def get_all_active_tasks(self) -> List[TaskProgress]:
        """
        모든 활성 작업 조회

        Returns:
            list: 활성 작업 목록
        """
        if not self.cache_manager:
            return []

        try:
            # Redis에서 모든 작업 키 조회
            pattern = f"{self.task_cache_prefix}:*"
            keys = self.cache_manager.redis_client.keys(pattern)

            active_tasks = []
            for key in keys:
                task_id = key.split(':')[-1]
                progress = self._load_progress(task_id)
                if progress and not progress.is_completed:
                    active_tasks.append(progress)

            # 시작 시간 순으로 정렬
            active_tasks.sort(key=lambda x: x.started_at or "")
            return active_tasks

        except Exception as e:
            logger.error(f"❌ 활성 작업 조회 실패: {e}")
            return []

    def cleanup_completed_tasks(self, hours_old: int = 24) -> int:
        """
        완료된 오래된 작업 정리

        Args:
            hours_old: 정리할 작업의 나이 (시간)

        Returns:
            int: 정리된 작업 수
        """
        if not self.cache_manager:
            return 0

        try:
            cutoff_time = datetime.now() - timedelta(hours=hours_old)
            pattern = f"{self.task_cache_prefix}:*"
            keys = self.cache_manager.redis_client.keys(pattern)

            cleaned_count = 0
            for key in keys:
                task_id = key.split(':')[-1]
                progress = self._load_progress(task_id)

                if progress and progress.is_completed:
                    completed_time = datetime.fromisoformat(progress.completed_at or progress.updated_at)
                    if completed_time < cutoff_time:
                        self.cache_manager.redis_client.delete(key)
                        cleaned_count += 1

            logger.info(f"🧹 완료된 작업 정리: {cleaned_count}개")
            return cleaned_count

        except Exception as e:
            logger.error(f"❌ 작업 정리 실패: {e}")
            return 0

    def register_websocket_callback(self, task_id: str, callback: Callable):
        """
        WebSocket 콜백 등록

        Args:
            task_id: 작업 ID
            callback: 콜백 함수
        """
        if task_id not in self.websocket_callbacks:
            self.websocket_callbacks[task_id] = []

        self.websocket_callbacks[task_id].append(callback)
        logger.debug(f"📡 WebSocket 콜백 등록: {task_id}")

    def unregister_websocket_callback(self, task_id: str, callback: Callable):
        """
        WebSocket 콜백 해제

        Args:
            task_id: 작업 ID
            callback: 콜백 함수
        """
        if task_id in self.websocket_callbacks:
            try:
                self.websocket_callbacks[task_id].remove(callback)
                if not self.websocket_callbacks[task_id]:
                    del self.websocket_callbacks[task_id]
                logger.debug(f"📡 WebSocket 콜백 해제: {task_id}")
            except ValueError:
                pass

    def get_task_statistics(self) -> Dict[str, Any]:
        """
        작업 통계 조회

        Returns:
            dict: 작업 통계 정보
        """
        if not self.cache_manager:
            return {'error': 'Redis 연결 없음'}

        try:
            pattern = f"{self.task_cache_prefix}:*"
            keys = self.cache_manager.redis_client.keys(pattern)

            stats = {
                'total_tasks': len(keys),
                'active_tasks': 0,
                'completed_tasks': 0,
                'failed_tasks': 0,
                'status_breakdown': {},
                'task_types': {},
                'generated_at': datetime.now().isoformat()
            }

            for key in keys:
                task_id = key.split(':')[-1]
                progress = self._load_progress(task_id)

                if not progress:
                    continue

                # 상태별 통계
                status = progress.status.value
                stats['status_breakdown'][status] = stats['status_breakdown'].get(status, 0) + 1

                # 작업 타입별 통계
                task_type = progress.task_name
                stats['task_types'][task_type] = stats['task_types'].get(task_type, 0) + 1

                # 활성/완료/실패 카운트
                if progress.status == TaskStatus.SUCCESS:
                    stats['completed_tasks'] += 1
                elif progress.status == TaskStatus.FAILURE:
                    stats['failed_tasks'] += 1
                elif not progress.is_completed:
                    stats['active_tasks'] += 1

            return stats

        except Exception as e:
            logger.error(f"❌ 작업 통계 조회 실패: {e}")
            return {'error': str(e)}

    def _save_progress(self, progress: TaskProgress):
        """진행 상황을 Redis에 저장"""
        if not self.cache_manager:
            return

        try:
            cache_key = self._get_cache_key(progress.task_id)
            progress_data = json.dumps(progress.to_dict(), ensure_ascii=False)

            self.cache_manager.redis_client.setex(
                cache_key,
                self.task_ttl,
                progress_data
            )

        except Exception as e:
            logger.error(f"❌ 진행 상황 저장 실패: {e}")

    def _load_progress(self, task_id: str) -> Optional[TaskProgress]:
        """Redis에서 진행 상황 로드"""
        if not self.cache_manager:
            return None

        try:
            cache_key = self._get_cache_key(task_id)
            progress_data = self.cache_manager.redis_client.get(cache_key)

            if not progress_data:
                return None

            data = json.loads(progress_data)
            data['status'] = TaskStatus(data['status'])

            # TaskProgress 객체 재구성
            progress = TaskProgress(
                task_id=data['task_id'],
                task_name=data['task_name'],
                status=data['status'],
                current=data['current'],
                total=data['total'],
                message=data['message'],
                started_at=data.get('started_at'),
                updated_at=data.get('updated_at'),
                completed_at=data.get('completed_at'),
                error_message=data.get('error_message'),
                metadata=data.get('metadata', {})
            )

            return progress

        except Exception as e:
            logger.error(f"❌ 진행 상황 로드 실패: {e}")
            return None

    def _notify_websockets(self, task_id: str, progress: TaskProgress):
        """WebSocket 콜백 호출"""
        if task_id not in self.websocket_callbacks:
            return

        progress_data = progress.to_dict()

        # 모든 등록된 콜백 호출
        callbacks_to_remove = []
        for callback in self.websocket_callbacks[task_id]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    # 비동기 함수는 백그라운드에서 실행
                    asyncio.create_task(callback(progress_data))
                else:
                    # 동기 함수는 직접 호출
                    callback(progress_data)

            except Exception as e:
                logger.error(f"❌ WebSocket 콜백 실행 실패: {e}")
                callbacks_to_remove.append(callback)

        # 실패한 콜백 제거
        for callback in callbacks_to_remove:
            self.unregister_websocket_callback(task_id, callback)

# 전역 인스턴스
task_tracker = TaskTracker()

def get_task_tracker() -> TaskTracker:
    """
    작업 추적기 인스턴스 반환

    Returns:
        TaskTracker: 작업 추적기 인스턴스
    """
    return task_tracker