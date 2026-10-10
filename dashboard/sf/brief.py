"""
«تحلیل امروز» — one short brief per day in plain Persian: headline, 4–8 bullets, 4 lights,
and «کارهای تو و هشدارها». Snapshot per day in data/briefs/<date>.json so any past day can be
reopened from the dashboard's day picker.

Contract (from the Lenzit conductor): code computes every number and every status; the model only
phrases them as «واقعیت — چرا — چه می‌کنیم». One `claude -p` call, Sonnet, no tools, no MCP,
≤ $0.5 per call and ≤ $1 per day (ledger in data/briefs/cost.json). If the model is unavailable
or its answer fails validation, the bullets are written by code — the page never stays empty.
"""

import json
import os
import re
import subprocess
from datetime import date, timedelta

from .util import DATA, decode_url, jalali, now_tehran, read_json, today_str, write_json

CLAUDE = os.path.expanduser("~/.local/bin/claude")
BDIR = os.path.join(DATA, "briefs")
COST = os.path.join(BDIR, "cost.json")
MAX_USD_DAY = 1.0
L = lambda n: read_json(os.path.join(DATA, "latest", f"{n}.json"), {}) or {}  # noqa: E731


def _fa(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


# ---------------------------------------------------------------- facts (code only)
def facts():
    today = today_str()
    yday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    hist = read_json(os.path.join(DATA, "history.json"), []) or []
    t = next((h for h in reversed(hist) if h["date"] == today), {})
    y = next((h for h in reversed(hist) if h["date"] < today), {})
    iss = L("issues")
    log = read_json(os.path.join(DATA, "issues_log.json"), {}) or {}
    serp = L("serp")
    sh = read_json(os.path.join(DATA, "serp_history.json"), {}) or {}
    moves = []
    for kw, rows in sh.items():
        if len(rows) >= 2 and rows[-1]["date"] == today:
            a, b = rows[-2].get("pos"), rows[-1].get("pos")
            if a != b:
                moves.append({"kw": kw, "from": a, "to": b})
    cands = (read_json(os.path.join(DATA, "competitor_candidates.json"), {}) or {}).get("candidates", {})
    new_cands = sorted((c for c in cands.values() if c.get("new")), key=lambda c: -c["keyword_count"])
    comp = L("competitors")
    comp_new = sorted(((c["domain"], len(c.get("new_today") or [])) for c in comp.get("competitors", []) if c.get("new_today")),
                      key=lambda x: -x[1])
    goals = L("goals")
    plan = L("content_plan")
    planned_today = [i for i in plan.get("items", []) if i["date"] == today]
    pub_today = {}
    pdir = os.path.join(DATA, "published")
    if os.path.isdir(pdir):
        for f in os.listdir(pdir):
            for line in open(os.path.join(pdir, f), encoding="utf-8"):
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r["ts"][:10] == today and r.get("status") in ("published", "sent-to-operator"):
                    pub_today[r["network"]] = pub_today.get(r["network"], 0) + 1
    social = read_json(os.path.join(DATA, "social_status.json"), {}) or {}
    alerts = read_json(os.path.join(DATA, "social_alerts.json"), {}) or {}
    now = now_tehran().isoformat()
    health = read_json(os.path.join(DATA, "health.json"), {}) or {}
    changes = read_json(os.path.join(DATA, "changes", "changes.json"), []) or []
    results = read_json(os.path.join(DATA, "results.json"), {}) or {}
    return {
        "date": today, "jalali": jalali(),
        "health": {"today": t.get("health"), "yesterday": y.get("health")},
        "issues": {"critical": t.get("issues", {}).get("critical"), "high": t.get("issues", {}).get("high"),
                   "new_today": [v["title"] for v in log.values() if v.get("first_seen") == today and not v.get("resolved")][:5],
                   "resolved_today": [v["title"] for v in log.values() if v.get("resolved") == today][:5],
                   "top": [i["title"] for i in iss.get("issues", [])[:3]]},
        "price_age_days": t.get("price_age_days"),
        "pages": {"live": t.get("pages"), "articles": t.get("articles"), "products": t.get("products")},
        "search": {"provider": serp.get("provider"), "tracked": len(serp.get("keywords", [])),
                   "top20": sum(1 for k in serp.get("keywords", []) if k.get("our_position") and k["our_position"] <= 20),
                   "moves": moves[:6], "gsc": L("gsc").get("status") == "ok"},
        "competitors": {"new_candidates_today": [{"domain": c["domain"], "keywords": c["keyword_count"], "best": c["best_pos"]} for c in new_cands[:5]],
                        "candidates_pending": len(cands), "new_pages_today": comp_new[:5]},
        "goals": [{"period": p["label"], "counts": p["counts"], "behind": [g["title"] for g in p["goals"] if g["status"] == "behind"],
                   "unmeasured": [g["title"] for g in p["goals"] if g["status"] == "unmeasured"][:3]} for p in goals.get("periods", [])],
        "publishing": {"planned_today": len(planned_today), "published_today": pub_today,
                       "networks_connected": [k for k, v in social.items() if v.get("logged_in")]},
        "alerts": [{"net": k, "kind": a["kind"]} for k, a in alerts.items() if not a.get("cleared") and a.get("until", "") > now],
        "machines": {"all_ok": health.get("all_ok"), "failed": [s["name"] + ": " + (s["why"] or "")[:80] for s in health.get("steps", [])
                                                                 if s["verdict"] in ("error", "missed", "auth")],
                     "outcomes": health.get("outcomes", [])},
        "site_changes_today": [c["title"] for c in changes if c["date"] == today and c["kind"] == "site"][:6],
        "change_verdicts": [{"title": c["title"], "verdict": c["verdict"]} for c in changes if c.get("evaluated_at", "")[:10] == today][:5],
        "content_results_7d": {"met": sum(1 for e in results.values() if e.get("verdict") == "met"),
                               "missed": sum(1 for e in results.values() if e.get("verdict") == "missed")},
    }


def lights(f):
    h = f["health"]["today"]
    top20 = f["search"]["top20"]
    pub = sum(f["publishing"]["published_today"].values())
    plan = f["publishing"]["planned_today"]
    conn = len(f["publishing"]["networks_connected"])
    return [
        {"id": "site", "name": "سلامت سایت", "state": "good" if (h or 0) >= 70 else "warn" if (h or 0) >= 50 else "bad",
         "text": f"{_fa(h)} از ۱۰۰" if h is not None else "سنجیده نشد"},
        {"id": "search", "name": "دیده‌شدن در گوگل", "state": "good" if top20 >= 3 else "warn" if top20 >= 1 else "bad",
         "text": f"{_fa(top20)} از {_fa(f['search']['tracked'])} کلمه در ۲۰ نتیجه‌ی اول"},
        {"id": "publish", "name": "انتشار محتوا",
         "state": "bad" if not conn else ("good" if plan and pub >= plan else "warn" if pub else ("good" if not plan else "bad")),
         "text": "هنوز هیچ شبکه‌ای وصل نیست" if not conn else f"{_fa(pub)} از {_fa(plan)} برنامه‌ی امروز"},
        {"id": "machines", "name": "ماشین‌ها", "state": "good" if f["machines"]["all_ok"] else "bad",
         "text": "همه سالم" if f["machines"]["all_ok"] else (f"{_fa(len(f['machines']['failed']) + len(f['machines']['outcomes']))} مشکل"
                                                              if f["machines"]["failed"] or f["machines"]["outcomes"] else "یک سرویس خاموش است")},
    ]


def tasks(f):
    """Everything that needs the owner, most important first. `tab` = where in the dashboard to act."""
    env = {}
    p = os.path.join(os.path.dirname(os.path.dirname(DATA)), ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            m = re.match(r"^([A-Z0-9_]+)=(.+)$", line.strip())
            if m:
                env[m.group(1)] = True
    out = []
    for a in f["alerts"]:
        out.append({"sev": "critical", "title": f"{a['net']} به‌خاطر هشدار «{a['kind']}» متوقف است", "why": "تا ۲۴ ساعت هیچ کاری در این شبکه انجام نمی‌شود", "tab": "integrations"})
    for m in f["machines"]["failed"]:
        out.append({"sev": "high", "title": "ماشین خطا داد: " + m, "why": "نگهبان یک‌بار دوباره اجرا می‌کند؛ اگر خطای ورود است کار شماست", "tab": "machines"})
    if not env.get("CLOUDFLARE_TUNNEL_TOKEN"):
        out.append({"sev": "high", "title": "توکن تونل Cloudflare را بگذارید", "why": "تا آن موقع داشبورد زنده روی دامنه نیست و ورود لینکدین کار نمی‌کند", "tab": "integrations"})
    if not f["search"]["gsc"]:
        out.append({"sev": "high", "title": "سرچ کنسول را وصل کنید", "why": "بدون آن کلیک، ایمپرشن و رتبه‌ی واقعی گوگل نداریم", "tab": "integrations"})
    if not env.get("GA4_PROPERTY_ID"):
        out.append({"sev": "medium", "title": "Property ID آنالیتیکس (GA4_PROPERTY_ID)", "why": "ترافیک و تماس‌ها به تفکیک صفحه", "tab": "integrations"})
    conn = set(f["publishing"]["networks_connected"])
    for net, fa, need in (("telegram", "تلگرام", "TELEGRAM_API_ID"), ("instagram", "اینستاگرام", "INSTAGRAM_USERNAME"),
                          ("linkedin", "لینکدین", "LINKEDIN_CLIENT_ID"), ("bale", "بله", None), ("eitaa", "ایتا", None),
                          ("rubika", "روبیکا", None), ("whatsapp", "واتساپ", None)):
        if net not in conn:
            out.append({"sev": "medium", "title": f"ورود به {fa}" + (f" (اول {need} در تنظیمات)" if need and not env.get(need) else ""),
                        "why": "تا وصل نشود، برنامه‌ی انتشار این شبکه اجرا نمی‌شود", "tab": "integrations"})
    if f["competitors"]["candidates_pending"]:
        out.append({"sev": "low", "title": f"{_fa(f['competitors']['candidates_pending'])} رقیب تازه منتظر بررسی (افزودن/نادیده)",
                    "why": "رقبای کشف‌شده در نتایج جستجو", "tab": "competitors"})
    known = read_json(os.path.join(os.path.dirname(DATA), "config", "known_issues.json"), {}) or {}
    for k in known.get("issues", []):
        if k.get("status") == "waiting-owner" and k["id"] != "gsc-ga4":      # GSC/GA4 already listed above
            out.append({"sev": k["severity"], "title": k["title"], "why": k["fix"], "tab": "issues"})
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(out, key=lambda x: order.get(x["sev"], 4))


def _fallback_bullets(f):
    b = []
    h = f["health"]
    if h["today"] is not None:
        d = (h["today"] - h["yesterday"]) if h["yesterday"] is not None else None
        b.append(f"امتیاز سلامت سایت {_fa(h['today'])} است" + (f" ({'+' if d > 0 else ''}{_fa(d)} نسبت به دیروز)" if d else "")
                 + (f" — مهم‌ترین مشکل: {f['issues']['top'][0]}" if f["issues"]["top"] else "") + ".")
    if f["price_age_days"]:
        b.append(f"جدیدترین قیمت سایت {_fa(f['price_age_days'])} روز پیش است — جدول قیمت باید هر روز ۱۲:۳۰ به‌روز شود.")
    s = f["search"]
    b.append(f"{_fa(s['top20'])} از {_fa(s['tracked'])} کلمه‌ی کلیدی اصلی در ۲۰ نتیجه‌ی اول است"
             + (" — صفحه‌های هدف باید قوی‌تر و پرلینک‌تر شوند." if s["top20"] < 3 else "."))
    if f["competitors"]["new_candidates_today"]:
        c = f["competitors"]["new_candidates_today"][0]
        b.append(f"رقیب تازه: {c['domain']} در {_fa(c['keywords'])} کلمه‌ی ما بالا آمده — در تب رقبا بررسی کنید.")
    if f["competitors"]["new_pages_today"]:
        d, n = f["competitors"]["new_pages_today"][0]
        b.append(f"{d} امروز {_fa(n)} صفحه‌ی تازه منتشر کرد.")
    if not f["publishing"]["networks_connected"]:
        b.append("هنوز هیچ شبکه‌ای وصل نیست؛ برنامه‌ی انتشار امروز اجرا نمی‌شود — از تب اتصالات وارد شوید.")
    if not f["machines"]["all_ok"]:
        b.append("یکی از ماشین‌ها مشکل داشت؛ نگهبان دوباره اجرایش می‌کند — جزئیات در بخش ماشین‌ها.")
    for c in f["site_changes_today"][:2]:
        b.append(f"تغییر روی سایت دیده شد: {c} — اثرش روی رتبه ۱۴ روز دیگر سنجیده می‌شود.")
    return b[:8]


def _llm(f):
    led = read_json(COST, {}) or {}
    day = led.setdefault(today_str(), {"usd": 0.0, "runs": 0})
    if day["usd"] >= MAX_USD_DAY or not os.path.exists(CLAUDE):
        return None, "budget-or-missing"
    prompt = (
        "تو برای صاحب کارخانه‌ی «سپاهان فلز» (صنایع مفتولی طلوع سپاهان، اصفهان؛ سایت sepahanfelez.ir) گزارش روزانه‌ی سئو و محتوا را "
        "به فارسی خیلی ساده می‌نویسی. او اصطلاح فنی بلد نیست. فقط از عددها و واقعیت‌های JSON زیر استفاده کن؛ هیچ عددی نساز.\n"
        "خروجی فقط یک JSON: {\"headline\": \"یک جمله‌ی کوتاه درباره‌ی وضع امروز\", \"bullets\": [\"…\", …]}\n"
        "۴ تا ۸ بولت. هر بولت یک جمله (حداکثر ۳۰ کلمه) به شکل «چه شد — چرا — چه می‌کنیم/چه باید کرد». "
        "مهم‌ترین چیز اول. ارقام فارسی. بدون ایموجی، بدون انگلیسی مگر نام دامنه.\n\nواقعیت‌های امروز:\n"
        + json.dumps(f, ensure_ascii=False))
    cmd = [CLAUDE, "-p", prompt, "--model", "sonnet", "--max-turns", "1", "--output-format", "json", "--strict-mcp-config",
           "--disallowedTools", "Bash", "Write", "Edit", "Read", "Glob", "Grep", "NotebookEdit", "WebFetch", "WebSearch", "Agent", "Task",
           "--max-budget-usd", "0.5"]
    try:
        r = subprocess.run(cmd, cwd=os.path.dirname(DATA), capture_output=True, text=True, timeout=300)
        res = json.loads(r.stdout or "{}")
        day["usd"] = round(day["usd"] + float(res.get("total_cost_usd") or 0), 4)
        day["runs"] += 1
        write_json(COST, dict(sorted(led.items())[-60:]))
        m = re.search(r"\{.*\}", str(res.get("result") or ""), re.S)
        out = json.loads(m.group(0)) if m else None
    except Exception as exc:                                           # noqa: BLE001
        return None, f"{type(exc).__name__}"
    if not isinstance(out, dict) or not isinstance(out.get("bullets"), list) or not out.get("headline"):
        return None, "invalid"
    bullets = [str(x).strip() for x in out["bullets"] if isinstance(x, str) and 8 < len(x) < 320][:8]
    if len(bullets) < 3:
        return None, "too-short"
    return {"headline": str(out["headline"])[:200], "bullets": bullets}, "ok"


def make():
    f = facts()
    lt = lights(f)
    llm, how = _llm(f)
    if not llm:
        llm = {"headline": ("همه‌ی ماشین‌ها کار کردند" if f["machines"]["all_ok"] else "یکی از ماشین‌ها مشکل داشت")
               + f"؛ امتیاز سلامت سایت {_fa(f['health']['today'])} است.",
               "bullets": _fallback_bullets(f)}
    day_goal = next((p for p in L("goals").get("periods", []) if p["kind"] == "day"), {})
    out = {"date": f["date"], "jalali": f["jalali"], "made_at": now_tehran().isoformat(timespec="seconds"),
           "written_by": "claude-sonnet" if how == "ok" else f"code ({how})", **llm, "lights": lt,
           "tasks": tasks(f), "day_verdict": day_goal.get("verdict"), "day_counts": day_goal.get("counts"), "facts": f}
    os.makedirs(BDIR, exist_ok=True)
    write_json(os.path.join(BDIR, f"{f['date']}.json"), out)
    write_json(os.path.join(DATA, "latest", "brief.json"), out)
    return f"نوشته شد ({out['written_by']}) · {len(out['bullets'])} بولت · {len(out['tasks'])} کار برای شما"


def index(days=21):
    """Day picker: [{date, jalali, verdict}] newest first."""
    out = []
    if os.path.isdir(BDIR):
        for f in sorted(os.listdir(BDIR), reverse=True):
            if re.match(r"\d{4}-\d{2}-\d{2}\.json$", f):
                b = read_json(os.path.join(BDIR, f), {}) or {}
                out.append({"date": b.get("date"), "jalali": b.get("jalali"), "verdict": b.get("day_verdict")})
            if len(out) >= days:
                break
    return out
