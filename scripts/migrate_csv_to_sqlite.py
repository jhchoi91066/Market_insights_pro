# -*- coding: utf-8 -*-
"""
CSV 데이터를 SQLite로 마이그레이션하는 스크립트
기존 쿠팡 CSV 데이터를 새로운 SQLite 데이터베이스로 이전합니다.
"""
import os
import sys
import pandas as pd
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from core.models import db_manager, Product, ScrapingSession


def migrate_csv_to_sqlite(csv_file_path: str):
    """
    CSV 파일의 데이터를 SQLite 데이터베이스로 마이그레이션합니다.
    
    Args:
        csv_file_path: 마이그레이션할 CSV 파일 경로
    """
    print(f"=== CSV → SQLite 마이그레이션 시작 ===")
    print(f"CSV 파일: {csv_file_path}")
    
    # CSV 파일 존재 확인
    if not os.path.exists(csv_file_path):
        print(f"❌ CSV 파일을 찾을 수 없습니다: {csv_file_path}")
        return False
    
    # CSV 데이터 로드
    try:
        df = pd.read_csv(csv_file_path)
        print(f"📊 CSV 데이터 로드 완료: {len(df)}개 레코드")
        print(f"컬럼: {list(df.columns)}")
    except Exception as e:
        print(f"❌ CSV 파일 로드 실패: {e}")
        return False
    
    # 데이터베이스 테이블 생성
    db_manager.create_tables()
    
    # 데이터베이스 세션 생성
    session = db_manager.get_session()
    
    try:
        # 기존 데이터 확인 (중복 방지)
        existing_products = session.query(Product).count()
        print(f"📈 기존 데이터베이스 상품 수: {existing_products}")
        
        # CSV 데이터를 Product 모델로 변환하여 삽입
        products_added = 0
        products_skipped = 0
        
        for index, row in df.iterrows():
            # 중복 체크 (product_id 기준)
            existing = session.query(Product).filter_by(product_id=row['product_id']).first()
            if existing:
                products_skipped += 1
                continue
            
            # Product 인스턴스 생성
            product = Product(
                product_id=row['product_id'],
                product_title=row['product_title'],
                product_category=row['product_category'],
                discounted_price=int(row['discounted_price']) if pd.notna(row['discounted_price']) else 0,
                product_rating=float(row['product_rating']) if pd.notna(row['product_rating']) else 0.0,
                total_reviews=int(row['total_reviews']) if pd.notna(row['total_reviews']) else 0,
                purchased_last_month=int(row['purchased_last_month']) if pd.notna(row['purchased_last_month']) else 0,
                brand=row['brand'] if pd.notna(row['brand']) and row['brand'] != 'N/A' else None,
                seller=row['seller'] if pd.notna(row['seller']) and row['seller'] != 'N/A' else None,
                is_rocket=row['is_rocket'] == 'Y' if pd.notna(row['is_rocket']) else False,
                product_url=None,  # CSV에는 URL이 저장되지 않았음
                scraped_at=datetime.strptime(row['scraped_at'], "%Y-%m-%d %H:%M:%S") if pd.notna(row['scraped_at']) else datetime.utcnow()
            )
            
            session.add(product)
            products_added += 1
        
        # 스크레이핑 세션 정보 추가 (메타데이터)
        filename = os.path.basename(csv_file_path)
        keyword = filename.replace('_products.csv', '').replace('_', ' ')
        
        scraping_session = ScrapingSession(
            keyword=keyword,
            products_found=len(df),
            products_saved=products_added,
            session_status='completed' if products_added > 0 else 'partial',
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        session.add(scraping_session)
        
        # 커밋
        session.commit()
        
        print(f"✅ 마이그레이션 완료!")
        print(f"   - 새로 추가된 상품: {products_added}개")
        print(f"   - 중복으로 스킵된 상품: {products_skipped}개")
        print(f"   - 스크레이핑 세션 추가: 1개")
        
        return True
        
    except Exception as e:
        session.rollback()
        print(f"❌ 마이그레이션 실패: {e}")
        return False
        
    finally:
        db_manager.close_session(session)


def verify_migration():
    """
    마이그레이션 결과를 확인합니다.
    """
    print(f"\n=== 마이그레이션 검증 ===")
    
    session = db_manager.get_session()
    try:
        # 상품 수 확인
        products_count = session.query(Product).count()
        print(f"📊 총 상품 수: {products_count}")
        
        # 카테고리별 상품 수
        from sqlalchemy import func
        categories = session.query(Product.product_category, func.count(Product.id)).group_by(Product.product_category).all()
        
        print("📈 카테고리별 상품 수:")
        for category, count in categories:
            print(f"   - {category}: {count}개")
        
        # 스크레이핑 세션 수
        sessions_count = session.query(ScrapingSession).count()
        print(f"📊 스크레이핑 세션 수: {sessions_count}")
        
        # 최근 상품 5개 출력
        recent_products = session.query(Product).order_by(Product.scraped_at.desc()).limit(5).all()
        print(f"\n🔍 최근 상품 5개:")
        for product in recent_products:
            print(f"   - {product.product_id}: {product.product_title[:50]}...")
            
    except Exception as e:
        print(f"❌ 검증 중 오류: {e}")
    finally:
        db_manager.close_session(session)


if __name__ == '__main__':
    # CSV 파일 경로
    csv_file = "/Users/jinhochoi/Desktop/개발/Market_insights/data/블루투스_이어폰_products.csv"
    
    # 마이그레이션 실행
    success = migrate_csv_to_sqlite(csv_file)
    
    if success:
        # 검증
        verify_migration()
    
    print("\n=== 마이그레이션 스크립트 완료 ===")