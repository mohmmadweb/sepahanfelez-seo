#!/usr/bin/env python3
"""
One clean login per network, kept as a persistent session on this server.

    automation/social/login.sh status              # who is logged in (also feeds the dashboard)
    automation/social/login.sh login eitaa         # eitaa | bale | rubika | whatsapp | telegram | instagram
    automation/social/login.sh logout eitaa

Run it yourself in the terminal: the verification code arrives on your phone and you
type it here, so it never passes through chat. Sessions live in automation/sessions/
(chmod 700, gitignored). Phone numbers, usernames and passwords come only from .env.

Web messengers (Eitaa, Bale, Rubika, WhatsApp) run in a headless Chromium profile — the
same thing as a browser tab left logged in. Telegram uses its official client API
(Telethon, needs TELEGRAM_API_ID/HASH). Instagram uses one fixed device session so the
account never looks like it is logging in from a new phone every day.
"""

import getpass
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "dashboard"))
from sf.env import get, load_env  # noqa: E402

load_env()
SESSIONS = os.path.join(ROOT, "automation", "sessions")
STATUS_FILE = os.path.join(ROOT, "dashboard", "data", "social_status.json")
TEHRAN = timezone(timedelta(hours=3, minutes=30))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")

WEB = {
    "eitaa": {"url": "https://web.eitaa.com/", "fa": "ایتا", "phone_env": "EITAA_PHONE", "locale": "fa-IR",
              "login_marker": ".input-field-phone", "ok_markers": [".chatlist", "#column-left .sidebar-header"]},
    "rubika": {"url": "https://web.rubika.ir/", "fa": "روبیکا", "phone_env": "RUBIKA_PHONE", "locale": "fa-IR",
               "login_marker": "input[name=phone_number]", "ok_markers": [".chatlist", "#column-left .sidebar-header"]},
    "bale": {"url": "https://web.bale.ai/", "fa": "بله", "phone_env": "BALE_PHONE", "locale": "en-US",
             "login_marker": "input[inputmode=numeric]", "ok_markers": ["body"], "login_url": "/login"},
    "whatsapp": {"url": "https://web.whatsapp.com/", "fa": "واتساپ", "phone_env": "WHATSAPP_PHONE", "locale": "en-US",
                 "login_marker": "canvas, [data-ref]", "ok_markers": ["#pane-side", "div[aria-label='Chat list']"]},
}
ALL = list(WEB) + ["telegram", "instagram"]


class TerminalIO:
    """How a login flow talks to a human. The web UI swaps in a queue-backed version."""
    def say(self, msg):
        print(msg, flush=True)

    def ask(self, prompt, secret=False):
        return (getpass.getpass(prompt) if secret else input(prompt)).strip()

    def link_code(self, code, how):
        self.say(how)
        self.say(f"  کد:  {code}")


IO = TerminalIO()


def say(msg):
    IO.say(msg)


