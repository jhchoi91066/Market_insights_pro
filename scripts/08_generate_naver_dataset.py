
import asyncio
import os
import pandas as pd
import sys
from dotenv import load_dotenv

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.naver_market_analyzer import NaverMarketAnalyzer

# .env 파일 로드
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env.development'))

async def main():
    """
    ML 모델 학습을 위한 데이터셋을 생성하는 메인 함수
    """
    print("🚀 ML 데이터셋 생성을 시작합니다...")

    # 분석할 키워드 목록
    keywords_to_analyze = [
        '키보드',
        '블루투스 이어폰',
        '모니터',
        '물통',
        '캠핑 의자',
        '마우스',
        '커피 원두'
    ]

    # 데이터셋을 저장할 경로
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    output_path = os.path.join(output_dir, "naver_products_for_ml.csv")

    # 출력 디렉토리 생성
    os.makedirs(output_dir, exist_ok=True)

    all_products = []
    try:
        analyzer = NaverMarketAnalyzer()
    except ValueError as e:
        print(f"❌ NaverMarketAnalyzer 초기화 실패: {e}")
        print("💡 .env 파일에 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET이 올바르게 설정되었는지 확인해주세요.")
        return

    for keyword in keywords_to_analyze:
        print(f"\n🔍 키워드 '{keyword}'에 대한 데이터 수집 중... (최대 100개)")
        try:
            # 트렌드 강화 분석을 사용하되, 제품 목록만 추출
            analysis_result = analyzer.analyze_market_competition(keyword, product_count=100)
            
            if 'products' in analysis_result and analysis_result['products']:
                products = analysis_result['products']
                print(f"✅ {len(products)}개의 상품 데이터를 수집했습니다.")
                # 각 상품에 키워드 정보 추가
                for p in products:
                    p['search_keyword'] = keyword
                all_products.extend(products)
            else:
                print(f"⚠️ 키워드 '{keyword}'에 대한 상품을 찾지 못했거나 오류가 발생했습니다.")

        except Exception as e:
            print(f"❌ 키워드 '{keyword}' 처리 중 예외 발생: {e}")

    if not all_products:
        print("\n❌ 수집된 상품 데이터가 전혀 없습니다. 스크립트를 종료합니다.")
        return

    # Pandas DataFrame으로 변환
    print("\n🔄 수집된 모든 데이터를 DataFrame으로 변환 중...")
    df = pd.DataFrame(all_products)

    # 중복 데이터 제거 (product_id 기준)
    initial_count = len(df)
    df.drop_duplicates(subset=['product_id'], keep='first', inplace=True)
    final_count = len(df)
    print(f"🗑️ 중복 제거 완료: {initial_count}개 -> {final_count}개 ({initial_count - final_count}개 제거)")

    # CSV 파일로 저장
    print(f"\n💾 최종 데이터셋을 '{output_path}' 파일로 저장 중...")
    try:
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"\n✨ 성공! 총 {final_count}개의 상품 데이터가 포함된 ML 데이터셋 생성이 완료되었습니다.")
    except Exception as e:
        print(f"❌ 파일 저장 중 오류 발생: {e}")

if __name__ == "__main__":
    # asyncio.run()은 Python 3.7+ 에서 사용 가능
    # 현재 환경의 이벤트 루프 정책에 따라 asyncio.run() 대신 아래와 같이 사용할 수 있습니다.
    # loop = asyncio.get_event_loop()
    # loop.run_until_complete(main())
    asyncio.run(main())
