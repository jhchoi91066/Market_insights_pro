#!/bin/bash
# Market Insights Pro 배포 스크립트
# Production deployment automation

set -e  # Exit on any error

echo "🚀 Market Insights Pro 배포 시작"
echo "=================================="

# 스크립트 디렉토리 설정
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}\")\" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "📁 프로젝트 루트: $PROJECT_ROOT"
cd "$PROJECT_ROOT"

# 환경 변수 확인
check_environment() {
    echo "🔍 환경 설정 확인 중..."

    if [ ! -f ".env.production" ]; then
        echo "❌ .env.production 파일이 없습니다."
        echo "   .env.production.example을 복사하여 환경 설정을 완료하세요."
        exit 1
    fi

    echo "✅ 환경 설정 파일 확인 완료"
}

# Docker 및 Docker Compose 확인
check_docker() {
    echo "🐳 Docker 환경 확인 중..."

    if ! command -v docker &> /dev/null; then
        echo "❌ Docker가 설치되지 않았습니다."
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null; then
        echo "❌ Docker Compose가 설치되지 않았습니다."
        exit 1
    fi

    if ! docker info > /dev/null 2>&1; then
        echo "❌ Docker가 실행되지 않고 있습니다."
        exit 1
    fi

    echo "✅ Docker 환경 확인 완료"
}

# 이전 배포 정리
cleanup_previous() {
    echo "🧹 이전 배포 정리 중..."

    # 기존 컨테이너 중지 및 제거
    docker-compose -f docker-compose.prod.yml down --remove-orphans 2>/dev/null || true

    # 사용하지 않는 이미지 정리
    docker image prune -f

    echo "✅ 이전 배포 정리 완료"
}

# 애플리케이션 빌드
build_application() {
    echo "🔨 애플리케이션 빌드 중..."

    # 필요한 디렉토리 생성
    mkdir -p logs/nginx
    mkdir -p data/{uploads,exports}
    mkdir -p ssl

    # Docker 이미지 빌드
    docker-compose -f docker-compose.prod.yml build --no-cache

    echo "✅ 애플리케이션 빌드 완료"
}

# 데이터베이스 초기화
init_database() {
    echo "🗄️ 데이터베이스 초기화 중..."

    # 데이터베이스 디렉토리 생성
    mkdir -p data/db

    # 임시 컨테이너로 데이터베이스 초기화 스크립트 실행
    if [ -f "scripts/init_db.py" ]; then
        docker run --rm \
            -v "$PROJECT_ROOT/data:/app/data" \
            -v "$PROJECT_ROOT:/app" \
            --env-file .env.production \
            market_insights_app:latest \
            python scripts/init_db.py
    fi

    echo "✅ 데이터베이스 초기화 완료"
}

# 서비스 시작
start_services() {
    echo "🚀 서비스 시작 중..."

    # Production 환경으로 서비스 시작
    docker-compose -f docker-compose.prod.yml up -d

    echo "⏳ 서비스 시작 대기 중..."
    sleep 30

    echo "✅ 서비스 시작 완료"
}

# 헬스체크
health_check() {
    echo "🏥 헬스체크 실행 중..."

    local max_attempts=10
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        echo "시도 $attempt/$max_attempts"

        # Nginx 헬스체크
        if curl -f http://localhost/health > /dev/null 2>&1; then
            echo "✅ 애플리케이션 헬스체크 성공"
            break
        fi

        if [ $attempt -eq $max_attempts ]; then
            echo "❌ 헬스체크 실패 - 배포를 롤백합니다."
            docker-compose -f docker-compose.prod.yml logs
            docker-compose -f docker-compose.prod.yml down
            exit 1
        fi

        sleep 10
        ((attempt++))
    done
}

# 서비스 상태 확인
check_services() {
    echo "📊 서비스 상태 확인 중..."

    # 컨테이너 상태 확인
    echo ""
    echo "컨테이너 상태:"
    docker-compose -f docker-compose.prod.yml ps

    echo ""
    echo "서비스 접속 정보:"
    echo "  🌐 메인 애플리케이션: http://localhost"
    echo "  🏥 헬스체크:         http://localhost/health"
    echo "  📊 상세 헬스체크:    http://localhost/health/detailed"
    echo "  📈 메트릭:           http://localhost/metrics"
    echo "  🌸 Flower (Celery):  http://localhost:5555"
    echo "  📊 Grafana:          http://localhost:3000"
    echo "  🔍 Prometheus:       http://localhost:9090"

    echo ""
    echo "로그 확인 명령어:"
    echo "  docker-compose -f docker-compose.prod.yml logs -f [service_name]"

    echo ""
    echo "서비스 중지 명령어:"
    echo "  docker-compose -f docker-compose.prod.yml down"
}

# 배포 옵션 처리
case "${1:-full}" in
    "build")
        check_environment
        check_docker
        build_application
        ;;
    "deploy")
        check_environment
        check_docker
        cleanup_previous
        start_services
        health_check
        check_services
        ;;
    "full")
        check_environment
        check_docker
        cleanup_previous
        build_application
        init_database
        start_services
        health_check
        check_services
        ;;
    "stop")
        echo "🛑 서비스 중지 중..."
        docker-compose -f docker-compose.prod.yml down
        echo "✅ 서비스 중지 완료"
        ;;
    "logs")
        docker-compose -f docker-compose.prod.yml logs -f "${2:-}"
        ;;
    "status")
        check_services
        ;;
    *)
        echo "사용법: $0 {full|build|deploy|stop|logs|status}"
        echo ""
        echo "옵션:"
        echo "  full    - 전체 배포 (빌드 + 데이터베이스 초기화 + 배포)"
        echo "  build   - 애플리케이션 빌드만"
        echo "  deploy  - 빌드된 이미지로 배포만"
        echo "  stop    - 서비스 중지"
        echo "  logs    - 로그 확인 (서비스명 추가 가능)"
        echo "  status  - 서비스 상태 확인"
        exit 1
        ;;
esac

echo ""
echo "🎉 배포 작업 완료!"