import os
from playwright.sync_api import sync_playwright

def debug_page():
    print("🚀 Starting DEBUG Mode...", flush=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        url = "https://www.producthunt.com/leaderboard/monthly/2015/1"
        print(f"📄 Opening: {url}", flush=True)
        
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000) # 5 ثانیه صبر مطلق
        
        print(f"✅ Page Title: {page.title()}", flush=True)
        
        # چاپ تمام لینک‌های صفحه برای بررسی ساختار
        links = page.locator('a').all()
        print(f"📊 Total links found on page: {len(links)}", flush=True)
        
        print("\n--- FIRST 20 LINKS SEEN BY ROBOT ---")
        for i, link in enumerate(links[:20]):
            try:
                href = link.get_attribute("href")
                text = link.inner_text().replace('\n', ' ')
                print(f"[{i}] Text: '{text}' | Link: '{href}'", flush=True)
            except: pass
        print("------------------------------------\n")
        
        # چک کردن HTML خالص
        content = page.content()
        if "styles_item" in content:
            print("✅ 'styles_item' class FOUND in HTML.")
        else:
            print("❌ 'styles_item' class NOT FOUND in HTML.")

        browser.close()

if __name__ == "__main__":
    debug_page()
