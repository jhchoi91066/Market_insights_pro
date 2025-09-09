"""
# -*- coding: utf-8 -*-
"""
이 파일은 Market Insights Pro 프로젝트의 핵심 데이터 분석 엔진입니다.
Pandas를 사용하여 CSV 데이터를 분석하고, 다양한 시장 지표를 계산합니다.
"""
import pandas as pd
from collections import Counter
import re
from .models import DatabaseManager


class MarketAnalyzer:
    """
    시장 데이터 분석을 수행하는 클래스.
    CSV 파일을 읽어 Pandas DataFrame으로 변환하고, 이를 기반으로 분석을 수행합니다.
    """

    def __init__(self, db_path):
        """
        분석기 초기화. 데이터 파일을 로드하고 기본 통계를 출력합니다.
        
        Args:
            db_path (str): 분석할 데이터 CSV 파일의 경로.
        """
        print("MarketAnalyzer 초기화 중...")
        self.df = self._load_data(db_path)
        self.db_manager = DatabaseManager(db_path)
        if not self.df.empty:
            print("✅ 데이터 로드 완료!")
            print(f"   - 총 {len(self.df)}개의 상품 데이터")
            print(f"   - {self.df['product_category'].nunique()}개의 카테고리")
        else:
            print("⚠️ 데이터 로드 실패! 빈 DataFrame입니다.")

    def _load_data(self, db_path):
        """
        지정된 경로의 CSV 파일을 읽어 DataFrame으로 변환합니다.
        
        Args:
            db_path (str): CSV 파일 경로.
            
        Returns:
            pd.DataFrame: 로드된 데이터. 오류 발생 시 빈 DataFrame 반환.
        """
        try:
            df = pd.read_csv(db_path)
            # 필요한 컬럼만 선택하고, 결측치가 있는 행은 제거
            required_columns = [
                'product_title', 'product_category', 'discounted_price',
                'product_rating', 'total_reviews', 'purchased_last_month'
            ]
            df = df[required_columns].dropna()
            
            # 데이터 타입 변환
            df['discounted_price'] = pd.to_numeric(df['discounted_price'], errors='coerce')
            df['product_rating'] = pd.to_numeric(df['product_rating'], errors='coerce')
            df['total_reviews'] = pd.to_numeric(df['total_reviews'], errors='coerce')
            df['purchased_last_month'] = pd.to_numeric(df['purchased_last_month'], errors='coerce')
            
            return df.dropna()
        except FileNotFoundError:
            print(f"오류: 파일을 찾을 수 없습니다 - {db_path}")
            return pd.DataFrame()
        except Exception as e:
            print(f"데이터 로드 중 오류 발생: {e}")
            return pd.DataFrame()

    def analyze_category_competition(self, category: str, price_range: tuple = (0, 999999), num_bins: int = 4):
        """
        특정 카테고리의 경쟁 강도를 분석합니다.
        
        Args:
            category (str): 분석할 카테고리.
            price_range (tuple): 분석할 가격 범위 (최소, 최대).
            num_bins (int): 가격 구간을 나눌 개수.
            
        Returns:
            dict: 경쟁 분석 결과.
        """
        print(f"'{category}' 카테고리 경쟁 분석 시작 (가격대: ${price_range[0]}-${price_range[1]})...")
        
        # 1. 카테고리 및 가격 범위 필터링
        filtered_df = self.df[
            (self.df['product_category'] == category) &
            (self.df['discounted_price'] >= price_range[0]) &
            (self.df['discounted_price'] <= price_range[1])
        ]
        
        competitor_count = len(filtered_df)
        print(f"🔍 경쟁 제품 수: {competitor_count}개")
        
        if competitor_count == 0:
            return {
                'competitor_count': 0,
                'rating_by_price_bin': {},
                'top_10_products_by_sales': [],
                'difficulty_score': 0
            }
        
        # 2. 가격 구간별 평균 평점 계산
        min_price, max_price = filtered_df['discounted_price'].min(), filtered_df['discounted_price'].max()
        bins = pd.cut(filtered_df['discounted_price'], bins=num_bins)
        rating_by_price_bin = filtered_df.groupby(bins)['product_rating'].mean().round(2).to_dict()
        rating_by_price_bin = {str(k): v for k, v in rating_by_price_bin.items()} # 키를 문자열로 변환
        
        print(f"📊 가격 구간별 평균 평점: {rating_by_price_bin}")
        
        # 3. 판매량 기준 TOP 10 제품
        top_10_products = filtered_df.sort_values(by='purchased_last_month', ascending=False).head(10)
        top_10_products_list = top_10_products[['product_title', 'purchased_last_month']].to_dict('records')
        
        print(f"🏆 TOP 10 제품 조회 완료")
        
        # 4. 진입 난이도 점수 계산 (간단한 모델)
        # 경쟁 제품 수(0-4점), 평균 평점(0-3점), 상위권 리뷰 수(0-3점)
        competitor_score = min(competitor_count / 500, 4)
        avg_rating_score = min(max(0, (filtered_df['product_rating'].mean() - 3.8)) * 2, 3)
        avg_top_reviews = top_10_products['total_reviews'].mean()
        review_score = min(avg_top_reviews / 1000, 3)
        
        difficulty_score = round(competitor_score + avg_rating_score + review_score, 1)
        
        print(f"📈 진입 난이도 점수: {difficulty_score}/10")
        
        return {
            'competitor_count': competitor_count,
            'rating_by_price_bin': rating_by_price_bin,
            'top_10_products_by_sales': top_10_products_list,
            'difficulty_score': difficulty_score
        }

    def find_price_gaps(self, category: str, bin_width: int = 100):
        """
        특정 카테고리 내에서 가격 공백 구간(기회 시장)을 탐색합니다.
        
        Args:
            category (str): 분석할 카테고리.
            bin_width (int): 가격을 나눌 구간의 너비.
            
        Returns:
            dict: 가격 분포 및 잠재적 공백 구간 정보.
        """
        print(f"'{category}' 카테고리 가격 공백 분석 시작 (구간: ${bin_width})...")
        
        category_df = self.df[self.df['product_category'] == category]
        
        if category_df.empty:
            return {'price_distribution': {}, 'price_gaps': {}}
            
        # 가격 분포 계산
        max_price = category_df['discounted_price'].max()
        bins = range(0, int(max_price) + bin_width, bin_width)
        price_distribution = category_df.groupby(pd.cut(category_df['discounted_price'], bins)).size().to_dict()
        price_distribution = {str(k): v for k, v in price_distribution.items()}
        
        # 가격 공백 구간 탐색 (제품 수가 10개 미만인 구간)
        price_gaps = {k: v for k, v in price_distribution.items() if v < 10}
        
        print(f"🔍 가격 공백 구간: {len(price_gaps)}개 발견")
        
        return {
            'price_distribution': price_distribution,
            'price_gaps': price_gaps
        }

    def extract_success_keywords(self, category: str, rating_threshold: float = 4.5, 
                               reviews_threshold: int = 100, num_keywords: int = 20):
        """
        성공적인 제품들(평점 및 리뷰 수가 높은)로부터 핵심 키워드를 추출합니다.
        
        Args:
            category (str): 분석할 카테고리.
            rating_threshold (float): 성공 기준으로 삼을 최소 평점.
            reviews_threshold (int): 성공 기준으로 삼을 최소 리뷰 수.
            num_keywords (int): 추출할 키워드 개수.
            
        Returns:
            dict: 추출된 상위 키워드 목록.
        """
        print(f"'{category}' 카테고리 성공 키워드 분석 (평점>={rating_threshold}, 리뷰>={reviews_threshold})...")
        
        successful_products = self.df[
            (self.df['product_category'] == category) &
            (self.df['product_rating'] >= rating_threshold) &
            (self.df['total_reviews'] >= reviews_threshold)
        ]
        
        if successful_products.empty:
            return {'top_keywords': []}
            
        # 모든 제품명 텍스트를 하나로 합치기
        all_titles = ' '.join(successful_products['product_title'])
        
        # 단어 추출 및 빈도 계산
        words = re.findall(r'\b\w+\b', all_titles.lower())
        
        # 간단한 불용어 처리
        stop_words = {'and', 'the', 'for', 'with', 'in', 'of', 'to', 'a', 'is', 'on', 'hd', 'pro', 'pc', 'usb', 'c'}
        meaningful_words = [word for word in words if word not in stop_words and not word.isdigit()]
        
        keyword_counts = Counter(meaningful_words)
        top_keywords = keyword_counts.most_common(num_keywords)
        
        print(f"🔤 TOP {num_keywords} 키워드 추출 완료")
        
        return {'top_keywords': top_keywords}

    def calculate_market_saturation(self, category: str):
        """
        특정 카테고리의 시장 포화도를 계산합니다.
        (상위 10개 제품이 전체 판매량의 몇 %를 차지하는지로 측정)
        
        Args:
            category (str): 분석할 카테고리.
            
        Returns:
            dict: 시장 포화도(%).
        """
        print(f"'{category}' 카테고리 시장 포화도 계산...")
        
        category_df = self.df[self.df['product_category'] == category]
        
        if category_df.empty:
            return {'market_saturation_percentage': 0}
            
        total_sales = category_df['purchased_last_month'].sum()
        
        if total_sales == 0:
            return {'market_saturation_percentage': 0}
            
        top_10_sales = category_df.sort_values(by='purchased_last_month', ascending=False).head(10)['purchased_last_month'].sum()
        
        saturation_percentage = (top_10_sales / total_sales) * 100
        
        print(f"📈 시장 포화도: {saturation_percentage:.2f}%")
        
        return {'market_saturation_percentage': round(saturation_percentage, 2)}
"""
