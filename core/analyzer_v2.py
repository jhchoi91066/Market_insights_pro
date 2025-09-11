# -*- coding: utf-8 -*-
"""
SQLite + ORM 기반 시장 분석 엔진 (v2)
기존 CSV 기반 analyzer.py를 대체하는 새로운 분석 엔진입니다.
표준 SQL 쿼리와 SQLAlchemy ORM을 활용하여 더 빠르고 확장 가능한 분석을 제공합니다.
"""
import pandas as pd
from datetime import datetime
from sqlalchemy import func, and_, desc, text
from sqlalchemy.orm import Session
from collections import Counter
import re
from functools import lru_cache

# ORM 모델 import
try:
    from .models import db_manager, Product, ScrapingSession, AnalysisResult
except ImportError:
    # 직접 실행시에는 절대 import 사용
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from core.models import db_manager, Product, ScrapingSession, AnalysisResult


class SQLiteMarketAnalyzer:
    """
    SQLite 기반 시장 데이터 분석을 수행하는 신버전 클래스.
    기존 CSV 기반 MarketAnalyzer를 대체합니다.
    """
    
    def format_price(self, price):
        """USD 가격을 포맷팅합니다."""
        return f"${price:.2f}"
    
    def __init__(self):
        """
        분석기 초기화. SQLite 데이터베이스와 연결합니다.
        """
        print("SQLiteMarketAnalyzer 초기화 중...")
        self.db_manager = db_manager
        
        # 데이터베이스 테이블 생성 (없을 경우)
        self.db_manager.create_tables()
        
        # 기본 통계 확인
        session = self.db_manager.get_session()
        try:
            total_products = session.query(Product).count()
            categories = session.query(Product.product_category).distinct().count()
            print(f"✅ 데이터베이스 연결 완료!")
            print(f"   📊 총 상품 수: {total_products}개")
            print(f"   📂 카테고리 수: {categories}개")
        finally:
            self.db_manager.close_session(session)

    def get_session(self) -> Session:
        """데이터베이스 세션을 반환합니다."""
        return self.db_manager.get_session()

    @lru_cache(maxsize=128)
    def analyze_category_competition(self, category: str, price_range: tuple = (0, 999999), num_bins: int = 4):
        """
        특정 카테고리의 경쟁 강도를 분석합니다. (SQL 기반)
        
        Args:
            category: 분석할 카테고리
            price_range: 분석할 가격 범위 (최소, 최대)
            num_bins: 가격 구간 분할 수
            
        Returns:
            dict: 분석 결과
        """
        print(f"'{category}' 카테고리 경쟁 분석 시작 (가격대: {self.format_price(price_range[0])}-{self.format_price(price_range[1])})...")
        
        session = self.get_session()
        try:
            min_price, max_price = price_range
            
            # 1. 경쟁 제품 수 조회 (SQL)
            competitor_count = session.query(Product).filter(
                and_(
                    Product.product_category == category,
                    Product.discounted_price >= min_price,
                    Product.discounted_price <= max_price
                )
            ).count()
            
            # Prime 제품 수 조회
            prime_count = session.query(Product).filter(
                and_(
                    Product.product_category == category,
                    Product.discounted_price >= min_price,
                    Product.discounted_price <= max_price,
                    Product.is_prime == True
                )
            ).count()
            
            print(f"🔍 경쟁 제품 수: {competitor_count}개 (Prime: {prime_count}개)")
            
            if competitor_count == 0:
                return {
                    'competitor_count': 0,
                    'prime_count': 0,
                    'prime_percentage': 0,
                    'rating_by_price_bin': {},
                    'top_10_products': [],
                    'difficulty_score': 0
                }
            
            # 2. 가격 구간별 평균 평점 계산 (SQL)
            bin_width = (max_price - min_price) / num_bins
            rating_by_price_bin = {}
            
            for i in range(num_bins):
                bin_min = min_price + (i * bin_width)
                bin_max = min_price + ((i + 1) * bin_width)
                
                avg_rating = session.query(func.avg(Product.product_rating)).filter(
                    and_(
                        Product.product_category == category,
                        Product.discounted_price >= bin_min,
                        Product.discounted_price < bin_max,
                        Product.product_rating > 0  # 평점이 있는 제품만
                    )
                ).scalar()
                
                if avg_rating:
                    bin_label = f"{self.format_price(bin_min)}-{self.format_price(bin_max)}"
                    rating_by_price_bin[bin_label] = round(float(avg_rating), 2)
            
            print(f"📊 가격 구간별 평균 평점: {rating_by_price_bin}")
            
            # 3. TOP 10 제품 조회 (판매량 기준, SQL)
            top_products_query = session.query(Product).filter(
                and_(
                    Product.product_category == category,
                    Product.discounted_price >= min_price,
                    Product.discounted_price <= max_price
                )
            ).order_by(desc(Product.purchased_last_month)).limit(10)
            
            top_10_products = []
            for product in top_products_query:
                top_10_products.append({
                    'product_title': product.product_title,
                    'discounted_price': self.format_price(product.discounted_price),
                    'product_rating': product.product_rating,
                    'purchased_last_month': product.purchased_last_month,
                    'total_reviews': product.total_reviews,
                    'is_prime': product.is_prime
                })
            
            print(f"🏆 TOP 10 제품 조회 완료")
            
            # 4. Prime 비율 계산
            prime_percentage = round((prime_count / competitor_count) * 100, 1) if competitor_count > 0 else 0
            
            # 5. 진입 난이도 점수 계산
            difficulty_score = self._calculate_difficulty_score(session, category, price_range, top_10_products)
            
            result = {
                'competitor_count': competitor_count,
                'prime_count': prime_count,
                'prime_percentage': prime_percentage,
                'rating_by_price_bin': rating_by_price_bin,
                'top_10_products': top_10_products,
                'difficulty_score': difficulty_score
            }
            
            # 분석 결과 저장
            self._save_analysis_result(session, category, 'competition', 
                                     {'price_range': price_range, 'num_bins': num_bins}, result)
            
            print(f"✅ 경쟁 분석 완료! 난이도: {difficulty_score}/10")
            return result
            
        finally:
            self.db_manager.close_session(session)

    def find_price_gaps(self, category: str, bin_width: int = 100):
        """
        특정 카테고리 내에서 가격 공백 구간을 탐색합니다. (SQL 기반)
        
        Args:
            category: 분석할 카테고리
            bin_width: 가격 구간 너비
            
        Returns:
            dict: 가격 분포 및 공백 구간 정보
        """
        print(f"'{category}' 카테고리 가격 공백 분석 시작 (구간: {self.format_price(bin_width)})...")
        
        session = self.get_session()
        try:
            # 1. 해당 카테고리의 가격 범위 조회
            price_stats = session.query(
                func.min(Product.discounted_price).label('min_price'),
                func.max(Product.discounted_price).label('max_price'),
                func.count(Product.id).label('total_count')
            ).filter(
                and_(
                    Product.product_category == category,
                    Product.discounted_price > 0
                )
            ).first()
            
            if not price_stats or price_stats.total_count == 0:
                print("❌ 해당 카테고리의 제품이 없습니다.")
                return {'price_distribution': {}, 'price_gaps': {}}
            
            min_price = float(price_stats.min_price)
            max_price = float(price_stats.max_price)
            
            print(f"📊 가격 범위: {self.format_price(min_price)} ~ {self.format_price(max_price)} ({price_stats.total_count}개 제품)")
            
            # 2. 가격 구간별 제품 수 계산 (SQL)
            price_distribution = {}
            price_gaps = {}
            
            current_price = min_price
            while current_price < max_price:
                bin_end = min(current_price + bin_width, max_price)
                
                # 해당 구간의 제품 수 조회
                count_in_bin = session.query(Product).filter(
                    and_(
                        Product.product_category == category,
                        Product.discounted_price >= current_price,
                        Product.discounted_price < bin_end
                    )
                ).count()
                
                bin_label = f"{self.format_price(current_price)}-{self.format_price(bin_end)}"
                price_distribution[bin_label] = count_in_bin
                
                # 가격 공백 구간 판정 (제품 수가 10개 미만)
                if count_in_bin < 10:
                    price_gaps[bin_label] = count_in_bin
                
                current_price = bin_end
            
            print(f"🔍 가격 공백 구간: {len(price_gaps)}개 발견")
            for gap, count in price_gaps.items():
                print(f"   - {gap}: {count}개 제품")
            
            result = {
                'price_distribution': price_distribution,
                'price_gaps': price_gaps
            }
            
            # 분석 결과 저장
            self._save_analysis_result(session, category, 'price_gaps', 
                                     {'bin_width': bin_width}, result)
            
            return result
            
        finally:
            self.db_manager.close_session(session)

    def extract_success_keywords(self, category: str, rating_threshold: float = 4.5, 
                               reviews_threshold: int = 100, num_keywords: int = 20):
        """
        성공적인 제품들로부터 핵심 키워드를 추출합니다. (SQL + NLP)
        
        Args:
            category: 분석할 카테고리
            rating_threshold: 성공 기준 최소 평점
            reviews_threshold: 성공 기준 최소 리뷰 수
            num_keywords: 추출할 키워드 수
            
        Returns:
            dict: 성공 키워드 목록
        """
        print(f"'{category}' 카테고리 성공 키워드 분석 (평점>={rating_threshold}, 리뷰>={reviews_threshold})...")
        
        session = self.get_session()
        try:
            # 1. 성공적인 제품들 조회 (SQL)
            successful_products = session.query(Product.product_title).filter(
                and_(
                    Product.product_category == category,
                    Product.product_rating >= rating_threshold,
                    Product.total_reviews >= reviews_threshold
                )
            ).all()
            
            if not successful_products:
                print("❌ 성공 기준을 만족하는 제품이 없습니다.")
                return {'top_keywords': []}
            
            print(f"🎯 성공 제품 수: {len(successful_products)}개")
            
            # 2. 키워드 추출 및 빈도 계산
            all_titles = ' '.join([product.product_title for product in successful_products])
            words = re.findall(r'\b\w+\b', all_titles.lower())
            
            # 불용어 제거 (Amazon 영어 제품명 최적화)
            stop_words = {
                'and', 'the', 'for', 'with', 'in', 'of', 'to', 'a', 'is', 'on', 'or', 'at', 'by',
                'hd', 'pro', 'pc', 'usb', 'type', 'new', 'pack', 'set', 'inch', 'size', 'color',
                'wireless', 'bluetooth', 'portable', 'rechargeable', 'waterproof', 'gaming', 'smart'
            }
            
            meaningful_words = [
                word for word in words 
                if word not in stop_words and not word.isdigit() and len(word) > 2
            ]
            
            keyword_counts = Counter(meaningful_words)
            top_keywords = keyword_counts.most_common(num_keywords)
            
            print(f"🔤 TOP {num_keywords} 키워드:")
            for keyword, count in top_keywords[:10]:
                print(f"   - {keyword}: {count}회")
            
            result = {'top_keywords': top_keywords}
            
            # 분석 결과 저장
            self._save_analysis_result(session, category, 'keywords', 
                                     {
                                         'rating_threshold': rating_threshold,
                                         'reviews_threshold': reviews_threshold,
                                         'num_keywords': num_keywords
                                     }, result)
            
            return result
            
        finally:
            self.db_manager.close_session(session)

    @lru_cache(maxsize=128)
    def calculate_market_saturation(self, category: str):
        """
        특정 카테고리의 시장 포화도를 계산합니다. (개선된 Amazon 기반 로직)
        
        Args:
            category: 분석할 카테고리
            
        Returns:
            dict: 시장 포화도 정보
        """
        print(f"'{category}' 카테고리 시장 포화도 계산...")
        
        session = self.get_session()
        try:
            # 1. 수집된 제품 수 확인
            collected_count = session.query(Product).filter(
                Product.product_category == category
            ).count()
            
            if collected_count == 0:
                print("❌ 수집된 제품이 없습니다.")
                return {'market_saturation_percentage': 0}
            
            # 2. TOP 10 제품의 판매량 계산
            top_10_products = session.query(Product.purchased_last_month).filter(
                Product.product_category == category
            ).order_by(desc(Product.purchased_last_month)).limit(10).all()
            
            top_10_sales_sum = sum([p.purchased_last_month for p in top_10_products])
            
            # 3. Amazon 시장 규모 추정 기반 포화도 계산
            # Amazon 카테고리별 평균 제품 수 추정
            category_multipliers = {
                'electronics': 10000,    # 전자제품
                'clothing': 20000,       # 의류
                'home': 15000,          # 홈용품
                'default': 8000         # 기본값
            }
            
            # 키워드 기반 카테고리 추정
            estimated_total_products = category_multipliers['default']
            if any(keyword in category.lower() for keyword in ['mouse', 'keyboard', 'headphone', 'phone', 'computer']):
                estimated_total_products = category_multipliers['electronics']
            elif any(keyword in category.lower() for keyword in ['bag', 'case', 'bottle', 'backpack']):
                estimated_total_products = category_multipliers['home']
            
            # 4. 현실적인 포화도 계산
            # TOP 10이 시장을 독점하는 비율을 현실적으로 계산
            # 일반적으로 Amazon에서 TOP 10은 15-40% 정도 차지
            collected_ratio = min(collected_count / estimated_total_products, 0.01)  # 최대 1% 샘플로 제한
            
            # 샘플 기반 추정 포화도
            if collected_count >= 50:
                # 충분한 샘플: 25-35% 범위
                estimated_saturation = 25 + (top_10_sales_sum / (top_10_sales_sum + sum([p.purchased_last_month for p in session.query(Product.purchased_last_month).filter(Product.product_category == category).offset(10).limit(40).all()]))) * 15
            elif collected_count >= 20:
                # 중간 샘플: 30-40% 범위  
                estimated_saturation = 30 + (collected_ratio * 1000)
            else:
                # 작은 샘플: 35-45% 범위 (불확실성 높음)
                estimated_saturation = 35 + (collected_count / 20 * 10)
            
            # 최종 포화도 (15-60% 범위로 제한)
            saturation_percentage = max(15, min(60, estimated_saturation))
            
            print(f"📊 수집된 제품 수: {collected_count:,}개")
            print(f"🏆 TOP 10 판매량: {top_10_sales_sum:,}개")
            print(f"📈 추정 시장 포화도: {saturation_percentage:.1f}%")
            print(f"🔍 (추정 전체 제품 수: {estimated_total_products:,}개)")
            
            result = {'market_saturation_percentage': round(saturation_percentage, 1)}
            
            # 분석 결과 저장
            self._save_analysis_result(session, category, 'saturation', {}, result)
            
            return result
            
        finally:
            self.db_manager.close_session(session)

    def get_analysis_history(self, category: str = None, analysis_type: str = None, limit: int = 10):
        """
        분석 히스토리를 조회합니다.
        
        Args:
            category: 특정 카테고리로 필터링 (선택사항)
            analysis_type: 특정 분석 타입으로 필터링 (선택사항)
            limit: 조회할 최대 개수
            
        Returns:
            list: 분석 히스토리 목록
        """
        session = self.get_session()
        try:
            query = session.query(AnalysisResult)
            
            if category:
                query = query.filter(AnalysisResult.category == category)
            if analysis_type:
                query = query.filter(AnalysisResult.analysis_type == analysis_type)
            
            history = query.order_by(desc(AnalysisResult.created_at)).limit(limit).all()
            
            result = []
            for record in history:
                result.append({
                    'id': record.id,
                    'category': record.category,
                    'analysis_type': record.analysis_type,
                    'created_at': record.created_at,
                    'results': record.results
                })
            
            return result
            
        finally:
            self.db_manager.close_session(session)

    def _calculate_difficulty_score(self, session: Session, category: str, price_range: tuple, top_products: list):
        """진입 난이도 점수를 계산하는 내부 메서드 (개선된 Amazon 기반 로직)"""
        min_price, max_price = price_range
        
        # 1. 경쟁 밀도 점수 (0-4점) - 더 현실적인 기준
        competitor_count = session.query(Product).filter(
            and_(
                Product.product_category == category,
                Product.discounted_price >= min_price,
                Product.discounted_price <= max_price
            )
        ).count()
        
        # Amazon 기준: 5개 미만=매우 낮음, 20개 미만=낮음, 50개 미만=보통, 100개 이상=높음
        if competitor_count < 5:
            competitor_score = 0.5
        elif competitor_count < 20:
            competitor_score = 1.5
        elif competitor_count < 50:
            competitor_score = 2.5
        elif competitor_count < 100:
            competitor_score = 3.5
        else:
            competitor_score = 4.0
        
        # 2. 품질 기대치 점수 (0-3점) - 평균 평점 기반
        avg_rating = session.query(func.avg(Product.product_rating)).filter(
            and_(
                Product.product_category == category,
                Product.discounted_price >= min_price,
                Product.discounted_price <= max_price,
                Product.product_rating > 0
            )
        ).scalar() or 0
        
        # Amazon 기준: 4.0 미만=낮음, 4.3 미만=보통, 4.5 미만=높음, 4.5 이상=매우 높음
        if avg_rating == 0:
            rating_score = 1.0  # 데이터 없음 = 보통 수준
        elif avg_rating < 4.0:
            rating_score = 0.5
        elif avg_rating < 4.3:
            rating_score = 1.5
        elif avg_rating < 4.5:
            rating_score = 2.5
        else:
            rating_score = 3.0
        
        # 3. 상위권 진입 장벽 점수 (0-3점) - 리뷰 수와 판매량 기반
        if top_products and len(top_products) > 0:
            # 평균 리뷰 수
            reviews_with_data = [p.get('total_reviews', 0) for p in top_products if p.get('total_reviews', 0) > 0]
            avg_top_reviews = sum(reviews_with_data) / len(reviews_with_data) if reviews_with_data else 0
            
            # 평균 판매량
            sales_with_data = [p.get('purchased_last_month', 0) for p in top_products if p.get('purchased_last_month', 0) > 0]
            avg_top_sales = sum(sales_with_data) / len(sales_with_data) if sales_with_data else 0
            
            # Amazon 기준: 리뷰 500개 미만=낮음, 2000개 미만=보통, 5000개 미만=높음, 이상=매우 높음
            review_barrier = 0
            if avg_top_reviews < 500:
                review_barrier = 0.5
            elif avg_top_reviews < 2000:
                review_barrier = 1.0
            elif avg_top_reviews < 5000:
                review_barrier = 1.5
            else:
                review_barrier = 2.0
            
            # 판매량 기반 추가 점수 (월 1000개 이상이면 +1점)
            sales_barrier = min(avg_top_sales / 1000, 1.0)
            
            review_score = min(review_barrier + sales_barrier, 3.0)
        else:
            review_score = 1.5  # 데이터 없음 = 보통 수준
        
        difficulty_score = round(competitor_score + rating_score + review_score, 1)
        
        print(f"📊 난이도 점수 계산: 경쟁밀도({competitor_score:.1f}) + 품질기대치({rating_score:.1f}) + 진입장벽({review_score:.1f}) = {difficulty_score}")
        
        return difficulty_score

    def _save_analysis_result(self, session: Session, category: str, analysis_type: str, params: dict, results: dict):
        """분석 결과를 데이터베이스에 저장하는 내부 메서드"""
        try:
            analysis_record = AnalysisResult(
                category=category,
                analysis_type=analysis_type,
                input_params=params,
                results=results,
                created_at=datetime.utcnow()
            )
            session.add(analysis_record)
            session.commit()
        except Exception as e:
            print(f"⚠️ 분석 결과 저장 실패: {e}")


