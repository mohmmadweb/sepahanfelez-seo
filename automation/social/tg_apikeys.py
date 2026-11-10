"""
TELEGRAM_API_ID / TELEGRAM_API_HASH without the owner visiting my.telegram.org.

my.telegram.org signs in with the phone number and a code that Telegram sends inside the Telegram app
(not by SMS). The code is asked through the same window as every other sign-in, then the developer
app is created if the account has none, and its api_id / api_hash are written to .env.

    fetch(phone, ask)  → (api_id, api_hash)      ask(prompt) returns what the person typed
"""

import html
import os
import re

import requests

BASE = "https://my.telegram.org"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
XHR = {"X-Requested-With": "XMLHttpRequest", "Origin": BASE, "Referer": BASE + "/apps"}   # only on the form posts
DEBUG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     "dashboard", "data", "tg_apikeys_debug")


def _keys(page):
    text = re.sub(r"<[^>]+>", " ", page)
    api_id = re.search(r"api_id\s*:?\s*(\d{5,12})", text)
    api_hash = re.search(r"api_hash\s*:?\s*([0-9a-f]{32})", text)
    return (api_id.group(1), api_hash.group(1)) if api_id and api_hash else (None, None)


def _keep(name, text):
    """What my.telegram.org answered, kept privately on the server when something does not match."""
    os.makedirs(DEBUG, mode=0o700, exist_ok=True)
    path = os.path.join(DEBUG, name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text or "")
    return path


def fetch(phone, ask, say=print):
    s = requests.Session()
    s.headers.update(UA)
    r = s.post(f"{BASE}/auth/send_password", data={"phone": phone}, headers=XHR, timeout=30)
    if "too many" in r.text.lower():
        raise RuntimeError("my.telegram.org می‌گوید درخواست‌ها زیاد بوده؛ چند ساعت بعد دوباره «ورود» را بزنید.")
    try:
        rnd = r.json()["random_hash"]
    except (ValueError, KeyError):
        raise RuntimeError(f"my.telegram.org کد نفرستاد: {r.text[:120]}")
    say("کد my.telegram.org در خود اپ تلگرامِ همین شماره آمد (پیام از طرف «Telegram»)، نه پیامک.")
    code = ask("کد تلگرام برای ساخت کلید (پیام «Telegram» در اپ؛ یک رشته‌ی کوتاه حرف و عدد)").strip()
    r = s.post(f"{BASE}/auth/login", data={"phone": phone, "random_hash": rnd, "password": code}, headers=XHR, timeout=30)
    if r.text.strip() != "true":
        raise RuntimeError("کد my.telegram.org پذیرفته نشد؛ دوباره «ورود» را بزنید و کد تازه را دقیق وارد کنید.")
    page = s.get(f"{BASE}/apps", timeout=30).text
    _keep("apps-1.html", page)
    api_id, api_hash = _keys(page)
    created = ""
    if not api_id:
        h = re.search(r'name="hash"\s+value="([^"]+)"', page) or re.search(r"hash\s*[:=]\s*['\"]([0-9a-f]{8,})['\"]", page)
        if not h:
            raise RuntimeError("صفحه‌ی ساخت اپ در my.telegram.org باز نشد (پاسخ در سرور ذخیره شد).")
        say("ساخت اپ تلگرام برای سپاهان فلز…")
        r = s.post(f"{BASE}/apps/create", headers=XHR, timeout=30, data={
            "hash": h.group(1), "app_title": "SepahanFelez Publisher", "app_shortname": "sepahanfelezpub",
            "app_url": "https://sepahanfelez.ir", "app_platform": "desktop",
            "app_desc": "Publishing stories and channel posts for Sepahan Felez"})
        created = r.text.strip()
        _keep("create.txt", f"HTTP {r.status_code}\n{created}")
        if created.upper().startswith("ERROR"):
            raise RuntimeError("تلگرام ساخت اپ را رد کرد (ERROR). این خطای معروف my.telegram.org معمولاً موقتی است؛ "
                               "چند ساعت بعد دوباره «ورود» را بزنید.")
        page = s.get(f"{BASE}/apps", timeout=30).text
        _keep("apps-2.html", page)
        api_id, api_hash = _keys(page)
    if not api_id:
        raise RuntimeError("کلیدها در صفحه‌ی my.telegram.org پیدا نشد" +
                           (f" (پاسخ ساخت اپ: «{re.sub(r'<[^>]+>', ' ', created)[:120].strip()}»)" if created else "") +
                           " — پاسخ‌ها در سرور ذخیره شد تا بررسی شود.")
    try:
        s.get(f"{BASE}/auth/logout", timeout=15)
    except requests.RequestException:
        pass
    return api_id, html.unescape(api_hash)