def profile_dir(net):
    os.makedirs(SESSIONS, mode=0o700, exist_ok=True)
    os.chmod(SESSIONS, 0o700)
    d = os.path.join(SESSIONS, net)
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def local_phone(phone):
    """+989133006030 → 9133006030 (forms that already show +98)."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("98"):
        digits = digits[2:]
    return digits.lstrip("0")


def save_status(net, ok, detail=""):
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    try:
        with open(STATUS_FILE, encoding="utf-8") as fh:
            st = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        st = {}
    st[net] = {"logged_in": ok, "checked": datetime.now(TEHRAN).isoformat(timespec="minutes"), "detail": detail}
    with open(STATUS_FILE, "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ web messengers
def _browser(p, net):
    cfg = WEB[net]
    return p.chromium.launch_persistent_context(
        profile_dir(net), headless=True, user_agent=UA, locale=cfg["locale"],
        viewport={"width": 1280, "height": 860}, timezone_id="Asia/Tehran")


def _logged_in(page, net):
    cfg = WEB[net]
    if cfg.get("login_url") and cfg["login_url"] in page.url:
        return False
    for sel in cfg["ok_markers"]:
        try:
            if page.locator(sel).first.is_visible(timeout=500):
                if not page.locator(cfg["login_marker"]).first.is_visible(timeout=300):
                    return True
        except Exception:                                              # noqa: BLE001
            pass
    return False


def _wait_logged_in(page, net, seconds):
    end = time.time() + seconds
    while time.time() < end:
        if _logged_in(page, net):
            return True
        page.wait_for_timeout(1500)
    return False


def _first_visible(page, selectors, timeout=20000):
    end = time.time() + timeout / 1000
    while time.time() < end:
        for sel in selectors:
            loc = page.locator(sel)
            for i in range(min(loc.count(), 6)):
                el = loc.nth(i)
                try:
                    if el.is_visible():
                        return el
                except Exception:                                      # noqa: BLE001
                    pass
        page.wait_for_timeout(500)
    return None


def _ask_code(net):
    name = WEB[net]["fa"] if net in WEB else {"telegram": "تلگرام", "instagram": "اینستاگرام"}.get(net, net)
    return IO.ask(f"کد تأییدی که {name} برای شماره‌تان فرستاد")


def _code_and_password(page, net, shot):
    code_box = _first_visible(page, ["input[inputmode=numeric]:not([disabled])", "input[type=tel]:not([name=phone_country]):not([name=phone_number])",
                                     "input[autocomplete=one-time-code]", ".input-field-input[contenteditable=true]",
                                     "input[type=text]:not([disabled])"], timeout=25000)
    page.screenshot(path=shot)
    if not code_box:
        raise RuntimeError(f"صفحه‌ی کد پیدا نشد؛ تصویر: {shot}")
    code = _ask_code(net)
    code_box.click()
    page.keyboard.type(code, delay=90)
    page.keyboard.press("Enter")
    page.wait_for_timeout(5000)
    pw = _first_visible(page, ["input[type=password]"], timeout=4000)
    if pw:
        pw.fill(IO.ask("رمز دومرحله‌ای حساب", secret=True))
        page.keyboard.press("Enter")


DRY = os.environ.get("SOCIAL_DRY") == "1"   # fill the phone form, screenshot, do NOT submit


def _dry_stop(page, net, shot):
    page.screenshot(path=shot)
    say(f"[dry] {WEB[net]['fa']}: فرم پر شد و ارسال نشد — {shot}")
    return None


def login_web(net):
    from playwright.sync_api import sync_playwright
    cfg = WEB[net]
    phone = get(cfg["phone_env"])
    if not phone:
        sys.exit(f"{cfg['phone_env']} در .env خالی است.")
    shot = os.path.join(profile_dir(net), "last.png")
    with sync_playwright() as p:
        ctx = _browser(p, net)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(cfg["url"], wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        if _logged_in(page, net):
            say(f"✓ {cfg['fa']}: از قبل وارد شده‌اید.")
            save_status(net, True, "session ok")
            ctx.close()
            return True
        say(f"… {cfg['fa']}: ورود با شماره‌ی {phone}")

        if net in ("eitaa", "rubika"):
            if net == "eitaa":
                box = page.locator(".input-field-phone .input-field-input").first
                box.click()
                page.keyboard.press("Control+A")
                page.keyboard.type("+98" + local_phone(phone), delay=60)
            else:
                page.locator("input[name=phone_number]").first.fill(local_phone(phone))
            page.wait_for_timeout(600)
            if DRY:
                return _dry_stop(page, net, shot)
            page.locator("button[type=submit]").first.click()
            _code_and_password(page, net, shot)

        elif net == "bale":
            for label in (r"Got it|متوجه شدم", r"^\s*(Login|ورود)\s*$"):
                try:
                    page.get_by_role("button", name=re.compile(label)).first.click(timeout=4000)
                    page.wait_for_timeout(1200)
                except Exception:                                      # noqa: BLE001
                    pass
            page.locator("input[inputmode=numeric]").first.fill(local_phone(phone))
            if DRY:
                return _dry_stop(page, net, shot)
            page.get_by_role("button", name=re.compile("Submit|Continue|ادامه|تأیید")).first.click()
            page.wait_for_timeout(3000)
            _code_and_password(page, net, shot)

        elif net == "whatsapp":
            page.get_by_text(re.compile(r"^Log in with phone number$", re.I)).last.click(timeout=15000)
            page.wait_for_timeout(2500)
            tel = _first_visible(page, ["input[type=text]", "input[type=tel]", "div[contenteditable=true]"], timeout=10000)
            tel.click()
            page.keyboard.press("Control+A")
            page.keyboard.type("+98" + local_phone(phone), delay=60)
            if DRY:
                return _dry_stop(page, net, shot)
            page.get_by_role("button", name=re.compile("Next", re.I)).first.click()
            page.wait_for_timeout(5000)
            page.screenshot(path=shot)
            code = page.locator("[data-link-code]").first.get_attribute("data-link-code") if page.locator("[data-link-code]").count() else None
            if not code:
                text = page.inner_text("body")
                m = re.search(r"\b([A-Z0-9]{4}[-\s]?[A-Z0-9]{4})\b", text)
                code = m.group(1) if m else None
            IO.link_code(code or "?", "روی گوشی: واتساپ ← Linked devices ← Link a device ← Link with phone number instead ← این کد را وارد کنید (تا ۳ دقیقه)")

        ok = _wait_logged_in(page, net, 180 if net == "whatsapp" else 60)
        page.screenshot(path=shot)
        save_status(net, ok, "logged in" if ok else f"not confirmed — see {shot}")
        say(f"{'✓' if ok else '✗'} {cfg['fa']}: {'وارد شدید؛ نشست ذخیره شد.' if ok else 'ورود تأیید نشد. تصویر: ' + shot}")
        ctx.close()
        return ok


def check_web(net):
    from playwright.sync_api import sync_playwright
    if not os.path.isdir(os.path.join(SESSIONS, net)):
        save_status(net, False, "no session")
        return False
    with sync_playwright() as p:
        ctx = _browser(p, net)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(WEB[net]["url"], wait_until="domcontentloaded")
        ok = _wait_logged_in(page, net, 25)
        ctx.close()
    save_status(net, ok, "session ok" if ok else "logged out")
    return ok


# ------------------------------------------------------------------ Telegram (official client API)
def _telegram_client():
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    from telethon.sync import TelegramClient
    api_id, api_hash = get("TELEGRAM_API_ID"), get("TELEGRAM_API_HASH")
    if not (api_id and api_hash):
        sys.exit("TELEGRAM_API_ID و TELEGRAM_API_HASH را در .env پر کنید (my.telegram.org → API development tools).")
    return TelegramClient(os.path.join(profile_dir("telegram"), "user"), int(api_id), api_hash,
                          device_model="SepahanFelez Server", system_version="Linux", app_version="1.0")


def login_telegram():
    client = _telegram_client()
    client.start(phone=lambda: get("TELEGRAM_PHONE"), code_callback=lambda: _ask_code("telegram"),
                 password=lambda: IO.ask("رمز دومرحله‌ای تلگرام", secret=True))
    me = client.get_me()
    say(f"✓ تلگرام: وارد شدید به‌عنوان {me.first_name} (@{me.username or '—'})")
    save_status("telegram", True, f"user {me.id}")
    client.disconnect()
    return True


def check_telegram():
    if not os.path.exists(os.path.join(SESSIONS, "telegram", "user.session")):
        save_status("telegram", False, "no session")
        return False
    client = _telegram_client()
    client.connect()
    ok = client.is_user_authorized()
    client.disconnect()
    save_status("telegram", ok, "session ok" if ok else "logged out")
    return ok


# ------------------------------------------------------------------ Instagram (one fixed device)
IG_SESSION = lambda: os.path.join(profile_dir("instagram"), "session.json")  # noqa: E731


def _ig_client():
    from instagrapi import Client
    cl = Client()
    cl.request_timeout = 1          # instagrapi: this is a pause BEFORE each request, not an HTTP timeout
    cl.delay_range = [3, 8]
    if get("INSTAGRAM_PROXY"):
        cl.set_proxy(get("INSTAGRAM_PROXY"))
    if os.path.exists(IG_SESSION()):
        cl.load_settings(IG_SESSION())
    cl.challenge_code_handler = lambda username, choice: IO.ask(f"کد تأیید اینستاگرام ({choice}) برای {username}")
    return cl


def login_instagram():
    user, pw = get("INSTAGRAM_USERNAME"), get("INSTAGRAM_PASSWORD")
    if not (user and pw):
        sys.exit("INSTAGRAM_USERNAME و INSTAGRAM_PASSWORD را در .env پر کنید.")
    cl = _ig_client()
    code = None
    if get("INSTAGRAM_TOTP_SECRET"):
        code = cl.totp_generate_code(get("INSTAGRAM_TOTP_SECRET"))
    cl.login(user, pw, verification_code=code or "")
    cl.dump_settings(IG_SESSION())
    os.chmod(IG_SESSION(), 0o600)
    say(f"✓ اینستاگرام: وارد شدید به‌عنوان @{user}؛ نشست ثابت ذخیره شد.")
    save_status("instagram", True, f"@{user}")
    return True


def check_instagram():
    if not os.path.exists(IG_SESSION()):
        save_status("instagram", False, "no session")
        return False
    try:
        cl = _ig_client()
        cl.get_timeline_feed()
        save_status("instagram", True, "session ok")
        return True
    except Exception as exc:                                           # noqa: BLE001
        save_status("instagram", False, type(exc).__name__)
        return False


# ------------------------------------------------------------------ CLI
def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("login", "status", "logout"):
        sys.exit(__doc__)
    cmd, nets = sys.argv[1], (sys.argv[2:] or ALL)
    for net in nets:
        if net not in ALL:
            sys.exit(f"شبکه‌ی ناشناخته: {net} — یکی از: {' '.join(ALL)}")
    for net in nets:
        try:
            if cmd == "login":
                {"telegram": login_telegram, "instagram": login_instagram}.get(net, lambda: login_web(net))()
            elif cmd == "status":
                ok = {"telegram": check_telegram, "instagram": check_instagram}.get(net, lambda: check_web(net))()
                say(f"{'✓' if ok else '✗'} {WEB.get(net, {}).get('fa', net)}")
            elif cmd == "logout":
                import shutil
                shutil.rmtree(os.path.join(SESSIONS, net), ignore_errors=True)
                save_status(net, False, "logged out by user")
                say(f"نشست {net} پاک شد.")
        except SystemExit:
            raise
        except Exception as exc:                                       # noqa: BLE001
            save_status(net, False, f"{type(exc).__name__}: {str(exc)[:160]}")
            say(f"✗ {net}: {type(exc).__name__}: {str(exc)[:200]}")


if __name__ == "__main__":
    main()
