#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
성능 벤치마크 테스트
Market Insights Pro의 종합적인 성능을 측정하고 최적화 포인트를 식별합니다.
"""

import asyncio
import aiohttp
import time
import psutil
import memory_profiler
from datetime import datetime
from typing import Dict, List, Any
import json
import statistics
import concurrent.futures
import threading

BASE_URL = "http://127.0.0.1:8001"

class PerformanceBenchmark:
    """성능 벤치마크 테스트 클래스"""

    def __init__(self):
        self.results = {}
        self.start_time = None
        self.process = psutil.Process()

    def start_monitoring(self):
        """성능 모니터링 시작"""
        self.start_time = time.time()
        initial_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        initial_cpu = self.process.cpu_percent()

        print(f"🚀 성능 벤치마크 시작")
        print(f"   📊 초기 메모리 사용량: {initial_memory:.2f} MB")
        print(f"   🖥️  초기 CPU 사용률: {initial_cpu:.2f}%")
        print("=" * 60)

    def record_result(self, test_name: str, duration: float, success: bool, details: Dict[str, Any] = None):
        """테스트 결과 기록"""
        self.results[test_name] = {
            "duration_ms": duration * 1000,
            "success": success,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        }

    async def test_ml_prediction_performance(self):
        """ML 예측 성능 테스트"""
        print("🧪 ML 예측 성능 테스트")

        # 단일 예측 성능
        single_prediction_times = []

        prediction_request = {
            "category": "컴퓨터/IT",
            "brand": "Logitech",
            "seller": "Coupang",
            "search_keyword": "무선마우스",
            "rating": 4.5,
            "review_count": 200
        }

        async with aiohttp.ClientSession() as session:
            # 워밍업 (캐시 로딩)
            try:
                async with session.post(f"{BASE_URL}/api/ml/predict/price", json=prediction_request) as response:
                    await response.json()
                print("   ✅ 모델 워밍업 완료")
            except:
                print("   ❌ 모델 워밍업 실패")
                return

            # 단일 예측 성능 테스트 (100회)
            print("   📊 단일 예측 성능 테스트 (100회)...")
            for i in range(100):
                start_time = time.time()
                try:
                    async with session.post(f"{BASE_URL}/api/ml/predict/price", json=prediction_request) as response:
                        if response.status == 200:
                            result = await response.json()
                            duration = time.time() - start_time
                            single_prediction_times.append(duration)
                        else:
                            print(f"   ❌ 예측 실패: {response.status}")
                except Exception as e:
                    print(f"   ❌ 요청 실패: {e}")

            # 동시 요청 성능 테스트 (50개 동시)
            print("   🚀 동시 요청 성능 테스트 (50개 동시)...")
            concurrent_times = []

            async def concurrent_request():
                start_time = time.time()
                try:
                    async with session.post(f"{BASE_URL}/api/ml/predict/price", json=prediction_request) as response:
                        if response.status == 200:
                            await response.json()
                            return time.time() - start_time
                except:
                    return None

            tasks = [concurrent_request() for _ in range(50)]
            concurrent_results = await asyncio.gather(*tasks, return_exceptions=True)

            concurrent_times = [r for r in concurrent_results if isinstance(r, float)]

        # 결과 분석
        if single_prediction_times:
            avg_single = statistics.mean(single_prediction_times)
            p95_single = statistics.quantiles(single_prediction_times, n=20)[18]  # 95th percentile
            p99_single = statistics.quantiles(single_prediction_times, n=100)[98]  # 99th percentile

            print(f"   📈 단일 예측 성능:")
            print(f"      - 평균: {avg_single*1000:.2f}ms")
            print(f"      - P95: {p95_single*1000:.2f}ms")
            print(f"      - P99: {p99_single*1000:.2f}ms")
            print(f"      - 성공률: {len(single_prediction_times)}/100 ({len(single_prediction_times)}%)")

            self.record_result("single_prediction", avg_single, True, {
                "p95_ms": p95_single * 1000,
                "p99_ms": p99_single * 1000,
                "success_rate": len(single_prediction_times)
            })

        if concurrent_times:
            avg_concurrent = statistics.mean(concurrent_times)
            print(f"   🚀 동시 요청 성능:")
            print(f"      - 평균: {avg_concurrent*1000:.2f}ms")
            print(f"      - 성공률: {len(concurrent_times)}/50 ({len(concurrent_times)*2}%)")

            self.record_result("concurrent_prediction", avg_concurrent, True, {
                "success_rate": len(concurrent_times) * 2
            })

    async def test_system_api_performance(self):
        """시스템 API 성능 테스트"""
        print("\n🧪 시스템 API 성능 테스트")

        endpoints = [
            ("/api/system/status", "시스템 상태"),
            ("/api/system/info", "시스템 정보"),
            ("/api/ml/health", "ML 헬스체크"),
            ("/api/ml/monitoring/dashboard", "모니터링 대시보드")
        ]

        async with aiohttp.ClientSession() as session:
            for endpoint, name in endpoints:
                times = []
                print(f"   📊 {name} 테스트...")

                for _ in range(10):
                    start_time = time.time()
                    try:
                        async with session.get(f"{BASE_URL}{endpoint}") as response:
                            if response.status == 200:
                                await response.json()
                                duration = time.time() - start_time
                                times.append(duration)
                    except Exception as e:
                        print(f"      ❌ 요청 실패: {e}")

                if times:
                    avg_time = statistics.mean(times)
                    print(f"      ✅ 평균 응답시간: {avg_time*1000:.2f}ms")
                    self.record_result(f"api_{endpoint.replace('/', '_')}", avg_time, True)

    def test_memory_usage(self):
        """메모리 사용량 테스트"""
        print("\n🧪 메모리 사용량 분석")

        memory_info = self.process.memory_info()
        memory_percent = self.process.memory_percent()

        print(f"   📊 현재 메모리 사용량:")
        print(f"      - RSS: {memory_info.rss / 1024 / 1024:.2f} MB")
        print(f"      - VMS: {memory_info.vms / 1024 / 1024:.2f} MB")
        print(f"      - 시스템 대비: {memory_percent:.2f}%")

        # 메모리 임계값 체크
        memory_limit_mb = 512  # 512MB 제한
        memory_ok = (memory_info.rss / 1024 / 1024) < memory_limit_mb

        print(f"   🎯 메모리 최적화 상태: {'✅ 양호' if memory_ok else '❌ 초과'}")

        self.record_result("memory_usage", memory_info.rss / 1024 / 1024, memory_ok, {
            "rss_mb": memory_info.rss / 1024 / 1024,
            "vms_mb": memory_info.vms / 1024 / 1024,
            "percent": memory_percent,
            "limit_mb": memory_limit_mb
        })

    def test_cpu_usage(self):
        """CPU 사용량 테스트"""
        print("\n🧪 CPU 사용량 분석")

        # 5초간 CPU 사용률 모니터링
        cpu_percentages = []
        for _ in range(5):
            cpu_percent = self.process.cpu_percent(interval=1)
            cpu_percentages.append(cpu_percent)

        avg_cpu = statistics.mean(cpu_percentages)
        max_cpu = max(cpu_percentages)

        print(f"   📊 CPU 사용률 (5초간):")
        print(f"      - 평균: {avg_cpu:.2f}%")
        print(f"      - 최대: {max_cpu:.2f}%")

        # CPU 임계값 체크 (평균 50% 이하)
        cpu_ok = avg_cpu < 50.0
        print(f"   🎯 CPU 최적화 상태: {'✅ 양호' if cpu_ok else '❌ 높음'}")

        self.record_result("cpu_usage", avg_cpu, cpu_ok, {
            "avg_percent": avg_cpu,
            "max_percent": max_cpu,
            "samples": cpu_percentages
        })

    async def test_cache_performance(self):
        """캐시 성능 테스트"""
        print("\n🧪 캐시 성능 테스트")

        # 동일한 예측 요청을 여러 번 보내서 캐시 히트율 확인
        prediction_request = {
            "category": "컴퓨터/IT",
            "brand": "Samsung",
            "search_keyword": "모니터",
            "rating": 4.0,
            "review_count": 100
        }

        response_times = []
        cache_hits = 0

        async with aiohttp.ClientSession() as session:
            # 첫 번째 요청 (캐시 미스)
            start_time = time.time()
            async with session.post(f"{BASE_URL}/api/ml/predict/price", json=prediction_request) as response:
                if response.status == 200:
                    first_duration = time.time() - start_time
                    result = await response.json()
                    print(f"   📊 첫 번째 요청 (캐시 미스): {first_duration*1000:.2f}ms")

            # 후속 요청들 (캐시 히트 예상)
            for i in range(10):
                start_time = time.time()
                async with session.post(f"{BASE_URL}/api/ml/predict/price", json=prediction_request) as response:
                    if response.status == 200:
                        duration = time.time() - start_time
                        response_times.append(duration)

                        # 캐시 히트 판정 (10ms 미만)
                        if duration < 0.01:
                            cache_hits += 1

        if response_times:
            avg_cached = statistics.mean(response_times)
            cache_hit_rate = (cache_hits / len(response_times)) * 100

            print(f"   📈 캐시 성능:")
            print(f"      - 캐시된 요청 평균: {avg_cached*1000:.2f}ms")
            print(f"      - 캐시 히트율: {cache_hit_rate:.1f}%")
            print(f"      - 성능 향상: {(first_duration/avg_cached):.1f}배")

            self.record_result("cache_performance", avg_cached, True, {
                "cache_hit_rate": cache_hit_rate,
                "first_request_ms": first_duration * 1000,
                "cached_avg_ms": avg_cached * 1000,
                "performance_improvement": first_duration / avg_cached
            })

    def generate_performance_report(self):
        """성능 보고서 생성"""
        print("\n" + "="*60)
        print("📊 최종 성능 벤치마크 보고서")
        print("="*60)

        total_time = time.time() - self.start_time
        print(f"⏱️  총 테스트 시간: {total_time:.2f}초")

        # 성능 목표 대비 평가
        performance_goals = {
            "single_prediction": {"target_ms": 2000, "description": "단일 예측 응답시간"},
            "concurrent_prediction": {"target_ms": 3000, "description": "동시 요청 응답시간"},
            "memory_usage": {"target_mb": 512, "description": "메모리 사용량"},
            "cpu_usage": {"target_percent": 50, "description": "평균 CPU 사용률"}
        }

        print(f"\n🎯 성능 목표 달성도:")
        for test_name, goal in performance_goals.items():
            if test_name in self.results:
                result = self.results[test_name]
                if test_name.endswith("_prediction"):
                    actual = result["duration_ms"]
                    target = goal["target_ms"]
                    achieved = actual <= target
                    print(f"   {'✅' if achieved else '❌'} {goal['description']}: {actual:.2f}ms (목표: {target}ms)")
                elif test_name == "memory_usage":
                    actual = result["details"]["rss_mb"]
                    target = goal["target_mb"]
                    achieved = actual <= target
                    print(f"   {'✅' if achieved else '❌'} {goal['description']}: {actual:.2f}MB (목표: {target}MB)")
                elif test_name == "cpu_usage":
                    actual = result["details"]["avg_percent"]
                    target = goal["target_percent"]
                    achieved = actual <= target
                    print(f"   {'✅' if achieved else '❌'} {goal['description']}: {actual:.2f}% (목표: {target}%)")

        # 최적화 권장사항
        print(f"\n💡 최적화 권장사항:")
        recommendations = []

        if "single_prediction" in self.results:
            duration_ms = self.results["single_prediction"]["duration_ms"]
            if duration_ms > 1000:
                recommendations.append("- ML 모델 추론 속도 최적화 필요 (모델 경량화, 배치 처리)")
            if duration_ms > 500:
                recommendations.append("- 예측 파이프라인 최적화 (전처리 단계 개선)")

        if "memory_usage" in self.results:
            memory_mb = self.results["memory_usage"]["details"]["rss_mb"]
            if memory_mb > 400:
                recommendations.append("- 메모리 사용량 최적화 (모델 로딩 전략, 캐시 크기 조정)")

        if "cache_performance" in self.results:
            hit_rate = self.results["cache_performance"]["details"]["cache_hit_rate"]
            if hit_rate < 80:
                recommendations.append("- 캐시 전략 개선 (TTL 조정, 캐시 키 최적화)")

        if recommendations:
            for rec in recommendations:
                print(f"   {rec}")
        else:
            print("   🎉 현재 성능이 모든 목표를 달성하고 있습니다!")

        # 결과를 JSON으로 저장
        with open("performance_benchmark_results.json", "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "total_test_time": total_time,
                "results": self.results,
                "recommendations": recommendations
            }, f, indent=2, ensure_ascii=False)

        print(f"\n💾 상세 결과가 'performance_benchmark_results.json'에 저장되었습니다.")

async def main():
    """메인 벤치마크 실행"""
    benchmark = PerformanceBenchmark()
    benchmark.start_monitoring()

    try:
        # 각 테스트 실행
        await benchmark.test_ml_prediction_performance()
        await benchmark.test_system_api_performance()
        benchmark.test_memory_usage()
        benchmark.test_cpu_usage()
        await benchmark.test_cache_performance()

        # 최종 보고서 생성
        benchmark.generate_performance_report()

    except Exception as e:
        print(f"❌ 벤치마크 실행 중 오류: {e}")

if __name__ == "__main__":
    asyncio.run(main())