"""
TELEGRAM_API_ID / TELEGRAM_API_HASH without the owner visiting my.telegram.org.

my.telegram.org signs in with the phone number and a code that Telegram sends inside the Telegram app
(not by SMS). The code is asked through the same window as every other sign-in, then the developer
app is created if the account has none, and its api_id / api_hash are written to .env.

    fetch(phone, ask)  → (api_id, api_hash)      ask(prompt) returns what the person typed
"""

import html
import re

import requests

BASE = "https://my.telegram.org"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "X-Requested-With": "XMLHttpRequest"}


def _keys(page):
    api_id = re.search(r"App api_id:.*?<strong>\s*(\d+)\s*</strong>", page, re.S)
    api_hash = re.search(r"App api_hash:.*?>\s*([0-9a-f]{32})\s*<", page, re.S)
    return (api_id.group(1), api_hash.group(1)) if api_id and api_hash else (None, None)


def fetch(phone, ask, say=print):
    s = requests.Session()
    s.headers.update(UA)
    r = s.post(f"{BASE}/auth/send_password", data={"phone": phone}, timeout=30)
    if "too many" in r.text.lower():
        raise RuntimeError("my.telegram.org می‌گوید درخواست‌ها زیاد بوده؛ چند ساعت بعد دوباره «ورود» را بزنید.")
    try:
        rnd = r.json()["random_hash"]
    except (ValueError, KeyError):
        raise RuntimeError(f"my.telegram.org کد نفرستاد: {r.text[:120]}")
    say("کد my.telegram.org در خود اپ تلگرامِ همین شماره آمد (پیام از طرف «Telegram»)، نه پیامک.")
    code = ask("کد تلگرام برای ساخت کلید (پیام «Telegram» در اپ؛ یک رشته‌ی کوتاه حرف و عدد)").strip()
    r = s.post(f"{BASE}/auth/login", data={"phone": phone, "random_hash": rnd, "password": code}, timeout=30)
    if r.text.strip() != "true":
        raise RuntimeError("کد my.telegram.org پذیرفته نشد؛ دوباره «ورود» را بزنید و کد تازه را دقیق وارد کنید.")
    page = s.get(f"{BASE}/apps", timeout=30).text
    api_id, api_hash = _keys(page)
    if not api_id:
        h = re.search(r'name="hash"\s+value="([^"]+)"', page)
        if not h:
            raise RuntimeError("صفحه‌ی ساخت اپ در my.telegram.org باز نشد.")
        say("ساخت اپ تلگرام برای سپاهان فلز…")
        r = s.post(f"{BASE}/apps/create", timeout=30, data={
            "hash": h.group(1), "app_title": "SepahanFelez Publisher", "app_shortname": "sepahanfelezpub",
            "app_url": "https://sepahanfelez.ir", "app_platform": "desktop",
            "app_desc": "Publishing stories and channel posts for Sepahan Felez"})
        if r.text.strip().upper().startswith("ERROR"):
            raise RuntimeError("تلگرام ساخت اپ را رد کرد (ERROR). این خطا معمولاً موقتی است؛ چند ساعت بعد دوباره «ورود» را بزنید.")
        api_id, api_hash = _keys(s.get(f"{BASE}/apps", timeout=30).text)
    if not api_id:
        raise RuntimeError("کلیدها در صفحه‌ی my.telegram.org پیدا نشد.")
    try:
        s.get(f"{BASE}/auth/logout", timeout=15)
    except requests.RequestException:
        pass
    return api_id, html.unescape(api_hash)
