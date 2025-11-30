import os
import json
import time
import requests
import google.generativeai as genai
from playwright.sync_api import sync_playwright

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
YOUR_CHANNEL_USERNAME = "peidano"

START_YEAR = 2015
END_YEAR = 2025
TOP_N_MONTHLY = 25
STATE_FILE = "archive_state.json"

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash-lite') 

MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December"
}

def load_state():
    default_state = {"year": START_YEAR, "month": 1, "product_idx": 0, "status": "MONTHLY"}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                content = f.read().strip()
                return json.loads(content) if content else default_state
        except: return default_state
    return default_state

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    try:
        os.system('git config --global user.email "bot@github.com"')
        os.system('git config --global user.name "Archive Bot"')
        os.system(f'git add {STATE_FILE}')
        os.system(f'git commit -m "Update state"')
        os.system('git push')
    except: pass

def generate_content(product_name, original_desc, maker_comment, launch_date):
    print(f"   Generating AI content...", flush=True)
    combined_text = f"Main Description: {original_desc}\n\nMaker's Comment: {maker_comment}"

    prompt_pitch = f"""
    اطلاعات محصول: {combined_text}
    وظیفه: تو سردبیر ارشد کانال Peidano هستی. این محصول را معرفی کن.
    قوانین:
    1. منبع: به متن "Maker's Comment" اولویت بده.
    2. لحن: سوم شخص (دانای کل).
    3. محتوا: چیست؟ چه مشکلی را حل می‌کند؟ چه ویژگی‌هایی دارد؟
    4. طول: 5 تا 15 خط.
    5. زبان: فارسی روان.
    """
    try:
        pitch_res = model.generate_content(prompt_pitch).text.strip()
        time.sleep(2)
    except:
        pitch_res = "توضیحات در دسترس نیست."

    prompt_history = f"""
    محصول: {product_name} ({launch_date})
    توضیحات: {original_desc[:200]}...
    وظیفه: تحلیل کوتاه (3 تا 5 خط) وضعیت فعلی.
    1. با سرچ یا دانش خودت: الان کجاست؟ (فعال/شکست‌خورده/فروخته شده)
    2. مدل درآمدی؟
    3. شروع با: "جمنای: ..."
    """
    try:
        history_res = model.generate_content(prompt_history).text.strip()
        time.sleep(2)
    except:
        history_res = "جمنای: اطلاعات تاریخی دقیقی یافت نشد."
        
    return pitch_res, history_res

def send_to_telegram(data):
    print(f"   Sending to Telegram...", flush=True)
    caption = f"""
🗓️ {data['date_str']}

{data['hashtags']}

**{data['title']}**

{data['pitch_text']}

──────────────
{data['history_text']}
──────────────
**Product Hunt:** [View Page]({data['ph_link']})
**Website:** [Visit Site]({data['website']})
**Channel:** @{YOUR_CHANNEL_USERNAME}
"""
    media = []
    images = data['images'][:10]
    
    if not images:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHANNEL_ID, "text": caption, "parse_mode": "Markdown"})
        return

    for i, img in enumerate(images):
        media_item = {"type": "photo", "media": img}
        if i == 0:
            media_item["caption"] = caption
            media_item["parse_mode"] = "Markdown"
        media.append(media_item)

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMediaGroup"
    requests.post(url, json={"chat_id": CHANNEL_ID, "media": media})

