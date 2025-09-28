"""
📖 리포트 설명 데이터베이스

각 메트릭과 분석 섹션에 대한 상세 설명과 비즈니스 인사이트를 제공합니다.
"""

from typing import Dict, List, Any

# 리포트 섹션별 설명 데이터베이스
SECTION_EXPLANATIONS = {
    "market_difficulty": {
        "title": "Market Difficulty (시장 진입 난이도)",
        "short_description": "해당 시장에 진입하기 위한 전반적인 난이도를 0-10 척도로 평가합니다.",
        "detailed_explanation": """
        <h3>🎯 Market Difficulty란?</h3>
        <p>시장 진입 난이도는 새로운 셀러가 특정 카테고리에서 성공적으로 사업을 시작할 수 있는 가능성을 나타내는 종합 지표입니다.</p>

        <h4>📊 평가 요소 (총 5가지)</h4>
        <ul>
            <li><strong>경쟁 밀도 (0-2.5점)</strong>: 시장 내 경쟁업체 수</li>
            <li><strong>리뷰 경쟁 강도 (0-2.0점)</strong>: 기존 상품들의 평균 리뷰 수</li>
            <li><strong>품질 표준 (0-2.0점)</strong>: 시장의 평균 상품 평점</li>
            <li><strong>브랜드 포화도 (0-2.0점)</strong>: 시장 내 브랜드 다양성</li>
            <li><strong>가격 경쟁 (0-1.0점)</strong>: 가격 변동성과 경쟁 강도</li>
        </ul>

        <h4>🚦 점수 해석</h4>
        <ul>
            <li><span class="text-green-600 font-semibold">0-3점: 진입 용이</span> - 신규 진입에 유리한 환경</li>
            <li><span class="text-yellow-600 font-semibold">4-6점: 보통 난이도</span> - 차별화 전략 필요</li>
            <li><span class="text-red-600 font-semibold">7-10점: 진입 어려움</span> - 신중한 접근과 강력한 전략 필요</li>
        </ul>
        """,
        "business_implications": """
        <h4>💼 비즈니스 활용법</h4>
        <ul>
            <li><strong>낮은 점수 (0-3):</strong> 빠른 진입과 공격적인 마케팅 전략 고려</li>
            <li><strong>중간 점수 (4-6):</strong> 틈새 시장 발굴이나 제품 차별화에 집중</li>
            <li><strong>높은 점수 (7-10):</strong> 충분한 자본과 장기적 관점으로 접근</li>
        </ul>
        """
    },

    "trending_opportunities": {
        "title": "Trending Opportunities (트렌딩 기회)",
        "short_description": "AI가 분석한 현재 급성장하고 있는 키워드와 시장 기회를 보여줍니다.",
        "detailed_explanation": """
        <h3>🎯 Trending Opportunities란?</h3>
        <p>머신러닝 알고리즘이 검색 트렌드, 판매 데이터, 시장 성장률을 분석하여 발굴한 잠재력 높은 키워드들입니다.</p>

        <h4>📊 평가 지표</h4>
        <ul>
            <li><strong>Trend Score (0-100):</strong> 최근 검색량과 관심도 증가율</li>
            <li><strong>Opportunity Score (0-100):</strong> 시장 기회와 수익성 잠재력</li>
        </ul>

        <h4>🔍 분석 방법</h4>
        <ul>
            <li>검색 트렌드 분석 (Google Trends, 네이버 등)</li>
            <li>경쟁 강도 대비 수요 증가율</li>
            <li>계절성 및 이벤트 연관성</li>
            <li>소셜 미디어 언급량 변화</li>
        </ul>
        """,
        "business_implications": """
        <h4>💼 비즈니스 활용법</h4>
        <ul>
            <li><strong>높은 Trend Score:</strong> 빠른 의사결정으로 트렌드 선점</li>
            <li><strong>높은 Opportunity Score:</strong> 중장기 투자 가치가 높은 분야</li>
            <li><strong>두 점수 모두 높음:</strong> 최우선 진입 고려 대상</li>
        </ul>
        """
    },

    "category_growth": {
        "title": "Category Growth Analysis (카테고리 성장 분석)",
        "short_description": "각 상품 카테고리별 성장률과 시장 규모를 분석하여 가장 유망한 분야를 식별합니다.",
        "detailed_explanation": """
        <h3>🎯 Category Growth Analysis란?</h3>
        <p>상품 카테고리별로 매출 성장률, 시장 규모, 진입 장벽 등을 종합 분석하여 투자 가치를 평가합니다.</p>

        <h4>📊 주요 지표</h4>
        <ul>
            <li><strong>Growth Rate (%):</strong> 최근 6개월 대비 성장률</li>
            <li><strong>Market Size Score:</strong> 시장 규모와 잠재적 수익성</li>
        </ul>

        <h4>🔍 분석 기준</h4>
        <ul>
            <li>판매량 증가 추세</li>
            <li>신규 셀러 진입률</li>
            <li>평균 상품 가격 변화</li>
            <li>소비자 관심도 변화</li>
        </ul>
        """,
        "business_implications": """
        <h4>💼 비즈니스 활용법</h4>
        <ul>
            <li><strong>높은 성장률:</strong> 빠른 시장 확장 기대, 조기 진입 유리</li>
            <li><strong>높은 Market Size Score:</strong> 안정적인 수익 창출 가능</li>
            <li><strong>두 지표 균형:</strong> 리스크 대비 수익률이 최적화된 분야</li>
        </ul>
        """
    },

    "brand_gap": {
        "title": "Brand Gap Analysis (브랜드 갭 분석)",
        "short_description": "시장 내 브랜드별 점유율과 경쟁 강도를 분석하여 브랜드 전략 수립에 도움을 제공합니다.",
        "detailed_explanation": """
        <h3>🎯 Brand Gap Analysis란?</h3>
        <p>시장 내 주요 브랜드들의 점유율과 브랜드 파워를 분석하여 신규 브랜드의 진입 기회를 찾아냅니다.</p>

        <h4>📊 주요 지표</h4>
        <ul>
            <li><strong>Market Share (%):</strong> 해당 브랜드의 시장 점유율</li>
            <li><strong>Brand Strength:</strong> 브랜드 인지도와 고객 충성도</li>
        </ul>

        <h4>🔍 분석 요소</h4>
        <ul>
            <li>브랜드별 판매량과 매출 비중</li>
            <li>고객 리뷰와 평점 분석</li>
            <li>가격 프리미엄 능력</li>
            <li>브랜드 인지도와 검색량</li>
        </ul>
        """,
        "business_implications": """
        <h4>💼 비즈니스 활용법</h4>
        <ul>
            <li><strong>낮은 브랜드 집중도:</strong> 새로운 브랜드 진입 기회</li>
            <li><strong>높은 브랜드 집중도:</strong> 틈새 전략이나 혁신적 차별화 필요</li>
            <li><strong>중간 정도 분산:</strong> 기존 브랜드와의 파트너십 고려</li>
        </ul>
        """
    },

    "ml_predictions": {
        "title": "AI Price Predictions (AI 가격 예측)",
        "short_description": "머신러닝 모델이 예측한 최적 가격과 현재 시장 가격을 비교하여 가격 전략을 제안합니다.",
        "detailed_explanation": """
        <h3>🎯 AI Price Predictions란?</h3>
        <p>고급 머신러닝 알고리즘이 상품 특성, 시장 상황, 경쟁 환경을 종합 분석하여 최적 가격을 예측합니다.</p>

        <h4>🤖 AI 모델 특징</h4>
        <ul>
            <li>수만 개 상품 데이터로 학습</li>
            <li>실시간 시장 상황 반영</li>
            <li>경쟁사 가격 변동 고려</li>
            <li>계절성과 트렌드 분석</li>
        </ul>

        <h4>📊 예측 정확도</h4>
        <ul>
            <li>평균 예측 정확도: 85% 이상</li>
            <li>가격 최적화 효과: 평균 15-25% 매출 증가</li>
        </ul>
        """,
        "business_implications": """
        <h4>💼 비즈니스 활용법</h4>
        <ul>
            <li><strong>현재 가격 > 추천 가격:</strong> 가격 인하로 판매량 증대 고려</li>
            <li><strong>현재 가격 < 추천 가격:</strong> 가격 인상으로 수익성 개선 가능</li>
            <li><strong>가격 차이가 큰 경우:</strong> 우선적으로 가격 조정 검토</li>
        </ul>
        """
    },

    "channel_strategy": {
        "title": "Channel Strategy Analysis (채널 전략 분석)",
        "short_description": "다양한 판매 채널별 시장 점유율과 특성을 분석하여 최적 채널 믹스를 제안합니다.",
        "detailed_explanation": """
        <h3>🎯 Channel Strategy Analysis란?</h3>
        <p>온라인 쇼핑몰, 오픈마켓, 소셜커머스 등 다양한 판매 채널의 특성과 기회를 분석합니다.</p>

        <h4>📊 분석 채널</h4>
        <ul>
            <li>네이버 쇼핑</li>
            <li>쿠팡, 11번가 등 오픈마켓</li>
            <li>브랜드 자체 쇼핑몰</li>
            <li>소셜커머스 플랫폼</li>
        </ul>

        <h4>🔍 평가 요소</h4>
        <ul>
            <li>채널별 트래픽과 전환율</li>
            <li>수수료와 마케팅 비용</li>
            <li>고객 특성과 구매 패턴</li>
            <li>경쟁 강도와 진입 장벽</li>
        </ul>
        """,
        "business_implications": """
        <h4>💼 비즈니스 활용법</h4>
        <ul>
            <li><strong>높은 점유율 채널:</strong> 우선 진입하여 시장 선점</li>
            <li><strong>성장하는 채널:</strong> 조기 진입으로 성장 동력 확보</li>
            <li><strong>틈새 채널:</strong> 차별화된 고객층 공략 기회</li>
        </ul>
        """
    }
}

