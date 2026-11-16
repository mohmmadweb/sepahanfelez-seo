"""
Alerts to the person who fixes things, through the company's own Telegram bot (@sepahanfelezbot).

Who: the chat in SF_ALERT_CHAT_ID (.env), else the chat remembered in dashboard/data/alert_chat.json,
else TELEGRAM_ADMIN_CHAT_ID. The bot token is SF_ALERT_BOT_TOKEN in this project's .env. Nothing is read
from the price bot's folder: this project only needs its own .env (SF_ALERT_MOBILE is shown in the UI).

    alert.send(key, title, detail, fix)   # once per key per `every_h` hours (default 6)
    alert.resolved(key, title)            # «✅ وصل شد» once, when a key that alerted is healthy again
"""

import json
import os
import re
import socket
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "dashboard"))
from sf.env import get, load_env  # noqa: E402
from sf.util import DATA, read_json, write_json  # noqa: E402

load_env()
CHAT_FILE = os.path.join(DATA, "alert_chat.json")
SENT = os.path.join(DATA, "alerts_sent.json")
LOG = os.path.join(DATA, "alerts_log.jsonl")
TEHRAN = timezone(timedelta(hours=3, minutes=30))
DASH = "https://sepahanfelezseo.lenzit.ir:9444/#integrations"


def _digits(m):
    d = re.sub(r"\D", "", (m or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
    return "0" + d[2:] if d.startswith("98") else d


def token():
    return get("SF_ALERT_BOT_TOKEN", "")


def chat_id():
    saved = read_json(CHAT_FILE, {}) or {}
    return get("SF_ALERT_CHAT_ID", "") or saved.get("chat") or get("TELEGRAM_ADMIN_CHAT_ID", "") or None


def _post(text):
    import requests
    import urllib3.util.connection
    urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET     # IPv6 to Telegram hangs from this server
    tok, chat = token(), chat_id()
    if not (tok and chat):
        return False, "ربات یا گیرنده پیدا نشد (SF_ALERT_BOT_TOKEN و SF_ALERT_CHAT_ID در .env)"
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=25,
                      data={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"})
    return r.ok, r.text[:200]


def _esc(t):
    return str(t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _log(row):
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def send(key, title, detail="", fix="", every_h=6):
    """One alert per key per every_h hours; returns True if a message went out."""
    now = datetime.now(TEHRAN)
    sent = read_json(SENT, {}) or {}
    last = (sent.get(key) or {}).get("at")
    if last and now - datetime.fromisoformat(last) < timedelta(hours=every_h):
        return False
    text = (f"⚠️ <b>سپاهان فلز — {_esc(title)}</b>\n\n{_esc(detail)}" + (f"\n\n<b>کار لازم:</b> {_esc(fix)}" if fix else "") +
            f"\n\n{DASH}\n<i>{now.strftime('%Y-%m-%d %H:%M')}</i>")
    try:
        ok, info = _post(text)
    except Exception as exc:                                            # noqa: BLE001
        ok, info = False, f"{type(exc).__name__}: {exc}"
    _log({"at": now.isoformat(timespec="minutes"), "key": key, "title": title, "ok": ok, "info": "" if ok else info})
    if ok:
        sent[key] = {"at": now.isoformat(timespec="minutes"), "title": title, "open": True}
        write_json(SENT, sent)
    return ok


def resolved(key, title):
    sent = read_json(SENT, {}) or {}
    if not (sent.get(key) or {}).get("open"):
        return False
    try:
        ok, _ = _post(f"✅ <b>سپاهان فلز — {_esc(title)}</b>\nدوباره سالم است.")
    except Exception:                                                   # noqa: BLE001
        ok = False
    if ok:
        sent[key]["open"] = False
        write_json(SENT, sent)
    return ok


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        ok, info = _post("✅ <b>سپاهان فلز</b>\nاز این به بعد اگر اتصالی قطع شود یا انتشاری در سایت یا شبکه‌ها گیر کند، همین‌جا خبر می‌دهم.\n\n" + DASH)
        print("sent" if ok else f"failed: {info}")
    else:
        print("chat:", "found" if chat_id() else "missing", "· token:", "ok" if token() else "missing")
