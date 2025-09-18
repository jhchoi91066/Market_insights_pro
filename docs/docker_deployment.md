# Docker 배포 가이드

Market Insights Pro의 Docker 컨테이너화 및 배포 가이드입니다.

## 📋 목차

- [개요](#개요)
- [아키텍처](#아키텍처)
- [사전 요구사항](#사전-요구사항)
- [빠른 시작](#빠른-시작)
- [배포 옵션](#배포-옵션)
- [모니터링](#모니터링)
- [트러블슈팅](#트러블슈팅)

## 🎯 개요

Market Insights Pro는 마이크로서비스 아키텍처로 설계되어 다음과 같은 컨테이너들로 구성됩니다:

### 🏗️ 아키텍처

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Nginx         │    │   App Server 1  │    │   App Server 2  │
│   Load Balancer │───▶│   (FastAPI)     │    │   (FastAPI)     │
│   Port: 80      │    │   Port: 8001    │    │   Port: 8001    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐    ┌─────────────────┐
         │              │   App Server 3  │    │   Celery Worker │
         │              │   (FastAPI)     │    │   (High Prio)   │
         │              │   Port: 8001    │    │                 │
         │              └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
         ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
         │   Redis Cache   │    │   Apache Kafka  │    │   Prometheus    │
         │   Port: 6379    │    │   Port: 9092    │    │   Port: 9090    │
         └─────────────────┘    └─────────────────┘    └─────────────────┘
                                         │
                                ┌─────────────────┐    ┌─────────────────┐
                                │   Zookeeper     │    │   Grafana       │
                                │   Port: 2181    │    │   Port: 3000    │
                                └─────────────────┘    └─────────────────┘
```

### 🐳 컨테이너 구성

| 서비스 | 설명 | 포트 | 스케일링 |
|--------|------|------|----------|
| nginx | 로드밸런서 & 리버스 프록시 | 80, 443 | 1개 |
| app1,2,3 | FastAPI 애플리케이션 서버 | 8001 | 3개 |
| celery-worker-high | 고우선순위 작업 처리 | - | 1개 |
| celery-worker-normal | 일반 작업 처리 | - | 1개 |
| celery-worker-batch | 배치 작업 처리 | - | 1개 |
| celery-beat | 스케줄러 | - | 1개 |
| flower | Celery 모니터링 | 5555 | 1개 |
| redis | 캐시 & 메시지 브로커 | 6379 | 1개 |
| kafka | 이벤트 스트리밍 | 9092 | 1개 |
| zookeeper | Kafka 코디네이터 | 2181 | 1개 |

## 🔧 사전 요구사항

### 시스템 요구사항
- Docker 20.10+
- Docker Compose 2.0+
- 최소 8GB RAM
- 최소 20GB 디스크 공간

### 설치 확인
```bash
docker --version
docker-compose --version
docker info
```

## 🚀 빠른 시작

### 1. 저장소 클론
```bash
git clone <repository-url>
cd Market_insights
```

### 2. 환경 설정
```bash
# 환경 파일 복사 및 수정
cp .env.production.example .env.production
# .env.production 파일을 편집하여 환경에 맞게 설정
```

### 3. 배포 실행
```bash
# 전체 배포 (권장)
./scripts/deploy.sh full

# 또는 단계별 배포
./scripts/deploy.sh build   # 빌드만
./scripts/deploy.sh deploy  # 배포만
```

## 📦 배포 옵션

### 개발 환경 배포
```bash
# 개발 모드 (핫 리로드 포함)
docker-compose up -d

# 로그 확인
docker-compose logs -f app
```

### 프로덕션 환경 배포
```bash
# 프로덕션 배포
docker-compose -f docker-compose.prod.yml up -d

# 스케일링
docker-compose -f docker-compose.prod.yml up -d --scale app1=2 --scale app2=2
```

### 모니터링 스택 배포
```bash
# 모니터링 시스템 시작
./scripts/start_monitoring.sh

# 또는 수동 시작
docker-compose -f docker-compose.monitoring.yml up -d
```

## 🎛️ 환경 설정

### 개발 환경 (.env.development)
```bash
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
MAX_WORKERS=1
RATE_LIMIT_ENABLED=false
```

### 프로덕션 환경 (.env.production)
```bash
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
MAX_WORKERS=4
RATE_LIMIT_ENABLED=true
SECRET_KEY=your_production_secret_key
```

## 📊 모니터링

### 접속 URL
- **메인 애플리케이션**: http://localhost
- **헬스체크**: http://localhost/health
- **상세 헬스체크**: http://localhost/health/detailed
- **Prometheus 메트릭**: http://localhost/metrics
- **Flower (Celery)**: http://localhost:5555
- **Grafana**: http://localhost:3000 (admin/admin123)
- **Prometheus**: http://localhost:9090

### 헬스체크 상태
```bash
# 간단한 헬스체크
curl http://localhost/health

# 상세 헬스체크
curl http://localhost/health/detailed
```

### 로그 확인
```bash
# 모든 서비스 로그
docker-compose -f docker-compose.prod.yml logs -f

# 특정 서비스 로그
docker-compose -f docker-compose.prod.yml logs -f app1
docker-compose -f docker-compose.prod.yml logs -f nginx
docker-compose -f docker-compose.prod.yml logs -f celery-worker-high
```

## 🔧 유지보수

### 서비스 재시작
```bash
# 특정 서비스 재시작
docker-compose -f docker-compose.prod.yml restart app1

# 모든 서비스 재시작
docker-compose -f docker-compose.prod.yml restart
```

### 볼륨 백업
```bash
# 데이터 백업
docker run --rm -v market_insights_app1_data:/data -v $(pwd):/backup ubuntu tar czf /backup/app_data_backup.tar.gz /data

# Redis 데이터 백업
docker exec market_insights_redis redis-cli BGSAVE
```

### 로그 로테이션
```bash
# 로그 정리
docker-compose -f docker-compose.prod.yml exec nginx logrotate /etc/logrotate.d/nginx
```

## 🚨 트러블슈팅

### 일반적인 문제

#### 1. 컨테이너 시작 실패
```bash
# 컨테이너 상태 확인
docker-compose -f docker-compose.prod.yml ps

# 로그 확인
docker-compose -f docker-compose.prod.yml logs [service_name]

# 이미지 재빌드
docker-compose -f docker-compose.prod.yml build --no-cache
```

#### 2. 네트워크 연결 문제
```bash
# 네트워크 확인
docker network ls
docker network inspect market_insights_net

# 네트워크 재생성
docker network rm market_insights_net
docker-compose -f docker-compose.prod.yml up -d
```

#### 3. 포트 충돌
```bash
# 포트 사용 확인
sudo lsof -i :80
sudo lsof -i :6379

# 포트 변경 후 재시작
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d
```

#### 4. 디스크 공간 부족
```bash
# 사용하지 않는 컨테이너/이미지 정리
docker system prune -a

# 볼륨 정리
docker volume prune
```

### 성능 최적화

#### 1. 메모리 사용량 최적화
```bash
# 컨테이너별 메모리 사용량 확인
docker stats --no-stream

# 메모리 제한 설정 (docker-compose.yml)
services:
  app1:
    mem_limit: 512m
    memswap_limit: 512m
```

#### 2. CPU 사용량 최적화
```bash
# CPU 제한 설정
services:
  app1:
    cpus: '0.5'
    cpu_percent: 50
```

## 🔒 보안

### 컨테이너 보안
- 비루트 사용자로 실행
- 최소 권한 원칙 적용
- 보안 업데이트 정기 적용

### 네트워크 보안
- 내부 통신용 브리지 네트워크 사용
- 불필요한 포트 노출 방지
- SSL/TLS 인증서 적용 (프로덕션)

### 데이터 보안
- 볼륨 암호화
- 민감한 정보는 환경변수로 관리
- 정기적인 백업 수행

## 📈 스케일링

### 수평 스케일링
```bash
# 애플리케이션 서버 확장
docker-compose -f docker-compose.prod.yml up -d --scale app1=3 --scale app2=3

# Celery 워커 확장
docker-compose -f docker-compose.prod.yml up -d --scale celery-worker-high=2
```

### 수직 스케일링
```bash
# 리소스 할당 증가 (docker-compose.yml 수정)
services:
  app1:
    mem_limit: 1g
    cpus: '1.0'
```

## 🔄 업데이트

### 롤링 업데이트
```bash
# 단계별 업데이트
docker-compose -f docker-compose.prod.yml up -d --no-deps app1
docker-compose -f docker-compose.prod.yml up -d --no-deps app2
docker-compose -f docker-compose.prod.yml up -d --no-deps app3
```

### 블루-그린 배포
```bash
# 새 버전 배포
docker-compose -f docker-compose.prod.yml -p market_insights_green up -d

# 헬스체크 후 트래픽 전환
# Nginx 설정 업데이트 필요
```