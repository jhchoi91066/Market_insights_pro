
import asyncio
import subprocess
import time
from playwright.async_api import async_playwright, expect

async def main():
    process = None
    try:
        # 1. Start the FastAPI server
        print("Starting FastAPI server...")
        process = subprocess.Popen(["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"])
        # Give the server a moment to start
        await asyncio.sleep(5)

        async with async_playwright() as p:
            # 2. Launch browser and go to the report page
            browser = await p.chromium.launch()
            page = await browser.new_page()
            
            console_logs = []
            page.on("console", lambda msg: console_logs.append(msg.text))

            print("Navigating to report page...")
            await page.goto("http://127.0.0.1:8000/report?keyword=블루투스 이어폰", wait_until="networkidle")

            # 3. Change the sort order
            print("Changing sort order to 'Price (High to Low)'...")
            await page.select_option("#sort-select", "numeric_price_desc")

            # 4. Wait for the sorting to be logged
            print("Waiting for sort log message...")
            
            log_found = False
            for _ in range(10): # Wait up to 5 seconds
                if any("Sorting by: numeric_price_desc" in log for log in console_logs):
                    log_found = True
                    print("✔ Sort log message found!")
                    break
                await asyncio.sleep(0.5)
            
            if not log_found:
                print("❌ Test Failed: Did not find the expected console log for sorting.")
                print("Captured logs:", console_logs)
                await browser.close()
                return

            # 5. Verify the table is sorted correctly
            print("Verifying table order...")
            await asyncio.sleep(1) # Wait for DOM to update

            prices = await page.locator("#products-table-body tr > td:nth-child(3)").all_text_contents()
            
            if len(prices) < 2:
                print(f"⚠️ Not enough products to compare sorting ({len(prices)} found). Test partially successful.")
            else:
                price1_str = prices[0].replace('$', '').replace(',', '')
                price2_str = prices[1].replace('$', '').replace(',', '')
                
                price1 = float(price1_str)
                price2 = float(price2_str)

                print(f"First product price: {price1}, Second product price: {price2}")

                if price1 >= price2:
                    print("✔ Test Passed: Products are sorted correctly by price (High to Low).")
                else:
                    print(f"❌ Test Failed: Products are not sorted correctly. {price1} is not >= {price2}")

            await browser.close()

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if process:
            print("Stopping FastAPI server...")
            process.terminate()
            process.wait()

if __name__ == "__main__":
    asyncio.run(main())
