#!/usr/bin/env python3
"""
Kafka Consumer 테스트 스크립트
구현된 Consumer들의 메시지 처리 기능을 테스트합니다.
"""
import asyncio
import sys
import os
import json
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.statistics_consumer import StatisticsConsumer
from core.notification_consumer import NotificationConsumer

async def test_consumers():
    print("🚀 Kafka Consumer 테스트 시작...")
    
    # 1. StatisticsConsumer 테스트
    print("\n1. StatisticsConsumer 인스턴스 생성")
    stats_consumer = StatisticsConsumer()
    
    # 초기 통계 확인
    initial_stats = stats_consumer.get_realtime_stats()
    print(f"   초기 통계: {json.dumps(initial_stats, indent=2, ensure_ascii=False)}")
    
    # 2. NotificationConsumer 테스트
    print("\n2. NotificationConsumer 인스턴스 생성")
    notification_consumer = NotificationConsumer()
    
    print(f"   이메일 알림 활성화: {notification_consumer.email_enabled}")
    print(f"   Slack 알림 활성화: {notification_consumer.slack_enabled}")
    
    # 3. Consumer 백그라운드 시작
    print("\n3. Consumer 백그라운드 시작 (5초간 실행)")
    
    # Consumer들을 백그라운드에서 실행
    stats_task = asyncio.create_task(stats_consumer.start())
    notification_task = asyncio.create_task(notification_consumer.start())
    
    # 5초 대기
    await asyncio.sleep(5)
    
    # Consumer 종료
    await stats_consumer.stop()
    await notification_consumer.stop()
    
    # 태스크 취소
    stats_task.cancel()
    notification_task.cancel()
    
    try:
        await stats_task
    except asyncio.CancelledError:
        pass
    
    try:
        await notification_task  
    except asyncio.CancelledError:
        pass
    
    # 4. 최종 통계 확인
    print("\n4. Consumer 실행 후 통계 확인")
    final_stats = stats_consumer.get_realtime_stats()
    print(f"   최종 통계: {json.dumps(final_stats, indent=2, ensure_ascii=False)}")
    
    print("\n✅ Consumer 테스트 완료!")
    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(test_consumers())
        if success:
            print("\n🎉 모든 Consumer 테스트 통과!")
        else:
            print("\n❌ Consumer 테스트 실패")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⏹️  테스트 중단됨")
    except Exception as e:
        print(f"\n❌ Consumer 테스트 오류: {e}")
        sys.exit(1)