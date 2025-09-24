"""
Redis 캐시 매니저
분석 결과, 스크래핑 상태, 세션 데이터를 캐싱하여 성능 향상
"""

import json
import redis
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, List
import logging
import hashlib

logger = logging.getLogger(__name__)

class CacheManager:
    """Redis 기반 캐시 매니저"""
    
    def __init__(self, host='localhost', port=6379, db=0, decode_responses=True):
        """
        Redis 연결 초기화 (성능 최적화 버전)

        Args:
            host: Redis 서버 호스트
            port: Redis 서버 포트
            db: 데이터베이스 번호
            decode_responses: 응답 자동 디코딩 여부
        """
        try:
            # 성능 최적화: 연결 풀 사용
            self.connection_pool = redis.ConnectionPool(
                host=host,
                port=port,
                db=db,
                decode_responses=decode_responses,
                socket_connect_timeout=5,
                socket_timeout=5,
                max_connections=20,  # 최대 연결 수
                retry_on_timeout=True,
                health_check_interval=30
            )

            self.redis_client = redis.Redis(connection_pool=self.connection_pool)

            # 연결 테스트
            self.redis_client.ping()
            logger.info("✅ Redis connection pool established successfully")

            # 성능 최적화: 자주 사용되는 키 패턴 캐시
            self._key_cache = {}

        except redis.ConnectionError as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Redis initialization error: {e}")
            raise

    def _generate_key(self, prefix: str, identifier: str) -> str:
        """
        캐시 키 생성 (해시 기반)
        
        Args:
            prefix: 키 접두사 (예: 'analysis', 'scraping_status')  
            identifier: 고유 식별자 (예: 키워드, 세션 ID)
            
        Returns:
            생성된 캐시 키
        """
        # 키워드를 해시화하여 긴 키워드도 안전하게 처리
        key_hash = hashlib.md5(identifier.encode()).hexdigest()[:8]
        return f"market_insights:{prefix}:{key_hash}:{identifier}"

    def set_analysis_result(self, keyword: str, result_data: Dict[str, Any], ttl_hours: int = 1) -> bool:
        """
        분석 결과 캐시 저장
        
        Args:
            keyword: 분석 키워드
            result_data: 분석 결과 데이터 
            ttl_hours: 캐시 유효 시간 (시간)
            
        Returns:
            저장 성공 여부
        """
        try:
            key = self._generate_key("analysis", keyword)
            
            # 메타데이터 추가
            cache_data = {
                'keyword': keyword,
                'result': result_data,
                'cached_at': datetime.now().isoformat(),
                'cache_ttl_hours': ttl_hours
            }
            
            # JSON 직렬화하여 저장
            success = self.redis_client.setex(
                key, 
                timedelta(hours=ttl_hours), 
                json.dumps(cache_data, ensure_ascii=False)
            )
            
            if success:
                logger.info(f"📦 Analysis result cached for keyword: '{keyword}' (TTL: {ttl_hours}h)")
                return True
            else:
                logger.warning(f"⚠️ Failed to cache analysis result for: '{keyword}'")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error caching analysis result for '{keyword}': {e}")
            return False

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        범용 캐시 조회 메서드 (비동기)

        Args:
            key: 캐시 키

        Returns:
            캐시된 데이터 (없으면 None)
        """
        try:
            cached_data = self.redis_client.get(key)

            if cached_data:
                result = json.loads(cached_data)
                logger.info(f"🎯 Cache HIT for key: '{key}'")
                return result
            else:
                logger.info(f"🔍 Cache MISS for key: '{key}'")
                return None

        except Exception as e:
            logger.error(f"❌ Error retrieving cached data for key '{key}': {e}")
            return None

    async def set(self, key: str, data: Any, ttl: int = 3600) -> bool:
        """
        범용 캐시 저장 메서드 (비동기)

        Args:
            key: 캐시 키
            data: 저장할 데이터
            ttl: TTL (초 단위)

        Returns:
            저장 성공 여부
        """
        try:
            json_data = json.dumps(data, ensure_ascii=False, default=str)
            self.redis_client.setex(key, ttl, json_data)
            logger.info(f"💾 Cache SET for key: '{key}' (TTL: {ttl}s)")
            return True

        except Exception as e:
            logger.error(f"❌ Error storing cached data for key '{key}': {e}")
            return False

    def get_analysis_result(self, keyword: str) -> Optional[Dict[str, Any]]:
        """
        분석 결과 캐시 조회

        Args:
            keyword: 분석 키워드

        Returns:
            캐시된 분석 결과 (없으면 None)
        """
        try:
            key = self._generate_key("analysis", keyword)
            cached_data = self.redis_client.get(key)

            if cached_data:
                result = json.loads(cached_data)
                logger.info(f"🎯 Cache HIT for analysis: '{keyword}'")
                return result['result']
            else:
                logger.info(f"🔍 Cache MISS for analysis: '{keyword}'")
                return None

        except Exception as e:
            logger.error(f"❌ Error retrieving cached analysis for '{keyword}': {e}")
            return None

    async def get_multiple(self, keys: List[str]) -> Dict[str, Any]:
        """
        여러 키를 한 번에 조회 (성능 최적화)

        Args:
            keys: 조회할 키 목록

        Returns:
            키-값 딕셔너리
        """
        try:
            if not keys:
                return {}

            # 파이프라인을 사용한 배치 조회
            pipe = self.redis_client.pipeline()
            for key in keys:
                pipe.get(key)

            results = pipe.execute()

            # 결과 매핑
            result_dict = {}
            for key, value in zip(keys, results):
                if value:
                    try:
                        result_dict[key] = json.loads(value)
                    except json.JSONDecodeError:
                        result_dict[key] = value

            logger.info(f"📦 배치 캐시 조회 완료: {len(result_dict)}/{len(keys)} 히트")
            return result_dict

        except Exception as e:
            logger.error(f"❌ 배치 캐시 조회 실패: {e}")
            return {}

    async def set_multiple(self, items: Dict[str, Any], ttl: int = 3600) -> bool:
        """
        여러 키-값을 한 번에 저장 (성능 최적화)

        Args:
            items: 저장할 키-값 딕셔너리
            ttl: TTL (초)

        Returns:
            성공 여부
        """
        try:
            if not items:
                return True

            # 파이프라인을 사용한 배치 저장
            pipe = self.redis_client.pipeline()
            for key, value in items.items():
                serialized_value = json.dumps(value, ensure_ascii=False)
                pipe.setex(key, ttl, serialized_value)

            results = pipe.execute()

            success_count = sum(1 for result in results if result)
            logger.info(f"📦 배치 캐시 저장 완료: {success_count}/{len(items)} 성공")

            return success_count == len(items)

        except Exception as e:
            logger.error(f"❌ 배치 캐시 저장 실패: {e}")
            return False

    def delete_analysis_result(self, keyword: str) -> bool:
        """
        분석 결과 캐시 삭제
        
        Args:
            keyword: 삭제할 분석 키워드
            
        Returns:
            삭제 성공 여부
        """
        try:
            key = self._generate_key("analysis", keyword)
            deleted_count = self.redis_client.delete(key)
            if deleted_count > 0:
                logger.info(f"🗑️ Analysis cache deleted for keyword: '{keyword}'")
                return True
            else:
                logger.info(f"ℹ️ No analysis cache to delete for keyword: '{keyword}'")
                return False
        except Exception as e:
            logger.error(f"❌ Error deleting analysis cache for '{keyword}': {e}")
            return False

    def set_scraping_status(self, session_id: str, status_data: Dict[str, Any], ttl_minutes: int = 30) -> bool:
        """
        스크래핑 진행 상태 캐시 저장
        
        Args:
            session_id: 스크래핑 세션 ID
            status_data: 진행 상태 데이터
            ttl_minutes: 캐시 유효 시간 (분)
            
        Returns:
            저장 성공 여부
        """
        try:
            key = self._generate_key("scraping_status", session_id)
            
            # 타임스탬프 추가
            status_data['updated_at'] = datetime.now().isoformat()
            
            success = self.redis_client.setex(
                key, 
                timedelta(minutes=ttl_minutes), 
                json.dumps(status_data, ensure_ascii=False)
            )
            
            if success:
                logger.debug(f"📊 Scraping status updated for session: {session_id}")
                return True
            else:
                logger.warning(f"⚠️ Failed to update scraping status for: {session_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error updating scraping status for '{session_id}': {e}")
            return False

    def get_scraping_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        스크래핑 진행 상태 조회
        
        Args:
            session_id: 스크래핑 세션 ID
            
        Returns:
            진행 상태 데이터 (없으면 None)
        """
        try:
            key = self._generate_key("scraping_status", session_id)
            status_data = self.redis_client.get(key)
            
            if status_data:
                return json.loads(status_data)
            return None
                
        except Exception as e:
            logger.error(f"❌ Error retrieving scraping status for '{session_id}': {e}")
            return None

    def delete_scraping_status(self, session_id: str) -> bool:
        """
        스크래핑 상태 캐시 삭제 (완료 후 정리)
        
        Args:
            session_id: 스크래핑 세션 ID
            
        Returns:
            삭제 성공 여부  
        """
        try:
            key = self._generate_key("scraping_status", session_id)
            deleted = self.redis_client.delete(key)
            if deleted:
                logger.debug(f"🗑️ Scraping status deleted for session: {session_id}")
            return bool(deleted)
                
        except Exception as e:
            logger.error(f"❌ Error deleting scraping status for '{session_id}': {e}")
            return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        캐시 통계 정보 조회
        
        Returns:
            캐시 통계 데이터
        """
        try:
            info = self.redis_client.info()
            stats = {
                'redis_version': info.get('redis_version', 'Unknown'),
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_human': info.get('used_memory_human', '0B'),
                'used_memory_peak_human': info.get('used_memory_peak_human', '0B'),
                'total_commands_processed': info.get('total_commands_processed', 0),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
            }
            
            # 히트율 계산
            hits = stats['keyspace_hits']
            misses = stats['keyspace_misses']
            total_requests = hits + misses
            
            if total_requests > 0:
                stats['cache_hit_rate'] = round((hits / total_requests) * 100, 2)
            else:
                stats['cache_hit_rate'] = 0.0
                
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error retrieving cache stats: {e}")
            return {}

    def flush_analysis_cache(self) -> int:
        """
        분석 결과 캐시만 전체 삭제
        
        Returns:
            삭제된 키 개수
        """
        try:
            pattern = "market_insights:analysis:*"
            keys = self.redis_client.keys(pattern)
            if keys:
                deleted = self.redis_client.delete(*keys)
                logger.info(f"🧹 Flushed {deleted} analysis cache entries")
                return deleted
            return 0
            
        except Exception as e:
            logger.error(f"❌ Error flushing analysis cache: {e}")
            return 0

    def health_check(self) -> Dict[str, Any]:
        """
        Redis 연결 상태 및 성능 체크
        
        Returns:
            헬스 체크 결과
        """
        health_status = {
            'status': 'unhealthy',
            'redis_connected': False,
            'response_time_ms': 0,
            'error': None
        }
        
        try:
            start_time = datetime.now()
            
            # ping 테스트
            pong = self.redis_client.ping()
            
            end_time = datetime.now()
            response_time = (end_time - start_time).total_seconds() * 1000
            
            if pong:
                health_status.update({
                    'status': 'healthy',
                    'redis_connected': True,
                    'response_time_ms': round(response_time, 2)
                })
                
        except Exception as e:
            health_status['error'] = str(e)
            logger.error(f"❌ Redis health check failed: {e}")
            
        return health_status

# 전역 캐시 인스턴스 (싱글톤 패턴)
_cache_instance = None

def get_cache_manager() -> CacheManager:
    """
    캐시 매니저 싱글톤 인스턴스 반환
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CacheManager()
    return _cache_instance