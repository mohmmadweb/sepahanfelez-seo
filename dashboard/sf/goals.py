"""
«برنامه» — month → week → day goals with a number to hit, measured by code every day.

Same contract as the Lenzit conductor: code computes every number; the daily brief (brief.py)
only explains why and what we do about it. Periods follow the Iranian calendar: the Jalali
month, the Saturday–Friday week, and today.

Each goal: {id, title, metric, op: ">="|"<=", target}. Status:
  رسید (met) · در مسیر (on track) · عقب (behind: progress clearly below elapsed time)
  · نرسید (period over, not met) · سنجیده نشده (metric not measurable yet, e.g. no Search Console)
Targets live in config/goals.json (created with defaults; editable from the dashboard).
"""

import json
import os
from datetime import date, datetime, timedelta

import jdatetime

from .util import CONFIG, DATA, now_tehran, read_json, today_str, write_json

PATH = os.path.join(CONFIG, "goals.json")
BASE = os.path.join(DATA, "goals", "baselines.json")

DEFAULTS = {
    "month": [
        {"id": "m-health", "title": "امتیاز سلامت سئو دست‌کم ۷۰", "metric": "health", "op": ">=", "target": 70},
        {"id": "m-critical", "title": "صفر مشکل بحرانی روی سایت", "metric": "critical_issues", "op": "<=", "target": 0},
        {"id": "m-price", "title": "قیمت‌ها حداکثر ۱ روز کهنه (به‌روزرسانی روزانه)", "metric": "price_age_days", "op": "<=", "target": 1},
        {"id": "m-products", "title": "دست‌کم ۲۰ صفحه‌ی محصول مستقل", "metric": "product_pages", "op": ">=", "target": 20},
        {"id": "m-top20", "title": "دست‌کم ۳ کلمه‌ی کلیدی اصلی در ۲۰ نتیجه‌ی اول", "metric": "serp_top20", "op": ">=", "target": 3},
        {"id": "m-networks", "title": "دست‌کم ۵ شبکه وصل و آماده‌ی انتشار", "metric": "networks_connected", "op": ">=", "target": 5},
        {"id": "m-gsc", "title": "سرچ کنسول وصل و داده‌ی واقعی در داشبورد", "metric": "gsc_connected", "op": ">=", "target": 1},
        {"id": "m-articles", "title": "دست‌کم ۱۲ مقاله‌ی تازه روی سایت", "metric": "articles_published", "op": ">=", "target": 12},
    ],
    "week": [
        {"id": "w-stories", "title": "همه‌ی استوری‌های برنامه‌ی این هفته منتشر شود", "metric": "stories_vs_plan_pct", "op": ">=", "target": 90},
        {"id": "w-channel", "title": "همه‌ی پست‌های کانال این هفته منتشر شود", "metric": "channel_vs_plan_pct", "op": ">=", "target": 90},
        {"id": "w-articles", "title": "مقاله‌های برنامه‌ی این هفته منتشر شود", "metric": "articles_vs_plan_pct", "op": ">=", "target": 100},
        {"id": "w-candidates", "title": "رقبای تازه‌ی کشف‌شده بررسی شوند (افزودن یا نادیده)", "metric": "candidates_pending", "op": "<=", "target": 5},
        {"id": "w-alerts", "title": "هیچ هشدار یا محدودیت از هیچ شبکه‌ای", "metric": "platform_alerts", "op": "<=", "target": 0},
    ],
    "day": [
        {"id": "d-machines", "title": "همه‌ی ماشین‌ها امروز سر وقت و بی‌خطا", "metric": "machines_ok_pct", "op": ">=", "target": 100},
        {"id": "d-stories", "title": "استوری‌های برنامه‌ی امروز", "metric": "stories_today_vs_plan_pct", "op": ">=", "target": 100},
        {"id": "d-channel", "title": "پست‌های کانال امروز", "metric": "channel_today_vs_plan_pct", "op": ">=", "target": 100},
        {"id": "d-alerts", "title": "بدون هشدار پلتفرم امروز", "metric": "platform_alerts", "op": "<=", "target": 0},
    ],
}
UNITS = {"health": "", "critical_issues": "مشکل", "price_age_days": "روز", "product_pages": "صفحه", "serp_top20": "کلمه",
         "networks_connected": "شبکه", "gsc_connected": "", "articles_published": "مقاله", "candidates_pending": "سایت",
         "platform_alerts": "هشدار", "machines_ok_pct": "٪"}


