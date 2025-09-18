#!/bin/bash
# Market Insights Pro 모니터링 스택 시작 스크립트
# Prometheus + Grafana + AlertManager

echo "🚀 Market Insights Pro 모니터링 스택 시작"
echo "==========================================="

# 현재 디렉토리 확인
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "📁 프로젝트 루트: $PROJECT_ROOT"

# 모니터링 디렉토리 존재 확인
if [ ! -d "$PROJECT_ROOT/monitoring" ]; then
    echo "❌ monitoring 디렉토리가 없습니다."
    echo "   필요한 설정 파일들을 먼저 생성하세요."
    exit 1
fi

# Docker 실행 확인
if ! docker --version > /dev/null 2>&1; then
    echo "❌ Docker가 설치되지 않았거나 실행되지 않습니다."
    exit 1
fi

echo "✅ Docker 사용 가능"

# 기존 모니터링 컨테이너 정리
echo "🧹 기존 모니터링 컨테이너 정리 중..."
cd "$PROJECT_ROOT"

docker-compose -f docker-compose.monitoring.yml down 2>/dev/null || true

# 이전 네트워크 정리
docker network rm market_insights_monitoring 2>/dev/null || true

echo "📊 모니터링 스택 시작 중..."

# 모니터링 스택 시작
docker-compose -f docker-compose.monitoring.yml up -d

# 컨테이너 상태 확인
echo ""
echo "⏳ 컨테이너 시작 대기 중..."
sleep 10

echo ""
echo "📋 컨테이너 상태 확인:"
docker-compose -f docker-compose.monitoring.yml ps

# 헬스체크
echo ""
echo "🏥 서비스 헬스체크:"

# Prometheus 체크
echo -n "Prometheus (9090): "
if curl -s -o /dev/null -w "%{http_code}" http://localhost:9090/-/healthy | grep -q "200"; then
    echo "✅ 정상"
else
    echo "❌ 응답 없음"
fi

# Grafana 체크
echo -n "Grafana (3000): "
if curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/api/health | grep -q "200"; then
    echo "✅ 정상"
else
    echo "❌ 응답 없음"
fi

# AlertManager 체크
echo -n "AlertManager (9093): "
if curl -s -o /dev/null -w "%{http_code}" http://localhost:9093/-/healthy | grep -q "200"; then
    echo "✅ 정상"
else
    echo "❌ 응답 없음"
fi

# Node Exporter 체크
echo -n "Node Exporter (9100): "
if curl -s -o /dev/null -w "%{http_code}" http://localhost:9100/metrics | grep -q "200"; then
    echo "✅ 정상"
else
    echo "❌ 응답 없음"
fi

echo ""
echo "🎉 모니터링 스택 시작 완료!"
echo ""
echo "📱 접속 정보:"
echo "  🔍 Prometheus:   http://localhost:9090"
echo "  📊 Grafana:      http://localhost:3000 (admin/admin123)"
echo "  🚨 AlertManager: http://localhost:9093"
echo "  💻 Node Exporter: http://localhost:9100"
echo "  📦 cAdvisor:     http://localhost:8080"
echo ""
echo "📈 Market Insights Pro 메트릭:"
echo "  http://localhost:8001/metrics"
echo ""
echo "💡 유용한 명령어:"
echo "  - 로그 확인: docker-compose -f docker-compose.monitoring.yml logs -f"
echo "  - 재시작: docker-compose -f docker-compose.monitoring.yml restart"
echo "  - 중지: docker-compose -f docker-compose.monitoring.yml down"
echo ""

# Grafana 대시보드 자동 import (선택사항)
read -p "🎨 Grafana 대시보드를 자동으로 import 하시겠습니까? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "📊 대시보드 import 시작..."
    # 여기에 대시보드 import 로직 추가 가능
    echo "💡 수동으로 http://localhost:3000에서 대시보드를 설정하세요."
fi

echo "✅ 모니터링 시스템 준비 완료!"