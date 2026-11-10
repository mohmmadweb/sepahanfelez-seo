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
             "login_marker": "input[inputmode=numeric], [data-testid=submit-button]", "login_url": "/login",
             "ok_markers": ["[data-testid=dialog-tab]", "[data-testid=virtuoso-scroller]", "svg[aria-label='AddStatus-icon']"]},
    "whatsapp": {"url": "https://web.whatsapp.com/", "fa": "واتساپ", "phone_env": "WHATSAPP_PHONE", "locale": "en-US",
                 "login_marker": "canvas, [data-ref]", "ok_markers": ["#pane-side", "div[aria-label='Chat list']"]},
}
ALL = list(WEB) + ["telegram", "instagram", "linkedin"]


class TerminalIO:
    """How a login flow talks to a human. The web UI swaps in a queue-backed version."""
    def say(self, msg):
        print(msg, flush=True)

    def ask(self, prompt, secret=False):
        return (getpass.getpass(prompt) if secret else input(prompt)).strip()

    def link_code(self, code, how):
        self.say(how)
        self.say(f"  کد:  {code}")

    def qr(self, png_b64):
        self.say("[QR تازه آماده است]")


IO = TerminalIO()


def say(msg):
    IO.say(msg)


ACCT = None          # the account a flow works on (accounts.py row); set with use()


def use(acct):
    """Select the account for the following login/check/act calls (None = default account of each network)."""
    global ACCT
    ACCT = acct
    return acct


def _acct(net):
    import accounts
    if ACCT and ACCT["net"] == net:
        return ACCT
    a = accounts.default(net)
    if not a:
        sys.exit(f"برای {net} هنوز حسابی اضافه نشده؛ از صفحه‌ی اتصالات «افزودن حساب» را بزنید.")
    return a


def profile_dir(net):
    os.makedirs(SESSIONS, mode=0o700, exist_ok=True)
    os.chmod(SESSIONS, 0o700)
    d = os.path.join(SESSIONS, net, _acct(net)["id"])
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def has_session(net, name=None):
    import accounts
    a = ACCT if ACCT and ACCT["net"] == net else accounts.default(net)
    if not a:
        return False
    d = os.path.join(SESSIONS, net, a["id"])
    return os.path.exists(os.path.join(d, name)) if name else os.path.isdir(d) and bool(os.listdir(d))


