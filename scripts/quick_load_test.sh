#!/bin/bash
# Quick Load Test Runner
# Market Insights Pro 빠른 부하 테스트 실행

echo "🚀 Market Insights Pro 빠른 부하 테스트"
echo "=================================="

# 서버 상태 확인
echo "📡 서버 상태 확인 중..."
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/database/health | grep -q "200"; then
    echo "✅ 서버 상태 정상"
else
    echo "❌ 서버가 실행되지 않았습니다. 먼저 서버를 시작하세요:"
    echo "   python main.py"
    exit 1
fi

# 결과 디렉토리 생성
mkdir -p load_test_results

echo ""
echo "📊 부하 테스트 시나리오 선택:"
echo "1) 가벼운 테스트 (10 사용자, 2분)"
echo "2) 중간 부하 테스트 (50 사용자, 5분)"
echo "3) 높은 부하 테스트 (100 사용자, 3분)"
echo "4) 급증 테스트 (200 사용자, 2분)"
echo "5) 사용자 정의"
echo "6) 전체 시나리오 자동 실행"

read -p "선택하세요 (1-6): " choice

case $choice in
    1)
        echo "🧪 가벼운 부하 테스트 실행 중..."
        locust -f scripts/load_testing.py \
               --host=http://localhost:8001 \
               --users=10 \
               --spawn-rate=2 \
               --run-time=120s \
               --headless \
               --csv=load_test_results/light_load \
               --html=load_test_results/light_load_report.html
        ;;
    2)
        echo "🧪 중간 부하 테스트 실행 중..."
        locust -f scripts/load_testing.py \
               --host=http://localhost:8001 \
               --users=50 \
               --spawn-rate=5 \
               --run-time=300s \
               --headless \
               --csv=load_test_results/moderate_load \
               --html=load_test_results/moderate_load_report.html
        ;;
    3)
        echo "🧪 높은 부하 테스트 실행 중..."
        locust -f scripts/load_testing.py \
               --host=http://localhost:8001 \
               --users=100 \
               --spawn-rate=10 \
               --run-time=180s \
               --headless \
               --csv=load_test_results/heavy_load \
               --html=load_test_results/heavy_load_report.html
        ;;
    4)
        echo "🧪 급증 테스트 실행 중..."
        locust -f scripts/load_testing.py \
               --host=http://localhost:8001 \
               --users=200 \
               --spawn-rate=50 \
               --run-time=120s \
               --headless \
               --csv=load_test_results/spike_test \
               --html=load_test_results/spike_test_report.html
        ;;
    5)
        read -p "사용자 수: " users
        read -p "증가율 (초당): " spawn_rate
        read -p "지속 시간 (초): " duration

        echo "🧪 사용자 정의 테스트 실행 중..."
        locust -f scripts/load_testing.py \
               --host=http://localhost:8001 \
               --users=$users \
               --spawn-rate=$spawn_rate \
               --run-time=${duration}s \
               --headless \
               --csv=load_test_results/custom_test \
               --html=load_test_results/custom_test_report.html
        ;;
    6)
        echo "🧪 전체 시나리오 자동 실행 중..."
        python scripts/run_load_tests.py
        ;;
    *)
        echo "❌ 잘못된 선택입니다."
        exit 1
        ;;
esac

echo ""
echo "✅ 부하 테스트 완료!"
echo "📊 결과 확인:"
echo "   - CSV 파일: load_test_results/"
echo "   - HTML 보고서: load_test_results/*.html"
echo ""

# 간단한 결과 요약 출력
if [ -f "load_test_results/load_test_summary.json" ]; then
    echo "📈 요약 보고서:"
    cat load_test_results/load_test_summary.json | python -m json.tool | head -20
fi

echo ""
echo "💡 추가 명령어:"
echo "   - 웹 UI로 테스트: locust -f scripts/load_testing.py --host=http://localhost:8001"
echo "   - 브라우저에서 http://localhost:8089 접속"