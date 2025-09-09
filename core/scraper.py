# -*- coding: utf-8 -*-
"""
Amazon Market Insights Pro - Scraper Module
Amazon 상품 데이터 스크래핑을 담당하는 AmazonScraper 클래스를 정의합니다.
Playwright를 사용하여 동적 웹 페이지를 로드하고, BeautifulSoup으로 데이터를 파싱합니다.
"""
import asyncio
import csv
import os
import random
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser, TimeoutError
from bs4 import BeautifulSoup

# ORM 모델 import
try:
    from .models import db_manager, Product, ScrapingSession
except ImportError:
    # 직접 실행시에는 절대 import 사용
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from core.models import db_manager, Product, ScrapingSession

class AmazonScraper:
    """
    Amazon 웹사이트에서 상품 데이터를 스크레이핑하는 클래스.
    봇 탐지 우회 및 Amazon 특화 최적화가 적용되었습니다.
    """
    def __init__(self):
        self.browser: Browser | None = None
        self.page: Page | None = None

    async def start_browser(self):
        """Playwright를 시작하고 브라우저와 페이지 인스턴스를 생성합니다."""
        print("브라우저를 시작합니다 (Chromium 사용)...")
        pw = await async_playwright().start()
        
        self.browser = await pw.chromium.launch(
            headless=False,  # 헤드리스 모드 비활성화 (더 자연스럽게)
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-http2',  # HTTP/2 비활성화
                '--disable-blink-features=AutomationControlled',
                '--disable-features=VizDisplayCompositor',
                '--disable-web-security',
                '--disable-features=site-per-process',
                '--no-first-run',
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
        
        # 다양한 실제 User-Agent 로테이션
        import random
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
        ]
        selected_user_agent = random.choice(user_agents)
        print(f"🔄 User-Agent 선택: {selected_user_agent[:50]}...")
        
        context = await self.browser.new_context(
            user_agent=selected_user_agent,
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',  # 한국어에서 영어로
            timezone_id='America/New_York',  # 미국 동부 시간대
            ignore_https_errors=True,
            java_script_enabled=True,
            permissions=['geolocation'],
            # 아마존 특화 헤더 (더 자연스럽게)
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0'
            }
        )
        
        # 타임아웃 설정 - Amazon은 더 빠르게 반응하므로 줄임
        context.set_default_timeout(90000)  # 1.5분
        
        self.page = await context.new_page()
        
        # Amazon 특화 봇 탐지 우회 스크립트 주입
        await self.page.add_init_script("""
            // navigator.webdriver 제거
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            
            // 플러그인 정보 추가
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            
            // 언어 설정
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            
            // 스크린 해상도 자연스럽게
            Object.defineProperty(screen, 'width', {
                get: () => 1920,
            });
            Object.defineProperty(screen, 'height', {
                get: () => 1080,
            });
            
            // Permission API 모킹
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Chrome runtime 정보
            window.chrome = window.chrome || {};
            window.chrome.runtime = window.chrome.runtime || {};
            window.chrome.runtime.onConnect = {
                addListener: () => {},
                removeListener: () => {},
            };
        """)
        
        print("브라우저가 성공적으로 시작되었습니다.")
        
        # Amazon 세션 워밍업 - 실제 사용자처럼 행동
        print("🔄 Amazon 세션 초기화 중...")
        try:
            # 먼저 Amazon 홈페이지에 방문하여 정상적인 세션 생성
            await self.page.goto("https://www.amazon.com", wait_until='domcontentloaded', timeout=30000)
            
            # 인간처럼 페이지를 살펴보는 시간
            warmup_delay = random.uniform(3, 7)  # 3-7초 랜덤 대기
            print(f"⏱️ 세션 워밍업: {warmup_delay:.1f}초 대기...")
            await asyncio.sleep(warmup_delay)
            
            # 페이지를 약간 스크롤하여 더 자연스럽게
            await self.page.evaluate("window.scrollTo(0, Math.random() * 500)")
            await asyncio.sleep(random.uniform(1, 2))
            
            print("✅ Amazon 세션 초기화 완료")
        except Exception as e:
            print(f"⚠️ 세션 워밍업 중 오류 (계속 진행): {e}")

    async def close_browser(self):
        """브라우저를 종료합니다."""
        if self.browser:
            await self.browser.close()
            print("브라우저를 종료했습니다.")

    async def scrape_search_page(self, keyword: str):
        """
        [v3] 사람처럼 행동하여 주어진 키워드로 쿠팡을 검색하고 상품 목록을 스크레이핑합니다.
        """
        if not self.page:
            return {"status": "error", "reason": "브라우저가 시작되지 않았습니다."}

        print(f"'{keyword}' 키워드로 스크레이핑을 시작합니다...")
        
        import random  # random 모듈 추가
        
        try:
            # 방법 1: 직접 검색 URL로 이동 (아마존)
            import urllib.parse
            encoded_keyword = urllib.parse.quote(keyword)
            search_url = f"https://www.amazon.com/s?k={encoded_keyword}"
            
            print(f"🎯 직접 검색 URL 접속: {search_url}")
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    print(f"📋 검색 페이지 접속 시도 {attempt + 1}/{max_retries}...")
                    # 인간처럼 행동: 더 긴 대기 시간으로 Amazon 차단 우회
                    base_delay = 5 + attempt * 3  # 5초, 8초, 11초... (차단 우회를 위해 증가)
                    random_delay = random.uniform(2, 5)  # 2~5초 랜덤 추가
                    total_delay = base_delay + random_delay
                    print(f"⏱️ Amazon 차단 우회를 위한 대기: {total_delay:.1f}초...")
                    await asyncio.sleep(total_delay)
                    
                    await self.page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
                    
                    # 페이지 로딩 후 추가 대기 (Amazon은 더 빠르게)
                    await asyncio.sleep(2 + attempt)  # 2초, 3초, 4초...
                    print("✅ 검색 페이지 접속 성공!")
                    break
                except Exception as retry_error:
                    print(f"⚠️ 직접 접속 시도 {attempt + 1} 실패: {retry_error}")
                    if attempt == max_retries - 1:
                        print("🔄 더 자연스러운 검색 방식으로 전환합니다...")
                        # 방법 2: 매우 자연스러운 방식 (아마존 메인 페이지 -> 검색)
                        await self.page.goto("https://www.amazon.com/", wait_until='domcontentloaded', timeout=60000)
                        
                        # 홈페이지에서 잠깐 머무르기
                        await asyncio.sleep(random.uniform(3, 6))
                        
                        # 페이지를 조금 스크롤하여 자연스럽게
                        await self.page.evaluate("window.scrollTo(0, Math.random() * 300)")
                        await asyncio.sleep(random.uniform(1, 2))
                        
                        search_input = await self.page.wait_for_selector("input#twotabsearchtextbox", timeout=20000)
                        await search_input.click()
                        
                        # 검색창 클리어하기 전에 잠깐 대기
                        await asyncio.sleep(random.uniform(0.5, 1))
                        await search_input.clear()
                        
                        # 인간처럼 천천히 타이핑 (더 긴 지연)
                        typing_delay = random.randint(80, 150)  # 80-150ms 지연
                        await search_input.type(keyword, delay=typing_delay)
                        
                        # 타이핑 후 잠깐 대기 (사용자가 생각하는 시간)
                        await asyncio.sleep(random.uniform(1, 3))
                        
                        search_button = await self.page.wait_for_selector("input#nav-search-submit-button", timeout=10000)
                        await search_button.click()
                        
                        await self.page.wait_for_load_state('domcontentloaded', timeout=30000)
                        
                        # 검색 결과 로딩 후 추가 대기
                        await asyncio.sleep(random.uniform(4, 7))
                        break
                    await asyncio.sleep(3)  # 재시도 전 대기

        except Exception as e:
            print(f"❌ 스크레이핑 중 오류 발생: {e}")
            return {"status": "error", "reason": f"아마존 페이지와 상호작용하는 중 오류가 발생했습니다: {e}"}

        # 5. Amazon 에러 페이지 감지
        print("🔍 Amazon 에러 페이지 확인 중...")
        page_title = await self.page.title()
        page_url = self.page.url
        
        # Amazon 에러 페이지 감지
        error_indicators = [
            "Sorry! Something went wrong!",
            "503 Service Unavailable", 
            "500 Internal Server Error",
            "Robot Check",
            "captcha"
        ]
        
        page_content = await self.page.content()
        for indicator in error_indicators:
            if indicator.lower() in page_title.lower() or indicator.lower() in page_content.lower():
                print(f"❌ Amazon 에러 페이지 감지: {indicator}")
                return {"status": "error", "reason": f"Amazon이 에러 페이지를 반환했습니다: {indicator}. 키워드를 변경하거나 나중에 다시 시도해주세요."}
        
        # 6. 아마존 페이지 로딩 대기 (아마존은 더 간단)
        print("⏰ 아마존 상품 목록 로딩 대기 중...")
        
        # 아마존 상품 컨테이너 선택자들을 반복 체크
        product_container_selectors = [
            '[data-component-type="s-search-result"]',  # 아마존 검색 결과
            '.s-result-item',  # 아마존 상품 아이템
            '[data-asin]',  # ASIN 속성을 가진 요소
            '.s-card-container',  # 아마존 카드 컨테이너
            '[data-cy="title-recipe-list"] > div',  # 아마존 상품 목록
            '.s-widget-container .s-card-container',  # 상품 위젯 컨테이너
            '[data-cel-widget*="search_result"]',  # 검색 결과 위젯
        ]
        
        # 최대 10초 동안 1초마다 상품이 로드되었는지 확인 (아마존은 더 빠름)
        products_found = False
        for attempt in range(10):
            print(f"  상품 로딩 확인 {attempt + 1}/10...")
            
            for selector in product_container_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    if elements and len(elements) > 0:
                        print(f"✅ 상품 발견! '{selector}' 선택자로 {len(elements)}개 요소 찾음")
                        products_found = True
                        break
                except:
                    continue
            
            if products_found:
                break
                
            await asyncio.sleep(1)  # 1초 대기 후 재시도
        
        if not products_found:
            print("❌ 10초 동안 상품 목록을 찾을 수 없었습니다.")
            
        # 6. 아마존 상품 목록 컨테이너를 찾기 위한 선택자들
        selectors_to_try = [
            # 아마존 검색 결과 컨테이너
            '[data-cy="title-recipe-list"]',  # 아마존 검색 결과 목록
            '.s-search-results',  # 검색 결과 컨테이너
            '[data-component-type="s-search-result"]',  # 검색 결과 컴포넌트
            '.s-widget-container',  # 위젯 컨테이너
            '#search',  # 검색 섹션
            
            # 백업 선택자
            '[cel_widget_id="MAIN-SEARCH_RESULTS"]',  # 메인 검색 결과
            '.s-card-container',  # 카드 컨테이너
            '[data-asin]',  # ASIN 요소들의 부모
        ]
        
        product_list_container = None
        for selector in selectors_to_try:
            try:
                print(f"🔍 선택자 '{selector}' 시도 중...")
                product_list_container = await self.page.query_selector(selector)
                if product_list_container:
                    print(f"✅ 선택자 '{selector}'로 상품 컨테이너를 찾았습니다!")
                    break
                else:
                    print(f"❌ 선택자 '{selector}'로 찾을 수 없음")
            except Exception as e:
                error_msg = str(e)
                if "Target page, context or browser has been closed" in error_msg:
                    print(f"❌ 브라우저가 예기치 않게 종료되었습니다: {e}")
                    return {"status": "error", "reason": "브라우저가 Amazon에 의해 종료되었습니다. 너무 빠른 요청으로 인한 차단으로 보입니다."}
                print(f"⚠️ 선택자 '{selector}' 오류: {e}")
                continue
                
        if not product_list_container:
            try:
                html = await self.page.content()
                with open("error_page.html", "w", encoding="utf-8") as f:
                    f.write(html)
            except Exception as e:
                if "Target page, context or browser has been closed" in str(e):
                    return {"status": "error", "reason": "브라우저가 Amazon에 의해 종료되었습니다. 너무 빠른 요청으로 인한 차단으로 보입니다."}
            return {"status": "error", "reason": "상품 목록 영역을 찾을 수 없습니다. (error_page.html 저장됨)"}

        # Next.js 렌더링된 컨테이너의 HTML 추출
        html = await product_list_container.inner_html()
        soup = BeautifulSoup(html, "html.parser")
        
        # 아마존 구조에서 상품 아이템 패턴 시도
        products = []
        product_selectors = [
            "[data-component-type='s-search-result']",  # 아마존 검색 결과 아이템
            ".s-result-item",  # 검색 결과 아이템
            "[data-asin]",  # ASIN 속성을 가진 요소
            ".s-card-container",  # 카드 컨테이너
            "[data-cel-widget*='search_result']",  # 검색 결과 위젯
            "div[data-cy='title-recipe-list'] > div",  # 상품 목록의 개별 아이템
        ]
        
        for selector in product_selectors:
            products = soup.select(selector)
            if products:
                print(f"✅ '{selector}' 선택자로 {len(products)}개 상품 요소 찾음")
                break
        
        if not products:
            # 디버그: 실제 HTML 구조 저장
            with open("debug_container.html", "w", encoding="utf-8") as f:
                f.write(html[:5000])  # 처음 5000자만 저장
            return {"status": "error", "reason": "상품 목록 영역은 찾았으나, 내부에 개별 상품 요소가 존재하지 않습니다. (debug_container.html 저장됨)"}

        print(f"{len(products)}개의 상품 리스트 아이템을 찾았습니다.")
        scraped_data = []
        import re
        
        for i, product in enumerate(products):
            name, price, product_url = "N/A", 0, ""
            
            # URL 추출 (아마존 패턴)
            url_element = product.find("a", href=True)
            if url_element and url_element.get('href'):
                href = url_element['href']
                product_url = "https://www.amazon.com" + href if href.startswith('/') else href
            
            # 상품명 추출 (아마존 패턴) - 개선된 로직
            name_selectors = [
                "h3.s-size-mini a span",  # 아마존 상품 제목 (가장 정확)
                "[data-cy='title-recipe-list'] h3 a span",  # 아마존 제목
                "h2 a span",  # h2 내의 링크 스팬
                "h3 a span",  # h3 내의 링크 스팬
                ".s-size-mini a span",  # 미니 사이즈 내의 링크 스팬
                "a[aria-label]",  # aria-label이 있는 링크 (백업)
                "img[alt]",  # 이미지 alt 속성 (최후 백업)
            ]
            
            for selector in name_selectors:
                element = product.select_one(selector)
                if element:
                    if element.name == "img" and element.get('alt'):
                        candidate_name = element['alt'].strip()
                    elif element.name == "a" and element.get('aria-label'):
                        candidate_name = element.get('aria-label').strip()
                    else:
                        candidate_name = element.get_text().strip()
                    
                    # 잘못된 텍스트 필터링
                    invalid_texts = [
                        'sponsored', 'best seller', 'amazon\'s choice', 'overall pick',
                        'limited time deal', '#1 best seller', 'climate pledge friendly',
                        'add to cart', 'save', 'coupon', 'free shipping'
                    ]
                    
                    if (candidate_name and 
                        candidate_name != "N/A" and 
                        len(candidate_name) > 10 and  # 최소 길이 확보
                        not any(invalid in candidate_name.lower() for invalid in invalid_texts)):
                        name = candidate_name
                        break
            
            # 가격 추출 (아마존 달러 구조)
            price_selectors = [
                ".a-price-whole",  # 아마존 가격 (정수 부분)
                ".a-price .a-offscreen",  # 아마존 숨겨진 가격
                ".a-price-range",  # 가격 범위
                "[data-cy='price-recipe'] .a-price",  # 가격 레시피
                ".s-price-instructions-style .a-price",  # 가격 지시
                ".a-color-price",  # 가격 색상
                ".a-size-base.a-color-price",  # 기본 가격
            ]
            
            for selector in price_selectors:
                price_element = product.select_one(selector)
                if price_element:
                    price_text = price_element.get_text().strip()
                    # 아마존 달러 가격 패턴: $12.99 또는 12.99
                    price_match = re.search(r'[\$]?([\d,]+\.?\d*)', price_text.replace(',', ''))
                    if price_match:
                        price = float(price_match.group(1))
                        break
            
            # 유효한 데이터만 추가
            if name not in ["N/A", ""] and price > 0 and product_url:
                scraped_data.append({"name": name, "price": price, "url": product_url})
                if len(scraped_data) <= 3:  # 처음 3개만 디버그 출력
                    print(f"  상품 {len(scraped_data)}: {name[:30]}... - {price:,}원")
            elif i < 5:  # 처음 5개 실패 케이스만 디버그 출력
                print(f"  상품 {i+1} 파싱 실패: name='{name[:20]}...' price={price} url='{product_url[:30]}...'")
        
        
        if not scraped_data:
            return {"status": "error", "reason": f"{len(products)}개의 상품 영역을 분석했으나, 유효한 이름과 가격 정보를 가진 상품을 하나도 찾지 못했습니다."}

        print(f"성공적으로 {len(scraped_data)}개의 상품 데이터를 추출했습니다.")
        return {"status": "success", "data": scraped_data}

    async def scrape_product_detail(self, product_url: str):
        """
        개별 상품 페이지에서 상세 정보를 스크레이핑합니다.
        """
        if not self.page:
            raise Exception("브라우저가 시작되지 않았습니다. start_browser()를 먼저 호출하세요.")

        print(f"상품 상세 페이지 스크레이핑을 시작합니다: {product_url}")
        
        try:
            await self.page.goto(product_url, wait_until='domcontentloaded', timeout=15000)
            
            # 페이지 로드 대기
            await asyncio.sleep(2)
            
            html = await self.page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            print("=== 상세 페이지 요소 추출 시작 ===")
            
            # 상품명 (다양한 셀렉터 시도)
            detail_name = "N/A"
            name_selectors = [
                "h1.prod-buy-header__title",
                "h1.prod-title", 
                ".prod-buy-header__title",
                "h1",
                "title"
            ]
            
            for selector in name_selectors:
                name_element = soup.select_one(selector)
                if name_element:
                    if selector == "title":
                        detail_name = name_element.text.strip().split(' - 쿠팡!')[0]
                    else:
                        detail_name = name_element.text.strip()
                    if detail_name and detail_name != "N/A":
                        print(f"상품명 발견 (셀렉터: {selector}): {detail_name[:50]}...")
                        break
            
            # 브랜드 정보
            brand = "N/A"
            brand_selectors = [
                "a.prod-brand-name",
                ".brand-name",
                ".prod-brand",
                "[class*='brand']"
            ]
            
            for selector in brand_selectors:
                brand_element = soup.select_one(selector)
                if brand_element:
                    brand = brand_element.text.strip()
                    if brand and brand != "N/A":
                        print(f"브랜드 발견 (셀렉터: {selector}): {brand}")
                        break
            
            # 판매자 정보  
            seller = "N/A"
            seller_selectors = [
                "a.shop-name",
                ".shop-name",
                ".seller-name",
                "[class*='shop']",
                "[class*='seller']"
            ]
            
            for selector in seller_selectors:
                seller_element = soup.select_one(selector)
                if seller_element:
                    seller = seller_element.text.strip()
                    if seller and seller != "N/A":
                        print(f"판매자 발견 (셀렉터: {selector}): {seller}")
                        break
            
            # Prime 배송 여부 (아마존)
            prime_selectors = [
                ".a-icon-prime",
                "[aria-label*='Prime']",
                "[alt*='Prime']",
                ".s-prime",
                "[class*='prime']"
            ]
            is_prime = False
            for selector in prime_selectors:
                prime_element = soup.select_one(selector)
                if prime_element:
                    is_prime = True
                    print(f"Prime 배송 발견 (셀렉터: {selector})")
                    break
            
            # 평점 정보
            rating = 0.0
            rating_selectors = [
                "span.rating-star-num",
                ".rating-star-num",
                ".rating",
                "[class*='rating']",
                "[class*='star']"
            ]
            
            for selector in rating_selectors:
                rating_element = soup.select_one(selector)
                if rating_element:
                    rating_text = rating_element.text.strip()
                    try:
                        rating = float(rating_text)
                        print(f"평점 발견 (셀렉터: {selector}): {rating}")
                        break
                    except ValueError:
                        continue
            
            # 리뷰 수
            review_count = 0
            review_selectors = [
                "span.count",
                ".count",
                ".review-count", 
                "[class*='review']",
                "[class*='count']"
            ]
            
            for selector in review_selectors:
                review_element = soup.select_one(selector)
                if review_element:
                    review_text = review_element.text.strip().replace("(", "").replace(")", "").replace(",", "")
                    try:
                        review_count = int(''.join(filter(str.isdigit, review_text)))
                        if review_count > 0:
                            print(f"리뷰수 발견 (셀렉터: {selector}): {review_count}")
                            break
                    except ValueError:
                        continue
            
            # 가격 정보
            price = 0
            price_selectors = [
                "span.total-price strong",
                ".total-price strong",
                ".price strong",
                ".price-value",
                "[class*='price']",
                "strong"
            ]
            
            for selector in price_selectors:
                price_element = soup.select_one(selector)
                if price_element:
                    price_text = price_element.text.strip().replace(",", "").replace("원", "")
                    try:
                        price = int(float(price_text))
                        if price > 0:
                            print(f"가격 발견 (셀렉터: {selector}): {price}원")
                            break
                    except ValueError:
                        continue
            
            product_detail = {
                "detail_name": detail_name,
                "brand": brand,
                "seller": seller,
                "is_prime": is_prime,
                "rating": rating,
                "review_count": review_count,
                "price": price,
                "url": product_url
            }
            
            print(f"상품 상세 정보 추출 완료: {detail_name}")
            return product_detail
            
        except Exception as e:
            print(f"상품 상세 페이지 스크레이핑 중 오류 발생: {str(e)}")
            return {
                "detail_name": "ERROR",
                "brand": "N/A",
                "seller": "N/A", 
                "is_prime": False,
                "rating": 0.0,
                "review_count": 0,
                "price": 0,
                "url": product_url
            }

    def save_to_csv(self, products_data, filename=None):
        """
        수집한 상품 데이터를 CSV 파일로 저장합니다.
        analyzer.py와 호환되는 형식으로 변환하여 저장합니다.
        """
        if not products_data:
            print("저장할 데이터가 없습니다.")
            return None

        # 파일명 생성 (기본값: 현재 시간)
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"coupang_products_{timestamp}.csv"
        
        # data 폴더 확인 및 생성
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        os.makedirs(data_dir, exist_ok=True)
        
        filepath = os.path.join(data_dir, filename)
        
        # analyzer.py와 호환되는 CSV 헤더 정의
        fieldnames = [
            'product_id',           # 상품 고유 ID
            'product_title',        # 상품명  
            'product_category',     # 카테고리 (검색 키워드로 대체)
            'discounted_price',     # 할인 가격
            'product_rating',       # 평점
            'total_reviews',        # 리뷰 총 개수
            'purchased_last_month', # 지난달 구매수 (임의값)
            'brand',               # 브랜드
            'seller',              # 판매자
            'is_prime',           # Prime 배송 여부
            'scraped_at'           # 수집 시간
        ]
        
        print(f"CSV 파일로 저장 중: {filepath}")
        
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for i, product in enumerate(products_data):
                # 쿠팡 데이터를 analyzer 호환 형식으로 변환
                converted_data = {
                    'product_id': f"CPG_{i+1:06d}",  # CPG_000001 형식
                    'product_title': product.get('name', product.get('detail_name', 'N/A')),
                    'product_category': '블루투스 이어폰',  # 현재는 고정값, 나중에 파라미터로 변경
                    'discounted_price': product.get('price', 0),
                    'product_rating': product.get('rating', 0.0),
                    'total_reviews': product.get('review_count', 0),
                    'purchased_last_month': max(1, product.get('review_count', 0) // 10),  # 리뷰수의 10% 추정
                    'brand': product.get('brand', 'N/A')[:50] if product.get('brand') != 'N/A' else 'N/A',  # 너무 길면 자르기
                    'seller': product.get('seller', 'N/A')[:50] if product.get('seller') != 'N/A' else 'N/A',
                    'is_prime': 'Y' if product.get('is_prime', False) else 'N',
                    'scraped_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                writer.writerow(converted_data)
        
        print(f"✅ {len(products_data)}개 상품 데이터를 {filename}에 저장완료!")
        return filepath

    def save_to_database(self, products_data, keyword: str):
        """
        수집한 상품 데이터를 SQLite 데이터베이스에 저장합니다 (ORM 사용).
        CSV 방식보다 안전하고 확장성이 좋습니다.
        
        Args:
            products_data: 상품 데이터 리스트
            keyword: 검색에 사용된 키워드
            
        Returns:
            dict: 저장 결과 정보
        """
        if not products_data:
            print("저장할 데이터가 없습니다.")
            return {"success": False, "message": "데이터 없음"}

        print(f"=== SQLite 데이터베이스에 저장 시작 ===")
        
        # 데이터베이스 테이블 생성 (없을 경우)
        db_manager.create_tables()
        
        # 세션 시작
        session = db_manager.get_session()
        session_start_time = datetime.utcnow()
        
        try:
            products_added = 0
            products_skipped = 0
            
            for i, product_data in enumerate(products_data):
                # 고유 상품 ID 생성
                product_id = f"CPG_{session_start_time.strftime('%Y%m%d_%H%M%S')}_{i+1:03d}"
                
                # 중복 체크 (URL 기준)
                product_url = product_data.get('url', '')
                if product_url:
                    existing = session.query(Product).filter_by(product_url=product_url).first()
                    if existing:
                        products_skipped += 1
                        print(f"중복 상품 스킵: {product_data.get('name', 'N/A')[:30]}...")
                        continue
                
                # Product 인스턴스 생성
                product = Product(
                    product_id=product_id,
                    product_title=product_data.get('name', product_data.get('detail_name', 'N/A')),
                    product_category=keyword,  # 검색 키워드를 카테고리로 사용
                    discounted_price=product_data.get('price', 0),
                    product_rating=product_data.get('rating', 0.0),
                    total_reviews=product_data.get('review_count', 0),
                    purchased_last_month=max(1, product_data.get('review_count', 0) // 10),  # 리뷰수의 10% 추정
                    brand=product_data.get('brand') if product_data.get('brand') not in ['N/A', None] else None,
                    seller=product_data.get('seller') if product_data.get('seller') not in ['N/A', None] else None,
                    is_prime=product_data.get('is_prime', False),
                    product_url=product_url,
                    scraped_at=datetime.utcnow()
                )
                
                session.add(product)
                products_added += 1
                print(f"✅ 상품 추가: {product.product_title[:30]}... (ID: {product_id})")
            
            # 스크레이핑 세션 정보 저장
            scraping_session = ScrapingSession(
                keyword=keyword,
                products_found=len(products_data),
                products_saved=products_added,
                session_status='completed' if products_added > 0 else 'partial',
                error_message=f"{products_skipped}개 중복 상품 스킵됨" if products_skipped > 0 else None,
                started_at=session_start_time,
                completed_at=datetime.utcnow()
            )
            session.add(scraping_session)
            
            # 커밋 (트랜잭션 완료)
            session.commit()
            
            result = {
                "success": True,
                "products_added": products_added,
                "products_skipped": products_skipped,
                "total_products_in_db": session.query(Product).count(),
                "message": f"성공적으로 {products_added}개 상품을 데이터베이스에 저장했습니다."
            }
            
            print(f"🎉 데이터베이스 저장 완료!")
            print(f"   - 새로 추가: {products_added}개")
            print(f"   - 중복 스킵: {products_skipped}개") 
            print(f"   - DB 총 상품 수: {result['total_products_in_db']}개")
            
            return result
            
        except Exception as e:
            session.rollback()
            error_message = f"데이터베이스 저장 중 오류 발생: {str(e)}"
            print(f"❌ {error_message}")
            
            # 실패한 스크레이핑 세션도 기록
            try:
                failed_session = ScrapingSession(
                    keyword=keyword,
                    products_found=len(products_data),
                    products_saved=0,
                    session_status='failed',
                    error_message=str(e),
                    started_at=session_start_time,
                    completed_at=datetime.utcnow()
                )
                session.add(failed_session)
                session.commit()
            except:
                pass  # 세션 저장도 실패하면 무시
            
            return {"success": False, "message": error_message}
            
        finally:
            db_manager.close_session(session)

    async def scrape_and_save_to_db(self, keyword: str, max_products: int = 50):
        """
        키워드로 검색하여 상품 데이터를 수집하고 SQLite 데이터베이스에 저장하는 통합 메서드 (ORM 버전)
        """
        print(f"=== '{keyword}' 키워드로 데이터 수집 및 DB 저장 시작 ===")
        
        # 1단계: 검색 결과 페이지에서 기본 상품 정보 수집
        scrape_result = await self.scrape_search_page(keyword)
        
        if scrape_result["status"] == "error":
            print(f"기본 상품 정보 수집에 실패했습니다: {scrape_result['reason']}")
            return {"success": False, "message": scrape_result["reason"]}
            
        products_basic = scrape_result["data"]
        # 상품 수 제한
        products_basic = products_basic[:max_products]
        print(f"{len(products_basic)}개 상품에 대해 상세 정보 수집을 진행합니다...")
        
        # 2단계: 각 상품의 상세 정보 수집 (처음 5개만 테스트)
        detailed_products = []
        for i, product in enumerate(products_basic[:5]):  # 테스트를 위해 5개만
            print(f"[{i+1}/{min(5, len(products_basic))}] 상세 정보 수집 중...")
            detail_info = await self.scrape_product_detail(product['url'])
            
            # 기본 정보와 상세 정보 병합
            merged_product = {**product, **detail_info}
            detailed_products.append(merged_product)
            
            # 요청 간 딜레이 (서버 부하 방지)
            await asyncio.sleep(1)
        
        # 3단계: SQLite 데이터베이스에 저장 (ORM 사용)
        db_result = self.save_to_database(detailed_products, keyword)
        
        print(f"=== 데이터 수집 및 DB 저장 완료! ===")
        print(f"저장 결과: {db_result.get('message', 'Unknown')}")
        
        return db_result

    async def scrape_and_save(self, keyword: str, max_products: int = 50):
        """
        키워드로 검색하여 상품 데이터를 수집하고 CSV로 저장하는 통합 메서드
        """
        print(f"=== '{keyword}' 키워드로 데이터 수집 및 저장 시작 ===")
        
        # 1단계: 검색 결과 페이지에서 기본 상품 정보 수집
        products_basic = await self.scrape_search_page(keyword)
        
        if not products_basic:
            print("기본 상품 정보 수집에 실패했습니다.")
            return None
            
        # 상품 수 제한
        products_basic = products_basic[:max_products]
        print(f"{len(products_basic)}개 상품에 대해 상세 정보 수집을 진행합니다...")
        
        # 2단계: 각 상품의 상세 정보 수집 (처음 5개만 테스트)
        detailed_products = []
        for i, product in enumerate(products_basic[:5]):  # 테스트를 위해 5개만
            print(f"[{i+1}/{min(5, len(products_basic))}] 상세 정보 수집 중...")
            detail_info = await self.scrape_product_detail(product['url'])
            
            # 기본 정보와 상세 정보 병합
            merged_product = {**product, **detail_info}
            detailed_products.append(merged_product)
            
            # 요청 간 딜레이 (서버 부하 방지)
            await asyncio.sleep(1)
        
        # 3단계: CSV 파일로 저장
        csv_filepath = self.save_to_csv(detailed_products, f"{keyword.replace(' ', '_')}_products.csv")
        
        print(f"=== 데이터 수집 및 저장 완료! ===")
        print(f"저장된 파일: {csv_filepath}")
        return csv_filepath

async def main():
    """CoupangScraper의 새로운 ORM 기반 통합 기능을 테스트합니다: 데이터 수집 + SQLite 저장"""
    scraper = CoupangScraper()
    await scraper.start_browser()
    try:
        # 새로운 ORM 기반 통합 메서드 사용: 검색 + 상세정보 수집 + SQLite 저장
        db_result = await scraper.scrape_and_save_to_db("무선마우스", max_products=20)
        
        if db_result and db_result.get('success'):
            print(f"\n🎉 성공적으로 데이터를 수집하고 데이터베이스에 저장했습니다!")
            print(f"📊 저장된 상품 수: {db_result['products_added']}개")
            print(f"📊 전체 DB 상품 수: {db_result['total_products_in_db']}개")
        else:
            print(f"\n❌ 데이터 수집 및 저장에 실패했습니다.")
            print(f"오류 메시지: {db_result.get('message', 'Unknown error') if db_result else 'No result'}")

    finally:
        await scraper.close_browser()

if __name__ == '__main__':
    asyncio.run(main())