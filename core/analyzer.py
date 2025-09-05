# -*- coding: utf-8 -*-
"""
이 파일은 Market Insights Pro 프로젝트의 핵심 분석 엔진인 MarketAnalyzer 클래스를 정의합니다.
데이터를 입력받아 다양한 시장 분석 기능을 수행하는 메소드들을 포함하게 될 예정입니다.
"""
import pandas as pd
import numpy as np
import re
from collections import Counter

class MarketAnalyzer:
    """
    시장 데이터 분석을 수행하는 핵심 클래스.
    """
    def __init__(self, data_path):
        """
        분석기 초기화. 데이터셋을 로드하고 준비합니다.
        """
        print(f"MarketAnalyzer를 초기화합니다. 데이터 경로: {data_path}")
        try:
            self.df = pd.read_csv(data_path)
            print("데이터 로드 성공!")
        except FileNotFoundError:
            print(f"오류: 데이터 파일을 찾을 수 없습니다. 경로: {data_path}")
            self.df = pd.DataFrame()

    def analyze_category_competition(self, category, price_range, num_bins=4):
        """
        특정 카테고리의 경쟁 강도를 분석합니다.
        """
        print(f"'{category}' 카테고리의 경쟁 강도 분석 (가격대: ${price_range[0]} - ${price_range[1]})...")
        category_df = self.df[self.df['product_category'] == category].copy()
        min_price, max_price = price_range
        target_df = category_df[
            (category_df['discounted_price'] >= min_price) & 
            (category_df['discounted_price'] <= max_price)
        ].copy()
        
        competitor_count = len(target_df)
        print(f"-> 분석 결과: 해당 조건의 경쟁 제품 수는 {competitor_count}개입니다.")

        rating_by_price_bin = pd.Series()
        if competitor_count > 0:
            price_bins = pd.cut(target_df['discounted_price'], bins=num_bins)
            rating_by_price_bin = target_df.groupby(price_bins, observed=False)['product_rating'].mean().round(2)
            print("\n-> 가격 구간별 평균 평점:")
            print(rating_by_price_bin)

        top_10_products = pd.DataFrame()
        if competitor_count > 0:
            print("\n-> 판매량 기준 TOP 10 제품:")
            top_10_products = target_df.sort_values(by='purchased_last_month', ascending=False).head(10)
            display_cols = ['product_title', 'discounted_price', 'product_rating', 'purchased_last_month']
            print(top_10_products[display_cols].reset_index(drop=True))

        difficulty_score = 0
        if competitor_count > 0:
            competitor_score = min(competitor_count / 500, 4)
            avg_rating = target_df['product_rating'].mean()
            rating_score = min(max(0, (avg_rating - 3.8)) * 2, 3)
            avg_top_reviews = top_10_products['total_reviews'].mean()
            review_score = min(np.log10(avg_top_reviews + 1), 3)
            difficulty_score = round(competitor_score + rating_score + review_score, 1)
            print(f"\n-> 진입 난이도 점수: {difficulty_score} / 10")
            print(f"   (경쟁강도: {round(competitor_score,1)}, 품질기대치: {round(rating_score,1)}, 상위권장벽: {round(review_score,1)})")

        # FastAPI가 JSON으로 변환할 수 있도록 pandas 객체를 파이썬 기본 객체로 변환합니다.
        return {
            'competitor_count': competitor_count,
            'rating_by_price_bin': {str(k): v for k, v in rating_by_price_bin.to_dict().items()},
            'top_10_products': top_10_products.to_dict('records'),
            'difficulty_score': difficulty_score
        }

    def find_price_gaps(self, category, bin_width=100):
        """
        특정 카테고리 내에서 가격 공백 구간(기회 시장)을 탐색합니다.
        """
        print(f"\n'{category}' 카테고리의 가격 공백 구간 탐색 (구간 너비: ${bin_width})...")
        category_df = self.df[self.df['product_category'] == category].copy()
        if category_df.empty:
            print("-> 해당 카테고리의 제품이 없습니다.")
            return pd.Series()

        min_price = int(category_df['discounted_price'].min())
        max_price = int(category_df['discounted_price'].max())
        bins = range(min_price, max_price + bin_width, bin_width)
        price_dist = pd.cut(category_df['discounted_price'], bins=bins, right=False).value_counts().sort_index()
        
        print("\n-> 가격대별 제품 분포:")
        print(price_dist)
        
        price_gaps = price_dist[price_dist < 10]
        print("\n-> 잠재적 가격 공백 구간 (제품 10개 미만):")
        if price_gaps.empty:
            print("특별한 가격 공백 구간이 발견되지 않았습니다.")
        else:
            print(price_gaps)

        # API 응답을 위해 JSON 친화적인 형태로 변환
        price_dist_dict = {str(k): v for k, v in price_dist.to_dict().items()}
        price_gaps_dict = {str(k): v for k, v in price_gaps.to_dict().items()}
        return {
            'price_distribution': price_dist_dict,
            'price_gaps': price_gaps_dict
        }

    def extract_success_keywords(self, category, rating_threshold=4.5, reviews_threshold=100, num_keywords=20):
        """
        성공적인 제품들로부터 핵심 키워드를 추출합니다.
        """
        print(f"\n'{category}' 카테고리 성공 키워드 추출 (평점 >= {rating_threshold}, 리뷰 >= {reviews_threshold})...")
        successful_products = self.df[
            (self.df['product_category'] == category) &
            (self.df['product_rating'] >= rating_threshold) &
            (self.df['total_reviews'] >= reviews_threshold)
        ]
        
        if successful_products.empty:
            print("-> 해당 기준을 만족하는 성공적인 제품을 찾을 수 없습니다.")
            return {'top_keywords': []}

        all_titles = ' '.join(successful_products['product_title'])
        words = re.findall(r'\b\w+\b', all_titles.lower())
        
        stop_words = set(['and', 'the', 'for', 'with', 'in', 'of', 'to', 'a', 'is', 'on', 'hd', 'pro', 'pc', 'usb', 'c', 'with', 'to', 'inch'])
        meaningful_words = [word for word in words if word not in stop_words and not word.isdigit() and len(word) > 2]
        
        keyword_counts = Counter(meaningful_words)
        
        print(f"\n-> '{category}' 카테고리 TOP {num_keywords} 성공 키워드:")
        top_keywords = keyword_counts.most_common(num_keywords)
        print(top_keywords)
        
        return {'top_keywords': top_keywords}

    def calculate_market_saturation(self, category):
        """
        특정 카테고리의 시장 포화도를 계산합니다.
        상위 10개 제품이 전체 판매량의 몇 %를 차지하는지로 측정합니다.
        :param category: 분석할 카테고리
        :return: 시장 포화도 (0-100%)
        """
        print(f"\n'{category}' 카테고리의 시장 포화도 계산...")
        
        category_df = self.df[self.df['product_category'] == category].copy()
        
        if category_df.empty:
            print("-> 해당 카테고리의 제품이 없습니다.")
            return {'market_saturation_percentage': 0}

        total_sales = category_df['purchased_last_month'].sum()
        
        if total_sales == 0:
            print("-> 해당 카테고리는 판매 기록이 없습니다.")
            return {'market_saturation_percentage': 0}
            
        top_10_products = category_df.sort_values(by='purchased_last_month', ascending=False).head(10)
        top_10_sales = top_10_products['purchased_last_month'].sum()
        
        saturation_percentage = (top_10_sales / total_sales) * 100
        
        print(f"-> 전체 판매량: {total_sales}")
        print(f"-> TOP 10 제품 판매량: {top_10_sales}")
        print(f"-> 시장 포화도: {saturation_percentage:.2f}%")
        
        return {'market_saturation_percentage': round(saturation_percentage, 2)}

if __name__ == '__main__':
    data_file_path = '/Users/jinhochoi/Desktop/개발/Market_insights/data/amazon_products_sales_data_cleaned.csv'
    analyzer = MarketAnalyzer(data_file_path)
    
    if not analyzer.df.empty:
        print("\nMarketAnalyzer 테스트 호출:")
        # analyzer.analyze_category_competition('Laptops', (200, 1000), num_bins=5)
        # print("\n-----------------------------------\n")
        # analyzer.find_price_gaps('Phones', bin_width=50)
        # print("\n-----------------------------------\n")
        # analyzer.extract_success_keywords('Headphones', rating_threshold=4.5, reviews_threshold=500)
        print("\n-----------------------------------\n")
        analyzer.calculate_market_saturation('Printers & Scanners')
