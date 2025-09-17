#!/usr/bin/env python3
"""
라우팅 키 기반 작업 분산 테스트
Topic Exchange를 사용한 라우팅 시스템 검증
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.priority_queue import get_priority_queue_manager
from core.celery_app import get_celery_app
import json

def test_routing_configuration():
    """라우팅 설정 테스트"""
    print("🔧 라우팅 키 설정 테스트")
    print("=" * 60)

    pq_manager = get_priority_queue_manager()
    routes = pq_manager.get_celery_route_config()

    print(f"📋 총 {len(routes)}개 작업 라우팅 설정:")
    print()

    for task_name, route_config in routes.items():
        print(f"🔧 {task_name}")
        print(f"   Exchange: {route_config['exchange']}")
        print(f"   Exchange Type: {route_config['exchange_type']}")
        print(f"   Routing Key: {route_config['routing_key']}")
        print(f"   Queue: {route_config['queue']}")
        print(f"   Priority: {route_config['priority']}")
        print()

def test_routing_patterns():
    """라우팅 키 패턴 테스트"""
    print("🎯 라우팅 키 패턴 분석")
    print("=" * 60)

    pq_manager = get_priority_queue_manager()
    routes = pq_manager.get_celery_route_config()

    # 우선순위별 그룹화
    priority_groups = {}
    queue_groups = {}

    for task_name, route_config in routes.items():
        routing_key = route_config['routing_key']
        queue = route_config['queue']
        priority = route_config['priority']

        # 라우팅 키 분석 (priority.queue.task)
        parts = routing_key.split('.')
        if len(parts) >= 3:
            priority_name = parts[0]
            queue_name = parts[1]
            task_name_short = parts[2]

            if priority_name not in priority_groups:
                priority_groups[priority_name] = []
            priority_groups[priority_name].append(routing_key)

            if queue_name not in queue_groups:
                queue_groups[queue_name] = []
            queue_groups[queue_name].append(routing_key)

    # 우선순위별 출력
    print("📊 우선순위별 라우팅 키:")
    for priority, keys in sorted(priority_groups.items()):
        print(f"   {priority.upper()}: {len(keys)}개 작업")
        for key in sorted(keys):
            print(f"      - {key}")
        print()

    # 큐별 출력
    print("📦 큐별 라우팅 키:")
    for queue, keys in sorted(queue_groups.items()):
        print(f"   {queue}: {len(keys)}개 작업")
        for key in sorted(keys):
            print(f"      - {key}")
        print()

def test_worker_routing_patterns():
    """워커 라우팅 패턴 테스트"""
    print("👷 워커 라우팅 패턴 분석")
    print("=" * 60)

    from core.worker_manager import get_worker_manager, WorkerType

    worker_manager = get_worker_manager()

    for worker_type in WorkerType:
        config = worker_manager.worker_configs[worker_type]
        print(f"🔧 {worker_type.value}")
        print(f"   처리 큐: {', '.join(config.queues)}")
        print(f"   설명: {config.description}")

        # 각 큐에 대한 라우팅 패턴 생성
        print("   수신 가능한 라우팅 패턴:")
        for queue in config.queues:
            patterns = [
                f'critical.{queue}.*',
                f'high.{queue}.*',
                f'normal.{queue}.*',
                f'low.{queue}.*',
                f'batch.{queue}.*'
            ]
            for pattern in patterns:
                print(f"      - {pattern}")
        print()

def test_routing_simulation():
    """라우팅 시뮬레이션 테스트"""
    print("🎮 라우팅 시뮬레이션")
    print("=" * 60)

    # 가상 시나리오
    scenarios = [
        {
            "task": "scrape_product_data",
            "priority": "high",
            "queue": "scraping",
            "description": "사용자 요청 스크래핑 작업"
        },
        {
            "task": "analyze_market_data",
            "priority": "high",
            "queue": "analysis",
            "description": "시장 분석 작업"
        },
        {
            "task": "send_notification_email",
            "priority": "normal",
            "queue": "notifications",
            "description": "이메일 알림 발송"
        },
        {
            "task": "update_statistics",
            "priority": "low",
            "queue": "statistics",
            "description": "통계 업데이트"
        },
        {
            "task": "cleanup_old_data",
            "priority": "batch",
            "queue": "maintenance",
            "description": "데이터 정리"
        }
    ]

    pq_manager = get_priority_queue_manager()
    routes = pq_manager.get_celery_route_config()

    print("📨 작업별 라우팅 시뮬레이션:")
    for scenario in scenarios:
        task_key = f"core.tasks.{scenario['task']}"
        if task_key in routes:
            route = routes[task_key]
            routing_key = route['routing_key']

            print(f"🔧 {scenario['description']}")
            print(f"   작업: {scenario['task']}")
            print(f"   라우팅 키: {routing_key}")
            print(f"   Exchange: {route['exchange']} ({route['exchange_type']})")
            print(f"   큐: {route['queue']}")
            print(f"   우선순위: {route['priority']}")

            # 어떤 워커가 처리할지 예측
            queue_name = route['queue']
            suitable_workers = []

            from core.worker_manager import WorkerType, get_worker_manager
            worker_manager = get_worker_manager()

            for worker_type in WorkerType:
                config = worker_manager.worker_configs[worker_type]
                if queue_name in config.queues:
                    suitable_workers.append(worker_type.value)

            if suitable_workers:
                print(f"   처리 워커: {', '.join(suitable_workers)}")
            else:
                print(f"   ⚠️ 처리할 워커 없음!")

            print()

def test_celery_configuration():
    """Celery 설정 확인"""
    print("⚙️ Celery 설정 확인")
    print("=" * 60)

    try:
        celery_app = get_celery_app()

        print("📋 Celery 앱 설정:")
        print(f"   Exchange: {celery_app.conf.task_default_exchange}")
        print(f"   Exchange Type: {celery_app.conf.task_default_exchange_type}")
        print(f"   Default Queue: {celery_app.conf.task_default_queue}")
        print(f"   Default Routing Key: {celery_app.conf.task_default_routing_key}")
        print()

        # 라우팅 설정 확인
        routes = celery_app.conf.task_routes
        if routes:
            print(f"📨 활성 라우팅 설정: {len(routes)}개")
            print("   주요 라우팅:")
            for task, route in list(routes.items())[:5]:  # 처음 5개만 표시
                if isinstance(route, dict):
                    routing_key = route.get('routing_key', 'N/A')
                    queue = route.get('queue', 'N/A')
                    print(f"      {task} → {routing_key} → {queue}")
        else:
            print("⚠️ 라우팅 설정이 적용되지 않았습니다.")

        print("\n✅ Celery 설정 확인 완료")

    except Exception as e:
        print(f"❌ Celery 설정 확인 실패: {e}")

def main():
    """메인 함수"""
    print("🚀 라우팅 키 기반 작업 분산 테스트")
    print("=" * 80)
    print()

    test_routing_configuration()
    print()

    test_routing_patterns()
    print()

    test_worker_routing_patterns()
    print()

    test_routing_simulation()
    print()

    test_celery_configuration()
    print()

    print("🎉 라우팅 시스템 테스트 완료!")
    print()
    print("💡 다음 단계:")
    print("   1. Redis와 Kafka 서비스 시작")
    print("   2. Celery 워커 시작: python scripts/manage_workers.py start")
    print("   3. 작업 테스트: python test_kafka_producer.py")

if __name__ == '__main__':
    main()