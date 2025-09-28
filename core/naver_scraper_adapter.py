#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Naver Scraper Adapter
기존 Amazon 스크래퍼 인터페이스와 호환되는 Naver API 래퍼
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass

from core.naver_shopping_api import NaverShoppingSearchAPI
from core.analyzer_v2 import SQLiteMarketAnalyzer

# 로깅 설정
logger = logging.getLogger(__name__)

@dataclass
class ScrapingMetrics:
    """스크래핑 성능 메트릭 (Amazon 스크래퍼 호환)"""
    start_time: datetime
    end_time: Optional[datetime] = None
    products_found: int = 0
    products_parsed: int = 0
    errors_count: int = 0
    success_rate: float = 0.0
    average_parse_time: float = 0.0


class NaverScraperAdapter:
    """
    Naver Shopping API를 기존 Amazon 스크래퍼 인터페이스로 래핑

    기존 Amazon 스크래퍼와 동일한 메서드를 제공하여
    코드 변경 없이 Naver API로 전환 가능
    """

    def __init__(self):
        """어댑터 초기화"""
        # 환경 변수에서 Naver API 키 가져오기
        client_id = os.getenv('NAVER_CLIENT_ID')
        client_secret = os.getenv('NAVER_CLIENT_SECRET')

        if not client_id or not client_secret:
            raise ValueError("NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET 환경 변수를 설정해주세요.")

        # Naver API 클라이언트 초기화
        self.naver_api = NaverShoppingSearchAPI(client_id, client_secret)

        # 메트릭 초기화 (Amazon 스크래퍼 호환)
        self.metrics = ScrapingMetrics(start_time=datetime.now())

        # 데이터베이스 분석기 초기화
        self.analyzer = SQLiteMarketAnalyzer()

        logger.info("Naver Scraper Adapter 초기화 완료")

    async def start_browser(self) -> bool:
        """
        브라우저 시작 (호환성을 위한 더미 메서드)
        Naver API는 브라우저가 필요하지 않음
        """
        logger.info("Naver API 사용 - 브라우저 불필요")
        return True

    async def close_browser(self):
        """
        브라우저 종료 (호환성을 위한 더미 메서드)
        Naver API는 브라우저가 필요하지 않음
        """
        logger.info("Naver API 사용 - 브라우저 종료 불필요")

    async def scrape_and_save_to_db(self, keyword: str, max_products: int = 30) -> dict:
        """
        키워드로 검색하여 상품 데이터를 수집하고 SQLite 데이터베이스에 저장

        Args:
            keyword: 검색 키워드
            max_products: 최대 수집할 상품 수

        Returns:
            결과 딕셔너리 (Amazon 스크래퍼 호환 형식)
        """
        logger.info(f"=== '{keyword}' 키워드로 Naver 데이터 수집 및 DB 저장 시작 ===")

        # 메트릭 초기화
        self.metrics = ScrapingMetrics(start_time=datetime.now())

        try:
            # Naver API로 상품 데이터 수집
            products = self.naver_api.collect_products_bulk(
                keyword=keyword,
                max_products=max_products,
                progress_callback=self._progress_callback
            )

            self.metrics.products_found = len(products)

            if not products:
                logger.warning(f"키워드 '{keyword}'에 대한 상품을 찾을 수 없습니다.")
                return {
                    "success": False,
                    "message": "상품을 찾을 수 없습니다.",
                    "products_found": 0,
                    "products_saved": 0
                }

            # 데이터베이스에 저장
            saved_count = 0

            with self.analyzer.get_session() as session:
                from core.models import Product, ScrapingSession

                # 스크래핑 세션 기록
                scraping_session = ScrapingSession(
                    keyword=keyword,
                    products_found=len(products),
                    products_saved=0,  # 나중에 업데이트
                    session_status='in_progress',
                    started_at=self.metrics.start_time
                )
                session.add(scraping_session)
                session.commit()

                # 상품 데이터 저장
                logger.info(f"상품 데이터 저장 시작: {len(products)}개 처리 예정")
                for i, product_data in enumerate(products):
                    try:
                        logger.debug(f"[{i+1}/{len(products)}] 상품 처리 중: {product_data.get('product_id', 'UNKNOWN_ID')}")

                        # 데이터 검증
                        required_fields = ['product_id', 'product_title', 'product_category', 'discounted_price']
                        missing_fields = []
                        for field in required_fields:
                            if field not in product_data or product_data[field] is None:
                                missing_fields.append(field)

                        if missing_fields:
                            logger.error(f"필수 필드 누락: {missing_fields} for product {product_data.get('product_id', 'UNKNOWN')}")
                            self.metrics.errors_count += 1
                            continue

                        # 중복 체크 (product_id 기준)
                        existing_product = session.query(Product).filter(
                            Product.product_id == product_data['product_id']
                        ).first()

                        if existing_product:
                            logger.info(f"중복 상품 건너뜀: {product_data['product_id']} (기존 ID: {existing_product.id})")
                            continue

                        # 새 상품 생성
                        product = Product(
                            product_id=product_data['product_id'],
                            product_title=product_data['product_title'],
                            product_category=product_data['product_category'],
                            discounted_price=float(product_data['discounted_price']) if product_data['discounted_price'] else 0.0,
                            product_rating=float(product_data.get('product_rating', 0.0)) if product_data.get('product_rating') else 0.0,
                            total_reviews=int(product_data.get('total_reviews', 0)) if product_data.get('total_reviews') else 0,
                            purchased_last_month=int(product_data.get('purchased_last_month', 0)) if product_data.get('purchased_last_month') else 0,
                            brand=product_data.get('brand', ''),
                            seller=product_data.get('seller', ''),
                            is_prime=bool(product_data.get('is_prime', False)),
                            asin=product_data.get('asin', ''),
                            product_url=product_data.get('product_url', ''),
                            scraped_at=product_data.get('scraped_at') or datetime.now(),
                            data_source='naver_shopping_api'
                        )

                        session.add(product)
                        saved_count += 1
                        logger.debug(f"상품 추가 성공: {product_data['product_id']}")

                    except Exception as e:
                        logger.error(f"상품 저장 중 오류 (상품 ID: {product_data.get('product_id', 'UNKNOWN')}): {str(e)}")
                        logger.error(f"상품 데이터: {product_data}")
                        self.metrics.errors_count += 1
                        continue

                logger.info(f"상품 저장 완료: {saved_count}개 상품이 세션에 추가됨")

                # 스크래핑 세션 업데이트
                scraping_session.products_saved = saved_count
                scraping_session.session_status = 'completed'
                scraping_session.completed_at = datetime.utcnow()

                logger.info(f"데이터베이스 커밋 시작: {saved_count}개 상품")
                try:
                    session.commit()
                    logger.info(f"✅ 데이터베이스 커밋 성공: {saved_count}개 상품 저장 완료")
                except Exception as commit_error:
                    logger.error(f"❌ 데이터베이스 커밋 실패: {str(commit_error)}")
                    session.rollback()
                    saved_count = 0  # 롤백 시 저장 수량 0으로 재설정
                    raise commit_error

            # 메트릭 완료
            self.metrics.end_time = datetime.now()
            self.metrics.products_parsed = saved_count
            self.metrics.success_rate = (saved_count / len(products)) * 100 if products else 0

            result = {
                "success": True,
                "message": f"총 {saved_count}개 상품 저장 완료",
                "products_found": len(products),
                "products_saved": saved_count,
                "errors": self.metrics.errors_count,
                "success_rate": f"{self.metrics.success_rate:.1f} percent",
                "data_source": "naver_shopping_api"
            }

            logger.info(f"✅ Naver 데이터 수집 완료: {result}")
            return result

        except Exception as e:
            error_msg = f"Naver 데이터 수집 중 오류: {str(e)}"
            logger.error(error_msg)

            self.metrics.end_time = datetime.now()
            self.metrics.errors_count += 1

            return {
                "success": False,
                "message": error_msg,
                "products_found": 0,
                "products_saved": 0,
                "error_details": str(e)
            }

    def _progress_callback(self, progress: float, count: int, keyword: str):
        """
        진행률 콜백 함수

        Args:
            progress: 진행률 (0-100)
            count: 현재까지 수집된 상품 수
            keyword: 검색 키워드
        """
        logger.info(f"[{keyword}] 진행률: {progress:.1f}% ({count}개 수집)")

    def get_metrics(self) -> dict:
        """
        스크래핑 메트릭 반환 (Amazon 스크래퍼 호환)

        Returns:
            메트릭 정보 딕셔너리
        """
        duration = 0
        if self.metrics.end_time:
            duration = (self.metrics.end_time - self.metrics.start_time).total_seconds()

        return {
            "start_time": self.metrics.start_time.isoformat(),
            "end_time": self.metrics.end_time.isoformat() if self.metrics.end_time else None,
            "duration_seconds": duration,
            "products_found": self.metrics.products_found,
            "products_parsed": self.metrics.products_parsed,
            "errors_count": self.metrics.errors_count,
            "success_rate": self.metrics.success_rate,
            "average_parse_time": self.metrics.average_parse_time,
            "data_source": "naver_shopping_api"
        }


# 기존 코드와의 호환성을 위한 별칭
AmazonScraperV2 = NaverScraperAdapter