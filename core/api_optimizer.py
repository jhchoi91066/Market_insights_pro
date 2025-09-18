"""
API 응답 최적화 도구
페이지네이션, 응답 압축, 조건부 요청, 캐싱 등을 담당
"""

import gzip
import json
import time
import hashlib
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

class PaginationParams(BaseModel):
    """페이지네이션 파라미터"""
    page: int = 1
    size: int = 20
    max_size: int = 100

    def __post_init__(self):
        # 페이지는 1부터 시작
        if self.page < 1:
            self.page = 1

        # 사이즈 제한
        if self.size > self.max_size:
            self.size = self.max_size
        elif self.size < 1:
            self.size = 20

class PaginatedResponse(BaseModel):
    """페이지네이션 응답 모델"""
    data: List[Any]
    pagination: Dict[str, Any]
    metadata: Dict[str, Any] = {}

class ResponseCompressor:
    """
    응답 압축 처리기
    gzip 압축을 통한 네트워크 트래픽 최적화
    """

    def __init__(self, min_size: int = 1024):
        """
        Args:
            min_size: 압축을 적용할 최소 바이트 크기 (기본: 1KB)
        """
        self.min_size = min_size

    def should_compress(self, content: bytes, accept_encoding: str) -> bool:
        """압축 여부 결정"""
        # Accept-Encoding 헤더에 gzip이 포함되어 있고
        # 콘텐츠 크기가 최소 크기 이상인 경우에만 압축
        return (
            'gzip' in accept_encoding.lower() and
            len(content) >= self.min_size
        )

    def compress_response(self, content: bytes) -> bytes:
        """gzip 압축 수행"""
        return gzip.compress(content)

    def create_compressed_response(
        self,
        data: Any,
        request: Request,
        status_code: int = 200,
        headers: Dict[str, str] = None
    ) -> Response:
        """압축된 JSON 응답 생성"""

        # JSON 직렬화
        if isinstance(data, dict) or isinstance(data, list):
            content = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        else:
            content = str(data).encode('utf-8')

        # 헤더 준비
        response_headers = headers or {}
        response_headers['Content-Type'] = 'application/json; charset=utf-8'

        # 압축 여부 결정
        accept_encoding = request.headers.get('accept-encoding', '')
        if self.should_compress(content, accept_encoding):
            # 압축 수행
            compressed_content = self.compress_response(content)
            response_headers['Content-Encoding'] = 'gzip'
            response_headers['Content-Length'] = str(len(compressed_content))

            logger.debug(f"응답 압축: {len(content)} → {len(compressed_content)} bytes ({len(compressed_content)/len(content)*100:.1f}%)")

            return Response(
                content=compressed_content,
                status_code=status_code,
                headers=response_headers
            )
        else:
            # 압축하지 않음
            response_headers['Content-Length'] = str(len(content))
            return Response(
                content=content,
                status_code=status_code,
                headers=response_headers
            )

class ConditionalRequestHandler:
    """
    조건부 요청 처리기 (ETag, Last-Modified)
    캐싱 효율성을 위한 HTTP 조건부 요청 지원
    """

    def generate_etag(self, data: Any) -> str:
        """데이터로부터 ETag 생성"""
        # 데이터를 JSON으로 직렬화한 후 해시 생성
        content = json.dumps(data, sort_keys=True, ensure_ascii=False)
        etag = hashlib.md5(content.encode('utf-8')).hexdigest()
        return f'"{etag}"'

    def check_not_modified(self, request: Request, etag: str, last_modified: datetime = None) -> bool:
        """클라이언트 캐시가 유효한지 확인"""

        # If-None-Match 헤더 확인 (ETag)
        if_none_match = request.headers.get('if-none-match')
        if if_none_match and etag in if_none_match:
            return True

        # If-Modified-Since 헤더 확인
        if last_modified:
            if_modified_since = request.headers.get('if-modified-since')
            if if_modified_since:
                try:
                    # RFC 2822 형식으로 파싱
                    from email.utils import parsedate_to_datetime
                    client_time = parsedate_to_datetime(if_modified_since)

                    # 초 단위로 비교 (HTTP 날짜는 초 단위)
                    if last_modified.replace(microsecond=0) <= client_time:
                        return True
                except ValueError:
                    # 파싱 실패시 무시
                    pass

        return False

    def create_conditional_response(
        self,
        data: Any,
        request: Request,
        last_modified: datetime = None,
        max_age: int = 3600  # 1시간 기본 캐시
    ) -> Response:
        """조건부 요청을 지원하는 응답 생성"""

        # ETag 생성
        etag = self.generate_etag(data)

        # 클라이언트 캐시 확인
        if self.check_not_modified(request, etag, last_modified):
            # 304 Not Modified 응답
            headers = {
                'ETag': etag,
                'Cache-Control': f'max-age={max_age}, must-revalidate'
            }
            if last_modified:
                headers['Last-Modified'] = last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT')

            return Response(status_code=304, headers=headers)

        # 정상 응답 생성
        content = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'ETag': etag,
            'Cache-Control': f'max-age={max_age}, must-revalidate'
        }

        if last_modified:
            headers['Last-Modified'] = last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT')

        return Response(content=content, headers=headers)

