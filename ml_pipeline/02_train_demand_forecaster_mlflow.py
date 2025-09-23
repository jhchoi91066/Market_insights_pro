import pandas as pd
from prophet import Prophet
import matplotlib.pyplot as plt
import os
import sys
import joblib
import pickle
from datetime import datetime, timedelta
from dotenv import load_dotenv
import mlflow
import mlflow.sklearn
import yaml
import numpy as np

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.naver_datalab_api import NaverDataLabAPI
from core.mlflow_manager import get_mlflow_manager

# .env 파일 로드
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env.development'))

def train_demand_forecasting_model():
    """
    Facebook Prophet을 사용하여 수요 예측 모델을 훈련하고 저장합니다.
    MLflow를 사용하여 실험을 추적하고 모델을 관리합니다.
    """
    print("🚀 MLflow 기반 수요 예측 모델 훈련 시작")
    print("=" * 60)

    # MLflow 매니저 초기화
    mlflow_manager = get_mlflow_manager()

    # 실험 생성 또는 기존 실험 사용
    experiment_name = "demand_forecasting"
    mlflow_manager.create_experiment(
        experiment_name=experiment_name,
        description="네이버 데이터랩 기반 수요 예측 모델 실험",
        tags={"team": "market_insights", "model_type": "time_series", "algorithm": "prophet"}
    )

    # MLflow 실행 시작
    run_name = f"demand_forecast_run_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}"

    with mlflow_manager.start_run(experiment_name, run_name,
                                 tags={"version": "v1.0", "data_source": "naver_datalab"}):

        print("\n🚀 Step 1: 시계열 데이터 수집 (Time-series Data Collection)")
        print("=" * 50)

        # 1. Naver DataLab API 초기화
        try:
            client_id = os.getenv('NAVER_CLIENT_ID')
            client_secret = os.getenv('NAVER_CLIENT_SECRET')
            if not client_id or not client_secret:
                raise ValueError("네이버 API 키가 설정되지 않았습니다.")
            datalab_api = NaverDataLabAPI(client_id, client_secret)
            print("✅ Naver DataLab API 클라이언트 초기화 완료")

            # API 정보 로깅
            mlflow.log_param("api_source", "naver_datalab")

        except ValueError as e:
            print(f"❌ API 클라이언트 초기화 실패: {e}")
            print("💡 .env 파일에 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET이 올바르게 설정되었는지 확인해주세요.")
            return

        # 2. 특정 키워드에 대한 트렌드 데이터 가져오기
        keyword = '캠핑 의자'
        days_to_fetch = 365 * 2  # 지난 2년간의 데이터

        print(f"🔍 키워드 '{keyword}'에 대한 지난 {days_to_fetch}일간의 트렌드 데이터 수집 중...")

        # 실험 파라미터 로깅
        mlflow.log_param("keyword", keyword)
        mlflow.log_param("days_to_fetch", days_to_fetch)
        mlflow.log_param("forecast_period", 30)

        search_trends_raw = datalab_api.get_search_trends([keyword], days=days_to_fetch)

        if not search_trends_raw or not search_trends_raw.get('results'):
            print(f"❌ 키워드 '{keyword}'에 대한 트렌드 데이터를 찾을 수 없습니다.")
            mlflow.log_param("data_collection_status", "FAILED")
            return

        print("✅ 트렌드 데이터 수집 완료")
        mlflow.log_param("data_collection_status", "SUCCESS")

        # 3. Prophet 모델용 데이터 준비 (ds, y 컬럼)
        print("\n🚀 Step 2: 데이터 전처리 (Data Preprocessing)")
        print("=" * 50)

        # 첫 번째 결과만 사용 (하나의 키워드)
        trend_data = search_trends_raw['results'][0]['data']

        # 데이터프레임 생성
        df = pd.DataFrame(trend_data)
        df['ds'] = pd.to_datetime(df['period'])  # Prophet이 요구하는 'ds' 컬럼
        df['y'] = df['ratio']  # Prophet이 요구하는 'y' 컬럼

        # 결측치 처리 (선형 보간)
        df['y'] = df['y'].interpolate(method='linear')
        df = df[['ds', 'y']].dropna()

        print(f"✅ 데이터 전처리 완료: {len(df)}개의 데이터 포인트")
        print(f"   - 기간: {df['ds'].min()} ~ {df['ds'].max()}")
        print(f"   - 평균 검색량: {df['y'].mean():.2f}")
        print(f"   - 검색량 변동폭: {df['y'].std():.2f}")

        # 데이터 정보 로깅
        mlflow.log_param("data_points", len(df))
        mlflow.log_param("start_date", df['ds'].min().strftime('%Y-%m-%d'))
        mlflow.log_param("end_date", df['ds'].max().strftime('%Y-%m-%d'))
        mlflow.log_metric("mean_search_volume", df['y'].mean())
        mlflow.log_metric("std_search_volume", df['y'].std())

        # 데이터 시각화
        plt.figure(figsize=(12, 6))
        plt.plot(df['ds'], df['y'])
        plt.title(f"키워드 '{keyword}' 검색 트렌드")
        plt.xlabel("날짜")
        plt.ylabel("검색량 (상대적 비율)")
        plt.grid(True, alpha=0.3)

        # 차트 저장 및 MLflow에 아티팩트로 저장
        chart_path = os.path.join(os.path.dirname(__file__), 'plots', f'search_trend_{keyword.replace(" ", "_")}.png')
        os.makedirs(os.path.dirname(chart_path), exist_ok=True)
        plt.savefig(chart_path)
        plt.close()

        mlflow.log_artifact(chart_path, "plots")
        print(f"📊 트렌드 차트 저장 완료: {chart_path}")

        print("\n🚀 Step 3: Prophet 모델 훈련 (Model Training)")
        print("=" * 50)

        # Prophet 모델 설정
        prophet_params = {
            'yearly_seasonality': True,
            'weekly_seasonality': True,
            'daily_seasonality': False,
            'seasonality_mode': 'multiplicative',
            'changepoint_prior_scale': 0.05,
            'seasonality_prior_scale': 10.0,
            'uncertainty_samples': 1000
        }

        # MLflow에 하이퍼파라미터 로깅
        mlflow.log_params(prophet_params)

        # Prophet 모델 생성 및 훈련
        model = Prophet(**prophet_params)

        print("🔥 Prophet 모델 훈련 시작...")
        model.fit(df)
        print("✅ Prophet 모델 훈련 완료!")

        print("\n🚀 Step 4: 미래 예측 및 평가 (Forecasting & Evaluation)")
        print("=" * 50)

        # 미래 30일 예측
        forecast_days = 30
        future = model.make_future_dataframe(periods=forecast_days)
        forecast = model.predict(future)

        # 예측 결과 시각화
        fig = model.plot(forecast, figsize=(15, 8))
        plt.title(f"키워드 '{keyword}' 수요 예측 (향후 {forecast_days}일)")
        plt.xlabel("날짜")
        plt.ylabel("검색량 (상대적 비율)")

        # 예측 차트 저장
        forecast_chart_path = os.path.join(os.path.dirname(__file__), 'plots', f'forecast_{keyword.replace(" ", "_")}.png')
        plt.savefig(forecast_chart_path)
        plt.close()

        mlflow.log_artifact(forecast_chart_path, "plots")
        print(f"📊 예측 차트 저장 완료: {forecast_chart_path}")

        # 계절성 분석 차트
        fig2 = model.plot_components(forecast, figsize=(15, 10))
        components_path = os.path.join(os.path.dirname(__file__), 'plots', f'components_{keyword.replace(" ", "_")}.png')
        plt.savefig(components_path)
        plt.close()

        mlflow.log_artifact(components_path, "plots")
        print("📊 계절성 분석 차트 저장 완료")

        # 백테스팅을 통한 성능 평가
        print("\n📊 백테스팅을 통한 모델 성능 평가...")

        # 마지막 30일을 테스트셋으로 사용
        train_data = df[:-30]
        test_data = df[-30:]

        if len(test_data) > 0:
            # 테스트용 모델 훈련
            test_model = Prophet(**prophet_params)
            test_model.fit(train_data)

            # 테스트 기간 예측
            test_future = test_model.make_future_dataframe(periods=30)
            test_forecast = test_model.predict(test_future)

            # 예측 성능 평가
            test_predictions = test_forecast[-30:]['yhat'].values
            test_actual = test_data['y'].values

            # MAPE (Mean Absolute Percentage Error) 계산
            mape = np.mean(np.abs((test_actual - test_predictions) / test_actual)) * 100
            mae = np.mean(np.abs(test_actual - test_predictions))
            rmse = np.sqrt(np.mean((test_actual - test_predictions)**2))

            # 메트릭 로깅
            mlflow.log_metric("mape", mape)
            mlflow.log_metric("mae", mae)
            mlflow.log_metric("rmse", rmse)

            print(f"📈 모델 성능 평가:")
            print(f"   - MAPE (평균 절대 백분율 오차): {mape:.2f}%")
            print(f"   - MAE (평균 절대 오차): {mae:.2f}")
            print(f"   - RMSE (평균 제곱근 오차): {rmse:.2f}")

        print("\n🚀 Step 5: 모델 저장 (Model Saving)")
        print("=" * 50)

        # Prophet 모델은 MLflow의 sklearn 형식으로 저장
        # Prophet 모델을 pickle로 직렬화
        model_wrapper = {
            'model': model,
            'keyword': keyword,
            'forecast_days': forecast_days,
            'prophet_params': prophet_params
        }

        # MLflow에 모델 저장 (sklearn 형식으로)
        mlflow.sklearn.log_model(
            sk_model=model_wrapper,
            artifact_path="demand_forecaster",
            registered_model_name="demand_forecaster"
        )

        # 로컬에도 백업 저장
        output_dir = os.path.join(os.path.dirname(__file__), 'models')
        os.makedirs(output_dir, exist_ok=True)
        model_path = os.path.join(output_dir, f"demand_forecaster_mlflow_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.pkl")

        with open(model_path, 'wb') as f:
            pickle.dump(model_wrapper, f)

        print(f"💾 로컬 백업 저장 완료: {model_path}")

        # 성능 임계값 확인
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mlflow_config.yaml")
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            thresholds = config.get("performance_thresholds", {}).get("demand_forecasting", {})
            mape_threshold = thresholds.get("mape_threshold", 15.0)

            print("\n🎯 성능 임계값 확인:")
            if len(test_data) > 0:
                mape_pass = mape <= mape_threshold
                print(f"   - MAPE: {mape:.2f}% <= {mape_threshold}% {'✅' if mape_pass else '❌'}")

                if mape_pass:
                    print("🎉 성능 임계값을 통과했습니다!")
                    mlflow.log_param("performance_check", "PASSED")
                    mlflow.log_param("promotion_eligible", "YES")
                else:
                    print("⚠️  성능 임계값에 미달했습니다.")
                    mlflow.log_param("performance_check", "FAILED")
                    mlflow.log_param("promotion_eligible", "NO")
            else:
                print("   - 테스트 데이터가 부족하여 성능 평가를 건너뜁니다.")
                mlflow.log_param("performance_check", "SKIPPED")

        except Exception as e:
            print(f"⚠️  성능 임계값 확인 중 오류: {e}")

        # 미래 예측 결과 일부 로깅
        future_predictions = forecast.tail(forecast_days)[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]
        print(f"\n🔮 향후 {forecast_days}일 예측 (상위 5개):")
        print(future_predictions.head().to_string(index=False))

        # 예측 결과를 CSV로 저장하고 아티팩트로 로깅
        predictions_path = os.path.join(os.path.dirname(__file__), 'models', f'forecast_results_{keyword.replace(" ", "_")}.csv')
        future_predictions.to_csv(predictions_path, index=False, encoding='utf-8-sig')
        mlflow.log_artifact(predictions_path, "predictions")

        print(f"\n✨ MLflow 기반 수요 예측 모델 훈련이 성공적으로 완료되었습니다.")
        print(f"📈 MLflow UI에서 실험 결과를 확인하세요: http://localhost:5000")

if __name__ == "__main__":
    train_demand_forecasting_model()