#!/usr/bin/env python3
"""
워커 관리 스크립트
다양한 타입의 Celery 워커를 쉽게 시작, 중지, 모니터링할 수 있는 CLI 도구
"""

import argparse
import sys
import os
import time
import json
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.worker_manager import get_worker_manager, WorkerType
from core.priority_queue import get_priority_queue_manager

def print_header(title: str):
    """헤더 출력"""
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)

def print_worker_status():
    """워커 상태 출력"""
    print_header("🔍 워커 상태 조회")

    worker_manager = get_worker_manager()
    status = worker_manager.get_worker_status()

    print(f"📊 시스템 정보:")
    print(f"   CPU 코어: {status['system_info']['cpu_cores']}개")
    print(f"   메모리: {status['system_info']['memory_gb']}GB")
    print(f"   CPU 사용률: {status['system_info']['cpu_usage']:.1f}%")
    print(f"   메모리 사용률: {status['system_info']['memory_usage_percent']:.1f}%")
    print()

    print(f"🔧 실행 중인 워커: {status['total_workers']}개")

    if status['workers']:
        for worker_id, worker_info in status['workers'].items():
            status_icon = "🟢" if worker_info['is_running'] else "🔴"
            print(f"   {status_icon} {worker_info['worker_type']} (PID: {worker_info['pid']})")
            print(f"      큐: {', '.join(worker_info['queues'])}")
            print(f"      동시성: {worker_info['concurrency']}")
            print(f"      설명: {worker_info['description']}")
            print()
    else:
        print("   실행 중인 워커가 없습니다.")

    # 성능 권장사항
    recommendations = worker_manager.get_performance_recommendations()
    if recommendations:
        print("💡 성능 권장사항:")
        for rec in recommendations:
            print(f"   {rec}")

def start_workers(worker_types: list = None):
    """워커 시작"""
    print_header("🚀 워커 시작")

    worker_manager = get_worker_manager()

    if worker_types:
        # 특정 워커만 시작
        results = {}
        for worker_type_str in worker_types:
            try:
                worker_type = WorkerType(worker_type_str)
                process = worker_manager.start_worker(worker_type)
                results[worker_type_str] = process is not None
                time.sleep(2)  # 워커 간 시작 지연
            except ValueError:
                print(f"❌ 잘못된 워커 타입: {worker_type_str}")
                results[worker_type_str] = False
    else:
        # 모든 워커 시작
        results = worker_manager.start_all_workers()

    # 결과 출력
    success_count = sum(results.values())
    total_count = len(results)

    print(f"\n📊 워커 시작 결과: {success_count}/{total_count}")
    for worker_type, success in results.items():
        status_icon = "✅" if success else "❌"
        print(f"   {status_icon} {worker_type}")

def stop_workers():
    """모든 워커 중지"""
    print_header("🛑 워커 중지")

    worker_manager = get_worker_manager()
    results = worker_manager.stop_all_workers()

    if results:
        success_count = sum(results.values())
        total_count = len(results)

        print(f"📊 워커 중지 결과: {success_count}/{total_count}")
        for worker_id, success in results.items():
            status_icon = "✅" if success else "❌"
            print(f"   {status_icon} {worker_id}")
    else:
        print("실행 중인 워커가 없습니다.")

def show_priority_queues():
    """우선순위 큐 정보 출력"""
    print_header("📋 우선순위 큐 설정")

    pq_manager = get_priority_queue_manager()

    # 큐 우선순위 순서
    priority_order = pq_manager.get_queue_priority_order()
    print("🎯 큐 처리 우선순위 순서:")
    for i, queue_name in enumerate(priority_order, 1):
        print(f"   {i}. {queue_name}")
    print()

    # 작업별 설정
    print("📋 작업별 설정:")
    for task_name, task_info in pq_manager.task_configs.items():
        print(f"   🔧 {task_name}")
        print(f"      큐: {task_info.queue_name}")
        print(f"      우선순위: {task_info.priority.name} ({task_info.priority.value})")
        print(f"      최대 재시도: {task_info.max_retries}")
        print(f"      타임아웃: {task_info.timeout}초")
        print(f"      설명: {task_info.description}")
        print()