if __name__ == '__main__':
    # 새로운 SQLite 기반 분석 엔진 테스트
    print("=== SQLite 기반 시장 분석 엔진 테스트 ===")
    
    analyzer = SQLiteMarketAnalyzer()
    
    # 테스트 1: 경쟁 분석
    print("\n🔍 테스트 1: wireless mouse 카테고리 경쟁 분석")
    competition_result = analyzer.analyze_category_competition('wireless mouse', (10.0, 50.0))
    
    # 테스트 2: 가격 공백 분석
    print("\n💰 테스트 2: 가격 공백 분석")
    price_gap_result = analyzer.find_price_gaps('wireless mouse', 10.0)
    
    # 테스트 3: 키워드 분석
    print("\n🔤 테스트 3: 성공 키워드 분석")
    keyword_result = analyzer.extract_success_keywords('wireless mouse', 4.0, 50)
    
    # 테스트 4: 시장 포화도
    print("\n📊 테스트 4: 시장 포화도 분석")
    saturation_result = analyzer.calculate_market_saturation('wireless mouse')
    
    # 테스트 5: 분석 히스토리
    print("\n📜 테스트 5: 분석 히스토리 조회")
    history = analyzer.get_analysis_history(category='wireless mouse', limit=5)
    print(f"분석 히스토리: {len(history)}개 기록")
    
    print("\n=== 테스트 완료 ===")