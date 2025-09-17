"""
Celery 비동기 작업 정의
무거운 작업들을 백그라운드에서 처리하여 사용자 경험 향상
"""

import logging
import asyncio
import traceback
from datetime import datetime
from typing import Dict, Any, Optional, List
from celery import current_task
from core.celery_app import celery_app
from core.cache import get_cache_manager
from core.task_tracker import get_task_tracker

logger = logging.getLogger(__name__)

# ================================
# 🕷️ 스크래핑 관련 작업
# ================================

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def scrape_product_data(self, keyword: str, max_products: int = 30) -> Dict[str, Any]:
    """
    Amazon 제품 데이터 스크래핑 (비동기)

    기존의 동기 스크래핑을 비동기로 변환하여 사용자가 기다리지 않도록 함

    Args:
        keyword: 검색 키워드
        max_products: 최대 수집 제품 수

    Returns:
        dict: 스크래핑 결과 및 상태
    """
    task_id = self.request.id
    tracker = get_task_tracker()

    # 작업 추적 생성
    tracker.create_task(
        task_id=task_id,
        task_name="scrape_product_data",
        total=100,
        metadata={'keyword': keyword, 'max_products': max_products}
    )

    try:
        # 작업 시작
        tracker.start_task(task_id, f'Starting Amazon scraping for "{keyword}"')

        # 실제 스크래핑 로직 (기존 코드 재사용)
        from core.scraper import AmazonScraper

        scraper = AmazonScraper()

        # 진행률 업데이트 (20%)
        tracker.update_progress(task_id, 20, 'Initializing browser...')

        # 브라우저 시작 (동기 함수를 비동기로 실행)
        asyncio.run(scraper.start_browser())

        # 진행률 업데이트 (40%)
        tracker.update_progress(task_id, 40, 'Scraping product data...')

        # 스크래핑 실행
        result = asyncio.run(scraper.scrape_and_save_to_db(keyword, max_products))

        # 진행률 업데이트 (80%)
        tracker.update_progress(task_id, 80, 'Saving to database...')

        # 브라우저 정리
        asyncio.run(scraper.close_browser())

        # 작업 완료
        tracker.complete_task(
            task_id=task_id,
            success=True,
            message="Scraping completed successfully",
            result_data={'result': result}
        )

        logger.info(f"✅ 스크래핑 완료: {keyword}, 결과: {result}")

        return {
            'task_id': task_id,
            'keyword': keyword,
            'status': 'completed',
            'result': result,
            'completed_at': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 스크래핑 실패: {keyword}, 오류: {e}")
        logger.error(traceback.format_exc())

        # 재시도 로직
        if self.request.retries < self.max_retries:
            retry_count = self.request.retries + 1
            tracker.retry_task(task_id, retry_count, f"Retrying... ({retry_count}/{self.max_retries})")
            logger.info(f"🔄 재시도 중... ({retry_count}/{self.max_retries})")
            raise self.retry(countdown=60, exc=e)

        # 최종 실패
        tracker.complete_task(
            task_id=task_id,
            success=False,
            message="Scraping failed after all retries",
            error_message=str(e)
        )

        return {
            'task_id': task_id,
            'keyword': keyword,
            'status': 'failed',
            'error': str(e),
            'failed_at': datetime.now().isoformat()
        }

@celery_app.task(bind=True)
def scrape_and_analyze(self, keyword: str, max_products: int = 30) -> Dict[str, Any]:
    """
    스크래핑 + 분석 통합 작업

    스크래핑과 분석을 한 번에 처리하여 효율성 향상
    """
    task_id = self.request.id

    try:
        # 1단계: 스크래핑
        self.update_state(
            state='PROGRESS',
            meta={'current': 10, 'total': 100, 'status': 'Starting data collection...'}
        )

        scraping_result = scrape_product_data.apply_async(
            args=[keyword, max_products]
        ).get()  # 동기적으로 기다림

        if scraping_result['status'] != 'completed':
            raise Exception(f"Scraping failed: {scraping_result.get('error')}")

        # 2단계: 분석
        self.update_state(
            state='PROGRESS',
            meta={'current': 60, 'total': 100, 'status': 'Analyzing market data...'}
        )

        analysis_result = analyze_market_data.apply_async(
            args=[keyword]
        ).get()

        # 3단계: 캐시 저장
        self.update_state(
            state='PROGRESS',
            meta={'current': 90, 'total': 100, 'status': 'Saving results...'}
        )

        # 결과를 캐시에 저장
        try:
            cache_manager = get_cache_manager()
            if cache_manager and analysis_result['status'] == 'completed':
                cache_manager.set_analysis_result(
                    keyword,
                    analysis_result['result'],
                    ttl_hours=24
                )
        except Exception as cache_error:
            logger.warning(f"⚠️ 캐시 저장 실패: {cache_error}")

        return {
            'task_id': task_id,
            'keyword': keyword,
            'status': 'completed',
            'scraping_result': scraping_result,
            'analysis_result': analysis_result,
            'completed_at': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 통합 작업 실패: {keyword}, 오류: {e}")
        return {
            'task_id': task_id,
            'keyword': keyword,
            'status': 'failed',
            'error': str(e),
            'failed_at': datetime.now().isoformat()
        }

# ================================
# 📊 분석 관련 작업
# ================================

@celery_app.task(bind=True)
def analyze_market_data(self, keyword: str) -> Dict[str, Any]:
    """
    시장 데이터 분석 (비동기)

    기존의 동기 분석을 비동기로 변환
    """
    task_id = self.request.id

    try:
        self.update_state(
            state='PROGRESS',
            meta={'current': 10, 'total': 100, 'status': f'Analyzing market for "{keyword}"'}
        )

        # 기존 분석 로직 재사용
        from core.analyzer_v2 import SQLiteMarketAnalyzer

        analyzer = SQLiteMarketAnalyzer()

        # 진행률 업데이트 (30%)
        self.update_state(
            state='PROGRESS',
            meta={'current': 30, 'total': 100, 'status': 'Analyzing competition...'}
        )

        competition_report = analyzer.analyze_category_competition(keyword)

        # 진행률 업데이트 (60%)
        self.update_state(
            state='PROGRESS',
            meta={'current': 60, 'total': 100, 'status': 'Calculating market saturation...'}
        )

        saturation_report = analyzer.calculate_market_saturation(keyword)

        # 진행률 업데이트 (90%)
        self.update_state(
            state='PROGRESS',
            meta={'current': 90, 'total': 100, 'status': 'Generating final report...'}
        )

        # 결과 병합
        final_report = {**competition_report, **saturation_report}
        final_report['keyword'] = keyword
        final_report['analyzed_at'] = datetime.now().isoformat()

        logger.info(f"✅ 분석 완료: {keyword}")

        return {
            'task_id': task_id,
            'keyword': keyword,
            'status': 'completed',
            'result': final_report,
            'completed_at': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 분석 실패: {keyword}, 오류: {e}")
        return {
            'task_id': task_id,
            'keyword': keyword,
            'status': 'failed',
            'error': str(e),
            'failed_at': datetime.now().isoformat()
        }

@celery_app.task(bind=True)
def generate_report(self, keyword: str, template: str = "standard") -> Dict[str, Any]:
    """
    보고서 생성 작업

    분석 결과를 기반으로 사용자 친화적인 보고서 생성
    """
    task_id = self.request.id

    try:
        # 분석 결과 가져오기
        analysis_result = analyze_market_data.apply_async(args=[keyword]).get()

        if analysis_result['status'] != 'completed':
            raise Exception("Analysis failed")

        # 보고서 템플릿 적용
        report_data = analysis_result['result']

        # 템플릿별 추가 처리
        if template == "detailed":
            # 상세 보고서 추가 데이터
            report_data['detailed_metrics'] = True
            report_data['recommendations'] = _generate_recommendations(report_data)

        return {
            'task_id': task_id,
            'keyword': keyword,
            'status': 'completed',
            'report': report_data,
            'template': template,
            'generated_at': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 보고서 생성 실패: {keyword}, 오류: {e}")
        return {
            'task_id': task_id,
            'keyword': keyword,
            'status': 'failed',
            'error': str(e),
            'failed_at': datetime.now().isoformat()
        }

# ================================
# 📧 알림 관련 작업
# ================================

@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
def send_notification_email(self, recipient: str, subject: str,
                          message: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    이메일 알림 발송 (비동기)

    분석 완료, 오류 발생 등의 상황에서 사용자에게 이메일 전송
    """
    task_id = self.request.id

    try:
        # 실제 이메일 발송 로직 (NotificationConsumer 재사용)
        from core.notification_consumer import NotificationConsumer

        notification_consumer = NotificationConsumer()

        # 이메일 발송
        success = notification_consumer._send_email(
            recipient=recipient,
            subject=subject,
            message=message,
            data=data or {}
        )

        if not success:
            raise Exception("Email sending failed")

        logger.info(f"✅ 이메일 발송 완료: {recipient}")

        return {
            'task_id': task_id,
            'recipient': recipient,
            'subject': subject,
            'status': 'sent',
            'sent_at': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 이메일 발송 실패: {recipient}, 오류: {e}")

        # 재시도 로직
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=30, exc=e)

        return {
            'task_id': task_id,
            'recipient': recipient,
            'status': 'failed',
            'error': str(e),
            'failed_at': datetime.now().isoformat()
        }

@celery_app.task(bind=True, max_retries=3)
def send_slack_notification(self, channel: str, message: str,
                          data: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Slack 알림 발송 (비동기)
    """
    task_id = self.request.id

    try:
        from core.notification_consumer import NotificationConsumer

        notification_consumer = NotificationConsumer()

        # Slack 메시지 발송
        success = notification_consumer._send_slack_message(
            message=message,
            data=data or {}
        )

        if not success:
            raise Exception("Slack notification failed")

        logger.info(f"✅ Slack 알림 발송 완료: {channel}")

        return {
            'task_id': task_id,
            'channel': channel,
            'status': 'sent',
            'sent_at': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Slack 알림 실패: {channel}, 오류: {e}")

        if self.request.retries < self.max_retries:
            raise self.retry(countdown=30, exc=e)

        return {
            'task_id': task_id,
            'channel': channel,
            'status': 'failed',
            'error': str(e),
            'failed_at': datetime.now().isoformat()
        }

# ================================
# 📈 통계 및 유지보수 작업
# ================================

@celery_app.task(bind=True)
def update_statistics(self, metric_name: str, metric_value: Any,
                     tags: Dict[str, str] = None) -> Dict[str, Any]:
    """
    시스템 통계 업데이트 (비동기)

    성능 지표, 사용량 통계 등을 백그라운드에서 처리
    """
    task_id = self.request.id

    try:
        from core.statistics_consumer import StatisticsConsumer

        stats_consumer = StatisticsConsumer()

        # 통계 데이터 처리
        stats_data = {
            'metric_name': metric_name,
            'metric_value': metric_value,
            'tags': tags or {},
            'timestamp': datetime.now().isoformat()
        }

        # 통계 저장 (기존 로직 재사용)
        stats_consumer._process_statistics(stats_data)

        logger.info(f"✅ 통계 업데이트 완료: {metric_name} = {metric_value}")

        return {
            'task_id': task_id,
            'metric_name': metric_name,
            'status': 'updated',
            'updated_at': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 통계 업데이트 실패: {metric_name}, 오류: {e}")
        return {
            'task_id': task_id,
            'metric_name': metric_name,
            'status': 'failed',
            'error': str(e),
            'failed_at': datetime.now().isoformat()
        }

@celery_app.task(bind=True)
def cleanup_old_data(self, days_old: int = 30) -> Dict[str, Any]:
    """
    오래된 데이터 정리 작업

    주기적으로 실행하여 디스크 공간 확보
    """
    task_id = self.request.id

    try:
        from datetime import timedelta
        from core.models import get_session, Product

        cutoff_date = datetime.now() - timedelta(days=days_old)

        with get_session() as session:
            # 오래된 제품 데이터 삭제
            deleted_count = session.query(Product).filter(
                Product.created_at < cutoff_date
            ).delete()

            session.commit()

        logger.info(f"✅ 데이터 정리 완료: {deleted_count}개 레코드 삭제")

        return {
            'task_id': task_id,
            'status': 'completed',
            'deleted_records': deleted_count,
            'cutoff_date': cutoff_date.isoformat(),
            'completed_at': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ 데이터 정리 실패: {e}")
        return {
            'task_id': task_id,
            'status': 'failed',
            'error': str(e),
            'failed_at': datetime.now().isoformat()
        }

# ================================
# 🛠️ 유틸리티 함수
# ================================

def _generate_recommendations(report_data: Dict[str, Any]) -> List[str]:
    """
    분석 결과를 기반으로 추천사항 생성
    """
    recommendations = []

    # 진입 장벽 점수 기반 추천
    entry_barrier = report_data.get('entry_barrier_score', 5)
    if entry_barrier < 3:
        recommendations.append("🟢 낮은 진입 장벽 - 시장 진입 추천")
    elif entry_barrier > 7:
        recommendations.append("🔴 높은 진입 장벽 - 신중한 접근 필요")
    else:
        recommendations.append("🟡 보통 수준 진입 장벽 - 차별화 전략 필요")

    # 경쟁 강도 기반 추천
    competitor_count = report_data.get('competitor_count', 0)
    if competitor_count < 10:
        recommendations.append("💡 경쟁이 적은 시장 - 선점 기회")
    elif competitor_count > 50:
        recommendations.append("⚠️ 경쟁이 치열한 시장 - 틈새 전략 고려")

    # 가격 전략 추천
    avg_price = report_data.get('avg_price', 0)
    if avg_price > 100:
        recommendations.append("💰 고가 시장 - 프리미엄 전략 고려")
    elif avg_price < 20:
        recommendations.append("🏷️ 저가 시장 - 대량 판매 전략 적합")

    return recommendations

# ================================
# 🔧 작업 상태 조회 함수
# ================================

def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    작업 상태 조회

    Args:
        task_id: Celery 작업 ID

    Returns:
        dict: 작업 상태 정보
    """
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=celery_app)

    return {
        'task_id': task_id,
        'status': result.status,
        'result': result.result,
        'info': result.info,
        'successful': result.successful(),
        'failed': result.failed()
    }

def get_active_tasks() -> List[Dict[str, Any]]:
    """
    현재 실행 중인 작업 목록 조회
    """
    inspect = celery_app.control.inspect()
    active_tasks = inspect.active()

    if not active_tasks:
        return []

    all_tasks = []
    for worker, tasks in active_tasks.items():
        for task in tasks:
            all_tasks.append({
                'worker': worker,
                'task_id': task['id'],
                'name': task['name'],
                'args': task['args'],
                'kwargs': task['kwargs'],
                'time_start': task['time_start']
            })

    return all_tasks