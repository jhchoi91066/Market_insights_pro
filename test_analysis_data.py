#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
분석 데이터 구조 및 내용 확인 테스트
"""

import sys
import os
from dotenv import load_dotenv
import json

# 환경 변수 로드
load_dotenv('.env.development')

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.analyzer_v2 import SQLiteMarketAnalyzer

def test_analysis_data():
    """분석 데이터 구조 확인"""

    print("🔍 분석 데이터 구조 및 내용 확인 테스트")
    print("=" * 60)

    analyzer = SQLiteMarketAnalyzer()

    # 테스트할 키워드들
    test_keywords = ["키보드", "마우스", "지갑", "전등"]

    for keyword in test_keywords:
        print(f"\n📊 키워드: '{keyword}' 분석 결과")
        print("-" * 40)

        try:
            # 경쟁 분석
            competition_report = analyzer.analyze_category_competition(keyword)
            print(f"🏆 경쟁 분석 결과:")
            print(json.dumps(competition_report, indent=2, ensure_ascii=False))

            # 시장 포화도 분석
            saturation_report = analyzer.calculate_market_saturation(keyword)
            print(f"\n📈 시장 포화도 분석 결과:")
            print(json.dumps(saturation_report, indent=2, ensure_ascii=False))

            # 합치기 (리포트에서 사용하는 방식)
            report_data = {**competition_report, **saturation_report}
            report_data['keyword'] = keyword

            print(f"\n🎯 최종 리포트 데이터:")
            print(json.dumps(report_data, indent=2, ensure_ascii=False))

        except Exception as e:
            print(f"❌ 키워드 '{keyword}' 분석 중 오류: {str(e)}")

        print("\n" + "=" * 60)

if __name__ == "__main__":
    test_analysis_data()