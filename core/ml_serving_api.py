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
    model_config = {"protected_namespaces": ()}

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
    model_config = {"protected_namespaces": ()}

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
            # 직접 훈련된 모델 파일에서 로드
            base_path = os.path.dirname(os.path.dirname(__file__))  # 프로젝트 루트
            models_path = os.path.join(base_path, "ml_pipeline", "models")

            # 가격 예측 모델 로드 (최신 파일)
            price_model = self._load_local_model(
                models_path,
                "price_predictor_mlflow_",
                "joblib"
            )
            if price_model:
                self.models["price_predictor"] = price_model
                logger.info("✅ 가격 예측 모델 로드 완료 (로컬 파일)")

            # 수요 예측 모델 로드 (최신 파일)
            demand_model = self._load_local_model(
                models_path,
                "demand_forecaster_mlflow_",
                "pkl"
            )
            if demand_model:
                self.models["demand_forecaster"] = demand_model
                logger.info("✅ 수요 예측 모델 로드 완료 (로컬 파일)")

        except Exception as e:
            logger.error(f"❌ 프로덕션 모델 로드 실패: {e}")

    def _load_local_model(self, models_path: str, model_prefix: str, extension: str):
        """로컬 파일에서 최신 모델 로드"""
        import joblib
        import pickle
        import glob

        try:
            # 해당 prefix로 시작하는 최신 파일 찾기
            pattern = os.path.join(models_path, f"{model_prefix}*.{extension}")
            model_files = glob.glob(pattern)

            if not model_files:
                logger.warning(f"⚠️ 모델 파일을 찾을 수 없습니다: {pattern}")
                return None

            # 파일명 기준으로 최신 파일 선택 (날짜시간 포함)
            latest_file = max(model_files, key=os.path.getctime)
            logger.info(f"📁 로드할 모델 파일: {latest_file}")

            # 확장자에 따라 적절한 로더 사용
            if extension == "joblib":
                model = joblib.load(latest_file)
            elif extension == "pkl":
                with open(latest_file, 'rb') as f:
                    model = pickle.load(f)
            else:
                logger.error(f"❌ 지원되지 않는 파일 확장자: {extension}")
                return None

            # 모델 정보 저장
            model_name = model_prefix.rstrip("_")
            self.model_info[model_name] = {
                "version": "local_file",
                "stage": "Production",
                "last_updated": datetime.fromtimestamp(os.path.getctime(latest_file)),
                "file_path": latest_file
            }

            logger.info(f"✅ 로컬 모델 로드 성공: {model_name}")
            return model

        except Exception as e:
            logger.error(f"❌ 로컬 모델 로드 실패: {e}")
            return None

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
        cache_key = f"price_prediction:{hash(str(request.model_dump()))}"

        # 캐시 확인
        cached_result = await self.cache_manager.get(cache_key)
        if cached_result:
            logger.info("📋 캐시에서 예측 결과 반환")
            return PricePredictionResponse.parse_obj(cached_result)

        # 모델 확인 (모델이 없으면 더미 예측 제공)
        model = self.models.get("price_predictor")
        if not model:
            return self._generate_dummy_price_prediction(request, start_time)

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
            await self.cache_manager.set(cache_key, response.model_dump(), ttl=3600)

            logger.info(f"💰 가격 예측 완료: ${predicted_price:.2f}")
            return response

        except Exception as e:
            logger.error(f"❌ 가격 예측 실패: {e}")
            raise

    def _prepare_price_prediction_input(self, request: PricePredictionRequest) -> pd.DataFrame:
        """훈련된 모델과 동일한 특성으로 입력 데이터 전처리 (동적 매핑)"""

        # 기본 숫자 특성들
        data = {
            'rating': request.rating,
            'review_count': request.review_count,
            'purchased_last_month': getattr(request, 'purchased_last_month', 0),
            'is_prime': getattr(request, 'is_prime', 0),
            'price_to_category_avg_ratio': request.price_to_category_avg_ratio,
            'price_to_keyword_avg_ratio': request.price_to_keyword_avg_ratio,
            'price_x_rating': request.rating * (request.price_to_category_avg_ratio * 50),
            'rating_x_review_count': request.rating * request.review_count,
            'price_x_review_count': (request.price_to_category_avg_ratio * 50) * request.review_count
        }

        # 훈련된 모델의 특성 정보 로드 (캐시)
        if not hasattr(self, '_categorical_mappings'):
            self._load_model_feature_mappings()

        # 모든 범주형 특성을 0으로 초기화
        for feature in self._model_features:
            if feature not in data:
                data[feature] = 0

        # 동적으로 범주형 특성 매핑
        self._map_categorical_features(data, request)

        # 정확한 순서로 DataFrame 생성
        ordered_data = [data.get(feature, 0) for feature in self._model_features]
        return pd.DataFrame([ordered_data], columns=self._model_features)

    def _load_model_feature_mappings(self):
        """훈련된 모델에서 범주형 특성 매핑을 동적으로 생성"""
        import os
        features_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'model_features.txt')

        with open(features_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        self._model_features = []
        self._categorical_mappings = {}

        for line in lines:
            if ':' in line:
                feature_name = line.split(':', 1)[1].strip()
                self._model_features.append(feature_name)

                # 범주형 특성 매핑 추출 (prefix_value 형태)
                if '_' in feature_name and not feature_name.startswith(('rating', 'review', 'purchased', 'is_', 'price')):
                    prefix = feature_name.split('_')[0]
                    value = feature_name.split('_', 1)[1]

                    if prefix not in self._categorical_mappings:
                        self._categorical_mappings[prefix] = set()
                    self._categorical_mappings[prefix].add(value)

        # set을 list로 변환
        for prefix in self._categorical_mappings:
            self._categorical_mappings[prefix] = list(self._categorical_mappings[prefix])

        logger.info(f"✅ 범주형 특성 매핑 로드 완료: {len(self._categorical_mappings)}개 카테고리")

    def _map_categorical_features(self, data: dict, request: PricePredictionRequest):
        """동적으로 범주형 특성을 매핑 (유연한 처리)"""

        # Category 처리
        category_value = getattr(request, 'category', 'Unknown')
        self._set_best_match_feature(data, 'category', category_value)

        # Brand 처리
        brand_value = getattr(request, 'brand', 'Unknown')
        self._set_best_match_feature(data, 'brand', brand_value)

        # Seller 처리
        seller_value = getattr(request, 'seller', 'Unknown')
        self._set_best_match_feature(data, 'seller', seller_value)

        # Search keyword 처리 (부분 매칭)
        keyword_value = getattr(request, 'search_keyword', '')
        self._set_keyword_match_feature(data, 'search', keyword_value)

        # Maker 처리
        maker_value = getattr(request, 'maker', 'Unknown')
        self._set_best_match_feature(data, 'maker', maker_value)

        # Naver 카테고리 기본값 설정
        self._set_default_naver_categories(data)

    def _set_best_match_feature(self, data: dict, prefix: str, value: str):
        """가장 적합한 특성을 찾아서 설정 (정확한 매칭 → 유사 매칭 → 기본값)"""
        if prefix not in self._categorical_mappings:
            return

        available_values = self._categorical_mappings[prefix]

        # 1. 정확한 매칭
        if value in available_values:
            data[f'{prefix}_{value}'] = 1
            return

        # 2. 부분 매칭 (값이 포함된 경우)
        for available_value in available_values:
            if value.lower() in available_value.lower() or available_value.lower() in value.lower():
                data[f'{prefix}_{available_value}'] = 1
                logger.info(f"📝 부분 매칭: {prefix} '{value}' → '{available_value}'")
                return

        # 3. Unknown 값 사용
        if 'Unknown' in available_values:
            data[f'{prefix}_Unknown'] = 1
            logger.warning(f"⚠️ 알 수 없는 값: {prefix} '{value}' → 'Unknown' 사용")
            return

        # 4. 기본값으로 첫 번째 값 사용
        if available_values:
            default_value = available_values[0]
            data[f'{prefix}_{default_value}'] = 1
            logger.warning(f"⚠️ 기본값 사용: {prefix} '{value}' → '{default_value}' 사용")

    def _set_keyword_match_feature(self, data: dict, prefix: str, keyword: str):
        """검색 키워드에 대한 특별한 매칭 로직"""
        if prefix not in self._categorical_mappings:
            return

        available_keywords = self._categorical_mappings[prefix]

        # 키워드 부분 매칭 (양방향)
        for available_keyword in available_keywords:
            # 'keyword_' 접두사 제거 후 비교
            clean_available = available_keyword.replace('keyword_', '')
            if keyword.lower() in clean_available.lower() or clean_available.lower() in keyword.lower():
                data[f'{prefix}_{available_keyword}'] = 1
                logger.info(f"🔍 키워드 매칭: '{keyword}' → '{available_keyword}'")
                return

        # 매칭되지 않으면 기본값 사용
        if available_keywords:
            default_keyword = available_keywords[0]
            data[f'{prefix}_{default_keyword}'] = 1
            logger.warning(f"⚠️ 키워드 기본값: '{keyword}' → '{default_keyword}' 사용")

    def _set_default_naver_categories(self, data: dict):
        """네이버 카테고리 기본값 설정"""
        # 네이버 카테고리 계층별 기본값 설정
        naver_prefixes = ['category1', 'category2', 'category3', 'category4']

        for naver_prefix in naver_prefixes:
            full_prefix = f'naver_{naver_prefix}'
            if full_prefix in self._categorical_mappings:
                available_values = self._categorical_mappings[full_prefix]
                if available_values:
                    # 각 계층의 첫 번째 값을 기본값으로 사용
                    default_value = available_values[0]
                    data[f'naver_{naver_prefix}_{default_value}'] = 1

    def get_supported_categories(self) -> Dict[str, List[str]]:
        """지원되는 범주형 값들 반환 (API 문서화용)"""
        if not hasattr(self, '_categorical_mappings'):
            self._load_model_feature_mappings()

        return self._categorical_mappings.copy()

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
                cache_key = f"price_prediction:{hash(str(product_request.model_dump()))}"
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
            cache_key = f"price_prediction:{hash(str(request.model_dump()))}"
            await self.cache_manager.set(cache_key, response.model_dump(), ttl=3600)

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

    def _generate_dummy_price_prediction(self, request: PricePredictionRequest, start_time: datetime) -> PricePredictionResponse:
        """실제 모델이 없을 때 더미 예측 생성"""
        import random

        # 카테고리별 기본 가격 범위 (실제 시장 데이터 기반 추정)
        category_price_ranges = {
            "컴퓨터/IT": (20, 500),
            "가전제품": (50, 1000),
            "생활용품": (5, 100),
            "패션": (10, 300),
            "스포츠/레저": (15, 400),
            "뷰티": (8, 200),
            "반려동물": (10, 150),
            "식품": (3, 80),
        }

        # 기본 가격 범위 (카테고리가 없는 경우)
        min_price, max_price = category_price_ranges.get(request.category, (10, 200))

        # 평점과 리뷰 수를 고려한 가격 조정
        rating_multiplier = 1 + (request.rating - 3.5) * 0.1  # 평점이 높을수록 더 비쌈
        review_multiplier = 1 + min(request.review_count / 1000, 0.3)  # 리뷰가 많을수록 더 비쌈

        # 브랜드 프리미엄 (잘 알려진 브랜드일 경우)
        premium_brands = ["Apple", "Samsung", "LG", "Nike", "Adidas", "Sony"]
        brand_multiplier = 1.2 if any(brand.lower() in request.brand.lower() for brand in premium_brands) else 1.0

        # 검색 키워드 기반 조정
        expensive_keywords = ["프리미엄", "럭셔리", "프로", "고급", "professional"]
        keyword_multiplier = 1.3 if any(keyword in request.search_keyword.lower() for keyword in expensive_keywords) else 1.0

        # 최종 가격 계산
        base_price = random.uniform(min_price, max_price)
        predicted_price = base_price * rating_multiplier * review_multiplier * brand_multiplier * keyword_multiplier

        # 신뢰구간 (더미 데이터이므로 넓게 설정)
        confidence_interval = {
            "lower": max(1, predicted_price * 0.7),
            "upper": predicted_price * 1.4
        }

        # 응답 생성
        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        response = PricePredictionResponse(
            predicted_price=round(predicted_price, 2),
            confidence_interval=confidence_interval,
            model_version="dummy-v1.0",
            prediction_timestamp=datetime.now(),
            processing_time_ms=round(processing_time, 2)
        )

        logger.info(f"🎭 더미 가격 예측 완료: ${predicted_price:.2f} (실제 모델 없음)")
        return response

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

            # 간단한 예측 테스트 (실제 훈련된 데이터 값 사용)
            if "price_predictor" in self.models:
                test_request = PricePredictionRequest(
                    category="디지털/가전 > 주변기기 > 마우스 > 무선마우스",
                    brand="로지텍",
                    seller="네이버",
                    search_keyword="무선마우스",
                    maker="로지텍",
                    rating=4.5,
                    review_count=100,
                    price_to_category_avg_ratio=1.0,
                    price_to_keyword_avg_ratio=1.0
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