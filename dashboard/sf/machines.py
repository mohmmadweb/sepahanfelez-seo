"""
«ماشین‌ها» — every automation of this system, when it last ran, whether it was on time,
and what it said. Idea and rules from the Lenzit content engine (machines/health.py):

- each step of the daily run is a machine; its start/end, result and error are recorded
- health is judged by *outcome*, not only exit code (crawl ran but 0 pages = problem)
- the watchdog (`python -m sf.machines --watchdog`, every 2 h) re-runs a missed or failed
  daily step once; login/credential errors are not retried (they need a person) — they become a task
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta

from .util import DATA, now_tehran, read_json, today_str, write_json

PATH = os.path.join(DATA, "machines.json")
DAILY_AT = (7, 15)              # Tehran, sepahanfelez-seo.timer
GRACE_MIN = 120
AUTH_HINTS = ("401", "403", "unauthor", "login", "oauth", "credential", "not logged", "LoginRequired",
              "ChallengeRequired", "SF_STATE_KEY", "API_ID", "missing in .env")
SERVICES = [
    ("sepahanfelez-dashboard.service", "سرور داشبورد", "service"),
    ("sepahanfelez-tunnel.service", "تونل دامنه (Cloudflare)", "service"),
    ("sepahanfelez-seo.timer", "زمان‌بند روزانه ۰۷:۱۵", "timer"),
    ("sepahanfelez-health.timer", "نگهبان سلامت (هر ۲ ساعت)", "timer"),
]


def _load():
    return read_json(PATH, {"runs": [], "steps": {}}) or {"runs": [], "steps": {}}


def start_run(trigger, steps):
    m = _load()
    rid = now_tehran().strftime("%Y%m%d-%H%M%S")
    m["runs"] = (m["runs"] + [{"id": rid, "trigger": trigger, "steps": steps,
                               "started": now_tehran().isoformat(timespec="seconds"), "finished": None, "results": {}}])[-60:]
    write_json(PATH, m)
    return rid


def record(run_id, name, ok, started, summary=None, error=None, trace=None):
    m = _load()
    end = time.time()
    row = {"ok": ok, "started": datetime.fromtimestamp(started, now_tehran().tzinfo).isoformat(timespec="seconds"),
           "finished": now_tehran().isoformat(timespec="seconds"), "seconds": round(end - started, 1),
           "summary": summary if isinstance(summary, str) else (json.dumps(summary, ensure_ascii=False)[:200] if summary else None),
           "error": error, "trace": trace, "run": run_id, "auth_error": bool(error and any(h.lower() in error.lower() for h in AUTH_HINTS))}
    prev = m["steps"].get(name, {})
    row["last_ok"] = row["finished"] if ok else prev.get("last_ok")
    row["fail_streak"] = 0 if ok else prev.get("fail_streak", 0) + 1
    m["steps"][name] = row
    for r in m["runs"]:
        if r["id"] == run_id:
            r["results"][name] = {"ok": ok, "seconds": row["seconds"], "error": error}
    write_json(PATH, m)


def finish_run(run_id):
    m = _load()
    for r in m["runs"]:
        if r["id"] == run_id:
            r["finished"] = now_tehran().isoformat(timespec="seconds")
    write_json(PATH, m)


def _systemctl(unit, prop):
    try:
        return subprocess.run(["systemctl", "--user", "show", unit, "-p", prop, "--value"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:                                                  # noqa: BLE001
        return ""


def _github_action():
    try:
        with urllib.request.urlopen("https://api.github.com/repos/mohmmadweb/sepahanfelez-seo/actions/workflows/google-data.yml/runs?per_page=1",
                                    timeout=15) as r:
            run = json.load(r).get("workflow_runs", [{}])[0]
        return {"status": run.get("conclusion") or run.get("status"), "at": run.get("created_at")}
    except Exception as exc:                                           # noqa: BLE001
        return {"status": "unknown", "error": type(exc).__name__}


def health():
    """Snapshot for the dashboard: every machine with a verdict, plus outcome checks."""
    m = _load()
    now = now_tehran()
    due = now.replace(hour=DAILY_AT[0], minute=DAILY_AT[1], second=0, microsecond=0)
    today = today_str()
    from run_daily import STEP_FA                                      # noqa: WPS433 (avoid circular at import time)
    rows = []
    for name, fa in STEP_FA.items():
        s = m["steps"].get(name)
        if not s:
            verdict, why = "pending", "هنوز اجرا نشده"
        elif not s["ok"]:
            verdict = "auth" if s.get("auth_error") else "error"
            why = s.get("error") or "خطا"
        elif s["finished"][:10] != today and now > due + timedelta(minutes=GRACE_MIN):
            verdict, why = "missed", "امروز سر وقت اجرا نشد"
        else:
            verdict, why = "ok", s.get("summary") or "انجام شد"
        rows.append({"id": name, "name": fa, "verdict": verdict, "why": why, "last": (s or {}).get("finished"),
                     "seconds": (s or {}).get("seconds"), "last_ok": (s or {}).get("last_ok"),
                     "fail_streak": (s or {}).get("fail_streak", 0)})
    services = []
    for unit, fa, kind in SERVICES:
        state = _systemctl(unit, "ActiveState")
        nxt = _systemctl(unit, "NextElapseUSecRealtime") if kind == "timer" else ""
        try:                                   # "Sun 2026-10-11 03:49:37 UTC" → ISO, so the page shows Jalali Tehran time
            from datetime import timezone
            nxt = datetime.strptime(nxt.replace(" UTC", ""), "%a %Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).isoformat() if nxt else ""
        except ValueError:
            pass
        services.append({"unit": unit, "name": fa, "state": state or "unknown",
                         "ok": state == "active", "next": nxt})
    gh = _github_action()
    services.append({"unit": "github:google-data", "name": "داده‌ی گوگل (GitHub Actions، ۰۶:۳۰)",
                     "state": gh.get("status"), "ok": gh.get("status") == "success", "next": gh.get("at")})
    # outcome checks
    outcomes = []
    crawl = read_json(os.path.join(DATA, "latest", "crawl.json"), {}) or {}
    if crawl and len(crawl.get("pages", [])) < 20:
        outcomes.append("خزش انجام شد ولی کمتر از ۲۰ صفحه دید — سایت در دسترس نبود؟")
    serp = read_json(os.path.join(DATA, "latest", "serp.json"), {}) or {}
    if serp and not serp.get("provider"):
        outcomes.append("هیچ منبع جستجویی جواب نداد؛ رتبه‌ها امروز سنجیده نشد.")
    for sv in services:
        if sv["ok"] or sv["unit"] == "sepahanfelez-tunnel.service":
            continue
        if sv["unit"] == "github:google-data":
            outcomes.append("داده‌ی گوگل (GitHub Actions) هر روز خطا می‌دهد — Secrets گیت‌هاب هنوز تعریف نشده (کار شما).")
        else:
            outcomes.append(f"«{sv['name']}» روشن نیست ({sv['state']}).")
    last_runs = [r for r in m["runs"] if r["started"][:10] == today]
    if not last_runs and now > due + timedelta(minutes=GRACE_MIN):
        outcomes.append("اجرای روزانه‌ی امروز اصلاً شروع نشده است.")
    bad = [r for r in rows if r["verdict"] in ("error", "missed", "auth")]
    out = {"checked_at": now.isoformat(timespec="seconds"), "steps": rows, "services": services,
           "outcomes": outcomes, "all_ok": not bad and not outcomes,
           "runs": m["runs"][-10:]}
    write_json(os.path.join(DATA, "health.json"), out)
    return out


def watchdog():
    """Re-run once whatever failed or was missed today (not auth problems — those need a person)."""
    h = health()
    m = _load()
    today = today_str()
    retried_today = {s for r in m["runs"] if r["started"][:10] == today and r["trigger"] == "watchdog" for s in r["steps"]}
    todo = [r["id"] for r in h["steps"] if r["verdict"] in ("error", "missed") and r["id"] not in retried_today
            and r["id"] not in ("brief",)]
    if any(s["unit"] == "sepahanfelez-seo.timer" and s["state"] != "active" for s in h["services"]):
        return {"skipped": "timer is stopped on purpose"}
    if todo:
        steps = todo + ([] if "analyse" in todo else ["analyse"]) + ["goals", "brief"]
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        subprocess.run([sys.executable, os.path.join(here, "run_daily.py"), "--only", *steps, "--trigger", "watchdog"],
                       cwd=here, timeout=3600, check=False)
        h = health()
    return {"retried": todo, "all_ok": h["all_ok"]}


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sf.env import load_env
    load_env()
    print(json.dumps(watchdog() if "--watchdog" in sys.argv else health(), ensure_ascii=False, indent=1)[:2000])