def config():
    c = read_json(PATH)
    if not c:
        write_json(PATH, DEFAULTS)
        c = DEFAULTS
    return c


def set_target(goal_id, target):
    c = config()
    for kind in c:
        for g in c[kind]:
            if g["id"] == goal_id:
                old = g["target"]
                g["target"] = target
                write_json(PATH, c)
                return {"id": goal_id, "old": old, "new": target}
    raise KeyError(goal_id)


# ---------------------------------------------------------------- periods (Iranian)
def periods(d=None):
    d = d or date.fromisoformat(today_str())
    j = jdatetime.date.fromgregorian(date=d)
    m_start = jdatetime.date(j.year, j.month, 1).togregorian()
    nm = jdatetime.date(j.year + (j.month == 12), j.month % 12 + 1, 1).togregorian()
    m_end = nm - timedelta(days=1)
    w_start = d - timedelta(days=(d.weekday() - 5) % 7)          # Saturday
    w_end = w_start + timedelta(days=6)
    month_fa = j.j_months_fa[j.month - 1]
    return {
        "month": (m_start, m_end, f"{month_fa} {j.year}"),
        "week": (w_start, w_end, f"هفته‌ی {jdatetime.date.fromgregorian(date=w_start).day} تا {jdatetime.date.fromgregorian(date=w_end).day} {jdatetime.date.fromgregorian(date=w_end).j_months_fa[jdatetime.date.fromgregorian(date=w_end).month - 1]}"),
        "day": (d, d, f"امروز {j.day} {month_fa}"),
    }


# ---------------------------------------------------------------- metrics (code only)
def _published(since, until, kinds=None, nets=None):
    pub = os.path.join(DATA, "published")
    n = 0
    if os.path.isdir(pub):
        for f in os.listdir(pub):
            net = f[:-6]
            if nets and net not in nets:
                continue
            for line in open(os.path.join(pub, f), encoding="utf-8"):
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("status") not in ("published", "sent-to-operator"):
                    continue
                if kinds and r.get("kind") not in kinds:
                    continue
                if since.isoformat() <= r["ts"][:10] <= until.isoformat():
                    n += 1
    return n


def _planned(since, until, kind):
    plan = read_json(os.path.join(DATA, "latest", "content_plan.json"), {}) or {}
    return sum(1 for i in plan.get("items", []) if i["kind"] == kind and since.isoformat() <= i["date"] <= until.isoformat())


def measure(metric, since, until):
    L = lambda n: read_json(os.path.join(DATA, "latest", f"{n}.json"), {}) or {}  # noqa: E731
    if metric == "health":
        return L("issues").get("health")
    if metric == "critical_issues":
        return sum(1 for i in L("issues").get("issues", []) if i["severity"] == "critical" and i.get("source") != "manual")
    if metric == "price_age_days":
        p = next((x for x in L("crawl").get("pages", []) if x.get("type") == "price"), {})
        return (p.get("price_freshness") or {}).get("freshest_days")
    if metric == "product_pages":
        return sum(1 for x in L("crawl").get("pages", []) if x.get("type") == "product" and x.get("status") == 200)
    if metric == "serp_top20":
        kws = L("serp").get("keywords", [])
        return sum(1 for k in kws if k.get("our_position") and k["our_position"] <= 20) if kws else None
    if metric == "networks_connected":
        st = read_json(os.path.join(DATA, "social_status.json"), {}) or {}
        return len({v.get("net") or k for k, v in st.items() if v.get("logged_in")})
    if metric == "gsc_connected":
        return 1 if L("gsc").get("status") == "ok" else 0
    if metric == "articles_published":
        return _published(since, until, kinds={"article"}, nets={"site"})
    if metric in ("stories_vs_plan_pct", "stories_today_vs_plan_pct"):
        plan = _planned(since, min(until, date.fromisoformat(today_str())), "story")
        return None if not plan else round(100 * _published(since, until, kinds={"story"}) / plan)
    if metric in ("channel_vs_plan_pct", "channel_today_vs_plan_pct"):
        plan = _planned(since, min(until, date.fromisoformat(today_str())), "telegram")
        return None if not plan else round(100 * _published(since, until, kinds={"post", "message"},
                                                             nets={"telegram", "bale", "eitaa", "rubika"}) / plan)
    if metric == "articles_vs_plan_pct":
        plan = _planned(since, min(until, date.fromisoformat(today_str())), "article")
        return None if not plan else round(100 * _published(since, until, kinds={"article"}, nets={"site"}) / plan)
    if metric == "candidates_pending":
        return len((read_json(os.path.join(DATA, "competitor_candidates.json"), {}) or {}).get("candidates", {}))
    if metric == "platform_alerts":
        al = read_json(os.path.join(DATA, "social_alerts.json"), {}) or {}
        now = now_tehran().isoformat()
        return sum(1 for a in al.values() if not a.get("cleared") and a.get("until", "") > now)
    if metric == "machines_ok_pct":
        m = read_json(os.path.join(DATA, "machines.json"), {}) or {}
        today = [s for s in (m.get("steps") or {}).values() if s.get("finished", "")[:10] == today_str()]
        return round(100 * sum(1 for s in today if s["ok"]) / len(today)) if today else None
    return None


