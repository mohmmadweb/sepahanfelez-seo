"""
Doing things on the networks: post to a channel, send a message, publish a story.

    act(net, kind, target=None, text="", media=None, link=None, item_id=None)
      net   telegram | instagram | linkedin | bale | eitaa | rubika | whatsapp
      kind  post (channel/feed) | story | message (to a person/chat)
      target  @username / channel / phone; empty → the channel from .env; "me" → Saved Messages

Every call passes through safety.py (lock, caps, gaps, 24h pause on pushback), and is written
to the publishing history (automation/history.py) and to the item's trace («روند تولید این محتوا»).

How each network is driven:
  telegram   official client API (Telethon) — messages, channel posts, stories
  instagram  instagrapi on one fixed device session (the @lenzit_org setup): feed photo, story
             (+link sticker), DM. Upload errors are verified on the page before anything is retried.
  linkedin   official REST API (Posts + Images) with the OAuth token from the dashboard
  bale/eitaa/rubika/whatsapp  their web apps in a logged-in headless browser. None of them offers
             a story API, so kind=story delivers the file to Saved Messages for the operator to repost.
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "dashboard"))

import login as L  # noqa: E402
import safety  # noqa: E402
from history import record  # noqa: E402
from sf import trace  # noqa: E402
from sf.env import get  # noqa: E402

CAN = {
    "telegram": {"post", "story", "message"},
    "instagram": {"post", "story", "message"},
    "linkedin": {"post"},
    "bale": {"post", "story", "message"},
    "eitaa": {"post", "story", "message"},
    "rubika": {"post", "story", "message"},
    "whatsapp": {"story", "message"},
}
KIND_FA = {"post": "پست", "story": "استوری", "message": "پیام"}
CHANNEL_ENV = {"telegram": "TELEGRAM_CHANNEL", "bale": "BALE_CHANNEL", "eitaa": "EITAA_CHANNEL", "rubika": "RUBIKA_CHANNEL"}


class NotLoggedIn(Exception):
    pass


def _say(msg):
    L.IO.say(msg)


def _jpeg(path):
    """Instagram and some web apps want JPEG; convert PNG/WebP to a sibling .jpg."""
    if path.lower().endswith((".jpg", ".jpeg")):
        return path
    from PIL import Image
    out = os.path.splitext(path)[0] + ".jpg"
    Image.open(path).convert("RGB").save(out, quality=92)
    return out


def _is_video(path):
    return bool(path) and path.lower().endswith((".mp4", ".mov", ".m4v"))


# ================================================================ Telegram
def _telegram(kind, target, text, media, link):
    from telethon import functions, types
    from telethon.errors import FloodWaitError
    client = L._telegram_client()
    client.connect()
    try:
        if not client.is_user_authorized():
            raise NotLoggedIn("تلگرام وارد نشده است.")
        peer = "me" if (target or "me") in ("me", "saved") else target
        try:
            if kind == "story":
                ent = client.get_input_entity(peer)
                up = client.upload_file(media)
                med = (types.InputMediaUploadedDocument(file=up, mime_type="video/mp4", attributes=[
                    types.DocumentAttributeVideo(duration=15, w=1080, h=1920, supports_streaming=True)])
                       if _is_video(media) else types.InputMediaUploadedPhoto(file=up))
                client(functions.stories.SendStoryRequest(peer=ent, media=med, caption=text or None,
                                                          privacy_rules=[types.InputPrivacyValueAllowAll()], period=86400))
                return {"status": "published", "detail": "استوری تلگرام منتشر شد", "url": None, "message_id": None}
            msg = client.send_file(peer, media, caption=text or None) if media else client.send_message(peer, text, link_preview=True)
            ent = client.get_entity(peer)
            uname = getattr(ent, "username", None)
            url = f"https://t.me/{uname}/{msg.id}" if uname and peer != "me" else None
            return {"status": "published", "detail": f"ارسال شد به {uname or peer}", "url": url, "message_id": msg.id}
        except FloodWaitError as exc:
            if exc.seconds > 120:
                safety.raise_alert("telegram", "FloodWait", f"{exc.seconds}s")
            raise
    finally:
        client.disconnect()


# ================================================================ Instagram
IG_SENSITIVE = ("ChallengeRequired", "FeedbackRequired", "LoginRequired", "PleaseWaitFewMinutes",
                "ClientThrottledError", "SentryBlock", "RateLimitError")


def _instagram(kind, target, text, media, link):
    from instagrapi import exceptions as E
    sensitive = tuple(getattr(E, x) for x in IG_SENSITIVE if hasattr(E, x))
    if not os.path.exists(L.IG_SESSION()):
        raise NotLoggedIn("اینستاگرام وارد نشده است.")
    cl = L._ig_client()
    cl.expose = lambda *a, **k: {}      # instagrapi calls a removed endpoint after uploads → false error → duplicate posts
    started = datetime.now().astimezone()
    try:
        try:
            if kind == "post":
                m = cl.video_upload(media, text) if _is_video(media) else cl.photo_upload(_jpeg(media), text)
                return {"status": "published", "url": f"https://www.instagram.com/p/{m.code}/", "message_id": str(m.pk),
                        "detail": "پست منتشر شد"}
            if kind == "story":
                from instagrapi.types import StoryLink
                links = [StoryLink(webUri=link, x=0.5, y=0.82, width=0.55, height=0.07)] if link else []
                st = cl.video_upload_to_story(media, "", links=links) if _is_video(media) else \
                    cl.photo_upload_to_story(_jpeg(media), "", links=links)
                return {"status": "published", "message_id": str(st.pk), "detail": "استوری منتشر شد",
                        "url": f"https://www.instagram.com/stories/{cl.username}/{st.pk}/"}
            if kind == "message":
                uid = cl.user_id_from_username(target.lstrip("@"))
                if media:
                    cl.direct_send_photo(_jpeg(media), user_ids=[uid])
                dm = cl.direct_send(text, user_ids=[uid]) if text else None
                return {"status": "published", "detail": f"دایرکت به @{target.lstrip('@')}", "message_id": str(getattr(dm, "id", "")), "url": None}
        except sensitive:
            raise
        except Exception:
            found = _ig_verify(cl, kind, started)        # maybe it went through and only a later call failed
            if found:
                _say("خطا بعد از آپلود؛ روی صفحه پیدا شد — دوباره ارسال نمی‌شود.")
                return found
            raise
    except sensitive as exc:
        safety.raise_alert("instagram", type(exc).__name__, str(exc))
        raise
    finally:
        try:
            cl.dump_settings(L.IG_SESSION())
        except Exception:                                              # noqa: BLE001
            pass
    raise ValueError(kind)


def _ig_verify(cl, kind, since):
    try:
        if kind == "post":
            for m in cl.user_medias_v1(cl.user_id, amount=3):
                if m.taken_at and m.taken_at >= since - timedelta(minutes=2):
                    return {"status": "published", "url": f"https://www.instagram.com/p/{m.code}/", "message_id": str(m.pk), "detail": "تأیید روی صفحه"}
        if kind == "story":
            for s in cl.user_stories(cl.user_id):
                if s.taken_at and s.taken_at >= since - timedelta(minutes=2):
                    return {"status": "published", "message_id": str(s.pk), "detail": "تأیید روی صفحه", "url": None}
    except Exception:                                                  # noqa: BLE001
        return None
    return None


# ================================================================ LinkedIn (official API)
LI_TOKEN = lambda: os.path.join(L.profile_dir("linkedin"), "token.json")  # noqa: E731


def _li_version():
    d = datetime.now() - timedelta(days=60)          # LinkedIn keeps ~12 months of monthly API versions
    return d.strftime("%Y%m")


def _linkedin(kind, target, text, media, link):
    import requests
    try:
        with open(LI_TOKEN(), encoding="utf-8") as fh:
            tok = json.load(fh)
    except FileNotFoundError:
        raise NotLoggedIn("لینکدین وصل نشده است.")
    if tok.get("expires_at", 0) < time.time():
        raise NotLoggedIn("توکن لینکدین منقضی شده؛ دوباره وصل کنید.")
    org = get("LINKEDIN_ORG_ID")
    author = f"urn:li:organization:{org}" if (target == "org" and org) else f"urn:li:person:{tok['sub']}"
    h = {"Authorization": f"Bearer {tok['access_token']}", "LinkedIn-Version": get("LINKEDIN_API_VERSION", _li_version()),
         "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}
    content = None
    if media and not _is_video(media):
        r = requests.post("https://api.linkedin.com/rest/images?action=initializeUpload", headers=h, timeout=30,
                          json={"initializeUploadRequest": {"owner": author}})
        r.raise_for_status()
        v = r.json()["value"]
        with open(_jpeg(media), "rb") as fh:
            requests.put(v["uploadUrl"], data=fh.read(), headers={"Authorization": h["Authorization"]}, timeout=120).raise_for_status()
        content = {"media": {"id": v["image"]}}
    body = {"author": author, "commentary": text + (f"\n\n{link}" if link else ""), "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False}
    if content:
        body["content"] = content
    r = requests.post("https://api.linkedin.com/rest/posts", headers=h, json=body, timeout=60)
    if r.status_code == 429:
        safety.raise_alert("linkedin", "RateLimit", r.text[:200])
    if r.status_code >= 300:
        raise RuntimeError(f"LinkedIn {r.status_code}: {r.text[:300]}")
    urn = r.headers.get("x-restli-id", "")
    return {"status": "published", "url": f"https://www.linkedin.com/feed/update/{urn}/" if urn else None,
            "message_id": urn, "detail": "پست لینکدین منتشر شد" + (" (صفحه‌ی شرکت)" if author.startswith("urn:li:organization") else "")}


# ================================================================ web messengers
SAVED_NAMES = ["Saved Messages", "پیام‌های ذخیره‌شده", "پیام های ذخیره شده", "ذخیره شده", "Saved"]


def _web(net, kind, target, text, media, link):
    """Bale/Eitaa/Rubika/WhatsApp through their web apps. Selectors are best-known; the first real
    send from the dashboard is the test, and every send leaves a screenshot in the job log."""
    from playwright.sync_api import sync_playwright
    cfg = L.WEB[net]
    if kind == "story":                         # no story API on the web apps → operator one-tap
        target = "me"
        text = ("📌 استوری برای انتشار — " + (text or "")).strip()
    target = (target or "me").strip()
    shot = os.path.join(L.profile_dir(net), "last-send.png")
    if link:
        text = (text + "\n" + link).strip()
    with sync_playwright() as p:
        ctx = L._browser(p, net)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            if net == "whatsapp":
                phone = L.local_phone(get("WHATSAPP_PHONE")) if target == "me" else re.sub(r"\D", "", target)
                phone = phone if phone.startswith("98") else "98" + phone.lstrip("0")
                page.goto(f"https://web.whatsapp.com/send?phone={phone}", wait_until="domcontentloaded")
                page.wait_for_timeout(12000)
                if not L._logged_in(page, net):
                    raise NotLoggedIn("واتساپ وارد نشده است.")
                box = page.locator("footer div[contenteditable=true]").first
                box.wait_for(timeout=30000)
            else:
                page.goto(cfg["url"], wait_until="domcontentloaded")
                page.wait_for_timeout(10000)
                if not L._logged_in(page, net):
                    raise NotLoggedIn(f"{cfg['fa']} وارد نشده است.")
                _open_chat(page, net, target)
                box = L._first_visible(page, [".input-message-input[contenteditable=true]", "footer [contenteditable=true]",
                                              "[contenteditable=true][role=textbox]", "textarea"], timeout=20000)
                if not box:
                    raise RuntimeError("جعبه‌ی پیام پیدا نشد")
            if media:
                files = page.locator("input[type=file]")
                if files.count() == 0:
                    for sel in ("[data-icon=plus]", "[data-icon=attach-menu-plus]", ".attach-file", "button[aria-label*=Attach]",
                                "button[aria-label*=پیوست]", "[class*=attach]"):
                        if page.locator(sel).count():
                            page.locator(sel).first.click()
                            page.wait_for_timeout(800)
                            break
                inp = page.locator("input[type=file][accept*=image], input[type=file]").first
                inp.set_input_files(media)
                page.wait_for_timeout(3000)
                cap = L._first_visible(page, [".popup-send-photo .input-message-input[contenteditable=true]",
                                              "div[contenteditable=true][data-tab]", "[role=dialog] [contenteditable=true]",
                                              "[role=dialog] textarea"], timeout=6000)
                if cap and text:
                    cap.click()
                    page.keyboard.insert_text(text)
                page.keyboard.press("Enter")
                page.wait_for_timeout(1500)
                send = L._first_visible(page, [".popup-send-photo .btn-primary", "[data-icon=send]", "[role=dialog] button[type=submit]"], timeout=2500)
                if send:
                    send.click()
            else:
                box.click()
                page.keyboard.insert_text(text)
                page.wait_for_timeout(500)
                page.keyboard.press("Enter")
            page.wait_for_timeout(5000)
            page.screenshot(path=shot)
            body = page.inner_text("body")
            sent = (text[:25] in body) if text else True
            return {"status": "sent-to-operator" if kind == "story" else ("published" if sent else "failed"),
                    "detail": (f"فرستاده شد به {target}" if sent else "ارسال تأیید نشد — تصویر: " + shot), "url": None, "message_id": None,
                    "screenshot": shot}
        finally:
            ctx.close()


def _open_chat(page, net, target):
    if target == "me":
        names = SAVED_NAMES
    else:
        names = [target.lstrip("@")]
        if net in ("eitaa", "rubika"):       # Telegram-WebK forks understand #@username
            page.goto(L.WEB[net]["url"] + "#@" + target.lstrip("@"), wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            if page.locator(".input-message-input[contenteditable=true]").count():
                return
    search = L._first_visible(page, [".input-search input", "input[type=search]", "input[placeholder*=جستجو]",
                                     "input[placeholder*=Search]", "input[type=text]"], timeout=15000)
    if not search:
        raise RuntimeError("جستجوی گفتگو پیدا نشد")
    for name in names:
        search.click()
        search.fill(name)
        page.wait_for_timeout(2500)
        hit = L._first_visible(page, [f".search-super .chatlist-chat:has-text('{name}')", f".chatlist-chat:has-text('{name}')",
                                      f"[role=listitem]:has-text('{name}')", f"a:has-text('{name}')", f"div[role=button]:has-text('{name}')"],
                               timeout=4000)
        if hit:
            hit.click()
            page.wait_for_timeout(2500)
            return
    raise RuntimeError(f"گفتگوی «{target}» پیدا نشد")


IMPL = {"telegram": _telegram, "instagram": _instagram, "linkedin": _linkedin,
        "bale": lambda *a: _web("bale", *a), "eitaa": lambda *a: _web("eitaa", *a),
        "rubika": lambda *a: _web("rubika", *a), "whatsapp": lambda *a: _web("whatsapp", *a)}


# ================================================================ entry point
def act(net, kind, target=None, text="", media=None, link=None, item_id=None, content_type=None, product=None):
    if net not in IMPL or kind not in CAN.get(net, set()):
        raise ValueError(f"«{KIND_FA.get(kind, kind)}» برای {net} پشتیبانی نمی‌شود.")
    if not target and kind == "post":
        target = get(CHANNEL_ENV.get(net, ""), "") if net in CHANNEL_ENV else ("org" if get("LINKEDIN_ORG_ID") else "me")
        if net in CHANNEL_ENV and not target:
            raise ValueError(f"کانال {net} در تنظیمات ({CHANNEL_ENV[net]}) خالی است.")
    if media and not os.path.isfile(media):
        raise ValueError("فایل رسانه پیدا نشد.")
    item_id = item_id or f"manual-{safety.now().strftime('%Y%m%d-%H%M%S')}-{net}"
    trace.step(item_id, "publish", f"درخواست {KIND_FA[kind]} در {net}",
               detail=f"مقصد: {target or '—'} · متن: {len(text or '')} نویسه · رسانه: {os.path.basename(media) if media else '—'}",
               decision="از داشبورد درخواست شد" if item_id.startswith("manual-") else "زمانش در تقویم انتشار رسید")
    try:
        safety.check(net, kind)
    except safety.Blocked as exc:
        trace.step(item_id, "publish", "رد شد توسط قواعد ایمنی", detail=str(exc))
        record(net, kind if kind != "post" else "post", content_type=content_type, product=product, text=text,
               media=media, status="failed", plan_ref=item_id, error=str(exc))
        raise
    trace.step(item_id, "publish", "بررسی ایمنی", detail="سقف روزانه، فاصله‌ی حداقل و هشدار فعال بررسی شد — مجاز")
    _say(f"در حال ارسال {KIND_FA[kind]} به {net}…")
    try:
        with safety.lock(net):
            try:
                res = IMPL[net](kind, target, text or "", media, link)
            except SystemExit as exc:            # login helpers exit with a message when a setting is missing
                raise NotLoggedIn(str(exc)) from None
    except Exception as exc:
        safety.note(net, kind, False, f"{type(exc).__name__}: {exc}")
        trace.step(item_id, "publish", "خطا", detail=f"{type(exc).__name__}: {str(exc)[:240]}",
                   decision="هشدار پلتفرم → توقف ۲۴ ساعته‌ی این شبکه" if safety.active_alert(net) else "دوباره به‌طور خودکار فرستاده نمی‌شود")
        record(net, kind, content_type=content_type, product=product, text=text, media=media, status="failed",
               plan_ref=item_id, error=f"{type(exc).__name__}: {exc}")
        raise
    ok = res.get("status") in ("published", "sent-to-operator")
    safety.note(net, kind, ok, res.get("detail", ""))
    trace.step(item_id, "publish", "نتیجه", detail=res.get("detail", ""), data={k: v for k, v in res.items() if k != "screenshot"})
    record(net, kind, content_type=content_type, product=product, text=text, media=media, url=res.get("url"),
           message_id=res.get("message_id"), status=res.get("status", "published"), plan_ref=item_id)
    _say(("✓ " if ok else "✗ ") + res.get("detail", ""))
    res["item_id"] = item_id
    return res
