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

from sf import build, calendar_ir, competitors, content_plan, crawl, google, issues, publish  # noqa: E402
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", nargs="*", default=[])
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()
    run = lambda step: (a.only is None or step in a.only) and step not in a.skip  # noqa: E731

    site = config("site.json")
    kw = config("keywords.json", {})
    known = config("known_issues.json", {})
    t0 = time.time()

    if run("crawl"):
        print("▸ crawl sepahanfelez.ir")
        write_json(os.path.join(LATEST, "crawl.json"), crawl.crawl(site))
    if run("competitors"):
        print("▸ competitor watch")
        write_json(os.path.join(LATEST, "competitors.json"), competitors.watch())
    if run("calendar"):
        print("▸ Iranian calendar (time.ir)")
        cal = calendar_ir.calendar(35, site)
        write_json(os.path.join(LATEST, "calendar.json"), cal)
        write_json(os.path.join(LATEST, "content_plan.json"), content_plan.plan(cal, kw, days=28))
    if run("google"):
        # Google answers 403 to this server, so GitHub Actions collects and encrypts it (google-data
        # branch); set SF_GOOGLE_DIRECT=1 to call Google from here instead (e.g. inside Actions).
        if os.environ.get("SF_GOOGLE_DIRECT") == "1":
            bundle = {"gsc": google.collect_gsc(site), "ga4": google.collect_ga4(site), "psi": google.collect_psi(site)}
        else:
            print("▸ Google data (encrypted bundle from GitHub Actions)")
            got = publish.pull_google()
            bundle = got.get("bundle") or {k: {"status": "blocked", "reason": got.get("reason")} for k in ("gsc", "ga4", "psi")}
        for name in ("gsc", "ga4", "psi", "inspection"):
            if name in bundle:
                res = keep_good(name, bundle[name])
                print(f"  {name}: {res['status']} {res.get('reason') or ''}")

    if run("analyse"):
        print("▸ issues")
        cr = latest("crawl")
        found = issues.analyse(site, cr, kw, latest("gsc"), latest("psi"), known)
        n_pages = len([p for p in cr["pages"] if p["status"] == 200 and not p.get("redirect_to")])
        score = issues.health_score(found, n_pages)
        write_json(os.path.join(LATEST, "issues.json"), {"health": score, "issues": found})
        track_issues(found)
        append_history(site, cr, found, score)
        print(f"  health {score}/100 · {len(found)} issues")

    if run("social"):
        print("▸ social login status")
        import subprocess
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "automation", "social", "login.py"), "status"], timeout=600, check=False)
    if run("build"):
        print("▸ build dashboard" + (" (encrypted)" if os.environ.get("SF_DASHBOARD_PASSWORD") else " (PLAIN — local preview only)"))
        out = build.build()
        print(f"  → {out}")
    if run("publish"):
        print("▸ publish to sepahanfelezseo.lenzit.ir")
        print("  →", publish.publish_site(build.SITE))
    if run("backup"):
        print("▸ encrypted backup to Drive")
        print("  →", publish.backup())
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
        "date": today_str(), "jalali": jalali(), "health": score,
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
