#!/usr/bin/env python3
"""
Daily SEO run for sepahanfelez.ir → data/latest/*.json + data/history.json → site/.

    python run_daily.py                 # everything
    python run_daily.py --skip crawl    # reuse yesterday's crawl (faster while developing)
    python run_daily.py --only build    # rebuild the dashboard from existing data
    python run_daily.py --only build publish   # after changing SF_DASHBOARD_PASSWORD in .env

Google collectors (GSC, GA4, PSI) only work where Google's API front-end does
not 403 us — GitHub Actions, not this server. When they come back "blocked",
the previous good snapshot is kept and marked stale instead of being replaced.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sf.env import load_env  # noqa: E402

load_env()

from sf import (brief, build, calendar_ir, changes, competitors, content_plan, crawl, drive_sync, goals,  # noqa: E402
                google, issues, machines, measure, publish, serp)
from sf.util import DATA, config, jalali, now_tehran, read_json, today_str, write_json  # noqa: E402

LATEST = os.path.join(DATA, "latest")


def latest(name, default=None):
    return read_json(os.path.join(LATEST, f"{name}.json"), default)


def keep_good(name, new):
    """Write `new` unless it is blocked and a previous OK snapshot exists; then keep that, marked stale."""
    old = latest(name)
    if new.get("status") != "ok" and old and old.get("status") == "ok":
        old["stale"] = {"since": old.get("collected_at"), "reason": new.get("reason")}
        write_json(os.path.join(LATEST, f"{name}.json"), old)
        return old
    new["collected_at"] = now_tehran().isoformat(timespec="minutes")
    write_json(os.path.join(LATEST, f"{name}.json"), new)
    return new


STEP_FA = {"crawl": "خزش سایت", "competitors": "رصد نقشه‌ی سایت رقبا", "serp": "نتایج جستجو و رقبای تازه",
           "drive": "عکس‌های درایو", "calendar": "تقویم و برنامه‌ی محتوا", "google": "داده‌ی گوگل",
           "analyse": "تحلیل مشکلات", "changes": "سیر تغییرات سایت", "measure": "سنجش نتیجه‌ی محتوا",
           "social": "وضعیت ورود شبکه‌ها", "goals": "سنجش اهداف", "brief": "تحلیل امروز", "backup": "پشتیبان رمزشده"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", nargs="*", default=[])
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--trigger", default="timer")
    a = ap.parse_args()
    run = lambda step: (a.only is None or step in a.only) and step not in a.skip  # noqa: E731

    site = config("site.json")
    kw = config("keywords.json", {})
    known = config("known_issues.json", {})
    t0 = time.time()
    run_id = machines.start_run(a.trigger, [s for s in STEP_FA if run(s)])

    def step(name, fn):
        """Run one step as a 'machine': its time, result and error are recorded; a failure does not stop the others."""
        if not run(name):
            return None
        print(f"▸ {STEP_FA[name]}")
        st = time.time()
        try:
            summary = fn()
            machines.record(run_id, name, True, st, summary=summary)
            if summary:
                print(f"  {summary}")
            return summary
        except Exception as exc:                                       # noqa: BLE001
            import traceback
            machines.record(run_id, name, False, st, error=f"{type(exc).__name__}: {str(exc)[:300]}",
                            trace=traceback.format_exc()[-1500:])
            print(f"  ✗ {type(exc).__name__}: {exc}")
            return None

    def s_crawl():
        r = crawl.crawl(site)
        write_json(os.path.join(LATEST, "crawl.json"), r)
        return f"{len(r['pages'])} صفحه در {r['duration_s']} ثانیه"

    def s_competitors():
        r = competitors.watch()
        write_json(os.path.join(LATEST, "competitors.json"), r)
        new = sum(len(c.get("new_today") or []) for c in r["competitors"])
        return f"{len(r['competitors'])} رقیب · {new} صفحه‌ی تازه"

    def s_serp():
        r = serp.check()
        write_json(os.path.join(LATEST, "serp.json"), r)
        ok = sum(1 for k in r["keywords"] if k["provider"])
        return f"{ok}/{len(r['keywords'])} کلمه · منبع {r['provider'] or '—'}"

    def s_drive():
        r = drive_sync.sync()
        return f"{r['status']} {r.get('reason') or ''}".strip()

    def s_calendar():
        cal = calendar_ir.calendar(35, site)
        cal["checked_at"] = now_tehran().isoformat(timespec="seconds")
        write_json(os.path.join(LATEST, "calendar.json"), cal)
        plan = content_plan.plan(cal, kw, days=28)
        write_json(os.path.join(LATEST, "content_plan.json"), plan)
        return f"{len(plan['items'])} آیتم در ۴ هفته · منبع {', '.join(cal['source'])}"

    def s_google():
        # Google answers 403 to this server, so GitHub Actions collects and encrypts it (google-data
        # branch); set SF_GOOGLE_DIRECT=1 to call Google from here instead (e.g. inside Actions).
        if os.environ.get("SF_GOOGLE_DIRECT") == "1":
            bundle = {"gsc": google.collect_gsc(site), "ga4": google.collect_ga4(site), "psi": google.collect_psi(site)}
        else:
            got = publish.pull_google()
            bundle = got.get("bundle") or {k: {"status": "blocked", "reason": got.get("reason")} for k in ("gsc", "ga4", "psi")}
        out = []
        for name in ("gsc", "ga4", "psi", "inspection"):
            if name in bundle:
                out.append(f"{name}:{keep_good(name, bundle[name])['status']}")
        return " ".join(out)

    def s_analyse():
        cr = latest("crawl")
        found = issues.analyse(site, cr, kw, latest("gsc"), latest("psi"), known)
        n_pages = len([p for p in cr["pages"] if p["status"] == 200 and not p.get("redirect_to")])
        score = issues.health_score(found, n_pages)
        write_json(os.path.join(LATEST, "issues.json"), {"health": score, "issues": found,
                                                         "checked_at": now_tehran().isoformat(timespec="seconds")})
        track_issues(found)
        append_history(site, cr, found, score)
        return f"سلامت {score}/100 · {len(found)} مشکل"

    def s_social():
        import subprocess
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "automation", "social", "login.py"), "status"], timeout=900, check=False)
        st = read_json(os.path.join(DATA, "social_status.json"), {}) or {}
        return f"{sum(1 for v in st.values() if v.get('logged_in'))} از {len(st)} شبکه وارد"

    step("crawl", s_crawl)
    step("competitors", s_competitors)
    step("serp", s_serp)
    step("drive", s_drive)
    step("calendar", s_calendar)
    step("google", s_google)
    step("analyse", s_analyse)
    step("changes", changes.daily)
    step("measure", measure.run)
    step("social", s_social)
    step("goals", goals.evaluate)
    try:
        machines.health()
    except Exception as exc:                                           # noqa: BLE001
        print(f"  health snapshot failed: {exc}")
    step("brief", brief.make)
    if run("build") and os.environ.get("SF_PUBLISH_PAGES", "0") == "1":
        step("build", lambda: build.build())
    if run("publish") and os.environ.get("SF_PUBLISH_PAGES", "0") == "1":
        step("publish", lambda: publish.publish_site(build.SITE))
    step("backup", publish.backup)
    machines.finish_run(run_id)
    print(f"done in {round(time.time() - t0)}s")


def track_issues(found):
    path = os.path.join(DATA, "issues_log.json")
    log = read_json(path, {}) or {}
    today = today_str()
    ids = set()
    for i in found:
        ids.add(i["id"])
        e = log.setdefault(i["id"], {"first_seen": today, "title": i["title"], "severity": i["severity"]})
        e.update({"last_seen": today, "title": i["title"], "severity": i["severity"], "count": i["count"],
                  "resolved": None})
    for iid, e in log.items():
        if iid not in ids and not e.get("resolved"):
            e["resolved"] = today
    write_json(path, log)


def append_history(site, cr, found, score):
    path = os.path.join(DATA, "history.json")
    hist = read_json(path, []) or []
    ok = [p for p in cr["pages"] if p["status"] == 200 and not p.get("redirect_to")]
    sev = {s: sum(1 for i in found if i["severity"] == s) for s in ("critical", "high", "medium", "low")}
    price = next((p for p in ok if p["type"] == "price"), {})
    gsc, ga4, psi = latest("gsc", {}), latest("ga4", {}), latest("psi", {})
    comp = latest("competitors", {}) or {}
    row = {
        "date": today_str(), "ts": now_tehran().isoformat(timespec="seconds"), "jalali": jalali(), "health": score,
        "pages": len(ok), "sitemap": cr["sitemap"]["count"], "broken": len(cr.get("broken", [])),
        "redirects": len(cr.get("redirects", [])), "issues": sev,
        "articles": sum(1 for p in ok if p["type"] == "article"),
        "products": sum(1 for p in ok if p["type"] == "product"),
        "avg_words": round(sum(p.get("words") or 0 for p in ok) / max(len(ok), 1)),
        "avg_seconds": round(sum(p.get("seconds") or 0 for p in ok) / max(len(ok), 1), 2),
        "price_age_days": (price.get("price_freshness") or {}).get("freshest_days"),
        "tls_days": cr["checks"].get("tls", {}).get("days_left"),
    }
    if gsc.get("status") == "ok":
        last28 = gsc["daily"][-28:]
        clicks = sum(d["clicks"] for d in last28)
        impr = sum(d["impressions"] for d in last28)
        row["gsc"] = {"clicks": clicks, "impressions": impr,
                      "ctr": round(100 * clicks / impr, 2) if impr else 0,
                      "position": round(sum(d["position"] * d["impressions"] for d in last28) / impr, 1) if impr else None,
                      "queries": len(gsc.get("queries", [])), "stale": bool(gsc.get("stale"))}
    if ga4.get("status") == "ok":
        org = [d for d in ga4["daily"] if d.get("sessionDefaultChannelGroup") == "Organic Search"]
        row["ga4"] = {"organic_sessions_90d": int(sum(d["sessions"] for d in org)),
                      "sessions_90d": int(sum(d["sessions"] for d in ga4["daily"]))}
    if psi.get("status") == "ok":
        mob = [r["scores"]["performance"] for r in psi["results"] if r["status"] == "ok" and r["strategy"] == "mobile"]
        row["psi_mobile"] = round(sum(mob) / len(mob)) if mob else None
    row["competitors"] = {c["id"]: c["urls_total"] for c in comp.get("competitors", [])}
    hist = [h for h in hist if h["date"] != row["date"]] + [row]
    write_json(path, hist[-730:])


if __name__ == "__main__":
    main()