def local_phone(phone):
    """+989120000000 → 9120000000 (forms that already show +98)."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("98"):
        digits = digits[2:]
    return digits.lstrip("0")


def save_status(net, ok, detail=""):
    """Status is kept per account (key = account id) so two numbers on one app are reported separately."""
    import accounts
    a = ACCT if ACCT and ACCT["net"] == net else accounts.default(net)
    key = a["id"] if a else net
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    try:
        with open(STATUS_FILE, encoding="utf-8") as fh:
            st = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        st = {}
    st[key] = {"logged_in": ok, "checked": datetime.now(TEHRAN).isoformat(timespec="minutes"), "detail": detail,
               "net": net, "label": (a or {}).get("label"), "who": (a or {}).get("phone") or (a or {}).get("username")}
    with open(STATUS_FILE, "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ web messengers
def _browser(p, net):
    cfg = WEB[net]
    return p.chromium.launch_persistent_context(
        profile_dir(net), headless=True, user_agent=UA, locale=cfg["locale"],
        viewport={"width": 1280, "height": 860}, timezone_id="Asia/Tehran")


def _logged_in(page, net):
    """Positive evidence only. A login page that has not redirected yet must not count as logged in
    (Bale's check said «logged in» for days because it looked before the redirect to /login)."""
    cfg = WEB[net]
    if cfg.get("login_url") and cfg["login_url"] in page.url:
        return False
    try:
        if page.locator(cfg["login_marker"]).first.is_visible(timeout=300):
            return False
    except Exception:                                                  # noqa: BLE001
        pass
    if not cfg["ok_markers"]:
        # no stable chat-list selector known (Bale): logged in = app loaded, settled, no login form anywhere
        return page.evaluate("document.readyState") == "complete" and page.locator("input, [contenteditable=true]").count() > 0
    for sel in cfg["ok_markers"]:
        try:
            if page.locator(sel).first.is_visible(timeout=500):
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


MARK_OLD = "()=>document.querySelectorAll('input,[contenteditable=true]').forEach(e=>e.setAttribute('data-sf-old','1'))"
NEW_FIELD = ("input:not([data-sf-old]):not([type=hidden]):not([disabled]), "
             "[contenteditable=true]:not([data-sf-old])")


def _code_and_password(page, net, shot, seconds=60):
    """After the phone form is sent the app shows a spinner, then a code page. The phone field stays in the
    page for a while, so the code box is the first *new* visible field (the old ones were marked before sending)."""
    code_box, end = None, time.time() + seconds
    while time.time() < end and not code_box:
        loc = page.locator(NEW_FIELD)
        for i in range(min(loc.count(), 8)):
            try:
                if loc.nth(i).is_visible():
                    code_box = loc.nth(i)
                    break
            except Exception:                                          # noqa: BLE001
                pass
        if not code_box:
            page.wait_for_timeout(1000)
    page.screenshot(path=shot)
    if not code_box:
        msg = re.sub(r"\s+", " ", page.inner_text("body"))[:200]
        raise RuntimeError(f"صفحه‌ی کد بعد از {seconds} ثانیه نیامد؛ پیام صفحه: «{msg}» — تصویر: {shot}")
    _dismiss(page)
    where = re.search(r"[^.\n]*(?:ارسال شد|ارسال شده|ارسال گردید|sent)[^.\n]*", page.inner_text("body"))
    if where:
        say(f"پیام {WEB[net]['fa']}: «{where.group(0).strip()}» — کد داخل خود اپ {WEB[net]['fa']} می‌آید (پیامک نیست)؛ اگر چند کد آمده، جدیدترین را بزنید.")
    for attempt in range(3):
        code = _ask_code(net) if attempt == 0 else IO.ask(f"{WEB[net]['fa']} گفت کد نامعتبر است؛ جدیدترین کدی را که در اپ {WEB[net]['fa']} آمده وارد کنید")
        _dismiss(page)
        code_box.click(force=True)
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.type(re.sub(r"\D", "", code.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))), delay=90)
        page.keyboard.press("Enter")
        page.wait_for_timeout(6000)
        page.screenshot(path=shot)
        body = page.inner_text("body")
        if _logged_in(page, net) or not re.search(r"نامعتبر|اشتباه|invalid|incorrect|wrong", body, re.I):
            break
    pw = _first_visible(page, ["input[type=password]"], timeout=4000)
    if pw:
        pw.fill(IO.ask("رمز دومرحله‌ای حساب", secret=True))
        page.keyboard.press("Enter")


def _dismiss(page):
    """Close an info popup («کد ورود … ارسال گردید» → «تایید») that covers the code box. Only a button that sits in
    the same small box as such a message is pressed — never the form's own submit button."""
    try:
        page.evaluate("""()=>{
          const msgs=[...document.querySelectorAll('body *')].filter(e=>e.offsetParent && e.children.length<3
              && /ارسال (گردید|شد)|sent/i.test(e.innerText||''));
          for (const m of msgs) {
            let box=m;
            for (let k=0;k<4 && box;k++,box=box.parentElement) {
              const b=[...box.querySelectorAll('button,a,[role=button]')].find(x=>x.offsetParent && /^\\s*(تایید|تأیید|باشه|OK)\\s*$/.test(x.innerText||''));
              if (b && box.getBoundingClientRect().height<320 && !box.querySelector('input')) { b.click(); return true; }
            }
          }
          return false}""")
        page.wait_for_timeout(800)
    except Exception:                                                  # noqa: BLE001
        pass