# 용어 사전 (툴팁용)
TERM_GLOSSARY = {
    "market_difficulty": "시장 진입의 어려움 정도를 0-10 척도로 나타낸 지표",
    "trend_score": "최근 검색량과 관심도 증가율을 0-100으로 표현한 점수",
    "opportunity_score": "시장 기회와 수익성 잠재력을 0-100으로 평가한 점수",
    "growth_rate": "최근 6개월 대비 해당 카테고리의 성장률 (단위: %)",
    "market_size_score": "시장 규모와 잠재적 수익성을 종합 평가한 점수",
    "market_share": "전체 시장에서 해당 브랜드가 차지하는 비율 (단위: %)",
    "brand_strength": "브랜드 인지도와 고객 충성도를 나타내는 지표",
    "competitor_count": "해당 키워드/카테고리에서 경쟁하는 셀러의 수",
    "market_saturation": "시장의 포화 정도를 백분율로 나타낸 지표"
}

# 액션 가이드 (상황별 권장사항)
ACTION_GUIDES = {
    "low_difficulty": {
        "title": "🟢 진입 용이 시장",
        "actions": [
            "빠른 의사결정으로 시장 선점",
            "공격적인 마케팅 전략 수립",
            "초기 물량 확보에 집중",
            "브랜딩보다는 판매량 확대 우선"
        ]
    },
    "medium_difficulty": {
        "title": "🟡 보통 난이도 시장",
        "actions": [
            "차별화된 상품 기획",
            "틈새 고객층 타겟팅",
            "경쟁사 분석 후 전략 수립",
            "품질과 서비스로 경쟁력 확보"
        ]
    },
    "high_difficulty": {
        "title": "🔴 진입 어려운 시장",
        "actions": [
            "충분한 자본과 장기적 관점 필요",
            "혁신적인 제품이나 서비스 개발",
            "강력한 브랜딩 전략 수립",
            "기존 플레이어와의 차별화 필수"
        ]
    }
}

def get_section_explanation(section_key: str) -> Dict[str, Any]:
    """섹션별 설명 정보 반환"""
    return SECTION_EXPLANATIONS.get(section_key, {})

def get_term_definition(term: str) -> str:
    """용어 정의 반환"""
    return TERM_GLOSSARY.get(term.lower(), "정의를 찾을 수 없습니다.")

def get_action_guide(difficulty_level: str) -> Dict[str, Any]:
    """난이도별 액션 가이드 반환"""
    return ACTION_GUIDES.get(difficulty_level, {})

def get_difficulty_level(score: float) -> str:
    """점수에 따른 난이도 레벨 반환"""
    if score <= 3:
        return "low_difficulty"
    elif score <= 6:
        return "medium_difficulty"
    else:
        return "high_difficulty"