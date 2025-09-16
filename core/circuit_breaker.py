"""
Circuit Breaker 패턴 구현
외부 서비스 호출 시 장애 대응을 위한 Circuit Breaker 패턴
"""

import asyncio
import time
import logging
from typing import Callable, Any, Optional, Dict
from enum import Enum
from dataclasses import dataclass
from contextlib import asynccontextmanager
import functools

logger = logging.getLogger(__name__)

class CircuitBreakerState(Enum):
    """Circuit Breaker 상태"""
    CLOSED = "closed"          # 정상 상태
    OPEN = "open"              # 차단 상태 (모든 요청 차단)
    HALF_OPEN = "half_open"    # 반열림 상태 (테스트 요청만 허용)

@dataclass
class CircuitBreakerConfig:
    """Circuit Breaker 설정"""
    failure_threshold: int = 5          # 실패 임계값
    success_threshold: int = 3          # 성공 임계값 (Half-Open 상태에서)
    timeout_seconds: int = 60           # Open 상태 유지 시간
    recovery_timeout: int = 30          # Half-Open 상태에서의 복구 타임아웃
    max_calls: int = 100               # 통계를 위한 최대 호출 수

class CircuitBreakerException(Exception):
    """Circuit Breaker 예외"""
    pass

class CircuitBreaker:
    """Circuit Breaker 구현"""
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        # 상태 관리
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.last_state_change = time.time()
        
        # 통계
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.rejected_calls = 0
        
        # 최근 호출 결과 (성공률 계산용)
        self.recent_calls = []
        
        logger.info(f"🔧 Circuit Breaker '{self.name}' 초기화 완료")
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Circuit Breaker를 통한 함수 호출"""
        self.total_calls += 1
        
        # 상태에 따른 호출 허용 여부 확인
        if not self._should_allow_call():
            self.rejected_calls += 1
            raise CircuitBreakerException(
                f"Circuit Breaker '{self.name}' is {self.state.value}. Call rejected."
            )
        
        try:
            # 함수 실행
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # 성공 처리
            self._on_success()
            return result
            
        except Exception as e:
            # 실패 처리
            self._on_failure(e)
            raise
    
    def _should_allow_call(self) -> bool:
        """호출 허용 여부 확인"""
        current_time = time.time()
        
        if self.state == CircuitBreakerState.CLOSED:
            return True
        
        elif self.state == CircuitBreakerState.OPEN:
            # Open 상태에서 타임아웃 확인
            if current_time - self.last_state_change >= self.config.timeout_seconds:
                logger.info(f"🔄 Circuit Breaker '{self.name}' transitioning to HALF_OPEN")
                self._transition_to_half_open()
                return True
            return False
        
        elif self.state == CircuitBreakerState.HALF_OPEN:
            # Half-Open 상태에서 제한된 호출만 허용
            return True
        
        return False
    
    def _on_success(self):
        """성공 시 처리"""
        self.successful_calls += 1
        self.recent_calls.append(True)
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            
            # Half-Open에서 충분한 성공이 누적되면 CLOSED로 전환
            if self.success_count >= self.config.success_threshold:
                logger.info(f"✅ Circuit Breaker '{self.name}' transitioning to CLOSED")
                self._transition_to_closed()
        
        elif self.state == CircuitBreakerState.CLOSED:
            # CLOSED 상태에서 실패 카운트 리셋
            self.failure_count = 0
        
        self._maintain_recent_calls()
    
    def _on_failure(self, exception: Exception):
        """실패 시 처리"""
        self.failed_calls += 1
        self.failure_count += 1
        self.recent_calls.append(False)
        self.last_failure_time = time.time()
        
        logger.warning(f"❌ Circuit Breaker '{self.name}' recorded failure: {str(exception)[:100]}")
        
        if self.state == CircuitBreakerState.CLOSED:
            # CLOSED에서 실패 임계값 확인
            if self.failure_count >= self.config.failure_threshold:
                logger.warning(f"🚨 Circuit Breaker '{self.name}' transitioning to OPEN")
                self._transition_to_open()
        
        elif self.state == CircuitBreakerState.HALF_OPEN:
            # Half-Open에서 실패 시 즉시 OPEN으로
            logger.warning(f"🚨 Circuit Breaker '{self.name}' transitioning back to OPEN")
            self._transition_to_open()
        
        self._maintain_recent_calls()
    
    def _transition_to_open(self):
        """OPEN 상태로 전환"""
        self.state = CircuitBreakerState.OPEN
        self.last_state_change = time.time()
        self.success_count = 0
    
    def _transition_to_half_open(self):
        """HALF_OPEN 상태로 전환"""
        self.state = CircuitBreakerState.HALF_OPEN
        self.last_state_change = time.time()
        self.success_count = 0
        self.failure_count = 0
    
    def _transition_to_closed(self):
        """CLOSED 상태로 전환"""
        self.state = CircuitBreakerState.CLOSED
        self.last_state_change = time.time()
        self.success_count = 0
        self.failure_count = 0
    
    def _maintain_recent_calls(self):
        """최근 호출 결과 유지 (성능을 위해 제한)"""
        if len(self.recent_calls) > self.config.max_calls:
            self.recent_calls = self.recent_calls[-self.config.max_calls:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Circuit Breaker 통계 조회"""
        success_rate = (self.successful_calls / max(1, self.total_calls)) * 100
        failure_rate = (self.failed_calls / max(1, self.total_calls)) * 100
        
        recent_success_rate = 0
        if self.recent_calls:
            recent_successes = sum(1 for call in self.recent_calls if call)
            recent_success_rate = (recent_successes / len(self.recent_calls)) * 100
        
        return {
            'name': self.name,
            'state': self.state.value,
            'total_calls': self.total_calls,
            'successful_calls': self.successful_calls,
            'failed_calls': self.failed_calls,
            'rejected_calls': self.rejected_calls,
            'success_rate': round(success_rate, 2),
            'failure_rate': round(failure_rate, 2),
            'recent_success_rate': round(recent_success_rate, 2),
            'current_failure_count': self.failure_count,
            'current_success_count': self.success_count,
            'last_state_change': self.last_state_change,
            'uptime_seconds': time.time() - self.last_state_change
        }
    
    def reset(self):
        """Circuit Breaker 리셋"""
        logger.info(f"🔄 Circuit Breaker '{self.name}' 수동 리셋")
        self._transition_to_closed()
    
    async def health_check(self) -> Dict[str, Any]:
        """헬스체크"""
        stats = self.get_stats()
        is_healthy = self.state == CircuitBreakerState.CLOSED
        
        return {
            'name': self.name,
            'healthy': is_healthy,
            'state': self.state.value,
            'success_rate': stats['success_rate'],
            'last_check': time.time()
        }

