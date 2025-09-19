# -*- coding: utf-8 -*-
"""
Market Insights Pro - 스크래핑 복원력 시스템
Amazon 스크래핑 중 발생하는 다양한 에러를 처리하고 자동 복구를 수행

주요 기능:
- 지능형 에러 분류 및 처리
- 적응형 재시도 로직
- 봇 탐지 우회 전략
- 네트워크 복원력
- 성능 기반 동적 조정
"""

import asyncio
import random
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)

class ErrorType(Enum):
    """에러 유형 분류"""
    NETWORK_ERROR = "network_error"           # 네트워크 연결 문제
    TIMEOUT_ERROR = "timeout_error"           # 타임아웃
    BOT_DETECTION = "bot_detection"           # 봇 탐지
    PAGE_NOT_FOUND = "page_not_found"         # 페이지 없음
    CAPTCHA_REQUIRED = "captcha_required"     # CAPTCHA 요구
    RATE_LIMIT = "rate_limit"                 # 요청 속도 제한
    PARSING_ERROR = "parsing_error"           # 파싱 오류
    SERVER_ERROR = "server_error"             # 서버 오류 (5xx)
    PERMISSION_DENIED = "permission_denied"   # 접근 거부
    UNKNOWN_ERROR = "unknown_error"           # 알 수 없는 오류

class RetryStrategy(Enum):
    """재시도 전략"""
    IMMEDIATE = "immediate"                   # 즉시 재시도
    EXPONENTIAL_BACKOFF = "exponential_backoff"  # 지수적 백오프
    LINEAR_BACKOFF = "linear_backoff"         # 선형 백오프
    RANDOM_JITTER = "random_jitter"          # 랜덤 지터
    ADAPTIVE = "adaptive"                     # 적응형

@dataclass
class ErrorContext:
    """에러 컨텍스트 정보"""
    error_type: ErrorType
    original_exception: Exception
    retry_count: int
    timestamp: datetime
    page_url: str = ""
    user_agent: str = ""
    additional_info: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RetryConfig:
    """재시도 설정"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    jitter_range: Tuple[float, float] = (0.1, 0.3)
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF

@dataclass
class ResilienceMetrics:
    """복원력 메트릭"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    retried_requests: int = 0
    error_counts: Dict[ErrorType, int] = field(default_factory=dict)
    average_retry_success_rate: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)

