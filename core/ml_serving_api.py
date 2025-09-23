# -*- coding: utf-8 -*-
"""
ML 모델 서빙 API
Market Insights Pro의 실시간 ML 예측 서비스를 제공합니다.
"""

import os
import sys
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
import pandas as pd
import numpy as np
from pydantic import BaseModel, Field
import mlflow
import mlflow.sklearn
import mlflow.xgboost

# MLflow 관련
from core.mlflow_manager import get_mlflow_manager
from core.cache import get_cache_manager

logger = logging.getLogger(__name__)


# ===== 요청/응답 모델 정의 =====

class PricePredictionRequest(BaseModel):
    """가격 예측 요청 모델"""
    category: str = Field(..., description="상품 카테고리")
    brand: str = Field(default="Unknown", description="브랜드명")
    seller: str = Field(default="Unknown", description="판매자")
    search_keyword: str = Field(..., description="검색 키워드")
    maker: str = Field(default="Unknown", description="제조사")
    rating: float = Field(default=4.0, ge=0.0, le=5.0, description="평점")
    review_count: int = Field(default=100, ge=0, description="리뷰 수")
    # 추가 특성들
    price_to_category_avg_ratio: float = Field(default=1.0, description="카테고리 평균 대비 가격 비율")
    price_to_keyword_avg_ratio: float = Field(default=1.0, description="키워드 평균 대비 가격 비율")
    rating_x_review_count: float = Field(default=400.0, description="평점 x 리뷰수")


class PricePredictionResponse(BaseModel):
    """가격 예측 응답 모델"""
    predicted_price: float = Field(..., description="예측된 가격 (USD)")
    confidence_interval: Dict[str, float] = Field(..., description="신뢰구간")
    model_version: str = Field(..., description="사용된 모델 버전")
    prediction_timestamp: datetime = Field(..., description="예측 시간")
    processing_time_ms: float = Field(..., description="처리 시간 (밀리초)")


class BatchPredictionRequest(BaseModel):
    """배치 예측 요청 모델"""
    products: List[PricePredictionRequest] = Field(..., description="예측할 상품 목록")
    use_cache: bool = Field(default=True, description="캐시 사용 여부")


class BatchPredictionResponse(BaseModel):
    """배치 예측 응답 모델"""
    predictions: List[PricePredictionResponse] = Field(..., description="예측 결과 목록")
    total_processed: int = Field(..., description="처리된 상품 수")
    cache_hits: int = Field(..., description="캐시 히트 수")
    processing_time_ms: float = Field(..., description="전체 처리 시간")


class ModelInfo(BaseModel):
    """모델 정보 응답 모델"""
    model_name: str = Field(..., description="모델 이름")
    model_version: str = Field(..., description="모델 버전")
    model_stage: str = Field(..., description="모델 스테이지")
    last_updated: datetime = Field(..., description="마지막 업데이트 시간")
    performance_metrics: Dict[str, float] = Field(..., description="성능 메트릭")


# ===== ML 서빙 서비스 클래스 =====

