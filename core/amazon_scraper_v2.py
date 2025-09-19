# -*- coding: utf-8 -*-
"""
Amazon Market Insights Pro - Stable Amazon Scraper v2
안정적이고 고품질 데이터 수집을 위한 Amazon 전용 스크래퍼

주요 개선사항:
- Amazon 전용 선택자 사용
- 강화된 데이터 품질 검증
- 개선된 에러 핸들링 및 재시도 로직
- 실시간 모니터링 메트릭
"""

import asyncio
import re
import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from playwright.async_api import async_playwright, Page, Browser, TimeoutError
from bs4 import BeautifulSoup
import json

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ProductData:
    """Amazon 상품 데이터 구조"""
    title: str
    price: float
    rating: float
    review_count: int
    url: str
    asin: str
    image_url: str = ""
    brand: str = ""
    is_prime: bool = False
    availability: str = ""
    category: str = ""

@dataclass
class ScrapingMetrics:
    """스크래핑 성능 메트릭"""
    start_time: datetime
    end_time: Optional[datetime] = None
    products_found: int = 0
    products_parsed: int = 0
    errors_count: int = 0
    success_rate: float = 0.0
    average_parse_time: float = 0.0

class AmazonScraperV2:
    """
    안정적인 Amazon 스크래핑을 위한 개선된 클래스

    특징:
    - Amazon 전용 최적화
    - 강화된 봇 탐지 우회
    - 데이터 품질 보장
    - 상세한 모니터링
    """

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.metrics = ScrapingMetrics(start_time=datetime.now())

        # 확장된 User-Agent 풀
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        ]

        # 동적 헤더 풀
        self.accept_headers = [
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        ]

        self.accept_language_headers = [
            "en-US,en;q=0.9",
            "en-US,en;q=0.8",
            "en-US,en;q=0.9,ko;q=0.8",
            "en-US,en;q=0.7,ko;q=0.3"
        ]

        self.accept_encoding_headers = [
            "gzip, deflate, br",
            "gzip, deflate",
            "gzip, deflate, br, zstd"
        ]

    def generate_random_headers(self) -> dict:
        """각 요청마다 다른 헤더 조합을 생성"""
        headers = {
            'Accept': random.choice(self.accept_headers),
            'Accept-Language': random.choice(self.accept_language_headers),
            'Accept-Encoding': random.choice(self.accept_encoding_headers),
            'DNT': random.choice(['1', '0']),
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

        # 선택적으로 추가할 헤더들
        optional_headers = {
            'Sec-Fetch-Dest': random.choice(['document', 'empty']),
            'Sec-Fetch-Mode': random.choice(['navigate', 'cors']),
            'Sec-Fetch-Site': random.choice(['none', 'same-origin']),
            'Sec-Fetch-User': '?1'
        }

        # 랜덤하게 일부 헤더만 포함 (더 자연스럽게)
        for header, value in optional_headers.items():
            if random.random() > 0.3:  # 70% 확률로 포함
                headers[header] = value

        # 헤더 순서도 랜덤하게 섞기
        headers_list = list(headers.items())
        random.shuffle(headers_list)

        return dict(headers_list)

    async def start_browser(self, headless: bool = True) -> bool:
        """
        최적화된 브라우저 시작

        Args:
            headless: 헤드리스 모드 사용 여부

        Returns:
            성공 여부
        """
        try:
            logger.info("🚀 Amazon 스크래퍼 v2 브라우저 시작...")

            pw = await async_playwright().start()

            # Amazon 최적화된 Chromium 브라우저 설정 (이전 작동 버전 복원)
            self.browser = await pw.chromium.launch(
                headless=headless,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-extensions',
                    '--disable-automation',
                    '--disable-infobars',
                    '--start-maximized',
                    # Amazon 특화 추가 설정
                    '--disable-notifications',
                    '--disable-popup-blocking',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-features=TranslateUI',
                    '--disable-ipc-flooding-protection',
                    '--disable-features=VizDisplayCompositor,site-per-process',
                    '--disable-field-trial-config',
                    '--disable-plugins-discovery',
                    '--disable-default-apps',
                    '--no-default-browser-check',
                    '--disable-component-extensions-with-background-pages'
                ]
            )
            logger.info("✅ Chromium 브라우저 시작 성공")

            # User-Agent 랜덤 선택
            selected_ua = random.choice(self.user_agents)
            logger.info(f"🔄 User-Agent: {selected_ua[:80]}...")

            # 동적 헤더 생성
            dynamic_headers = self.generate_random_headers()
            logger.info(f"🔀 동적 헤더 생성: {len(dynamic_headers)}개 헤더")

            # 컨텍스트 생성 (동적 헤더 사용)
            context = await self.browser.new_context(
                user_agent=selected_ua,
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',  # 한국어에서 영어로
                timezone_id='America/New_York',  # 미국 동부 시간대
                ignore_https_errors=True,
                java_script_enabled=True,
                permissions=['geolocation'],
                # 동적으로 생성된 헤더 사용
                extra_http_headers=dynamic_headers
            )

            # 타임아웃 설정
            context.set_default_timeout(45000)  # 45초
            context.set_default_navigation_timeout(60000)  # 60초

            self.page = await context.new_page()

            # Amazon 특화 봇 탐지 우회
            await self.page.add_init_script("""
                // webdriver 탐지 우회
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });

                // 플러그인 정보 추가
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });

                // permissions API
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );

                // Chrome runtime
                window.chrome = {
                    runtime: {}
                };
            """)

            # Amazon 홈페이지 방문으로 세션 워밍업
            await self._warm_up_session()

            logger.info("✅ 브라우저 시작 완료")
            return True

        except Exception as e:
            logger.error(f"❌ 브라우저 시작 실패: {e}")
            return False

    async def _warm_up_session(self) -> None:
        """Amazon 세션 워밍업"""
        try:
            logger.info("🔄 Amazon 세션 워밍업 중...")

            await self.page.goto("https://www.amazon.com",
                                wait_until='domcontentloaded',
                                timeout=30000)

            # 자연스러운 사용자 행동 시뮬레이션
            await asyncio.sleep(random.uniform(2, 4))

            # 페이지 스크롤
            await self.page.evaluate("window.scrollTo(0, Math.random() * 500)")
            await asyncio.sleep(random.uniform(1, 2))

            logger.info("✅ 세션 워밍업 완료")

        except Exception as e:
            logger.warning(f"⚠️ 세션 워밍업 실패 (계속 진행): {e}")

    async def search_products(self, keyword: str, max_products: int = 20) -> List[ProductData]:
        """
        키워드로 Amazon 상품 검색

        Args:
            keyword: 검색 키워드
            max_products: 최대 수집 상품 수

        Returns:
            수집된 상품 리스트
        """
        if not self.page:
            raise Exception("브라우저가 시작되지 않았습니다.")

        logger.info(f"🔍 '{keyword}' 키워드로 Amazon 검색 시작...")
        self.metrics = ScrapingMetrics(start_time=datetime.now())

        try:
            # 검색 수행
            await self._perform_search(keyword)

            # 상품 데이터 수집
            products = await self._extract_products(max_products)

            # 메트릭 업데이트
            self.metrics.end_time = datetime.now()
            self.metrics.products_found = len(products)
            self.metrics.products_parsed = len([p for p in products if p.price > 0])
            self.metrics.success_rate = self.metrics.products_parsed / max(1, self.metrics.products_found) * 100

            duration = (self.metrics.end_time - self.metrics.start_time).total_seconds()
            self.metrics.average_parse_time = duration / max(1, self.metrics.products_parsed)

            logger.info(f"✅ 검색 완료: {self.metrics.products_parsed}/{self.metrics.products_found}개 상품 파싱 성공")
            logger.info(f"📊 성공률: {self.metrics.success_rate:.1f}%, 평균 처리시간: {self.metrics.average_parse_time:.2f}초/상품")

            return products

        except Exception as e:
            self.metrics.errors_count += 1
            logger.error(f"❌ 검색 실패: {e}")
            raise

    async def _perform_search(self, keyword: str) -> None:
        """Amazon에서 키워드 검색 수행 (동적 헤더 적용)"""
        try:
            # 각 검색마다 새로운 헤더 적용
            new_headers = self.generate_random_headers()
            await self.page.set_extra_http_headers(new_headers)
            logger.info(f"🔀 검색 요청용 새 헤더 적용: {len(new_headers)}개")

            # 직접 검색 URL 접근 (더 안정적)
            import urllib.parse
            encoded_keyword = urllib.parse.quote_plus(keyword)
            search_url = f"https://www.amazon.com/s?k={encoded_keyword}&ref=sr_pg_1"

            logger.info(f"🎯 검색 URL 접근: {search_url}")

            # 요청 전 대기 (봇 탐지 회피)
            await asyncio.sleep(random.uniform(2, 4))

            await self.page.goto(search_url, wait_until='domcontentloaded', timeout=60000)

            # 검색 결과 로딩 대기 (더 긴 대기시간)
            await asyncio.sleep(random.uniform(4, 7))

            # CAPTCHA 또는 봇 탐지 페이지 확인
            await self._check_for_blocks()

            logger.info("✅ 검색 페이지 로딩 완료")

        except TimeoutError:
            raise Exception("Amazon 검색 페이지 로딩 타임아웃")
        except Exception as e:
            raise Exception(f"검색 수행 중 오류: {e}")

    async def _check_for_blocks(self) -> None:
        """Amazon 차단 페이지 감지"""
        page_content = await self.page.content()
        page_title = await self.page.title()

        # 차단 패턴 감지
        block_patterns = [
            "robot", "captcha", "blocked", "unusual traffic",
            "sorry", "access denied", "temporarily unavailable"
        ]

        content_lower = page_content.lower()
        title_lower = page_title.lower()

        for pattern in block_patterns:
            if pattern in content_lower or pattern in title_lower:
                raise Exception(f"Amazon 접근 차단 감지: {pattern}")

    async def _extract_products(self, max_products: int) -> List[ProductData]:
        """검색 결과에서 상품 데이터 추출"""
        logger.info("📦 상품 데이터 추출 시작...")

        # Amazon 검색 결과 컨테이너 찾기
        search_results = await self._find_search_results()
        if not search_results:
            raise Exception("검색 결과 컨테이너를 찾을 수 없음")

        # HTML 파싱
        html = await search_results.inner_html()
        soup = BeautifulSoup(html, 'html.parser')

        # 상품 요소들 찾기
        product_elements = soup.select('[data-component-type="s-search-result"]')

        if not product_elements:
            # 백업 선택자들 시도
            backup_selectors = [
                '.s-result-item',
                '[data-asin]',
                '.s-card-container'
            ]

            for selector in backup_selectors:
                product_elements = soup.select(selector)
                if product_elements:
                    logger.info(f"📦 백업 선택자로 발견: {selector}")
                    break

        if not product_elements:
            raise Exception("상품 요소를 찾을 수 없음")

        logger.info(f"📦 {len(product_elements)}개 상품 요소 발견")

        # 각 상품 파싱
        products = []
        for i, element in enumerate(product_elements[:max_products]):
            try:
                product = await self._parse_product_element(element, i + 1)
                if product and self._validate_product(product):
                    products.append(product)

            except Exception as e:
                logger.warning(f"⚠️ 상품 {i+1} 파싱 실패: {e}")
                self.metrics.errors_count += 1
                continue

        return products

    async def _find_search_results(self):
        """검색 결과 컨테이너 찾기"""
        selectors = [
            '[data-component-type="s-search-result"]',
            '.s-search-results',
            '[cel_widget_id="MAIN-SEARCH_RESULTS"]',
            '#search',
            '.s-widget-container'
        ]

        for selector in selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    logger.info(f"✅ 검색 결과 컨테이너 발견: {selector}")
                    return await self.page.query_selector('.s-search-results, #search')
            except:
                continue

        return None

    async def _parse_product_element(self, element, index: int) -> Optional[ProductData]:
        """개별 상품 요소 파싱"""
        try:
            # ASIN 추출
            asin = element.get('data-asin', '')

            # 상품명 추출
            title = self._extract_title(element)

            # 가격 추출
            price = self._extract_price(element)

            # 평점 추출
            rating = self._extract_rating(element)

            # 리뷰 수 추출
            review_count = self._extract_review_count(element)

            # URL 추출
            url = self._extract_url(element)

            # 브랜드 추출
            brand = self._extract_brand(element)

            # Prime 배송 확인
            is_prime = self._check_prime(element)

            # 이미지 URL 추출
            image_url = self._extract_image_url(element)

            product = ProductData(
                title=title,
                price=price,
                rating=rating,
                review_count=review_count,
                url=url,
                asin=asin,
                image_url=image_url,
                brand=brand,
                is_prime=is_prime
            )

            if index <= 3:  # 처음 3개만 로깅
                logger.info(f"  ✅ 상품 {index}: {title[:40]}... - ${price}")

            return product

        except Exception as e:
            logger.warning(f"상품 {index} 파싱 오류: {e}")
            return None

    def _extract_title(self, element) -> str:
        """상품명 추출"""
        title_selectors = [
            'h3.s-size-mini a span',
            'h2.a-size-mini a span',
            '.s-link-style a span',
            'h3 a span',
            'h2 a span',
            '[data-cy="title-recipe-list"] a span'
        ]

        for selector in title_selectors:
            title_elem = element.select_one(selector)
            if title_elem:
                title = title_elem.get_text().strip()

                # 불필요한 텍스트 필터링
                invalid_patterns = [
                    'sponsored', 'best seller', 'amazon\'s choice',
                    'limited time deal', 'overall pick', 'climate pledge',
                    'add to cart', 'save', 'coupon'
                ]

                title_lower = title.lower()
                if (title and len(title) > 10 and
                    not any(pattern in title_lower for pattern in invalid_patterns)):
                    return title

        return "Unknown Product"

    def _extract_price(self, element) -> float:
        """가격 추출 (USD)"""
        price_selectors = [
            '.a-price.a-text-price .a-offscreen',
            '.a-price .a-offscreen',
            '.a-price-whole',
            '.a-price-fraction',
            '.a-color-price'
        ]

        for selector in price_selectors:
            price_elem = element.select_one(selector)
            if price_elem:
                price_text = price_elem.get_text().strip()

                # 가격 파싱 (USD 형식: $12.99, 12.99 등)
                price_match = re.search(r'[\$]?([\d,]+(?:\.\d{2})?)', price_text.replace(',', ''))
                if price_match:
                    try:
                        price = float(price_match.group(1))
                        if 0.01 <= price <= 10000:  # 합리적인 가격 범위
                            return price
                    except ValueError:
                        continue

        return 0.0

    def _extract_rating(self, element) -> float:
        """평점 추출"""
        # aria-label에서 평점 추출 (가장 정확)
        rating_elem = element.select_one('.a-icon-alt')
        if rating_elem:
            aria_label = rating_elem.get('aria-label', '')
            rating_match = re.search(r'(\d+(?:\.\d+)?)\s*out\s*of\s*5\s*stars', aria_label.lower())
            if rating_match:
                try:
                    rating = float(rating_match.group(1))
                    if 0 <= rating <= 5:
                        return rating
                except ValueError:
                    pass

        # 백업: 텍스트에서 추출
        rating_selectors = [
            '.a-icon-alt',
            '.a-rating-average'
        ]

        for selector in rating_selectors:
            rating_elem = element.select_one(selector)
            if rating_elem:
                rating_text = rating_elem.get_text().strip()
                rating_match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
                if rating_match:
                    try:
                        rating = float(rating_match.group(1))
                        if 0 <= rating <= 5:
                            return rating
                    except ValueError:
                        continue

        return 0.0

    def _extract_review_count(self, element) -> int:
        """리뷰 수 추출"""
        review_selectors = [
            '.a-size-base.a-link-normal',
            '.a-size-base',
            'a[href*="#customerReviews"]'
        ]

        for selector in review_selectors:
            review_elem = element.select_one(selector)
            if review_elem:
                review_text = review_elem.get_text().strip()

                # 숫자만 추출 (예: "1,234" -> 1234)
                review_match = re.search(r'([\d,]+)', review_text.replace(',', ''))
                if review_match:
                    try:
                        count = int(review_match.group(1))
                        if 0 <= count <= 1000000:  # 합리적인 범위
                            return count
                    except ValueError:
                        continue

        return 0

    def _extract_url(self, element) -> str:
        """상품 URL 추출"""
        url_elem = element.select_one('h3 a, h2 a, .s-link-style a')
        if url_elem and url_elem.get('href'):
            href = url_elem['href']
            if href.startswith('/'):
                return f"https://www.amazon.com{href}"
            elif href.startswith('http'):
                return href

        return ""

    def _extract_brand(self, element) -> str:
        """브랜드 추출"""
        brand_selectors = [
            '.a-size-base-plus',
            '.s-brand-strip',
            '[data-cy="brand-strip"]'
        ]

        for selector in brand_selectors:
            brand_elem = element.select_one(selector)
            if brand_elem:
                brand = brand_elem.get_text().strip()
                if brand and len(brand) < 50:  # 브랜드명은 보통 짧음
                    return brand

        return ""

    def _check_prime(self, element) -> bool:
        """Prime 배송 여부 확인"""
        prime_selectors = [
            '.a-icon-prime',
            '[aria-label*="Prime"]',
            '.s-prime'
        ]

        for selector in prime_selectors:
            if element.select_one(selector):
                return True

        return False

    def _extract_image_url(self, element) -> str:
        """상품 이미지 URL 추출"""
        img_elem = element.select_one('.s-image')
        if img_elem:
            src = img_elem.get('src') or img_elem.get('data-src')
            if src and src.startswith('http'):
                return src

        return ""

    def _validate_product(self, product: ProductData) -> bool:
        """상품 데이터 유효성 검증"""
        # 필수 필드 확인
        if not product.title or product.title == "Unknown Product":
            return False

        if not product.asin:
            return False

        if product.price <= 0:
            return False

        if not product.url:
            return False

        # 제목 길이 확인
        if len(product.title) < 5 or len(product.title) > 500:
            return False

        # 가격 범위 확인
        if product.price > 10000:  # $10,000 초과 제품 제외
            return False

        return True

    async def close_browser(self) -> None:
        """브라우저 종료"""
        if self.browser:
            await self.browser.close()
            logger.info("🔚 브라우저 종료 완료")

    async def scrape_and_save_to_db(self, keyword: str, max_products: int = 30) -> dict:
        """
        키워드로 검색하여 상품 데이터를 수집하고 SQLite 데이터베이스에 저장하는 통합 메서드
        """
        logger.info(f"=== '{keyword}' 키워드로 데이터 수집 및 DB 저장 시작 ===")

        try:
            # 브라우저 시작
            if not await self.start_browser():
                return {"success": False, "message": "브라우저 시작 실패"}

            # 상품 검색
            products = await self.search_products(keyword, max_products)

            if not products:
                await self.close_browser()
                return {"success": False, "message": "상품을 찾을 수 없습니다"}

            # 데이터베이스 저장 (SQLite)
            saved_count = 0
            from core.analyzer_v2 import SQLiteMarketAnalyzer
            analyzer = SQLiteMarketAnalyzer()

            for product in products:
                try:
                    # ProductData를 dict로 변환
                    product_dict = {
                        'title': product.title,
                        'price': product.price,
                        'rating': product.rating,
                        'review_count': product.review_count,
                        'url': product.url,
                        'asin': product.asin,
                        'image_url': product.image_url,
                        'brand': product.brand,
                        'is_prime': product.is_prime,
                        'availability': product.availability,
                        'category': keyword,  # 키워드를 카테고리로 사용
                        'description': '',
                        'features': [],
                        'sales_rank': None,
                        'shipping_info': '',
                        'seller_info': ''
                    }

                    analyzer.save_product_to_db(product_dict)
                    saved_count += 1
                    logger.info(f"✅ 상품 저장: {product.title[:50]}...")

                except Exception as e:
                    logger.error(f"❌ 상품 저장 실패: {e}")
                    continue

            await self.close_browser()

            return {
                "success": True,
                "message": f"{saved_count}개 상품 저장 완료",
                "products_found": len(products),
                "products_saved": saved_count
            }

        except Exception as e:
            logger.error(f"❌ 스크래핑 실패: {e}")
            await self.close_browser()
            return {"success": False, "message": str(e)}

    def get_metrics(self) -> Dict[str, Any]:
        """스크래핑 메트릭 반환"""
        return {
            "start_time": self.metrics.start_time.isoformat(),
            "end_time": self.metrics.end_time.isoformat() if self.metrics.end_time else None,
            "products_found": self.metrics.products_found,
            "products_parsed": self.metrics.products_parsed,
            "errors_count": self.metrics.errors_count,
            "success_rate": self.metrics.success_rate,
            "average_parse_time": self.metrics.average_parse_time
        }

# 사용 예시
async def test_scraper():
    """스크래퍼 테스트 함수"""
    scraper = AmazonScraperV2()

    try:
        # 브라우저 시작
        if not await scraper.start_browser(headless=True):
            return

        # 상품 검색
        products = await scraper.search_products("wireless headphones", max_products=10)

        print(f"\n🎉 총 {len(products)}개 상품 수집 완료!")

        # 결과 출력
        for i, product in enumerate(products[:3], 1):
            print(f"\n{i}. {product.title}")
            print(f"   가격: ${product.price}")
            print(f"   평점: {product.rating}/5.0 ({product.review_count}개 리뷰)")
            print(f"   브랜드: {product.brand}")
            print(f"   Prime: {'Yes' if product.is_prime else 'No'}")

        # 메트릭 출력
        metrics = scraper.get_metrics()
        print(f"\n📊 스크래핑 메트릭:")
        print(f"   성공률: {metrics['success_rate']:.1f}%")
        print(f"   평균 처리시간: {metrics['average_parse_time']:.2f}초/상품")
        print(f"   에러 수: {metrics['errors_count']}")

    finally:
        await scraper.close_browser()

if __name__ == "__main__":
    asyncio.run(test_scraper())