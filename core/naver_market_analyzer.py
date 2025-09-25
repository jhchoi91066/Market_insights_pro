#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
네이버 API 기반 시장 분석기
기존 스크래핑 데이터를 완전히 대체하는 실시간 분석 시스템
"""

import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import statistics
from dotenv import load_dotenv

from .naver_shopping_api import NaverShoppingSearchAPI
from .naver_datalab_api import NaverDataLabAPI

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NaverMarketAnalyzer:
    """
    네이버 API 기반 실시간 시장 분석기
    """

    def __init__(self):
        """분석기 초기화"""
        logger.info("🚀 네이버 기반 시장 분석기 초기화 중...")

        # 환경변수 강제 로드 (여러 번 로드해도 안전)
        load_dotenv('.env.development')
        load_dotenv()  # 기본 .env 파일도 시도

        # API 키 확인
        self.client_id = os.getenv('NAVER_CLIENT_ID')
        self.client_secret = os.getenv('NAVER_CLIENT_SECRET')

        logger.debug(f"로드된 API 키: {self.client_id[:10] if self.client_id else 'None'}...")
        logger.debug(f"로드된 Secret: {self.client_secret[:5] if self.client_secret else 'None'}...")

        if not self.client_id or not self.client_secret:
            logger.error("❌ 네이버 API 키가 설정되지 않았습니다.")
            raise ValueError("네이버 API 키가 필요합니다.")

        # API 클라이언트 초기화
        self.shopping_api = NaverShoppingSearchAPI(self.client_id, self.client_secret)
        self.datalab_api = NaverDataLabAPI(self.client_id, self.client_secret)

        logger.info("✅ 네이버 기반 시장 분석기 초기화 완료!")

    def analyze_market_competition(self, keyword: str, product_count: int = 50) -> Dict[str, Any]:
        """
        키워드 기반 시장 경쟁 분석

        Args:
            keyword: 분석할 키워드
            product_count: 분석할 상품 수 (최대 100)

        Returns:
            경쟁 분석 결과
        """
        logger.info(f"🔍 '{keyword}' 시장 경쟁 분석 시작...")

        try:
            # 네이버 쇼핑 검색
            search_result = self.shopping_api.search_products(keyword, display=min(product_count, 100))

            if not search_result.get('items'):
                return {
                    'keyword': keyword,
                    'error': 'No products found',
                    'competitor_count': 0,
                    'difficulty_score': 0,
                    'market_analysis': 'No data available'
                }

            # 상품 데이터 변환
            products = []
            for item in search_result['items']:
                converted = self.shopping_api.convert_to_amazon_format(item, keyword)
                if self._is_valid_product(converted):
                    products.append(converted)

            logger.info(f"✅ 유효한 상품 {len(products)}개 분석")

            # 경쟁 분석 수행
            analysis_result = self._perform_competition_analysis(keyword, products)

            return analysis_result

        except Exception as e:
            logger.error(f"❌ 시장 경쟁 분석 중 오류: {str(e)}")
            return {
                'keyword': keyword,
                'error': str(e),
                'competitor_count': 0,
                'difficulty_score': 0,
                'market_analysis': 'Analysis failed'
            }

    def _perform_competition_analysis(self, keyword: str, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """경쟁 분석 수행"""

        if not products:
            return {
                'keyword': keyword,
                'competitor_count': 0,
                'difficulty_score': 0,
                'market_analysis': 'No valid products found'
            }

        # 기본 통계
        competitor_count = len(products)
        prices = [p.get('discounted_price', 0) for p in products if p.get('discounted_price', 0) > 0]
        ratings = [p.get('product_rating', 0) for p in products if p.get('product_rating', 0) > 0]
        reviews = [p.get('total_reviews', 0) for p in products if p.get('total_reviews', 0) > 0]

        # 가격 분석
        price_analysis = self._analyze_prices(prices)

        # 품질 분석
        quality_analysis = self._analyze_quality(ratings, reviews)

        # 브랜드 분석
        brands = [p.get('brand', 'Unknown') for p in products if p.get('brand')]
        brand_diversity = len(set(brands))

        # 난이도 점수 계산 (0-10)
        difficulty_score = self._calculate_difficulty_score(
            competitor_count, prices, ratings, reviews, brand_diversity
        )

        # TOP 10 상품 추출
        top_products = sorted(products, key=lambda x: x.get('purchased_last_month', 0), reverse=True)[:10]

        return {
            'keyword': keyword,
            'analysis_timestamp': datetime.now().isoformat(),

            # 기본 지표
            'competitor_count': competitor_count,
            'difficulty_score': round(difficulty_score, 1),
            'brand_diversity': brand_diversity,

            # 가격 분석
            'price_analysis': price_analysis,

            # 품질 분석
            'quality_analysis': quality_analysis,

            # 상품 데이터
            'products': products,
            'top_10_products': top_products,

            # 시장 인사이트
            'market_insights': self._generate_market_insights(
                difficulty_score, competitor_count, price_analysis, quality_analysis
            ),

            # 추천
            'recommendation': self._generate_recommendation(difficulty_score),

            # 메타데이터
            'data_source': 'naver_shopping_api',
            'data_freshness': 'real_time'
        }

    def _analyze_prices(self, prices: List[float]) -> Dict[str, Any]:
        """가격 분석"""
        if not prices:
            return {'error': 'No price data available'}

        return {
            'min_price': round(min(prices), 2),
            'max_price': round(max(prices), 2),
            'avg_price': round(statistics.mean(prices), 2),
            'median_price': round(statistics.median(prices), 2),
            'price_range': round(max(prices) - min(prices), 2),
            'price_std': round(statistics.stdev(prices) if len(prices) > 1 else 0, 2)
        }

    def _analyze_quality(self, ratings: List[float], reviews: List[int]) -> Dict[str, Any]:
        """품질 분석"""
        quality_data = {}

        if ratings:
            quality_data.update({
                'avg_rating': round(statistics.mean(ratings), 2),
                'min_rating': round(min(ratings), 1),
                'max_rating': round(max(ratings), 1),
                'rating_std': round(statistics.stdev(ratings) if len(ratings) > 1 else 0, 2)
            })

        if reviews:
            quality_data.update({
                'avg_reviews': round(statistics.mean(reviews)),
                'total_reviews': sum(reviews),
                'max_reviews': max(reviews)
            })

        return quality_data

    def _calculate_difficulty_score(self, competitor_count: int, prices: List[float],
                                  ratings: List[float], reviews: List[int],
                                  brand_diversity: int) -> float:
        """시장 진입 난이도 점수 계산 (0-10)"""

        # 경쟁 밀도 점수 (0-4)
        if competitor_count <= 10:
            competition_density = 1
        elif competitor_count <= 30:
            competition_density = 2
        elif competitor_count <= 50:
            competition_density = 3
        else:
            competition_density = 4

        # 품질 기대치 점수 (0-3)
        avg_rating = statistics.mean(ratings) if ratings else 3.5
        if avg_rating < 3.5:
            quality_expectation = 1
        elif avg_rating < 4.0:
            quality_expectation = 2
        else:
            quality_expectation = 3

        # 브랜드 다양성 점수 (0-2)
        if brand_diversity <= 3:
            brand_score = 0.5
        elif brand_diversity <= 7:
            brand_score = 1
        else:
            brand_score = 2

        # 가격 경쟁 점수 (0-1)
        price_competition = 1 if prices and (max(prices) - min(prices)) > statistics.mean(prices) else 0.5

        total_score = competition_density + quality_expectation + brand_score + price_competition
        return min(10, max(0, total_score))

    def _generate_market_insights(self, difficulty_score: float, competitor_count: int,
                                price_analysis: Dict[str, Any], quality_analysis: Dict[str, Any]) -> List[str]:
        """시장 인사이트 생성"""
        insights = []

        # 경쟁 강도
        if difficulty_score < 3:
            insights.append("🟢 낮은 경쟁 강도: 시장 진입에 유리한 환경")
        elif difficulty_score < 6:
            insights.append("🟡 중간 경쟁 강도: 차별화 전략 필요")
        else:
            insights.append("🔴 높은 경쟁 강도: 신중한 시장 접근 필요")

        # 가격 경쟁
        if price_analysis.get('price_std', 0) > price_analysis.get('avg_price', 0) * 0.3:
            insights.append("💰 높은 가격 변동성: 가격 포지셔닝 기회 존재")
        else:
            insights.append("📊 안정적 가격대: 일관된 시장 가격 형성")

        # 품질 경쟁
        avg_rating = quality_analysis.get('avg_rating', 0)
        if avg_rating > 4.2:
            insights.append("⭐ 높은 품질 기대치: 품질 경쟁이 중요")
        elif avg_rating < 3.8:
            insights.append("🔧 품질 개선 기회: 시장 표준 향상 가능")

        return insights

    def _generate_recommendation(self, difficulty_score: float) -> Dict[str, Any]:
        """추천 생성"""
        if difficulty_score < 3:
            return {
                'level': 'recommended',
                'emoji': '🟢',
                'message': '시장 진입 추천',
                'reason': '낮은 경쟁과 좋은 기회'
            }
        elif difficulty_score < 6:
            return {
                'level': 'cautious',
                'emoji': '🟡',
                'message': '신중한 진입',
                'reason': '중간 경쟁, 차별화 필요'
            }
        else:
            return {
                'level': 'not_recommended',
                'emoji': '🔴',
                'message': '진입 비추천',
                'reason': '높은 경쟁과 시장 포화'
            }

    def get_trend_enhanced_analysis(self, keyword: str, days: int = 14, product_count: int = 50) -> Dict[str, Any]:
        """
        트렌드 데이터가 결합된 종합 분석

        Args:
            keyword: 분석할 키워드
            days: 트렌드 분석 기간
            product_count: 분석할 상품 수

        Returns:
            트렌드와 경쟁 분석이 결합된 결과
        """
        logger.info(f"🔄 '{keyword}' 트렌드 결합 종합 분석 시작...")

        # 1. 기본 경쟁 분석
        competition_analysis = self.analyze_market_competition(keyword, product_count)

        # 2. 트렌드 분석
        try:
            trend_data = self.datalab_api.get_comprehensive_market_insight(keyword, days)

            # 3. 트렌드 기반 난이도 조정
            original_difficulty = competition_analysis.get('difficulty_score', 0)
            trend_adjustment = self._calculate_trend_adjustment(trend_data)
            adjusted_difficulty = min(10, max(0, original_difficulty + trend_adjustment))

            logger.info(f"✅ 트렌드 조정: {original_difficulty} → {adjusted_difficulty}")

            # 4. 결합된 분석 결과
            enhanced_analysis = competition_analysis.copy()
            enhanced_analysis.update({
                'trend_data': trend_data,
                'original_difficulty_score': original_difficulty,
                'adjusted_difficulty_score': round(adjusted_difficulty, 1),
                'trend_adjustment': round(trend_adjustment, 1),
                'enhanced_recommendation': self._generate_enhanced_recommendation(
                    adjusted_difficulty, trend_data
                ),
                'analysis_type': 'trend_enhanced'
            })

            return enhanced_analysis

        except Exception as e:
            logger.warning(f"⚠️ 트렌드 데이터 조회 실패: {str(e)}")
            # 트렌드 데이터 없이 기본 분석 반환
            competition_analysis['analysis_type'] = 'competition_only'
            return competition_analysis

    def _calculate_trend_adjustment(self, trend_data: Dict[str, Any]) -> float:
        """트렌드 데이터 기반 난이도 조정 계산"""
        if not trend_data:
            return 0

        market_heat = trend_data.get('market_heat', 'cold')
        trend_direction = trend_data.get('trend_direction', 'stable')
        popularity_index = trend_data.get('popularity_index', 0)

        adjustment = 0

        # 시장 열기 기반 조정
        if market_heat == 'hot':
            adjustment += 1.5  # 뜨거운 시장은 경쟁 증가
        elif market_heat == 'warm':
            adjustment += 0.5
        elif market_heat == 'cold':
            adjustment -= 1.0  # 차가운 시장은 경쟁 감소

        # 트렌드 방향 기반 조정
        if trend_direction == 'rising':
            adjustment += 1.0  # 상승 트렌드는 경쟁 증가
        elif trend_direction == 'falling':
            adjustment -= 0.5

        # 인기도 지수 기반 조정
        if popularity_index > 70:
            adjustment += 0.5
        elif popularity_index < 30:
            adjustment -= 0.5

        return adjustment

    def _generate_enhanced_recommendation(self, adjusted_difficulty: float,
                                       trend_data: Dict[str, Any]) -> Dict[str, Any]:
        """트렌드 데이터가 포함된 향상된 추천"""
        base_recommendation = self._generate_recommendation(adjusted_difficulty)

        market_heat = trend_data.get('market_heat', 'unknown')
        trend_direction = trend_data.get('trend_direction', 'unknown')

        # 트렌드 기반 추가 인사이트
        trend_insights = []

        if market_heat == 'hot' and trend_direction == 'rising':
            trend_insights.append("🔥 뜨거운 상승 트렌드: 기회이지만 경쟁 치열")
        elif market_heat == 'cold' and adjusted_difficulty < 4:
            trend_insights.append("❄️ 조용한 시장: 선점 기회")
        elif trend_direction == 'falling':
            trend_insights.append("📉 하락 트렌드: 시장 진입 재고 필요")

        base_recommendation['trend_insights'] = trend_insights
        base_recommendation['market_heat'] = market_heat
        base_recommendation['trend_direction'] = trend_direction

        return base_recommendation

    def calculate_market_saturation(self, keyword: str, product_count: int = 100) -> Dict[str, Any]:
        """시장 포화도 계산"""
        logger.info(f"📊 '{keyword}' 시장 포화도 계산...")

        try:
            # 상품 데이터 조회
            search_result = self.shopping_api.search_products(keyword, display=product_count)

            if not search_result.get('items'):
                return {
                    'keyword': keyword,
                    'market_saturation_percentage': 0,
                    'analysis': 'No data available'
                }

            products = []
            for item in search_result['items']:
                converted = self.shopping_api.convert_to_amazon_format(item, keyword)
                if self._is_valid_product(converted):
                    products.append(converted)

            # 포화도 계산
            actual_products = len(products)
            top_10_sales = sum(
                p.get('purchased_last_month', 0)
                for p in sorted(products, key=lambda x: x.get('purchased_last_month', 0), reverse=True)[:10]
            )

            # 추정 전체 시장 크기 (검색 결과 기반)
            estimated_total_products = search_result.get('total', actual_products * 10)

            # 포화도 계산 (TOP 10이 차지하는 비율)
            total_sales = sum(p.get('purchased_last_month', 0) for p in products)
            saturation_percentage = (top_10_sales / total_sales * 100) if total_sales > 0 else 0

            return {
                'keyword': keyword,
                'actual_products_analyzed': actual_products,
                'estimated_total_products': min(estimated_total_products, 10000),  # 상한선
                'top_10_total_sales': top_10_sales,
                'market_saturation_percentage': round(saturation_percentage, 1),
                'saturation_level': self._get_saturation_level(saturation_percentage),
                'analysis_timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ 시장 포화도 계산 중 오류: {str(e)}")
            return {
                'keyword': keyword,
                'error': str(e),
                'market_saturation_percentage': 0
            }

    def _get_saturation_level(self, percentage: float) -> str:
        """포화도 레벨 결정"""
        if percentage < 20:
            return "low"
        elif percentage < 40:
            return "medium"
        elif percentage < 60:
            return "high"
        else:
            return "very_high"

    def _is_valid_product(self, product: Dict[str, Any]) -> bool:
        """유효한 상품인지 확인"""
        required_fields = ['product_title', 'discounted_price']
        return all(
            product.get(field) is not None and
            str(product.get(field)) != 'N/A' and
            product.get(field) != 0
            for field in required_fields
        )

    def get_health_status(self) -> Dict[str, Any]:
        """분석기 상태 확인"""
        return {
            'status': 'healthy',
            'shopping_api': 'connected' if self.shopping_api else 'disconnected',
            'datalab_api': 'connected' if self.datalab_api else 'disconnected',
            'data_source': 'naver_apis_only',
            'last_check': datetime.now().isoformat()
        }