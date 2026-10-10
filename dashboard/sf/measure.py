"""
Result of every published piece: views/engagement at 24 h and at 7 days, against a goal.

Goal = the median of the same network + format (Lenzit's «بیشتر از معمولِ ریل‌های ما»), with a
small floor while there is no history. Verdict at 7 days: رسید / نرسید. Reads only, never posts;
uses the network's lock and at most 12 reads per network per day.

  telegram   message views + forwards + reactions (Telethon)
  instagram  play/like/comment counts (instagrapi media_info)
  others     no reliable read API → «قابل سنجش نیست» (kept honest instead of guessed)
"""

import json
import os
import statistics
import sys
from datetime import datetime, timedelta

from .util import DATA, now_tehran, read_json, write_json

PUB = os.path.join(DATA, "published")
OUT = os.path.join(DATA, "results.json")
FLOOR = {"telegram": 30, "instagram": 20}
MAX_READS = 12


def _rows(net):
    path = os.path.join(PUB, f"{net}.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return [r for r in out if r.get("status") == "published" and r.get("message_id")]


def _key(r):
    return f"{r['network']}:{r['message_id']}"


def _due(res, r, now):
    age = now - datetime.fromisoformat(r["ts"])
    have = res.get(_key(r), {})
    if age >= timedelta(days=7) and "d7" not in have:
        return "d7"
    if timedelta(hours=24) <= age < timedelta(days=7) and "h24" not in have:
        return "h24"
    return None


def _telegram_reads(todo):
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.join(root, "automation", "social"))
    import login as L
    import safety
    import accounts
    out = {}
    by_acct = {}
    for r, w in todo:
        by_acct.setdefault(r.get("account"), []).append((r, w))
    for acct_id, items in by_acct.items():
        L.use(accounts.get_account(acct_id) if acct_id else accounts.default("telegram"))
        if not L.has_session("telegram", "user.session"):
            continue
        out.update(_telegram_one(L, safety, items))
    L.use(None)
    return out


def _telegram_one(L, safety, todo):
    out = {}
    with safety.lock(f"telegram-{(L.ACCT or {}).get('id')}", wait_sec=60):
        client = L._telegram_client()
        client.connect()
        try:
            if not client.is_user_authorized():
                return {}
            for r, _ in todo:
                url = r.get("url") or ""
                chan = url.split("t.me/")[1].split("/")[0] if "t.me/" in url else None
                if not chan:
                    continue
                m = client.get_messages(chan, ids=int(r["message_id"]))
                if m:
                    reacts = sum(x.count for x in (m.reactions.results if m.reactions else []))
                    out[_key(r)] = {"views": m.views or 0, "forwards": m.forwards or 0, "reactions": reacts}
        finally:
            client.disconnect()
    return out


def _instagram_reads(todo):
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.join(root, "automation", "social"))
    import login as L
    import safety
    import accounts
    out = {}
    by_acct = {}
    for r, w in todo:
        by_acct.setdefault(r.get("account"), []).append((r, w))
    for acct_id, items in by_acct.items():
        L.use(accounts.get_account(acct_id) if acct_id else accounts.default("instagram"))
        if not L.has_session("instagram", "session.json") or safety.active_alert("instagram", (L.ACCT or {}).get("id")):
            continue
        out.update(_instagram_one(L, safety, items))
    L.use(None)
    return out


def _instagram_one(L, safety, todo):
    out = {}
    with safety.lock(f"instagram-{(L.ACCT or {}).get('id')}", wait_sec=60):
        cl = L._ig_client()
        for r, _ in todo:
            if r.get("kind") != "post":
                continue
            m = cl.media_info(r["message_id"])
            out[_key(r)] = {"views": m.play_count or m.view_count or 0, "likes": m.like_count or 0,
                            "comments": m.comment_count or 0}
        cl.dump_settings(L.IG_SESSION())
    return out


def run():
    from . import trace
    res = read_json(OUT, {}) or {}
    now = now_tehran()
    done = 0
    for net, reader in (("telegram", _telegram_reads), ("instagram", _instagram_reads)):
        todo = [(r, w) for r in _rows(net) if (w := _due(res, r, now))][:MAX_READS]
        if not todo:
            continue
        try:
            got = reader(todo)
        except Exception as exc:                                       # noqa: BLE001
            got = {}
            print(f"  {net}: {type(exc).__name__}: {exc}")
        for r, when in todo:
            k = _key(r)
            if k not in got:
                continue
            e = res.setdefault(k, {"network": net, "kind": r.get("kind"), "ts": r["ts"], "plan_ref": r.get("plan_ref")})
            e[when] = {**got[k], "at": now.isoformat(timespec="seconds")}
            done += 1
    # goals and verdicts from the same network+format median
    for k, e in res.items():
        peers = [x["d7"]["views"] for x in res.values()
                 if x is not e and x["network"] == e["network"] and x["kind"] == e["kind"] and "d7" in x]
        base = statistics.median(peers) if len(peers) >= 3 else None
        e["goal_views"] = max(FLOOR.get(e["network"], 20), round(base)) if base else FLOOR.get(e["network"], 20)
        e["goal_basis"] = f"میانه‌ی {len(peers)} {e['kind']} قبلی" if base else "کف اولیه (هنوز سابقه نیست)"
        if "d7" in e and "verdict" not in e:
            e["verdict"] = "met" if e["d7"]["views"] >= e["goal_views"] else "missed"
            if e.get("plan_ref"):
                trace.step(e["plan_ref"], "measure", "نتیجه‌ی ۷ روزه",
                           detail=f"{e['d7']['views']} بازدید؛ هدف {e['goal_views']} ({e['goal_basis']})",
                           decision="رسید" if e["verdict"] == "met" else "نرسید — در تحلیل امروز بررسی می‌شود")
    write_json(OUT, res)
    return f"{done} سنجش تازه · {sum(1 for e in res.values() if 'd7' in e)} محتوای ۷ روزه"
