"""
StreamProcessor - 실시간 스트리밍 데이터 처리
Kafka 이벤트를 실시간으로 처리하여 시장 동향 분석, 이상치 탐지, 윈도우 집계를 수행합니다.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict, deque
from kafka import KafkaConsumer
from kafka.errors import KafkaError
import sqlite3
from contextlib import contextmanager
import statistics
import time

logger = logging.getLogger(__name__)

class TimeWindowAggregator:
    """시간 윈도우 기반 데이터 집계"""
    
    def __init__(self, window_size_minutes: int = 15):
        self.window_size = timedelta(minutes=window_size_minutes)
        self.sliding_windows = defaultdict(deque)  # keyword -> [(timestamp, data), ...]
        self.tumbling_windows = defaultdict(dict)  # keyword -> {window_start: aggregated_data}
    
    def add_data_point(self, keyword: str, timestamp: datetime, data: Dict[str, Any]):
        """데이터 포인트를 윈도우에 추가"""
        # Sliding window에 추가
        self.sliding_windows[keyword].append((timestamp, data))
        
        # 오래된 데이터 제거 (sliding window 유지)
        cutoff_time = timestamp - self.window_size
        while (self.sliding_windows[keyword] and 
               self.sliding_windows[keyword][0][0] < cutoff_time):
            self.sliding_windows[keyword].popleft()
    
    def get_sliding_window_stats(self, keyword: str) -> Dict[str, Any]:
        """슬라이딩 윈도우 통계 계산"""
        if keyword not in self.sliding_windows or not self.sliding_windows[keyword]:
            return {}
        
        window_data = list(self.sliding_windows[keyword])
        
        # 가격 데이터 추출
        prices = []
        ratings = []
        competitor_counts = []
        
        for timestamp, data in window_data:
            if 'avg_price' in data:
                prices.append(data['avg_price'])
            if 'avg_rating' in data:
                ratings.append(data['avg_rating'])
            if 'competitor_count' in data:
                competitor_counts.append(data['competitor_count'])
        
        stats = {
            'window_size_minutes': self.window_size.total_seconds() / 60,
            'data_points': len(window_data),
            'time_range': {
                'start': window_data[0][0].isoformat() if window_data else None,
                'end': window_data[-1][0].isoformat() if window_data else None
            }
        }
        
        # 가격 통계
        if prices:
            stats['price_stats'] = {
                'mean': statistics.mean(prices),
                'median': statistics.median(prices),
                'min': min(prices),
                'max': max(prices),
                'std_dev': statistics.stdev(prices) if len(prices) > 1 else 0,
                'volatility': (max(prices) - min(prices)) / statistics.mean(prices) if prices else 0
            }
        
        # 평점 통계
        if ratings:
            stats['rating_stats'] = {
                'mean': statistics.mean(ratings),
                'median': statistics.median(ratings),
                'trend': 'stable'  # 추후 트렌드 분석 로직 추가
            }
        
        # 경쟁 강도 통계
        if competitor_counts:
            stats['competition_stats'] = {
                'mean_competitors': statistics.mean(competitor_counts),
                'max_competitors': max(competitor_counts),
                'competition_level': 'high' if statistics.mean(competitor_counts) > 50 else 'medium' if statistics.mean(competitor_counts) > 20 else 'low'
            }
        
        return stats

class AnomalyDetector:
    """이상치 탐지 시스템"""
    
    def __init__(self, threshold_std_dev: float = 2.0):
        self.threshold = threshold_std_dev
        self.historical_data = defaultdict(deque)  # keyword -> [price_history]
        self.max_history = 100  # 최대 100개 데이터 포인트 유지
    
    def add_price_data(self, keyword: str, price: float, timestamp: datetime):
        """가격 데이터 추가 및 이상치 탐지"""
        self.historical_data[keyword].append((timestamp, price))
        
        # 최대 이력 유지
        if len(self.historical_data[keyword]) > self.max_history:
            self.historical_data[keyword].popleft()
    
    def detect_price_anomaly(self, keyword: str, current_price: float) -> Dict[str, Any]:
        """가격 이상치 탐지"""
        if keyword not in self.historical_data or len(self.historical_data[keyword]) < 10:
            return {'is_anomaly': False, 'reason': 'insufficient_data'}
        
        # 과거 가격 데이터
        prices = [price for _, price in self.historical_data[keyword]]
        mean_price = statistics.mean(prices)
        
        if len(prices) < 2:
            return {'is_anomaly': False, 'reason': 'insufficient_variance_data'}
        
        std_dev = statistics.stdev(prices)
        
        # Z-score 계산
        if std_dev == 0:
            z_score = 0
        else:
            z_score = abs(current_price - mean_price) / std_dev
        
        is_anomaly = z_score > self.threshold
        
        return {
            'is_anomaly': is_anomaly,
            'z_score': z_score,
            'threshold': self.threshold,
            'current_price': current_price,
            'mean_price': mean_price,
            'price_change_percent': ((current_price - mean_price) / mean_price * 100) if mean_price > 0 else 0,
            'severity': 'high' if z_score > 3 else 'medium' if z_score > 2 else 'low',
            'timestamp': datetime.now().isoformat()
        }

class MarketTrendAnalyzer:
    """실시간 시장 트렌드 분석"""
    
    def __init__(self):
        self.keyword_trends = defaultdict(list)  # keyword -> [(timestamp, metrics), ...]
        self.global_trends = []
        self.trend_window = timedelta(hours=1)  # 1시간 트렌드 윈도우
    
    def analyze_keyword_trend(self, keyword: str, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """키워드별 트렌드 분석"""
        timestamp = datetime.now()
        
        # 트렌드 데이터 추가
        trend_point = {
            'timestamp': timestamp,
            'competitor_count': analysis_data.get('competitor_count', 0),
            'avg_price': analysis_data.get('avg_price', 0),
            'avg_rating': analysis_data.get('avg_rating', 0),
            'difficulty_score': analysis_data.get('difficulty_score', 0)
        }
        
        self.keyword_trends[keyword].append(trend_point)
        
        # 오래된 데이터 제거
        cutoff_time = timestamp - self.trend_window
        self.keyword_trends[keyword] = [
            point for point in self.keyword_trends[keyword] 
            if point['timestamp'] > cutoff_time
        ]
        
        # 트렌드 분석
        if len(self.keyword_trends[keyword]) < 2:
            return {'trend': 'insufficient_data', 'keyword': keyword}
        
        trend_data = self.keyword_trends[keyword]
        
        # 경쟁 강도 트렌드
        competitor_counts = [point['competitor_count'] for point in trend_data]
        competitor_trend = self._calculate_trend(competitor_counts)
        
        # 가격 트렌드
        prices = [point['avg_price'] for point in trend_data if point['avg_price'] > 0]
        price_trend = self._calculate_trend(prices) if prices else 'stable'
        
        # 난이도 트렌드
        difficulties = [point['difficulty_score'] for point in trend_data if point['difficulty_score'] > 0]
        difficulty_trend = self._calculate_trend(difficulties) if difficulties else 'stable'
        
        return {
            'keyword': keyword,
            'analysis_timestamp': timestamp.isoformat(),
            'data_points': len(trend_data),
            'time_window_hours': self.trend_window.total_seconds() / 3600,
            'trends': {
                'competition': {
                    'direction': competitor_trend,
                    'current_count': competitor_counts[-1] if competitor_counts else 0,
                    'change_rate': self._calculate_change_rate(competitor_counts) if len(competitor_counts) > 1 else 0
                },
                'pricing': {
                    'direction': price_trend,
                    'current_price': prices[-1] if prices else 0,
                    'change_rate': self._calculate_change_rate(prices) if len(prices) > 1 else 0
                },
                'difficulty': {
                    'direction': difficulty_trend,
                    'current_score': difficulties[-1] if difficulties else 0,
                    'change_rate': self._calculate_change_rate(difficulties) if len(difficulties) > 1 else 0
                }
            },
            'market_signal': self._generate_market_signal(competitor_trend, price_trend, difficulty_trend),
            'recommendation': self._generate_recommendation(competitor_trend, price_trend, difficulty_trend)
        }
    
    def _calculate_trend(self, values: List[float]) -> str:
        """값 목록의 트렌드 계산"""
        if len(values) < 2:
            return 'stable'
        
        # 선형 회귀의 기울기로 트렌드 판단
        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        
        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return 'stable'
        
        slope = numerator / denominator
        
        # 기울기 기반 트렌드 분류
        if slope > 0.1:
            return 'increasing'
        elif slope < -0.1:
            return 'decreasing'
        else:
            return 'stable'
    
    def _calculate_change_rate(self, values: List[float]) -> float:
        """변화율 계산 (첫 값 대비 마지막 값)"""
        if len(values) < 2 or values[0] == 0:
            return 0
        return ((values[-1] - values[0]) / values[0]) * 100
    
    def _generate_market_signal(self, competitor_trend: str, price_trend: str, difficulty_trend: str) -> str:
        """시장 신호 생성"""
        if competitor_trend == 'increasing' and difficulty_trend == 'increasing':
            return 'market_heating_up'
        elif competitor_trend == 'decreasing' and difficulty_trend == 'decreasing':
            return 'market_cooling_down'
        elif price_trend == 'increasing' and competitor_trend == 'stable':
            return 'price_inflation'
        elif price_trend == 'decreasing' and competitor_trend == 'increasing':
            return 'price_competition'
        else:
            return 'market_stable'
    
    def _generate_recommendation(self, competitor_trend: str, price_trend: str, difficulty_trend: str) -> str:
        """투자/진입 추천 생성"""
        if competitor_trend == 'decreasing' and difficulty_trend == 'decreasing':
            return 'good_entry_opportunity'
        elif competitor_trend == 'increasing' and difficulty_trend == 'increasing':
            return 'avoid_entry_high_competition'
        elif price_trend == 'increasing' and competitor_trend == 'stable':
            return 'monitor_price_trends'
        else:
            return 'neutral_market_conditions'

class StreamProcessor:
    """메인 스트림 프로세서"""
    
    def __init__(self, bootstrap_servers='localhost:9092'):
        self.bootstrap_servers = bootstrap_servers
        self.consumer = None
        self.running = False
        
        # 컴포넌트 초기화
        self.time_aggregator = TimeWindowAggregator(window_size_minutes=15)
        self.anomaly_detector = AnomalyDetector(threshold_std_dev=2.0)
        self.trend_analyzer = MarketTrendAnalyzer()
        
        # 처리 결과 저장
        self.processed_results = []
        
        # SQLite 스트림 처리 결과 DB
        self.stream_db_path = 'data/stream_processing.db'
        self._init_stream_database()
    
    def _init_stream_database(self):
        """스트림 처리 결과 저장용 데이터베이스 초기화"""
        try:
            with self._get_db_connection() as conn:
                # 시간 윈도우 집계 결과
                conn.execute('''
                CREATE TABLE IF NOT EXISTS window_aggregations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT,
                    window_start TIMESTAMP,
                    window_end TIMESTAMP,
                    data_points INTEGER,
                    avg_price REAL,
                    price_volatility REAL,
                    avg_rating REAL,
                    competition_level TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                
                # 이상치 탐지 결과
                conn.execute('''
                CREATE TABLE IF NOT EXISTS anomaly_detections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT,
                    current_price REAL,
                    mean_price REAL,
                    z_score REAL,
                    severity TEXT,
                    price_change_percent REAL,
                    detected_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                
                # 시장 트렌드 분석 결과
                conn.execute('''
                CREATE TABLE IF NOT EXISTS market_trends (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT,
                    competition_trend TEXT,
                    price_trend TEXT,
                    difficulty_trend TEXT,
                    market_signal TEXT,
                    recommendation TEXT,
                    data_points INTEGER,
                    analyzed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                
                conn.commit()
                logger.info("✅ 스트림 처리 데이터베이스 초기화 완료")
                
        except Exception as e:
            logger.error(f"❌ 스트림 처리 DB 초기화 실패: {e}")
    
    @contextmanager
    def _get_db_connection(self):
        """SQLite 연결 컨텍스트 매니저"""
        conn = None
        try:
            conn = sqlite3.connect(self.stream_db_path)
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
        """스트림 프로세서 시작"""
        self.running = True
        logger.info("🚀 StreamProcessor 시작...")
        
        try:
            # Kafka Consumer 설정
            self.consumer = KafkaConsumer(
                'market-analysis-events',    # 분석 완료 이벤트
                'statistics-events',         # 통계 이벤트
                
                bootstrap_servers=self.bootstrap_servers,
                group_id='stream-processors',
                auto_offset_reset='latest',
                enable_auto_commit=True,
                
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                key_deserializer=lambda x: x.decode('utf-8') if x else None,
                
                consumer_timeout_ms=1000,
            )
            
            logger.info("✅ StreamProcessor Kafka 연결 성공")
            
            # 메인 스트림 처리 루프
            while self.running:
                try:
                    messages = self.consumer.poll(timeout_ms=1000)
                    
                    if not messages:
                        continue
                    
                    for topic_partition, records in messages.items():
                        for record in records:
                            await self._process_stream_event(record)
                            
                except Exception as e:
                    logger.error(f"❌ 스트림 처리 중 오류: {e}")
                    await asyncio.sleep(5)
                    
        except Exception as e:
            logger.error(f"❌ StreamProcessor 시작 실패: {e}")
        finally:
            if self.consumer:
                self.consumer.close()
    
    async def _process_stream_event(self, record):
        """스트림 이벤트 처리"""
        try:
            message = record.value
            topic = record.topic
            timestamp = datetime.now()
            
            if topic == 'market-analysis-events':
                await self._handle_analysis_event(message, timestamp)
            elif topic == 'statistics-events':
                await self._handle_statistics_event(message, timestamp)
                
        except Exception as e:
            logger.error(f"❌ 스트림 이벤트 처리 실패: {e}")
    
    async def _handle_analysis_event(self, message: Dict[str, Any], timestamp: datetime):
        """분석 이벤트 스트림 처리"""
        event_type = message.get('event_type', '')
        
        if event_type == 'analysis_completed':
            keyword = message.get('keyword', 'unknown')
            data = message.get('data', {})
            results = data.get('results', {})
            
            if not results:
                return
            
            # 1. 시간 윈도우 집계
            self.time_aggregator.add_data_point(keyword, timestamp, results)
            window_stats = self.time_aggregator.get_sliding_window_stats(keyword)
            
            if window_stats:
                await self._save_window_aggregation(keyword, window_stats, timestamp)
            
            # 2. 이상치 탐지
            avg_price = results.get('avg_price', 0)
            if avg_price > 0:
                self.anomaly_detector.add_price_data(keyword, avg_price, timestamp)
                anomaly_result = self.anomaly_detector.detect_price_anomaly(keyword, avg_price)
                
                if anomaly_result['is_anomaly']:
                    await self._save_anomaly_detection(keyword, anomaly_result)
                    logger.warning(f"🚨 가격 이상치 탐지: {keyword} - {anomaly_result['severity']} 심각도")
            
            # 3. 시장 트렌드 분석
            trend_result = self.trend_analyzer.analyze_keyword_trend(keyword, results)
            await self._save_market_trend(keyword, trend_result)
            
            # 중요한 시장 신호 로깅
            if trend_result['market_signal'] in ['market_heating_up', 'price_competition']:
                logger.info(f"📈 시장 신호 감지: {keyword} - {trend_result['market_signal']}")
            
            logger.debug(f"📊 스트림 처리 완료: {keyword}")
    
    async def _handle_statistics_event(self, message: Dict[str, Any], timestamp: datetime):
        """통계 이벤트 스트림 처리"""
        # 통계 이벤트에 대한 추가 스트림 처리 로직
        stat_type = message.get('stat_type', '')
        
        if stat_type == 'system_metric':
            # 시스템 메트릭 기반 스트림 처리
            pass
        elif stat_type == 'business_metric':
            # 비즈니스 메트릭 기반 스트림 처리  
            pass
    
    async def _save_window_aggregation(self, keyword: str, stats: Dict[str, Any], timestamp: datetime):
        """시간 윈도우 집계 결과 저장"""
        try:
            with self._get_db_connection() as conn:
                time_range = stats.get('time_range', {})
                price_stats = stats.get('price_stats', {})
                competition_stats = stats.get('competition_stats', {})
                
                conn.execute('''
                INSERT INTO window_aggregations 
                (keyword, window_start, window_end, data_points, avg_price, price_volatility, avg_rating, competition_level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    keyword,
                    time_range.get('start'),
                    time_range.get('end'),
                    stats.get('data_points', 0),
                    price_stats.get('mean', 0),
                    price_stats.get('volatility', 0),
                    stats.get('rating_stats', {}).get('mean', 0),
                    competition_stats.get('competition_level', 'unknown')
                ))
                conn.commit()
                
        except Exception as e:
            logger.error(f"❌ 윈도우 집계 저장 실패: {e}")
    
    async def _save_anomaly_detection(self, keyword: str, anomaly: Dict[str, Any]):
        """이상치 탐지 결과 저장"""
        try:
            with self._get_db_connection() as conn:
                conn.execute('''
                INSERT INTO anomaly_detections 
                (keyword, current_price, mean_price, z_score, severity, price_change_percent, detected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    keyword,
                    anomaly['current_price'],
                    anomaly['mean_price'],
                    anomaly['z_score'],
                    anomaly['severity'],
                    anomaly['price_change_percent'],
                    anomaly['timestamp']
                ))
                conn.commit()
                
        except Exception as e:
            logger.error(f"❌ 이상치 탐지 저장 실패: {e}")
    
    async def _save_market_trend(self, keyword: str, trend: Dict[str, Any]):
        """시장 트렌드 분석 결과 저장"""
        try:
            with self._get_db_connection() as conn:
                trends = trend.get('trends', {})
                
                conn.execute('''
                INSERT INTO market_trends 
                (keyword, competition_trend, price_trend, difficulty_trend, market_signal, recommendation, data_points, analyzed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    keyword,
                    trends.get('competition', {}).get('direction', 'stable'),
                    trends.get('pricing', {}).get('direction', 'stable'),
                    trends.get('difficulty', {}).get('direction', 'stable'),
                    trend['market_signal'],
                    trend['recommendation'],
                    trend['data_points'],
                    trend['analysis_timestamp']
                ))
                conn.commit()
                
        except Exception as e:
            logger.error(f"❌ 시장 트렌드 저장 실패: {e}")
    
    def get_recent_insights(self, hours: int = 1) -> Dict[str, Any]:
        """최근 시간 동안의 스트림 처리 인사이트 조회"""
        try:
            with self._get_db_connection() as conn:
                cutoff_time = datetime.now() - timedelta(hours=hours)
                
                # 최근 이상치 탐지
                anomalies = conn.execute('''
                SELECT keyword, severity, price_change_percent, detected_at
                FROM anomaly_detections 
                WHERE datetime(detected_at) > datetime(?)
                ORDER BY detected_at DESC
                LIMIT 10
                ''', (cutoff_time.isoformat(),)).fetchall()
                
                # 최근 시장 신호
                market_signals = conn.execute('''
                SELECT keyword, market_signal, recommendation, analyzed_at
                FROM market_trends 
                WHERE datetime(analyzed_at) > datetime(?) AND market_signal != 'market_stable'
                ORDER BY analyzed_at DESC
                LIMIT 10
                ''', (cutoff_time.isoformat(),)).fetchall()
                
                return {
                    'time_window_hours': hours,
                    'anomalies_detected': [dict(row) for row in anomalies],
                    'market_signals': [dict(row) for row in market_signals],
                    'summary': {
                        'total_anomalies': len(anomalies),
                        'critical_signals': len([s for s in market_signals if 'heating_up' in dict(s)['market_signal']])
                    }
                }
                
        except Exception as e:
            logger.error(f"❌ 인사이트 조회 실패: {e}")
            return {}
    
    async def stop(self):
        """스트림 프로세서 종료"""
        self.running = False
        if self.consumer:
            self.consumer.close()
        logger.info("🔒 StreamProcessor 종료")


# 전역 인스턴스
_stream_processor_instance = None

def get_stream_processor() -> StreamProcessor:
    """StreamProcessor 싱글톤 인스턴스 반환"""
    global _stream_processor_instance
    if _stream_processor_instance is None:
        _stream_processor_instance = StreamProcessor()
    return _stream_processor_instance

async def start_stream_processor():
    """
    StreamProcessor를 별도 태스크로 시작
    main.py의 startup 이벤트에서 호출
    """
    processor = get_stream_processor()
    asyncio.create_task(processor.start())
    logger.info("🚀 StreamProcessor 백그라운드 시작됨")


if __name__ == '__main__':
    # 단독 실행시 테스트
    async def test_stream_processor():
        processor = StreamProcessor()
        await processor.start()
    
    asyncio.run(test_stream_processor())