def circuit_breaker(name: str, config: CircuitBreakerConfig = None):
    """Circuit Breaker 데코레이터"""
    def decorator(func: Callable) -> Callable:
        breaker = CircuitBreaker(name, config)
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return asyncio.create_task(breaker.call(func, *args, **kwargs))
        
        # 함수 타입에 따라 적절한 래퍼 반환
        if asyncio.iscoroutinefunction(func):
            wrapper = async_wrapper
        else:
            wrapper = sync_wrapper
        
        # Circuit Breaker 인스턴스를 함수에 첨부
        wrapper.circuit_breaker = breaker
        return wrapper
    
    return decorator

class CircuitBreakerManager:
    """Circuit Breaker 매니저"""
    
    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        logger.info("🏭 Circuit Breaker Manager 초기화 완료")
    
    def get_or_create(self, name: str, config: CircuitBreakerConfig = None) -> CircuitBreaker:
        """Circuit Breaker 조회 또는 생성"""
        if name not in self.circuit_breakers:
            self.circuit_breakers[name] = CircuitBreaker(name, config)
        return self.circuit_breakers[name]
    
    def get_all_stats(self) -> Dict[str, Any]:
        """모든 Circuit Breaker 통계 조회"""
        stats = {}
        for name, breaker in self.circuit_breakers.items():
            stats[name] = breaker.get_stats()
        
        return {
            'circuit_breakers': stats,
            'total_breakers': len(self.circuit_breakers),
            'healthy_breakers': len([
                cb for cb in self.circuit_breakers.values() 
                if cb.state == CircuitBreakerState.CLOSED
            ]),
            'timestamp': time.time()
        }
    
    async def health_check_all(self) -> Dict[str, Any]:
        """모든 Circuit Breaker 헬스체크"""
        health_results = {}
        
        for name, breaker in self.circuit_breakers.items():
            health_results[name] = await breaker.health_check()
        
        overall_healthy = all(
            result['healthy'] for result in health_results.values()
        )
        
        return {
            'overall_healthy': overall_healthy,
            'individual_health': health_results,
            'timestamp': time.time()
        }
    
    def reset_all(self):
        """모든 Circuit Breaker 리셋"""
        for breaker in self.circuit_breakers.values():
            breaker.reset()
        logger.info("🔄 모든 Circuit Breaker 리셋 완료")
    
    def reset_breaker(self, name: str) -> bool:
        """특정 Circuit Breaker 리셋"""
        if name in self.circuit_breakers:
            self.circuit_breakers[name].reset()
            return True
        return False

