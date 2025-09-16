"""
EventStore - 이벤트 소싱 패턴 구현
모든 시스템 이벤트를 순서대로 저장하고 상태를 재구성할 수 있는 이벤트 저장소
"""

import asyncio
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from enum import Enum
import uuid
import hashlib

logger = logging.getLogger(__name__)

class EventType(Enum):
    """이벤트 타입 정의"""
    # 사용자 관련
    USER_CREATED = "user_created"
    USER_ACTION = "user_action"
    USER_SESSION_STARTED = "user_session_started"
    USER_SESSION_ENDED = "user_session_ended"
    
    # 분석 관련
    ANALYSIS_REQUESTED = "analysis_requested"
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETED = "analysis_completed"
    ANALYSIS_FAILED = "analysis_failed"
    
    # 스크래핑 관련
    SCRAPING_STARTED = "scraping_started"
    SCRAPING_PROGRESS = "scraping_progress"
    SCRAPING_COMPLETED = "scraping_completed"
    SCRAPING_FAILED = "scraping_failed"
    
    # 캐시 관련
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    CACHE_SET = "cache_set"
    CACHE_INVALIDATED = "cache_invalidated"
    
    # 시스템 관련
    SYSTEM_STARTED = "system_started"
    SYSTEM_SHUTDOWN = "system_shutdown"
    SYSTEM_ERROR = "system_error"
    
    # 비즈니스 관련
    KEYWORD_ANALYZED = "keyword_analyzed"
    MARKET_TREND_DETECTED = "market_trend_detected"
    ANOMALY_DETECTED = "anomaly_detected"

@dataclass
class Event:
    """이벤트 데이터 클래스"""
    event_id: str
    event_type: EventType
    aggregate_id: str  # 집합체 ID (예: user_id, keyword, analysis_id)
    aggregate_type: str  # 집합체 타입 (예: user, analysis, keyword)
    event_data: Dict[str, Any]
    metadata: Dict[str, Any]
    timestamp: datetime
    version: int  # 집합체 버전
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type.value,
            'aggregate_id': self.aggregate_id,
            'aggregate_type': self.aggregate_type,
            'event_data': json.dumps(self.event_data),
            'metadata': json.dumps(self.metadata),
            'timestamp': self.timestamp.isoformat(),
            'version': self.version
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        """딕셔너리에서 생성"""
        return cls(
            event_id=data['event_id'],
            event_type=EventType(data['event_type']),
            aggregate_id=data['aggregate_id'],
            aggregate_type=data['aggregate_type'],
            event_data=json.loads(data['event_data']),
            metadata=json.loads(data['metadata']),
            timestamp=datetime.fromisoformat(data['timestamp']),
            version=data['version']
        )

