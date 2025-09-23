
import pandas as pd
from prophet import Prophet
import matplotlib.pyplot as plt
import os
import sys
import joblib
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.naver_datalab_api import NaverDataLabAPI

# .env 파일 로드
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env.development'))

def train_demand_forecasting_model():
    """
    Facebook Prophet을 사용하여 수요 예측 모델을 훈련하고 저장합니다.
    """
    print("🚀 Step 1: 시계열 데이터 수집 (Time-series Data Collection)")
    print("=" * 50)

    # 1. Naver DataLab API 초기화
    try:
        client_id = os.getenv('NAVER_CLIENT_ID')
        client_secret = os.getenv('NAVER_CLIENT_SECRET')
        if not client_id or not client_secret:
            raise ValueError("네이버 API 키가 설정되지 않았습니다.")
        datalab_api = NaverDataLabAPI(client_id, client_secret)
        print("✅ Naver DataLab API 클라이언트 초기화 완료")
    except ValueError as e:
        print(f"❌ API 클라이언트 초기화 실패: {e}")
        print("💡 .env 파일에 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET이 올바르게 설정되었는지 확인해주세요.")
        return

    # 2. 특정 키워드에 대한 트렌드 데이터 가져오기 (예: '캠핑 의자')
    keyword = '캠핑 의자' # 예측할 키워드
    days_to_fetch = 365 * 2 # 지난 2년간의 데이터

    print(f"🔍 키워드 '{keyword}'에 대한 지난 {days_to_fetch}일간의 트렌드 데이터 수집 중...")
    search_trends_raw = datalab_api.get_search_trends([keyword], days=days_to_fetch)

    if not search_trends_raw or not search_trends_raw.get('results'):
        print(f"❌ 키워드 '{keyword}'에 대한 트렌드 데이터를 찾을 수 없습니다.")
        return

    # 3. Prophet 모델용 데이터 준비 (ds, y 컬럼)
    print("🔄 Prophet 모델용 데이터 준비 중...")
    data_points = search_trends_raw['results'][0]['data']
    df = pd.DataFrame(data_points)
    df.rename(columns={'period': 'ds', 'ratio': 'y'}, inplace=True)
    df['ds'] = pd.to_datetime(df['ds'])
    print(f"✅ 데이터 준비 완료: {len(df)}개 데이터 포인트")

    print("\n🚀 Step 2: Prophet 모델 훈련 (Model Training)")
    print("=" * 50)

    # 1. Prophet 모델 초기화 및 훈련
    # weekly_seasonality, yearly_seasonality: 주간/연간 계절성 패턴 학습 여부
    model = Prophet(
        weekly_seasonality=True,
        yearly_seasonality=True,
        daily_seasonality=False # 일간 계절성은 데이터가 시간 단위일 때 유용
    )

    print("🔥 Prophet 모델 훈련 시작...")
    model.fit(df)
    print("✅ 모델 훈련 완료!")

    print("\n🚀 Step 3: 미래 수요 예측 (Future Prediction)")
    print("=" * 50)

    # 1. 예측할 미래 기간 설정 (예: 90일)
    future = model.make_future_dataframe(periods=90)

    # 2. 예측 수행
    forecast = model.predict(future)
    print(f"✅ 향후 {90}일간의 수요 예측 완료!")

    print("\n🚀 Step 4: 결과 시각화 및 모델 저장 (Visualization & Saving)")
    print("=" * 50)

    # 1. 예측 결과 시각화
    fig1 = model.plot(forecast)
    plt.title(f'{keyword}' + ' 검색량 트렌드 예측')
    plt.xlabel('날짜')
    plt.ylabel('검색량 비율')

    # 플롯 저장 디렉토리 생성
    plot_dir = os.path.join(os.path.dirname(__file__), 'plots')
    os.makedirs(plot_dir, exist_ok=True)
    plot_path = os.path.join(plot_dir, "demand_forecast_v1.png")
    fig1.savefig(plot_path)
    print(f"✅ 예측 그래프 저장 완료: {plot_path}")

    # 2. 모델 저장
    model_dir = os.path.join(os.path.dirname(__file__), 'models')
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "demand_forecaster_v1.joblib")
    joblib.dump(model, model_path)
    print(f"✅ 모델 저장 완료: {model_path}")

    print("\n✨ 수요 예측 모델 훈련 파이프라인이 성공적으로 완료되었습니다.")

if __name__ == "__main__":
    train_demand_forecasting_model()