def show_system_info():
    """시스템 정보 상세 출력"""
    print_header("💻 시스템 정보")

    worker_manager = get_worker_manager()
    system_info = worker_manager.system_info

    print("🖥️ 하드웨어:")
    print(f"   CPU 코어: {system_info['cpu_cores']}개")
    print(f"   메모리: {system_info['memory_gb']}GB")
    print(f"   사용 가능한 메모리: {system_info['available_memory_gb']}GB")
    print()

    print("📊 현재 사용률:")
    print(f"   CPU: {system_info['cpu_usage']:.1f}%")
    print(f"   메모리: {system_info['memory_usage_percent']:.1f}%")
    print()

    # 워커 설정 최적화 제안
    recommendations = worker_manager.get_performance_recommendations()
    print("💡 최적화 권장사항:")
    for rec in recommendations:
        print(f"   {rec}")

def test_celery_connection():
    """Celery 연결 테스트"""
    print_header("🧪 Celery 연결 테스트")

    try:
        from core.celery_app import get_celery_app

        celery_app = get_celery_app()

        # 헬스체크 작업 실행
        print("📡 Celery 브로커 연결 테스트 중...")

        # Celery inspect를 통한 연결 테스트
        inspect = celery_app.control.inspect()

        # 활성 워커 확인
        active_workers = inspect.active()
        if active_workers:
            print("✅ Celery 브로커 연결 성공")
            print(f"📊 활성 워커: {len(active_workers)}개")
            for worker_name, tasks in active_workers.items():
                print(f"   🔧 {worker_name}: {len(tasks)}개 작업 실행 중")
        else:
            print("⚠️ 활성 워커가 없습니다. (연결은 정상)")

        # 등록된 작업 확인
        registered_tasks = inspect.registered()
        if registered_tasks:
            total_tasks = sum(len(tasks) for tasks in registered_tasks.values())
            print(f"📋 등록된 작업: {total_tasks}개")

        print("\n✅ Celery 시스템이 정상 작동 중입니다.")

    except Exception as e:
        print(f"❌ Celery 연결 실패: {e}")
        print("💡 확인사항:")
        print("   - Redis 서버가 실행 중인지 확인")
        print("   - 환경 변수 REDIS_URL이 올바른지 확인")
        print("   - 의존성이 모두 설치되었는지 확인")

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="Market Insights Pro 워커 관리 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python scripts/manage_workers.py status                    # 워커 상태 확인
  python scripts/manage_workers.py start                     # 모든 워커 시작
  python scripts/manage_workers.py start --types scraping    # 특정 워커만 시작
  python scripts/manage_workers.py stop                      # 모든 워커 중지
  python scripts/manage_workers.py queues                    # 우선순위 큐 정보
  python scripts/manage_workers.py system                    # 시스템 정보
  python scripts/manage_workers.py test                      # 연결 테스트

워커 타입:
  scraping_worker      - 스크래핑 전용 워커
  analysis_worker      - 분석 전용 워커
  notification_worker  - 알림 전용 워커
  statistics_worker    - 통계 전용 워커
  maintenance_worker   - 유지보수 전용 워커
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='사용 가능한 명령어')

    # status 명령어
    subparsers.add_parser('status', help='워커 상태 조회')

    # start 명령어
    start_parser = subparsers.add_parser('start', help='워커 시작')
    start_parser.add_argument(
        '--types',
        nargs='+',
        choices=[wt.value for wt in WorkerType],
        help='시작할 워커 타입 (기본값: 모든 워커)'
    )

    # stop 명령어
    subparsers.add_parser('stop', help='모든 워커 중지')

    # queues 명령어
    subparsers.add_parser('queues', help='우선순위 큐 정보 조회')

    # system 명령어
    subparsers.add_parser('system', help='시스템 정보 조회')

    # test 명령어
    subparsers.add_parser('test', help='Celery 연결 테스트')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == 'status':
            print_worker_status()
        elif args.command == 'start':
            start_workers(args.types)
        elif args.command == 'stop':
            stop_workers()
        elif args.command == 'queues':
            show_priority_queues()
        elif args.command == 'system':
            show_system_info()
        elif args.command == 'test':
            test_celery_connection()

    except KeyboardInterrupt:
        print("\n⏹️ 사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()