# 전역 매니저 인스턴스
_circuit_breaker_manager = CircuitBreakerManager()

def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """Circuit Breaker Manager 싱글톤 반환"""
    return _circuit_breaker_manager

def get_circuit_breaker(name: str, config: CircuitBreakerConfig = None) -> CircuitBreaker:
    """Circuit Breaker 인스턴스 조회"""
    return _circuit_breaker_manager.get_or_create(name, config)

# 미리 정의된 Circuit Breaker 설정들
class PresetConfigs:
    """미리 정의된 Circuit Breaker 설정"""
    
    # Amazon 스크래핑용 (엄격)
    SCRAPING = CircuitBreakerConfig(
        failure_threshold=3,
        success_threshold=2,
        timeout_seconds=300,  # 5분
        recovery_timeout=60,
        max_calls=50
    )
    
    # 외부 API 호출용 (보통)
    EXTERNAL_API = CircuitBreakerConfig(
        failure_threshold=5,
        success_threshold=3,
        timeout_seconds=120,  # 2분
        recovery_timeout=30,
        max_calls=100
    )
    
    # 데이터베이스용 (관대)
    DATABASE = CircuitBreakerConfig(
        failure_threshold=10,
        success_threshold=5,
        timeout_seconds=60,   # 1분
        recovery_timeout=15,
        max_calls=200
    )
    
    # 캐시용 (매우 관대)
    CACHE = CircuitBreakerConfig(
        failure_threshold=15,
        success_threshold=7,
        timeout_seconds=30,   # 30초
        recovery_timeout=10,
        max_calls=300
    )

if __name__ == '__main__':
    # 단독 실행시 테스트
    async def test_circuit_breaker():
        # 실패하는 함수
        @circuit_breaker("test_service", PresetConfigs.EXTERNAL_API)
        async def failing_service():
            import random
            if random.random() < 0.7:  # 70% 실패율
                raise Exception("Service failure")
            return "Success"
        
        # 테스트 실행
        for i in range(20):
            try:
                result = await failing_service()
                print(f"Call {i+1}: {result}")
            except Exception as e:
                print(f"Call {i+1}: Failed - {e}")
            
            await asyncio.sleep(0.1)
        
        # 통계 출력
        stats = failing_service.circuit_breaker.get_stats()
        print(f"Final stats: {stats}")
    
    asyncio.run(test_circuit_breaker())