class ScrapingResilience:
    """
    Amazon 스크래핑 복원력 시스템

    다양한 에러 상황에 대한 지능형 처리와
    적응형 재시도 전략을 제공합니다.
    """

    def __init__(self):
        self.retry_configs = self._load_retry_configs()
        self.error_handlers = self._setup_error_handlers()
        self.metrics = ResilienceMetrics()
        self.user_agents = self._load_user_agents()
        self.current_ua_index = 0

    def _load_retry_configs(self) -> Dict[ErrorType, RetryConfig]:
        """에러 유형별 재시도 설정 로드"""
        return {
            ErrorType.NETWORK_ERROR: RetryConfig(
                max_retries=5,
                base_delay=2.0,
                strategy=RetryStrategy.EXPONENTIAL_BACKOFF
            ),
            ErrorType.TIMEOUT_ERROR: RetryConfig(
                max_retries=3,
                base_delay=5.0,
                strategy=RetryStrategy.LINEAR_BACKOFF
            ),
            ErrorType.BOT_DETECTION: RetryConfig(
                max_retries=2,
                base_delay=30.0,
                max_delay=300.0,
                strategy=RetryStrategy.ADAPTIVE
            ),
            ErrorType.RATE_LIMIT: RetryConfig(
                max_retries=4,
                base_delay=60.0,
                strategy=RetryStrategy.LINEAR_BACKOFF
            ),
            ErrorType.CAPTCHA_REQUIRED: RetryConfig(
                max_retries=1,
                base_delay=120.0,
                strategy=RetryStrategy.IMMEDIATE
            ),
            ErrorType.PAGE_NOT_FOUND: RetryConfig(
                max_retries=1,
                base_delay=1.0,
                strategy=RetryStrategy.IMMEDIATE
            ),
            ErrorType.PARSING_ERROR: RetryConfig(
                max_retries=2,
                base_delay=1.0,
                strategy=RetryStrategy.IMMEDIATE
            ),
            ErrorType.SERVER_ERROR: RetryConfig(
                max_retries=3,
                base_delay=10.0,
                strategy=RetryStrategy.EXPONENTIAL_BACKOFF
            ),
            ErrorType.PERMISSION_DENIED: RetryConfig(
                max_retries=1,
                base_delay=60.0,
                strategy=RetryStrategy.IMMEDIATE
            ),
            ErrorType.UNKNOWN_ERROR: RetryConfig(
                max_retries=2,
                base_delay=5.0,
                strategy=RetryStrategy.RANDOM_JITTER
            )
        }

    def _load_user_agents(self) -> List[str]:
        """User-Agent 목록 로드"""
        return [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
        ]

    def _setup_error_handlers(self) -> Dict[ErrorType, Callable]:
        """에러 핸들러 설정"""
        return {
            ErrorType.BOT_DETECTION: self._handle_bot_detection,
            ErrorType.CAPTCHA_REQUIRED: self._handle_captcha,
            ErrorType.RATE_LIMIT: self._handle_rate_limit,
            ErrorType.NETWORK_ERROR: self._handle_network_error,
            ErrorType.TIMEOUT_ERROR: self._handle_timeout,
            ErrorType.SERVER_ERROR: self._handle_server_error,
            ErrorType.PARSING_ERROR: self._handle_parsing_error
        }

    async def execute_with_resilience(
        self,
        operation: Callable,
        *args,
        context_info: Dict[str, Any] = None,
        **kwargs
    ) -> Any:
        """
        복원력이 있는 작업 실행

        Args:
            operation: 실행할 비동기 함수
            *args: 함수 인자
            context_info: 컨텍스트 정보
            **kwargs: 함수 키워드 인자

        Returns:
            작업 실행 결과
        """
        self.metrics.total_requests += 1
        context_info = context_info or {}

        retry_count = 0
        last_error = None

        while True:
            try:
                # 작업 실행
                start_time = time.time()
                result = await operation(*args, **kwargs)

                # 성공 메트릭 업데이트
                self.metrics.successful_requests += 1
                execution_time = time.time() - start_time

                if retry_count > 0:
                    logger.info(f"✅ 재시도 후 성공 (시도 횟수: {retry_count + 1}, 실행시간: {execution_time:.2f}초)")

                return result

            except Exception as e:
                # 에러 분류
                error_type = self._classify_error(e, context_info)
                error_context = ErrorContext(
                    error_type=error_type,
                    original_exception=e,
                    retry_count=retry_count,
                    timestamp=datetime.now(),
                    page_url=context_info.get("page_url", ""),
                    user_agent=context_info.get("user_agent", ""),
                    additional_info=context_info
                )

                # 에러 메트릭 업데이트
                if error_type not in self.metrics.error_counts:
                    self.metrics.error_counts[error_type] = 0
                self.metrics.error_counts[error_type] += 1

                logger.warning(f"⚠️ 에러 발생 ({error_type.value}): {str(e)}")

                # 재시도 가능 여부 확인
                config = self.retry_configs.get(error_type)
                if not config or retry_count >= config.max_retries:
                    logger.error(f"❌ 최대 재시도 횟수 초과 또는 재시도 불가능한 에러: {error_type.value}")
                    self.metrics.failed_requests += 1
                    raise e

                # 재시도 전 처리
                await self._handle_error_before_retry(error_context)

                # 재시도 대기
                delay = self._calculate_retry_delay(error_context, config)
                logger.info(f"🔄 {delay:.1f}초 후 재시도 (시도 {retry_count + 1}/{config.max_retries})")
                await asyncio.sleep(delay)

                retry_count += 1
                self.metrics.retried_requests += 1
                last_error = e

    def _classify_error(self, error: Exception, context: Dict[str, Any]) -> ErrorType:
        """에러 분류"""
        error_str = str(error).lower()
        error_type_name = type(error).__name__.lower()

        # Playwright/Selenium 특정 에러
        if "timeouterror" in error_type_name or "timeout" in error_str:
            return ErrorType.TIMEOUT_ERROR

        # 네트워크 관련 에러
        if any(keyword in error_str for keyword in [
            "connection", "network", "unreachable", "dns", "socket"
        ]):
            return ErrorType.NETWORK_ERROR

        # 봇 탐지 관련
        if any(keyword in error_str for keyword in [
            "robot", "bot", "automated", "unusual traffic", "blocked"
        ]):
            return ErrorType.BOT_DETECTION

        # CAPTCHA
        if any(keyword in error_str for keyword in [
            "captcha", "prove you're human", "verification"
        ]):
            return ErrorType.CAPTCHA_REQUIRED

        # 서버 에러
        if any(keyword in error_str for keyword in [
            "500", "502", "503", "504", "internal server error",
            "bad gateway", "service unavailable"
        ]):
            return ErrorType.SERVER_ERROR

        # 페이지 없음
        if any(keyword in error_str for keyword in [
            "404", "not found", "page not found"
        ]):
            return ErrorType.PAGE_NOT_FOUND

        # 권한 거부
        if any(keyword in error_str for keyword in [
            "403", "forbidden", "access denied", "permission denied"
        ]):
            return ErrorType.PERMISSION_DENIED

        # 속도 제한
        if any(keyword in error_str for keyword in [
            "429", "too many requests", "rate limit"
        ]):
            return ErrorType.RATE_LIMIT

        # 파싱 에러
        if any(keyword in error_str for keyword in [
            "parsing", "selector", "element not found", "beautifulsoup"
        ]):
            return ErrorType.PARSING_ERROR

        return ErrorType.UNKNOWN_ERROR

    async def _handle_error_before_retry(self, error_context: ErrorContext) -> None:
        """재시도 전 에러 처리"""
        handler = self.error_handlers.get(error_context.error_type)
        if handler:
            try:
                await handler(error_context)
            except Exception as e:
                logger.warning(f"에러 핸들러 실행 중 오류: {e}")

    async def _handle_bot_detection(self, error_context: ErrorContext) -> None:
        """봇 탐지 처리"""
        logger.info("🤖 봇 탐지 대응 조치 시행...")

        # User-Agent 변경
        self._rotate_user_agent()

        # 더 긴 대기 시간
        extra_delay = random.uniform(60, 180)
        logger.info(f"   추가 대기: {extra_delay:.1f}초")
        await asyncio.sleep(extra_delay)

        # 세션 재초기화 신호 (구현체에서 처리)
        error_context.additional_info["require_session_reset"] = True

    async def _handle_captcha(self, error_context: ErrorContext) -> None:
        """CAPTCHA 처리"""
        logger.warning("🔒 CAPTCHA 감지됨")

        # 긴 대기 시간 (수동 해결 대기)
        await asyncio.sleep(300)  # 5분 대기

        # IP 변경 권장 신호
        error_context.additional_info["require_ip_change"] = True

    async def _handle_rate_limit(self, error_context: ErrorContext) -> None:
        """속도 제한 처리"""
        logger.info("⏰ 속도 제한 감지, 대기 중...")

        # 요청 간격 늘리기
        base_delay = 60 + random.uniform(30, 90)
        await asyncio.sleep(base_delay)

        # 동적 딜레이 조정 신호
        error_context.additional_info["increase_delay"] = True

    async def _handle_network_error(self, error_context: ErrorContext) -> None:
        """네트워크 에러 처리"""
        logger.info("🌐 네트워크 연결 확인 중...")

        # 기본 대기
        await asyncio.sleep(5)

        # 연결 테스트 (실제 구현에서는 ping 등 사용)
        # 여기서는 간단히 시뮬레이션
        error_context.additional_info["network_check"] = True

    async def _handle_timeout(self, error_context: ErrorContext) -> None:
        """타임아웃 처리"""
        logger.info("⏱️ 타임아웃 대응...")

        # 점진적으로 타임아웃 시간 증가 요청
        current_timeout = error_context.additional_info.get("timeout", 30)
        new_timeout = min(current_timeout * 1.5, 120)  # 최대 2분
        error_context.additional_info["suggested_timeout"] = new_timeout

    async def _handle_server_error(self, error_context: ErrorContext) -> None:
        """서버 에러 처리"""
        logger.info("🛠️ 서버 에러 대응...")

        # 서버 복구 대기
        await asyncio.sleep(10)

    async def _handle_parsing_error(self, error_context: ErrorContext) -> None:
        """파싱 에러 처리"""
        logger.info("📄 파싱 에러 대응...")

        # 페이지 구조 변경 가능성 체크
        error_context.additional_info["check_page_structure"] = True

    def _calculate_retry_delay(self, error_context: ErrorContext, config: RetryConfig) -> float:
        """재시도 대기 시간 계산"""
        retry_count = error_context.retry_count

        if config.strategy == RetryStrategy.IMMEDIATE:
            return 0.1

        elif config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = config.base_delay * (config.backoff_factor ** retry_count)
            delay = min(delay, config.max_delay)

        elif config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = config.base_delay * (retry_count + 1)
            delay = min(delay, config.max_delay)

        elif config.strategy == RetryStrategy.RANDOM_JITTER:
            jitter_min, jitter_max = config.jitter_range
            jitter = random.uniform(jitter_min, jitter_max)
            delay = config.base_delay * (1 + jitter)

        elif config.strategy == RetryStrategy.ADAPTIVE:
            # 최근 성공률 기반 적응형 대기
            base_delay = config.base_delay
            if self.metrics.total_requests > 10:
                success_rate = self.metrics.successful_requests / self.metrics.total_requests
                if success_rate < 0.5:
                    base_delay *= 2  # 성공률이 낮으면 더 오래 대기
            delay = base_delay * (retry_count + 1)
            delay = min(delay, config.max_delay)

        else:
            delay = config.base_delay

        # 랜덤 지터 추가 (서버 부하 분산)
        jitter = random.uniform(0.8, 1.2)
        return delay * jitter

    def _rotate_user_agent(self) -> str:
        """User-Agent 로테이션"""
        self.current_ua_index = (self.current_ua_index + 1) % len(self.user_agents)
        new_ua = self.user_agents[self.current_ua_index]
        logger.info(f"🔄 User-Agent 변경: {new_ua[:80]}...")
        return new_ua

    def get_current_user_agent(self) -> str:
        """현재 User-Agent 반환"""
        return self.user_agents[self.current_ua_index]

    def should_abort_operation(self) -> bool:
        """작업 중단 여부 판단"""
        # 에러율이 너무 높으면 중단
        if self.metrics.total_requests > 20:
            error_rate = self.metrics.failed_requests / self.metrics.total_requests
            if error_rate > 0.8:  # 80% 이상 실패
                logger.warning("🚨 에러율이 너무 높아 작업을 중단합니다")
                return True

        # 특정 에러 타입이 너무 많으면 중단
        bot_detection_count = self.metrics.error_counts.get(ErrorType.BOT_DETECTION, 0)
        if bot_detection_count > 5:
            logger.warning("🚨 봇 탐지가 너무 많이 발생하여 작업을 중단합니다")
            return True

        return False

    def get_metrics_summary(self) -> Dict[str, Any]:
        """메트릭 요약 반환"""
        total = max(1, self.metrics.total_requests)
        success_rate = self.metrics.successful_requests / total * 100
        retry_rate = self.metrics.retried_requests / total * 100

        return {
            "total_requests": self.metrics.total_requests,
            "success_rate": round(success_rate, 1),
            "retry_rate": round(retry_rate, 1),
            "error_distribution": {
                error_type.value: count
                for error_type, count in self.metrics.error_counts.items()
            },
            "last_updated": self.metrics.last_updated.isoformat()
        }

    def reset_metrics(self) -> None:
        """메트릭 리셋"""
        self.metrics = ResilienceMetrics()
        logger.info("📊 복원력 메트릭 리셋 완료")

