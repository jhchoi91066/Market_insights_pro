"""
데이터베이스 성능 최적화 도구
인덱스 최적화, 쿼리 분석, 연결 풀 관리 등을 담당
"""

import sqlite3
import time
import logging
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, text, inspect, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool, QueuePool
from datetime import datetime, timedelta
import threading
import json

logger = logging.getLogger(__name__)

class QueryAnalyzer:
    """
    SQL 쿼리 성능 분석기
    실행 시간, 실행 계획 등을 분석하여 최적화 포인트 제공
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.query_stats = {}
        self.slow_queries = []
        self.query_threshold = 0.1  # 100ms 이상 쿼리를 느린 쿼리로 분류
        self._setup_monitoring()

    def _setup_monitoring(self):
        """SQLAlchemy 이벤트 리스너를 설정하여 쿼리 모니터링"""

        @event.listens_for(self.engine, "before_cursor_execute")
        def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            context._query_start_time = time.time()

        @event.listens_for(self.engine, "after_cursor_execute")
        def receive_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            total_time = time.time() - context._query_start_time
            self._record_query_stats(statement, total_time, parameters)

    def _record_query_stats(self, statement: str, execution_time: float, parameters: tuple):
        """쿼리 통계 기록"""
        # 쿼리 정규화 (파라미터 제거)
        normalized_query = self._normalize_query(statement)

        if normalized_query not in self.query_stats:
            self.query_stats[normalized_query] = {
                'count': 0,
                'total_time': 0,
                'min_time': float('inf'),
                'max_time': 0,
                'avg_time': 0
            }

        stats = self.query_stats[normalized_query]
        stats['count'] += 1
        stats['total_time'] += execution_time
        stats['min_time'] = min(stats['min_time'], execution_time)
        stats['max_time'] = max(stats['max_time'], execution_time)
        stats['avg_time'] = stats['total_time'] / stats['count']

        # 느린 쿼리 기록
        if execution_time > self.query_threshold:
            self.slow_queries.append({
                'query': statement,
                'execution_time': execution_time,
                'parameters': parameters,
                'timestamp': datetime.now().isoformat()
            })

            # 최근 100개만 유지
            if len(self.slow_queries) > 100:
                self.slow_queries = self.slow_queries[-100:]

        logger.debug(f"Query executed in {execution_time:.4f}s: {normalized_query[:100]}")

    def _normalize_query(self, statement: str) -> str:
        """쿼리 정규화 (파라미터를 ? 로 치환)"""
        # 간단한 정규화 - 실제로는 더 정교한 파싱이 필요
        import re
        normalized = re.sub(r'\b\d+\b', '?', statement)
        normalized = re.sub(r"'[^']*'", '?', normalized)
        return normalized.strip()

    def get_query_statistics(self) -> Dict[str, Any]:
        """쿼리 통계 반환"""
        return {
            'total_queries': sum(stats['count'] for stats in self.query_stats.values()),
            'unique_queries': len(self.query_stats),
            'slow_queries_count': len(self.slow_queries),
            'query_stats': self.query_stats,
            'slow_queries': self.slow_queries[-10:]  # 최근 10개 느린 쿼리
        }

    def get_optimization_suggestions(self) -> List[str]:
        """최적화 제안사항 반환"""
        suggestions = []

        # 자주 실행되는 쿼리 분석
        frequent_queries = sorted(
            self.query_stats.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )[:5]

        for query, stats in frequent_queries:
            if stats['avg_time'] > self.query_threshold:
                suggestions.append(
                    f"🔍 자주 실행되는 느린 쿼리 발견 (실행 {stats['count']}회, 평균 {stats['avg_time']:.3f}s):\n"
                    f"   {query[:100]}..."
                )

        # 매우 느린 쿼리
        very_slow_queries = [q for q in self.slow_queries if q['execution_time'] > 1.0]
        if very_slow_queries:
            suggestions.append(
                f"⚠️ 1초 이상 실행되는 매우 느린 쿼리 {len(very_slow_queries)}개 발견"
            )

        return suggestions

class IndexOptimizer:
    """
    데이터베이스 인덱스 최적화 도구
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    def analyze_table_usage(self, table_name: str) -> Dict[str, Any]:
        """테이블 사용 패턴 분석"""
        with self.engine.connect() as conn:
            # SQLite의 경우 EXPLAIN QUERY PLAN 사용
            analysis = {
                'table_name': table_name,
                'row_count': 0,
                'indexes': [],
                'suggestions': []
            }

            try:
                # 행 수 조회
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                analysis['row_count'] = result.scalar()

                # 인덱스 정보 조회
                result = conn.execute(text(f"PRAGMA index_list({table_name})"))
                indexes = result.fetchall()

                for index in indexes:
                    index_info = conn.execute(text(f"PRAGMA index_info({index[1]})")).fetchall()
                    analysis['indexes'].append({
                        'name': index[1],
                        'unique': bool(index[2]),
                        'columns': [col[2] for col in index_info]
                    })

                # 최적화 제안
                if analysis['row_count'] > 1000:
                    analysis['suggestions'].append(
                        f"📊 테이블 {table_name}에 {analysis['row_count']}개 행이 있습니다. "
                        "자주 WHERE 절에 사용되는 컬럼에 인덱스 추가를 고려하세요."
                    )

            except Exception as e:
                logger.error(f"테이블 {table_name} 분석 중 오류: {e}")
                analysis['error'] = str(e)

        return analysis

    def suggest_indexes(self, table_name: str) -> List[str]:
        """인덱스 생성 제안"""
        suggestions = []

        # 테이블별 인덱스 제안
        index_recommendations = {
            'products': [
                "CREATE INDEX IF NOT EXISTS idx_products_category ON products(product_category);",
                "CREATE INDEX IF NOT EXISTS idx_products_rating ON products(product_rating);",
                "CREATE INDEX IF NOT EXISTS idx_products_price ON products(discounted_price);",
                "CREATE INDEX IF NOT EXISTS idx_products_scraped_date ON products(scraped_at);",
                "CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand);",
                "CREATE INDEX IF NOT EXISTS idx_products_prime ON products(is_prime);"
            ],
            'scraping_sessions': [
                "CREATE INDEX IF NOT EXISTS idx_sessions_keyword ON scraping_sessions(keyword);",
                "CREATE INDEX IF NOT EXISTS idx_sessions_status ON scraping_sessions(session_status);",
                "CREATE INDEX IF NOT EXISTS idx_sessions_started ON scraping_sessions(started_at);"
            ],
            'analysis_results': [
                "CREATE INDEX IF NOT EXISTS idx_analysis_category ON analysis_results(category);",
                "CREATE INDEX IF NOT EXISTS idx_analysis_type ON analysis_results(analysis_type);",
                "CREATE INDEX IF NOT EXISTS idx_analysis_created ON analysis_results(created_at);",
                "CREATE INDEX IF NOT EXISTS idx_analysis_user ON analysis_results(user_id);"
            ]
        }

        return index_recommendations.get(table_name, [])

    def create_recommended_indexes(self, table_name: str = None) -> Dict[str, Any]:
        """권장 인덱스 생성"""
        results = {'created': [], 'errors': []}

        tables = [table_name] if table_name else ['products', 'scraping_sessions', 'analysis_results']

        with self.engine.connect() as conn:
            for table in tables:
                suggestions = self.suggest_indexes(table)
                for sql in suggestions:
                    try:
                        conn.execute(text(sql))
                        results['created'].append(sql)
                        logger.info(f"인덱스 생성 성공: {sql}")
                    except Exception as e:
                        error_msg = f"인덱스 생성 실패 - {sql}: {e}"
                        results['errors'].append(error_msg)
                        logger.error(error_msg)

            conn.commit()

        return results