DRY = os.environ.get("SOCIAL_DRY") == "1"   # fill the phone form, screenshot, do NOT submit


def _dry_stop(page, net, shot):
    page.screenshot(path=shot)
    say(f"[dry] {WEB[net]['fa']}: فرم پر شد و ارسال نشد — {shot}")
    return None


def login_web(net):
    from playwright.sync_api import sync_playwright
    cfg = WEB[net]
    phone = _acct(net).get("phone")
    if not phone:
        sys.exit("برای این حساب شماره ثبت نشده است.")
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
            btn = page.get_by_role("button", name=re.compile(r"^\s*(ادامه|بعدی|Next|Continue)\s*$")).first
            btn.wait_for(state="visible", timeout=15000)
            if DRY:
                return _dry_stop(page, net, shot)
            page.evaluate(MARK_OLD)
            btn.click()
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
            page.evaluate(MARK_OLD)
            page.get_by_role("button", name=re.compile("Submit|Continue|ادامه|تأیید")).first.click()
            _code_and_password(page, net, shot)

        elif net == "whatsapp":
            return _whatsapp_qr(ctx, page, shot)

        ok = _wait_logged_in(page, net, 180 if net == "whatsapp" else 60)
        page.screenshot(path=shot)
        save_status(net, ok, "logged in" if ok else f"not confirmed — see {shot}")
        say(f"{'✓' if ok else '✗'} {cfg['fa']}: {'وارد شدید؛ نشست ذخیره شد.' if ok else 'ورود تأیید نشد. تصویر: ' + shot}")
        ctx.close()
        return ok


def _whatsapp_qr(ctx, page, shot, seconds=240):
    """WhatsApp Web shows a QR that changes every ~20 s: its picture goes to the dashboard window, refreshed,
    until the phone has scanned it (WhatsApp → Linked devices → Link a device)."""
    import base64
    say("روی گوشی: واتساپ ← ⋮ یا Settings ← Linked devices ← Link a device ← QR داخل همین پنجره را اسکن کنید.")
    end, last = time.time() + seconds, None
    while time.time() < end:
        if _logged_in(page, "whatsapp"):
            break
        reload = page.get_by_role("button", name=re.compile(r"reload|Reload|بارگذاری")).first
        try:
            if reload.count() and reload.is_visible(timeout=300):
                reload.click()                             # WhatsApp stops refreshing the QR after a few rounds
                page.wait_for_timeout(2500)
        except Exception:                                              # noqa: BLE001
            pass
        canvas = page.locator("canvas").first
        try:
            if canvas.is_visible(timeout=1000):
                png = canvas.screenshot()
                if png != last:
                    last = png
                    if hasattr(IO, "qr"):
                        IO.qr(base64.b64encode(png).decode())
        except Exception:                                              # noqa: BLE001
            pass
        page.wait_for_timeout(2500)
    if hasattr(IO, "qr"):
        IO.qr(None)
    ok = _wait_logged_in(page, "whatsapp", 45)             # after the scan WhatsApp loads the chats
    page.screenshot(path=shot)
    save_status("whatsapp", ok, "logged in" if ok else f"not confirmed — see {shot}")
    say("✓ واتساپ: وارد شدید؛ نشست ذخیره شد." if ok else "✗ واتساپ: QR در ۴ دقیقه اسکن نشد؛ دوباره «ورود» را بزنید.")
    ctx.close()
    return ok


def check_web(net):
    from playwright.sync_api import sync_playwright
    if not has_session(net):
        save_status(net, False, "no session")
        return False
    with sync_playwright() as p:
        ctx = _browser(p, net)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(WEB[net]["url"], wait_until="domcontentloaded")
        page.wait_for_timeout(10000)               # let client-side redirects (→ /login) happen first
        ok = _wait_logged_in(page, net, 60 if net == "whatsapp" else 20)    # WhatsApp loads its chats for ~25 s
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


