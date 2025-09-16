"""
NotificationConsumer - 알림 전송 전용 Consumer
이메일, 슬랙, 웹푸시 등 다양한 채널로 사용자에게 알림을 발송합니다.
"""

import asyncio
import json
import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
from kafka import KafkaConsumer
from kafka.errors import KafkaError
import requests

# 환경 변수 (실제 운영시에는 .env 파일이나 환경변수로 관리)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_USER = ""  # 실제 설정 필요
EMAIL_PASSWORD = ""  # 실제 설정 필요
SLACK_WEBHOOK_URL = ""  # 실제 설정 필요

logger = logging.getLogger(__name__)

class NotificationConsumer:
    """
    알림 전송 Consumer
    
    처리하는 알림 타입:
    1. analysis_completed - 분석 완료 알림
    2. analysis_failed - 분석 실패 알림  
    3. system_alert - 시스템 경고
    4. welcome - 신규 사용자 환영
    """
    
    def __init__(self, bootstrap_servers='localhost:9092'):
        self.bootstrap_servers = bootstrap_servers
        self.consumer = None
        self.running = False
        
        # 알림 채널별 설정
        self.email_enabled = bool(EMAIL_USER and EMAIL_PASSWORD)
        self.slack_enabled = bool(SLACK_WEBHOOK_URL)
        
        # 알림 템플릿
        self.notification_templates = {
            'analysis_completed': {
                'email_subject': '🎉 Market Analysis Complete - {keyword}',
                'email_body': '''
                Hello!
                
                Your market analysis for "{keyword}" has been completed successfully.
                
                📊 Results Summary:
                - Competitor Count: {competitor_count}
                - Market Entry Barrier: {difficulty_score}/10
                - Analysis Duration: {duration} seconds
                
                View your detailed report: {report_url}
                
                Best regards,
                Market Insights Pro Team
                ''',
                'slack_message': '🎉 Analysis complete for "{keyword}" - Entry barrier: {difficulty_score}/10'
            },
            'analysis_failed': {
                'email_subject': '❌ Market Analysis Failed - {keyword}',
                'email_body': '''
                Hello,
                
                Unfortunately, your market analysis for "{keyword}" could not be completed.
                
                Error: {error_message}
                
                Please try again or contact support if the issue persists.
                
                Best regards,
                Market Insights Pro Team
                ''',
                'slack_message': '❌ Analysis failed for "{keyword}": {error_message}'
            },
            'welcome': {
                'email_subject': '🚀 Welcome to Market Insights Pro!',
                'email_body': '''
                Welcome to Market Insights Pro!
                
                Thank you for joining our platform. You can now:
                ✅ Analyze Amazon market competition
                ✅ Get real-time market insights
                ✅ Track competitor pricing
                
                Get started: {dashboard_url}
                
                Best regards,
                Market Insights Pro Team
                ''',
                'slack_message': '🚀 New user joined Market Insights Pro!'
            }
        }
    
    async def start(self):
        """Consumer 시작"""
        self.running = True
        logger.info("🚀 NotificationConsumer 시작...")
        
        try:
            # Kafka Consumer 설정
            self.consumer = KafkaConsumer(
                'user-notifications',  # 알림 전용 토픽
                
                bootstrap_servers=self.bootstrap_servers,
                group_id='notification-consumers',  # 알림 Consumer 그룹
                auto_offset_reset='latest',
                enable_auto_commit=True,
                
                # JSON 역직렬화
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                key_deserializer=lambda x: x.decode('utf-8') if x else None,
                
                consumer_timeout_ms=1000,
            )
            
            logger.info("✅ NotificationConsumer Kafka 연결 성공")
            
            # 메인 처리 루프
            while self.running:
                try:
                    messages = self.consumer.poll(timeout_ms=1000)
                    
                    if not messages:
                        continue
                    
                    for topic_partition, records in messages.items():
                        for record in records:
                            await self._process_notification(record)
                            
                except Exception as e:
                    logger.error(f"❌ 알림 처리 중 오류: {e}")
                    await asyncio.sleep(5)
                    
        except Exception as e:
            logger.error(f"❌ NotificationConsumer 시작 실패: {e}")
        finally:
            if self.consumer:
                self.consumer.close()
    
    async def _process_notification(self, record):
        """개별 알림 메시지 처리"""
        try:
            message = record.value
            notification_type = message.get('type', 'unknown')
            user_id = message.get('user_id', 'anonymous')
            
            logger.info(f"📨 알림 처리: {notification_type} -> {user_id}")
            
            # 알림 타입에 따른 처리
            if notification_type == 'analysis_completed':
                await self._handle_analysis_completed(message)
            elif notification_type == 'analysis_failed':
                await self._handle_analysis_failed(message)
            elif notification_type == 'welcome':
                await self._handle_welcome(message)
            elif notification_type == 'system_alert':
                await self._handle_system_alert(message)
            else:
                logger.warning(f"⚠️ 알 수 없는 알림 타입: {notification_type}")
                
        except Exception as e:
            logger.error(f"❌ 알림 메시지 처리 실패: {e}")
    
    async def _handle_analysis_completed(self, message: Dict[str, Any]):
        """분석 완료 알림 처리"""
        data = message.get('data', {})
        keyword = data.get('keyword', 'Unknown')
        
        # 이메일 발송
        if self.email_enabled:
            await self._send_email(
                to_email=data.get('user_email', ''),
                notification_type='analysis_completed',
                template_data={
                    'keyword': keyword,
                    'competitor_count': data.get('competitor_count', 0),
                    'difficulty_score': data.get('difficulty_score', 0),
                    'duration': data.get('duration', 0),
                    'report_url': f"http://localhost:8000/report?keyword={keyword}"
                }
            )
        
        # 슬랙 발송
        if self.slack_enabled:
            await self._send_slack(
                notification_type='analysis_completed',
                template_data={
                    'keyword': keyword,
                    'difficulty_score': data.get('difficulty_score', 0)
                }
            )
    
    async def _handle_analysis_failed(self, message: Dict[str, Any]):
        """분석 실패 알림 처리"""
        data = message.get('data', {})
        keyword = data.get('keyword', 'Unknown')
        
        if self.email_enabled:
            await self._send_email(
                to_email=data.get('user_email', ''),
                notification_type='analysis_failed',
                template_data={
                    'keyword': keyword,
                    'error_message': data.get('error_message', 'Unknown error')
                }
            )
        
        if self.slack_enabled:
            await self._send_slack(
                notification_type='analysis_failed',
                template_data={
                    'keyword': keyword,
                    'error_message': data.get('error_message', 'Unknown error')
                }
            )
    
    async def _handle_welcome(self, message: Dict[str, Any]):
        """환영 메시지 처리"""
        data = message.get('data', {})
        
        if self.email_enabled:
            await self._send_email(
                to_email=data.get('user_email', ''),
                notification_type='welcome',
                template_data={
                    'dashboard_url': 'http://localhost:8000'
                }
            )
    
    async def _handle_system_alert(self, message: Dict[str, Any]):
        """시스템 경고 처리 (관리자용)"""
        data = message.get('data', {})
        
        # 시스템 경고는 주로 슬랙으로만 발송
        if self.slack_enabled:
            await self._send_slack_raw(
                f"🚨 System Alert: {data.get('alert_message', 'Unknown alert')}"
            )
    
    async def _send_email(self, to_email: str, notification_type: str, template_data: Dict[str, Any]):
        """이메일 발송"""
        if not self.email_enabled or not to_email:
            logger.warning("⚠️ 이메일 설정이 없거나 수신자 이메일이 없습니다.")
            return
            
        try:
            template = self.notification_templates.get(notification_type)
            if not template:
                logger.error(f"❌ 알 수 없는 이메일 템플릿: {notification_type}")
                return
            
            # 템플릿 데이터 적용
            subject = template['email_subject'].format(**template_data)
            body = template['email_body'].format(**template_data)
            
            # 이메일 구성
            msg = MIMEMultipart()
            msg['From'] = EMAIL_USER
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            # SMTP 발송
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASSWORD)
                server.send_message(msg)
            
            logger.info(f"📧 이메일 발송 성공: {to_email} ({notification_type})")
            
        except Exception as e:
            logger.error(f"❌ 이메일 발송 실패: {e}")
    
    async def _send_slack(self, notification_type: str, template_data: Dict[str, Any]):
        """슬랙 메시지 발송 (템플릿 사용)"""
        try:
            template = self.notification_templates.get(notification_type)
            if not template:
                logger.error(f"❌ 알 수 없는 슬랙 템플릿: {notification_type}")
                return
            
            message = template['slack_message'].format(**template_data)
            await self._send_slack_raw(message)
            
        except Exception as e:
            logger.error(f"❌ 슬랙 메시지 발송 실패: {e}")
    
    async def _send_slack_raw(self, message: str):
        """슬랙 메시지 발송 (원본 메시지)"""
        if not self.slack_enabled:
            logger.warning("⚠️ 슬랙 설정이 없습니다.")
            return
            
        try:
            payload = {
                "text": message,
                "username": "Market Insights Bot",
                "icon_emoji": ":chart_with_upwards_trend:"
            }
            
            response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"💬 슬랙 메시지 발송 성공")
            else:
                logger.error(f"❌ 슬랙 메시지 발송 실패: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ 슬랙 메시지 발송 실패: {e}")
    
    async def stop(self):
        """Consumer 종료"""
        self.running = False
        if self.consumer:
            self.consumer.close()
        logger.info("🔒 NotificationConsumer 종료")


# 전역 인스턴스
_notification_consumer_instance = None

def get_notification_consumer() -> NotificationConsumer:
    """NotificationConsumer 싱글톤 인스턴스 반환"""
    global _notification_consumer_instance
    if _notification_consumer_instance is None:
        _notification_consumer_instance = NotificationConsumer()
    return _notification_consumer_instance

async def start_notification_consumer():
    """
    NotificationConsumer를 별도 태스크로 시작
    main.py의 startup 이벤트에서 호출
    """
    consumer = get_notification_consumer()
    asyncio.create_task(consumer.start())
    logger.info("🚀 NotificationConsumer 백그라운드 시작됨")


if __name__ == '__main__':
    # 단독 실행시 테스트
    async def test_notification_consumer():
        consumer = NotificationConsumer()
        await consumer.start()
    
    asyncio.run(test_notification_consumer())