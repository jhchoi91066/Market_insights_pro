# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM 모델 정의
Market Insights Pro 프로젝트의 데이터베이스 모델들을 정의합니다.
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, JSON
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class Product(Base):
    """
    상품 정보를 저장하는 모델
    아마존에서 스크레이핑한 상품 데이터를 저장합니다.
    """
    __tablename__ = 'products'
    
    id = Column(Integer, primary_key=True)
    product_id = Column(String(50), unique=True, nullable=False, index=True)  # AMZ_000001 형식
    product_title = Column(Text, nullable=False)
    product_category = Column(String(100), nullable=False, index=True)
    discounted_price = Column(Float, nullable=False)  # 가격 (USD 달러)
    product_rating = Column(Float, default=0.0)  # 평점 (0.0 ~ 5.0)
    total_reviews = Column(Integer, default=0)  # 총 리뷰 수
    purchased_last_month = Column(Integer, default=0)  # 지난달 구매수 (추정)
    brand = Column(String(100))
    seller = Column(String(100))
    is_prime = Column(Boolean, default=False)  # Prime 배송 여부
    asin = Column(String(20))  # Amazon Standard Identification Number
    product_url = Column(Text)  # 원본 상품 URL
    scraped_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    def __repr__(self):
        return f"<Product(id={self.id}, title='{self.product_title[:50]}...', price={self.discounted_price})>"


class ScrapingSession(Base):
    """
    스크레이핑 세션 정보를 저장하는 모델
    언제, 어떤 키워드로 몇 개의 상품을 수집했는지 추적합니다.
    """
    __tablename__ = 'scraping_sessions'
    
    id = Column(Integer, primary_key=True)
    keyword = Column(String(200), nullable=False)  # 검색 키워드
    products_found = Column(Integer, nullable=False)  # 발견된 상품 수
    products_saved = Column(Integer, nullable=False)  # 실제 저장된 상품 수
    session_status = Column(String(20), default='completed')  # completed, failed, partial
    error_message = Column(Text)  # 에러 발생 시 메시지
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<ScrapingSession(id={self.id}, keyword='{self.keyword}', status='{self.session_status}')>"


class AnalysisResult(Base):
    """
    분석 결과를 저장하는 모델
    사용자의 시장 분석 결과와 히스토리를 추적합니다.
    """
    __tablename__ = 'analysis_results'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(100))  # 나중에 사용자 시스템 연동시 사용
    category = Column(String(100), nullable=False, index=True)
    analysis_type = Column(String(50), nullable=False)  # competition, price_gaps, keywords, saturation
    input_params = Column(JSON)  # 분석에 사용된 파라미터들
    results = Column(JSON, nullable=False)  # 분석 결과 (JSON 형태)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    def __repr__(self):
        return f"<AnalysisResult(id={self.id}, type='{self.analysis_type}', category='{self.category}')>"


# 데이터베이스 설정 클래스
class DatabaseManager:
    """
    데이터베이스 연결과 세션을 관리하는 클래스
    """
    def __init__(self, database_url: str = "sqlite:///data/market_insights.db"):
        self.database_url = database_url
        self.engine = create_engine(
            database_url, 
            echo=False,  # SQL 쿼리 로깅 (개발시에만 True)
            pool_pre_ping=True,  # 연결 유효성 검사
            connect_args={"check_same_thread": False} # FastAPI 환경에서 SQLite 사용시 필수
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def create_tables(self):
        """
        모든 테이블을 생성합니다.
        """
        print("데이터베이스 테이블을 생성합니다...")
        Base.metadata.create_all(bind=self.engine)
        print("✅ 테이블 생성 완료!")
    
    def get_session(self):
        """
        데이터베이스 세션을 반환합니다.
        """
        return self.SessionLocal()
    
    def close_session(self, session):
        """
        데이터베이스 세션을 안전하게 종료합니다.
        """
        session.close()


# 전역 데이터베이스 매니저 인스턴스
db_manager = DatabaseManager()


if __name__ == '__main__':
    # 테스트: 테이블 생성 및 샘플 데이터 삽입
    print("=== ORM 모델 테스트 ===")
    
    # 테이블 생성
    db_manager.create_tables()
    
    # 세션 생성 및 샘플 데이터 삽입 테스트
    session = db_manager.get_session()
    try:
        # 샘플 상품 데이터 생성
        sample_product = Product(
            product_id="AMZ_TEST_001",
            product_title="Test Wireless Bluetooth Headphones",
            product_category="bluetooth headphones",
            discounted_price=24.99,
            product_rating=4.5,
            total_reviews=150,
            purchased_last_month=15,
            brand="TestBrand",
            seller="Amazon.com",
            is_prime=True,
            asin="B07TESTSIN",
            product_url="https://amazon.com/dp/B07TESTSIN"
        )
        
        # 샘플 스크레이핑 세션 데이터 생성
        sample_session = ScrapingSession(
            keyword="wireless mouse",
            products_found=20,
            products_saved=18,
            session_status="completed",
            started_at=datetime.utcnow()
        )
        
        # 데이터베이스에 저장
        session.add(sample_product)
        session.add(sample_session)
        session.commit()
        
        print("✅ 샘플 데이터 삽입 성공!")
        
        # 데이터 조회 테스트
        products = session.query(Product).all()
        sessions = session.query(ScrapingSession).all()
        
        print(f"📊 저장된 상품 수: {len(products)}")
        print(f"📊 저장된 세션 수: {len(sessions)}")
        
        if products:
            print(f"첫 번째 상품: {products[0]}")
        if sessions:
            print(f"첫 번째 세션: {sessions[0]}")
    
    except Exception as e:
        session.rollback()
        print(f"❌ 에러 발생: {e}")
    
    finally:
        db_manager.close_session(session)
    
    print("=== 테스트 완료 ===")