class ConnectionPoolManager:
    """
    데이터베이스 연결 풀 최적화 관리자
    """

    def __init__(self):
        self.pool_stats = {
            'connections_created': 0,
            'connections_reused': 0,
            'pool_size': 0,
            'checked_out': 0
        }

    def create_optimized_engine(self, database_url: str, max_connections: int = 20) -> Engine:
        """최적화된 엔진 생성"""

        if database_url.startswith('sqlite'):
            # SQLite 최적화 설정
            engine = create_engine(
                database_url,
                poolclass=StaticPool,
                pool_pre_ping=True,
                pool_recycle=3600,  # 1시간마다 연결 재생성
                connect_args={
                    "check_same_thread": False,
                    "timeout": 30,
                    # SQLite 성능 최적화 PRAGMA 설정
                    "isolation_level": None,  # autocommit 모드
                },
                echo=False  # 프로덕션에서는 False
            )

            # SQLite 최적화 설정 적용
            @event.listens_for(engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                # 성능 최적화 PRAGMA 설정
                cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
                cursor.execute("PRAGMA synchronous=NORMAL")  # 적당한 안전성
                cursor.execute("PRAGMA cache_size=10000")  # 캐시 크기 증가 (기본: 2000)
                cursor.execute("PRAGMA temp_store=MEMORY")  # 임시 테이블을 메모리에
                cursor.execute("PRAGMA mmap_size=268435456")  # 256MB 메모리 맵
                cursor.close()

        else:
            # PostgreSQL 등 다른 DB 최적화
            engine = create_engine(
                database_url,
                poolclass=QueuePool,
                pool_size=max_connections,
                max_overflow=0,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False
            )

        # 연결 풀 모니터링 설정
        self._setup_pool_monitoring(engine)

        return engine

    def _setup_pool_monitoring(self, engine: Engine):
        """연결 풀 모니터링 설정"""

        @event.listens_for(engine, "connect")
        def on_connect(dbapi_connection, connection_record):
            self.pool_stats['connections_created'] += 1

        @event.listens_for(engine, "checkout")
        def on_checkout(dbapi_connection, connection_record, connection_proxy):
            self.pool_stats['checked_out'] += 1

        @event.listens_for(engine, "checkin")
        def on_checkin(dbapi_connection, connection_record):
            if self.pool_stats['checked_out'] > 0:
                self.pool_stats['checked_out'] -= 1
                self.pool_stats['connections_reused'] += 1

    def get_pool_statistics(self, engine: Engine) -> Dict[str, Any]:
        """연결 풀 통계 조회"""
        pool = engine.pool

        stats = {
            'pool_size': getattr(pool, 'size', lambda: 'N/A')(),
            'checked_out_connections': getattr(pool, 'checkedout', lambda: 'N/A')(),
            'overflow_connections': getattr(pool, 'overflow', lambda: 'N/A')(),
            'invalid_connections': getattr(pool, 'invalidated', lambda: 'N/A')(),
            'statistics': self.pool_stats
        }

        return stats

class DatabaseOptimizer:
    """
    통합 데이터베이스 최적화 관리자
    """

    def __init__(self, database_url: str = "sqlite:///data/market_insights.db"):
        self.database_url = database_url
        self.pool_manager = ConnectionPoolManager()
        self.engine = self.pool_manager.create_optimized_engine(database_url)
        self.query_analyzer = QueryAnalyzer(self.engine)
        self.index_optimizer = IndexOptimizer(self.engine)

        logger.info("데이터베이스 최적화 시스템 초기화 완료")

    def run_health_check(self) -> Dict[str, Any]:
        """데이터베이스 건강 상태 확인"""
        health_status = {
            'timestamp': datetime.now().isoformat(),
            'database_url': self.database_url,
            'connection_test': False,
            'query_performance': {},
            'index_analysis': {},
            'pool_stats': {},
            'recommendations': []
        }

        try:
            # 연결 테스트
            with self.engine.connect() as conn:
                start_time = time.time()
                result = conn.execute(text("SELECT 1"))
                connection_time = time.time() - start_time

                health_status['connection_test'] = True
                health_status['connection_time_ms'] = round(connection_time * 1000, 2)

            # 쿼리 성능 통계
            health_status['query_performance'] = self.query_analyzer.get_query_statistics()

            # 테이블별 인덱스 분석
            tables = ['products', 'scraping_sessions', 'analysis_results']
            for table in tables:
                health_status['index_analysis'][table] = self.index_optimizer.analyze_table_usage(table)

            # 연결 풀 통계
            health_status['pool_stats'] = self.pool_manager.get_pool_statistics(self.engine)

            # 최적화 권장사항
            health_status['recommendations'] = self.query_analyzer.get_optimization_suggestions()

        except Exception as e:
            health_status['error'] = str(e)
            logger.error(f"데이터베이스 헬스체크 실패: {e}")

        return health_status

    def optimize_database(self) -> Dict[str, Any]:
        """데이터베이스 최적화 실행"""
        optimization_results = {
            'timestamp': datetime.now().isoformat(),
            'indexes_created': [],
            'optimizations_applied': [],
            'errors': []
        }

        try:
            # 권장 인덱스 생성
            index_results = self.index_optimizer.create_recommended_indexes()
            optimization_results['indexes_created'] = index_results['created']
            optimization_results['errors'].extend(index_results['errors'])

            # SQLite VACUUM 실행 (데이터베이스 정리)
            if self.database_url.startswith('sqlite'):
                with self.engine.connect() as conn:
                    conn.execute(text("VACUUM"))
                    optimization_results['optimizations_applied'].append("SQLite VACUUM 실행")

            # ANALYZE 실행 (통계 업데이트)
            with self.engine.connect() as conn:
                conn.execute(text("ANALYZE"))
                optimization_results['optimizations_applied'].append("통계 정보 업데이트 (ANALYZE)")

            logger.info("데이터베이스 최적화 완료")

        except Exception as e:
            error_msg = f"데이터베이스 최적화 중 오류: {e}"
            optimization_results['errors'].append(error_msg)
            logger.error(error_msg)

        return optimization_results

    def get_engine(self) -> Engine:
        """최적화된 엔진 반환"""
        return self.engine

# 전역 최적화 인스턴스
db_optimizer = DatabaseOptimizer()

def get_optimized_engine() -> Engine:
    """최적화된 데이터베이스 엔진 반환"""
    return db_optimizer.get_engine()

def get_database_optimizer() -> DatabaseOptimizer:
    """데이터베이스 최적화 매니저 반환"""
    return db_optimizer

if __name__ == '__main__':
    # 테스트 실행
    optimizer = DatabaseOptimizer()

    print("=== 데이터베이스 헬스체크 ===")
    health = optimizer.run_health_check()
    print(json.dumps(health, indent=2, ensure_ascii=False))

    print("\n=== 데이터베이스 최적화 실행 ===")
    results = optimizer.optimize_database()
    print(json.dumps(results, indent=2, ensure_ascii=False))