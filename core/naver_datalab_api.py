#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
네이버 데이터랩 쇼핑인사이트 API 클라이언트
시장 트렌드 분석 및 클릭 데이터 수집을 위한 API
"""

import urllib.request
import urllib.parse
import json
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import requests

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NaverDataLabAPI:
    """
    네이버 데이터랩 쇼핑인사이트 API 클라이언트 클래스
    트렌드 분석 및 시장 인사이트 데이터 제공
    """

    def __init__(self, client_id: str, client_secret: str):
        """
        API 클라이언트 초기화

        Args:
            client_id: 네이버 API Client ID (데이터랩 권한 필요)
            client_secret: 네이버 API Client Secret
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.trend_url = "https://openapi.naver.com/v1/datalab/search"
        self.shopping_url = "https://openapi.naver.com/v1/datalab/shopping/categories"
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 데이터랩 API는 제한이 더 엄격

        logger.info("네이버 데이터랩 API 클라이언트 초기화 완료")

    def _wait_for_rate_limit(self):
        """API 호출 제한 준수를 위한 대기"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        if time_since_last_request < self.min_request_interval:
            wait_time = self.min_request_interval - time_since_last_request
            time.sleep(wait_time)

        self.last_request_time = time.time()

    def get_shopping_category_trends(self, keyword: str, days: int = 30) -> Dict[str, Any]:
        """
        키워드 관련 쇼핑 카테고리 트렌드 데이터 조회

        Args:
            keyword: 검색 키워드
            days: 조회할 기간 (일 단위, 기본 30일)

        Returns:
            쇼핑 카테고리 트렌드 데이터
        """
        self._wait_for_rate_limit()

        # 날짜 범위 설정
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # 요청 데이터 구성
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": "date",
            "category": [
                {
                    "name": keyword,
                    "param": ["50000000"]  # 전체 쇼핑 카테고리
                }
            ]
        }

        # 헤더 설정
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                self.shopping_url,
                headers=headers,
                data=json.dumps(body),
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"쇼핑 카테고리 트렌드 조회 성공: {keyword}")
                return result
            else:
                logger.error(f"쇼핑 카테고리 트렌드 API 요청 실패: HTTP {response.status_code}")
                logger.error(f"응답 내용: {response.text}")
                return {"results": []}

        except Exception as e:
            logger.error(f"쇼핑 카테고리 트렌드 API 요청 중 오류: {str(e)}")
            return {"results": []}

    def get_search_trends(self, keywords: List[str], days: int = 30) -> Dict[str, Any]:
        """
        검색어 트렌드 데이터 조회 (통합 검색)

        Args:
            keywords: 검색 키워드 리스트 (최대 5개)
            days: 조회할 기간 (일 단위, 기본 30일)

        Returns:
            검색어 트렌드 데이터
        """
        self._wait_for_rate_limit()

        # 날짜 범위 설정
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # 키워드 그룹 구성 (최대 5개)
        keyword_groups = []
        for i, keyword in enumerate(keywords[:5]):
            keyword_groups.append({
                "groupName": keyword,
                "keywords": [keyword]
            })

        # 요청 데이터 구성
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": "date",
            "keywordGroups": keyword_groups
        }

        # 헤더 설정
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                self.trend_url,
                headers=headers,
                data=json.dumps(body),
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"검색어 트렌드 조회 성공: {keywords}")
                return result
            else:
                logger.error(f"검색어 트렌드 API 요청 실패: HTTP {response.status_code}")
                logger.error(f"응답 내용: {response.text}")
                return {"results": []}

        except Exception as e:
            logger.error(f"검색어 트렌드 API 요청 중 오류: {str(e)}")
            return {"results": []}

    def analyze_trend_metrics(self, trend_data: Dict[str, Any], keyword: str) -> Dict[str, Any]:
        """
        트렌드 데이터를 분석하여 시장 지표 생성

        Args:
            trend_data: 트렌드 API 응답 데이터
            keyword: 분석 대상 키워드

        Returns:
            분석된 시장 지표
        """
        try:
            if not trend_data.get("results"):
                return {
                    "trend_score": 0,
                    "trend_direction": "stable",
                    "popularity_index": 0,
                    "market_heat": "cold"
                }

            # 첫 번째 결과의 데이터 추출
            result = trend_data["results"][0]
            data_points = result.get("data", [])

            if not data_points:
                return {
                    "trend_score": 0,
                    "trend_direction": "stable",
                    "popularity_index": 0,
                    "market_heat": "cold"
                }

            # 트렌드 분석
            values = [point.get("ratio", 0) for point in data_points]

            # 평균 인기도
            avg_popularity = sum(values) / len(values) if values else 0

            # 트렌드 방향 분석 (최근 7일 vs 이전 7일)
            if len(values) >= 14:
                recent_avg = sum(values[-7:]) / 7
                previous_avg = sum(values[-14:-7]) / 7
                trend_change = ((recent_avg - previous_avg) / previous_avg * 100) if previous_avg > 0 else 0
            else:
                trend_change = 0

            # 트렌드 방향 결정
            if trend_change > 10:
                trend_direction = "rising"
            elif trend_change < -10:
                trend_direction = "falling"
            else:
                trend_direction = "stable"

            # 시장 열기 분석
            if avg_popularity > 80:
                market_heat = "hot"
            elif avg_popularity > 50:
                market_heat = "warm"
            elif avg_popularity > 20:
                market_heat = "cool"
            else:
                market_heat = "cold"

            # 트렌드 점수 계산 (0-100)
            trend_score = min(100, max(0, avg_popularity + (trend_change / 2)))

            return {
                "trend_score": round(trend_score, 1),
                "trend_direction": trend_direction,
                "trend_change_percent": round(trend_change, 1),
                "popularity_index": round(avg_popularity, 1),
                "market_heat": market_heat,
                "data_points": len(values),
                "analysis_period": f"{len(values)}일"
            }

        except Exception as e:
            logger.error(f"트렌드 분석 중 오류: {str(e)}")
            return {
                "trend_score": 0,
                "trend_direction": "stable",
                "popularity_index": 0,
                "market_heat": "cold"
            }

    def get_comprehensive_market_insight(self, keyword: str, days: int = 30) -> Dict[str, Any]:
        """
        종합적인 시장 인사이트 분석

        Args:
            keyword: 분석 대상 키워드
            days: 분석 기간 (일 단위)

        Returns:
            종합 시장 분석 결과
        """
        logger.info(f"'{keyword}' 종합 시장 인사이트 분석 시작")

        # 검색어 트렌드 조회
        search_trends = self.get_search_trends([keyword], days)
        trend_metrics = self.analyze_trend_metrics(search_trends, keyword)

        # 쇼핑 카테고리 트렌드 조회
        shopping_trends = self.get_shopping_category_trends(keyword, days)

        # 관련 키워드 생성 (키워드 확장)
        related_keywords = self._generate_related_keywords(keyword)
        if related_keywords:
            related_trends = self.get_search_trends(related_keywords[:4], days)
        else:
            related_trends = {"results": []}

        # 종합 분석 결과
        comprehensive_insight = {
            "keyword": keyword,
            "analysis_date": datetime.now().isoformat(),
            "analysis_period_days": days,

            # 메인 트렌드 지표
            "trend_score": trend_metrics["trend_score"],
            "trend_direction": trend_metrics["trend_direction"],
            "trend_change_percent": trend_metrics.get("trend_change_percent", 0),
            "popularity_index": trend_metrics["popularity_index"],
            "market_heat": trend_metrics["market_heat"],

            # 원본 데이터
            "search_trends_raw": search_trends,
            "shopping_trends_raw": shopping_trends,
            "related_trends_raw": related_trends,

            # 메타데이터
            "data_source": "naver_datalab_api",
            "related_keywords": related_keywords
        }

        logger.info(f"'{keyword}' 종합 시장 인사이트 분석 완료")
        return comprehensive_insight

    def _generate_related_keywords(self, keyword: str) -> List[str]:
        """
        키워드 기반 관련 검색어 생성

        Args:
            keyword: 기본 키워드

        Returns:
            관련 키워드 리스트
        """
        # 간단한 키워드 확장 로직
        # 실제로는 더 정교한 키워드 확장 알고리즘 사용 권장

        related_patterns = [
            f"{keyword} 추천",
            f"{keyword} 인기",
            f"{keyword} 브랜드",
            f"{keyword} 가격"
        ]

        return related_patterns


def test_naver_datalab_api():
    """
    네이버 데이터랩 API 테스트 함수
    """
    import os

    client_id = os.getenv('NAVER_CLIENT_ID', 'YOUR_CLIENT_ID')
    client_secret = os.getenv('NAVER_CLIENT_SECRET', 'YOUR_CLIENT_SECRET')

    if client_id == 'YOUR_CLIENT_ID':
        print("❌ 환경 변수에 네이버 API 키를 설정해주세요.")
        print("⚠️ 데이터랩 API 권한이 있는 키가 필요합니다.")
        return

    # API 클라이언트 초기화
    api = NaverDataLabAPI(client_id, client_secret)

    # 테스트 키워드
    test_keyword = "키보드"
    print(f"테스트 키워드: '{test_keyword}'")

    # 종합 시장 인사이트 분석
    insight = api.get_comprehensive_market_insight(test_keyword, days=14)

    print(f"✅ 분석 완료!")
    print(f"   트렌드 점수: {insight['trend_score']}/100")
    print(f"   트렌드 방향: {insight['trend_direction']}")
    print(f"   인기도 지수: {insight['popularity_index']}")
    print(f"   시장 열기: {insight['market_heat']}")


if __name__ == "__main__":
    test_naver_datalab_api()