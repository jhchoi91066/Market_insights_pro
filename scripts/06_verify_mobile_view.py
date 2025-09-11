# -*- coding: utf-8 -*-
"""
모바일 브라우저 뷰를 검증하는 테스트 스크립트.
Playwright를 사용하여 iPhone 13 환경을 에뮬레이션하고, 주요 페이지의 스크린샷을 캡처합니다.
"""
import asyncio
import os
from playwright.async_api import async_playwright, expect

# 테스트 설정
BASE_URL = "http://localhost:8000"
DEVICE_TO_EMULATE = "iPhone 13"

async def main():
    print(f"🚀 모바일 뷰 검증 시작 (에뮬레이션 기기: {DEVICE_TO_EMULATE})")
    
    async with async_playwright() as p:
        iphone = p.devices[DEVICE_TO_EMULATE]
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(**iphone, locale="en-US")
        page = await context.new_page()

        try:
            # 1. 메인 페이지 접속 및 스크린샷
            print(f"[1/4] 메인 페이지 접속: {BASE_URL}")
            await page.goto(BASE_URL, wait_until="networkidle")
            
            await expect(page).to_have_title("Amazon Market Insights Pro")
            print("✅ 메인 페이지 제목 확인 완료")
            
            screenshot_path_index = "mobile_index_view.png"
            await page.screenshot(path=screenshot_path_index, full_page=True)
            print(f"📸 메인 페이지 스크린샷 저장 완료: {screenshot_path_index}")

            # 2. 키워드 분석 실행
            print("[2/4] 'wireless mouse' 키워드로 분석 시작...")
            await page.get_by_placeholder("Enter keyword...").fill("wireless mouse")
            await page.get_by_role("button", name="Start Market Analysis").click()
            
            await expect(page.locator("#loader")).to_be_visible()
            print("✅ 로딩 화면 표시 확인")
            
            print("⏳ 분석 완료 및 리포트 페이지 로딩 대기 중... (최대 2분)")
            await expect(page).to_have_url(f"{BASE_URL}/report?keyword=wireless%20mouse", timeout=120000)
            await page.wait_for_load_state("networkidle")
            print("✅ 리포트 페이지 로딩 완료")

            # 3. 리포트 페이지 스크린샷
            print("[3/4] 리포트 페이지 스크린샷 생성...")
            await expect(page.get_by_text("Market Analysis")).to_be_visible()
            
            await page.wait_for_timeout(1000)
            
            screenshot_path_report = "mobile_report_view.png"
            await page.screenshot(path=screenshot_path_report, full_page=True)
            print(f"📸 리포트 페이지 스크린샷 저장 완료: {screenshot_path_report}")
            
            # 4. 최종 검증
            print("[4/4] 최종 결과 검증...")
            entry_barrier_score = await page.locator(".stat-value").first.inner_text()
            print(f"📈 시장 진입 장벽 점수: {entry_barrier_score}")
            assert entry_barrier_score is not None, "시장 진입 장벽 점수를 찾을 수 없습니다."
            
            print("\n🎉 모바일 뷰 검증 테스트 성공!")
            print(f"👉 다음 파일들을 확인하여 UI가 올바르게 표시되는지 검토해주세요:")
            print(f"   - {os.path.abspath(screenshot_path_index)}")
            print(f"   - {os.path.abspath(screenshot_path_report)}")

        except Exception as e:
            print(f"❌ 테스트 실패: {e}")
            await page.screenshot(path="mobile_test_failure.png")
            print("📸 실패 시점의 스크린샷을 'mobile_test_failure.png'로 저장했습니다.")
        
        finally:
            await context.close()
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())