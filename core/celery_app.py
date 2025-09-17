"""
Celery 분산 작업 큐 설정
대용량 트래픽 처리를 위한 비동기 작업 처리 시스템의 핵심
"""

from celery import Celery
import os
import logging

logger = logging.getLogger(__name__)

# Redis 브로커 설정 (Kafka와 함께 사용)
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/1')  # DB 1 사용 (캐시는 DB 0)

# Celery 앱 인스턴스 생성
celery_app = Celery(
    'market_insights',
    broker=REDIS_URL,           # 작업 큐 브로커
    backend=REDIS_URL,          # 결과 저장소
    include=['core.tasks']      # 작업 모듈 자동 로드
)

# 우선순위 큐 설정 적용
def apply_priority_queue_config():
    """
    우선순위 큐 시스템 설정을 Celery에 적용
    """
    try:
        from core.priority_queue import get_priority_queue_manager

        pq_manager = get_priority_queue_manager()

        # 동적 라우팅 설정
        routes = pq_manager.get_celery_route_config()
        celery_app.conf.task_routes = routes

        # 동적 어노테이션 설정
        annotations = pq_manager.get_task_annotations()
        celery_app.conf.task_annotations = annotations

        logger.info(f"✅ 우선순위 큐 설정 적용 완료: {len(routes)}개 작업, {len(annotations)}개 어노테이션")

    except Exception as e:
        logger.error(f"❌ 우선순위 큐 설정 적용 실패: {e}")

# 설정 적용
apply_priority_queue_config()

# Celery 설정
celery_app.conf.update(
    # === 성능 최적화 설정 ===
    task_serializer='json',                    # JSON 직렬화 (빠름)
    accept_content=['json'],                   # JSON만 허용 (보안)
    result_serializer='json',                  # 결과도 JSON
    timezone='Asia/Seoul',                     # 한국 시간대
    enable_utc=True,                          # UTC 기본 사용

    # === 작업 라우팅 설정 (우선순위 큐 시스템 사용) ===
    task_routes=None,  # 동적으로 설정됨

    # === 큐별 설정 (라우팅 키 기반) ===
    task_default_queue='default',
    task_default_exchange='market_insights',
    task_default_exchange_type='topic',  # topic exchange로 변경 (라우팅 키 패턴 매칭)
    task_default_routing_key='default.task',

    # === 성능 튜닝 ===
    worker_prefetch_multiplier=4,             # 워커당 미리 가져올 작업 수
    task_acks_late=True,                      # 작업 완료 후 ACK (안정성)
    worker_disable_rate_limits=False,         # 속도 제한 활성화

    # === 결과 저장 설정 ===
    result_expires=3600,                      # 결과 1시간 후 만료
    result_persistent=True,                   # 결과 영구 저장

    # === 재시도 설정 (우선순위 큐 시스템에서 동적 설정) ===
    task_annotations={},  # 동적으로 설정됨

    # === 모니터링 설정 ===
    worker_send_task_events=True,             # 작업 이벤트 전송
    task_send_sent_event=True,                # 작업 전송 이벤트

    # === 보안 설정 ===
    worker_hijack_root_logger=False,          # 로거 보호
    worker_log_color=False,                   # 컬러 로그 비활성화 (프로덕션)
)

def get_celery_app() -> Celery:
    """
    Celery 앱 인스턴스 반환

    다른 모듈에서 import해서 사용:
    from core.celery_app import get_celery_app
    celery = get_celery_app()
    """
    return celery_app

# 헬스체크용 간단한 작업
@celery_app.task(bind=True)
def health_check(self):
    """
    Celery 시스템 헬스체크 작업

    Returns:
        dict: 시스템 상태 정보
    """
    import time
    from datetime import datetime

    return {
        'status': 'healthy',
        'worker_id': self.request.id,
        'timestamp': datetime.now().isoformat(),
        'message': 'Celery worker is running properly'
    }

if __name__ == '__main__':
    # 개발용 워커 실행
    # 실제 사용: celery -A core.celery_app worker --loglevel=info
    print("🚀 Starting Celery development worker...")
    celery_app.start()