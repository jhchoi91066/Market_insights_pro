"""
StatisticsConsumer - 통계 집계 전용 Consumer
실시간으로 들어오는 이벤트 데이터를 집계하여 대시보드용 통계를 생성합니다.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from collections import defaultdict, deque
import sqlite3
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class StatisticsConsumer:
    """
    실시간 통계 집계 Consumer
    
    집계하는 메트릭:
    1. 분석 요청 수 (시간별/일별)
    2. 키워드별 분석 빈도
    3. 평균 분석 처리 시간
    4. 성공/실패 비율
    5. 사용자별 활동 통계
    """
    
    def __init__(self, bootstrap_servers='localhost:9092'):
        self.bootstrap_servers = bootstrap_servers
        self.consumer = None
        self.running = False
        
        # 인메모리 통계 저장소 (실시간 데이터)
        self.stats = {
            'hourly_requests': defaultdict(int),  # 시간별 요청 수
            'daily_requests': defaultdict(int),   # 일별 요청 수
            'keyword_frequency': defaultdict(int),  # 키워드별 빈도
            'processing_times': deque(maxlen=1000),  # 최근 1000개 처리 시간
            'success_count': 0,
            'failure_count': 0,
            'user_activity': defaultdict(int),  # 사용자별 활동
            'category_analysis': defaultdict(int),  # 카테고리별 분석 수
        }
        
        # SQLite 통계 DB 경로
        self.stats_db_path = 'data/statistics.db'
        self._init_stats_database()
    
    def _init_stats_database(self):
        """통계용 SQLite 데이터베이스 초기화"""
        try:
            with self._get_db_connection() as conn:
                # 일별 통계 테이블
                conn.execute('''
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date TEXT PRIMARY KEY,
                    total_requests INTEGER DEFAULT 0,
                    successful_requests INTEGER DEFAULT 0,
                    failed_requests INTEGER DEFAULT 0,
                    avg_processing_time REAL DEFAULT 0.0,
                    unique_users INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                
                # 키워드 분석 통계
                conn.execute('''
                CREATE TABLE IF NOT EXISTS keyword_stats (
                    keyword TEXT PRIMARY KEY,
                    total_analyses INTEGER DEFAULT 0,
                    avg_difficulty_score REAL DEFAULT 0.0,
                    avg_competitors INTEGER DEFAULT 0,
                    last_analyzed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                
                # 사용자 활동 통계
                conn.execute('''
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id TEXT PRIMARY KEY,
                    total_analyses INTEGER DEFAULT 0,
                    successful_analyses INTEGER DEFAULT 0,
                    failed_analyses INTEGER DEFAULT 0,
                    first_analysis TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_analysis TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                
                # 시간별 요청 패턴
                conn.execute('''
                CREATE TABLE IF NOT EXISTS hourly_patterns (
                    hour INTEGER PRIMARY KEY,
                    avg_requests REAL DEFAULT 0.0,
                    peak_requests INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                
                conn.commit()
                logger.info("✅ 통계 데이터베이스 초기화 완료")
                
        except Exception as e:
            logger.error(f"❌ 통계 DB 초기화 실패: {e}")
    
    @contextmanager
    def _get_db_connection(self):
        """SQLite 연결 컨텍스트 매니저"""
        conn = None
        try:
            conn = sqlite3.connect(self.stats_db_path)
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
    
    async def start(self):
        """Consumer 시작"""
        self.running = True
        logger.info("🚀 StatisticsConsumer 시작...")
        
        try:
            # Kafka Consumer 설정
            self.consumer = KafkaConsumer(
                'statistics-events',  # 통계 이벤트 토픽
                'market-analysis-events',  # 분석 이벤트도 구독 (통계용)
                'user-actions',  # 사용자 액션도 구독
                
                bootstrap_servers=self.bootstrap_servers,
                group_id='statistics-consumers',
                auto_offset_reset='latest',
                enable_auto_commit=True,
                
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                key_deserializer=lambda x: x.decode('utf-8') if x else None,
                
                consumer_timeout_ms=1000,
            )
            
            logger.info("✅ StatisticsConsumer Kafka 연결 성공")
            
            # 백그라운드 통계 저장 태스크 시작
            asyncio.create_task(self._periodic_stats_save())
            
            # 메인 처리 루프
            while self.running:
                try:
                    messages = self.consumer.poll(timeout_ms=1000)
                    
                    if not messages:
                        continue
                    
                    for topic_partition, records in messages.items():
                        for record in records:
                            await self._process_statistics_event(record)
                            
                except Exception as e:
                    logger.error(f"❌ 통계 처리 중 오류: {e}")
                    await asyncio.sleep(5)
                    
        except Exception as e:
            logger.error(f"❌ StatisticsConsumer 시작 실패: {e}")
        finally:
            if self.consumer:
                self.consumer.close()
    
    async def _process_statistics_event(self, record):
        """통계 이벤트 처리"""
        try:
            message = record.value
            topic = record.topic
            
            if topic == 'market-analysis-events':
                await self._handle_analysis_event(message)
            elif topic == 'user-actions':
                await self._handle_user_action_event(message)
            elif topic == 'statistics-events':
                await self._handle_custom_statistics_event(message)
                
        except Exception as e:
            logger.error(f"❌ 통계 이벤트 처리 실패: {e}")
    
    async def _handle_analysis_event(self, message: Dict[str, Any]):
        """분석 이벤트 통계 처리"""
        event_type = message.get('event_type', '')
        timestamp = datetime.fromisoformat(message.get('timestamp', datetime.now().isoformat()))
        
        if event_type == 'analysis_requested':
            # 요청 통계 업데이트
            hour_key = timestamp.strftime('%Y-%m-%d %H')
            day_key = timestamp.strftime('%Y-%m-%d')
            
            self.stats['hourly_requests'][hour_key] += 1
            self.stats['daily_requests'][day_key] += 1
            
            # 키워드 빈도 업데이트
            keyword = message.get('keyword', 'unknown')
            self.stats['keyword_frequency'][keyword] += 1
            
            # 사용자 활동 업데이트
            session_id = message.get('session_id', 'anonymous')
            self.stats['user_activity'][session_id] += 1
            
            logger.debug(f"📊 분석 요청 통계 업데이트: {keyword}")
            
        elif event_type == 'analysis_completed':
            # 성공 통계 업데이트
            self.stats['success_count'] += 1
            
            # 처리 시간 통계
            data = message.get('data', {})
            processing_time = data.get('processing_time_seconds', 0)
            if processing_time > 0:
                self.stats['processing_times'].append(processing_time)
            
            # 분석 결과 통계
            results = data.get('results', {})
            if results:
                keyword = results.get('keyword', 'unknown')
                difficulty_score = results.get('difficulty_score', 0)
                competitor_count = results.get('competitor_count', 0)
                
                # 키워드별 분석 결과 업데이트 (SQLite에 직접 저장)
                await self._update_keyword_stats(keyword, difficulty_score, competitor_count)
            
            logger.debug(f"📊 분석 완료 통계 업데이트")
            
        elif event_type == 'analysis_failed':
            # 실패 통계 업데이트
            self.stats['failure_count'] += 1
            logger.debug(f"📊 분석 실패 통계 업데이트")
    
    async def _handle_user_action_event(self, message: Dict[str, Any]):
        """사용자 액션 이벤트 통계 처리"""
        action_type = message.get('action_type', '')
        user_id = message.get('user_id', 'anonymous')
        
        # 사용자별 액션 카운트
        self.stats['user_activity'][user_id] += 1
        
        # 액션 타입별 통계 (추후 확장 가능)
        if action_type == 'page_view':
            pass  # 페이지 뷰 통계
        elif action_type == 'keyword_search':
            pass  # 검색 통계
            
        logger.debug(f"📊 사용자 액션 통계 업데이트: {action_type}")
    
    async def _handle_custom_statistics_event(self, message: Dict[str, Any]):
        """커스텀 통계 이벤트 처리"""
        stat_type = message.get('stat_type', '')
        
        if stat_type == 'system_metric':
            # 시스템 메트릭 처리
            pass
        elif stat_type == 'business_metric':
            # 비즈니스 메트릭 처리
            pass
            
        logger.debug(f"📊 커스텀 통계 이벤트 처리: {stat_type}")
    
    async def _update_keyword_stats(self, keyword: str, difficulty_score: float, competitor_count: int):
        """키워드별 분석 통계 업데이트"""
        try:
            with self._get_db_connection() as conn:
                # 기존 데이터 조회
                existing = conn.execute(
                    "SELECT total_analyses, avg_difficulty_score, avg_competitors FROM keyword_stats WHERE keyword = ?",
                    (keyword,)
                ).fetchone()
                
                if existing:
                    # 기존 데이터 업데이트 (이동평균 계산)
                    total_analyses = existing['total_analyses'] + 1
                    avg_difficulty = ((existing['avg_difficulty_score'] * existing['total_analyses']) + difficulty_score) / total_analyses
                    avg_competitors = ((existing['avg_competitors'] * existing['total_analyses']) + competitor_count) / total_analyses
                    
                    conn.execute('''
                    UPDATE keyword_stats 
                    SET total_analyses = ?, avg_difficulty_score = ?, avg_competitors = ?, last_analyzed = CURRENT_TIMESTAMP
                    WHERE keyword = ?
                    ''', (total_analyses, avg_difficulty, avg_competitors, keyword))
                else:
                    # 새 키워드 추가
                    conn.execute('''
                    INSERT INTO keyword_stats (keyword, total_analyses, avg_difficulty_score, avg_competitors)
                    VALUES (?, 1, ?, ?)
                    ''', (keyword, difficulty_score, competitor_count))
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"❌ 키워드 통계 업데이트 실패: {e}")
    
    async def _periodic_stats_save(self):
        """주기적으로 인메모리 통계를 DB에 저장"""
        while self.running:
            try:
                await asyncio.sleep(300)  # 5분마다 저장
                await self._save_daily_stats()
                logger.debug("📊 일별 통계 저장 완료")
                
            except Exception as e:
                logger.error(f"❌ 주기적 통계 저장 실패: {e}")
    
    async def _save_daily_stats(self):
        """일별 통계를 DB에 저장"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            
            # 오늘의 통계 계산
            today_requests = self.stats['daily_requests'].get(today, 0)
            success_rate = self.stats['success_count'] / max(1, self.stats['success_count'] + self.stats['failure_count'])
            avg_processing_time = sum(self.stats['processing_times']) / max(1, len(self.stats['processing_times']))
            unique_users = len(self.stats['user_activity'])
            
            with self._get_db_connection() as conn:
                conn.execute('''
                INSERT OR REPLACE INTO daily_stats 
                (date, total_requests, successful_requests, failed_requests, avg_processing_time, unique_users)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    today,
                    today_requests,
                    self.stats['success_count'],
                    self.stats['failure_count'],
                    avg_processing_time,
                    unique_users
                ))
                conn.commit()
                
        except Exception as e:
            logger.error(f"❌ 일별 통계 저장 실패: {e}")
    
    def get_realtime_stats(self) -> Dict[str, Any]:
        """실시간 통계 반환 (API용)"""
        processing_times = list(self.stats['processing_times'])
        avg_processing_time = sum(processing_times) / max(1, len(processing_times))
        
        return {
            'current_session': {
                'total_requests': self.stats['success_count'] + self.stats['failure_count'],
                'success_count': self.stats['success_count'],
                'failure_count': self.stats['failure_count'],
                'success_rate': self.stats['success_count'] / max(1, self.stats['success_count'] + self.stats['failure_count']),
                'avg_processing_time': avg_processing_time,
                'active_users': len(self.stats['user_activity'])
            },
            'top_keywords': dict(sorted(self.stats['keyword_frequency'].items(), key=lambda x: x[1], reverse=True)[:10]),
            'hourly_requests': dict(self.stats['hourly_requests']),
            'daily_requests': dict(self.stats['daily_requests'])
        }
    
    async def get_historical_stats(self, days: int = 7) -> Dict[str, Any]:
        """과거 통계 조회 (DB에서)"""
        try:
            with self._get_db_connection() as conn:
                # 최근 N일 통계
                daily_stats = conn.execute('''
                SELECT * FROM daily_stats 
                WHERE date >= date('now', '-{} days')
                ORDER BY date DESC
                '''.format(days)).fetchall()
                
                # 인기 키워드 (분석 횟수 기준)
                top_keywords = conn.execute('''
                SELECT keyword, total_analyses, avg_difficulty_score 
                FROM keyword_stats 
                ORDER BY total_analyses DESC 
                LIMIT 10
                ''').fetchall()
                
                return {
                    'daily_stats': [dict(row) for row in daily_stats],
                    'top_keywords': [dict(row) for row in top_keywords]
                }
                
        except Exception as e:
            logger.error(f"❌ 과거 통계 조회 실패: {e}")
            return {}
    
    async def stop(self):
        """Consumer 종료"""
        self.running = False
        # 종료 전 마지막으로 통계 저장
        await self._save_daily_stats()
        
        if self.consumer:
            self.consumer.close()
        logger.info("🔒 StatisticsConsumer 종료")


# 전역 인스턴스
_statistics_consumer_instance = None

def get_statistics_consumer() -> StatisticsConsumer:
    """StatisticsConsumer 싱글톤 인스턴스 반환"""
    global _statistics_consumer_instance
    if _statistics_consumer_instance is None:
        _statistics_consumer_instance = StatisticsConsumer()
    return _statistics_consumer_instance

async def start_statistics_consumer():
    """
    StatisticsConsumer를 별도 태스크로 시작
    main.py의 startup 이벤트에서 호출
    """
    consumer = get_statistics_consumer()
    asyncio.create_task(consumer.start())
    logger.info("🚀 StatisticsConsumer 백그라운드 시작됨")


if __name__ == '__main__':
    # 단독 실행시 테스트
    async def test_statistics_consumer():
        consumer = StatisticsConsumer()
        await consumer.start()
    
    asyncio.run(test_statistics_consumer())