"""
Locust 부하 테스트 스크립트
실제 사용자 행동 패턴을 시뮬레이션하여 시스템 성능 테스트
"""

import json
import random
import time
from locust import HttpUser, task, between
from locust.exception import StopUser
import logging

# 테스트 데이터
TEST_KEYWORDS = [
    "wireless mouse", "bluetooth headphones", "laptop stand",
    "gaming keyboard", "webcam", "monitor", "phone case",
    "tablet", "smart watch", "earbuds"
]

FILTER_CATEGORIES = [
    "electronics", "computers", "mobile", "accessories", "gaming"
]

class MarketInsightsUser(HttpUser):
    """
    Market Insights Pro 사용자 시뮬레이션

    실제 사용자의 행동 패턴을 모방:
    1. 메인 페이지 방문
    2. 키워드 검색/분석
    3. 결과 조회 및 필터링
    4. 상품 상세 조회
    """

    # 사용자 요청 간격 (1-3초)
    wait_time = between(1, 3)

    def on_start(self):
        """사용자 세션 시작시 실행"""
        self.session_id = f"load_test_{random.randint(1000, 9999)}"
        self.analysis_results = []

        # 메인 페이지 방문
        self.visit_homepage()

    def visit_homepage(self):
        """메인 페이지 방문"""
        with self.client.get("/", catch_response=True, name="HomePage") as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"홈페이지 로드 실패: {response.status_code}")

    @task(30)  # 30% 확률
    def analyze_keyword(self):
        """키워드 분석 요청 (비동기)"""
        keyword = random.choice(TEST_KEYWORDS)

        # 비동기 분석 시작
        with self.client.post(
            "/api/analyze/async",
            json={"keyword": keyword},
            catch_response=True,
            name="StartAsyncAnalysis"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                task_id = data.get("task_id")

                if task_id and task_id != "cached":
                    # 작업 진행률 추적
                    self.track_task_progress(task_id, keyword)
                    response.success()
                else:
                    # 캐시된 결과
                    response.success()
                    logging.info(f"캐시 히트: {keyword}")
            else:
                response.failure(f"분석 시작 실패: {response.status_code}")

    def track_task_progress(self, task_id: str, keyword: str):
        """작업 진행률 추적"""
        max_attempts = 30  # 최대 30회 시도 (약 1분)
        attempt = 0

        while attempt < max_attempts:
            time.sleep(2)  # 2초 대기
            attempt += 1

            with self.client.get(
                f"/api/tasks/{task_id}/progress",
                catch_response=True,
                name="TaskProgress"
            ) as response:
                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status")

                    if status == "completed":
                        logging.info(f"분석 완료: {keyword} ({attempt}회 조회)")
                        response.success()
                        return
                    elif status == "failed":
                        response.failure(f"작업 실패: {keyword}")
                        return
                    else:
                        response.success()
                else:
                    response.failure(f"진행률 조회 실패: {response.status_code}")

        # 타임아웃
        logging.warning(f"작업 타임아웃: {keyword} (Task ID: {task_id})")

    @task(20)  # 20% 확률
    def browse_products_v2(self):
        """최적화된 상품 목록 조회 (v2 API)"""
        page = random.randint(1, 5)
        size = random.choice([10, 20, 50])

        params = {
            "page": page,
            "size": size
        }

        # 필터 추가 (50% 확률)
        if random.random() < 0.5:
            if random.random() < 0.3:
                params["category"] = random.choice(FILTER_CATEGORIES)
            if random.random() < 0.3:
                params["min_price"] = random.uniform(10, 50)
            if random.random() < 0.3:
                params["max_price"] = random.uniform(100, 500)
            if random.random() < 0.3:
                params["min_rating"] = random.uniform(3.5, 4.5)

        with self.client.get(
            "/api/v2/products",
            params=params,
            catch_response=True,
            name="ProductsV2"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                total_items = data.get("pagination", {}).get("total_items", 0)
                response.success()
                logging.debug(f"상품 조회: 페이지 {page}, 총 {total_items}개")
            elif response.status_code == 304:
                # Not Modified - 캐시 히트
                response.success()
                logging.info(f"상품 목록 캐시 히트: 페이지 {page}")
            else:
                response.failure(f"상품 조회 실패: {response.status_code}")

    @task(15)  # 15% 확률
    def browse_analysis_results(self):
        """분석 결과 조회"""
        page = random.randint(1, 3)
        size = random.choice([5, 10, 20])

        params = {"page": page, "size": size}

        # 카테고리 필터 (30% 확률)
        if random.random() < 0.3:
            params["category"] = random.choice(TEST_KEYWORDS)

        with self.client.get(
            "/api/v2/analysis-results",
            params=params,
            catch_response=True,
            name="AnalysisResultsV2"
        ) as response:
            if response.status_code in [200, 304]:
                response.success()
            else:
                response.failure(f"분석 결과 조회 실패: {response.status_code}")

    @task(10)  # 10% 확률
    def check_system_health(self):
        """시스템 헬스체크"""
        endpoints = [
            "/api/database/health",
            "/api/database/query-stats",
            "/api/database/connection-pool/stats",
            "/api/v2/cache/stats"
        ]

        endpoint = random.choice(endpoints)

        with self.client.get(
            endpoint,
            catch_response=True,
            name="SystemHealth"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"헬스체크 실패: {response.status_code}")

    @task(8)  # 8% 확률
    def browse_scraping_sessions(self):
        """스크래핑 세션 조회"""
        page = random.randint(1, 2)
        size = random.choice([10, 20])

        with self.client.get(
            "/api/v2/scraping-sessions",
            params={"page": page, "size": size},
            catch_response=True,
            name="ScrapingSessionsV2"
        ) as response:
            if response.status_code in [200, 304]:
                response.success()
            else:
                response.failure(f"세션 조회 실패: {response.status_code}")

    @task(5)  # 5% 확률
    def test_database_optimization(self):
        """데이터베이스 최적화 테스트"""
        with self.client.post(
            "/api/database/optimize",
            catch_response=True,
            name="DatabaseOptimize"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"DB 최적화 실패: {response.status_code}")

    @task(3)  # 3% 확률
    def clear_cache(self):
        """캐시 정리 (관리자 작업)"""
        if random.random() < 0.5:
            # 패턴 기반 정리
            pattern = random.choice(["products", "analysis", "sessions"])
            with self.client.post(
                "/api/v2/cache/clear",
                params={"pattern": pattern},
                catch_response=True,
                name="CacheClear"
            ) as response:
                if response.status_code == 200:
                    response.success()
                else:
                    response.failure(f"캐시 정리 실패: {response.status_code}")

class HighVolumeUser(MarketInsightsUser):
    """
    고부하 사용자 (API 집중 사용)
    """
    wait_time = between(0.5, 1.5)  # 더 짧은 대기시간

    @task(50)
    def rapid_product_queries(self):
        """빠른 상품 조회"""
        for _ in range(3):  # 연속 3번 요청
            page = random.randint(1, 10)
            with self.client.get(
                "/api/v2/products",
                params={"page": page, "size": 20},
                catch_response=True,
                name="RapidProductQuery"
            ) as response:
                if response.status_code in [200, 304]:
                    response.success()
                else:
                    response.failure(f"빠른 조회 실패: {response.status_code}")

            time.sleep(0.1)  # 100ms 대기

class DataAnalysisUser(MarketInsightsUser):
    """
    데이터 분석 중심 사용자
    """

    @task(60)
    def intensive_analysis(self):
        """집중적인 분석 작업"""
        keyword = random.choice(TEST_KEYWORDS)

        # 기존 분석 결과 확인
        with self.client.get(
            "/api/v2/analysis-results",
            params={"category": keyword, "size": 5},
            catch_response=True,
            name="CheckExistingAnalysis"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("pagination", {}).get("total_items", 0) == 0:
                    # 분석 결과가 없으면 새로 분석
                    self.analyze_keyword()
                response.success()

if __name__ == '__main__':
    # 독립 실행을 위한 코드
    print("Locust 부하 테스트 스크립트")
    print("실행 방법:")
    print("locust -f scripts/load_testing.py --host=http://localhost:8001")
    print("")
    print("테스트 시나리오:")
    print("- MarketInsightsUser: 일반 사용자 (70%)")
    print("- HighVolumeUser: 고부하 사용자 (20%)")
    print("- DataAnalysisUser: 분석 중심 사용자 (10%)")
    print("")
    print("주요 테스트:")
    print("- 비동기 분석 처리")
    print("- API v2 페이지네이션")
    print("- 캐시 효율성")
    print("- 데이터베이스 성능")