def ensure_telegram_keys():
    """No TELEGRAM_API_ID/HASH yet: get them from my.telegram.org with this account's number (one code in the
    Telegram app), save them in .env, and go on — the owner never visits my.telegram.org."""
    if get("TELEGRAM_API_ID") and get("TELEGRAM_API_HASH"):
        return
    import tg_apikeys
    from dashboard_env import set_settings
    phone = _acct("telegram").get("phone")
    if not phone:
        sys.exit("برای این حساب تلگرام شماره ثبت نشده است.")
    say("۱ از ۲ — گرفتن کلید تلگرام از my.telegram.org با همین شماره…")
    api_id, api_hash = tg_apikeys.fetch(phone, lambda prompt: IO.ask(prompt), say=say)
    set_settings({"TELEGRAM_API_ID": api_id, "TELEGRAM_API_HASH": api_hash})
    os.environ["TELEGRAM_API_ID"], os.environ["TELEGRAM_API_HASH"] = api_id, api_hash
    say("✓ کلید تلگرام گرفته و در تنظیمات ذخیره شد. ۲ از ۲ — ورود خود حساب (کد دوم هم در اپ تلگرام می‌آید)…")


def login_telegram():
    ensure_telegram_keys()
    client = _telegram_client()
    client.start(phone=lambda: _acct("telegram")["phone"], code_callback=lambda: _ask_code("telegram"),
                 password=lambda: IO.ask("رمز دومرحله‌ای تلگرام", secret=True))
    me = client.get_me()
    say(f"✓ تلگرام: وارد شدید به‌عنوان {me.first_name} (@{me.username or '—'})")
    save_status("telegram", True, f"user {me.id}")
    try:                                     # the channel's name, description and photo, once
        import channel_profile
        channel_profile.apply(client, say=say)
    except Exception as exc:                 # noqa: BLE001
        say(f"پروفایل کانال: {exc}")
    client.disconnect()
    return True


def check_telegram():
    if not has_session("telegram", "user.session"):
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
    """One fixed device for the account's whole life (what kept @lenzit_org stable): the device is
    written to disk before the first login, so a retry after a challenge is the *same* phone."""
    from instagrapi import Client
    cl = Client()
    cl.request_timeout = 1          # instagrapi: this is a pause BEFORE each request, not an HTTP timeout
    cl.delay_range = [3, 8]
    if os.path.exists(IG_SESSION()):
        cl.load_settings(IG_SESSION())
    else:
        cl.set_locale("fa_IR")
        cl.set_country("IR")
        cl.set_country_code(98)
        cl.set_timezone_offset(int(3.5 * 3600))
    import accounts
    proxy = accounts.secret(_acct("instagram"), "proxy")
    if proxy:
        cl.set_proxy(proxy)
    cl.challenge_code_handler = lambda username, choice: IO.ask(f"کد تأیید اینستاگرام ({choice}) برای {username}")
    return cl


