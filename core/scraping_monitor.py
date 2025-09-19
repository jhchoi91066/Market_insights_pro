# -*- coding: utf-8 -*-
"""
Market Insights Pro - 실시간 스크래핑 모니터링 시스템
Amazon 스크래핑 작업의 실시간 상태 모니터링 및 대시보드

주요 기능:
- 실시간 스크래핑 상태 추적
- 성능 메트릭 모니터링
- 에러 및 경고 알림
- 품질 지표 시각화
- WebSocket 기반 실시간 업데이트
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import threading
import time
from collections import deque, defaultdict

logger = logging.getLogger(__name__)

class ScrapingStatus(Enum):
    """스크래핑 상태"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    COMPLETED = "completed"

class AlertLevel(Enum):
    """알림 수준"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class ScrapingSession:
    """스크래핑 세션 정보"""
    session_id: str
    keyword: str
    status: ScrapingStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    products_found: int = 0
    products_processed: int = 0
    products_valid: int = 0
    current_page: int = 1
    error_count: int = 0
    last_activity: datetime = field(default_factory=datetime.now)

@dataclass
class PerformanceMetrics:
    """성능 메트릭"""
    timestamp: datetime
    products_per_minute: float = 0.0
    success_rate: float = 0.0
    error_rate: float = 0.0
    average_response_time: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0

@dataclass
class QualityMetrics:
    """품질 메트릭"""
    timestamp: datetime
    data_quality_score: float = 0.0
    title_validity_rate: float = 0.0
    price_validity_rate: float = 0.0
    rating_validity_rate: float = 0.0
    duplicate_rate: float = 0.0

@dataclass
class Alert:
    """알림 정보"""
    id: str
    level: AlertLevel
    title: str
    message: str
    timestamp: datetime
    session_id: Optional[str] = None
    acknowledged: bool = False

class ScrapingMonitor:
    """
    실시간 스크래핑 모니터링 시스템

    스크래핑 작업의 모든 측면을 실시간으로 모니터링하고
    문제 발생 시 즉시 알림을 제공합니다.
    """

    def __init__(self, max_history: int = 1000):
        self.active_sessions: Dict[str, ScrapingSession] = {}
        self.completed_sessions: List[ScrapingSession] = []
        self.performance_history: deque = deque(maxlen=max_history)
        self.quality_history: deque = deque(maxlen=max_history)
        self.alerts: List[Alert] = []
        self.websocket_clients: List = []

        # 실시간 통계
        self.real_time_stats = {
            "total_sessions": 0,
            "active_sessions": 0,
            "total_products": 0,
            "products_today": 0,
            "average_quality_score": 0.0,
            "uptime_hours": 0.0
        }

        # 모니터링 시작 시간
        self.start_time = datetime.now()

        # 백그라운드 모니터링 태스크
        self._monitoring_task = None
        self._running = False

    async def start_monitoring(self):
        """모니터링 시작"""
        if self._running:
            return

        self._running = True
        self._monitoring_task = asyncio.create_task(self._background_monitoring())
        logger.info("📊 스크래핑 모니터링 시작")

    async def stop_monitoring(self):
        """모니터링 중지"""
        self._running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("📊 스크래핑 모니터링 중지")

    async def _background_monitoring(self):
        """백그라운드 모니터링 루프"""
        while self._running:
            try:
                await self._collect_system_metrics()
                await self._check_alerts()
                await self._update_real_time_stats()
                await self._broadcast_updates()
                await asyncio.sleep(5)  # 5초마다 업데이트
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"모니터링 루프 에러: {e}")
                await asyncio.sleep(10)

    def start_session(self, session_id: str, keyword: str) -> ScrapingSession:
        """새 스크래핑 세션 시작"""
        session = ScrapingSession(
            session_id=session_id,
            keyword=keyword,
            status=ScrapingStatus.RUNNING,
            start_time=datetime.now()
        )

        self.active_sessions[session_id] = session
        self.real_time_stats["total_sessions"] += 1
        self.real_time_stats["active_sessions"] += 1

        self._create_alert(
            AlertLevel.INFO,
            "세션 시작",
            f"키워드 '{keyword}'로 스크래핑 세션 시작",
            session_id
        )

        logger.info(f"📋 세션 시작: {session_id} (키워드: {keyword})")
        return session

    def update_session_progress(
        self,
        session_id: str,
        products_found: int = None,
        products_processed: int = None,
        products_valid: int = None,
        current_page: int = None,
        error_count: int = None
    ):
        """세션 진행상황 업데이트"""
        if session_id not in self.active_sessions:
            return

        session = self.active_sessions[session_id]

        if products_found is not None:
            session.products_found = products_found
        if products_processed is not None:
            session.products_processed = products_processed
        if products_valid is not None:
            session.products_valid = products_valid
        if current_page is not None:
            session.current_page = current_page
        if error_count is not None:
            session.error_count = error_count

        session.last_activity = datetime.now()

        # 에러율 체크
        if session.products_processed > 0:
            error_rate = session.error_count / session.products_processed
            if error_rate > 0.3:  # 30% 이상 에러
                self._create_alert(
                    AlertLevel.WARNING,
                    "높은 에러율",
                    f"세션 {session_id}의 에러율이 {error_rate*100:.1f}%입니다",
                    session_id
                )

    def complete_session(self, session_id: str, status: ScrapingStatus = ScrapingStatus.COMPLETED):
        """세션 완료"""
        if session_id not in self.active_sessions:
            return

        session = self.active_sessions[session_id]
        session.status = status
        session.end_time = datetime.now()

        # 완료된 세션으로 이동
        self.completed_sessions.append(session)
        del self.active_sessions[session_id]

        self.real_time_stats["active_sessions"] -= 1
        self.real_time_stats["total_products"] += session.products_valid

        # 성능 알림
        duration = session.end_time - session.start_time
        if duration.total_seconds() > 0:
            products_per_minute = session.products_valid / (duration.total_seconds() / 60)

            alert_level = AlertLevel.INFO
            if products_per_minute < 1:  # 분당 1개 미만
                alert_level = AlertLevel.WARNING

            self._create_alert(
                alert_level,
                "세션 완료",
                f"세션 {session_id} 완료: {session.products_valid}개 상품 수집 "
                f"(분당 {products_per_minute:.1f}개)",
                session_id
            )

        logger.info(f"✅ 세션 완료: {session_id}")

    def record_performance_metrics(self, metrics: PerformanceMetrics):
        """성능 메트릭 기록"""
        self.performance_history.append(metrics)

        # 성능 임계값 체크
        if metrics.success_rate < 70:  # 성공률 70% 미만
            self._create_alert(
                AlertLevel.WARNING,
                "낮은 성공률",
                f"현재 성공률이 {metrics.success_rate:.1f}%입니다"
            )

        if metrics.average_response_time > 10:  # 평균 응답시간 10초 초과
            self._create_alert(
                AlertLevel.WARNING,
                "느린 응답시간",
                f"평균 응답시간이 {metrics.average_response_time:.1f}초입니다"
            )

    def record_quality_metrics(self, metrics: QualityMetrics):
        """품질 메트릭 기록"""
        self.quality_history.append(metrics)

        # 품질 임계값 체크
        if metrics.data_quality_score < 60:  # 품질 점수 60% 미만
            self._create_alert(
                AlertLevel.ERROR,
                "낮은 데이터 품질",
                f"데이터 품질 점수가 {metrics.data_quality_score:.1f}%입니다"
            )

        if metrics.duplicate_rate > 20:  # 중복률 20% 초과
            self._create_alert(
                AlertLevel.WARNING,
                "높은 중복률",
                f"데이터 중복률이 {metrics.duplicate_rate:.1f}%입니다"
            )

    def _create_alert(
        self,
        level: AlertLevel,
        title: str,
        message: str,
        session_id: str = None
    ):
        """알림 생성"""
        alert = Alert(
            id=f"alert_{int(time.time())}_{len(self.alerts)}",
            level=level,
            title=title,
            message=message,
            timestamp=datetime.now(),
            session_id=session_id
        )

        self.alerts.append(alert)

        # 최대 알림 수 제한 (최근 100개만 유지)
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]

        logger.info(f"🚨 알림 생성 ({level.value}): {title}")

    async def _collect_system_metrics(self):
        """시스템 메트릭 수집"""
        try:
            import psutil

            # CPU 및 메모리 사용률
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()

            # 현재 시간의 성능 메트릭 생성
            now = datetime.now()

            # 활성 세션들의 통계 계산
            total_products = sum(s.products_processed for s in self.active_sessions.values())
            total_valid = sum(s.products_valid for s in self.active_sessions.values())
            total_errors = sum(s.error_count for s in self.active_sessions.values())

            success_rate = (total_valid / max(1, total_products)) * 100
            error_rate = (total_errors / max(1, total_products)) * 100

            metrics = PerformanceMetrics(
                timestamp=now,
                success_rate=success_rate,
                error_rate=error_rate,
                memory_usage_mb=memory.used / (1024 * 1024),
                cpu_usage_percent=cpu_percent
            )

            self.record_performance_metrics(metrics)

        except ImportError:
            # psutil이 없는 경우 기본 메트릭만 수집
            pass
        except Exception as e:
            logger.warning(f"시스템 메트릭 수집 실패: {e}")

    async def _check_alerts(self):
        """알림 조건 체크"""
        now = datetime.now()

        # 비활성 세션 체크 (5분 이상 활동 없음)
        for session_id, session in list(self.active_sessions.items()):
            if (now - session.last_activity).total_seconds() > 300:  # 5분
                if session.status == ScrapingStatus.RUNNING:
                    session.status = ScrapingStatus.ERROR
                    self._create_alert(
                        AlertLevel.ERROR,
                        "세션 응답 없음",
                        f"세션 {session_id}가 5분 이상 응답하지 않습니다",
                        session_id
                    )

    async def _update_real_time_stats(self):
        """실시간 통계 업데이트"""
        now = datetime.now()
        uptime = (now - self.start_time).total_seconds() / 3600  # 시간 단위

        # 오늘 수집된 상품 수 계산
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        products_today = sum(
            s.products_valid for s in self.completed_sessions
            if s.end_time and s.end_time >= today_start
        )

        # 최근 품질 점수 평균
        recent_quality = list(self.quality_history)[-10:]  # 최근 10개
        avg_quality = sum(q.data_quality_score for q in recent_quality) / max(1, len(recent_quality))

        self.real_time_stats.update({
            "active_sessions": len(self.active_sessions),
            "products_today": products_today,
            "average_quality_score": avg_quality,
            "uptime_hours": uptime
        })

    async def _broadcast_updates(self):
        """WebSocket 클라이언트들에게 업데이트 브로드캐스트"""
        if not self.websocket_clients:
            return

        update_data = {
            "type": "status_update",
            "timestamp": datetime.now().isoformat(),
            "stats": self.real_time_stats,
            "active_sessions": {
                sid: asdict(session) for sid, session in self.active_sessions.items()
            },
            "recent_alerts": [
                asdict(alert) for alert in self.alerts[-5:]  # 최근 5개 알림
            ]
        }

        # 연결된 클라이언트들에게 전송
        for client in self.websocket_clients[:]:  # 복사본으로 순회
            try:
                await client.send_text(json.dumps(update_data, default=str))
            except Exception as e:
                logger.warning(f"WebSocket 전송 실패: {e}")
                self.websocket_clients.remove(client)

    def add_websocket_client(self, websocket):
        """WebSocket 클라이언트 추가"""
        self.websocket_clients.append(websocket)
        logger.info(f"📡 WebSocket 클라이언트 연결 ({len(self.websocket_clients)}개)")

    def remove_websocket_client(self, websocket):
        """WebSocket 클라이언트 제거"""
        if websocket in self.websocket_clients:
            self.websocket_clients.remove(websocket)
            logger.info(f"📡 WebSocket 클라이언트 연결 해제 ({len(self.websocket_clients)}개)")

    def get_dashboard_data(self) -> Dict[str, Any]:
        """대시보드 데이터 반환"""
        now = datetime.now()

        # 최근 성능 메트릭 (최근 1시간)
        recent_performance = [
            m for m in self.performance_history
            if (now - m.timestamp).total_seconds() < 3600
        ]

        # 최근 품질 메트릭 (최근 1시간)
        recent_quality = [
            m for m in self.quality_history
            if (now - m.timestamp).total_seconds() < 3600
        ]

        return {
            "overview": self.real_time_stats,
            "active_sessions": [asdict(s) for s in self.active_sessions.values()],
            "recent_sessions": [asdict(s) for s in self.completed_sessions[-10:]],
            "performance_metrics": [asdict(m) for m in recent_performance],
            "quality_metrics": [asdict(m) for m in recent_quality],
            "alerts": [asdict(a) for a in self.alerts[-20:]],  # 최근 20개 알림
            "system_health": self._get_system_health()
        }

    def _get_system_health(self) -> Dict[str, str]:
        """시스템 건강 상태 반환"""
        health = {"overall": "healthy"}

        # 최근 에러율 체크
        recent_alerts = [a for a in self.alerts[-10:] if a.level in [AlertLevel.ERROR, AlertLevel.CRITICAL]]
        if len(recent_alerts) > 3:
            health["overall"] = "degraded"
            health["reason"] = "많은 에러 발생"

        # 활성 세션 수 체크
        if len(self.active_sessions) == 0 and self.real_time_stats["uptime_hours"] > 1:
            health["overall"] = "idle"
            health["reason"] = "활성 세션 없음"

        # 메모리 사용량 체크 (최근 메트릭 기준)
        if self.performance_history:
            latest_perf = self.performance_history[-1]
            if latest_perf.memory_usage_mb > 1000:  # 1GB 초과
                health["overall"] = "warning"
                health["reason"] = "높은 메모리 사용량"

        return health

    def acknowledge_alert(self, alert_id: str):
        """알림 확인 처리"""
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                logger.info(f"✅ 알림 확인: {alert_id}")
                break

    def get_session_details(self, session_id: str) -> Optional[Dict[str, Any]]:
        """세션 상세 정보 반환"""
        # 활성 세션에서 찾기
        if session_id in self.active_sessions:
            return asdict(self.active_sessions[session_id])

        # 완료된 세션에서 찾기
        for session in self.completed_sessions:
            if session.session_id == session_id:
                return asdict(session)

        return None

# 전역 모니터 인스턴스
_global_monitor = None

def get_scraping_monitor() -> ScrapingMonitor:
    """전역 스크래핑 모니터 인스턴스 반환"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = ScrapingMonitor()
    return _global_monitor

# 사용 예시
async def test_monitor():
    """모니터링 시스템 테스트"""
    monitor = ScrapingMonitor()

    # 모니터링 시작
    await monitor.start_monitoring()

    # 테스트 세션 시작
    session = monitor.start_session("test_001", "wireless headphones")

    # 진행상황 시뮬레이션
    for i in range(10):
        monitor.update_session_progress(
            "test_001",
            products_found=i * 5,
            products_processed=i * 4,
            products_valid=i * 3,
            current_page=i + 1
        )
        await asyncio.sleep(2)

    # 세션 완료
    monitor.complete_session("test_001")

    # 대시보드 데이터 출력
    dashboard_data = monitor.get_dashboard_data()
    print(json.dumps(dashboard_data, indent=2, default=str))

    # 모니터링 중지
    await monitor.stop_monitoring()

if __name__ == "__main__":
    asyncio.run(test_monitor())