def _status(g, value, base, time_pct, over):
    if value is None:
        return "unmeasured", None
    met = value >= g["target"] if g["op"] == ">=" else value <= g["target"]
    if met:
        return "met", 100
    if g["op"] == ">=":
        start = base if base is not None and base < g["target"] else 0
        prog = (value - start) / ((g["target"] - start) or 1)
    else:
        start = base if base is not None and base > g["target"] else value
        prog = (start - value) / ((start - g["target"]) or 1)
    prog = max(0.0, min(0.99, prog))
    if over:
        return "missed", round(prog * 100)
    return ("behind" if prog < time_pct - 0.2 else "on_track"), round(prog * 100)


def evaluate():
    c = config()
    base = read_json(BASE, {}) or {}
    now = now_tehran()
    out = {"checked_at": now.isoformat(timespec="seconds"), "periods": []}
    for kind, (start, end, label) in periods().items():
        # time is counted from when tracking of this period began (goals added mid-month must not
        # start out «behind» just because half the month had already passed)
        tkey = f"{kind}:{start.isoformat()}:__since"
        since = date.fromisoformat(base.setdefault(tkey, today_str()))
        days = (end - since).days + 1
        elapsed = (date.fromisoformat(today_str()) - since).days + (now.hour / 24)
        time_pct = min(1.0, max(0.0, elapsed / days))
        rows = []
        for g in c.get(kind, []):
            v = measure(g["metric"], start, end)
            key = f"{kind}:{start.isoformat()}:{g['id']}"
            if v is not None and key not in base:
                base[key] = v
            st, prog = _status(g, v, base.get(key), time_pct, over=False)
            rows.append({**g, "value": v, "baseline": base.get(key), "status": st, "progress": prog, "unit": UNITS.get(g["metric"], "")})
        measured = [r for r in rows if r["status"] != "unmeasured"]
        avg = round(sum(r["progress"] for r in measured) / len(measured)) if measured else None
        n = {s: sum(1 for r in rows if r["status"] == s) for s in ("met", "on_track", "behind", "missed", "unmeasured")}
        verdict = "met" if measured and n["met"] == len(measured) else ("behind" if n["behind"] else "on_track")
        out["periods"].append({"kind": kind, "label": label, "start": start.isoformat(), "end": end.isoformat(),
                               "tracked_since": since.isoformat(),
                               "time_pct": round(time_pct * 100), "progress": avg, "verdict": verdict, "counts": n, "goals": rows})
    write_json(BASE, base)
    write_json(os.path.join(DATA, "latest", "goals.json"), out)
    write_json(os.path.join(DATA, "goals", f"{today_str()}.json"), out)
    d = out["periods"][-1]["counts"]
    return f"امروز: {d['met']} رسید، {d['on_track']} در مسیر، {d['behind']} عقب، {d['unmeasured']} سنجیده نشده"