# 데코레이터 버전
def resilient_operation(
    error_types: List[ErrorType] = None,
    max_retries: int = 3,
    base_delay: float = 1.0
):
    """
    복원력 있는 작업을 위한 데코레이터

    Args:
        error_types: 처리할 에러 타입 목록
        max_retries: 최대 재시도 횟수
        base_delay: 기본 대기 시간
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            resilience = ScrapingResilience()

            # 커스텀 설정 적용
            if error_types:
                for error_type in error_types:
                    if error_type in resilience.retry_configs:
                        resilience.retry_configs[error_type].max_retries = max_retries
                        resilience.retry_configs[error_type].base_delay = base_delay

            return await resilience.execute_with_resilience(func, *args, **kwargs)

        return wrapper
    return decorator

# 사용 예시
@resilient_operation(
    error_types=[ErrorType.NETWORK_ERROR, ErrorType.TIMEOUT_ERROR],
    max_retries=5,
    base_delay=2.0
)
async def resilient_scraping_function():
    """복원력이 있는 스크래핑 함수 예시"""
    # 실제 스크래핑 로직
    pass

# 테스트 함수
async def test_resilience():
    """복원력 시스템 테스트"""
    resilience = ScrapingResilience()

    async def failing_operation():
        """실패하는 작업 시뮬레이션"""
        if random.random() < 0.7:  # 70% 확률로 실패
            raise Exception("Simulated network error")
        return "Success!"

    try:
        result = await resilience.execute_with_resilience(
            failing_operation,
            context_info={"page_url": "https://example.com"}
        )
        print(f"결과: {result}")

        # 메트릭 출력
        metrics = resilience.get_metrics_summary()
        print(f"메트릭: {json.dumps(metrics, indent=2)}")

    except Exception as e:
        print(f"최종 실패: {e}")

if __name__ == "__main__":
    asyncio.run(test_resilience())