def login_instagram():
    from instagrapi.exceptions import BadPassword, ChallengeRequired, TwoFactorRequired
    import accounts
    a = _acct("instagram")
    user, pw = a.get("username"), accounts.secret(a, "password")
    if not (user and pw):
        sys.exit("نام کاربری یا رمز این حساب اینستاگرام ثبت نشده است.")
    cl = _ig_client()
    cl.dump_settings(IG_SESSION())
    os.chmod(IG_SESSION(), 0o600)
    try:
        cl.get_timeline_feed()
        cl.account_info()
        say(f"✓ اینستاگرام: نشست قبلی @{user} هنوز معتبر است.")
        save_status("instagram", True, f"@{user}")
        return True
    except Exception:                                                  # noqa: BLE001
        pass
    try:
        totp = accounts.secret(a, "totp")
        code = cl.totp_generate_code(totp) if totp else ""
        try:
            cl.login(user, pw, verification_code=code)
        except TwoFactorRequired:
            cl.login(user, pw, verification_code=IO.ask("کد ورود دومرحله‌ای اینستاگرام (پیامک یا اپ احراز هویت)"))
    except ChallengeRequired:
        cl.dump_settings(IG_SESSION())
        save_status("instagram", False, "challenge")
        say("اینستاگرام این ورود را بررسی می‌کند: در اپ اینستاگرام روی همین اکانت پیام «آیا این شما بودید؟» را تأیید کنید، "
            "بعد دوباره «ورود» را بزنید (همان دستگاه ذخیره شده است).")
        return False
    except BadPassword:
        save_status("instagram", False, "bad password")
        say("رمز اینستاگرام درست نیست (INSTAGRAM_PASSWORD).")
        return False
    cl.dump_settings(IG_SESSION())
    say(f"✓ اینستاگرام: وارد شدید به‌عنوان @{user}؛ نشست ثابت ذخیره شد.")
    save_status("instagram", True, f"@{user}")
    return True


def check_instagram():
    if not has_session("instagram", "session.json"):
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


# ------------------------------------------------------------------ LinkedIn (OAuth from the dashboard)
def check_linkedin():
    if not has_session("linkedin", "token.json"):
        save_status("linkedin", False, "no session")
        return False
    path = os.path.join(profile_dir("linkedin"), "token.json")
    try:
        with open(path, encoding="utf-8") as fh:
            tok = json.load(fh)
    except FileNotFoundError:
        save_status("linkedin", False, "no session")
        return False
    ok = tok.get("expires_at", 0) > time.time()
    days = int((tok.get("expires_at", 0) - time.time()) / 86400)
    save_status("linkedin", ok, f"{tok.get('name', '')} · {days} روز تا انقضا" if ok else "token expired")
    return ok


def login_linkedin():
    sys.exit("ورود لینکدین از داشبورد انجام می‌شود (دکمه‌ی «اتصال لینکدین»): نیاز به صفحه‌ی بازگشت روی دامنه دارد.")


# ------------------------------------------------------------------ CLI
def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("login", "status", "logout"):
        sys.exit(__doc__)
    cmd, nets = sys.argv[1], (sys.argv[2:] or ALL)
    for net in nets:
        if net not in ALL:
            sys.exit(f"شبکه‌ی ناشناخته: {net} — یکی از: {' '.join(ALL)}")
    import accounts
    for net in nets:
        targets = accounts.for_net(net) or [None]
        for a in targets:
            use(a)
            who = (a or {}).get("phone") or (a or {}).get("username") or ""
            try:
                if a is None:
                    if cmd == "status":
                        say(f"– {net}: حسابی اضافه نشده")
                    continue
                if cmd == "login":
                    {"telegram": login_telegram, "instagram": login_instagram, "linkedin": login_linkedin}.get(net, lambda: login_web(net))()
                elif cmd == "status":
                    ok = {"telegram": check_telegram, "instagram": check_instagram, "linkedin": check_linkedin}.get(net, lambda: check_web(net))()
                    say(f"{'✓' if ok else '✗'} {WEB.get(net, {}).get('fa', net)} {who}")
                elif cmd == "logout":
                    import shutil
                    shutil.rmtree(os.path.join(SESSIONS, net, a["id"]), ignore_errors=True)
                    save_status(net, False, "logged out by user")
                    say(f"نشست {net} {who} پاک شد.")
            except SystemExit as exc:
                say(f"✗ {net} {who}: {exc}")
            except Exception as exc:                                   # noqa: BLE001
                save_status(net, False, f"{type(exc).__name__}: {str(exc)[:160]}")
                say(f"✗ {net} {who}: {type(exc).__name__}: {str(exc)[:200]}")
        use(None)


if __name__ == "__main__":
    main()
