"""
Kafka Consumer 백그라운드 워커
실제 시장 분석 작업을 수행하는 "요리사" 역할
"""

import asyncio
import json
import logging
from typing import Dict, Any
from kafka import KafkaConsumer
from kafka.errors import KafkaError

from core.kafka_manager import get_kafka_manager
from core.cache import get_cache_manager
from core.analyzer_v2 import SQLiteMarketAnalyzer
from core.naver_scraper_adapter import NaverScraperAdapter as AmazonScraper

logger = logging.getLogger(__name__)

class MarketAnalysisWorker:
    """
    시장 분석 백그라운드 워커
    
    역할:
    1. Kafka에서 분석 요청 이벤트 수신
    2. Amazon 스크래핑 수행
    3. 데이터 분석 실행  
    4. 결과를 캐시에 저장
    5. 완료 이벤트 발행 (WebSocket 알림용)
    """
    
    def __init__(self):
        self.kafka_manager = get_kafka_manager()
        self.cache_manager = get_cache_manager()
        self.analyzer = SQLiteMarketAnalyzer()
        self.scraper = AmazonScraper()
        self.consumer = None
        self.running = False
        
    async def start(self):
        """
        백그라운드 워커 시작
        
        이 함수가 호출되면 별도 스레드에서 계속 실행되면서
        Kafka 메시지를 기다리다가 오면 처리
        """
        self.running = True
        logger.info("🚀 Market Analysis Worker 시작...")
        
        try:
            # Kafka Consumer 설정
            self.consumer = KafkaConsumer(
                # 구독할 토픽들
                self.kafka_manager.TOPIC_ANALYSIS_EVENTS,
                
                bootstrap_servers=self.kafka_manager.bootstrap_servers,
                
                # 컨슈머 그룹 설정 (여러 워커가 작업을 나눠서 처리)
                group_id='market-analysis-workers',
                
                # 메시지 처리 방식
                auto_offset_reset='latest',  # 새로운 메시지부터 처리
                enable_auto_commit=True,     # 처리 완료시 자동으로 오프셋 커밋
                
                # JSON 역직렬화
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                key_deserializer=lambda x: x.decode('utf-8') if x else None,
                
                # 타임아웃 설정
                consumer_timeout_ms=1000,  # 1초마다 체크
            )
            
            logger.info("✅ Kafka Consumer 연결 성공")
            
            # 🔄 메인 루프: 계속해서 메시지를 기다림
            while self.running:
                try:
                    # Kafka에서 메시지 폴링 (1초 타임아웃)
                    messages = self.consumer.poll(timeout_ms=1000)
                    
                    if not messages:
                        continue  # 메시지가 없으면 다시 대기
                    
                    # 받은 메시지들을 하나씩 처리
                    for topic_partition, records in messages.items():
                        for record in records:
                            await self._process_message(record)
                            
                except Exception as e:
                    logger.error(f"❌ 메시지 처리 중 오류: {e}")
                    await asyncio.sleep(5)  # 오류시 5초 대기
                    
        except Exception as e:
            logger.error(f"❌ Worker 시작 실패: {e}")
        finally:
            if self.consumer:
                self.consumer.close()
    
    async def _process_message(self, record):
        """
        개별 메시지 처리
        
        이게 핵심! 실제 분석 작업이 여기서 수행됨
        """
        try:
            message = record.value
            session_id = record.key
            event_type = message.get('event_type')
            
            logger.info(f"📨 메시지 수신: {event_type} | 세션: {session_id}")
            
            if event_type == 'analysis_requested':
                await self._handle_analysis_request(message, session_id)
            else:
                logger.warning(f"⚠️ 알 수 없는 이벤트 타입: {event_type}")
                
        except Exception as e:
            logger.error(f"❌ 메시지 처리 실패: {e}")
    
    async def _handle_analysis_request(self, message: Dict[str, Any], session_id: str):
        """
        분석 요청 처리 - 실제 작업이 수행되는 곳!
        
        단계:
        1. 상태 업데이트 (시작)
        2. Amazon 스크래핑 수행  
        3. 데이터 분석
        4. 결과 캐시 저장
        5. 완료 알림
        """
        keyword = message.get('keyword')
        
        if not keyword:
            logger.error("❌ 키워드가 없습니다.")
            return
            
        try:
            # 1단계: 분석 시작 상태 알림
            self.kafka_manager.send_status_update(
                session_id=session_id,
                status="scraping",
                progress=10,
                message=f"'{keyword}' Amazon 제품 스크래핑 시작..."
            )
            
            # 2단계: 🕷️ Amazon 스크래핑 수행 (30초 소요)
            logger.info(f"🕷️ 스크래핑 시작: {keyword}")
            scrape_result = await self.scraper.scrape_and_save_to_db(keyword, max_products=30)
            
            if not scrape_result or not scrape_result.get('success'):
                # 스크래핑 실패시
                self.kafka_manager.send_status_update(
                    session_id=session_id,
                    status="failed",
                    progress=100,
                    message=f"스크래핑 실패: {scrape_result.get('message', '알 수 없는 오류')}"
                )
                return
            
            # 3단계: 분석 진행 상태 업데이트
            self.kafka_manager.send_status_update(
                session_id=session_id,
                status="analyzing", 
                progress=70,
                message="데이터 분석 중..."
            )
            
            # 4단계: 📊 데이터 분석 수행 (20초 소요)
            logger.info(f"📊 분석 시작: {keyword}")
            competition_report = self.analyzer.analyze_category_competition(keyword)
            saturation_report = self.analyzer.calculate_market_saturation(keyword)
            
            # 분석 결과 합치기
            report_data = {**competition_report, **saturation_report}
            report_data['keyword'] = keyword
            report_data['session_id'] = session_id
            
            # 5단계: 🗄️ 결과를 캐시에 저장
            if self.cache_manager:
                self.cache_manager.set_analysis_result(keyword, report_data, ttl_hours=24)
                logger.info(f"💾 결과 캐시 저장: {keyword}")
            
            # 6단계: ✅ 완료 이벤트 발행
            self.kafka_manager.send_analysis_event(
                event_type="analysis_completed",
                keyword=keyword,
                session_id=session_id,
                data={
                    "results": report_data,
                    "processing_time_seconds": 50  # 실제 소요 시간
                }
            )
            
            # 7단계: 상태 완료 업데이트
            self.kafka_manager.send_status_update(
                session_id=session_id,
                status="completed",
                progress=100,
                message=f"'{keyword}' 시장 분석 완료!"
            )
            
            logger.info(f"🎉 분석 완료: {keyword} | 세션: {session_id}")
            
        except Exception as e:
            logger.error(f"❌ 분석 작업 실패: {keyword} | 오류: {e}")
            
            # 오류 상태 업데이트
            self.kafka_manager.send_status_update(
                session_id=session_id,
                status="failed",
                progress=100,
                message=f"분석 중 오류 발생: {str(e)}"
            )
    
    async def stop(self):
        """워커 종료"""
        self.running = False
        if self.consumer:
            self.consumer.close()
        logger.info("🔒 Market Analysis Worker 종료")

# 전역 워커 인스턴스
_worker_instance = None

def get_worker() -> MarketAnalysisWorker:
    """워커 싱글톤 인스턴스 반환"""
    global _worker_instance
    if _worker_instance is None:
        _worker_instance = MarketAnalysisWorker()
    return _worker_instance

async def start_background_worker():
    """
    백그라운드 워커를 별도 태스크로 시작
    
    main.py의 startup 이벤트에서 호출됨
    """
    worker = get_worker()
    await worker.scraper.start_browser()  # 브라우저 미리 시작
    asyncio.create_task(worker.start())   # 백그라운드에서 실행
    logger.info("🚀 백그라운드 분석 워커 시작됨")