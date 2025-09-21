#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
네이버 데이터랩 API 통합 테스트
"""

import sys
import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv('.env.development')

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.analyzer_v2 import SQLiteMarketAnalyzer
from core.naver_datalab_api import NaverDataLabAPI

def test_datalab_integration():
    """데이터랩 API 통합 테스트"""

    print("🔗 네이버 데이터랩 API 통합 테스트")
    print("=" * 50)

    # 1. 기본 분석기 초기화
    analyzer = SQLiteMarketAnalyzer()

    # 2. 데이터랩 API 상태 확인
    if analyzer.datalab_api:
        print("✅ 데이터랩 API 연결 성공!")

        # 3. 통합 분석 테스트
        test_keyword = "키보드"
        print(f"\n🔍 테스트 키워드: '{test_keyword}'")

        try:
            # 기존 분석
            print("\n📊 기존 경쟁 분석...")
            competition_result = analyzer.analyze_category_competition(test_keyword)
            print(f"   기존 난이도: {competition_result.get('difficulty_score', 0)}/10")

            # 데이터랩 트렌드 분석
            print("\n📈 데이터랩 트렌드 분석...")
            trend_data = analyzer.datalab_api.get_comprehensive_market_insight(test_keyword, days=14)

            print(f"   트렌드 점수: {trend_data.get('trend_score', 0)}/100")
            print(f"   트렌드 방향: {trend_data.get('trend_direction', 'stable')}")
            print(f"   인기도 지수: {trend_data.get('popularity_index', 0)}")
            print(f"   시장 열기: {trend_data.get('market_heat', 'cold')}")

            # 통합 리포트 생성 (analyzer_v2.py에서 새 메서드 추가 필요)
            print(f"\n📋 통합 분석 결과:")
            print(f"   기존 데이터: 경쟁 제품 {competition_result.get('competitor_count', 0)}개")
            print(f"   트렌드 데이터: {trend_data.get('analysis_period', 'N/A')} 기간 분석")

            # 조합된 인사이트
            market_heat = trend_data.get('market_heat', 'cold')
            difficulty = competition_result.get('difficulty_score', 0)

            if market_heat in ['hot', 'warm'] and difficulty < 5:
                recommendation = "🟢 좋은 기회! 뜨거운 시장에 적당한 경쟁"
            elif market_heat == 'cold' and difficulty > 6:
                recommendation = "🔴 어려운 상황: 관심도 낮고 경쟁 치열"
            else:
                recommendation = "🟡 신중한 접근 필요"

            print(f"\n💡 종합 추천: {recommendation}")

        except Exception as e:
            print(f"❌ 통합 테스트 중 오류: {str(e)}")

    else:
        print("❌ 데이터랩 API 연결 실패")
        print("   - API 키 확인 필요")
        print("   - 데이터랩 API 권한 확인 필요")

        # 기존 분석만 테스트
        test_keyword = "키보드"
        print(f"\n📊 기존 분석만 테스트: '{test_keyword}'")
        competition_result = analyzer.analyze_category_competition(test_keyword)
        print(f"   난이도: {competition_result.get('difficulty_score', 0)}/10")
        print(f"   경쟁 제품: {competition_result.get('competitor_count', 0)}개")

    print("\n" + "=" * 50)

def test_enhanced_analysis():
    """향상된 분석 메서드 테스트 (analyzer_v2.py에 추가할 기능들)"""

    print("🚀 향상된 분석 기능 미리보기")
    print("=" * 50)

    analyzer = SQLiteMarketAnalyzer()
    test_keywords = ["키보드", "마우스", "지갑"]

    for keyword in test_keywords:
        print(f"\n🎯 키워드: '{keyword}'")

        # 기존 분석
        competition = analyzer.analyze_category_competition(keyword)
        saturation = analyzer.calculate_market_saturation(keyword)

        # 데이터 조합
        combined_score = (competition.get('difficulty_score', 0) +
                         saturation.get('market_saturation_percentage', 0) / 10) / 2

        # 추천 생성
        if combined_score < 3:
            recommendation = "🟢 진입 추천"
        elif combined_score < 6:
            recommendation = "🟡 신중한 진입"
        else:
            recommendation = "🔴 진입 비추천"

        print(f"   난이도: {competition.get('difficulty_score', 0):.1f}/10")
        print(f"   포화도: {saturation.get('market_saturation_percentage', 0):.1f}%")
        print(f"   종합 점수: {combined_score:.1f}/10")
        print(f"   추천: {recommendation}")

    print("\n" + "=" * 50)

if __name__ == "__main__":
    test_datalab_integration()
    test_enhanced_analysis()