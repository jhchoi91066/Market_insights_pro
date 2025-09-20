#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
네이버 쇼핑검색 API 클라이언트
Amazon 스크래핑을 대체하는 안정적인 데이터 수집 시스템
"""

import urllib.request
import urllib.parse
import json
import time
import re
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import requests

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NaverShoppingSearchAPI:
    """
    네이버 쇼핑검색 API 클라이언트 클래스
    기존 Amazon 스크래퍼와 동일한 인터페이스를 제공하여 호환성 보장
    """

    def __init__(self, client_id: str, client_secret: str):
        """
        API 클라이언트 초기화

        Args:
            client_id: 네이버 API Client ID
            client_secret: 네이버 API Client Secret
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://openapi.naver.com/v1/search/shop.json"
        self.last_request_time = 0
        self.min_request_interval = 0.04  # 초당 최대 25회 (여유있게 설정)

        # 환율 정보 (원 → 달러, 실제로는 환율 API 연동 권장)
        self.exchange_rate = 1350  # 1달러 = 1350원 (임시값)

        logger.info("네이버 쇼핑검색 API 클라이언트 초기화 완료")

    def _wait_for_rate_limit(self):
        """API 호출 제한 준수를 위한 대기"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        if time_since_last_request < self.min_request_interval:
            wait_time = self.min_request_interval - time_since_last_request
            time.sleep(wait_time)

        self.last_request_time = time.time()

    def search_products(self, keyword: str, start: int = 1, display: int = 100, sort: str = "sim") -> Dict[str, Any]:
        """
        네이버 쇼핑검색 API로 상품 검색

        Args:
            keyword: 검색 키워드
            start: 검색 시작 위치 (1~1000)
            display: 한 번에 가져올 상품 수 (1~100)
            sort: 정렬 방식 (sim: 정확도, date: 날짜, asc: 가격오름차순, dsc: 가격내림차순)

        Returns:
            API 응답 데이터 (JSON)
        """
        self._wait_for_rate_limit()

        # URL 인코딩
        encText = urllib.parse.quote(keyword)
        url = f"{self.base_url}?query={encText}&start={start}&display={display}&sort={sort}"

        # 헤더 설정
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret
        }

        try:
            # requests 라이브러리 사용 (SSL 문제 해결)
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                result = response.json()
                logger.info(f"키워드 '{keyword}' 검색 완료: {len(result.get('items', []))}개 상품")
                return result
            else:
                logger.error(f"API 요청 실패: HTTP {response.status_code}")
                logger.error(f"응답 내용: {response.text}")
                return {"items": [], "total": 0, "start": start, "display": display}

        except Exception as e:
            logger.error(f"API 요청 중 오류 발생: {str(e)}")
            return {"items": [], "total": 0, "start": start, "display": display}

    def clean_product_title(self, title: str) -> str:
        """
        제품 제목에서 HTML 태그 및 불필요한 내용 제거

        Args:
            title: 원본 제품 제목

        Returns:
            정제된 제품 제목
        """
        if not title:
            return ""

        # HTML 태그 제거
        title = re.sub(r'<[^>]+>', '', title)

        # 특수문자 정규화
        title = title.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')

        # 불필요한 공백 제거
        title = ' '.join(title.split())

        return title[:200]  # 길이 제한

    def convert_price_to_dollar(self, korean_price: str) -> float:
        """
        한국 원화를 달러로 변환

        Args:
            korean_price: 원화 가격 (문자열)

        Returns:
            달러 가격 (float)
        """
        try:
            # 숫자만 추출
            price_numbers = re.findall(r'\d+', korean_price)
            if price_numbers:
                won_price = int(''.join(price_numbers))
                dollar_price = round(won_price / self.exchange_rate, 2)
                return dollar_price
            return 0.0
        except Exception:
            return 0.0

    def convert_to_amazon_format(self, naver_product: Dict[str, Any], keyword: str) -> Dict[str, Any]:
        """
        네이버 검색 API 응답을 Amazon 호환 형식으로 변환

        Args:
            naver_product: 네이버 API 상품 데이터
            keyword: 검색 키워드

        Returns:
            Amazon Product 모델 호환 데이터
        """
        try:
            # 기본 데이터 추출 (docs/naver.md 참고)
            title = self.clean_product_title(naver_product.get('title', ''))
            lprice = naver_product.get('lprice', '0')
            hprice = naver_product.get('hprice', '0')  # 최고가
            mall_name = naver_product.get('mallName', 'Unknown')
            product_url = naver_product.get('link', '')
            product_id = naver_product.get('productId', '')

            # 네이버 특화 데이터
            category1 = naver_product.get('category1', '')
            category2 = naver_product.get('category2', '')
            category3 = naver_product.get('category3', '')
            category4 = naver_product.get('category4', '')
            brand = naver_product.get('brand', '')
            maker = naver_product.get('maker', '')
            image_url = naver_product.get('image', '')

            # 고유 ID 생성
            if not product_id and product_url:
                # URL에서 상품 ID 추출 시도
                url_match = re.search(r'product[=/](\d+)', product_url)
                product_id = url_match.group(1) if url_match else str(abs(hash(product_url)))[:8]

            final_product_id = f"NAVER_{product_id}" if product_id else f"NAVER_{abs(hash(title + lprice))}"

            # 가격 변환 (최저가 우선 사용)
            dollar_price = self.convert_price_to_dollar(lprice if lprice != '0' else hprice)

            # 카테고리 처리 (category1~4를 통합)
            categories = []
            for cat in [category1, category2, category3, category4]:
                if cat:
                    categories.append(cat)

            final_category = ' > '.join(categories) if categories else keyword

            # Amazon 호환 형식으로 변환
            amazon_format = {
                'product_id': final_product_id,
                'product_title': title,
                'product_category': final_category,
                'discounted_price': dollar_price,
                'product_rating': 4.0,  # 기본값 (네이버 API에서 제공하지 않음)
                'total_reviews': 100,   # 기본값 (네이버 API에서 제공하지 않음)
                'purchased_last_month': 50,  # 기본값 (추정치)
                'brand': brand,
                'seller': mall_name,
                'is_prime': False,  # 네이버에는 Prime 개념 없음
                'asin': '',  # 네이버에는 ASIN 없음
                'product_url': product_url,
                'scraped_at': datetime.utcnow(),

                # 추가 메타데이터 (네이버 특화)
                'original_price_won': lprice,
                'highest_price_won': hprice,
                'image_url': image_url,
                'maker': maker,
                'data_source': 'naver_shopping_search',
                'naver_category1': category1,
                'naver_category2': category2,
                'naver_category3': category3,
                'naver_category4': category4
            }

            return amazon_format

        except Exception as e:
            logger.error(f"데이터 변환 중 오류: {str(e)}")
            return None

    def is_valid_product(self, product: Dict[str, Any]) -> bool:
        """
        상품 데이터 유효성 검증

        Args:
            product: 변환된 상품 데이터

        Returns:
            유효성 여부 (bool)
        """
        if not product:
            return False

        # 필수 필드 체크
        required_fields = ['product_title', 'discounted_price', 'product_url']
        for field in required_fields:
            if not product.get(field):
                return False

        # 가격 유효성 체크 (0원 제품 제외)
        if product['discounted_price'] <= 0:
            return False

        # 제목 길이 체크
        if len(product['product_title']) < 5:
            return False

        # URL 유효성 체크
        if not product['product_url'].startswith('http'):
            return False

        # 제목에서 광고성 키워드 필터링
        ad_keywords = ['광고', '스폰', 'AD', 'sponsored']
        title_lower = product['product_title'].lower()
        for keyword in ad_keywords:
            if keyword.lower() in title_lower:
                return False

        return True

    def collect_products_bulk(self, keyword: str, max_products: int = 1000,
                             progress_callback=None) -> List[Dict[str, Any]]:
        """
        대량 상품 데이터 수집

        Args:
            keyword: 검색 키워드
            max_products: 최대 수집할 상품 수
            progress_callback: 진행률 콜백 함수

        Returns:
            변환된 상품 데이터 리스트
        """
        products = []
        page_size = 100  # 한 번에 가져올 상품 수
        start = 1
        seen_products = set()  # 중복 제거용

        logger.info(f"키워드 '{keyword}'로 최대 {max_products}개 상품 수집 시작")

        while len(products) < max_products:
            # API 요청
            api_response = self.search_products(keyword, start, page_size)
            items = api_response.get('items', [])

            if not items:
                logger.info("더 이상 상품이 없습니다.")
                break

            # 데이터 변환 및 필터링
            for item in items:
                if len(products) >= max_products:
                    break

                converted_product = self.convert_to_amazon_format(item, keyword)

                if self.is_valid_product(converted_product):
                    # 중복 제거 (제품명 + 가격 기준)
                    product_key = f"{converted_product['product_title']}_{converted_product['discounted_price']}"

                    if product_key not in seen_products:
                        seen_products.add(product_key)
                        products.append(converted_product)

            # 진행률 콜백 호출
            if progress_callback:
                progress = min(len(products) / max_products * 100, 100)
                progress_callback(progress, len(products), keyword)

            # 다음 페이지 준비
            start += page_size

            # API 제한 확인 (1000개 제한)
            if start > 1000:
                logger.warning("네이버 검색 API 제한(1000개)에 도달했습니다.")
                break

        logger.info(f"수집 완료: {len(products)}개 유효한 상품")
        return products


def test_naver_search_api():
    """
    네이버 쇼핑검색 API 테스트 함수
    실제 API 키가 있을 때 테스트용으로 사용
    """
    # 환경 변수에서 API 키 가져오기 (실제 구현시)
    import os

    client_id = os.getenv('NAVER_CLIENT_ID', 'YOUR_CLIENT_ID')
    client_secret = os.getenv('NAVER_CLIENT_SECRET', 'YOUR_CLIENT_SECRET')

    if client_id == 'YOUR_CLIENT_ID':
        print("❌ 환경 변수에 네이버 API 키를 설정해주세요.")
        return

    # API 클라이언트 초기화
    api = NaverShoppingSearchAPI(client_id, client_secret)

    # 테스트 검색
    test_keyword = "아이패드"
    print(f"테스트 검색: '{test_keyword}'")

    # 소량 테스트
    products = api.collect_products_bulk(test_keyword, max_products=10)

    print(f"✅ 수집된 상품 수: {len(products)}")

    if products:
        print("\n첫 번째 상품 정보:")
        first_product = products[0]
        for key, value in first_product.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    test_naver_search_api()