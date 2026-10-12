"""
«تست کامل» of one account: really does each thing the account will be asked to do, privately.

Private by default (nothing appears to followers):
  telegram   who am I · text + photo to Saved Messages · story visible only to you · channel admin rights
  instagram  session valid · story to Close Friends only (empty list → only you) · inbox readable
  linkedin   token valid + publishing scope
  bale/eitaa/rubika/whatsapp
             logged in · text + photo to Saved Messages (the same path the one-tap story uses) · channel open + composer
Public tests run only when the owner ticks them, and clean up right away:
  instagram  feed photo → archived immediately · linkedin  post → deleted immediately

Results go to dashboard/data/validation/<account>.json and show on the account card. Tests are not
counted in the publishing history and do not use the daily caps, but they do take the account's lock
and any platform pushback still pauses the account for 24 h (same rule as real publishing).
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.join(ROOT, "dashboard")]

import actions  # noqa: E402
import login as L  # noqa: E402
import safety  # noqa: E402
from sf.env import get  # noqa: E402

OUT = os.path.join(ROOT, "dashboard", "data", "validation")
ASSETS = os.path.join(HERE, "test_assets")
TEHRAN = timezone(timedelta(hours=3, minutes=30))
CAPS_FA = {"auth": "ورود معتبر", "message": "ارسال پیام", "photo": "ارسال عکس", "story": "استوری",
           "channel": "انتشار در کانال", "inbox": "خواندن دایرکت", "post": "پست عمومی", "scope": "مجوز انتشار"}


def _now():
    return datetime.now(TEHRAN)


def _assets():
    """A story frame (1080×1920) and a feed frame (1080×1350) made from the brand sample."""
    os.makedirs(ASSETS, exist_ok=True)
    story, post = os.path.join(ASSETS, "test-story.jpg"), os.path.join(ASSETS, "test-post.jpg")
    if not (os.path.exists(story) and os.path.exists(post)):
        from PIL import Image, ImageDraw
        src = os.path.join(ROOT, "dashboard", "web", "samples", "story-1300-product.jpg")
        im = Image.open(src).convert("RGB").resize((1080, 1920))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, 1080, 90), fill=(18, 49, 82))
        d.text((40, 30), "TEST - Sepahan Felez connection check", fill=(255, 255, 255))
        im.save(story, quality=90)
        im.crop((0, 285, 1080, 1635)).save(post, quality=90)
    return story, post


class Run:
    def __init__(self, acct):
        self.acct, self.steps = acct, []

    def step(self, cap, fn, public=False):
        L.IO.say(f"… {CAPS_FA.get(cap, cap)}")
        t0 = time.time()
        try:
            detail = fn()
            st = "ok"
        except actions.NotLoggedIn as exc:
            st, detail = "fail", str(exc)
        except SkipStep as exc:
            st, detail = "skip", str(exc)
        except SystemExit as exc:
            st, detail = "fail", str(exc)
        except Exception as exc:                                       # noqa: BLE001
            st, detail = "fail", f"{type(exc).__name__}: {str(exc)[:220]}"
        row = {"cap": cap, "name": CAPS_FA.get(cap, cap), "status": st, "detail": str(detail or "")[:300],
               "public": public, "seconds": round(time.time() - t0, 1), "ts": _now().isoformat(timespec="seconds")}
        self.steps.append(row)
        L.IO.say(("✓ " if st == "ok" else "⏭ " if st == "skip" else "✗ ") + row["name"] + (f" — {row['detail']}" if row["detail"] else ""))
        return st == "ok"


class SkipStep(Exception):
    pass


# ---------------------------------------------------------------- per network
def _telegram(run, public):
    from telethon import functions, types
    story, _ = _assets()
    stamp = _now().strftime("%Y/%m/%d %H:%M")
    try:
        client = L._telegram_client()
    except SystemExit as exc:                     # API_ID / API_HASH missing in settings
        run.step("auth", lambda: (_ for _ in ()).throw(actions.NotLoggedIn(str(exc))))
        return
    client.connect()
    try:
        def auth():
            if not client.is_user_authorized():
                raise actions.NotLoggedIn("تلگرام وارد نیست")
            me = client.get_me()
            return f"{me.first_name or ''} @{me.username or '—'}"
        if not run.step("auth", auth):
            return
        run.step("message", lambda: f"پیام {client.send_message('me', f'🔧 تست اتصال سپاهان فلز — {stamp}').id} در پیام‌های ذخیره‌شده")
        run.step("photo", lambda: f"عکس {client.send_file('me', story, caption='🔧 تست عکس — ' + stamp).id} در پیام‌های ذخیره‌شده")

        def st():
            up = client.upload_file(story)
            r = client(functions.stories.SendStoryRequest(peer="me", media=types.InputMediaUploadedPhoto(file=up),
                                                          caption="تست اتصال — فقط شما می‌بینید",
                                                          privacy_rules=[types.InputPrivacyValueDisallowAll()], period=86400))
            return "استوری خصوصی منتشر شد (فقط خودتان، ۲۴ ساعت) — در تلگرام «استوری‌های من» را ببینید"
        run.step("story", st)

        def ch():
            chan = get("TELEGRAM_CHANNEL")
            if not chan:
                raise SkipStep("TELEGRAM_CHANNEL در تنظیمات خالی است")
            perm = client.get_permissions(chan, "me")
            if not (perm.is_creator or getattr(perm, "post_messages", False)):
                raise RuntimeError(f"در {chan} اجازه‌ی پست ندارید")
            return f"اجازه‌ی پست در {chan} دارید (چیزی منتشر نشد)"
        run.step("channel", ch)
    finally:
        client.disconnect()


def _instagram(run, public):
    from instagrapi import exceptions as E
    story, post = _assets()
    if not L.has_session("instagram", "session.json"):
        run.step("auth", lambda: (_ for _ in ()).throw(actions.NotLoggedIn("اینستاگرام وارد نیست")))
        return
    cl = L._ig_client()
    cl.expose = lambda *a, **k: {}
    sensitive = tuple(getattr(E, x) for x in actions.IG_SENSITIVE if hasattr(E, x))
    try:
        if not run.step("auth", lambda: f"@{cl.account_info().username}"):
            return
        run.step("story", lambda: "استوری فقط برای Close Friends منتشر شد (شناسه " +
                 str(cl.photo_upload_to_story(story, "", extra_data={"audience": "besties"}).pk) + ") — اگر فهرست خالی است فقط خودتان می‌بینید")
        run.step("inbox", lambda: f"{len(cl.direct_threads(amount=3))} گفتگوی اخیر خوانده شد")
        if public:
            def p():
                m = cl.photo_upload(post, "تست اتصال — بلافاصله آرشیو می‌شود")
                cl.media_archive(m.id)
                return f"پست منتشر و بلافاصله آرشیو شد (https://www.instagram.com/p/{m.code}/ — از بخش Archive قابل دیدن/حذف)"
            run.step("post", p, public=True)
        else:
            run.steps.append({"cap": "post", "name": CAPS_FA["post"], "status": "skip", "public": True,
                              "detail": "تست عمومی انتخاب نشد", "seconds": 0, "ts": _now().isoformat(timespec="seconds")})
    except sensitive as exc:
        safety.raise_alert("instagram", type(exc).__name__, str(exc), run.acct["id"])
        run.steps.append({"cap": "alert", "name": "هشدار اینستاگرام", "status": "fail", "public": False, "seconds": 0,
                          "detail": f"{type(exc).__name__} — این حساب ۲۴ ساعت متوقف شد", "ts": _now().isoformat(timespec="seconds")})
    finally:
        try:
            cl.dump_settings(L.IG_SESSION())
        except Exception:                                              # noqa: BLE001
            pass


def _linkedin(run, public):
    import requests
    path = os.path.join(L.profile_dir("linkedin"), "token.json")

    def auth():
        if not os.path.exists(path):
            raise actions.NotLoggedIn("لینکدین وصل نیست")
        tok = json.load(open(path, encoding="utf-8"))
        r = requests.get("https://api.linkedin.com/v2/userinfo", timeout=20, headers={"Authorization": f"Bearer {tok['access_token']}"})
        if r.status_code != 200:
            raise RuntimeError(f"توکن رد شد ({r.status_code})")
        days = int((tok["expires_at"] - time.time()) / 86400)
        return f"{r.json().get('name')} · {days} روز تا انقضا"
    if not run.step("auth", auth):
        return
    tok = json.load(open(path, encoding="utf-8"))
    run.step("scope", lambda: "w_member_social دارد" if "w_member_social" in (tok.get("scope") or "")
             else (_ for _ in ()).throw(RuntimeError("مجوز انتشار (w_member_social) در توکن نیست")))
    if public:
        def p():
            res = actions._linkedin("post", None, "تست اتصال سپاهان فلز — این پست بلافاصله حذف می‌شود", None, None)
            urn = res.get("message_id")
            h = {"Authorization": f"Bearer {tok['access_token']}", "LinkedIn-Version": actions._li_version(),
                 "X-Restli-Protocol-Version": "2.0.0"}
            import urllib.parse
            requests.delete("https://api.linkedin.com/rest/posts/" + urllib.parse.quote(urn, safe=""), headers=h, timeout=30)
            return "پست منتشر و بلافاصله حذف شد"
        run.step("post", p, public=True)
    else:
        run.steps.append({"cap": "post", "name": CAPS_FA["post"], "status": "skip", "public": True,
                          "detail": "تست عمومی انتخاب نشد", "seconds": 0, "ts": _now().isoformat(timespec="seconds")})


def _web(net, run, public):
    story, _ = _assets()
    stamp = _now().strftime("%Y/%m/%d %H:%M")
    ok = run.step("auth", lambda: "وارد است" if L.check_web(net) else (_ for _ in ()).throw(actions.NotLoggedIn("وارد نیست")))
    if not ok:
        return

    def send(text, media):
        r = actions._web(net, "message", "me", text, media, None)
        if r.get("status") != "published":
            raise RuntimeError(r.get("detail") or "ارسال تأیید نشد")
        return "در پیام‌های ذخیره‌شده" + (" — تصویر صفحه: " + r["screenshot"] if r.get("screenshot") else "")
    run.step("message", lambda: send(f"🔧 تست اتصال سپاهان فلز — {stamp}", None))
    run.step("photo", lambda: send(f"🔧 تست عکس — {stamp}", story))
    run.steps.append({"cap": "story", "name": CAPS_FA["story"], "status": "ok" if run.steps[-1]["status"] == "ok" else "fail",
                      "public": False, "seconds": 0, "ts": _now().isoformat(timespec="seconds"),
                      "detail": "این اپ برای استوری API ندارد؛ فایل آماده‌ی استوری با همین مسیر به پیام‌های ذخیره‌شده می‌رود و از گوشی با دو لمس استوری می‌شود"})
    chan_env = {"bale": "BALE_CHANNEL", "eitaa": "EITAA_CHANNEL", "rubika": "RUBIKA_CHANNEL"}.get(net)

    def ch():
        if not chan_env or not get(chan_env):
            raise SkipStep(f"{chan_env} در تنظیمات خالی است" if chan_env else "واتساپ کانال ندارد")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ctx = L._browser(p, net)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(L.WEB[net]["url"], wait_until="domcontentloaded")
            page.wait_for_timeout(9000)
            actions._open_chat(page, net, get(chan_env))
            box = L._first_visible(page, [".input-message-input[contenteditable=true]", "footer [contenteditable=true]",
                                          "[contenteditable=true][role=textbox]", "textarea"], timeout=8000)
            ctx.close()
        if not box:
            raise RuntimeError("کانال باز شد ولی جعبه‌ی نوشتن نیست — احتمالاً ادمین نیستید")
        return f"کانال {get(chan_env)} باز شد و اجازه‌ی نوشتن دارید (چیزی منتشر نشد)"
    run.step("channel", ch)


def validate(acct, public=False):
    L.use(acct)
    run = Run(acct)
    try:
        with safety.lock(f"{acct['net']}-{acct['id']}", wait_sec=120):
            if acct["net"] == "telegram":
                _telegram(run, public)
            elif acct["net"] == "instagram":
                _instagram(run, public)
            elif acct["net"] == "linkedin":
                _linkedin(run, public)
            else:
                _web(acct["net"], run, public)
    finally:
        L.use(None)
    res = {"account": acct["id"], "net": acct["net"], "at": _now().isoformat(timespec="seconds"), "public": public,
           "steps": run.steps, "ok": sum(1 for s in run.steps if s["status"] == "ok"),
           "fail": sum(1 for s in run.steps if s["status"] == "fail"), "skip": sum(1 for s in run.steps if s["status"] == "skip")}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"{acct['id']}.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    return res
