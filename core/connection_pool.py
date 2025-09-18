"""
데이터베이스 연결 풀 및 읽기 전용 복제본 관리
SQLite에서는 읽기 복제본 개념을 WAL 모드와 다중 연결로 시뮬레이션
"""

import sqlite3
import threading
import time
import logging
from contextlib import contextmanager
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from queue import Queue, Empty
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ConnectionType(Enum):
    """연결 타입"""
    READ_WRITE = "read_write"
    READ_ONLY = "read_only"

@dataclass
class ConnectionInfo:
    """연결 정보"""
    connection: sqlite3.Connection
    connection_type: ConnectionType
    created_at: datetime
    last_used: datetime
    usage_count: int = 0
    thread_id: Optional[int] = None

class SQLiteConnectionPool:
    """
    SQLite 연결 풀 매니저

    SQLite는 동시 쓰기를 지원하지 않지만, WAL 모드에서는
    다중 읽기 연결을 통해 성능을 향상시킬 수 있음
    """

    def __init__(
        self,
        database_path: str = "data/market_insights.db",
        max_connections: int = 10,
        max_read_connections: int = 5,
        connection_timeout: int = 30,
        max_idle_time: int = 300  # 5분
    ):
        self.database_path = database_path
        self.max_connections = max_connections
        self.max_read_connections = max_read_connections
        self.connection_timeout = connection_timeout
        self.max_idle_time = max_idle_time

        # 연결 풀
        self._write_connection: Optional[ConnectionInfo] = None
        self._read_connections: Queue = Queue(maxsize=max_read_connections)
        self._all_connections: Dict[int, ConnectionInfo] = {}

        # 통계
        self._stats = {
            'total_connections_created': 0,
            'read_connections_created': 0,
            'write_connections_created': 0,
            'connections_reused': 0,
            'connections_closed': 0,
            'read_queries': 0,
            'write_queries': 0,
            'connection_timeouts': 0
        }

        # 락
        self._write_lock = threading.RLock()
        self._pool_lock = threading.Lock()

        # 정리 스레드
        self._cleanup_thread = threading.Thread(target=self._cleanup_idle_connections, daemon=True)
        self._cleanup_thread.start()

        logger.info(f"SQLite 연결 풀 초기화: 최대 {max_connections}개 연결 (읽기: {max_read_connections})")

    def _create_connection(self, connection_type: ConnectionType) -> sqlite3.Connection:
        """새 데이터베이스 연결 생성"""

        try:
            # WAL 모드를 위한 연결 설정
            conn = sqlite3.connect(
                self.database_path,
                timeout=self.connection_timeout,
                check_same_thread=False,  # 다중 스레드 지원
                isolation_level=None  # autocommit 모드
            )

            # SQLite 최적화 설정
            cursor = conn.cursor()

            if connection_type == ConnectionType.READ_WRITE:
                # 쓰기 연결 최적화
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA cache_size=10000")
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.execute("PRAGMA mmap_size=268435456")  # 256MB
                cursor.execute("PRAGMA wal_autocheckpoint=1000")

                self._stats['write_connections_created'] += 1
                logger.debug("쓰기 연결 생성됨")

            else:
                # 읽기 연결 최적화
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA query_only=1")  # 읽기 전용 모드
                cursor.execute("PRAGMA cache_size=5000")
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.execute("PRAGMA mmap_size=134217728")  # 128MB

                self._stats['read_connections_created'] += 1
                logger.debug("읽기 연결 생성됨")

            cursor.close()
            self._stats['total_connections_created'] += 1

            return conn

        except sqlite3.Error as e:
            logger.error(f"데이터베이스 연결 생성 실패: {e}")
            raise

    def _get_write_connection(self) -> ConnectionInfo:
        """쓰기 연결 획득 (싱글톤)"""

        with self._write_lock:
            current_time = datetime.now()

            # 기존 쓰기 연결 확인
            if self._write_connection:
                # 연결이 살아있는지 확인
                try:
                    self._write_connection.connection.execute("SELECT 1")
                    self._write_connection.last_used = current_time
                    self._write_connection.usage_count += 1
                    self._stats['connections_reused'] += 1
                    return self._write_connection
                except sqlite3.Error:
                    # 연결이 죽었으면 새로 생성
                    self._close_connection_info(self._write_connection)
                    self._write_connection = None

            # 새 쓰기 연결 생성
            conn = self._create_connection(ConnectionType.READ_WRITE)
            conn_info = ConnectionInfo(
                connection=conn,
                connection_type=ConnectionType.READ_WRITE,
                created_at=current_time,
                last_used=current_time,
                thread_id=threading.get_ident()
            )

            self._write_connection = conn_info
            self._all_connections[id(conn_info)] = conn_info

            return conn_info

    def _get_read_connection(self) -> ConnectionInfo:
        """읽기 연결 획득"""

        current_time = datetime.now()

        # 풀에서 사용 가능한 읽기 연결 가져오기
        try:
            conn_info = self._read_connections.get_nowait()

            # 연결 상태 확인
            try:
                conn_info.connection.execute("SELECT 1")
                conn_info.last_used = current_time
                conn_info.usage_count += 1
                self._stats['connections_reused'] += 1
                return conn_info
            except sqlite3.Error:
                # 죽은 연결은 제거
                self._close_connection_info(conn_info)

        except Empty:
            pass

        # 새 읽기 연결 생성
        if len([c for c in self._all_connections.values()
                if c.connection_type == ConnectionType.READ_ONLY]) < self.max_read_connections:

            conn = self._create_connection(ConnectionType.READ_ONLY)
            conn_info = ConnectionInfo(
                connection=conn,
                connection_type=ConnectionType.READ_ONLY,
                created_at=current_time,
                last_used=current_time,
                thread_id=threading.get_ident()
            )

            with self._pool_lock:
                self._all_connections[id(conn_info)] = conn_info

            return conn_info

        # 연결 한도 초과시 기존 쓰기 연결 사용 (읽기 목적)
        logger.warning("읽기 연결 한도 초과, 쓰기 연결 사용")
        return self._get_write_connection()

    def _return_read_connection(self, conn_info: ConnectionInfo):
        """읽기 연결을 풀에 반환"""

        if conn_info.connection_type == ConnectionType.READ_ONLY:
            try:
                self._read_connections.put_nowait(conn_info)
            except:
                # 풀이 가득하면 연결 닫기
                self._close_connection_info(conn_info)

    def _close_connection_info(self, conn_info: ConnectionInfo):
        """연결 정보 정리"""

        try:
            conn_info.connection.close()
            self._stats['connections_closed'] += 1
        except:
            pass

        with self._pool_lock:
            conn_id = id(conn_info)
            if conn_id in self._all_connections:
                del self._all_connections[conn_id]

    @contextmanager
    def get_connection(self, read_only: bool = True):
        """
        연결 컨텍스트 매니저

        Args:
            read_only: True면 읽기 연결, False면 쓰기 연결
        """

        start_time = time.time()
        conn_info = None

        try:
            if read_only:
                conn_info = self._get_read_connection()
                self._stats['read_queries'] += 1
            else:
                conn_info = self._get_write_connection()
                self._stats['write_queries'] += 1

            yield conn_info.connection

        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower():
                self._stats['connection_timeouts'] += 1
                logger.warning(f"데이터베이스 락 타임아웃: {e}")
            raise

        except Exception as e:
            logger.error(f"데이터베이스 연결 오류: {e}")
            raise

        finally:
            # 읽기 연결은 풀에 반환, 쓰기 연결은 유지
            if conn_info and conn_info.connection_type == ConnectionType.READ_ONLY:
                self._return_read_connection(conn_info)

            # 성능 로그
            duration = time.time() - start_time
            if duration > 1.0:  # 1초 이상 걸린 쿼리
                logger.warning(f"느린 쿼리 감지: {duration:.2f}초 (읽기: {read_only})")

    def _cleanup_idle_connections(self):
        """유휴 연결 정리 스레드"""

        while True:
            try:
                time.sleep(60)  # 1분마다 실행
                current_time = datetime.now()
                idle_threshold = current_time - timedelta(seconds=self.max_idle_time)

                connections_to_close = []

                with self._pool_lock:
                    for conn_info in self._all_connections.values():
                        if (conn_info.connection_type == ConnectionType.READ_ONLY and
                            conn_info.last_used < idle_threshold):
                            connections_to_close.append(conn_info)

                # 유휴 읽기 연결 정리
                for conn_info in connections_to_close:
                    self._close_connection_info(conn_info)
                    logger.debug(f"유휴 연결 정리: {conn_info.usage_count}회 사용됨")

            except Exception as e:
                logger.error(f"연결 정리 스레드 오류: {e}")

    def get_pool_stats(self) -> Dict[str, Any]:
        """연결 풀 통계 조회"""

        with self._pool_lock:
            active_connections = len(self._all_connections)
            read_connections = len([c for c in self._all_connections.values()
                                  if c.connection_type == ConnectionType.READ_ONLY])
            write_connections = len([c for c in self._all_connections.values()
                                   if c.connection_type == ConnectionType.READ_WRITE])

        return {
            **self._stats,
            'active_connections': active_connections,
            'read_connections_active': read_connections,
            'write_connections_active': write_connections,
            'read_pool_size': self._read_connections.qsize(),
            'max_connections': self.max_connections,
            'max_read_connections': self.max_read_connections,
            'timestamp': datetime.now().isoformat()
        }

    def execute_read_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """읽기 쿼리 실행 헬퍼"""

        with self.get_connection(read_only=True) as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # 컬럼명과 함께 결과 반환
            columns = [description[0] for description in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))

            cursor.close()
            return results

    def execute_write_query(self, query: str, params: tuple = None) -> int:
        """쓰기 쿼리 실행 헬퍼"""

        with self.get_connection(read_only=False) as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            affected_rows = cursor.rowcount
            conn.commit()
            cursor.close()
            return affected_rows

    def close_all_connections(self):
        """모든 연결 종료"""

        with self._pool_lock:
            # 모든 연결 닫기
            for conn_info in list(self._all_connections.values()):
                self._close_connection_info(conn_info)

            # 풀 정리
            while not self._read_connections.empty():
                try:
                    self._read_connections.get_nowait()
                except Empty:
                    break

            self._write_connection = None
            logger.info("모든 데이터베이스 연결이 종료되었습니다.")

