"""
ML serving API의 특성 전처리를 훈련된 모델과 동일하게 맞추기
"""
import pandas as pd
import numpy as np
from typing import List

def create_correct_feature_preprocessor():
    """훈련된 모델과 동일한 특성 전처리 함수 생성"""

    # 모든 특성 이름 로드
    with open('/Users/jinhochoi/Desktop/개발/Market_insights/model_features.txt', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    feature_names = []
    for line in lines:
        if ':' in line:
            feature_name = line.split(':', 1)[1].strip()
            feature_names.append(feature_name)

    print(f"✅ 총 {len(feature_names)}개 특성 로드")

    # 범주형 특성별로 가능한 값들 추출
    categorical_mapping = {}

    for feature_name in feature_names:
        if '_' in feature_name and not feature_name.startswith(('rating', 'review', 'purchased', 'is_', 'price')):
            prefix = feature_name.split('_')[0]
            value = feature_name.split('_', 1)[1]

            if prefix not in categorical_mapping:
                categorical_mapping[prefix] = []
            categorical_mapping[prefix].append(value)

    print(f"\n📊 범주형 특성 매핑:")
    for prefix, values in categorical_mapping.items():
        print(f"  {prefix}: {len(values)}개 값")

    # 새로운 전처리 함수 코드 생성
    function_code = f'''
def _prepare_price_prediction_input_correct(self, request) -> pd.DataFrame:
    """훈련된 모델과 동일한 특성으로 입력 데이터 전처리"""

    # 기본 숫자 특성들
    data = {{
        'rating': request.rating,
        'review_count': request.review_count,
        'purchased_last_month': getattr(request, 'purchased_last_month', 0),  # 기본값 0
        'is_prime': getattr(request, 'is_prime', 0),  # 기본값 0
        'price_to_category_avg_ratio': request.price_to_category_avg_ratio,
        'price_to_keyword_avg_ratio': request.price_to_keyword_avg_ratio,
        'price_x_rating': request.rating * (request.price_to_category_avg_ratio * 50),  # 추정 가격
        'rating_x_review_count': request.rating * request.review_count,
        'price_x_review_count': (request.price_to_category_avg_ratio * 50) * request.review_count
    }}

    # 모든 범주형 특성을 0으로 초기화
'''

    # 각 범주형 특성에 대한 원-핫 인코딩 초기화
    for prefix, values in categorical_mapping.items():
        for value in values:
            function_code += f'''
    data['{prefix}_{value}'] = 0'''

    function_code += '''

    # 실제 값에 따라 해당 특성을 1로 설정
    # category 처리 (정확한 매핑 필요)
    category_value = getattr(request, 'category', 'Unknown')'''

    # category 값들에 대한 처리
    if 'category' in categorical_mapping:
        function_code += f'''
    category_mapping = {categorical_mapping['category']}
    if category_value in category_mapping:
        data[f'category_{{category_value}}'] = 1
    elif category_mapping:  # 기본값으로 첫 번째 값 사용
        data[f'category_{{category_mapping[0]}}'] = 1'''

    # brand 처리
    if 'brand' in categorical_mapping:
        function_code += f'''

    # brand 처리
    brand_value = getattr(request, 'brand', 'Unknown')
    brand_mapping = {categorical_mapping['brand']}
    if brand_value in brand_mapping:
        data[f'brand_{{brand_value}}'] = 1
    elif 'Unknown' in brand_mapping:
        data['brand_Unknown'] = 1
    elif brand_mapping:  # 기본값으로 첫 번째 값 사용
        data[f'brand_{{brand_mapping[0]}}'] = 1'''

    # seller 처리
    if 'seller' in categorical_mapping:
        function_code += f'''

    # seller 처리
    seller_value = getattr(request, 'seller', 'Unknown')
    seller_mapping = {categorical_mapping['seller']}
    if seller_value in seller_mapping:
        data[f'seller_{{seller_value}}'] = 1
    elif 'Unknown' in seller_mapping:
        data['seller_Unknown'] = 1
    elif seller_mapping:  # 기본값으로 첫 번째 값 사용
        data[f'seller_{{seller_mapping[0]}}'] = 1'''

    # search_keyword 처리
    if 'search' in categorical_mapping:
        function_code += f'''

    # search_keyword 처리
    keyword_value = getattr(request, 'search_keyword', '')
    search_mapping = {categorical_mapping['search']}
    keyword_found = False
    for search_key in search_mapping:
        if keyword_value in search_key or search_key in keyword_value:
            data[f'search_{{search_key}}'] = 1
            keyword_found = True
            break
    if not keyword_found and search_mapping:
        data[f'search_{{search_mapping[0]}}'] = 1'''

    # maker 처리
    if 'maker' in categorical_mapping:
        function_code += f'''

    # maker 처리
    maker_value = getattr(request, 'maker', 'Unknown')
    maker_mapping = {categorical_mapping['maker']}
    if maker_value in maker_mapping:
        data[f'maker_{{maker_value}}'] = 1
    elif 'Unknown' in maker_mapping:
        data['maker_Unknown'] = 1
    elif maker_mapping:  # 기본값으로 첫 번째 값 사용
        data[f'maker_{{maker_mapping[0]}}'] = 1'''

    # naver 카테고리 처리 (기본값 설정)
    if 'naver' in categorical_mapping:
        function_code += f'''

    # naver 카테고리 기본값 설정
    naver_mapping = {categorical_mapping['naver']}
    # 기본값으로 첫 번째 naver 카테고리 설정
    if naver_mapping:
        data[f'naver_{{naver_mapping[0]}}'] = 1'''

    function_code += f'''

    # 정확한 순서로 DataFrame 생성
    feature_order = {feature_names}
    ordered_data = [data.get(feature, 0) for feature in feature_order]

    return pd.DataFrame([ordered_data], columns=feature_order)
'''

    return function_code, categorical_mapping, feature_names

if __name__ == "__main__":
    function_code, mapping, features = create_correct_feature_preprocessor()

    # 파일로 저장
    with open('/Users/jinhochoi/Desktop/개발/Market_insights/correct_preprocessor.py', 'w', encoding='utf-8') as f:
        f.write(function_code)

    print(f"✅ 올바른 전처리 함수가 'correct_preprocessor.py'에 저장되었습니다!")
    print(f"총 특성 수: {len(features)}개")