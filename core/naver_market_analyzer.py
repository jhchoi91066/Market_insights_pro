#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
네이버 API 기반 시장 분석기
기존 스크래핑 데이터를 완전히 대체하는 실시간 분석 시스템
"""

import os
import logging
import math
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
        """시장 진입 난이도 점수 계산 (0-10) - 개선된 로직"""

        # 1. 경쟁 밀도 점수 (0-3.5) - 더 세밀한 구분
        if competitor_count <= 15:
            competition_density = 0.5  # 매우 낮은 경쟁
        elif competitor_count <= 25:
            competition_density = 1.5  # 낮은 경쟁
        elif competitor_count <= 40:
            competition_density = 2.5  # 중간 경쟁
        elif competitor_count <= 60:
            competition_density = 3.0  # 높은 경쟁
        else:
            competition_density = 3.5  # 매우 높은 경쟁

        # 2. 리뷰 경쟁 강도 (0-2.5) - 리뷰 수가 많을수록 진입장벽
        avg_reviews = statistics.mean(reviews) if reviews else 100
        if avg_reviews <= 50:
            review_competition = 0.5
        elif avg_reviews <= 200:
            review_competition = 1.0
        elif avg_reviews <= 500:
            review_competition = 1.5
        elif avg_reviews <= 1000:
            review_competition = 2.0
        else:
            review_competition = 2.5

        # 3. 품질 표준 점수 (0-2.5) - 평점이 높을수록 진입 어려움
        avg_rating = statistics.mean(ratings) if ratings else 3.5
        if avg_rating < 3.5:
            quality_standard = 0.5  # 품질 개선 기회
        elif avg_rating < 4.0:
            quality_standard = 1.0  # 보통 품질 기준
        elif avg_rating < 4.3:
            quality_standard = 1.5  # 높은 품질 기준
        elif avg_rating < 4.5:
            quality_standard = 2.0  # 매우 높은 품질 기준
        else:
            quality_standard = 2.5  # 극도로 높은 품질 기준

        # 4. 브랜드 포화도 (0-1.5)
        if brand_diversity <= 5:
            brand_saturation = 0.5  # 브랜드 기회 존재
        elif brand_diversity <= 10:
            brand_saturation = 1.0  # 보통 브랜드 경쟁
        else:
            brand_saturation = 1.5  # 높은 브랜드 포화

        # 5. 가격 전쟁 지표 (0-0.5) - 작은 가중치로 조정
        if not prices:
            price_war = 0
        else:
            price_std = statistics.stdev(prices) if len(prices) > 1 else 0
            price_mean = statistics.mean(prices)
            price_cv = price_std / price_mean if price_mean > 0 else 0  # 변동계수
            price_war = min(0.5, price_cv * 2)  # 가격 변동이 클수록 경쟁 치열

        total_score = competition_density + review_competition + quality_standard + brand_saturation + price_war
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

    async def analyze_trending_opportunities(self, base_keyword: str) -> Dict[str, Any]:
        """
        트렌딩 기회 분석 - Phase 1.1 구현
        기본 키워드를 바탕으로 높은 성장률과 낮은 경쟁도를 가진 관련 키워드 탐지

        Args:
            base_keyword: 기본 분석 키워드

        Returns:
            트렌딩 기회 분석 결과
        """
        logger.info(f"🎯 트렌딩 기회 분석 시작: '{base_keyword}'")

        try:
            # 1. 관련 키워드 생성
            related_keywords = self._generate_opportunity_keywords(base_keyword)

            # 2. 각 키워드에 대한 트렌드 및 경쟁 분석
            opportunities = []

            for keyword in related_keywords[:10]:  # 최대 10개 키워드 분석
                logger.info(f"   분석 중: {keyword}")

                # 트렌드 데이터 수집
                trend_data = self.datalab_api.get_search_trends([keyword], days=30)
                trend_metrics = self.datalab_api.analyze_trend_metrics(trend_data, keyword)

                # 경쟁도 분석
                competition_data = self._analyze_keyword_competition(keyword)

                # 기회 점수 계산
                opportunity_score = self._calculate_opportunity_score(
                    trend_metrics, competition_data, keyword
                )

                opportunities.append({
                    "keyword": keyword,
                    "opportunity_score": opportunity_score["score"],
                    "trend_score": trend_metrics["trend_score"],
                    "trend_direction": trend_metrics["trend_direction"],
                    "trend_change_percent": trend_metrics.get("trend_change_percent", 0),
                    "competition_level": competition_data["competition_level"],
                    "competitor_count": competition_data["competitor_count"],
                    "avg_price": competition_data["avg_price"],
                    "market_gap_indicator": opportunity_score["market_gap_indicator"],
                    "recommendation_reason": opportunity_score["reason"]
                })

                # API 제한 준수
                import time
                time.sleep(0.5)

            # 3. 기회 점수 기준으로 정렬
            opportunities.sort(key=lambda x: x["opportunity_score"], reverse=True)

            # 4. 상위 기회 키워드 선별
            top_opportunities = opportunities[:5]

            # 5. 종합 분석 결과 생성
            analysis_result = {
                "base_keyword": base_keyword,
                "analysis_timestamp": datetime.now().isoformat(),
                "total_analyzed": len(opportunities),
                "top_opportunities": top_opportunities,
                "analysis_summary": {
                    "high_opportunity_count": len([o for o in opportunities if o["opportunity_score"] >= 75]),
                    "medium_opportunity_count": len([o for o in opportunities if 50 <= o["opportunity_score"] < 75]),
                    "avg_opportunity_score": sum(o["opportunity_score"] for o in opportunities) / len(opportunities) if opportunities else 0,
                    "trending_up_count": len([o for o in opportunities if o["trend_direction"] == "rising"]),
                    "low_competition_count": len([o for o in opportunities if o["competition_level"] == "low"])
                }
            }

            logger.info(f"✅ 트렌딩 기회 분석 완료: 상위 기회 {len(top_opportunities)}개 발견")
            return analysis_result

        except Exception as e:
            logger.error(f"❌ 트렌딩 기회 분석 중 오류: {str(e)}")
            return {
                "base_keyword": base_keyword,
                "error": str(e),
                "top_opportunities": [],
                "analysis_summary": {}
            }

    def _generate_opportunity_keywords(self, base_keyword: str) -> List[str]:
        """
        기회 키워드 생성 - 다양한 패턴으로 관련 키워드 확장

        Args:
            base_keyword: 기본 키워드

        Returns:
            확장된 키워드 리스트
        """
        opportunity_patterns = [
            # 트렌드 관련
            f"{base_keyword} 신제품",
            f"{base_keyword} 2024",
            f"{base_keyword} 2025",
            f"{base_keyword} 최신",
            f"{base_keyword} 인기",
            f"{base_keyword} 화제",

            # 용도/목적별
            f"{base_keyword} 선물",
            f"{base_keyword} 업무용",
            f"{base_keyword} 가정용",
            f"{base_keyword} 전문가용",
            f"고급 {base_keyword}",
            f"프리미엄 {base_keyword}",

            # 특성별
            f"무선 {base_keyword}",
            f"휴대용 {base_keyword}",
            f"소형 {base_keyword}",
            f"대용량 {base_keyword}",
            f"고성능 {base_keyword}",

            # 가격대별
            f"저렴한 {base_keyword}",
            f"가성비 {base_keyword}",
            f"합리적 {base_keyword}",

            # 브랜드/품질
            f"국산 {base_keyword}",
            f"수입 {base_keyword}",
            f"브랜드 {base_keyword}",

            # 구매 관련
            f"{base_keyword} 추천",
            f"{base_keyword} 비교",
            f"{base_keyword} 순위",
            f"{base_keyword} 리뷰"
        ]

        return opportunity_patterns

    def _analyze_keyword_competition(self, keyword: str) -> Dict[str, Any]:
        """
        키워드별 경쟁도 분석

        Args:
            keyword: 분석할 키워드

        Returns:
            경쟁도 분석 결과
        """
        try:
            # 쇼핑 검색 결과 조회
            search_results = self.shopping_api.search_products(keyword, display=30)

            if not search_results or not search_results.get('items'):
                return {
                    "competition_level": "unknown",
                    "competitor_count": 0,
                    "avg_price": 0,
                    "price_range": {"min": 0, "max": 0}
                }

            items = search_results['items']
            competitor_count = len(items)

            # 가격 정보 추출 및 분석
            prices = []
            for item in items:
                price_str = item.get('lprice', '0')
                try:
                    price = int(price_str)
                    if price > 0:
                        prices.append(price)
                except:
                    continue

            if prices:
                avg_price = statistics.mean(prices)
                min_price = min(prices)
                max_price = max(prices)
            else:
                avg_price = min_price = max_price = 0

            # 경쟁도 레벨 결정
            if competitor_count <= 10:
                competition_level = "low"
            elif competitor_count <= 20:
                competition_level = "medium"
            else:
                competition_level = "high"

            return {
                "competition_level": competition_level,
                "competitor_count": competitor_count,
                "avg_price": round(avg_price),
                "price_range": {
                    "min": min_price,
                    "max": max_price
                }
            }

        except Exception as e:
            logger.error(f"경쟁도 분석 중 오류: {str(e)}")
            return {
                "competition_level": "unknown",
                "competitor_count": 0,
                "avg_price": 0,
                "price_range": {"min": 0, "max": 0}
            }

    def _calculate_opportunity_score(self, trend_metrics: Dict, competition_data: Dict, keyword: str) -> Dict[str, Any]:
        """
        기회 점수 계산 알고리즘
        트렌드 성장률과 경쟁도를 종합하여 시장 진입 기회 점수 산출

        Args:
            trend_metrics: 트렌드 분석 결과
            competition_data: 경쟁도 분석 결과
            keyword: 키워드

        Returns:
            기회 점수 및 분석 결과
        """
        try:
            # 1. 트렌드 점수 (0-50점)
            trend_score = trend_metrics.get("trend_score", 0)
            trend_change = trend_metrics.get("trend_change_percent", 0)

            # 트렌드 방향에 따른 가중치
            trend_direction = trend_metrics.get("trend_direction", "stable")
            if trend_direction == "rising":
                trend_weight = min(50, trend_score * 0.4 + abs(trend_change) * 0.3)
            elif trend_direction == "stable":
                trend_weight = min(50, trend_score * 0.3)
            else:  # falling
                trend_weight = min(50, trend_score * 0.2)

            # 2. 경쟁도 점수 (0-30점) - 경쟁이 낮을수록 높은 점수
            competition_level = competition_data.get("competition_level", "unknown")
            competitor_count = competition_data.get("competitor_count", 0)

            if competition_level == "low" or competitor_count <= 10:
                competition_weight = 30
            elif competition_level == "medium" or competitor_count <= 20:
                competition_weight = 20
            elif competition_level == "high":
                competition_weight = 10
            else:
                competition_weight = 5

            # 3. 시장 갭 지표 (0-20점)
            # 트렌드는 상승하는데 경쟁자가 적으면 높은 점수
            market_gap_score = 0
            if trend_direction == "rising" and competition_level in ["low", "medium"]:
                market_gap_score = 20
            elif trend_direction == "rising" and competition_level == "high":
                market_gap_score = 10
            elif trend_direction == "stable" and competition_level == "low":
                market_gap_score = 15
            else:
                market_gap_score = 5

            # 4. 총 기회 점수 계산 (0-100점)
            total_score = trend_weight + competition_weight + market_gap_score
            total_score = min(100, max(0, total_score))

            # 5. 추천 이유 생성
            reasons = []
            if trend_direction == "rising":
                reasons.append(f"상승 트렌드 (+{trend_change:.1f}%)")
            if competition_level == "low":
                reasons.append("낮은 경쟁도")
            if market_gap_score >= 15:
                reasons.append("시장 갭 존재")
            if trend_score >= 70:
                reasons.append("높은 검색 관심도")

            recommendation_reason = ", ".join(reasons) if reasons else "안정적 시장"

            # 6. 시장 갭 지표 텍스트
            if market_gap_score >= 20:
                gap_indicator = "🎯 고기회"
            elif market_gap_score >= 15:
                gap_indicator = "📈 중기회"
            elif market_gap_score >= 10:
                gap_indicator = "⚡ 저기회"
            else:
                gap_indicator = "⚠️ 주의"

            return {
                "score": round(total_score, 1),
                "trend_weight": round(trend_weight, 1),
                "competition_weight": competition_weight,
                "market_gap_score": market_gap_score,
                "market_gap_indicator": gap_indicator,
                "reason": recommendation_reason
            }

        except Exception as e:
            logger.error(f"기회 점수 계산 중 오류: {str(e)}")
            return {
                "score": 0,
                "trend_weight": 0,
                "competition_weight": 0,
                "market_gap_score": 0,
                "market_gap_indicator": "⚠️ 오류",
                "reason": "분석 오류"
            }

    async def analyze_category_growth_rates(self, target_categories: List[str] = None, days: int = 30) -> Dict[str, Any]:
        """
        카테고리 성장률 분석 - Phase 1.2 구현
        주요 카테고리들의 성장률을 비교하고 진입 추천도를 계산

        Args:
            target_categories: 분석할 카테고리 리스트 (없으면 기본 카테고리 사용)
            days: 분석 기간 (일 단위)

        Returns:
            카테고리별 성장률 분석 결과
        """
        logger.info(f"📊 카테고리 성장률 분석 시작 (분석 기간: {days}일)")

        try:
            # 1. 기본 카테고리 또는 사용자 지정 카테고리 설정
            if not target_categories:
                target_categories = self._get_trending_categories()

            # 2. 각 카테고리에 대한 성장률 및 시장 데이터 수집
            category_analyses = []

            for category in target_categories[:15]:  # 최대 15개 카테고리 분석
                logger.info(f"   📈 분석 중: {category}")

                # 카테고리 트렌드 데이터 수집
                trend_data = self.datalab_api.get_search_trends([category], days=days)
                trend_metrics = self.datalab_api.analyze_trend_metrics(trend_data, category)

                # 카테고리 시장 규모 추정 (상품 검색 결과 수 기반)
                market_size_data = await self._estimate_category_market_size(category)

                # 카테고리별 성장률 계산
                growth_analysis = self._calculate_category_growth_rate(
                    trend_metrics, market_size_data, category
                )

                category_analyses.append({
                    "category": category,
                    "growth_rate": growth_analysis["growth_rate"],
                    "growth_direction": trend_metrics["trend_direction"],
                    "trend_score": trend_metrics["trend_score"],
                    "market_size_score": market_size_data["market_size_score"],
                    "competition_density": market_size_data["competition_density"],
                    "entry_recommendation_score": growth_analysis["entry_score"],
                    "entry_difficulty": growth_analysis["entry_difficulty"],
                    "growth_momentum": growth_analysis["growth_momentum"],
                    "recommendation_reason": growth_analysis["reason"],
                    "market_indicators": {
                        "product_count": market_size_data["product_count"],
                        "avg_price": market_size_data["avg_price"],
                        "price_range": market_size_data["price_range"]
                    }
                })

                # API 제한 준수
                import time
                time.sleep(0.5)

            # 3. 카테고리별 성장률 순위 매기기
            category_analyses.sort(key=lambda x: x["growth_rate"], reverse=True)

            # 4. 상위 성장 카테고리 선별
            top_growth_categories = category_analyses[:10]

            # 5. 진입 추천도 기준 정렬
            recommended_categories = sorted(category_analyses,
                                          key=lambda x: x["entry_recommendation_score"],
                                          reverse=True)[:10]

            # 6. 종합 분석 결과 생성
            analysis_result = {
                "analysis_timestamp": datetime.now().isoformat(),
                "analysis_period_days": days,
                "total_categories_analyzed": len(category_analyses),

                # 성장률 기준 랭킹
                "top_growth_categories": top_growth_categories,

                # 진입 추천도 기준 랭킹
                "recommended_entry_categories": recommended_categories,

                # 전체 카테고리 데이터
                "all_category_data": category_analyses,

                # 분석 요약
                "analysis_summary": {
                    "high_growth_count": len([c for c in category_analyses if c["growth_rate"] >= 15.0]),
                    "rising_trend_count": len([c for c in category_analyses if c["growth_direction"] == "rising"]),
                    "high_opportunity_count": len([c for c in category_analyses if c["entry_recommendation_score"] >= 75]),
                    "avg_growth_rate": sum(c["growth_rate"] for c in category_analyses) / len(category_analyses) if category_analyses else 0,
                    "avg_entry_score": sum(c["entry_recommendation_score"] for c in category_analyses) / len(category_analyses) if category_analyses else 0
                }
            }

            logger.info(f"✅ 카테고리 성장률 분석 완료: {len(top_growth_categories)}개 고성장 카테고리 발견")
            return analysis_result

        except Exception as e:
            logger.error(f"❌ 카테고리 성장률 분석 중 오류: {str(e)}")
            return {
                "error": str(e),
                "analysis_timestamp": datetime.now().isoformat(),
                "top_growth_categories": [],
                "recommended_entry_categories": [],
                "analysis_summary": {}
            }

    def _get_trending_categories(self) -> List[str]:
        """
        트렌딩 카테고리 목록 생성
        현재 시장에서 주목받는 주요 카테고리들을 반환

        Returns:
            카테고리 키워드 리스트
        """
        trending_categories = [
            # 테크 & 가전
            "무선이어폰", "스마트워치", "노트북", "태블릿", "스마트폰액세서리",
            "로봇청소기", "공기청정기", "무선충전기", "블루투스스피커",

            # 홈 & 라이프스타일
            "홈인테리어", "캠핑용품", "운동기구", "요가매트", "베개",
            "수납용품", "주방용품", "텀블러", "향초", "화분",

            # 패션 & 뷰티
            "마스크팩", "선크림", "립스틱", "향수", "운동복",
            "슬리퍼", "백팩", "모자", "지갑", "시계",

            # 푸드 & 헬스
            "프로틴", "다이어트식품", "건강식품", "차", "원두커피",
            "간편식", "견과류", "비타민", "유산균",

            # 취미 & 여가
            "보드게임", "퍼즐", "아트용품", "독서대", "플래너",
            "키보드", "마우스", "게임패드", "헤드셋"
        ]

        return trending_categories

    async def _estimate_category_market_size(self, category: str) -> Dict[str, Any]:
        """
        카테고리 시장 규모 추정
        검색 결과 수와 가격 데이터를 기반으로 시장 크기와 경쟁 밀도 계산

        Args:
            category: 분석할 카테고리

        Returns:
            시장 규모 분석 결과
        """
        try:
            # 해당 카테고리 상품 검색
            search_results = self.shopping_api.search_products(category, display=100)

            if not search_results or not search_results.get('items'):
                return {
                    "market_size_score": 0,
                    "competition_density": "unknown",
                    "product_count": 0,
                    "avg_price": 0,
                    "price_range": {"min": 0, "max": 0}
                }

            items = search_results['items']
            product_count = len(items)

            # 가격 데이터 추출
            prices = []
            for item in items:
                price_str = item.get('lprice', '0')
                try:
                    price = int(price_str)
                    if price > 0:
                        prices.append(price)
                except:
                    continue

            if prices:
                avg_price = statistics.mean(prices)
                min_price = min(prices)
                max_price = max(prices)
            else:
                avg_price = min_price = max_price = 0

            # 시장 규모 점수 계산 (0-100)
            # 상품 수와 평균 가격을 고려한 복합 지표
            if product_count >= 80:
                size_factor = 100
            elif product_count >= 50:
                size_factor = 75
            elif product_count >= 20:
                size_factor = 50
            else:
                size_factor = 25

            # 평균 가격으로 시장 가치 보정
            if avg_price >= 100000:  # 10만원 이상
                price_factor = 1.3
            elif avg_price >= 50000:  # 5만원 이상
                price_factor = 1.1
            elif avg_price <= 10000:  # 1만원 이하
                price_factor = 0.8
            else:
                price_factor = 1.0

            market_size_score = min(100, size_factor * price_factor)

            # 경쟁 밀도 결정
            if product_count >= 70:
                competition_density = "high"
            elif product_count >= 30:
                competition_density = "medium"
            else:
                competition_density = "low"

            return {
                "market_size_score": round(market_size_score, 1),
                "competition_density": competition_density,
                "product_count": product_count,
                "avg_price": round(avg_price),
                "price_range": {
                    "min": min_price,
                    "max": max_price
                }
            }

        except Exception as e:
            logger.error(f"시장 규모 추정 중 오류: {str(e)}")
            return {
                "market_size_score": 0,
                "competition_density": "unknown",
                "product_count": 0,
                "avg_price": 0,
                "price_range": {"min": 0, "max": 0}
            }

    def _calculate_category_growth_rate(self, trend_metrics: Dict, market_size_data: Dict, category: str) -> Dict[str, Any]:
        """
        카테고리 성장률 및 진입 추천도 계산

        Args:
            trend_metrics: 트렌드 분석 결과
            market_size_data: 시장 규모 데이터
            category: 카테고리명

        Returns:
            성장률 분석 결과
        """
        try:
            # 1. 기본 성장률 계산 (트렌드 변화율 기반)
            trend_change = trend_metrics.get("trend_change_percent", 0)
            trend_score = trend_metrics.get("trend_score", 0)

            # 성장률 = 트렌드 변화율 + 트렌드 점수 가중치
            base_growth_rate = trend_change + (trend_score / 10)

            # 2. 시장 규모로 성장률 보정
            market_size_score = market_size_data.get("market_size_score", 0)
            if market_size_score >= 80:
                size_multiplier = 1.2  # 큰 시장은 성장률 가중
            elif market_size_score <= 30:
                size_multiplier = 0.8  # 작은 시장은 성장률 할인
            else:
                size_multiplier = 1.0

            growth_rate = base_growth_rate * size_multiplier

            # 3. 성장 모멘텀 계산
            trend_direction = trend_metrics.get("trend_direction", "stable")
            if trend_direction == "rising":
                if trend_change > 20:
                    momentum = "매우높음"
                elif trend_change > 10:
                    momentum = "높음"
                else:
                    momentum = "중간"
            elif trend_direction == "stable":
                momentum = "안정"
            else:
                momentum = "하락"

            # 4. 진입 추천도 점수 계산 (0-100)
            # 성장률 점수 (0-40점)
            growth_score = min(40, max(0, growth_rate * 2))

            # 시장 규모 점수 (0-30점)
            size_score = market_size_score * 0.3

            # 경쟁도 점수 (0-30점) - 경쟁이 낮을수록 높은 점수
            competition_density = market_size_data.get("competition_density", "medium")
            if competition_density == "low":
                competition_score = 30
            elif competition_density == "medium":
                competition_score = 20
            else:
                competition_score = 10

            entry_score = growth_score + size_score + competition_score

            # 5. 진입 난이도 결정
            if entry_score >= 80:
                entry_difficulty = "쉬움"
            elif entry_score >= 60:
                entry_difficulty = "보통"
            elif entry_score >= 40:
                entry_difficulty = "어려움"
            else:
                entry_difficulty = "매우어려움"

            # 6. 추천 이유 생성
            reasons = []
            if growth_rate >= 15:
                reasons.append(f"높은 성장률 ({growth_rate:.1f}%)")
            if momentum in ["높음", "매우높음"]:
                reasons.append(f"강한 성장 모멘텀")
            if competition_density == "low":
                reasons.append("낮은 경쟁 밀도")
            if market_size_score >= 70:
                reasons.append("충분한 시장 규모")

            recommendation_reason = ", ".join(reasons) if reasons else "안정적 시장"

            return {
                "growth_rate": round(growth_rate, 1),
                "growth_momentum": momentum,
                "entry_score": round(entry_score, 1),
                "entry_difficulty": entry_difficulty,
                "reason": recommendation_reason
            }

        except Exception as e:
            logger.error(f"성장률 계산 중 오류: {str(e)}")
            return {
                "growth_rate": 0,
                "growth_momentum": "알 수 없음",
                "entry_score": 0,
                "entry_difficulty": "알 수 없음",
                "reason": "분석 오류"
            }

    async def analyze_brand_gap_opportunities(self, keyword: str, max_products: int = 100) -> Dict[str, Any]:
        """
        브랜드 갭 분석 - Phase 2.1 구현
        시장에서 브랜드별 점유율을 분석하고 기회 영역을 탐지

        Args:
            keyword: 분석할 키워드
            max_products: 분석할 최대 상품 수

        Returns:
            브랜드 갭 분석 결과
        """
        logger.info(f"🏷️ 브랜드 갭 분석 시작: '{keyword}'")

        try:
            # 1. 키워드 관련 상품 데이터 수집
            search_results = self.shopping_api.search_products(keyword, display=max_products)

            if not search_results or not search_results.get('items'):
                return {
                    "keyword": keyword,
                    "error": "상품 데이터 없음",
                    "brand_analysis": {},
                    "gap_opportunities": [],
                    "analysis_summary": {}
                }

            # 2. 브랜드 데이터 추출 및 정규화
            brand_data = self._extract_brand_data(search_results['items'])

            # 3. 브랜드별 시장 점유율 계산
            brand_market_share = self._calculate_brand_market_share(brand_data)

            # 4. 브랜드 갭 기회 탐지
            gap_opportunities = self._detect_brand_gaps(brand_market_share, keyword)

            # 5. 브랜드 경쟁 강도 분석
            brand_competition_analysis = self._analyze_brand_competition_intensity(brand_market_share)

            # 6. 종합 분석 결과
            analysis_result = {
                "keyword": keyword,
                "analysis_timestamp": datetime.now().isoformat(),
                "total_products_analyzed": len(search_results['items']),
                "unique_brands_found": len(brand_market_share),

                # 브랜드 시장 점유율 (상위 15개)
                "brand_market_share": sorted(brand_market_share,
                                           key=lambda x: x["market_share"], reverse=True)[:15],

                # 브랜드 갭 기회
                "gap_opportunities": gap_opportunities,

                # 브랜드 경쟁 분석
                "brand_competition_analysis": brand_competition_analysis,

                # 분석 요약
                "analysis_summary": {
                    "market_concentration": self._calculate_market_concentration(brand_market_share),
                    "top_3_market_share": sum(b["market_share"] for b in sorted(brand_market_share,
                                            key=lambda x: x["market_share"], reverse=True)[:3]),
                    "brand_diversity_score": len(brand_market_share),
                    "gap_opportunity_count": len([g for g in gap_opportunities if g["opportunity_score"] >= 70]),
                    "average_brand_strength": sum(b.get("brand_strength", 0) for b in brand_market_share) / len(brand_market_share) if brand_market_share else 0
                }
            }

            logger.info(f"✅ 브랜드 갭 분석 완료: {len(gap_opportunities)}개 기회 발견")
            return analysis_result

        except Exception as e:
            logger.error(f"❌ 브랜드 갭 분석 중 오류: {str(e)}")
            return {
                "keyword": keyword,
                "error": str(e),
                "brand_analysis": {},
                "gap_opportunities": [],
                "analysis_summary": {}
            }

    def _extract_brand_data(self, items: List[Dict]) -> List[Dict[str, Any]]:
        """
        상품 데이터에서 브랜드 정보 추출 및 정규화

        Args:
            items: 네이버 쇼핑 API 상품 리스트

        Returns:
            정규화된 브랜드 데이터
        """
        brand_products = {}

        for item in items:
            # 브랜드명 추출 (brand 필드가 없으면 maker에서 추출)
            brand_name = item.get('brand', '').strip()
            if not brand_name:
                brand_name = item.get('maker', '').strip()
            if not brand_name:
                # 상품명에서 브랜드 추출 시도
                brand_name = self._extract_brand_from_title(item.get('title', ''))

            # 브랜드명 정규화
            normalized_brand = self._normalize_brand_name(brand_name)

            if not normalized_brand or normalized_brand == "알 수 없음":
                normalized_brand = "기타/무브랜드"

            # 가격 정보 추출
            price = 0
            try:
                price = int(item.get('lprice', 0))
            except:
                price = 0

            # 브랜드별 상품 데이터 집계
            if normalized_brand not in brand_products:
                brand_products[normalized_brand] = {
                    "brand": normalized_brand,
                    "product_count": 0,
                    "total_price": 0,
                    "prices": [],
                    "products": []
                }

            brand_products[normalized_brand]["product_count"] += 1
            brand_products[normalized_brand]["total_price"] += price
            brand_products[normalized_brand]["prices"].append(price)
            brand_products[normalized_brand]["products"].append({
                "title": item.get('title', ''),
                "price": price,
                "link": item.get('link', ''),
                "image": item.get('image', '')
            })

        return list(brand_products.values())

    def _normalize_brand_name(self, brand_name: str) -> str:
        """
        브랜드명 정규화

        Args:
            brand_name: 원본 브랜드명

        Returns:
            정규화된 브랜드명
        """
        if not brand_name or len(brand_name.strip()) < 1:
            return "알 수 없음"

        brand = brand_name.strip().upper()

        # 잘알려진 브랜드 정규화 매핑
        brand_mapping = {
            # 테크 브랜드
            "APPLE": "Apple", "SAMSUNG": "Samsung", "LG": "LG",
            "SONY": "Sony", "LOGITECH": "Logitech", "HP": "HP",

            # 패션 브랜드
            "NIKE": "Nike", "ADIDAS": "Adidas", "UNIQLO": "Uniqlo",

            # 화장품 브랜드
            "INNISFREE": "Innisfree", "THEFACESHOP": "The Face Shop",

            # 기타
            "IKEA": "IKEA", "MUJI": "MUJI"
        }

        for key, value in brand_mapping.items():
            if key in brand:
                return value

        # 기본 정규화 (첫 글자 대문자)
        return brand_name.strip().title()

    def _extract_brand_from_title(self, title: str) -> str:
        """
        상품명에서 브랜드명 추출 시도

        Args:
            title: 상품명

        Returns:
            추출된 브랜드명 (또는 빈 문자열)
        """
        if not title:
            return ""

        # 흔한 브랜드 패턴 검색
        common_brands = [
            "삼성", "LG", "Apple", "Sony", "Nike", "Adidas",
            "이케아", "무지", "유니클로", "자라", "H&M"
        ]

        title_upper = title.upper()
        for brand in common_brands:
            if brand.upper() in title_upper:
                return brand

        # 대괄호 안의 브랜드명 추출
        import re
        bracket_match = re.search(r'\[([^\]]+)\]', title)
        if bracket_match:
            potential_brand = bracket_match.group(1).strip()
            if len(potential_brand) <= 20:  # 너무 긴 경우 제외
                return potential_brand

        return ""

    def _calculate_brand_market_share(self, brand_data: List[Dict]) -> List[Dict[str, Any]]:
        """
        브랜드별 시장 점유율 계산

        Args:
            brand_data: 브랜드 데이터 리스트

        Returns:
            시장 점유율이 포함된 브랜드 분석 결과
        """
        total_products = sum(b["product_count"] for b in brand_data)

        enhanced_brand_data = []
        for brand_info in brand_data:
            product_count = brand_info["product_count"]
            prices = brand_info["prices"]

            # 시장 점유율 계산
            market_share = (product_count / total_products) * 100 if total_products > 0 else 0

            # 평균 가격 계산
            avg_price = sum(prices) / len(prices) if prices else 0

            # 가격 범위
            price_range = {
                "min": min(prices) if prices else 0,
                "max": max(prices) if prices else 0
            }

            # 브랜드 강도 점수 계산 (시장점유율 + 가격 포지셔닝)
            brand_strength = self._calculate_brand_strength(market_share, avg_price, product_count)

            enhanced_brand_data.append({
                "brand": brand_info["brand"],
                "product_count": product_count,
                "market_share": round(market_share, 2),
                "avg_price": round(avg_price),
                "price_range": price_range,
                "brand_strength": brand_strength,
                "products": brand_info["products"][:3]  # 상위 3개 상품만 포함
            })

        return enhanced_brand_data

    def _calculate_brand_strength(self, market_share: float, avg_price: float, product_count: int) -> float:
        """
        브랜드 강도 점수 계산

        Args:
            market_share: 시장 점유율
            avg_price: 평균 가격
            product_count: 상품 수

        Returns:
            브랜드 강도 점수 (0-100)
        """
        # 시장 점유율 점수 (0-40)
        share_score = min(40, market_share * 2)

        # 제품 다양성 점수 (0-30)
        diversity_score = min(30, product_count * 3)

        # 가격 포지셔닝 점수 (0-30)
        # 중간 가격대가 높은 점수 (너무 싸거나 비싸지 않은)
        if 10000 <= avg_price <= 100000:
            price_score = 30
        elif 5000 <= avg_price <= 200000:
            price_score = 20
        else:
            price_score = 10

        total_score = share_score + diversity_score + price_score
        return round(min(100, total_score), 1)

    def _detect_brand_gaps(self, brand_market_share: List[Dict], keyword: str) -> List[Dict[str, Any]]:
        """
        브랜드 갭 기회 탐지

        Args:
            brand_market_share: 브랜드 시장 점유율 데이터
            keyword: 분석 키워드

        Returns:
            브랜드 갭 기회 리스트
        """
        gaps = []

        # 1. 시장 집중도 분석
        total_brands = len(brand_market_share)
        top_3_share = sum(b["market_share"] for b in sorted(brand_market_share,
                         key=lambda x: x["market_share"], reverse=True)[:3])

        # 2. 가격대별 갭 분석
        price_gaps = self._analyze_price_segment_gaps(brand_market_share)

        # 3. 시장 점유율 갭 분석
        share_gaps = self._analyze_market_share_gaps(brand_market_share)

        # 4. 종합 기회 탐지
        if top_3_share < 60:  # 시장이 분산되어 있으면 기회
            gaps.append({
                "gap_type": "분산형 시장",
                "opportunity_score": 85,
                "description": "상위 3개 브랜드 점유율이 낮아 신규 진입 기회가 높습니다",
                "recommendation": "차별화된 브랜드 포지셔닝으로 시장 진입 추천",
                "target_segment": "전체 시장",
                "expected_share": f"{(100 - top_3_share) / 4:.1f}%"
            })

        # 5. 가격대별 기회 추가
        for price_gap in price_gaps:
            if price_gap["opportunity_score"] >= 60:
                gaps.append(price_gap)

        # 6. 시장 점유율 기반 기회 추가
        for share_gap in share_gaps:
            if share_gap["opportunity_score"] >= 65:
                gaps.append(share_gap)

        # 기회 점수 순으로 정렬하여 상위 5개만 반환
        return sorted(gaps, key=lambda x: x["opportunity_score"], reverse=True)[:5]

    def _analyze_price_segment_gaps(self, brand_data: List[Dict]) -> List[Dict[str, Any]]:
        """가격대별 브랜드 갭 분석"""
        price_segments = {
            "저가": (0, 30000),
            "중저가": (30000, 80000),
            "중고가": (80000, 200000),
            "고가": (200000, float('inf'))
        }

        segment_analysis = {}
        for segment_name, (min_price, max_price) in price_segments.items():
            brands_in_segment = [b for b in brand_data
                               if min_price <= b["avg_price"] < max_price]
            segment_analysis[segment_name] = {
                "brand_count": len(brands_in_segment),
                "total_share": sum(b["market_share"] for b in brands_in_segment),
                "avg_strength": sum(b["brand_strength"] for b in brands_in_segment) / len(brands_in_segment) if brands_in_segment else 0
            }

        gaps = []
        for segment, data in segment_analysis.items():
            if data["brand_count"] <= 2 and data["total_share"] < 40:
                opportunity_score = 75 + (40 - data["total_share"])
                gaps.append({
                    "gap_type": f"{segment} 가격대 진입 기회",
                    "opportunity_score": min(100, opportunity_score),
                    "description": f"{segment} 가격대에 강력한 브랜드가 부족합니다",
                    "recommendation": f"{segment} 가격 포지셔닝으로 브랜드 진입 추천",
                    "target_segment": segment,
                    "expected_share": f"{max(5, (40 - data['total_share']) / 2):.1f}%"
                })

        return gaps

    def _analyze_market_share_gaps(self, brand_data: List[Dict]) -> List[Dict[str, Any]]:
        """시장 점유율 기반 갭 분석"""
        gaps = []

        # 시장 점유율별 정렬
        sorted_brands = sorted(brand_data, key=lambda x: x["market_share"], reverse=True)

        # 1위와 2위 사이 격차가 크면 2위 도전 기회
        if len(sorted_brands) >= 2:
            gap_between_top2 = sorted_brands[0]["market_share"] - sorted_brands[1]["market_share"]
            if gap_between_top2 > 15:
                gaps.append({
                    "gap_type": "2위 브랜드 도전 기회",
                    "opportunity_score": 70,
                    "description": f"1위({sorted_brands[0]['brand']})와 2위 브랜드 간 {gap_between_top2:.1f}% 격차 존재",
                    "recommendation": f"{sorted_brands[1]['market_share']:.1f}% 이상 점유율 목표로 진입",
                    "target_segment": "2위 브랜드 추격",
                    "expected_share": f"{sorted_brands[1]['market_share'] + 3:.1f}%"
                })

        # 꼬리 브랜드들이 많으면 통합 기회
        small_brands = [b for b in brand_data if b["market_share"] < 5]
        if len(small_brands) >= 5:
            total_small_share = sum(b["market_share"] for b in small_brands)
            gaps.append({
                "gap_type": "소형 브랜드 통합 기회",
                "opportunity_score": 65,
                "description": f"{len(small_brands)}개 소형 브랜드가 {total_small_share:.1f}% 점유",
                "recommendation": "소형 브랜드들을 통합하는 강력한 브랜드 론칭",
                "target_segment": "소형 브랜드 시장",
                "expected_share": f"{total_small_share / 3:.1f}%"
            })

        return gaps

    def _analyze_brand_competition_intensity(self, brand_data: List[Dict]) -> Dict[str, Any]:
        """브랜드 경쟁 강도 분석"""
        if not brand_data:
            return {"intensity": "알 수 없음", "score": 0}

        # HHI (허핀달-허쉬만 지수) 계산
        hhi = sum((b["market_share"] / 100) ** 2 for b in brand_data) * 10000

        # 경쟁 강도 분류
        if hhi < 1000:
            intensity = "높은 경쟁"
            competition_level = "매우 치열"
        elif hhi < 1800:
            intensity = "보통 경쟁"
            competition_level = "치열"
        else:
            intensity = "낮은 경쟁"
            competition_level = "안정적"

        return {
            "intensity": intensity,
            "competition_level": competition_level,
            "hhi_score": round(hhi, 1),
            "market_concentration": "높음" if hhi > 2500 else ("보통" if hhi > 1500 else "낮음"),
            "entry_barrier": "높음" if hhi > 2000 else ("보통" if hhi > 1200 else "낮음")
        }

    def _calculate_market_concentration(self, brand_data: List[Dict]) -> str:
        """시장 집중도 계산"""
        if not brand_data:
            return "알 수 없음"

        sorted_brands = sorted(brand_data, key=lambda x: x["market_share"], reverse=True)
        top_4_share = sum(b["market_share"] for b in sorted_brands[:4])

        if top_4_share >= 80:
            return "높은 집중도"
        elif top_4_share >= 60:
            return "보통 집중도"
        else:
            return "낮은 집중도"

    async def analyze_channel_strategy_opportunities(self, keyword: str, max_products: int = 100) -> Dict[str, Any]:
        """
        채널별 판매 전략 분석 - 가격대별, 플랫폼별 기회 분석

        Args:
            keyword: 검색 키워드
            max_products: 분석할 최대 상품 수

        Returns:
            채널 전략 분석 결과
        """
        try:
            logger.info(f"채널 전략 분석 시작: {keyword}")

            # 1. 기본 상품 데이터 수집
            products = await self.search_products(keyword, display=max_products)
            if not products or len(products) < 10:
                logger.warning(f"충분한 상품 데이터가 없습니다: {len(products) if products else 0}개")
                return self._get_empty_channel_analysis(keyword)

            # 2. 채널별 데이터 분석
            channel_analysis = self._analyze_sales_channels(products)

            # 3. 가격대별 전략 분석
            price_strategy = self._analyze_price_tier_strategy(products)

            # 4. 시장 진입 기회 분석
            market_opportunities = self._identify_channel_opportunities(products, channel_analysis, price_strategy)

            # 5. 채널별 경쟁 강도 분석
            competition_analysis = self._analyze_channel_competition(products)

            return {
                "keyword": keyword,
                "total_products_analyzed": len(products),
                "channel_analysis": channel_analysis,
                "price_strategy": price_strategy,
                "market_opportunities": market_opportunities,
                "competition_analysis": competition_analysis,
                "analysis_summary": self._generate_channel_summary(channel_analysis, price_strategy, market_opportunities),
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"채널 전략 분석 중 오류 발생: {str(e)}")
            return self._get_empty_channel_analysis(keyword, str(e))

    def _analyze_sales_channels(self, products: List[Dict]) -> Dict[str, Any]:
        """판매 채널 분석"""
        channel_data = {}
        total_products = len(products)

        for product in products:
            # 쇼핑몰 정보 추출
            mall_name = product.get('mallName', '기타').strip()
            price = int(product.get('lprice', 0))

            if mall_name not in channel_data:
                channel_data[mall_name] = {
                    'mall_name': mall_name,
                    'product_count': 0,
                    'total_price': 0,
                    'prices': [],
                    'avg_price': 0,
                    'market_share': 0,
                    'price_range': {'min': float('inf'), 'max': 0}
                }

            channel_data[mall_name]['product_count'] += 1
            channel_data[mall_name]['total_price'] += price
            channel_data[mall_name]['prices'].append(price)

            # 가격 범위 업데이트
            if price > 0:
                channel_data[mall_name]['price_range']['min'] = min(
                    channel_data[mall_name]['price_range']['min'], price
                )
                channel_data[mall_name]['price_range']['max'] = max(
                    channel_data[mall_name]['price_range']['max'], price
                )

        # 통계 계산
        for mall_name, data in channel_data.items():
            if data['prices']:
                data['avg_price'] = data['total_price'] / len(data['prices'])
                data['market_share'] = (data['product_count'] / total_products) * 100

                if data['price_range']['min'] == float('inf'):
                    data['price_range']['min'] = 0

        # 상위 채널 정렬
        sorted_channels = sorted(
            channel_data.values(),
            key=lambda x: x['market_share'],
            reverse=True
        )

        return {
            'channels': sorted_channels[:15],  # 상위 15개 채널
            'total_channels': len(channel_data),
            'channel_diversity_index': self._calculate_channel_diversity(sorted_channels)
        }

    def _analyze_price_tier_strategy(self, products: List[Dict]) -> Dict[str, Any]:
        """가격대별 전략 분석"""
        prices = [int(p.get('lprice', 0)) for p in products if int(p.get('lprice', 0)) > 0]

        if not prices:
            return {'error': '가격 데이터가 부족합니다'}

        prices.sort()
        total_products = len(prices)

        # 가격대 구분 (사분위수 기준)
        q1_idx = total_products // 4
        q2_idx = total_products // 2
        q3_idx = (total_products * 3) // 4

        price_tiers = {
            'budget': {'min': prices[0], 'max': prices[q1_idx], 'products': []},
            'mid_range': {'min': prices[q1_idx], 'max': prices[q2_idx], 'products': []},
            'premium': {'min': prices[q2_idx], 'max': prices[q3_idx], 'products': []},
            'luxury': {'min': prices[q3_idx], 'max': prices[-1], 'products': []}
        }

        # 각 가격대별 상품 분류
        for product in products:
            price = int(product.get('lprice', 0))
            if price == 0:
                continue

            if price <= price_tiers['budget']['max']:
                price_tiers['budget']['products'].append(product)
            elif price <= price_tiers['mid_range']['max']:
                price_tiers['mid_range']['products'].append(product)
            elif price <= price_tiers['premium']['max']:
                price_tiers['premium']['products'].append(product)
            else:
                price_tiers['luxury']['products'].append(product)

        # 각 티어별 통계 계산
        tier_stats = {}
        for tier_name, tier_data in price_tiers.items():
            tier_products = tier_data['products']
            tier_stats[tier_name] = {
                'price_range': f"{tier_data['min']:,}원 - {tier_data['max']:,}원",
                'product_count': len(tier_products),
                'market_share': (len(tier_products) / total_products) * 100,
                'avg_price': sum(int(p.get('lprice', 0)) for p in tier_products) / len(tier_products) if tier_products else 0,
                'competition_level': self._assess_tier_competition(tier_products)
            }

        return {
            'price_tiers': tier_stats,
            'market_gaps': self._identify_price_gaps(prices),
            'optimal_pricing': self._suggest_optimal_pricing(tier_stats)
        }

    def _identify_channel_opportunities(self, products: List[Dict], channel_analysis: Dict, price_strategy: Dict) -> List[Dict[str, Any]]:
        """채널별 기회 분석"""
        opportunities = []

        channels = channel_analysis.get('channels', [])
        if not channels:
            return opportunities

        # 1. 저점유율 높은수익성 채널 기회
        for channel in channels:
            if channel['market_share'] < 5 and channel['avg_price'] > 0:
                opportunity_score = self._calculate_channel_opportunity_score(channel, channels)
                if opportunity_score > 60:
                    opportunities.append({
                        'type': '틈새 채널 진입',
                        'channel': channel['mall_name'],
                        'market_share': channel['market_share'],
                        'avg_price': channel['avg_price'],
                        'opportunity_score': opportunity_score,
                        'reasoning': f"낮은 경쟁({channel['market_share']:.1f}% 점유율)과 적정 가격대 유지"
                    })

        # 2. 가격대별 기회
        price_tiers = price_strategy.get('price_tiers', {})
        for tier_name, tier_data in price_tiers.items():
            if tier_data['market_share'] < 20:  # 점유율 20% 미만인 가격대
                opportunities.append({
                    'type': '가격대 진입 기회',
                    'tier': tier_name,
                    'price_range': tier_data['price_range'],
                    'market_share': tier_data['market_share'],
                    'opportunity_score': 100 - tier_data['market_share'],
                    'reasoning': f"{tier_name.replace('_', ' ').title()} 가격대 저경쟁 구간"
                })

        # 기회 점수순으로 정렬
        opportunities.sort(key=lambda x: x['opportunity_score'], reverse=True)
        return opportunities[:10]  # 상위 10개 기회

    def _analyze_channel_competition(self, products: List[Dict]) -> Dict[str, Any]:
        """채널별 경쟁 강도 분석"""
        mall_competition = {}

        for product in products:
            mall_name = product.get('mallName', '기타').strip()
            if mall_name not in mall_competition:
                mall_competition[mall_name] = {'products': [], 'brands': set()}

            mall_competition[mall_name]['products'].append(product)
            brand = product.get('brand', product.get('maker', '알 수 없음'))
            mall_competition[mall_name]['brands'].add(brand)

        competition_levels = {}
        for mall_name, data in mall_competition.items():
            product_count = len(data['products'])
            brand_count = len(data['brands'])

            # 경쟁 강도 계산 (상품 수 대비 브랜드 다양성)
            competition_intensity = (product_count / max(brand_count, 1)) * 10

            if competition_intensity > 50:
                level = "매우 높음"
            elif competition_intensity > 30:
                level = "높음"
            elif competition_intensity > 15:
                level = "보통"
            else:
                level = "낮음"

            competition_levels[mall_name] = {
                'mall_name': mall_name,
                'competition_level': level,
                'competition_score': min(competition_intensity, 100),
                'product_count': product_count,
                'brand_count': brand_count
            }

        # 경쟁 강도순으로 정렬
        sorted_competition = sorted(
            competition_levels.values(),
            key=lambda x: x['competition_score'],
            reverse=True
        )

        return {
            'channel_competition': sorted_competition,
            'avg_competition_score': sum(c['competition_score'] for c in sorted_competition) / len(sorted_competition) if sorted_competition else 0
        }

    def _calculate_channel_diversity(self, channels: List[Dict]) -> float:
        """채널 다양성 지수 계산 (Shannon Diversity Index)"""
        if not channels:
            return 0

        total_products = sum(c['product_count'] for c in channels)
        if total_products == 0:
            return 0

        diversity = 0
        for channel in channels:
            if channel['product_count'] > 0:
                proportion = channel['product_count'] / total_products
                diversity -= proportion * math.log(proportion)

        return round(diversity, 3)

    def _assess_tier_competition(self, tier_products: List[Dict]) -> str:
        """가격대별 경쟁 수준 평가"""
        if not tier_products:
            return "정보 없음"

        brands = set()
        for product in tier_products:
            brand = product.get('brand', product.get('maker', '알 수 없음'))
            brands.add(brand)

        product_per_brand = len(tier_products) / len(brands) if brands else 0

        if product_per_brand > 5:
            return "높은 경쟁"
        elif product_per_brand > 3:
            return "보통 경쟁"
        else:
            return "낮은 경쟁"

    def _identify_price_gaps(self, sorted_prices: List[int]) -> List[Dict]:
        """가격대 공백 구간 식별"""
        gaps = []

        for i in range(len(sorted_prices) - 1):
            current_price = sorted_prices[i]
            next_price = sorted_prices[i + 1]
            gap_size = next_price - current_price

            # 가격 차이가 30% 이상인 구간을 공백으로 판단
            if gap_size > current_price * 0.3 and gap_size > 10000:
                gaps.append({
                    'start_price': current_price,
                    'end_price': next_price,
                    'gap_size': gap_size,
                    'opportunity_score': min(gap_size / 1000, 100)
                })

        return sorted(gaps, key=lambda x: x['opportunity_score'], reverse=True)[:5]

    def _suggest_optimal_pricing(self, tier_stats: Dict) -> Dict[str, Any]:
        """최적 가격 제안"""
        suggestions = {}

        for tier_name, stats in tier_stats.items():
            if stats['market_share'] < 25:  # 점유율 25% 미만인 구간
                suggestions[tier_name] = {
                    'recommended': True,
                    'avg_price': stats['avg_price'],
                    'market_share': stats['market_share'],
                    'reason': f"낮은 시장 점유율로 진입 기회 존재"
                }

        return suggestions

    def _calculate_channel_opportunity_score(self, channel: Dict, all_channels: List[Dict]) -> float:
        """채널별 기회 점수 계산"""
        # 기본 점수 (낮은 점유율일수록 높은 점수)
        market_share_score = max(0, 100 - channel['market_share'] * 2)

        # 평균 가격 점수 (너무 낮지 않은 가격대 선호)
        avg_all_prices = sum(c['avg_price'] for c in all_channels) / len(all_channels)
        price_ratio = channel['avg_price'] / avg_all_prices if avg_all_prices > 0 else 0
        price_score = min(100, price_ratio * 50)

        # 종합 점수
        total_score = (market_share_score * 0.6) + (price_score * 0.4)
        return round(total_score, 1)

    def _generate_channel_summary(self, channel_analysis: Dict, price_strategy: Dict, opportunities: List[Dict]) -> Dict[str, Any]:
        """채널 전략 분석 요약"""
        channels = channel_analysis.get('channels', [])
        top_channel = channels[0] if channels else None

        return {
            'total_channels': channel_analysis.get('total_channels', 0),
            'dominant_channel': {
                'name': top_channel['mall_name'] if top_channel else 'N/A',
                'share': top_channel['market_share'] if top_channel else 0
            },
            'channel_diversity': channel_analysis.get('channel_diversity_index', 0),
            'top_opportunities': len(opportunities),
            'price_tier_analysis': {
                'most_competitive': self._find_most_competitive_tier(price_strategy),
                'best_opportunity': self._find_best_price_opportunity(price_strategy)
            }
        }

    def _find_most_competitive_tier(self, price_strategy: Dict) -> str:
        """가장 경쟁이 치열한 가격대 찾기"""
        tiers = price_strategy.get('price_tiers', {})
        max_share = 0
        most_competitive = 'N/A'

        for tier_name, tier_data in tiers.items():
            if tier_data['market_share'] > max_share:
                max_share = tier_data['market_share']
                most_competitive = tier_name

        return most_competitive.replace('_', ' ').title()

    def _find_best_price_opportunity(self, price_strategy: Dict) -> str:
        """최고의 가격대 기회 찾기"""
        tiers = price_strategy.get('price_tiers', {})
        min_share = 100
        best_opportunity = 'N/A'

        for tier_name, tier_data in tiers.items():
            if tier_data['market_share'] < min_share and tier_data['market_share'] > 0:
                min_share = tier_data['market_share']
                best_opportunity = tier_name

        return best_opportunity.replace('_', ' ').title()

    def _get_empty_channel_analysis(self, keyword: str, error: str = None) -> Dict[str, Any]:
        """빈 채널 분석 결과 반환"""
        return {
            "keyword": keyword,
            "error": error,
            "total_products_analyzed": 0,
            "channel_analysis": {"channels": [], "total_channels": 0, "channel_diversity_index": 0},
            "price_strategy": {"price_tiers": {}, "market_gaps": [], "optimal_pricing": {}},
            "market_opportunities": [],
            "competition_analysis": {"channel_competition": [], "avg_competition_score": 0},
            "analysis_summary": {},
            "timestamp": datetime.now().isoformat()
        }

    async def analyze_trend_changes(self, keywords: List[str], monitoring_period: int = 7) -> Dict[str, Any]:
        """
        트렌드 급변 감지 분석 - 키워드별 트렌드 변화량 모니터링

        Args:
            keywords: 모니터링할 키워드 리스트
            monitoring_period: 모니터링 기간 (일)

        Returns:
            트렌드 변화 분석 결과
        """
        try:
            logger.info(f"트렌드 변화 감지 시작: {len(keywords)}개 키워드")

            trend_changes = []
            significant_changes = []

            for keyword in keywords:
                try:
                    # 현재와 과거 트렌드 데이터 비교
                    current_trend = await self._get_current_trend_data(keyword)
                    past_trend = await self._get_past_trend_data(keyword, monitoring_period)

                    # 변화율 계산
                    change_analysis = self._calculate_trend_change(keyword, current_trend, past_trend)
                    trend_changes.append(change_analysis)

                    # 유의미한 변화 감지 (±30% 이상 변화)
                    if abs(change_analysis['change_percentage']) >= 30:
                        significant_changes.append(change_analysis)

                except Exception as keyword_error:
                    logger.warning(f"키워드 {keyword} 트렌드 분석 실패: {keyword_error}")
                    continue

            # 급변 키워드 정렬
            rising_trends = [t for t in significant_changes if t['change_percentage'] > 0]
            falling_trends = [t for t in significant_changes if t['change_percentage'] < 0]

            rising_trends.sort(key=lambda x: x['change_percentage'], reverse=True)
            falling_trends.sort(key=lambda x: x['change_percentage'])

            return {
                "monitoring_period": monitoring_period,
                "total_keywords_analyzed": len(keywords),
                "significant_changes_count": len(significant_changes),
                "trend_changes": trend_changes,
                "rising_trends": rising_trends[:10],  # 상위 10개 급상승
                "falling_trends": falling_trends[:10],  # 상위 10개 급하락
                "analysis_summary": {
                    "most_rising_keyword": rising_trends[0]['keyword'] if rising_trends else None,
                    "most_falling_keyword": falling_trends[0]['keyword'] if falling_trends else None,
                    "average_change": sum(t['change_percentage'] for t in trend_changes) / len(trend_changes) if trend_changes else 0,
                    "volatility_index": self._calculate_market_volatility(trend_changes)
                },
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"트렌드 변화 감지 중 오류: {str(e)}")
            return self._get_empty_trend_change_analysis(keywords)

    async def monitor_competitors(self, base_keyword: str, competitor_products: List[Dict] = None) -> Dict[str, Any]:
        """
        경쟁사 동향 모니터링 - 가격 변화, 신규 진입자, 점유율 변화 추적

        Args:
            base_keyword: 기준 키워드
            competitor_products: 기존 경쟁 상품 리스트 (비교용)

        Returns:
            경쟁사 모니터링 결과
        """
        try:
            logger.info(f"경쟁사 모니터링 시작: {base_keyword}")

            # 현재 시장 상황 분석
            current_products = await self.search_products(base_keyword, display=100)
            if not current_products:
                return self._get_empty_competitor_analysis(base_keyword)

            # 경쟁사 변화 분석
            competitor_changes = self._analyze_competitor_changes(current_products, competitor_products)

            # 가격 변화 추적
            price_changes = self._track_price_changes(current_products, competitor_products)

            # 신규 진입자 감지
            new_entrants = self._detect_new_entrants(current_products, competitor_products)

            # 시장 점유율 변화
            market_share_changes = self._track_market_share_changes(current_products, competitor_products)

            # 경쟁 강도 변화
            competition_intensity = self._calculate_competition_intensity_change(current_products, competitor_products)

            return {
                "keyword": base_keyword,
                "monitoring_timestamp": datetime.now().isoformat(),
                "total_competitors": len(current_products),
                "competitor_changes": competitor_changes,
                "price_changes": price_changes,
                "new_entrants": new_entrants,
                "market_share_changes": market_share_changes,
                "competition_intensity": competition_intensity,
                "alerts": self._generate_competitor_alerts(competitor_changes, price_changes, new_entrants),
                "analysis_summary": {
                    "significant_price_changes": len([p for p in price_changes if abs(p.get('change_percentage', 0)) > 10]),
                    "new_entrants_count": len(new_entrants),
                    "market_volatility": self._assess_market_volatility(current_products),
                    "competition_trend": "증가" if competition_intensity.get('intensity_change', 0) > 0 else "감소"
                }
            }

        except Exception as e:
            logger.error(f"경쟁사 모니터링 중 오류: {str(e)}")
            return self._get_empty_competitor_analysis(base_keyword, str(e))

    async def _get_current_trend_data(self, keyword: str) -> Dict[str, Any]:
        """현재 트렌드 데이터 수집"""
        try:
            if self.datalab_api:
                # 최근 7일 트렌드 데이터
                trend_data = await self.datalab_api.get_trend_data([keyword], period="7d")
                if trend_data and keyword in trend_data:
                    recent_values = trend_data[keyword][-7:]  # 최근 7일
                    return {
                        'average_trend': sum(recent_values) / len(recent_values) if recent_values else 0,
                        'latest_value': recent_values[-1] if recent_values else 0,
                        'trend_direction': 'up' if len(recent_values) >= 2 and recent_values[-1] > recent_values[-2] else 'down'
                    }

            # DataLab 없을 때 쇼핑 API로 대체
            products = await self.search_products(keyword, display=20)
            if products:
                return {
                    'average_trend': len(products),
                    'latest_value': len(products),
                    'trend_direction': 'stable'
                }

            return {'average_trend': 0, 'latest_value': 0, 'trend_direction': 'stable'}

        except Exception as e:
            logger.error(f"현재 트렌드 데이터 수집 실패: {e}")
            return {'average_trend': 0, 'latest_value': 0, 'trend_direction': 'stable'}

    async def _get_past_trend_data(self, keyword: str, days_ago: int) -> Dict[str, Any]:
        """과거 트렌드 데이터 수집"""
        try:
            if self.datalab_api:
                # 과거 기간의 트렌드 데이터 (예: 7일 전 ~ 14일 전)
                trend_data = await self.datalab_api.get_trend_data([keyword], period="30d")
                if trend_data and keyword in trend_data:
                    past_values = trend_data[keyword][-30:-7] if len(trend_data[keyword]) > 14 else []
                    if past_values:
                        return {
                            'average_trend': sum(past_values) / len(past_values),
                            'latest_value': past_values[-1],
                            'trend_direction': 'up' if len(past_values) >= 2 and past_values[-1] > past_values[-2] else 'down'
                        }

            # 폴백: 현재 데이터와 유사하게 처리
            return {'average_trend': 50, 'latest_value': 50, 'trend_direction': 'stable'}

        except Exception as e:
            logger.error(f"과거 트렌드 데이터 수집 실패: {e}")
            return {'average_trend': 50, 'latest_value': 50, 'trend_direction': 'stable'}

    def _calculate_trend_change(self, keyword: str, current: Dict, past: Dict) -> Dict[str, Any]:
        """트렌드 변화율 계산"""
        try:
            current_value = current.get('average_trend', 0)
            past_value = past.get('average_trend', 1)  # 0으로 나누기 방지

            if past_value == 0:
                past_value = 1

            change_percentage = ((current_value - past_value) / past_value) * 100

            # 변화 타입 분류
            if change_percentage > 50:
                change_type = "급상승"
                severity = "critical"
            elif change_percentage > 30:
                change_type = "상승"
                severity = "high"
            elif change_percentage < -50:
                change_type = "급하락"
                severity = "critical"
            elif change_percentage < -30:
                change_type = "하락"
                severity = "high"
            else:
                change_type = "안정"
                severity = "normal"

            return {
                'keyword': keyword,
                'current_value': current_value,
                'past_value': past_value,
                'change_percentage': round(change_percentage, 2),
                'change_type': change_type,
                'severity': severity,
                'trend_direction': current.get('trend_direction', 'stable'),
                'analysis_timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"트렌드 변화 계산 실패: {e}")
            return {
                'keyword': keyword,
                'current_value': 0,
                'past_value': 0,
                'change_percentage': 0,
                'change_type': '분석 실패',
                'severity': 'error',
                'trend_direction': 'unknown'
            }

    def _analyze_competitor_changes(self, current_products: List[Dict], past_products: List[Dict] = None) -> Dict[str, Any]:
        """경쟁사 변화 분석"""
        if not past_products:
            past_products = []

        current_brands = set(p.get('brand', p.get('maker', '알 수 없음')) for p in current_products)
        past_brands = set(p.get('brand', p.get('maker', '알 수 없음')) for p in past_products)

        new_brands = current_brands - past_brands
        lost_brands = past_brands - current_brands
        continuing_brands = current_brands & past_brands

        return {
            'total_current_brands': len(current_brands),
            'total_past_brands': len(past_brands),
            'new_brands': list(new_brands),
            'lost_brands': list(lost_brands),
            'continuing_brands': list(continuing_brands),
            'brand_turnover_rate': len(new_brands) / max(len(past_brands), 1) * 100 if past_brands else 0
        }

    def _track_price_changes(self, current_products: List[Dict], past_products: List[Dict] = None) -> List[Dict]:
        """가격 변화 추적"""
        if not past_products:
            return []

        price_changes = []

        # 상품별 가격 변화 비교 (상품명 기준으로 매칭)
        past_product_map = {p.get('title', ''): p for p in past_products}

        for current_product in current_products:
            title = current_product.get('title', '')
            if title in past_product_map:
                past_product = past_product_map[title]
                current_price = int(current_product.get('lprice', 0))
                past_price = int(past_product.get('lprice', 1))

                if past_price > 0:
                    change_percentage = ((current_price - past_price) / past_price) * 100

                    if abs(change_percentage) > 5:  # 5% 이상 변화만 추적
                        price_changes.append({
                            'product_title': title[:50] + '...' if len(title) > 50 else title,
                            'current_price': current_price,
                            'past_price': past_price,
                            'change_percentage': round(change_percentage, 2),
                            'change_direction': 'increase' if change_percentage > 0 else 'decrease'
                        })

        return sorted(price_changes, key=lambda x: abs(x['change_percentage']), reverse=True)[:20]

    def _detect_new_entrants(self, current_products: List[Dict], past_products: List[Dict] = None) -> List[Dict]:
        """신규 진입자 감지"""
        if not past_products:
            return []

        past_titles = set(p.get('title', '') for p in past_products)
        new_entrants = []

        for product in current_products:
            title = product.get('title', '')
            if title not in past_titles and title:
                new_entrants.append({
                    'product_title': title[:50] + '...' if len(title) > 50 else title,
                    'brand': product.get('brand', product.get('maker', '알 수 없음')),
                    'price': int(product.get('lprice', 0)),
                    'mall_name': product.get('mallName', '알 수 없음'),
                    'detected_at': datetime.now().isoformat()
                })

        return new_entrants[:15]  # 상위 15개 신규 진입자

    def _track_market_share_changes(self, current_products: List[Dict], past_products: List[Dict] = None) -> Dict[str, Any]:
        """시장 점유율 변화 추적"""
        if not past_products:
            return {"message": "과거 데이터가 없어 점유율 변화를 계산할 수 없습니다"}

        # 현재와 과거 브랜드별 점유율 계산
        current_brand_share = self._calculate_simple_brand_share(current_products)
        past_brand_share = self._calculate_simple_brand_share(past_products)

        share_changes = []
        for brand, current_share in current_brand_share.items():
            past_share = past_brand_share.get(brand, 0)
            change = current_share - past_share

            if abs(change) > 1:  # 1% 이상 변화
                share_changes.append({
                    'brand': brand,
                    'current_share': round(current_share, 2),
                    'past_share': round(past_share, 2),
                    'share_change': round(change, 2),
                    'change_direction': 'gain' if change > 0 else 'loss'
                })

        return {
            'share_changes': sorted(share_changes, key=lambda x: abs(x['share_change']), reverse=True)[:10],
            'market_concentration_change': self._calculate_concentration_change(current_brand_share, past_brand_share)
        }

    def _calculate_simple_brand_share(self, products: List[Dict]) -> Dict[str, float]:
        """간단한 브랜드 점유율 계산"""
        if not products:
            return {}

        brand_counts = {}
        total_products = len(products)

        for product in products:
            brand = product.get('brand', product.get('maker', '기타'))
            brand_counts[brand] = brand_counts.get(brand, 0) + 1

        return {brand: (count / total_products) * 100 for brand, count in brand_counts.items()}

    def _calculate_market_volatility(self, trend_changes: List[Dict]) -> float:
        """시장 변동성 지수 계산"""
        if not trend_changes:
            return 0

        change_values = [abs(t.get('change_percentage', 0)) for t in trend_changes]
        if not change_values:
            return 0

        # 표준편차를 이용한 변동성 계산
        mean_change = sum(change_values) / len(change_values)
        variance = sum((x - mean_change) ** 2 for x in change_values) / len(change_values)
        volatility = variance ** 0.5

        return round(volatility, 2)

    def _calculate_competition_intensity_change(self, current_products: List[Dict], past_products: List[Dict] = None) -> Dict[str, Any]:
        """경쟁 강도 변화 계산"""
        current_intensity = len(set(p.get('brand', p.get('maker', '')) for p in current_products))
        past_intensity = len(set(p.get('brand', p.get('maker', '')) for p in past_products)) if past_products else current_intensity

        intensity_change = current_intensity - past_intensity
        change_percentage = (intensity_change / max(past_intensity, 1)) * 100

        return {
            'current_brand_count': current_intensity,
            'past_brand_count': past_intensity,
            'intensity_change': intensity_change,
            'change_percentage': round(change_percentage, 2),
            'trend': 'increasing' if intensity_change > 0 else 'decreasing' if intensity_change < 0 else 'stable'
        }

    def _generate_competitor_alerts(self, competitor_changes: Dict, price_changes: List[Dict], new_entrants: List[Dict]) -> List[Dict]:
        """경쟁사 모니터링 알림 생성"""
        alerts = []

        # 신규 브랜드 진입 알림
        if competitor_changes.get('new_brands'):
            alerts.append({
                'type': 'new_brand_entry',
                'severity': 'high',
                'message': f"{len(competitor_changes['new_brands'])}개 신규 브랜드가 시장에 진입했습니다",
                'details': competitor_changes['new_brands'][:5]
            })

        # 가격 급변 알림
        significant_price_changes = [p for p in price_changes if abs(p.get('change_percentage', 0)) > 20]
        if significant_price_changes:
            alerts.append({
                'type': 'significant_price_change',
                'severity': 'medium',
                'message': f"{len(significant_price_changes)}개 상품에서 20% 이상 가격 변화가 감지되었습니다",
                'details': significant_price_changes[:3]
            })

        # 신규 진입자 알림
        if len(new_entrants) > 10:
            alerts.append({
                'type': 'high_new_entrant_activity',
                'severity': 'medium',
                'message': f"{len(new_entrants)}개 신규 상품이 감지되었습니다 - 시장 활성화 신호",
                'details': new_entrants[:5]
            })

        return alerts

    def _assess_market_volatility(self, products: List[Dict]) -> str:
        """시장 변동성 평가"""
        if not products:
            return "정보 없음"

        prices = [int(p.get('lprice', 0)) for p in products if int(p.get('lprice', 0)) > 0]
        if not prices:
            return "정보 없음"

        # 가격 분산을 이용한 변동성 평가
        mean_price = sum(prices) / len(prices)
        price_variance = sum((p - mean_price) ** 2 for p in prices) / len(prices)
        coefficient_of_variation = (price_variance ** 0.5) / mean_price * 100

        if coefficient_of_variation > 80:
            return "매우 높음"
        elif coefficient_of_variation > 60:
            return "높음"
        elif coefficient_of_variation > 40:
            return "보통"
        else:
            return "낮음"

    def _calculate_concentration_change(self, current_share: Dict, past_share: Dict) -> str:
        """시장 집중도 변화 계산"""
        try:
            current_hhi = sum(share ** 2 for share in current_share.values())
            past_hhi = sum(share ** 2 for share in past_share.values()) if past_share else current_hhi

            hhi_change = current_hhi - past_hhi

            if hhi_change > 200:
                return "집중도 크게 증가"
            elif hhi_change > 50:
                return "집중도 증가"
            elif hhi_change < -200:
                return "집중도 크게 감소"
            elif hhi_change < -50:
                return "집중도 감소"
            else:
                return "집중도 안정"

        except Exception:
            return "집중도 변화 측정 불가"

    def _get_empty_trend_change_analysis(self, keywords: List[str]) -> Dict[str, Any]:
        """빈 트렌드 변화 분석 결과"""
        return {
            "monitoring_period": 7,
            "total_keywords_analyzed": len(keywords),
            "significant_changes_count": 0,
            "trend_changes": [],
            "rising_trends": [],
            "falling_trends": [],
            "analysis_summary": {
                "most_rising_keyword": None,
                "most_falling_keyword": None,
                "average_change": 0,
                "volatility_index": 0
            },
            "error": "트렌드 변화 분석 실패",
            "timestamp": datetime.now().isoformat()
        }

    def _get_empty_competitor_analysis(self, keyword: str, error: str = None) -> Dict[str, Any]:
        """빈 경쟁사 분석 결과"""
        return {
            "keyword": keyword,
            "error": error,
            "monitoring_timestamp": datetime.now().isoformat(),
            "total_competitors": 0,
            "competitor_changes": {},
            "price_changes": [],
            "new_entrants": [],
            "market_share_changes": {},
            "competition_intensity": {},
            "alerts": [],
            "analysis_summary": {
                "significant_price_changes": 0,
                "new_entrants_count": 0,
                "market_volatility": "정보 없음",
                "competition_trend": "정보 없음"
            }
        }

    def get_health_status(self) -> Dict[str, Any]:
        """분석기 상태 확인"""
        return {
            'status': 'healthy',
            'shopping_api': 'connected' if self.shopping_api else 'connected',
            'datalab_api': 'connected' if self.datalab_api else 'disconnected',
            'data_source': 'naver_apis_only',
            'last_check': datetime.now().isoformat()
        }