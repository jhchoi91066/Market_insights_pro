#!/usr/bin/env python3
"""
Kafka 토픽 자동 생성 스크립트
애플리케이션에서 사용할 모든 토픽을 미리 생성하고 설정합니다.
"""

import time
import logging
from kafka import KafkaProducer, KafkaAdminClient
from kafka.admin import ConfigResource, ConfigResourceType, NewTopic
from kafka.errors import TopicAlreadyExistsError, KafkaError

# 로거 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KafkaTopicSetup:
    """Kafka 토픽 설정 및 생성 클래스"""
    
    def __init__(self, bootstrap_servers='localhost:9092'):
        self.bootstrap_servers = bootstrap_servers
        self.admin_client = None
        
        # 생성할 토픽 정의
        self.topics_config = [
            {
                'name': 'market-analysis-events',
                'partitions': 3,
                'replication_factor': 1,
                'description': '시장 분석 요청/완료 이벤트',
                'config': {
                    'retention.ms': '604800000',  # 7일 보존
                    'cleanup.policy': 'delete'
                }
            },
            {
                'name': 'scraping-status-updates', 
                'partitions': 2,
                'replication_factor': 1,
                'description': '스크래핑 진행 상황 실시간 업데이트',
                'config': {
                    'retention.ms': '86400000',  # 1일 보존
                    'cleanup.policy': 'delete'
                }
            },
            {
                'name': 'user-notifications',
                'partitions': 1,
                'replication_factor': 1, 
                'description': '사용자 알림 (이메일, 슬랙)',
                'config': {
                    'retention.ms': '259200000',  # 3일 보존
                    'cleanup.policy': 'delete'
                }
            },
            {
                'name': 'user-actions',
                'partitions': 2,
                'replication_factor': 1,
                'description': '사용자 행동 추적 (페이지 방문, 클릭)',
                'config': {
                    'retention.ms': '2592000000',  # 30일 보존
                    'cleanup.policy': 'compact'  # 최신 상태만 유지
                }
            },
            {
                'name': 'statistics-events',
                'partitions': 2,
                'replication_factor': 1,
                'description': '통계 집계용 이벤트',
                'config': {
                    'retention.ms': '2592000000',  # 30일 보존
                    'cleanup.policy': 'delete'
                }
            }
        ]
    
    def wait_for_kafka(self, max_retries=30, retry_interval=2):
        """
        Kafka가 준비될 때까지 대기
        Docker Compose로 시작할 때 Kafka가 완전히 준비되기까지 시간이 필요
        """
        logger.info("🔍 Kafka 서버 연결 대기 중...")
        
        for attempt in range(max_retries):
            try:
                # 간단한 Producer 생성으로 연결 테스트
                producer = KafkaProducer(
                    bootstrap_servers=self.bootstrap_servers,
                    request_timeout_ms=5000,
                    api_version=(2, 0, 2)
                )
                producer.close()
                logger.info("✅ Kafka 서버 연결 성공!")
                return True
                
            except Exception as e:
                logger.warning(f"⏳ Kafka 연결 시도 {attempt + 1}/{max_retries} 실패: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_interval)
                
        logger.error(f"❌ {max_retries}회 시도 후 Kafka 연결 실패")
        return False
    
    def create_admin_client(self):
        """KafkaAdminClient 생성"""
        try:
            self.admin_client = KafkaAdminClient(
                bootstrap_servers=self.bootstrap_servers,
                client_id='topic_setup_client',
                request_timeout_ms=10000
            )
            logger.info("✅ Kafka Admin Client 생성 완료")
            return True
            
        except Exception as e:
            logger.error(f"❌ Admin Client 생성 실패: {e}")
            return False
    
    def create_topics(self):
        """모든 토픽 생성"""
        if not self.admin_client:
            logger.error("❌ Admin Client가 초기화되지 않았습니다.")
            return False
            
        topics_to_create = []
        
        for topic_config in self.topics_config:
            topic = NewTopic(
                name=topic_config['name'],
                num_partitions=topic_config['partitions'],
                replication_factor=topic_config['replication_factor'],
                topic_configs=topic_config['config']
            )
            topics_to_create.append(topic)
            
        try:
            # 토픽 생성 실행
            create_result = self.admin_client.create_topics(
                new_topics=topics_to_create,
                validate_only=False
            )
            
            # 결과 확인
            for topic_name, future in create_result.items():
                try:
                    future.result()  # 완료 대기
                    
                    # 토픽 정보 찾기
                    topic_info = next(t for t in self.topics_config if t['name'] == topic_name)
                    logger.info(f"✅ 토픽 생성 성공: {topic_name}")
                    logger.info(f"   📊 파티션: {topic_info['partitions']}, "
                              f"보존기간: {int(topic_info['config']['retention.ms']) // 86400000}일")
                    logger.info(f"   📝 설명: {topic_info['description']}")
                    
                except TopicAlreadyExistsError:
                    logger.info(f"ℹ️ 토픽 이미 존재: {topic_name}")
                    
                except Exception as e:
                    logger.error(f"❌ 토픽 생성 실패: {topic_name} - {e}")
                    
            return True
            
        except Exception as e:
            logger.error(f"❌ 토픽 생성 중 오류: {e}")
            return False
    
    def list_topics(self):
        """생성된 토픽 목록 확인"""
        try:
            metadata = self.admin_client.describe_topics()
            topic_names = list(metadata.keys())
            
            logger.info("📋 현재 생성된 토픽 목록:")
            for topic_name in sorted(topic_names):
                if topic_name in [t['name'] for t in self.topics_config]:
                    logger.info(f"   ✅ {topic_name}")
                    
        except Exception as e:
            logger.error(f"❌ 토픽 목록 조회 실패: {e}")
    
    def setup_all(self):
        """전체 설정 프로세스 실행"""
        logger.info("🚀 Kafka 토픽 설정 시작...")
        
        # 1단계: Kafka 연결 대기
        if not self.wait_for_kafka():
            return False
            
        # 2단계: Admin Client 생성  
        if not self.create_admin_client():
            return False
            
        # 3단계: 토픽 생성
        if not self.create_topics():
            return False
            
        # 4단계: 결과 확인
        self.list_topics()
        
        logger.info("🎉 Kafka 토픽 설정 완료!")
        return True
    
    def close(self):
        """리소스 정리"""
        if self.admin_client:
            self.admin_client.close()


def main():
    """메인 실행 함수"""
    setup = KafkaTopicSetup()
    
    try:
        success = setup.setup_all()
        if success:
            print("\n🎯 토픽 설정이 성공적으로 완료되었습니다!")
            print("📍 Kafka UI에서 확인: http://localhost:8080")
        else:
            print("\n❌ 토픽 설정 중 오류가 발생했습니다.")
            
    except KeyboardInterrupt:
        print("\n⏹️ 사용자에 의해 중단되었습니다.")
        
    finally:
        setup.close()


if __name__ == '__main__':
    main()