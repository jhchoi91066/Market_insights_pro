
import pandas as pd
import joblib
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.naver_market_analyzer import NaverMarketAnalyzer
from prophet import Prophet

# .env 파일 로드
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env.development'))

def build_opportunity_recommender():
    """
    시장 기회 추천 시스템을 구축하고 실행합니다.
    """
    print("🚀 시장 기회 추천 시스템 구축 시작...")
    print("=" * 50)

    # 1단계: 데이터 및 모델 로딩
    print("🔄 데이터 및 모델 로딩 중...")
    # NaverMarketAnalyzer 초기화
    try:
        analyzer = NaverMarketAnalyzer()
        print("✅ NaverMarketAnalyzer 초기화 완료")
    except ValueError as e:
        print(f"❌ NaverMarketAnalyzer 초기화 실패: {e}")
        print("💡 .env 파일에 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET이 올바르게 설정되었는지 확인해주세요.")
        return

    # 훈련된 모델 로드
    model_dir = os.path.join(os.path.dirname(__file__), 'models')
    price_model_path = os.path.join(model_dir, "price_predictor_v1.joblib")
    demand_model_path = os.path.join(model_dir, "demand_forecaster_v1.joblib")

    try:
        price_predictor = joblib.load(price_model_path)
        print(f"✅ 가격 예측 모델 로드 완료: {price_model_path}")
    except FileNotFoundError:
        print(f"❌ 가격 예측 모델({price_model_path})을 찾을 수 없습니다. 먼저 01_train_price_predictor.py를 실행해주세요.")
        return

    try:
        demand_forecaster = joblib.load(demand_model_path)
        print(f"✅ 수요 예측 모델 로드 완료: {demand_model_path}")
    except FileNotFoundError:
        print(f"❌ 수요 예측 모델({demand_model_path})을 찾을 수 없습니다. 먼저 02_train_demand_forecaster.py를 실행해주세요.")
        return

    # 추천할 키워드 목록 (데이터셋 생성에 사용했던 키워드)
    keywords_to_recommend = [
        '키보드',
        '블루투스 이어폰',
        '모니터',
        '물통',
        '캠핑 의자',
        '마우스',
        '커피 원두'
    ]

    recommendations = []

    print("\n🚀 2단계: 각 키워드에 대한 분석 및 기회 점수 계산...")
    print("=" * 50)

    for keyword in keywords_to_recommend:
        print(f"🔍 키워드 '{keyword}' 분석 중...")
        try:
            # 1. 경쟁 강도 및 트렌드 데이터 분석
            analysis_result = analyzer.get_trend_enhanced_analysis(keyword, days=14, product_count=50)
            difficulty_score = analysis_result.get('adjusted_difficulty_score', 10) # 낮을수록 좋음
            market_heat = analysis_result.get('trend_data', {}).get('market_heat', 'cold')
            trend_direction = analysis_result.get('trend_data', {}).get('trend_direction', 'stable')

            # 2. 수요 예측 (Prophet 모델 사용)
            # Prophet 모델은 시계열 데이터프레임을 필요로 하므로, API에서 다시 가져와야 함
            search_trends_raw = analyzer.datalab_api.get_search_trends([keyword], days=365*2)
            if not search_trends_raw or not search_trends_raw.get('results'):
                print(f"⚠️ 키워드 '{keyword}'에 대한 수요 트렌드 데이터를 찾을 수 없습니다. 건너뜁니다.")
                continue

            data_points = search_trends_raw['results'][0]['data']
            df_demand = pd.DataFrame(data_points)
            df_demand.rename(columns={'period': 'ds', 'ratio': 'y'}, inplace=True)
            df_demand['ds'] = pd.to_datetime(df_demand['ds'])

            # 미래 예측 (90일)
            future = demand_forecaster.make_future_dataframe(periods=90)
            forecast = demand_forecaster.predict(future)

            # 미래 트렌드 방향 판단 (예측된 마지막 30일의 평균 vs 이전 30일의 평균)
            if len(forecast) > 60:
                predicted_recent_avg = forecast['yhat'].iloc[-30:].mean()
                predicted_previous_avg = forecast['yhat'].iloc[-60:-30].mean()
                demand_change_percent = ((predicted_recent_avg - predicted_previous_avg) / predicted_previous_avg * 100) if predicted_previous_avg > 0 else 0
            else:
                demand_change_percent = 0

            demand_trend_status = "stable"
            if demand_change_percent > 5: # 5% 이상 증가하면 상승
                demand_trend_status = "rising"
            elif demand_change_percent < -5: # 5% 이상 감소하면 하락
                demand_trend_status = "falling"

            # 3. 규칙 기반 기회 점수 계산
            opportunity_score = 0
            reasons = []

            # 난이도 점수 (낮을수록 좋음)
            if difficulty_score < 4:
                opportunity_score += 3
                reasons.append("낮은 경쟁 강도")
            elif difficulty_score < 7:
                opportunity_score += 1
                reasons.append("중간 경쟁 강도")

            # 수요 트렌드 (상승할수록 좋음)
            if demand_trend_status == "rising":
                opportunity_score += 4
                reasons.append("수요 상승 트렌드")
            elif demand_trend_status == "stable":
                opportunity_score += 2
                reasons.append("안정적인 수요")

            # 시장 열기 (뜨거울수록 좋음)
            if market_heat == "hot":
                opportunity_score += 2
                reasons.append("뜨거운 시장 열기")
            elif market_heat == "warm":
                opportunity_score += 1
                reasons.append("따뜻한 시장 열기")

            recommendations.append({
                'keyword': keyword,
                'opportunity_score': opportunity_score,
                'difficulty_score': difficulty_score,
                'market_heat': market_heat,
                'demand_trend_status': demand_trend_status,
                'reasons': reasons
            })

        except Exception as e:
            print(f"❌ 키워드 '{keyword}' 분석 중 오류 발생: {e}")

    # 4단계: 추천 결과 생성 및 출력
    print("\n✨ 시장 기회 추천 결과:")
    print("=" * 50)

    if not recommendations:
        print("추천할 시장 기회를 찾을 수 없습니다.")
        return

    # 기회 점수 기준으로 정렬 (높은 점수 우선)
    recommendations.sort(key=lambda x: x['opportunity_score'], reverse=True)

    for i, rec in enumerate(recommendations, 1):
        print(f"{i}. 키워드: {rec['keyword']} (기회 점수: {rec['opportunity_score']})")
        print(f"   - 경쟁 난이도: {rec['difficulty_score']}")
        print(f"   - 시장 열기: {rec['market_heat']}")
        print(f"   - 수요 트렌드: {rec['demand_trend_status']}")
        print(f"   - 추천 이유: {', '.join(rec['reasons']) if rec['reasons'] else '해당 없음'}")
        print("-" * 20)

    print("\n✅ 시장 기회 추천 시스템 구축 및 실행 완료.")

if __name__ == "__main__":
    build_opportunity_recommender()