class DatabaseReadReplicaSimulator:
    """
    읽기 복제본 시뮬레이터 (SQLite용)

    실제 복제본이 아닌 읽기 최적화된 별도 연결을 통해
    읽기 성능을 향상시키는 시뮬레이션
    """

    def __init__(self, connection_pool: SQLiteConnectionPool):
        self.connection_pool = connection_pool

    def route_query(self, query: str, read_only: bool = None) -> bool:
        """쿼리 라우팅 결정"""

        if read_only is not None:
            return read_only

        # 쿼리 패턴으로 자동 라우팅 결정
        query_lower = query.strip().lower()

        # 읽기 쿼리 패턴
        read_patterns = ['select', 'with', 'explain', 'pragma']

        # 쓰기 쿼리 패턴
        write_patterns = ['insert', 'update', 'delete', 'create', 'alter', 'drop']

        for pattern in read_patterns:
            if query_lower.startswith(pattern):
                return True

        for pattern in write_patterns:
            if query_lower.startswith(pattern):
                return False

        # 기본값: 읽기로 간주
        return True

    def execute_smart_query(self, query: str, params: tuple = None, read_only: bool = None):
        """스마트 쿼리 라우팅 실행"""

        is_read_only = self.route_query(query, read_only)

        if is_read_only:
            return self.connection_pool.execute_read_query(query, params)
        else:
            return self.connection_pool.execute_write_query(query, params)