class PaginationHelper:
    """
    페이지네이션 도우미 클래스
    데이터 분할과 메타데이터 생성을 담당
    """

    @staticmethod
    def paginate_data(
        data: List[Any],
        page: int,
        size: int,
        total_count: int = None
    ) -> PaginatedResponse:
        """데이터 페이지네이션"""

        if total_count is None:
            total_count = len(data)

        # 오프셋 계산
        offset = (page - 1) * size

        # 데이터 슬라이싱
        paginated_data = data[offset:offset + size]

        # 메타데이터 계산
        total_pages = (total_count + size - 1) // size  # 올림 계산
        has_next = page < total_pages
        has_prev = page > 1

        pagination_info = {
            'current_page': page,
            'page_size': size,
            'total_items': total_count,
            'total_pages': total_pages,
            'has_next': has_next,
            'has_previous': has_prev,
            'next_page': page + 1 if has_next else None,
            'previous_page': page - 1 if has_prev else None,
            'start_index': offset + 1 if paginated_data else 0,
            'end_index': offset + len(paginated_data)
        }

        return PaginatedResponse(
            data=paginated_data,
            pagination=pagination_info,
            metadata={
                'generated_at': datetime.now().isoformat(),
                'items_on_page': len(paginated_data)
            }
        )

    @staticmethod
    def create_pagination_links(
        base_url: str,
        current_page: int,
        total_pages: int,
        page_size: int,
        query_params: Dict[str, Any] = None
    ) -> Dict[str, str]:
        """페이지네이션 링크 생성"""

        links = {}
        query_params = query_params or {}

        def build_url(page: int) -> str:
            params = {**query_params, 'page': page, 'size': page_size}
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            return f"{base_url}?{query_string}"

        # 첫 페이지
        if current_page > 1:
            links['first'] = build_url(1)
            links['prev'] = build_url(current_page - 1)

        # 마지막 페이지
        if current_page < total_pages:
            links['next'] = build_url(current_page + 1)
            links['last'] = build_url(total_pages)

        # 현재 페이지
        links['self'] = build_url(current_page)

        return links

