# Multi-stage Dockerfile for Market Insights Pro
# Stage 1: Build dependencies and setup
FROM python:3.11-slim as builder

# 시스템 패키지 업데이트 및 필수 도구 설치
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# Python 의존성 설치를 위한 requirements.txt 복사
COPY requirements.txt .

# 가상환경 생성 및 의존성 설치
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Production runtime
FROM python:3.11-slim as production

# 시스템 패키지 업데이트 및 런타임 도구만 설치
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# 비루트 사용자 생성 (보안)
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 빌드 스테이지에서 가상환경 복사
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 애플리케이션 소스 복사
COPY . .

# 로그 및 데이터 디렉토리 생성
RUN mkdir -p /app/logs /app/data && \
    chown -R appuser:appuser /app

# 사용자 전환
USER appuser

# 환경 변수 설정
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 헬스체크 추가
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# 포트 노출
EXPOSE 8001

# 기본 명령어 (FastAPI 서버 시작)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "4"]

# Stage 3: Development version
FROM production as development

# 개발용 추가 도구 설치
RUN pip install --no-cache-dir pytest pytest-asyncio black flake8 mypy

# 개발 모드 환경 변수
ENV ENVIRONMENT=development
ENV DEBUG=true

# 개발 서버 명령어 (핫 리로드 포함)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]

# Stage 4: Celery worker
FROM production as celery-worker

# Celery worker 시작 명령어
CMD ["celery", "-A", "core.celery_app", "worker", "--loglevel=info", "--concurrency=4"]

# Stage 5: Celery beat (스케줄러)
FROM production as celery-beat

# Celery beat 시작 명령어
CMD ["celery", "-A", "core.celery_app", "beat", "--loglevel=info"]

# Stage 6: Flower (Celery 모니터링)
FROM production as flower

# Flower 포트 노출
EXPOSE 5555

# Flower 시작 명령어
CMD ["celery", "-A", "core.celery_app", "flower", "--port=5555"]