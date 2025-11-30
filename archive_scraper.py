import os
import json
import time
import requests
import google.generativeai as genai
from playwright.sync_api import sync_playwright

# --- تنظیمات ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
YOUR_CHANNEL_USERNAME = "peidano"

# تنظیمات اسکرپینگ
START_YEAR = 2015
END_YEAR = 2025
TOP_N_MONTHLY = 25 # 25 محصول برتر ماه
MAX_POSTS_PER_RUN = 30 # در هر بار اجرا 30 تا پست بذاره و خاموش شه (برای ایمنی)
STATE_FILE = "archive_state.json"

# تنظیم جمنای
genai.configure(api_key=GEMINI_API_KEY)
# مدل استاندارد (ابزار سرچ رو در پرامپت هندل میکنیم چون ممکنه روی اکانت رایگان محدودیت تولز باشه)
model = genai.GenerativeModel('gemini-2.0-flash-lite') 

# لیست ماه‌ها
MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December"
}

def load_state():
    """لود کردن وضعیت قبلی"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    # شروع از اول
    return {"year": START_YEAR, "month": 1, "product_idx": 0, "status": "MONTHLY"}

def save_state(state):
    """ذخیره وضعیت و کامیت به گیت‌هاب"""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    
    # دستورات گیت برای ذخیره در مخزن
    os.system('git config --global user.email "bot@github.com"')
    os.system('git config --global user.name "Archive Bot"')
    os.system(f'git add {STATE_FILE}')
    os.system(f'git commit -m "Update state: {state["year"]}-{state["month"]}"')
    os.system('git push')

def generate_content(product_name, original_desc, launch_date):
    """
    تولید محتوا با دو وظیفه: 1. خلاصه فاندر 2. تحلیل تاریخی
    """
    # 1. خلاصه سازی توضیحات فاندر
    prompt_pitch = f"""
    متن اصلی محصول: "{original_desc}"
    
    وظیفه: این متن را به فارسی روان بازنویسی کن.
    - بر روی **نوآوری و مشکلی که حل می‌کند** تمرکز کن.
    - طول متن: 5 تا 15 خط.
    - اگر متن کوتاه است، کوتاه بنویس.
    - لحن: جذاب و تکنولوژیک.
    """
    try:
        pitch_res = model.generate_content(prompt_pitch).text.strip()
    except:
        pitch_res = "توضیحات در دسترس نیست."

    # 2. تحلیل تاریخی و سرچ
    # (به هوش مصنوعی میگوییم با دانش خودش و جستجو پاسخ دهد)
    prompt_history = f"""
    محصول: {product_name}
    تاریخ عرضه: {launch_date}
    توضیحات: {original_desc[:200]}...

    وظیفه: به عنوان یک کارشناس استارتاپ، یک تحلیل کوتاه (3 تا 5 خط) درباره سرنوشت این محصول بنویس.
    1. الان این محصول کجاست؟ (فعال، شکست‌خورده، خریداری شده توسط شرکت دیگر؟)
    2. مدل درآمدی‌اش چیست؟
    3. اطلاعات بخش توضیحات را تکرار نکن.
    4. شروع جمله با: "جمنای: ..."
    """
    try:
        # مکث کوتاه برای عدم تداخل
        time.sleep(2)
        history_res = model.generate_content(prompt_history).text.strip()
    except:
        history_res = "جمنای: اطلاعات تاریخی دقیقی یافت نشد."
        
    return pitch_res, history_res

def send_to_telegram(data):
    """ارسال آلبوم عکس به تلگرام"""
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
    # آماده سازی مدیا گروپ (آلبوم)
    media = []
    
    # اگر عکسی پیدا نشد، یک عکس پیشفرض یا لوگو بفرستیم (اختیاری)
    # اینجا فرض میکنیم عکس هست.
    
    images = data['images'][:10] # فقط 10 تا
    
    if not images:
        # ارسال تک پیام متنی اگر عکس نبود
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHANNEL_ID, "text": caption, "parse_mode": "Markdown"})
        return

    for i, img in enumerate(images):
        media_item = {"type": "photo", "media": img}
        if i == 0: # کپشن فقط روی عکس اول
            media_item["caption"] = caption
            media_item["parse_mode"] = "Markdown"
        media.append(media_item)

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMediaGroup"
    requests.post(url, json={"chat_id": CHANNEL_ID, "media": media})

def run_scraper():
    state = load_state()
    posts_sent = 0
    
    print(f"🚀 Starting scraper from: {state['year']} - {MONTHS[state['month']]}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        while posts_sent < MAX_POSTS_PER_RUN:
            year = state['year']
            month = state['month']
            
            if year >= END_YEAR:
                print("✅ Archive Complete!")
                break

            # ساخت آدرس ماهانه
            url = f"https://www.producthunt.com/leaderboard/monthly/{year}/{month}/all"
            print(f"📄 Loading List: {url}")
            
            try:
                page.goto(url, timeout=60000)
                page.wait_for_selector('div[class*="styles_item__"]', timeout=10000) # صبر برای لود لیست
                
                # اسکرول برای لود شدن آیتم‌های پایین (lazy load)
                for _ in range(5):
                    page.mouse.wheel(0, 1000)
                    time.sleep(1)

                # پیدا کردن تمام آیتم‌های لیست
                # سلکتورهای PH مدام عوض میشن، سعی میکنیم جنرال پیدا کنیم
                items = page.locator('div[class*="styles_item__"]').all()
                
                # فیلتر کردن Top 25
                items = items[:TOP_N_MONTHLY]
                
                current_idx = state['product_idx']
                
                if current_idx >= len(items):
                    # رفتن به ماه بعد
                    print("Month finished. Moving to next month.")
                    state['month'] += 1
                    state['product_idx'] = 0
                    if state['month'] > 12:
                        state['month'] = 1
                        state['year'] += 1
                    save_state(state)
                    continue

                # پردازش محصول فعلی
                item = items[current_idx]
                
                # استخراج اطلاعات از لیست (تگ‌ها اینجان)
                try:
                    title_el = item.locator('a[class*="styles_title__"]').first
                    title = title_el.inner_text()
                    ph_link = "https://www.producthunt.com" + title_el.get_attribute("href")
                    
                    # تگ‌ها
                    tag_els = item.locator('a[class*="styles_topic__"]').all()
                    tags = [t.inner_text() for t in tag_els]
                    hashtags = " ".join([f"#{t.replace(' ', '')}" for t in tags])
                    
                except Exception as e:
                    print(f"Error extracting list item: {e}")
                    state['product_idx'] += 1
                    continue

                print(f"🔍 Processing: {title}")
                
                # --- ورود به صفحه محصول ---
                p_page = browser.new_page()
                try:
                    p_page.goto(ph_link, timeout=60000)
                    time.sleep(3) # صبر برای لود عکس‌ها
                    
                    # استخراج لینک سایت اصلی
                    try:
                        website = p_page.locator('a[data-test="visit-button"]').first.get_attribute("href")
                    except:
                        website = ph_link

                    # استخراج توضیحات
                    try:
                        desc = p_page.locator('div[class*="styles_description__"]').first.inner_text()
                    except:
                        desc = title

                    # استخراج عکس‌ها (گالری)
                    images = []
                    try:
                        img_els = p_page.locator('img[class*="styles_mediaImage__"]').all()
                        for img in img_els:
                            src = img.get_attribute("src")
                            if src and "http" in src:
                                images.append(src)
                        # حذف تکراری‌ها و فیلتر
                        images = list(set(images))
                    except: pass
                    
                    p_page.close()

                    # تولید محتوا با هوش مصنوعی
                    date_str = f"{MONTHS[month]} {year}"
                    pitch_text, history_text = generate_content(title, desc, date_str)
                    
                    # ارسال به تلگرام
                    post_data = {
                        "title": title,
                        "date_str": date_str,
                        "hashtags": hashtags,
                        "pitch_text": pitch_text,
                        "history_text": history_text,
                        "ph_link": ph_link,
                        "website": website,
                        "images": images
                    }
                    
                    send_to_telegram(post_data)
                    print(f"✅ Sent: {title}")
                    
                    posts_sent += 1
                    state['product_idx'] += 1
                    save_state(state) # ذخیره بعد از هر پست موفق
                    
                    time.sleep(5) # استراحت

                except Exception as e:
                    print(f"Failed to process product page: {e}")
                    p_page.close()
                    state['product_idx'] += 1 # رد کردن محصول خراب
                    save_state(state)

            except Exception as e:
                print(f"Error loading monthly page: {e}")
                time.sleep(10)

    print("Run finished.")

if __name__ == "__main__":
    run_scraper()
