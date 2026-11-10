"""
Daily check of every connection the system depends on, so a broken one is never discovered by a
missed post. Writes dashboard/data/connections.json; the dashboard shows a red banner on «نمای کلی»
for anything broken, with what to do, and the full table under «اتصالات و تنظیمات».

    python3 checkup.py          # all (the daily timer, 07:40 Tehran, and the dashboard button)
    python3 checkup.py social   # only the social accounts

Each row: state ok | warn | broken | missing, the reason, what to do, since when it is broken, and
when it last worked. Checks are read-only: nothing is posted (the full «تست کامل» stays manual).
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(HERE, "social"), os.path.join(HERE, "site"), os.path.join(ROOT, "dashboard")]

from sf.util import DATA, read_json, write_json  # noqa: E402

OUT = os.path.join(DATA, "connections.json")
TEHRAN = timezone(timedelta(hours=3, minutes=30))
NETS = [("instagram", "اینستاگرام"), ("telegram", "تلگرام"), ("whatsapp", "واتساپ"), ("bale", "بله"),
        ("eitaa", "ایتا"), ("rubika", "روبیکا"), ("linkedin", "لینکدین")]
REASON_FA = {"no session": "هنوز وارد نشده", "logged out": "از حساب بیرون افتاده (نشست باطل شد)",
             "token expired": "توکن لینکدین منقضی شده", "challenge": "اینستاگرام تأیید «آیا شما بودید؟» می‌خواهد",
             "bad password": "رمز اینستاگرام اشتباه است", "LoginRequired": "اینستاگرام نشست را باطل کرده",
             "ChallengeRequired": "اینستاگرام تأیید «آیا شما بودید؟» می‌خواهد"}


def _now():
    return datetime.now(TEHRAN).isoformat(timespec="minutes")


def _row(key, group, name, state, detail="", fix="", prev=None):
    prev = prev or {}
    r = {"key": key, "group": group, "name": name, "state": state, "detail": detail, "fix": fix, "checked": _now()}
    r["last_ok"] = r["checked"] if state == "ok" else prev.get("last_ok")
    r["since"] = (prev.get("since") if prev.get("state") == state else r["checked"]) if state in ("broken", "warn") else None
    return r


# ------------------------------------------------------------------ social accounts
def social(prev):
    import accounts
    import login as L
    from actions import CHANNEL_ENV
    from sf.env import get
    rows = []
    accts = accounts.load()
    for net, fa in NETS:
        mine = [a for a in accts if a["net"] == net]
        if not mine:
            rows.append(_row(f"acct:{net}", "شبکه‌ها", fa, "missing", "حسابی اضافه نشده",
                             "اتصالات و تنظیمات → «+ افزودن حساب» → «ورود»", prev.get(f"acct:{net}")))
            continue
        for a in mine:
            key = f"acct:{a['id']}"
            name = f"{fa} — {a.get('label') or a.get('username') or a.get('phone') or a['id']}"
            L.use(a)
            try:
                fn = {"telegram": L.check_telegram, "instagram": L.check_instagram, "linkedin": L.check_linkedin}.get(net)
                ok = fn() if fn else L.check_web(net)
                st = (read_json(os.path.join(DATA, "social_status.json"), {}) or {}).get(a["id"], {})
                detail = st.get("detail", "")
            except SystemExit as exc:                                   # missing keys etc. (login.py exits with a message)
                ok, detail = False, str(exc)
            except Exception as exc:                                    # noqa: BLE001
                ok, detail = None, f"بررسی نشد: {type(exc).__name__}: {str(exc)[:120]}"
            finally:
                L.use(None)
            if ok is None:
                rows.append(_row(key, "شبکه‌ها", name, "warn", detail, "اگر فردا هم تکرار شد «تست کامل» را بزنید", prev.get(key)))
                continue
            state = "ok" if ok else "broken"
            fix = "" if ok else "اتصالات و تنظیمات → همین حساب → «ورود» (کد به گوشی همان شماره می‌آید)"
            if ok and net == "linkedin" and "روز تا انقضا" in detail:
                days = int("".join(ch for ch in detail.split("·")[-1] if ch.isdigit()) or 99)
                if days <= 10:
                    state, fix = "warn", "تا چند روز دیگر توکن لینکدین تمام می‌شود: «اتصال لینکدین» را دوباره بزنید"
            channels = [n.strip() for n in get("SOCIAL_CHANNEL_NETS", "telegram").split(",")]
            if ok and net in CHANNEL_ENV and net in channels and not get(CHANNEL_ENV[net], ""):
                state, fix = "warn", f"حساب وصل است ولی نشانی کانال ({CHANNEL_ENV[net]}) در «تنظیمات» خالی است"
            reason = REASON_FA.get(detail, detail)
            if not ok and not (prev.get(key) or {}).get("last_ok"):
                reason = "هنوز وارد نشده"                  # never connected: not «signed out»
            rows.append(_row(key, "شبکه‌ها", name, state, reason, fix, prev.get(key)))
    return rows


# ------------------------------------------------------------------ site panel, Google, Drive, news
def _age_h(iso):
    try:
        t = datetime.fromisoformat(iso)
        if t.tzinfo is None:
            t = t.replace(tzinfo=TEHRAN)
        return (datetime.now(TEHRAN) - t).total_seconds() / 3600
    except (TypeError, ValueError):
        return None


def site(prev):
    import panel
    if os.path.exists(panel.state_path()) and (_age_h(panel.status().get("checked")) or 99) > 0.2:
        panel.check()
    st = panel.status()
    if st.get("logged_in") and not str(st.get("detail", "")).startswith("unreachable"):
        r = _row("site", "سایت", "پنل مدیریت sepahanfelez.ir", "ok", "وارد است؛ هر ۲ ساعت تمدید می‌شود", "", prev.get("site"))
    elif str(st.get("detail", "")).startswith("unreachable"):
        r = _row("site", "سایت", "پنل مدیریت sepahanfelez.ir", "warn", "سایت موقتاً پاسخ نداد", "خودکار دوباره امتحان می‌شود", prev.get("site"))
    else:
        r = _row("site", "سایت", "پنل مدیریت sepahanfelez.ir", "broken",
                 "وارد نیست — انتشار مقاله و خبر متوقف است" if st.get("detail") != "never" else "هنوز وارد نشده — انتشار مقاله و خبر متوقف است",
                 "اتصالات و تنظیمات → «پنل سایت» → موبایل مدیر → «ورود» → کد پیامکی", prev.get("site"))
    return [r]


def google(prev):
    rows = []
    for key, name, f in (("gsc", "Google Search Console", "gsc.json"), ("ga4", "Google Analytics 4", "ga4.json")):
        d = read_json(os.path.join(DATA, "latest", f), {}) or {}
        age = _age_h(d.get("collected_at"))
        if d.get("status") == "ok" and age is not None and age < 50 and not d.get("stale"):
            rows.append(_row(key, "گوگل", name, "ok", f"داده‌ی تازه ({int(age)} ساعت پیش)", "", prev.get(key)))
        else:
            why = d.get("reason") or ("داده‌ی تازه نرسیده" + (f" ({int(age)} ساعت)" if age else ""))
            rows.append(_row(key, "گوگل", name, "broken", why,
                             "ایمیل حساب سرویس باید در Search Console/Analytics دسترسی داشته باشد؛ «ماشین‌ها» → «بررسی دوباره»", prev.get(key)))
    d = read_json(os.path.join(DATA, "latest", "drive.json"), {}) or {}
    age = _age_h(d.get("synced_at"))
    if d.get("status") == "ok" and age is not None and age < 26:
        rows.append(_row("drive", "گوگل", "گوگل درایو (عکس محصولات)", "ok", f"{d.get('photos')} عکس", "", prev.get("drive")))
    else:
        rows.append(_row("drive", "گوگل", "گوگل درایو (عکس محصولات)", "broken", d.get("reason") or "همگام‌سازی انجام نشده",
                         "پوشه باید با ایمیل حساب سرویس (Viewer) به اشتراک گذاشته شده باشد", prev.get("drive")))
    return rows


def news_sources(prev):
    st = read_json(os.path.join(DATA, "site", "news", "sources_status.json"), {}) or {}
    src = st.get("sources") or {}
    bad = [k for k, v in src.items() if not v.get("ok")]
    if not src:
        return [_row("news", "سایت", "منابع خبر", "warn", "هنوز خوانده نشده", "", prev.get("news"))]
    state = "ok" if len(bad) < len(src) / 2 else "warn"
    return [_row("news", "سایت", "منابع خبر", state,
                 f"{len(src) - len(bad)} از {len(src)} منبع در دسترس" + (f" (قطع: {'، '.join(bad)})" if bad else ""),
                 "" if state == "ok" else "منابع در dashboard/config/news_sources.json", prev.get("news"))]


def run(parts=("site", "google", "news", "social")):
    old = read_json(OUT, {}) or {}
    prev = {r["key"]: r for r in old.get("rows", [])}
    rows = {r["key"]: r for r in old.get("rows", [])
            if not ("social" in parts and r["key"].startswith("acct:")) and r["key"] not in {f"err:{x}" for x in parts}} if parts != ("site", "google", "news", "social") else {}
    for name in parts:
        try:
            for r in {"site": site, "google": google, "news": news_sources, "social": social}[name](prev):
                rows[r["key"]] = r
        except Exception as exc:                                        # noqa: BLE001
            rows[f"err:{name}"] = _row(f"err:{name}", "سیستم", f"بررسی {name}", "warn", f"{type(exc).__name__}: {str(exc)[:150]}", "", prev.get(f"err:{name}"))
    out = {"checked": _now(), "rows": list(rows.values())}
    out["broken"] = [r["key"] for r in out["rows"] if r["state"] == "broken"]
    out["notified"] = notify(out, prev, old.get("notified"))
    write_json(OUT, out)
    return out


def notify(out, prev, last):
    """Each broken connection (or a warning that stops publishing) → a message from @sepahanfelezbot to
    SF_ALERT_MOBILE, repeated every 12 hours while it stays broken; «✅ دوباره سالم» when it is fixed."""
    import alert
    sent = None
    for r in out["rows"]:
        key = "conn:" + r["key"]
        transient = r["state"] == "warn" and (r["key"] == "site" or r["detail"].startswith("بررسی نشد"))
        never = r["group"] == "شبکه‌ها" and not r.get("last_ok")      # added but not connected yet: the dashboard shows it, no alarm
        if not never and (r["state"] == "broken" or (r["state"] == "warn" and not transient and r["group"] == "شبکه‌ها")):
            if alert.send(key, ("اتصال قطع: " if r["state"] == "broken" else "مانع انتشار: ") + r["name"],
                          r["detail"] + (f" (از {r['since'][:16].replace('T', ' ')})" if r.get("since") else ""), r["fix"], every_h=12):
                sent = _now()
        elif r["state"] == "ok":
            alert.resolved(key, r["name"])
    return sent or last


if __name__ == "__main__":
    parts = tuple(sys.argv[1:]) or ("site", "google", "news", "social")
    res = run(parts)
    for r in res["rows"]:
        print(f"{ {'ok': '✓', 'warn': '!', 'broken': '✗', 'missing': '—'}[r['state']]} {r['name']}: {r['detail']}")
