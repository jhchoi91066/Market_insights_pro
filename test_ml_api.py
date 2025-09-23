#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML 예측 API 테스트 클라이언트
실시간 가격 예측 API의 기능을 테스트합니다.
"""

import asyncio
import aiohttp
import json
from datetime import datetime

BASE_URL = "http://127.0.0.1:8001"

async def test_price_prediction():
    """단일 가격 예측 테스트"""
    print("🧪 단일 가격 예측 테스트")
    print("=" * 50)

    prediction_request = {
        "category": "컴퓨터/IT",
        "brand": "Logitech",
        "seller": "Coupang",
        "search_keyword": "무선마우스",
        "maker": "Logitech",
        "rating": 4.5,
        "review_count": 250,
        "price_to_category_avg_ratio": 1.2,
        "price_to_keyword_avg_ratio": 1.1,
        "rating_x_review_count": 1125.0
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{BASE_URL}/api/ml/predict/price",
                json=prediction_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ 예측 성공!")
                    print(f"   📊 예측 가격: ${result['predicted_price']:.2f}")
                    print(f"   📈 신뢰구간: ${result['confidence_interval']['lower']:.2f} - ${result['confidence_interval']['upper']:.2f}")
                    print(f"   ⏱️  처리시간: {result['processing_time_ms']:.2f}ms")
                    print(f"   🏷️  모델 버전: {result['model_version']}")
                    print(f"   🕐 예측 시간: {result['prediction_timestamp']}")
                else:
                    error = await response.text()
                    print(f"❌ 예측 실패 ({response.status}): {error}")

        except Exception as e:
            print(f"❌ 연결 오류: {e}")

async def test_batch_prediction():
    """배치 가격 예측 테스트"""
    print("\n🧪 배치 가격 예측 테스트")
    print("=" * 50)

    batch_request = {
        "products": [
            {
                "category": "컴퓨터/IT",
                "brand": "Logitech",
                "search_keyword": "무선마우스",
                "rating": 4.5,
                "review_count": 200
            },
            {
                "category": "컴퓨터/IT",
                "brand": "Samsung",
                "search_keyword": "모니터",
                "rating": 4.2,
                "review_count": 150
            },
            {
                "category": "가전디지털",
                "brand": "Apple",
                "search_keyword": "이어폰",
                "rating": 4.8,
                "review_count": 500
            }
        ],
        "use_cache": True
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{BASE_URL}/api/ml/predict/batch",
                json=batch_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ 배치 예측 성공!")
                    print(f"   📦 처리된 상품 수: {result['total_processed']}")
                    print(f"   🎯 캐시 히트: {result['cache_hits']}")
                    print(f"   ⏱️  전체 처리시간: {result['processing_time_ms']:.2f}ms")

                    print(f"\n📊 예측 결과:")
                    for i, prediction in enumerate(result['predictions']):
                        print(f"   상품 {i+1}: ${prediction['predicted_price']:.2f} "
                              f"(처리시간: {prediction['processing_time_ms']:.2f}ms)")
                else:
                    error = await response.text()
                    print(f"❌ 배치 예측 실패 ({response.status}): {error}")

        except Exception as e:
            print(f"❌ 연결 오류: {e}")

async def test_model_info():
    """모델 정보 조회 테스트"""
    print("\n🧪 모델 정보 조회 테스트")
    print("=" * 50)

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{BASE_URL}/api/ml/model/price_predictor/info") as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ 모델 정보 조회 성공!")
                    print(f"   📝 모델명: {result['model_name']}")
                    print(f"   🏷️  버전: {result['model_version']}")
                    print(f"   🎭 스테이지: {result['model_stage']}")
                    print(f"   🕐 마지막 업데이트: {result['last_updated']}")

                    if result['performance_metrics']:
                        print(f"   📊 성능 메트릭:")
                        for metric_name, value in result['performance_metrics'].items():
                            print(f"      - {metric_name}: {value}")
                else:
                    error = await response.text()
                    print(f"❌ 모델 정보 조회 실패 ({response.status}): {error}")

        except Exception as e:
            print(f"❌ 연결 오류: {e}")

async def test_health_check():
    """ML 서비스 헬스 체크 테스트"""
    print("\n🧪 ML 서비스 헬스 체크 테스트")
    print("=" * 50)

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{BASE_URL}/api/ml/health") as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ ML 서비스 상태: {result['status']}")
                    print(f"   🕐 체크 시간: {result['timestamp']}")
                    print(f"   🤖 로드된 모델: {', '.join(result['loaded_models'])}")
                    print(f"   📊 모델 수: {result['model_count']}")
                    print(f"   🔗 MLflow 연결: {result['mlflow_connection']}")
                    print(f"   💾 캐시 연결: {result['cache_connection']}")

                    if 'test_prediction' in result:
                        print(f"   🧪 테스트 예측: ${result['test_prediction']:.2f}")

                elif response.status == 503:
                    error = await response.json()
                    print(f"⚠️  ML 서비스 불안정: {error}")
                else:
                    error = await response.text()
                    print(f"❌ 헬스 체크 실패 ({response.status}): {error}")

        except Exception as e:
            print(f"❌ 연결 오류: {e}")

async def main():
    """메인 테스트 실행"""
    print("🚀 ML 예측 API 테스트 시작")
    print(f"🔗 서버 URL: {BASE_URL}")
    print(f"🕐 테스트 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 각 테스트 실행
    await test_health_check()
    await test_price_prediction()
    await test_batch_prediction()
    await test_model_info()

    print("\n✨ 모든 테스트 완료!")

if __name__ == "__main__":
    asyncio.run(main())