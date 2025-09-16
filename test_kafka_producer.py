#!/usr/bin/env python3
"""
Kafka Producer 테스트 스크립트
구현된 KafkaManager의 각 기능을 테스트합니다.
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.kafka_manager import get_kafka_manager
import time

async def test_kafka_producer():
    print("🚀 Kafka Producer 테스트 시작...")
    
    # KafkaManager 인스턴스 생성
    kafka_manager = get_kafka_manager()
    
    # 1. 헬스체크 테스트
    print("\n1. 헬스체크 테스트")
    health = kafka_manager.health_check()
    print(f"   상태: {health}")
    
    if health['status'] != 'healthy':
        print("❌ Kafka 연결 실패")
        return False
    
    # 2. 분석 이벤트 전송 테스트
    print("\n2. 분석 이벤트 전송 테스트")
    try:
        session_id = kafka_manager.send_analysis_event(
            event_type="analysis_requested",
            keyword="test_keyword",
            data={"test": "data", "timestamp": time.time()}
        )
        print(f"   ✅ 분석 이벤트 전송 성공! Session ID: {session_id}")
    except Exception as e:
        print(f"   ❌ 분석 이벤트 전송 실패: {e}")
        return False
    
    # 3. 사용자 액션 이벤트 전송 테스트
    print("\n3. 사용자 액션 이벤트 전송 테스트")
    try:
        kafka_manager.send_user_action(
            user_id="test_user_123",
            action_type="page_view",
            page_url="/test-page",
            data={"browser": "test", "ip": "127.0.0.1"}
        )
        print("   ✅ 사용자 액션 이벤트 전송 성공!")
    except Exception as e:
        print(f"   ❌ 사용자 액션 이벤트 전송 실패: {e}")
        return False
    
    # 4. 알림 이벤트 전송 테스트
    print("\n4. 알림 이벤트 전송 테스트")
    try:
        kafka_manager.send_notification_event(
            notification_type="analysis_completed",
            recipient="test@example.com",
            subject="테스트 분석 완료",
            data={"keyword": "test_keyword", "results": {"score": 85}}
        )
        print("   ✅ 알림 이벤트 전송 성공!")
    except Exception as e:
        print(f"   ❌ 알림 이벤트 전송 실패: {e}")
        return False
    
    # 5. 배치 처리 테스트 (여러 이벤트 연속 전송)
    print("\n5. 배치 처리 테스트 (10개 이벤트 연속 전송)")
    try:
        start_time = time.time()
        for i in range(10):
            kafka_manager.send_user_action(
                user_id=f"batch_user_{i}",
                action_type="batch_test",
                page_url=f"/batch-test-{i}",
                data={"batch_id": i}
            )
        
        # 배치 처리 완료 대기
        await asyncio.sleep(2)
        
        end_time = time.time()
        print(f"   ✅ 배치 처리 완료! 소요시간: {end_time - start_time:.2f}초")
    except Exception as e:
        print(f"   ❌ 배치 처리 실패: {e}")
        return False
    
    # 6. 통계 이벤트 전송 테스트
    print("\n6. 통계 이벤트 전송 테스트")
    try:
        kafka_manager.send_statistics_event(
            stat_type="system_metric",
            data={
                "metric_name": "cpu_usage",
                "value": 75.5,
                "timestamp": time.time()
            }
        )
        print("   ✅ 통계 이벤트 전송 성공!")
    except Exception as e:
        print(f"   ❌ 통계 이벤트 전송 실패: {e}")
        return False
    
    print(f"\n🎉 모든 Producer 테스트 통과!")
    return True

if __name__ == "__main__":
    success = asyncio.run(test_kafka_producer())
    if success:
        print("\n✅ Kafka Producer 테스트 완료")
    else:
        print("\n❌ Kafka Producer 테스트 실패")
        sys.exit(1)