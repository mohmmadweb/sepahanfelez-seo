"""
Safety rails for every action on a network — the rules that kept @lenzit_org alive
(content-engine/machines/admin/publisher.py and engage/engage.py):

- one process at a time per network (fcntl lock on automation/sessions/<net>.lock)
- daily caps and a minimum gap per action type (dashboard/config/social_safety.json)
- any pushback from the platform (challenge, feedback/action block, rate limit, logout)
  pauses *every* action on that network for 24 hours (data/social_alerts.json)
- an upload that errors after it may already have gone through is verified, never blindly re-sent
"""

import contextlib
import fcntl
import json
import os
import time
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESSIONS = os.path.join(ROOT, "automation", "sessions")
DATA = os.path.join(ROOT, "dashboard", "data")
CFG_PATH = os.path.join(ROOT, "dashboard", "config", "social_safety.json")
ALERTS = os.path.join(DATA, "social_alerts.json")
ACTLOG = os.path.join(DATA, "social_actions.jsonl")
TEHRAN = timezone(timedelta(hours=3, minutes=30))

DEFAULTS = {
    "pause_hours_after_alert": 24,
    "networks": {
        # caps per Tehran day; gap = minimum minutes between two actions of that kind
        "instagram": {"post": [2, 60], "story": [6, 20], "message": [5, 30], "comment": [4, 45], "like": [20, 6]},
        "telegram": {"post": [12, 5], "story": [4, 30], "message": [30, 1]},
        "bale": {"post": [12, 5], "story": [4, 30], "message": [30, 1]},
        "eitaa": {"post": [12, 5], "story": [4, 30], "message": [30, 1]},
        "rubika": {"post": [12, 5], "story": [4, 30], "message": [30, 1]},
        "whatsapp": {"post": [6, 10], "story": [4, 30], "message": [15, 3]},
        "linkedin": {"post": [2, 120], "message": [0, 0]},
    },
}


class Blocked(Exception):
    """Refused by a safety rule (not an error from the platform)."""


def config():
    try:
        with open(CFG_PATH, encoding="utf-8") as fh:
            c = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
        with open(CFG_PATH, "w", encoding="utf-8") as fh:
            json.dump(DEFAULTS, fh, ensure_ascii=False, indent=1)
        c = DEFAULTS
    return c


def now():
    return datetime.now(TEHRAN)


@contextlib.contextmanager
def lock(net, wait_sec=600):
    os.makedirs(SESSIONS, mode=0o700, exist_ok=True)
    fh = open(os.path.join(SESSIONS, f"{net}.lock"), "w")
    t0 = time.time()
    while True:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.time() - t0 > wait_sec:
                fh.close()
                raise Blocked(f"نشست {net} دست یک کار دیگر است؛ کمی بعد دوباره امتحان کنید.")
            time.sleep(3)
    try:
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def _alerts():
    try:
        with open(ALERTS, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def active_alert(net):
    a = _alerts().get(net)
    if not a or a.get("cleared"):
        return None
    until = datetime.fromisoformat(a["until"])
    return a if until > now() else None


def raise_alert(net, kind, detail):
    a = _alerts()
    hours = config().get("pause_hours_after_alert", 24)
    a[net] = {"at": now().isoformat(timespec="seconds"), "until": (now() + timedelta(hours=hours)).isoformat(timespec="seconds"),
              "kind": kind, "detail": str(detail)[:300], "cleared": False}
    os.makedirs(DATA, exist_ok=True)
    with open(ALERTS, "w", encoding="utf-8") as fh:
        json.dump(a, fh, ensure_ascii=False, indent=1)


def clear_alert(net):
    a = _alerts()
    if net in a:
        a[net]["cleared"] = True
        with open(ALERTS, "w", encoding="utf-8") as fh:
            json.dump(a, fh, ensure_ascii=False, indent=1)


def _log_rows():
    rows = []
    if os.path.exists(ACTLOG):
        with open(ACTLOG, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def check(net, kind):
    """Raise Blocked with a Persian reason if this action may not run now."""
    a = active_alert(net)
    if a:
        raise Blocked(f"{net} به‌خاطر هشدار «{a['kind']}» تا {a['until'][:16].replace('T', ' ')} متوقف است.")
    cap, gap = (config()["networks"].get(net, {}).get(kind) or [0, 0])
    if cap <= 0:
        raise Blocked(f"اقدام «{kind}» برای {net} خاموش است (social_safety.json).")
    today = now().date().isoformat()
    mine = [r for r in _log_rows() if r["net"] == net and r["kind"] == kind and r.get("ok")]
    n_today = sum(1 for r in mine if r["ts"][:10] == today)
    if n_today >= cap:
        raise Blocked(f"سقف روزانه‌ی «{kind}» در {net} ({cap}) پر شده است.")
    if mine:
        last = datetime.fromisoformat(mine[-1]["ts"])
        wait = gap * 60 - (now() - last).total_seconds()
        if wait > 0:
            raise Blocked(f"حداقل فاصله‌ی دو «{kind}» در {net} {gap} دقیقه است؛ {int(wait // 60) + 1} دقیقه‌ی دیگر.")


def note(net, kind, ok, detail=""):
    os.makedirs(DATA, exist_ok=True)
    with open(ACTLOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": now().isoformat(timespec="seconds"), "net": net, "kind": kind, "ok": ok,
                             "detail": str(detail)[:200]}, ensure_ascii=False) + "\n")
