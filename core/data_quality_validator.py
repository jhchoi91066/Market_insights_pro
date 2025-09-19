# -*- coding: utf-8 -*-
"""
Market Insights Pro - 데이터 품질 검증 시스템
수집된 Amazon 데이터의 품질을 실시간으로 검증하고 모니터링

주요 기능:
- 실시간 데이터 품질 검증
- 이상 데이터 탐지 및 필터링
- 품질 메트릭 추적
- 자동 품질 보고서 생성
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import statistics
import json

logger = logging.getLogger(__name__)

class QualityLevel(Enum):
    """데이터 품질 수준"""
    EXCELLENT = "excellent"  # 95% 이상
    GOOD = "good"           # 80-95%
    FAIR = "fair"           # 60-80%
    POOR = "poor"           # 40-60%
    CRITICAL = "critical"   # 40% 미만

class ValidationResult(Enum):
    """검증 결과"""
    VALID = "valid"
    WARNING = "warning"
    INVALID = "invalid"

@dataclass
class QualityIssue:
    """품질 문제 정보"""
    field: str
    issue_type: str
    description: str
    severity: str
    suggestion: str
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class QualityMetrics:
    """품질 메트릭"""
    total_products: int = 0
    valid_products: int = 0
    warning_products: int = 0
    invalid_products: int = 0

    # 필드별 유효성
    title_validity_rate: float = 0.0
    price_validity_rate: float = 0.0
    rating_validity_rate: float = 0.0
    review_validity_rate: float = 0.0
    url_validity_rate: float = 0.0

    # 품질 점수
    overall_quality_score: float = 0.0
    quality_level: QualityLevel = QualityLevel.POOR

    # 시간 정보
    last_updated: datetime = field(default_factory=datetime.now)
    issues: List[QualityIssue] = field(default_factory=list)

class DataQualityValidator:
    """
    Amazon 상품 데이터 품질 검증기

    다양한 규칙과 패턴을 사용하여 데이터 품질을 검증하고
    품질 문제를 실시간으로 탐지합니다.
    """

    def __init__(self):
        self.metrics = QualityMetrics()
        self.validation_rules = self._load_validation_rules()
        self.quality_history: List[QualityMetrics] = []

    def _load_validation_rules(self) -> Dict[str, Any]:
        """검증 규칙 로드"""
        return {
            "title": {
                "min_length": 10,
                "max_length": 500,
                "invalid_patterns": [
                    r"sponsored",
                    r"best seller",
                    r"amazon's choice",
                    r"overall pick",
                    r"limited time",
                    r"add to cart",
                    r"save \d+%",
                    r"free shipping",
                    r"climate pledge",
                    r"^advertisement",
                    r"^ad:",
                    r"^\s*$"
                ],
                "required_patterns": [
                    r"[a-zA-Z]"  # 최소한 알파벳 포함
                ]
            },
            "price": {
                "min_value": 0.01,
                "max_value": 50000.0,  # $50,000
                "suspicious_values": [0.0, 999999.0],
                "currency_format": r"^\d+(\.\d{2})?$"
            },
            "rating": {
                "min_value": 0.0,
                "max_value": 5.0,
                "precision": 1  # 소수점 1자리
            },
            "review_count": {
                "min_value": 0,
                "max_value": 1000000,
                "suspicious_threshold": 500000  # 50만 개 이상은 의심스러움
            },
            "url": {
                "required_domain": "amazon.com",
                "required_patterns": [
                    r"amazon\.com",
                    r"/(dp|gp/product)/[A-Z0-9]{10}"  # ASIN 패턴
                ]
            },
            "asin": {
                "pattern": r"^[A-Z0-9]{10}$",
                "required": True
            }
        }

    def validate_product(self, product_data: Dict[str, Any]) -> Tuple[ValidationResult, List[QualityIssue]]:
        """
        단일 상품 데이터 검증

        Args:
            product_data: 상품 데이터 딕셔너리

        Returns:
            (검증 결과, 발견된 이슈 리스트)
        """
        issues = []

        # 각 필드별 검증
        title_result = self._validate_title(product_data.get("title", ""))
        if title_result[0] != ValidationResult.VALID:
            issues.extend(title_result[1])

        price_result = self._validate_price(product_data.get("price", 0))
        if price_result[0] != ValidationResult.VALID:
            issues.extend(price_result[1])

        rating_result = self._validate_rating(product_data.get("rating", 0))
        if rating_result[0] != ValidationResult.VALID:
            issues.extend(rating_result[1])

        review_result = self._validate_review_count(product_data.get("review_count", 0))
        if review_result[0] != ValidationResult.VALID:
            issues.extend(review_result[1])

        url_result = self._validate_url(product_data.get("url", ""))
        if url_result[0] != ValidationResult.VALID:
            issues.extend(url_result[1])

        asin_result = self._validate_asin(product_data.get("asin", ""))
        if asin_result[0] != ValidationResult.VALID:
            issues.extend(asin_result[1])

        # 전체 검증 결과 결정
        critical_issues = [i for i in issues if i.severity == "critical"]
        warning_issues = [i for i in issues if i.severity == "warning"]

        if critical_issues:
            return ValidationResult.INVALID, issues
        elif warning_issues:
            return ValidationResult.WARNING, issues
        else:
            return ValidationResult.VALID, issues

    def _validate_title(self, title: str) -> Tuple[ValidationResult, List[QualityIssue]]:
        """상품명 검증"""
        issues = []
        rules = self.validation_rules["title"]

        # 길이 검증
        if len(title) < rules["min_length"]:
            issues.append(QualityIssue(
                field="title",
                issue_type="length_too_short",
                description=f"상품명이 너무 짧습니다 ({len(title)}자)",
                severity="critical",
                suggestion=f"최소 {rules['min_length']}자 이상이어야 합니다"
            ))

        if len(title) > rules["max_length"]:
            issues.append(QualityIssue(
                field="title",
                issue_type="length_too_long",
                description=f"상품명이 너무 깁니다 ({len(title)}자)",
                severity="warning",
                suggestion=f"최대 {rules['max_length']}자 이하로 권장합니다"
            ))

        # 불필요한 패턴 검증
        title_lower = title.lower()
        for pattern in rules["invalid_patterns"]:
            if re.search(pattern, title_lower):
                issues.append(QualityIssue(
                    field="title",
                    issue_type="invalid_content",
                    description=f"부적절한 내용 포함: {pattern}",
                    severity="critical",
                    suggestion="상품명에서 광고성 문구를 제거하세요"
                ))

        # 필수 패턴 검증
        for pattern in rules["required_patterns"]:
            if not re.search(pattern, title):
                issues.append(QualityIssue(
                    field="title",
                    issue_type="missing_required_content",
                    description=f"필수 내용 누락: {pattern}",
                    severity="critical",
                    suggestion="유효한 상품명을 입력하세요"
                ))

        if issues:
            severity_levels = [i.severity for i in issues]
            if "critical" in severity_levels:
                return ValidationResult.INVALID, issues
            else:
                return ValidationResult.WARNING, issues

        return ValidationResult.VALID, issues

    def _validate_price(self, price: float) -> Tuple[ValidationResult, List[QualityIssue]]:
        """가격 검증"""
        issues = []
        rules = self.validation_rules["price"]

        # 범위 검증
        if price < rules["min_value"]:
            issues.append(QualityIssue(
                field="price",
                issue_type="price_too_low",
                description=f"가격이 너무 낮습니다: ${price}",
                severity="critical",
                suggestion=f"최소 ${rules['min_value']} 이상이어야 합니다"
            ))

        if price > rules["max_value"]:
            issues.append(QualityIssue(
                field="price",
                issue_type="price_too_high",
                description=f"가격이 비정상적으로 높습니다: ${price}",
                severity="warning",
                suggestion="가격 정보를 다시 확인하세요"
            ))

        # 의심스러운 값 검증
        if price in rules["suspicious_values"]:
            issues.append(QualityIssue(
                field="price",
                issue_type="suspicious_price",
                description=f"의심스러운 가격 값: ${price}",
                severity="warning",
                suggestion="가격 파싱 로직을 점검하세요"
            ))

        # 가격 형식 검증 (소수점 둘째 자리까지)
        if price > 0:
            price_str = f"{price:.2f}"
            if not re.match(rules["currency_format"], price_str):
                issues.append(QualityIssue(
                    field="price",
                    issue_type="invalid_format",
                    description=f"잘못된 가격 형식: ${price}",
                    severity="warning",
                    suggestion="가격은 소수점 둘째 자리까지만 허용됩니다"
                ))

        if issues:
            severity_levels = [i.severity for i in issues]
            if "critical" in severity_levels:
                return ValidationResult.INVALID, issues
            else:
                return ValidationResult.WARNING, issues

        return ValidationResult.VALID, issues

    def _validate_rating(self, rating: float) -> Tuple[ValidationResult, List[QualityIssue]]:
        """평점 검증"""
        issues = []
        rules = self.validation_rules["rating"]

        # 범위 검증
        if rating < rules["min_value"] or rating > rules["max_value"]:
            issues.append(QualityIssue(
                field="rating",
                issue_type="rating_out_of_range",
                description=f"평점이 범위를 벗어남: {rating}",
                severity="critical",
                suggestion=f"평점은 {rules['min_value']}-{rules['max_value']} 범위여야 합니다"
            ))

        # 정밀도 검증
        if rating > 0:
            decimal_places = len(str(rating).split('.')[-1]) if '.' in str(rating) else 0
            if decimal_places > rules["precision"]:
                issues.append(QualityIssue(
                    field="rating",
                    issue_type="excessive_precision",
                    description=f"평점 정밀도 초과: {rating}",
                    severity="warning",
                    suggestion=f"소수점 {rules['precision']}자리까지만 허용됩니다"
                ))

        if issues:
            severity_levels = [i.severity for i in issues]
            if "critical" in severity_levels:
                return ValidationResult.INVALID, issues
            else:
                return ValidationResult.WARNING, issues

        return ValidationResult.VALID, issues

    def _validate_review_count(self, review_count: int) -> Tuple[ValidationResult, List[QualityIssue]]:
        """리뷰 수 검증"""
        issues = []
        rules = self.validation_rules["review_count"]

        # 범위 검증
        if review_count < rules["min_value"] or review_count > rules["max_value"]:
            issues.append(QualityIssue(
                field="review_count",
                issue_type="review_count_out_of_range",
                description=f"리뷰 수가 범위를 벗어남: {review_count}",
                severity="critical",
                suggestion=f"리뷰 수는 {rules['min_value']}-{rules['max_value']} 범위여야 합니다"
            ))

        # 의심스러운 값 검증
        if review_count > rules["suspicious_threshold"]:
            issues.append(QualityIssue(
                field="review_count",
                issue_type="suspicious_review_count",
                description=f"비정상적으로 많은 리뷰: {review_count}",
                severity="warning",
                suggestion="리뷰 수 파싱 로직을 점검하세요"
            ))

        if issues:
            severity_levels = [i.severity for i in issues]
            if "critical" in severity_levels:
                return ValidationResult.INVALID, issues
            else:
                return ValidationResult.WARNING, issues

        return ValidationResult.VALID, issues

    def _validate_url(self, url: str) -> Tuple[ValidationResult, List[QualityIssue]]:
        """URL 검증"""
        issues = []
        rules = self.validation_rules["url"]

        if not url:
            issues.append(QualityIssue(
                field="url",
                issue_type="missing_url",
                description="URL이 없습니다",
                severity="critical",
                suggestion="유효한 Amazon URL이 필요합니다"
            ))
            return ValidationResult.INVALID, issues

        # 도메인 검증
        if rules["required_domain"] not in url.lower():
            issues.append(QualityIssue(
                field="url",
                issue_type="invalid_domain",
                description=f"잘못된 도메인: {url}",
                severity="critical",
                suggestion=f"URL은 {rules['required_domain']}를 포함해야 합니다"
            ))

        # 패턴 검증
        valid_pattern_found = False
        for pattern in rules["required_patterns"]:
            if re.search(pattern, url):
                valid_pattern_found = True
                break

        if not valid_pattern_found:
            issues.append(QualityIssue(
                field="url",
                issue_type="invalid_url_pattern",
                description=f"잘못된 URL 형식: {url}",
                severity="warning",
                suggestion="Amazon 상품 URL 형식을 확인하세요"
            ))

        if issues:
            severity_levels = [i.severity for i in issues]
            if "critical" in severity_levels:
                return ValidationResult.INVALID, issues
            else:
                return ValidationResult.WARNING, issues

        return ValidationResult.VALID, issues

    def _validate_asin(self, asin: str) -> Tuple[ValidationResult, List[QualityIssue]]:
        """ASIN 검증"""
        issues = []
        rules = self.validation_rules["asin"]

        if not asin and rules["required"]:
            issues.append(QualityIssue(
                field="asin",
                issue_type="missing_asin",
                description="ASIN이 없습니다",
                severity="critical",
                suggestion="Amazon ASIN이 필요합니다"
            ))
        elif asin and not re.match(rules["pattern"], asin):
            issues.append(QualityIssue(
                field="asin",
                issue_type="invalid_asin_format",
                description=f"잘못된 ASIN 형식: {asin}",
                severity="critical",
                suggestion="ASIN은 10자리 영숫자 조합이어야 합니다"
            ))

        if issues:
            return ValidationResult.INVALID, issues

        return ValidationResult.VALID, issues

    def validate_batch(self, products: List[Dict[str, Any]]) -> QualityMetrics:
        """
        배치 상품 데이터 검증

        Args:
            products: 상품 데이터 리스트

        Returns:
            품질 메트릭
        """
        logger.info(f"📊 {len(products)}개 상품 배치 검증 시작...")

        # 메트릭 초기화
        self.metrics = QualityMetrics()
        self.metrics.total_products = len(products)

        valid_count = 0
        warning_count = 0
        invalid_count = 0

        # 필드별 유효성 카운터
        field_validity = {
            "title": 0,
            "price": 0,
            "rating": 0,
            "review_count": 0,
            "url": 0
        }

        all_issues = []

        # 각 상품 검증
        for i, product in enumerate(products):
            result, issues = self.validate_product(product)

            if result == ValidationResult.VALID:
                valid_count += 1
                # 모든 필드가 유효하다고 가정
                for field in field_validity:
                    field_validity[field] += 1
            elif result == ValidationResult.WARNING:
                warning_count += 1
                # 경고가 있는 필드만 제외하고 유효성 카운트
                warning_fields = {issue.field for issue in issues if issue.severity == "warning"}
                for field in field_validity:
                    if field not in warning_fields:
                        field_validity[field] += 1
            else:  # INVALID
                invalid_count += 1
                # 크리티컬 이슈가 없는 필드만 유효성 카운트
                critical_fields = {issue.field for issue in issues if issue.severity == "critical"}
                for field in field_validity:
                    if field not in critical_fields:
                        field_validity[field] += 1

            all_issues.extend(issues)

            # 진행상황 로깅 (매 20개마다)
            if (i + 1) % 20 == 0:
                logger.info(f"  진행상황: {i + 1}/{len(products)} 완료")

        # 메트릭 계산
        self.metrics.valid_products = valid_count
        self.metrics.warning_products = warning_count
        self.metrics.invalid_products = invalid_count

        # 필드별 유효성 비율 계산
        total = max(1, len(products))
        self.metrics.title_validity_rate = field_validity["title"] / total * 100
        self.metrics.price_validity_rate = field_validity["price"] / total * 100
        self.metrics.rating_validity_rate = field_validity["rating"] / total * 100
        self.metrics.review_validity_rate = field_validity["review_count"] / total * 100
        self.metrics.url_validity_rate = field_validity["url"] / total * 100

        # 전체 품질 점수 계산
        self.metrics.overall_quality_score = self._calculate_quality_score()
        self.metrics.quality_level = self._determine_quality_level(self.metrics.overall_quality_score)

        # 상위 이슈들 저장
        self.metrics.issues = self._get_top_issues(all_issues)
        self.metrics.last_updated = datetime.now()

        # 히스토리에 추가
        self.quality_history.append(self.metrics)

        logger.info(f"✅ 배치 검증 완료!")
        logger.info(f"   품질 점수: {self.metrics.overall_quality_score:.1f}% ({self.metrics.quality_level.value})")
        logger.info(f"   유효: {valid_count}, 경고: {warning_count}, 무효: {invalid_count}")

        return self.metrics

    def _calculate_quality_score(self) -> float:
        """전체 품질 점수 계산"""
        # 가중치 설정
        weights = {
            "valid_ratio": 0.4,      # 유효한 상품 비율
            "title_validity": 0.15,   # 제목 유효성
            "price_validity": 0.25,   # 가격 유효성
            "rating_validity": 0.1,   # 평점 유효성
            "review_validity": 0.05,  # 리뷰 유효성
            "url_validity": 0.05      # URL 유효성
        }

        total = max(1, self.metrics.total_products)
        valid_ratio = self.metrics.valid_products / total * 100

        score = (
            weights["valid_ratio"] * valid_ratio +
            weights["title_validity"] * self.metrics.title_validity_rate +
            weights["price_validity"] * self.metrics.price_validity_rate +
            weights["rating_validity"] * self.metrics.rating_validity_rate +
            weights["review_validity"] * self.metrics.review_validity_rate +
            weights["url_validity"] * self.metrics.url_validity_rate
        )

        return round(score, 1)

    def _determine_quality_level(self, score: float) -> QualityLevel:
        """품질 점수에 따른 품질 수준 결정"""
        if score >= 95:
            return QualityLevel.EXCELLENT
        elif score >= 80:
            return QualityLevel.GOOD
        elif score >= 60:
            return QualityLevel.FAIR
        elif score >= 40:
            return QualityLevel.POOR
        else:
            return QualityLevel.CRITICAL

    def _get_top_issues(self, all_issues: List[QualityIssue], limit: int = 10) -> List[QualityIssue]:
        """상위 이슈들 반환"""
        # 심각도별 정렬 (critical > warning)
        critical_issues = [i for i in all_issues if i.severity == "critical"]
        warning_issues = [i for i in all_issues if i.severity == "warning"]

        # 각 타입별로 빈도수 계산하여 상위 이슈들 선택
        issue_counts = {}
        for issue in all_issues:
            key = (issue.field, issue.issue_type, issue.severity)
            if key not in issue_counts:
                issue_counts[key] = {"count": 0, "example": issue}
            issue_counts[key]["count"] += 1

        # 빈도순 정렬
        sorted_issues = sorted(
            issue_counts.items(),
            key=lambda x: (x[1]["count"], x[0][2] == "critical"),
            reverse=True
        )

        # 상위 이슈들 반환
        top_issues = []
        for (field, issue_type, severity), data in sorted_issues[:limit]:
            issue = data["example"]
            issue.description += f" (발생 횟수: {data['count']})"
            top_issues.append(issue)

        return top_issues

    def generate_quality_report(self) -> Dict[str, Any]:
        """품질 보고서 생성"""
        if not self.metrics:
            return {"error": "검증된 데이터가 없습니다"}

        report = {
            "summary": {
                "timestamp": self.metrics.last_updated.isoformat(),
                "total_products": self.metrics.total_products,
                "quality_score": self.metrics.overall_quality_score,
                "quality_level": self.metrics.quality_level.value,
                "valid_products": self.metrics.valid_products,
                "warning_products": self.metrics.warning_products,
                "invalid_products": self.metrics.invalid_products
            },
            "field_validity": {
                "title": self.metrics.title_validity_rate,
                "price": self.metrics.price_validity_rate,
                "rating": self.metrics.rating_validity_rate,
                "review_count": self.metrics.review_validity_rate,
                "url": self.metrics.url_validity_rate
            },
            "top_issues": [
                {
                    "field": issue.field,
                    "type": issue.issue_type,
                    "description": issue.description,
                    "severity": issue.severity,
                    "suggestion": issue.suggestion
                }
                for issue in self.metrics.issues
            ],
            "recommendations": self._generate_recommendations()
        }

        return report

    def _generate_recommendations(self) -> List[str]:
        """개선 권장사항 생성"""
        recommendations = []

        if self.metrics.overall_quality_score < 60:
            recommendations.append("🚨 전체적인 데이터 품질이 낮습니다. 스크래핑 로직을 전면 재검토하세요.")

        if self.metrics.price_validity_rate < 70:
            recommendations.append("💰 가격 파싱 로직을 개선하세요. Amazon의 가격 선택자가 변경되었을 수 있습니다.")

        if self.metrics.title_validity_rate < 80:
            recommendations.append("📝 상품명 추출 로직을 개선하세요. 광고성 텍스트 필터링을 강화하세요.")

        if self.metrics.url_validity_rate < 90:
            recommendations.append("🔗 URL 추출 로직을 점검하세요. Amazon 상품 링크 구조를 재확인하세요.")

        if self.metrics.invalid_products > self.metrics.total_products * 0.3:
            recommendations.append("⚠️ 무효한 상품이 30% 이상입니다. 스크래핑 대상 페이지를 재검토하세요.")

        return recommendations

    def save_report(self, filepath: str = None) -> str:
        """품질 보고서 파일로 저장"""
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"data/quality_reports/quality_report_{timestamp}.json"

        import os
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        report = self.generate_quality_report()

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"📄 품질 보고서 저장: {filepath}")
        return filepath

# 사용 예시
def test_validator():
    """검증기 테스트"""
    # 테스트 데이터
    test_products = [
        {
            "title": "Apple AirPods Pro (2nd Generation) Wireless Earbuds",
            "price": 199.99,
            "rating": 4.5,
            "review_count": 25689,
            "url": "https://www.amazon.com/dp/B0BDHWDR12",
            "asin": "B0BDHWDR12"
        },
        {
            "title": "Sponsored",  # 잘못된 제목
            "price": 0.0,         # 잘못된 가격
            "rating": 6.0,        # 잘못된 평점
            "review_count": -5,   # 잘못된 리뷰 수
            "url": "invalid-url", # 잘못된 URL
            "asin": "123"         # 잘못된 ASIN
        }
    ]

    validator = DataQualityValidator()
    metrics = validator.validate_batch(test_products)

    print(f"품질 점수: {metrics.overall_quality_score}% ({metrics.quality_level.value})")
    print(f"유효 상품: {metrics.valid_products}/{metrics.total_products}")

    # 보고서 생성
    report = validator.generate_quality_report()
    print("\n품질 보고서:")
    print(json.dumps(report, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test_validator()