class EventStore:
    """이벤트 저장소"""
    
    def __init__(self, db_path: str = 'data/event_store.db'):
        self.db_path = db_path
        self._init_database()
        
        # 집합체별 버전 캐시
        self.version_cache = {}
        
        # 이벤트 핸들러 등록
        self.event_handlers = {}
        
        # 스냅샷 설정
        self.snapshot_frequency = 10  # 10개 이벤트마다 스냅샷
    
    def _init_database(self):
        """이벤트 저장소 데이터베이스 초기화"""
        try:
            with self._get_db_connection() as conn:
                # 이벤트 테이블
                conn.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    event_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    event_data TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    UNIQUE(aggregate_id, version)
                )
                ''')
                
                # 스냅샷 테이블
                conn.execute('''
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aggregate_id TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    state_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    UNIQUE(aggregate_id, version)
                )
                ''')
                
                # 인덱스 생성
                conn.execute('CREATE INDEX IF NOT EXISTS idx_events_aggregate ON events(aggregate_id, aggregate_type)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_aggregate ON snapshots(aggregate_id, aggregate_type)')
                
                conn.commit()
                logger.info("✅ 이벤트 저장소 데이터베이스 초기화 완료")
                
        except Exception as e:
            logger.error(f"❌ 이벤트 저장소 DB 초기화 실패: {e}")
    
    @contextmanager
    def _get_db_connection(self):
        """SQLite 연결 컨텍스트 매니저"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"❌ DB 연결 오류: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    async def append_event(self, event: Event) -> bool:
        """이벤트 추가"""
        try:
            with self._get_db_connection() as conn:
                # 현재 집합체 버전 확인
                current_version = self._get_current_version(conn, event.aggregate_id)
                
                # 버전 충돌 확인
                if event.version != current_version + 1:
                    logger.error(f"❌ 버전 충돌: 예상 {current_version + 1}, 실제 {event.version}")
                    return False
                
                # 이벤트 저장
                event_dict = event.to_dict()
                conn.execute('''
                INSERT INTO events 
                (event_id, event_type, aggregate_id, aggregate_type, event_data, metadata, timestamp, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    event_dict['event_id'],
                    event_dict['event_type'],
                    event_dict['aggregate_id'],
                    event_dict['aggregate_type'],
                    event_dict['event_data'],
                    event_dict['metadata'],
                    event_dict['timestamp'],
                    event_dict['version']
                ))
                
                conn.commit()
                
                # 버전 캐시 업데이트
                self.version_cache[event.aggregate_id] = event.version
                
                # 이벤트 핸들러 실행
                await self._handle_event(event)
                
                # 스냅샷 생성 확인
                if event.version % self.snapshot_frequency == 0:
                    await self._create_snapshot_if_needed(event.aggregate_id, event.aggregate_type)
                
                logger.debug(f"📝 이벤트 저장 완료: {event.event_type.value} - {event.aggregate_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ 이벤트 저장 실패: {e}")
            return False
    
    def _get_current_version(self, conn, aggregate_id: str) -> int:
        """집합체의 현재 버전 조회"""
        if aggregate_id in self.version_cache:
            return self.version_cache[aggregate_id]
        
        result = conn.execute(
            'SELECT MAX(version) as max_version FROM events WHERE aggregate_id = ?',
            (aggregate_id,)
        ).fetchone()
        
        version = result['max_version'] if result['max_version'] is not None else 0
        self.version_cache[aggregate_id] = version
        return version
    
    async def get_events(self, aggregate_id: str, from_version: int = 0) -> List[Event]:
        """집합체의 이벤트 목록 조회"""
        try:
            with self._get_db_connection() as conn:
                rows = conn.execute('''
                SELECT * FROM events 
                WHERE aggregate_id = ? AND version > ?
                ORDER BY version ASC
                ''', (aggregate_id, from_version)).fetchall()
                
                return [Event.from_dict(dict(row)) for row in rows]
                
        except Exception as e:
            logger.error(f"❌ 이벤트 조회 실패: {e}")
            return []
    
    async def get_events_by_type(self, event_type: EventType, 
                                since: Optional[datetime] = None,
                                limit: int = 100) -> List[Event]:
        """타입별 이벤트 조회"""
        try:
            with self._get_db_connection() as conn:
                if since:
                    rows = conn.execute('''
                    SELECT * FROM events 
                    WHERE event_type = ? AND datetime(timestamp) >= datetime(?)
                    ORDER BY timestamp DESC
                    LIMIT ?
                    ''', (event_type.value, since.isoformat(), limit)).fetchall()
                else:
                    rows = conn.execute('''
                    SELECT * FROM events 
                    WHERE event_type = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    ''', (event_type.value, limit)).fetchall()
                
                return [Event.from_dict(dict(row)) for row in rows]
                
        except Exception as e:
            logger.error(f"❌ 타입별 이벤트 조회 실패: {e}")
            return []
    
    async def rebuild_aggregate_state(self, aggregate_id: str, 
                                    aggregate_type: str) -> Dict[str, Any]:
        """집합체 상태 재구성"""
        try:
            # 최신 스냅샷 조회
            snapshot = await self._get_latest_snapshot(aggregate_id)
            
            if snapshot:
                from_version = snapshot['version']
                state = json.loads(snapshot['state_data'])
                logger.debug(f"🔄 스냅샷부터 상태 재구성: {aggregate_id} (version {from_version})")
            else:
                from_version = 0
                state = self._get_initial_state(aggregate_type)
                logger.debug(f"🔄 처음부터 상태 재구성: {aggregate_id}")
            
            # 스냅샷 이후의 이벤트들 적용
            events = await self.get_events(aggregate_id, from_version)
            
            for event in events:
                state = self._apply_event_to_state(state, event, aggregate_type)
            
            logger.debug(f"✅ 상태 재구성 완료: {aggregate_id} ({len(events)}개 이벤트 적용)")
            return state
            
        except Exception as e:
            logger.error(f"❌ 상태 재구성 실패: {e}")
            return {}
    
    def _get_initial_state(self, aggregate_type: str) -> Dict[str, Any]:
        """집합체 타입별 초기 상태"""
        initial_states = {
            'user': {
                'user_id': None,
                'session_count': 0,
                'total_analyses': 0,
                'last_activity': None,
                'preferences': {}
            },
            'analysis': {
                'analysis_id': None,
                'keyword': None,
                'status': 'pending',
                'start_time': None,
                'end_time': None,
                'results': {},
                'error_message': None
            },
            'keyword': {
                'keyword': None,
                'analysis_count': 0,
                'first_analyzed': None,
                'last_analyzed': None,
                'trend_data': [],
                'anomaly_count': 0
            }
        }
        
        return initial_states.get(aggregate_type, {})
    
    def _apply_event_to_state(self, state: Dict[str, Any], event: Event, 
                            aggregate_type: str) -> Dict[str, Any]:
        """이벤트를 상태에 적용"""
        event_data = event.event_data
        
        if aggregate_type == 'user':
            if event.event_type == EventType.USER_CREATED:
                state['user_id'] = event_data.get('user_id')
            elif event.event_type == EventType.USER_SESSION_STARTED:
                state['session_count'] += 1
                state['last_activity'] = event.timestamp.isoformat()
            elif event.event_type == EventType.USER_ACTION:
                state['last_activity'] = event.timestamp.isoformat()
                if event_data.get('action_type') == 'analysis_request':
                    state['total_analyses'] += 1
        
        elif aggregate_type == 'analysis':
            if event.event_type == EventType.ANALYSIS_REQUESTED:
                state['analysis_id'] = event_data.get('analysis_id')
                state['keyword'] = event_data.get('keyword')
                state['status'] = 'requested'
            elif event.event_type == EventType.ANALYSIS_STARTED:
                state['status'] = 'running'
                state['start_time'] = event.timestamp.isoformat()
            elif event.event_type == EventType.ANALYSIS_COMPLETED:
                state['status'] = 'completed'
                state['end_time'] = event.timestamp.isoformat()
                state['results'] = event_data.get('results', {})
            elif event.event_type == EventType.ANALYSIS_FAILED:
                state['status'] = 'failed'
                state['end_time'] = event.timestamp.isoformat()
                state['error_message'] = event_data.get('error')
        
        elif aggregate_type == 'keyword':
            if event.event_type == EventType.KEYWORD_ANALYZED:
                state['keyword'] = event_data.get('keyword')
                state['analysis_count'] += 1
                state['last_analyzed'] = event.timestamp.isoformat()
                if not state['first_analyzed']:
                    state['first_analyzed'] = event.timestamp.isoformat()
                
                # 트렌드 데이터 추가
                trend_point = {
                    'timestamp': event.timestamp.isoformat(),
                    'competitor_count': event_data.get('competitor_count', 0),
                    'avg_price': event_data.get('avg_price', 0)
                }
                state['trend_data'].append(trend_point)
                
                # 최근 100개만 유지
                if len(state['trend_data']) > 100:
                    state['trend_data'] = state['trend_data'][-100:]
            
            elif event.event_type == EventType.ANOMALY_DETECTED:
                state['anomaly_count'] += 1
        
        return state
    
    async def _get_latest_snapshot(self, aggregate_id: str) -> Optional[Dict[str, Any]]:
        """최신 스냅샷 조회"""
        try:
            with self._get_db_connection() as conn:
                row = conn.execute('''
                SELECT * FROM snapshots 
                WHERE aggregate_id = ?
                ORDER BY version DESC
                LIMIT 1
                ''', (aggregate_id,)).fetchone()
                
                return dict(row) if row else None
                
        except Exception as e:
            logger.error(f"❌ 스냅샷 조회 실패: {e}")
            return None
    
    async def _create_snapshot_if_needed(self, aggregate_id: str, aggregate_type: str):
        """필요시 스냅샷 생성"""
        try:
            # 현재 상태 재구성
            current_state = await self.rebuild_aggregate_state(aggregate_id, aggregate_type)
            current_version = self.version_cache.get(aggregate_id, 0)
            
            # 스냅샷 저장
            with self._get_db_connection() as conn:
                conn.execute('''
                INSERT OR REPLACE INTO snapshots 
                (aggregate_id, aggregate_type, version, state_data)
                VALUES (?, ?, ?, ?)
                ''', (
                    aggregate_id,
                    aggregate_type,
                    current_version,
                    json.dumps(current_state)
                ))
                conn.commit()
                
            logger.debug(f"📸 스냅샷 생성: {aggregate_id} (version {current_version})")
            
        except Exception as e:
            logger.error(f"❌ 스냅샷 생성 실패: {e}")
    
    def register_event_handler(self, event_type: EventType, handler):
        """이벤트 핸들러 등록"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
    
    async def _handle_event(self, event: Event):
        """등록된 이벤트 핸들러 실행"""
        if event.event_type in self.event_handlers:
            for handler in self.event_handlers[event.event_type]:
                try:
                    await handler(event)
                except Exception as e:
                    logger.error(f"❌ 이벤트 핸들러 실행 실패: {e}")
    
    async def get_aggregate_history(self, aggregate_id: str) -> List[Dict[str, Any]]:
        """집합체의 전체 이력 조회"""
        events = await self.get_events(aggregate_id)
        
        history = []
        for event in events:
            history.append({
                'event_id': event.event_id,
                'event_type': event.event_type.value,
                'timestamp': event.timestamp.isoformat(),
                'data': event.event_data,
                'version': event.version
            })
        
        return history
    
    async def get_system_stats(self) -> Dict[str, Any]:
        """이벤트 저장소 통계"""
        try:
            with self._get_db_connection() as conn:
                # 전체 이벤트 수
                total_events = conn.execute('SELECT COUNT(*) as count FROM events').fetchone()['count']
                
                # 집합체 수
                total_aggregates = conn.execute(
                    'SELECT COUNT(DISTINCT aggregate_id) as count FROM events'
                ).fetchone()['count']
                
                # 이벤트 타입별 통계
                type_stats = conn.execute('''
                SELECT event_type, COUNT(*) as count
                FROM events
                GROUP BY event_type
                ORDER BY count DESC
                ''').fetchall()
                
                # 최근 이벤트
                recent_events = conn.execute('''
                SELECT event_type, timestamp
                FROM events
                ORDER BY timestamp DESC
                LIMIT 10
                ''').fetchall()
                
                return {
                    'total_events': total_events,
                    'total_aggregates': total_aggregates,
                    'events_by_type': [dict(row) for row in type_stats],
                    'recent_events': [dict(row) for row in recent_events],
                    'last_updated': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"❌ 시스템 통계 조회 실패: {e}")
            return {}

class EventStoreService:
    """이벤트 저장소 서비스"""
    
    def __init__(self):
        self.event_store = EventStore()
        
    async def create_user_event(self, user_id: str, event_type: EventType, 
                              event_data: Dict[str, Any]) -> Event:
        """사용자 이벤트 생성"""
        current_version = self.event_store._get_current_version(
            self.event_store._get_db_connection().__enter__(), 
            user_id
        )
        
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            aggregate_id=user_id,
            aggregate_type='user',
            event_data=event_data,
            metadata={'source': 'web_application'},
            timestamp=datetime.now(),
            version=current_version + 1
        )
        
        await self.event_store.append_event(event)
        return event
    
    async def create_analysis_event(self, analysis_id: str, keyword: str, 
                                  event_type: EventType, 
                                  event_data: Dict[str, Any]) -> Event:
        """분석 이벤트 생성"""
        with self.event_store._get_db_connection() as conn:
            current_version = self.event_store._get_current_version(conn, analysis_id)
        
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            aggregate_id=analysis_id,
            aggregate_type='analysis',
            event_data={**event_data, 'keyword': keyword},
            metadata={'source': 'analysis_system'},
            timestamp=datetime.now(),
            version=current_version + 1
        )
        
        await self.event_store.append_event(event)
        return event
    
    async def create_keyword_event(self, keyword: str, event_type: EventType,
                                 event_data: Dict[str, Any]) -> Event:
        """키워드 이벤트 생성"""
        # 키워드를 집합체 ID로 사용
        aggregate_id = hashlib.md5(keyword.encode()).hexdigest()
        
        with self.event_store._get_db_connection() as conn:
            current_version = self.event_store._get_current_version(conn, aggregate_id)
        
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            aggregate_id=aggregate_id,
            aggregate_type='keyword',
            event_data={**event_data, 'keyword': keyword},
            metadata={'source': 'analysis_system'},
            timestamp=datetime.now(),
            version=current_version + 1
        )
        
        await self.event_store.append_event(event)
        return event


# 전역 인스턴스
_event_store_service_instance = None

def get_event_store_service() -> EventStoreService:
    """EventStoreService 싱글톤 인스턴스 반환"""
    global _event_store_service_instance
    if _event_store_service_instance is None:
        _event_store_service_instance = EventStoreService()
    return _event_store_service_instance


if __name__ == '__main__':
    # 단독 실행시 테스트
    async def test_event_store():
        service = EventStoreService()
        
        # 사용자 이벤트 생성
        await service.create_user_event(
            'user_123',
            EventType.USER_CREATED,
            {'user_id': 'user_123', 'email': 'test@example.com'}
        )
        
        await service.create_user_event(
            'user_123',
            EventType.USER_ACTION,
            {'action_type': 'page_view', 'page': 'index'}
        )
        
        # 상태 재구성
        state = await service.event_store.rebuild_aggregate_state('user_123', 'user')
        print(f"사용자 상태: {state}")
        
        # 이력 조회
        history = await service.event_store.get_aggregate_history('user_123')
        print(f"사용자 이력: {history}")
    
    asyncio.run(test_event_store())