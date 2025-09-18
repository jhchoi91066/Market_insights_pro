#!/usr/bin/env python3
"""
부하 테스트 실행 및 결과 분석 스크립트
다양한 부하 시나리오를 실행하고 성능 지표를 수집
"""

import subprocess
import time
import json
import requests
import threading
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LoadTestRunner:
    """
    부하 테스트 실행 및 모니터링 클래스
    """

    def __init__(self, host: str = "http://localhost:8001"):
        self.host = host
        self.results_dir = "load_test_results"
        self.ensure_results_directory()

    def ensure_results_directory(self):
        """결과 저장 디렉토리 생성"""
        os.makedirs(self.results_dir, exist_ok=True)

    def check_server_health(self) -> bool:
        """서버 상태 확인"""
        try:
            response = requests.get(f"{self.host}/api/database/health", timeout=10)
            if response.status_code == 200:
                logger.info("✅ 서버 상태 정상")
                return True
            else:
                logger.error(f"❌ 서버 응답 오류: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ 서버 연결 실패: {e}")
            return False

    def collect_baseline_metrics(self) -> Dict[str, Any]:
        """기준 성능 지표 수집"""
        logger.info("📊 기준 성능 지표 수집 중...")

        metrics = {
            "timestamp": datetime.now().isoformat(),
            "database_health": {},
            "connection_pool": {},
            "cache_stats": {},
            "query_stats": {}
        }

        try:
            # 데이터베이스 헬스
            response = requests.get(f"{self.host}/api/database/health")
            if response.status_code == 200:
                metrics["database_health"] = response.json()

            # 연결 풀 통계
            response = requests.get(f"{self.host}/api/database/connection-pool/stats")
            if response.status_code == 200:
                metrics["connection_pool"] = response.json()

            # 캐시 통계
            response = requests.get(f"{self.host}/api/v2/cache/stats")
            if response.status_code == 200:
                metrics["cache_stats"] = response.json()

            # 쿼리 통계
            response = requests.get(f"{self.host}/api/database/query-stats")
            if response.status_code == 200:
                metrics["query_stats"] = response.json()

        except Exception as e:
            logger.error(f"기준 지표 수집 실패: {e}")

        return metrics

    def run_load_test_scenario(
        self,
        scenario_name: str,
        users: int,
        spawn_rate: int,
        duration: int,
        user_classes: List[str] = None
    ) -> Dict[str, Any]:
        """
        특정 시나리오 부하 테스트 실행

        Args:
            scenario_name: 시나리오 이름
            users: 동시 사용자 수
            spawn_rate: 사용자 증가율 (초당)
            duration: 테스트 지속 시간 (초)
            user_classes: 사용할 사용자 클래스 목록
        """

        logger.info(f"🚀 부하 테스트 시작: {scenario_name}")
        logger.info(f"   사용자: {users}명, 증가율: {spawn_rate}/초, 지속시간: {duration}초")

        # 사전 메트릭 수집
        before_metrics = self.collect_baseline_metrics()

        # Locust 명령어 구성
        cmd = [
            "locust",
            "-f", "scripts/load_testing.py",
            "--host", self.host,
            "--users", str(users),
            "--spawn-rate", str(spawn_rate),
            "--run-time", f"{duration}s",
            "--headless",  # GUI 없이 실행
            "--csv", f"{self.results_dir}/{scenario_name}"  # CSV 결과 저장
        ]

        # 특정 사용자 클래스만 실행
        if user_classes:
            for user_class in user_classes:
                cmd.extend(["--user-class", user_class])

        # 실시간 모니터링 시작
        monitoring_thread = threading.Thread(
            target=self._monitor_during_test,
            args=(scenario_name, duration)
        )
        monitoring_thread.start()

        # 부하 테스트 실행
        start_time = time.time()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 60)
            success = result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.warning("부하 테스트 타임아웃")
            success = False
        except Exception as e:
            logger.error(f"부하 테스트 실행 오류: {e}")
            success = False

        end_time = time.time()

        # 모니터링 스레드 종료 대기
        monitoring_thread.join(timeout=10)

        # 사후 메트릭 수집
        time.sleep(5)  # 시스템 안정화 대기
        after_metrics = self.collect_baseline_metrics()

        # 결과 수집
        test_result = {
            "scenario_name": scenario_name,
            "config": {
                "users": users,
                "spawn_rate": spawn_rate,
                "duration": duration,
                "user_classes": user_classes
            },
            "execution": {
                "start_time": datetime.fromtimestamp(start_time).isoformat(),
                "end_time": datetime.fromtimestamp(end_time).isoformat(),
                "actual_duration": end_time - start_time,
                "success": success
            },
            "metrics": {
                "before": before_metrics,
                "after": after_metrics
            }
        }

        # Locust 결과 파일 읽기
        try:
            stats_file = f"{self.results_dir}/{scenario_name}_stats.csv"
            if os.path.exists(stats_file):
                test_result["locust_stats"] = self._parse_locust_results(stats_file)
        except Exception as e:
            logger.error(f"Locust 결과 파일 읽기 실패: {e}")

        # 결과 저장
        result_file = f"{self.results_dir}/{scenario_name}_result.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(test_result, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ 테스트 완료: {scenario_name}")
        return test_result

    def _monitor_during_test(self, scenario_name: str, duration: int):
        """테스트 중 시스템 모니터링"""
        monitoring_data = []
        interval = 10  # 10초 간격
        end_time = time.time() + duration

        while time.time() < end_time:
            try:
                timestamp = datetime.now().isoformat()
                snapshot = {
                    "timestamp": timestamp,
                    "connection_pool": {},
                    "cache_stats": {},
                    "system_load": {}
                }

                # 연결 풀 상태
                response = requests.get(f"{self.host}/api/database/connection-pool/stats", timeout=5)
                if response.status_code == 200:
                    snapshot["connection_pool"] = response.json().get("data", {})

                # 캐시 통계
                response = requests.get(f"{self.host}/api/v2/cache/stats", timeout=5)
                if response.status_code == 200:
                    snapshot["cache_stats"] = response.json().get("data", {})

                monitoring_data.append(snapshot)

            except Exception as e:
                logger.debug(f"모니터링 스냅샷 실패: {e}")

            time.sleep(interval)

        # 모니터링 데이터 저장
        monitoring_file = f"{self.results_dir}/{scenario_name}_monitoring.json"
        with open(monitoring_file, 'w', encoding='utf-8') as f:
            json.dump(monitoring_data, f, indent=2, ensure_ascii=False)

    def _parse_locust_results(self, stats_file: str) -> Dict[str, Any]:
        """Locust 결과 파일 파싱"""
        try:
            import pandas as pd
            df = pd.read_csv(stats_file)

            # 주요 통계 추출
            summary = {
                "total_requests": df['Request Count'].sum(),
                "total_failures": df['Failure Count'].sum(),
                "average_response_time": df['Average Response Time'].mean(),
                "min_response_time": df['Min Response Time'].min(),
                "max_response_time": df['Max Response Time'].max(),
                "requests_per_second": df['Requests/s'].mean(),
                "failure_rate": df['Failure Count'].sum() / df['Request Count'].sum() if df['Request Count'].sum() > 0 else 0
            }

            # 엔드포인트별 통계
            endpoint_stats = df.to_dict('records')

            return {
                "summary": summary,
                "endpoints": endpoint_stats
            }

        except Exception as e:
            logger.error(f"Locust 결과 파싱 실패: {e}")
            return {}

    def run_all_scenarios(self):
        """모든 테스트 시나리오 실행"""

        if not self.check_server_health():
            logger.error("서버가 실행되지 않았습니다. 테스트를 중단합니다.")
            return

        scenarios = [
            {
                "name": "light_load",
                "description": "가벼운 부하 (일반 사용)",
                "users": 10,
                "spawn_rate": 2,
                "duration": 120,  # 2분
                "user_classes": ["MarketInsightsUser"]
            },
            {
                "name": "moderate_load",
                "description": "중간 부하 (피크 시간)",
                "users": 50,
                "spawn_rate": 5,
                "duration": 300,  # 5분
                "user_classes": ["MarketInsightsUser", "DataAnalysisUser"]
            },
            {
                "name": "heavy_load",
                "description": "높은 부하 (스트레스 테스트)",
                "users": 100,
                "spawn_rate": 10,
                "duration": 180,  # 3분
                "user_classes": ["MarketInsightsUser", "HighVolumeUser"]
            },
            {
                "name": "spike_test",
                "description": "급증 테스트 (갑작스런 트래픽)",
                "users": 200,
                "spawn_rate": 50,  # 빠른 증가
                "duration": 120,  # 2분
                "user_classes": ["HighVolumeUser"]
            },
            {
                "name": "analysis_intensive",
                "description": "분석 집중 테스트 (CPU 부하)",
                "users": 30,
                "spawn_rate": 3,
                "duration": 240,  # 4분
                "user_classes": ["DataAnalysisUser"]
            }
        ]

        results = []

        for i, scenario in enumerate(scenarios, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"시나리오 {i}/{len(scenarios)}: {scenario['description']}")
            logger.info(f"{'='*60}")

            result = self.run_load_test_scenario(
                scenario_name=scenario["name"],
                users=scenario["users"],
                spawn_rate=scenario["spawn_rate"],
                duration=scenario["duration"],
                user_classes=scenario.get("user_classes")
            )

            results.append(result)

            # 시나리오 간 휴식 시간
            if i < len(scenarios):
                logger.info("💤 시나리오 간 휴식 중 (30초)...")
                time.sleep(30)

        # 전체 결과 요약 생성
        self.generate_summary_report(results)

        return results

    def generate_summary_report(self, results: List[Dict[str, Any]]):
        """전체 테스트 요약 보고서 생성"""

        summary = {
            "test_session": {
                "timestamp": datetime.now().isoformat(),
                "total_scenarios": len(results),
                "host": self.host
            },
            "scenarios": [],
            "performance_analysis": {}
        }

        for result in results:
            scenario_summary = {
                "name": result["scenario_name"],
                "config": result["config"],
                "success": result["execution"]["success"],
                "duration": result["execution"]["actual_duration"]
            }

            # Locust 통계가 있으면 추가
            if "locust_stats" in result and "summary" in result["locust_stats"]:
                stats = result["locust_stats"]["summary"]
                scenario_summary.update({
                    "total_requests": stats.get("total_requests", 0),
                    "failure_rate": stats.get("failure_rate", 0),
                    "avg_response_time": stats.get("average_response_time", 0),
                    "requests_per_second": stats.get("requests_per_second", 0)
                })

            summary["scenarios"].append(scenario_summary)

        # 성능 분석
        successful_scenarios = [s for s in summary["scenarios"] if s["success"]]

        if successful_scenarios:
            avg_response_times = [s.get("avg_response_time", 0) for s in successful_scenarios]
            failure_rates = [s.get("failure_rate", 0) for s in successful_scenarios]
            rps_values = [s.get("requests_per_second", 0) for s in successful_scenarios]

            summary["performance_analysis"] = {
                "avg_response_time_range": {
                    "min": min(avg_response_times),
                    "max": max(avg_response_times),
                    "avg": sum(avg_response_times) / len(avg_response_times)
                },
                "failure_rate_range": {
                    "min": min(failure_rates),
                    "max": max(failure_rates),
                    "avg": sum(failure_rates) / len(failure_rates)
                },
                "rps_range": {
                    "min": min(rps_values),
                    "max": max(rps_values),
                    "avg": sum(rps_values) / len(rps_values)
                }
            }

        # 요약 보고서 저장
        summary_file = f"{self.results_dir}/load_test_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"\n📊 부하 테스트 완료! 결과: {summary_file}")

        # 콘솔에 간단한 요약 출력
        print("\n" + "="*80)
        print("📊 부하 테스트 결과 요약")
        print("="*80)

        for scenario in summary["scenarios"]:
            status = "✅ 성공" if scenario["success"] else "❌ 실패"
            print(f"{scenario['name']}: {status}")
            if scenario.get("avg_response_time"):
                print(f"  평균 응답시간: {scenario['avg_response_time']:.2f}ms")
            if scenario.get("failure_rate"):
                print(f"  실패율: {scenario['failure_rate']*100:.2f}%")
            if scenario.get("requests_per_second"):
                print(f"  초당 요청: {scenario['requests_per_second']:.1f} RPS")
            print()

if __name__ == '__main__':
    import sys

    # 실행 인자 처리
    host = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"

    runner = LoadTestRunner(host)

    print("🚀 Market Insights Pro 부하 테스트 시작")
    print(f"대상 서버: {host}")
    print()

    try:
        results = runner.run_all_scenarios()
        print("✅ 모든 부하 테스트가 완료되었습니다!")

    except KeyboardInterrupt:
        print("\n⏹️ 사용자에 의해 테스트가 중단되었습니다.")
    except Exception as e:
        print(f"\n❌ 부하 테스트 실행 중 오류: {e}")
        sys.exit(1)