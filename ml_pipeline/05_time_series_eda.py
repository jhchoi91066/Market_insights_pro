
import pandas as pd
import matplotlib.pyplot as plt
import os
import sys
from statsmodels.tsa.seasonal import seasonal_decompose

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def perform_time_series_eda():
    """
    시계열 데이터 패턴 분석을 수행합니다.
    """
    print("🚀 시계열 데이터 패턴 분석 시작...")
    print("=" * 50)

    # 1. 데이터 로딩
    input_data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'naver_products_cleaned_for_ml.csv')
    
    try:
        df = pd.read_csv(input_data_path)
        print(f"✅ 데이터 로딩 완료: {len(df)}개 행")
    except FileNotFoundError:
        print(f"❌ 입력 데이터 파일({input_data_path})을 찾을 수 없습니다!")
        print("💡 먼저 ml_pipeline/04_data_preprocessing.py를 실행하여 데이터셋을 생성해주세요.")
        return

    # 2. 시간 데이터 준비
    print("🔄 시간 데이터 준비 중...")
    df['scraped_at'] = pd.to_datetime(df['scraped_at'])
    df.set_index('scraped_at', inplace=True)
    df.sort_index(inplace=True)
    print("✅ 'scraped_at' 컬럼을 Datetime 인덱스로 설정 완료")

    # 3. 시간별 집계 (일별 수집된 상품 수)
    print("📊 일별 상품 수 집계 중...")
    daily_counts = df.resample('D').size().fillna(0) # 일별로 집계하고, 데이터 없는 날은 0으로 채움
    print(f"✅ 일별 상품 수 집계 완료. 총 {len(daily_counts)}일 데이터.")

    # 4. 패턴 시각화
    print("📈 시계열 패턴 시각화 중...")
    plt.figure(figsize=(15, 6))
    plt.plot(daily_counts, marker='o', linestyle='-', markersize=4)
    plt.title('일별 상품 수집 트렌드')
    plt.xlabel('날짜')
    plt.ylabel('수집된 상품 수')
    plt.grid(True)
    plt.tight_layout()

    # 플롯 저장 디렉토리 생성
    plot_dir = os.path.join(os.path.dirname(__file__), 'plots')
    os.makedirs(plot_dir, exist_ok=True)
    plot_path = os.path.join(plot_dir, "time_series_eda_daily_counts.png")
    plt.savefig(plot_path)
    plt.close()
    print(f"✅ 일별 상품 수집 트렌드 그래프 저장 완료: {plot_path}")

    # 5. 시계열 분해 (선택 사항: 데이터에 명확한 계절성이 있다면)
    # Prophet 모델은 이미 계절성을 잘 처리하므로, 여기서는 간단한 시각화만.
    # 만약 데이터가 충분히 길고 명확한 주기를 가진다면 seasonal_decompose 사용 가능
    # 예: result = seasonal_decompose(daily_counts, model='additive', period=7) # 주간 계절성
    # result.plot()
    # plt.savefig(os.path.join(plot_dir, "time_series_eda_decomposition.png"))
    # plt.close()

    print("\n✨ 시계열 데이터 패턴 분석이 성공적으로 완료되었습니다.")

if __name__ == "__main__":
    perform_time_series_eda()
