import os
import json
import time
import requests
import google.generativeai as genai
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

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
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except: pass
    return {"year": START_YEAR, "month": 1, "product_idx": 0, "status": "MONTHLY"}

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
    print(f"   Generating AI content for {product_name}...", flush=True)
    combined_text = f"Product: {product_name}\nDescription: {original_desc}\nMaker Comment: {maker_comment}"

    prompt_pitch = f"""
    اطلاعات محصول:
    {combined_text}
    
    وظیفه: تو سردبیر ارشد کانال Peidano هستی. این محصول را معرفی کن.
    قوانین:
    1. لحن راوی: سوم شخص (دانای کل).
    2. محتوا: چیست؟ چه مشکلی را حل می‌کند؟
    3. اگر متن ورودی ناقص است، بر اساس نام محصول و توضیحات کوتاه، حدس بزن کارش چیست (اما دروغ نگو).
    4. طول: 5 تا 10 خط.
    5. زبان: فارسی روان.
    """
    try:
        pitch_res = model.generate_content(prompt_pitch).text.strip()
        time.sleep(2)
    except: pitch_res = "توضیحات در دسترس نیست."

    prompt_history = f"""
    محصول: {product_name} ({launch_date})
    توضیحات: {original_desc[:300]}...
    وظیفه: تحلیل کوتاه (3 تا 5 خط) وضعیت فعلی.
    1. با سرچ یا دانش خودت: الان کجاست؟ (فعال/شکست‌خورده/فروخته شده)
    2. مدل درآمدی؟
    3. شروع با: "جمنای: ..."
    """
    try:
        history_res = model.generate_content(prompt_history).text.strip()
        time.sleep(2)
    except: history_res = "جمنای: اطلاعات تاریخی یافت نشد."
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
    
    print(f"🚀 Starting scraper. Target: {state['year']}/{state['month']} - Start Index: {state['product_idx']}", flush=True)

    with sync_playwright() as p:
        # مرورگر برای گرفتن سورس HTML
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        page = browser.new_page()

        while state['month'] == current_run_month:
            year = state['year']
            month = state['month']
            if year >= END_YEAR: break

            url = f"https://www.producthunt.com/leaderboard/monthly/{year}/{month}"
            print(f"📄 Opening List: {url}", flush=True)
            
            try:
                page.goto(url, timeout=60000, wait_until="commit") # فقط صبر برای اتصال اولیه
                time.sleep(5) # کمی صبر برای رندر اولیه
                
                # دریافت HTML کامل لیست
                list_html = page.content()
                soup = BeautifulSoup(list_html, 'html.parser')

                # پیدا کردن آیتم‌ها (روش data-test که در فایل شما بود)
                items = soup.select('[data-test^="post-item-"]')
                
                # فال‌بک به لینک‌ها اگر data-test نبود
                if not items:
                    print("⚠️ data-test not found. Fallback to links.", flush=True)
                    links = soup.find_all('a', href=True)
                    valid_items = []
                    seen = set()
                    for link in links:
                        href = link['href']
                        if ("/posts/" in href or "/products/" in href) and "#" not in href:
                            full = "https://www.producthunt.com" + href if href.startswith("/") else href
                            if full not in seen:
                                valid_items.append({"url": full, "element": link})
                                seen.add(full)
                    items = valid_items
                else:
                    # تبدیل data-test ها به فرمت استاندارد
                    parsed_items = []
                    for item in items:
                        link_tag = item.find('a', href=True)
                        if link_tag:
                            href = link_tag['href']
                            full = "https://www.producthunt.com" + href if href.startswith("/") else href
                            parsed_items.append({"url": full, "element": item})
                    items = parsed_items

                items = items[:TOP_N_MONTHLY]
                print(f"   Found {len(items)} products.", flush=True)
                
                if not items:
                    print("❌ No items found. Skipping month.", flush=True)
                    state['month'] += 1
                    if state['month'] > 12:
                        state['month'] = 1
                        state['year'] += 1
                    save_state(state)
                    break

                # --- پردازش محصول تکی ---
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
                
                # تمیز کردن تیتر از لیست
                raw_title = item_data['element'].get_text(separator=" ", strip=True)
                # معمولا تیتر بخش اول متنه
                title = raw_title.split("  ")[0] if "  " in raw_title else raw_title[:30] 

                print(f"🔍 Processing: {title} ({ph_link})", flush=True)

                # --- باز کردن صفحه جزئیات (فقط برای گرفتن HTML) ---
                page.goto(ph_link, timeout=60000, wait_until="commit")
                time.sleep(4)
                detail_html = page.content()
                detail_soup = BeautifulSoup(detail_html, 'html.parser')

                # 1. استخراج تیتر دقیق (h1)
                h1 = detail_soup.find('h1')
                if h1: title = h1.get_text(strip=True)

                # 2. استخراج وبسایت
                website = ph_link
                visit_btn = detail_soup.find('a', attrs={'data-test': 'visit-button'})
                if visit_btn: website = visit_btn.get('href')

                # 3. استخراج توضیحات
                desc = title
                # تلاش برای پیدا کردن متای توضیحات
                meta_desc = detail_soup.find('meta', attrs={'name': 'description'})
                if meta_desc: 
                    desc = meta_desc.get('content')
                else:
                    # تلاش برای پیدا کردن متن بدنه
                    desc_div = detail_soup.find('div', class_=lambda x: x and 'description' in x)
                    if desc_div: desc = desc_div.get_text(strip=True)

                # 4. استخراج کامنت سازنده
                maker_comment = ""
                comment_div = detail_soup.find('div', class_=lambda x: x and 'commentBody' in x)
                if comment_div: maker_comment = comment_div.get_text(strip=True)

                # 5. استخراج عکس‌ها
                images = []
                # همه عکس‌های صفحه که سورس معتبر دارند
                img_tags = detail_soup.find_all('img')
                for img in img_tags:
                    src = img.get('src') or img.get('srcset')
                    if src and "http" in src and "avatar" not in src and "logo" not in src:
                        # فیلتر کردن عکس‌های خیلی کوچک (آیکون‌ها)
                        if "width" in img.attrs and int(img['width']) > 100:
                             images.append(src.split(' ')[0]) # هندل کردن srcset
                        elif "media" in str(img.parent): # عکس‌های داخل گالری معمولا توی مدیا هستن
                             images.append(src.split(' ')[0])
                
                # حذف تکراری
                images = list(set(images))
                if not images: # اگر عکسی پیدا نشد، عکس اوجی (OG Image) رو بگیر
                    og_img = detail_soup.find('meta', property='og:image')
                    if og_img: images.append(og_img['content'])

                hashtags = "#Tech" # تگ پیشفرض
                
                # تولید و ارسال
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
                print(f"❌ Error processing item: {e}", flush=True)
                # رد کردن آیتم خراب برای جلوگیری از گیر کردن
                state['product_idx'] += 1
                save_state(state)
                time.sleep(5)

if __name__ == "__main__":
    run_scraper()
