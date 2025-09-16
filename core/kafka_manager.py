"""
Kafka 메시지 브로커 관리자
이벤트 기반 아키텍처의 핵심 - Producer와 Consumer 관리
"""

import json
import logging
import uuid
import asyncio
from datetime import datetime
from typing import Any, Dict, Optional, List
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError
from collections import defaultdict
import threading
import time

logger = logging.getLogger(__name__)

class KafkaManager:
    """
    Kafka Producer와 Consumer를 관리하는 중앙 클래스
    
    역할:
    - Producer: 이벤트 발행 (주문서를 주방에 전달하는 점원)
    - Consumer: 이벤트 처리 (주방에서 요리를 만드는 요리사)
    """
    
    def __init__(self, bootstrap_servers='localhost:9092'):
        """
        Kafka 연결 초기화
        
        Args:
            bootstrap_servers: Kafka 서버 주소
        """
        self.bootstrap_servers = bootstrap_servers
        self.producer = None
        self.consumer = None
        
        # 토픽 이름 상수 (실수 방지)
        self.TOPIC_ANALYSIS_EVENTS = 'market-analysis-events'
        self.TOPIC_STATUS_UPDATES = 'scraping-status-updates' 
        self.TOPIC_NOTIFICATIONS = 'user-notifications'
        
        # 배치 처리 설정
        self.batch_enabled = True
        self.batch_size = 50  # 배치당 최대 메시지 수
        self.batch_timeout = 5.0  # 배치 타임아웃 (초)
        self.batch_buffer = defaultdict(list)  # 토픽별 배치 버퍼
        self.batch_lock = threading.Lock()
        self.batch_thread = None
        self.batch_running = False
        
        # 배치 처리 스레드 시작
        self._start_batch_processor()
        
    def get_producer(self) -> KafkaProducer:
        """
        Kafka Producer 인스턴스 반환 (싱글톤 패턴)
        
        Producer란?
        - 메시지를 Kafka 토픽에 보내는 역할
        - 예: 사용자가 "wireless mouse" 분석 요청 → Producer가 이벤트 발행
        """
        if self.producer is None:
            try:
                self.producer = KafkaProducer(
                    bootstrap_servers=self.bootstrap_servers,
                    # JSON 직렬화 설정
                    value_serializer=lambda x: json.dumps(x, ensure_ascii=False).encode('utf-8'),
                    key_serializer=lambda x: x.encode('utf-8') if x else None,
                    
                    # 성능 최적화 설정 (fire-and-forget 모드)
                    acks=0,  # 확인 없이 즉시 전송 (가장 빠름)
                    retries=0,  # 재시도 없음 (빠른 실패)
                    batch_size=1024,  # 1KB 배치로 전송 (빠른 전송)
                    linger_ms=0,  # 즉시 전송 (지연 없음)
                    
                    # Timeout 설정 (짧게 설정)
                    request_timeout_ms=5000,  # 5초 요청 timeout
                    max_block_ms=1000,  # 1초 블록 timeout
                    
                    # 압축 설정 (네트워크 효율성) - snappy 라이브러리 이슈로 임시 비활성화
                    compression_type=None
                )
                logger.info("✅ Kafka Producer 초기화 성공")
                
            except Exception as e:
                logger.error(f"❌ Kafka Producer 초기화 실패: {e}")
                raise
                
        return self.producer
        
    def send_analysis_event(self, event_type: str, keyword: str, 
                          session_id: str = None, data: Dict[str, Any] = None) -> str:
        """
        시장 분석 이벤트 발송
        
        이것이 핵심! 사용자 요청을 즉시 이벤트로 변환
        
        Args:
            event_type: 이벤트 타입 ('analysis_requested', 'analysis_completed' 등)
            keyword: 분석 키워드
            session_id: 세션 ID (없으면 자동 생성)
            data: 추가 데이터
            
        Returns:
            session_id: 프론트엔드에서 진행 상황 추적용
        """
        if session_id is None:
            session_id = str(uuid.uuid4())
            
        # 이벤트 메시지 구성
        event_message = {
            'event_type': event_type,
            'keyword': keyword,
            'session_id': session_id,
            'timestamp': datetime.now().isoformat(),
            'data': data or {}
        }
        
        try:
            producer = self.get_producer()
            
            # 핵심! 메시지를 토픽에 발송 (비동기)
            future = producer.send(
                topic=self.TOPIC_ANALYSIS_EVENTS,
                key=session_id,  # 같은 세션의 메시지는 같은 파티션으로
                value=event_message
            )
            
            # 콜백으로 성공/실패 처리
            def on_success(metadata):
                logger.info(f"🚀 이벤트 발송 성공: {event_type} | 키워드: {keyword} | 세션: {session_id} | 파티션: {metadata.partition}")
            
            def on_error(error):
                logger.error(f"❌ 이벤트 발송 실패: {event_type} | 키워드: {keyword} | 오류: {error}")
            
            future.add_callback(on_success)
            future.add_errback(on_error)
            
            # 즉시 반환 (블로킹 하지 않음)
            logger.info(f"📤 이벤트 발송 요청: {event_type} | 키워드: {keyword} | 세션: {session_id}")
            return session_id
            
        except KafkaError as e:
            logger.error(f"❌ Kafka 이벤트 발송 실패: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 예상치 못한 오류: {e}")
            raise
            
    def send_status_update(self, session_id: str, status: str, 
                          progress: int = 0, message: str = ""):
        """
        실시간 상태 업데이트 발송
        
        사용자가 "지금 어디까지 진행됐지?"를 알 수 있도록
        
        Args:
            session_id: 세션 ID
            status: 상태 ('scraping', 'analyzing', 'completed', 'failed')
            progress: 진행률 (0-100)
            message: 상태 메시지
        """
        status_message = {
            'session_id': session_id,
            'status': status,
            'progress': progress,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            producer = self.get_producer()
            producer.send(
                topic=self.TOPIC_STATUS_UPDATES,
                key=session_id,
                value=status_message
            )
            logger.debug(f"📊 상태 업데이트 발송: {status} ({progress}%) - {session_id}")
            
        except Exception as e:
            logger.error(f"❌ 상태 업데이트 발송 실패: {e}")
            
    def send_notification(self, user_id: str, notification_type: str, 
                         title: str, message: str):
        """
        사용자 알림 발송
        
        분석 완료되면 "분석이 완료되었습니다!" 알림
        """
        notification_message = {
            'user_id': user_id,
            'type': notification_type,
            'title': title,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            producer = self.get_producer()
            producer.send(
                topic=self.TOPIC_NOTIFICATIONS,
                key=user_id,
                value=notification_message
            )
            logger.info(f"🔔 알림 발송: {title} → {user_id}")
            
        except Exception as e:
            logger.error(f"❌ 알림 발송 실패: {e}")
    
    def send_user_action(self, user_id: str, action_type: str, 
                        page_url: str = "", data: Dict[str, Any] = None):
        """
        사용자 액션 이벤트 발송
        
        사용자의 모든 행동을 추적하여 통계 및 개인화에 활용
        
        Args:
            user_id: 사용자 ID (세션 기반)
            action_type: 액션 타입 ('page_view', 'keyword_search', 'report_view', 'button_click')
            page_url: 액션이 발생한 페이지 URL
            data: 추가 데이터 (키워드, 클릭 요소 등)
        """
        action_message = {
            'user_id': user_id,
            'action_type': action_type,
            'page_url': page_url,
            'timestamp': datetime.now().isoformat(),
            'data': data or {}
        }
        
        try:
            producer = self.get_producer()
            producer.send(
                topic='user-actions',
                key=user_id,
                value=action_message
            )
            logger.debug(f"👆 사용자 액션 발송: {action_type} - {user_id}")
            
        except Exception as e:
            logger.error(f"❌ 사용자 액션 발송 실패: {e}")
    
    def send_statistics_event(self, stat_type: str, metric_name: str, 
                            metric_value: Any, tags: Dict[str, str] = None):
        """
        통계 이벤트 발송
        
        시스템 메트릭, 비즈니스 메트릭을 통계 Consumer로 전송
        
        Args:
            stat_type: 통계 타입 ('system_metric', 'business_metric', 'performance_metric')
            metric_name: 메트릭 이름 (예: 'response_time', 'memory_usage')
            metric_value: 메트릭 값
            tags: 메트릭 태그 (분류용)
        """
        stats_message = {
            'stat_type': stat_type,
            'metric_name': metric_name,
            'metric_value': metric_value,
            'tags': tags or {},
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            producer = self.get_producer()
            producer.send(
                topic='statistics-events',
                key=f"{stat_type}:{metric_name}",
                value=stats_message
            )
            logger.debug(f"📊 통계 이벤트 발송: {metric_name} = {metric_value}")
            
        except Exception as e:
            logger.error(f"❌ 통계 이벤트 발송 실패: {e}")
    
    def _start_batch_processor(self):
        """배치 처리 스레드 시작"""
        if not self.batch_enabled or self.batch_running:
            return
            
        self.batch_running = True
        self.batch_thread = threading.Thread(target=self._batch_processor, daemon=True)
        self.batch_thread.start()
        logger.info("🚀 배치 처리 스레드 시작됨")
    
    def _batch_processor(self):
        """배치 처리 백그라운드 스레드"""
        while self.batch_running:
            try:
                time.sleep(self.batch_timeout)
                self._flush_batches()
            except Exception as e:
                logger.error(f"❌ 배치 처리 오류: {e}")
    
    def _flush_batches(self):
        """모든 배치 버퍼를 강제로 전송"""
        with self.batch_lock:
            for topic, messages in self.batch_buffer.items():
                if messages:
                    self._send_batch_messages(topic, messages)
                    messages.clear()
    
    def _send_batch_messages(self, topic: str, messages: List[Dict[str, Any]]):
        """배치 메시지들을 실제로 전송"""
        if not messages:
            return
            
        try:
            producer = self.get_producer()
            
            # 배치로 메시지 전송
            for message_data in messages:
                producer.send(
                    topic=topic,
                    key=message_data.get('key'),
                    value=message_data.get('value')
                )
            
            # 전송 완료 대기
            producer.flush()
            
            logger.info(f"📦 배치 전송 완료: {topic} ({len(messages)}개 메시지)")
            
        except Exception as e:
            logger.error(f"❌ 배치 전송 실패 ({topic}): {e}")
    
    def send_batch_events(self, events: List[Dict[str, Any]]):
        """
        여러 이벤트를 배치로 발송
        
        대량 이벤트 처리시 사용 (예: 사용자 액션 로그 배치 업로드)
        
        Args:
            events: 이벤트 리스트
                [
                    {
                        'topic': 'user-actions',
                        'key': 'user_123',
                        'value': {...}
                    },
                    ...
                ]
        """
        if not self.batch_enabled:
            # 배치 비활성화시 개별 전송
            for event in events:
                self._send_single_event(event)
            return
        
        with self.batch_lock:
            for event in events:
                topic = event.get('topic', 'default')
                self.batch_buffer[topic].append({
                    'key': event.get('key'),
                    'value': event.get('value')
                })
                
                # 배치 크기 초과시 즉시 전송
                if len(self.batch_buffer[topic]) >= self.batch_size:
                    messages = self.batch_buffer[topic].copy()
                    self.batch_buffer[topic].clear()
                    self._send_batch_messages(topic, messages)
        
        logger.debug(f"📦 배치 이벤트 버퍼링: {len(events)}개 이벤트")
    
    def _send_single_event(self, event: Dict[str, Any]):
        """단일 이벤트 즉시 전송 (배치 비활성화시)"""
        try:
            producer = self.get_producer()
            producer.send(
                topic=event.get('topic', 'default'),
                key=event.get('key'),
                value=event.get('value')
            )
        except Exception as e:
            logger.error(f"❌ 단일 이벤트 전송 실패: {e}")
    
    def send_user_actions_batch(self, user_actions: List[Dict[str, Any]]):
        """
        사용자 액션들을 배치로 발송
        
        사용 예시:
        actions = [
            {'user_id': 'user1', 'action': 'page_view', 'page': '/'},
            {'user_id': 'user2', 'action': 'click', 'element': 'button'},
        ]
        kafka_manager.send_user_actions_batch(actions)
        """
        batch_events = []
        
        for action in user_actions:
            event_message = {
                'user_id': action.get('user_id', 'anonymous'),
                'action_type': action.get('action', 'unknown'),
                'page_url': action.get('page_url', ''),
                'timestamp': datetime.now().isoformat(),
                'data': action.get('data', {})
            }
            
            batch_events.append({
                'topic': 'user-actions',
                'key': action.get('user_id', 'anonymous'),
                'value': event_message
            })
        
        self.send_batch_events(batch_events)
        logger.info(f"👥 사용자 액션 배치 발송: {len(user_actions)}개")
    
    def send_statistics_batch(self, stats: List[Dict[str, Any]]):
        """
        통계 메트릭들을 배치로 발송
        
        시스템 모니터링에서 주기적으로 대량의 메트릭을 전송할 때 사용
        """
        batch_events = []
        
        for stat in stats:
            stats_message = {
                'stat_type': stat.get('type', 'metric'),
                'metric_name': stat.get('name', 'unknown'),
                'metric_value': stat.get('value', 0),
                'tags': stat.get('tags', {}),
                'timestamp': datetime.now().isoformat()
            }
            
            batch_events.append({
                'topic': 'statistics-events',
                'key': f"{stat.get('type', 'metric')}:{stat.get('name', 'unknown')}",
                'value': stats_message
            })
        
        self.send_batch_events(batch_events)
        logger.info(f"📊 통계 메트릭 배치 발송: {len(stats)}개")
    
    def get_batch_stats(self) -> Dict[str, Any]:
        """배치 처리 통계 반환"""
        with self.batch_lock:
            buffer_sizes = {topic: len(messages) for topic, messages in self.batch_buffer.items()}
            
        return {
            'batch_enabled': self.batch_enabled,
            'batch_size': self.batch_size,
            'batch_timeout': self.batch_timeout,
            'buffer_sizes': buffer_sizes,
            'total_buffered': sum(buffer_sizes.values())
        }
            
    def close(self):
        """리소스 정리"""
        # 배치 처리 종료
        self.batch_running = False
        if self.batch_thread and self.batch_thread.is_alive():
            # 마지막 배치 전송
            self._flush_batches()
            self.batch_thread.join(timeout=2)
            logger.info("🔒 배치 처리 스레드 종료")
        
        if self.producer:
            self.producer.close()
            logger.info("🔒 Kafka Producer 종료")
            
    def health_check(self) -> Dict[str, Any]:
        """
        Kafka 연결 상태 확인
        """
        try:
            # 빠른 연결 테스트를 위해 간단한 Producer 생성
            from kafka import KafkaProducer
            
            test_producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                request_timeout_ms=10000,  # 10초로 증가
                retry_backoff_ms=500,
                retries=3,
                api_version=(0, 10, 1)  # 호환성을 위한 버전 지정
            )
            
            # 메타데이터만 확인하고 즉시 종료
            test_producer.bootstrap_connected()
            test_producer.close()
            
            return {
                'status': 'healthy',
                'producer_connected': True,
                'bootstrap_servers': self.bootstrap_servers
            }
        except Exception as e:
            return {
                'status': 'unhealthy', 
                'error': str(e),
                'bootstrap_servers': self.bootstrap_servers
            }

# 전역 인스턴스 (싱글톤)
_kafka_manager_instance = None

def get_kafka_manager() -> KafkaManager:
    """
    KafkaManager 싱글톤 인스턴스 반환
    앱 전체에서 하나의 Kafka 연결만 사용
    """
    global _kafka_manager_instance
    if _kafka_manager_instance is None:
        _kafka_manager_instance = KafkaManager()
    return _kafka_manager_instance