# 전역 연결 풀 인스턴스
_connection_pool: Optional[SQLiteConnectionPool] = None
_read_replica_simulator: Optional[DatabaseReadReplicaSimulator] = None

def get_connection_pool() -> SQLiteConnectionPool:
    """연결 풀 인스턴스 반환"""
    global _connection_pool

    if _connection_pool is None:
        _connection_pool = SQLiteConnectionPool()

    return _connection_pool

def get_read_replica_simulator() -> DatabaseReadReplicaSimulator:
    """읽기 복제본 시뮬레이터 반환"""
    global _read_replica_simulator

    if _read_replica_simulator is None:
        _read_replica_simulator = DatabaseReadReplicaSimulator(get_connection_pool())

    return _read_replica_simulator

def init_connection_pool(database_path: str = "data/market_insights.db", **kwargs):
    """연결 풀 초기화"""
    global _connection_pool, _read_replica_simulator

    _connection_pool = SQLiteConnectionPool(database_path, **kwargs)
    _read_replica_simulator = DatabaseReadReplicaSimulator(_connection_pool)

    logger.info("데이터베이스 연결 풀이 초기화되었습니다.")

if __name__ == '__main__':
    # 테스트 실행
    import asyncio
    import tempfile
    import os

    async def test_connection_pool():
        """연결 풀 테스트"""

        # 임시 데이터베이스로 테스트
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as f:
            test_db_path = f.name

        try:
            # 연결 풀 초기화
            init_connection_pool(test_db_path, max_connections=5, max_read_connections=3)
            pool = get_connection_pool()
            simulator = get_read_replica_simulator()

            # 테스트 테이블 생성
            pool.execute_write_query("""
                CREATE TABLE test_products (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    price REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 테스트 데이터 삽입
            for i in range(100):
                pool.execute_write_query(
                    "INSERT INTO test_products (name, price) VALUES (?, ?)",
                    (f"Product {i}", 10.0 + i)
                )

            print("✅ 테스트 데이터 생성 완료")

            # 동시 읽기 테스트
            async def read_test(thread_id: int):
                for i in range(10):
                    results = pool.execute_read_query(
                        "SELECT * FROM test_products WHERE price > ? LIMIT 5",
                        (50.0,)
                    )
                    print(f"Thread {thread_id}, Query {i}: {len(results)} results")
                    await asyncio.sleep(0.1)

            # 여러 읽기 작업 동시 실행
            tasks = [read_test(i) for i in range(5)]
            await asyncio.gather(*tasks)

            # 통계 출력
            stats = pool.get_pool_stats()
            print("\n📊 연결 풀 통계:")
            for key, value in stats.items():
                print(f"  {key}: {value}")

            # 연결 정리
            pool.close_all_connections()
            print("\n✅ 연결 풀 테스트 완료")

        finally:
            # 임시 파일 정리
            if os.path.exists(test_db_path):
                os.unlink(test_db_path)

    # 테스트 실행
    asyncio.run(test_connection_pool())