def run_scraper():
    state = load_state()
    current_run_month = state['month']
    
    print(f"🚀 Starting scraper. Target: {state['year']}/{state['month']}", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844}
        )
        page = context.new_page()

        while state['month'] == current_run_month:
            year = state['year']
            month = state['month']
            
            if year >= END_YEAR:
                print("End of years reached.", flush=True)
                break

            url = f"https://www.producthunt.com/leaderboard/monthly/{year}/{month}"
            print(f"📄 Opening: {url}", flush=True)
            
            try:
                page.goto(url, timeout=90000, wait_until="domcontentloaded")
                time.sleep(5)
                print(f"   Page Title: {page.title()}", flush=True)

                for _ in range(5):
                    page.mouse.wheel(0, 3000)
                    time.sleep(1)

                # --- استراتژی تورِ بزرگ (Broad Sweep) ---
                # گرفتن همه لینک‌ها
                all_links = page.locator('a').all()
                print(f"   Total links found: {len(all_links)}", flush=True)

                unique_products = []
                seen_urls = set()
                
                # لیست سیاه لینک‌های منو و ناوبری
                banned_words = ["subscribe", "sign in", "login", "newsletter", "twitter", "facebook", 
                                "instagram", "linkedin", "about", "branding", "jobs", "leaderboard", 
                                "topics", "discussions", "stories", "alternatives", "search"]

                for link in all_links:
                    try:
                        href = link.get_attribute("href")
                        text = link.inner_text().strip()
                        
                        if not href or not text: continue
                        
                        href_lower = href.lower()
                        # فیلتر کردن لینک‌های نامربوط
                        if any(banned in href_lower for banned in banned_words): continue
                        if len(text) < 2 or len(text) > 50: continue # تیتر محصول معمولا بین 2 تا 50 حرفه
                        if href.startswith("/@"): continue # پروفایل کاربرها
                        
                        # لینک محصول باید داخلی باشه (با / شروع شه) و شامل موارد بالا نباشه
                        if href.startswith("/") and not href.startswith("//"):
                            full_url = "https://www.producthunt.com" + href
                            
                            if full_url not in seen_urls:
                                unique_products.append({"url": full_url, "title": text})
                                seen_urls.add(full_url)
                                # چاپ لینک برای دیباگ (که ببینیم چی پیدا کرده)
                                # print(f"Found candidate: {text} -> {full_url}") 
                    except: pass

                # فیلتر نهایی: فقط 25 تای اول که شبیه محصول هستن رو برمیداریم
                # معمولا محصولات بعد از لینک های هدر میان
                items = unique_products[:TOP_N_MONTHLY]
                print(f"   Filtered Candidates: {len(items)}", flush=True)
                
                if not items:
                    print("❌ No items found. Page structure might be very different.", flush=True)
                    break

                current_idx = state['product_idx']
                if current_idx >= len(items):
                    print("   Month finished! Next.", flush=True)
                    state['month'] += 1
                    state['product_idx'] = 0
                    if state['month'] > 12:
                        state['month'] = 1
                        state['year'] += 1
                    save_state(state)
                    break

                item_data = items[current_idx]
                ph_link = item_data['url']
                title = item_data['title']

                print(f"🔍 Processing: {title}", flush=True)

                p_page = context.new_page()
                try:
                    p_page.goto(ph_link, timeout=60000, wait_until="domcontentloaded")
                    time.sleep(3)
                    
                    try: h1 = p_page.locator('h1').first.inner_text(); title = h1 if h1 else title
                    except: pass
                    try: website = p_page.locator('a[data-test="visit-button"]').first.get_attribute("href")
                    except: website = ph_link
                    try: desc = p_page.locator('div[class*="styles_description"]').first.inner_text()
                    except: desc = title
                    
                    hashtags = "#Tech"
                    try:
                        tag_els = p_page.locator('div[class*="styles_topics"] a').all()
                        if tag_els:
                            tags = [t.inner_text() for t in tag_els]
                            hashtags = " ".join([f"#{t.replace(' ', '')}" for t in tags])
                    except: pass

                    maker_comment = ""
                    try:
                        comment_el = p_page.locator('div[class*="styles_commentBody"]').first
                        if comment_el.is_visible(): maker_comment = comment_el.inner_text()
                    except: pass

                    images = []
                    try:
                        img_els = p_page.locator('img[class*="styles_mediaImage"]').all()
                        for img in img_els:
                            src = img.get_attribute("src")
                            if src and "http" in src: images.append(src)
                        images = list(set(images))
                    except: pass
                    
                    p_page.close()

                    date_str = f"{MONTHS[month]} {year}"
                    pitch_text, history_text = generate_content(title, desc, maker_comment, date_str)
                    
                    post_data = {
                        "title": title, "date_str": date_str, "hashtags": hashtags,
                        "pitch_text": pitch_text, "history_text": history_text,
                        "ph_link": ph_link, "website": website, "images": images
                    }
                    
                    send_to_telegram(post_data)
                    print(f"✅ Sent.", flush=True)
                    
                    state['product_idx'] += 1
                    save_state(state)
                    time.sleep(5)

                except Exception as e:
                    print(f"❌ Failed product page: {e}", flush=True)
                    p_page.close()
                    state['product_idx'] += 1
                    save_state(state)

            except Exception as e:
                print(f"❌ Error loading monthly page: {e}", flush=True)
                time.sleep(10)
                break 

if __name__ == "__main__":
    run_scraper()