class MLServingService:
    """
    ML 모델 서빙 서비스
    실시간 예측, 배치 예측, 모델 관리 기능을 제공합니다.
    """

    def __init__(self):
        """서빙 서비스 초기화"""
        self.mlflow_manager = get_mlflow_manager()
        self.cache_manager = get_cache_manager()
        self.models = {}  # 로드된 모델 캐시
        self.model_info = {}  # 모델 정보 캐시
        self._load_production_models()

    def _load_production_models(self):
        """프로덕션 모델들을 메모리에 로드"""
        try:
            # 가격 예측 모델 로드
            price_model = self._load_model("price_predictor", stage="Production")
            if price_model:
                self.models["price_predictor"] = price_model
                logger.info("✅ 가격 예측 모델 로드 완료")
            else:
                # 프로덕션 모델이 없으면 최신 모델 로드
                price_model = self._load_model("price_predictor", version="latest")
                if price_model:
                    self.models["price_predictor"] = price_model
                    logger.info("✅ 가격 예측 모델 (최신 버전) 로드 완료")

            # 수요 예측 모델 로드 (시계열 예측)
            demand_model = self._load_model("demand_forecaster", stage="Production")
            if demand_model:
                self.models["demand_forecaster"] = demand_model
                logger.info("✅ 수요 예측 모델 로드 완료")

        except Exception as e:
            logger.error(f"❌ 프로덕션 모델 로드 실패: {e}")

    def _load_model(self, model_name: str, stage: str = None, version: str = None):
        """MLflow에서 모델 로드"""
        try:
            model = self.mlflow_manager.load_model(model_name, version=version, stage=stage)

            # 모델 정보 수집
            client = self.mlflow_manager.client
            if stage:
                model_versions = client.get_latest_versions(model_name, stages=[stage])
            else:
                model_versions = client.get_latest_versions(model_name, stages=["None"])

            if model_versions:
                model_version = model_versions[0]
                self.model_info[model_name] = {
                    "version": model_version.version,
                    "stage": model_version.current_stage,
                    "last_updated": datetime.fromtimestamp(model_version.last_updated_timestamp / 1000)
                }

            return model

        except Exception as e:
            logger.error(f"❌ 모델 로드 실패 ({model_name}): {e}")
            return None

    async def predict_price(self, request: PricePredictionRequest) -> PricePredictionResponse:
        """단일 상품 가격 예측"""
        start_time = datetime.now()

        # 캐시 키 생성
        cache_key = f"price_prediction:{hash(str(request.dict()))}"

        # 캐시 확인
        cached_result = await self.cache_manager.get(cache_key)
        if cached_result:
            logger.info("📋 캐시에서 예측 결과 반환")
            return PricePredictionResponse.parse_obj(cached_result)

        # 모델 확인
        model = self.models.get("price_predictor")
        if not model:
            raise ValueError("가격 예측 모델이 로드되지 않았습니다.")

        try:
            # 입력 데이터 전처리
            input_data = self._prepare_price_prediction_input(request)

            # 예측 수행
            predicted_price = model.predict(input_data)[0]

            # 신뢰구간 계산 (간단한 추정)
            confidence_interval = {
                "lower": max(0, predicted_price * 0.85),  # 15% 하한
                "upper": predicted_price * 1.15  # 15% 상한
            }

            # 응답 생성
            processing_time = (datetime.now() - start_time).total_seconds() * 1000

            response = PricePredictionResponse(
                predicted_price=round(predicted_price, 2),
                confidence_interval=confidence_interval,
                model_version=self.model_info.get("price_predictor", {}).get("version", "unknown"),
                prediction_timestamp=datetime.now(),
                processing_time_ms=round(processing_time, 2)
            )

            # 캐시 저장 (1시간)
            await self.cache_manager.set(cache_key, response.dict(), ttl=3600)

            logger.info(f"💰 가격 예측 완료: ${predicted_price:.2f}")
            return response

        except Exception as e:
            logger.error(f"❌ 가격 예측 실패: {e}")
            raise

    def _prepare_price_prediction_input(self, request: PricePredictionRequest) -> pd.DataFrame:
        """가격 예측을 위한 입력 데이터 전처리 (최적화된 버전)"""
        # 성능 최적화: 사전 계산된 값들 사용
        rating_x_review = request.rating * request.review_count
        estimated_base_price = request.price_to_category_avg_ratio * 50  # 추정 기준 가격

        # 최적화: 딕셔너리 대신 리스트로 데이터 구성 (메모리 효율성)
        numeric_data = [
            request.rating,
            request.review_count,
            request.price_to_category_avg_ratio,
            request.price_to_keyword_avg_ratio,
            rating_x_review,
            request.rating * estimated_base_price,
            request.review_count * estimated_base_price
        ]

        # 범주형 변수 원-핫 인코딩 (캐시된 매핑 사용)
        categorical_encodings = self._get_cached_categorical_encoding(
            request.category, request.brand, request.seller,
            request.search_keyword, request.maker
        )

        # 최적화: DataFrame 생성 최소화
        all_features = numeric_data + categorical_encodings

        # 컬럼명은 캐시된 순서 사용
        return pd.DataFrame([all_features], columns=self._get_feature_names())

    def _get_cached_categorical_encoding(self, category: str, brand: str, seller: str,
                                       search_keyword: str, maker: str) -> List[int]:
        """캐시된 범주형 인코딩 (성능 최적화)"""
        # 실제 구현에서는 이 값들을 캐시해야 함
        encoding = []

        features = ['category', 'brand', 'seller', 'search_keyword', 'maker']
        values = [category, brand, seller, search_keyword, maker]

        for feature, value in zip(features, values):
            possible_values = self._get_possible_values(feature)
            for possible_value in possible_values:
                encoding.append(1 if possible_value == value else 0)

        return encoding

    def _get_feature_names(self) -> List[str]:
        """특성 이름 목록 반환 (캐시된 순서)"""
        # 성능 최적화: 특성 이름을 캐시해서 재사용
        if not hasattr(self, '_cached_feature_names'):
            numeric_features = [
                'rating', 'review_count', 'price_to_category_avg_ratio',
                'price_to_keyword_avg_ratio', 'rating_x_review_count',
                'price_x_rating', 'price_x_review_count'
            ]

            categorical_features = []
            for feature in ['category', 'brand', 'seller', 'search_keyword', 'maker']:
                for possible_value in self._get_possible_values(feature):
                    categorical_features.append(f"{feature}_{possible_value}")

            self._cached_feature_names = numeric_features + categorical_features

        return self._cached_feature_names

    def _get_possible_values(self, feature: str) -> List[str]:
        """각 범주형 특성의 가능한 값들 반환 (실제로는 훈련 데이터에서 추출)"""
        # 실제 구현에서는 훈련 시 사용된 값들을 저장해두어야 함
        defaults = {
            'category': ['컴퓨터/IT', '가전디지털', '스포츠/레저', '홈/인테리어'],
            'brand': ['Unknown', 'Samsung', 'LG', 'Apple'],
            'seller': ['Unknown', 'Naver', 'Coupang', '11번가'],
            'search_keyword': ['무선마우스', '블루투스헤드폰', '모니터'],
            'maker': ['Unknown', 'Samsung', 'LG']
        }
        return defaults.get(feature, ['Unknown'])

    async def predict_batch(self, request: BatchPredictionRequest) -> BatchPredictionResponse:
        """배치 가격 예측 (최적화된 버전)"""
        start_time = datetime.now()
        predictions = []
        cache_hits = 0

        # 성능 최적화: 캐시 히트 확인을 먼저 일괄 처리
        cache_results = {}
        if request.use_cache:
            cache_keys = []
            for product_request in request.products:
                cache_key = f"price_prediction:{hash(str(product_request.dict()))}"
                cache_keys.append((cache_key, product_request))

            # 캐시에서 일괄 조회 (존재하는 경우)
            for cache_key, product_request in cache_keys:
                cached_result = await self.cache_manager.get(cache_key)
                if cached_result:
                    cache_results[id(product_request)] = PricePredictionResponse.parse_obj(cached_result)

        # 캐시되지 않은 요청들만 모델 예측 수행
        uncached_requests = []
        for product_request in request.products:
            if id(product_request) in cache_results:
                predictions.append(cache_results[id(product_request)])
                cache_hits += 1
            else:
                uncached_requests.append(product_request)

        # 배치 모델 예측 (최적화: 한 번에 여러 개 처리)
        if uncached_requests:
            try:
                batch_predictions = await self._predict_batch_optimized(uncached_requests)
                predictions.extend(batch_predictions)
            except Exception as e:
                logger.error(f"❌ 배치 예측 실패: {e}")
                # 개별 예측으로 폴백
                for product_request in uncached_requests:
                    try:
                        prediction = await self.predict_price(product_request)
                        predictions.append(prediction)
                    except Exception as inner_e:
                        logger.error(f"❌ 개별 예측 실패: {inner_e}")

        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        return BatchPredictionResponse(
            predictions=predictions,
            total_processed=len(predictions),
            cache_hits=cache_hits,
            processing_time_ms=round(processing_time, 2)
        )

    async def _predict_batch_optimized(self, requests: List[PricePredictionRequest]) -> List[PricePredictionResponse]:
        """최적화된 배치 예측"""
        if not requests:
            return []

        model = self.models.get("price_predictor")
        if not model:
            raise ValueError("가격 예측 모델이 로드되지 않았습니다.")

        start_time = datetime.now()

        # 모든 요청을 한 번에 전처리
        batch_data = []
        for request in requests:
            input_data = self._prepare_price_prediction_input(request)
            batch_data.append(input_data.iloc[0].values)  # numpy array로 변환

        # 배치 예측 수행
        batch_input = pd.DataFrame(batch_data, columns=self._get_feature_names())
        batch_predictions = model.predict(batch_input)

        # 응답 생성
        responses = []
        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        for i, (request, predicted_price) in enumerate(zip(requests, batch_predictions)):
            confidence_interval = {
                "lower": max(0, predicted_price * 0.85),
                "upper": predicted_price * 1.15
            }

            response = PricePredictionResponse(
                predicted_price=round(predicted_price, 2),
                confidence_interval=confidence_interval,
                model_version=self.model_info.get("price_predictor", {}).get("version", "unknown"),
                prediction_timestamp=datetime.now(),
                processing_time_ms=round(processing_time / len(requests), 2)  # 평균 처리 시간
            )

            responses.append(response)

            # 개별 결과 캐시 저장
            cache_key = f"price_prediction:{hash(str(request.dict()))}"
            await self.cache_manager.set(cache_key, response.dict(), ttl=3600)

        return responses

    async def get_model_info(self, model_name: str) -> ModelInfo:
        """모델 정보 조회"""
        try:
            model_info = self.model_info.get(model_name)
            if not model_info:
                raise ValueError(f"모델 정보를 찾을 수 없습니다: {model_name}")

            # 성능 메트릭 조회
            performance_history = self.mlflow_manager.get_model_performance_history(model_name)
            metrics = {}
            if not performance_history.empty:
                latest_run = performance_history.iloc[0]
                for col in performance_history.columns:
                    if col.startswith("metrics."):
                        metric_name = col.replace("metrics.", "")
                        metrics[metric_name] = latest_run[col]

            return ModelInfo(
                model_name=model_name,
                model_version=model_info["version"],
                model_stage=model_info["stage"],
                last_updated=model_info["last_updated"],
                performance_metrics=metrics
            )

        except Exception as e:
            logger.error(f"❌ 모델 정보 조회 실패: {e}")
            raise

    async def reload_models(self):
        """모델 재로드"""
        logger.info("🔄 모델 재로드 시작...")
        self.models.clear()
        self.model_info.clear()
        self._load_production_models()
        logger.info("✅ 모델 재로드 완료")

    async def health_check(self) -> Dict[str, Any]:
        """서빙 서비스 헬스 체크"""
        try:
            health_status = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "loaded_models": list(self.models.keys()),
                "model_count": len(self.models),
                "mlflow_connection": "ok",
                "cache_connection": "ok"
            }

            # 간단한 예측 테스트
            if "price_predictor" in self.models:
                test_request = PricePredictionRequest(
                    category="컴퓨터/IT",
                    search_keyword="무선마우스"
                )
                test_prediction = await self.predict_price(test_request)
                health_status["test_prediction"] = test_prediction.predicted_price

            return health_status

        except Exception as e:
            logger.error(f"❌ 헬스 체크 실패: {e}")
            return {
                "status": "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }


# 전역 서빙 서비스 인스턴스
_serving_service = None

def get_ml_serving_service() -> MLServingService:
    """
    ML 서빙 서비스 싱글톤 인스턴스 반환
    """
    global _serving_service
    if _serving_service is None:
        _serving_service = MLServingService()
    return _serving_service


if __name__ == "__main__":
    # 테스트 실행
    async def test_serving():
        service = MLServingService()

        # 헬스 체크
        health = await service.health_check()
        print(f"헬스 체크: {health}")

        # 가격 예측 테스트
        test_request = PricePredictionRequest(
            category="컴퓨터/IT",
            brand="Logitech",
            search_keyword="무선마우스",
            rating=4.5,
            review_count=200
        )

        prediction = await service.predict_price(test_request)
        print(f"예측 결과: ${prediction.predicted_price}")

    asyncio.run(test_serving())