class ApiResponseOptimizer:
    """
    API 응답 최적화 통합 클래스
    """

    def __init__(self):
        self.compressor = ResponseCompressor(min_size=1024)  # 1KB 이상 압축
        self.conditional_handler = ConditionalRequestHandler()
        self.response_cache = {}  # 간단한 메모리 캐시
        self.cache_ttl = 300  # 5분 TTL

    def optimize_list_response(
        self,
        data: List[Any],
        request: Request,
        pagination_params: PaginationParams,
        total_count: int = None,
        last_modified: datetime = None,
        enable_compression: bool = True,
        enable_conditional: bool = True,
        cache_key: str = None
    ) -> Response:
        """리스트 API 응답 최적화"""

        # 캐시 확인
        if cache_key:
            cached_response = self._get_cached_response(cache_key)
            if cached_response:
                logger.debug(f"캐시 히트: {cache_key}")
                return cached_response

        # 페이지네이션 적용
        paginated = PaginationHelper.paginate_data(
            data=data,
            page=pagination_params.page,
            size=pagination_params.size,
            total_count=total_count
        )

        # 응답 데이터 구성
        response_data = {
            'status': 'success',
            'data': paginated.data,
            'pagination': paginated.pagination,
            'metadata': paginated.metadata
        }

        # 조건부 요청 처리
        if enable_conditional:
            response = self.conditional_handler.create_conditional_response(
                data=response_data,
                request=request,
                last_modified=last_modified
            )

            # 304 Not Modified인 경우 바로 반환
            if response.status_code == 304:
                return response

        # 압축 응답 생성
        if enable_compression:
            response = self.compressor.create_compressed_response(
                data=response_data,
                request=request
            )
        else:
            response = JSONResponse(content=response_data)

        # 캐시 저장
        if cache_key:
            self._cache_response(cache_key, response)

        return response

    def optimize_single_response(
        self,
        data: Any,
        request: Request,
        last_modified: datetime = None,
        enable_compression: bool = True,
        enable_conditional: bool = True,
        cache_key: str = None
    ) -> Response:
        """단일 객체 API 응답 최적화"""

        # 캐시 확인
        if cache_key:
            cached_response = self._get_cached_response(cache_key)
            if cached_response:
                return cached_response

        # 응답 데이터 구성
        response_data = {
            'status': 'success',
            'data': data,
            'metadata': {
                'generated_at': datetime.now().isoformat()
            }
        }

        # 조건부 요청 처리
        if enable_conditional:
            response = self.conditional_handler.create_conditional_response(
                data=response_data,
                request=request,
                last_modified=last_modified
            )

            if response.status_code == 304:
                return response

        # 압축 응답 생성
        if enable_compression:
            response = self.compressor.create_compressed_response(
                data=response_data,
                request=request
            )
        else:
            response = JSONResponse(content=response_data)

        # 캐시 저장
        if cache_key:
            self._cache_response(cache_key, response)

        return response

    def _get_cached_response(self, cache_key: str) -> Optional[Response]:
        """캐시된 응답 조회"""
        cached = self.response_cache.get(cache_key)
        if cached:
            cache_time, response = cached
            if time.time() - cache_time < self.cache_ttl:
                return response
            else:
                # 만료된 캐시 제거
                del self.response_cache[cache_key]
        return None

    def _cache_response(self, cache_key: str, response: Response):
        """응답 캐시 저장"""
        self.response_cache[cache_key] = (time.time(), response)

        # 캐시 크기 제한 (최대 100개)
        if len(self.response_cache) > 100:
            # 가장 오래된 항목 제거
            oldest_key = min(self.response_cache.keys(),
                           key=lambda k: self.response_cache[k][0])
            del self.response_cache[oldest_key]

    def clear_cache(self, pattern: str = None):
        """캐시 정리"""
        if pattern:
            # 패턴에 맞는 키만 제거
            keys_to_remove = [k for k in self.response_cache.keys() if pattern in k]
            for key in keys_to_remove:
                del self.response_cache[key]
            logger.info(f"패턴 '{pattern}'에 맞는 {len(keys_to_remove)}개 캐시 항목 제거")
        else:
            # 전체 캐시 제거
            cache_size = len(self.response_cache)
            self.response_cache.clear()
            logger.info(f"전체 {cache_size}개 캐시 항목 제거")

    def get_cache_stats(self) -> Dict[str, Any]:
        """캐시 통계 조회"""
        current_time = time.time()
        valid_items = sum(1 for cache_time, _ in self.response_cache.values()
                         if current_time - cache_time < self.cache_ttl)

        return {
            'total_items': len(self.response_cache),
            'valid_items': valid_items,
            'expired_items': len(self.response_cache) - valid_items,
            'cache_ttl_seconds': self.cache_ttl,
            'memory_usage_mb': sum(len(str(response)) for _, response in self.response_cache.values()) / 1024 / 1024
        }

# 전역 최적화 인스턴스
api_optimizer = ApiResponseOptimizer()

def get_api_optimizer() -> ApiResponseOptimizer:
    """API 응답 최적화 인스턴스 반환"""
    return api_optimizer

def parse_pagination_params(request: Request) -> PaginationParams:
    """요청에서 페이지네이션 파라미터 파싱"""
    page = int(request.query_params.get('page', 1))
    size = int(request.query_params.get('size', 20))

    return PaginationParams(page=page, size=size)

if __name__ == '__main__':
    # 테스트 실행
    import asyncio
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    app = FastAPI()
    optimizer = ApiResponseOptimizer()

    @app.get("/test-pagination")
    async def test_pagination(request: Request):
        # 테스트 데이터
        test_data = [{'id': i, 'name': f'item_{i}'} for i in range(100)]
        pagination_params = parse_pagination_params(request)

        return optimizer.optimize_list_response(
            data=test_data,
            request=request,
            pagination_params=pagination_params,
            cache_key=f"test_pagination_{pagination_params.page}_{pagination_params.size}"
        )

    # 간단한 테스트
    client = TestClient(app)
    response = client.get("/test-pagination?page=2&size=10")
    print("테스트 응답:", response.status_code)
    print("응답 헤더:", dict(response.headers))
    print("페이지네이션 테스트 완료")