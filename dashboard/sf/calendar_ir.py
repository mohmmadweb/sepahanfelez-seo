"""
Iranian working-day calendar for the publishing schedule.

Primary source is time.ir's own JSON API (the one its calendar page calls) — it
carries official holidays *and* the day's occasions, which feed the
«فصلی/مناسبتی» content type. Lunar holidays shift by a day depending on the moon
sighting, so time.ir is the authority. The `holidays` package is the offline
fallback; it marks its lunar dates «تخمینی» and so do we.

Working days and hours come from config/site.json → working_days.days (owner: Sat–Wed
09–18, Thursday 09–13, Friday and official holidays off).
"""

import os
from datetime import date, timedelta

import jdatetime

from .util import DATA, fetch, read_json, today_str, write_json

API = ("https://api.time.ir/v1/event/fa/events/calendar"
       "?year={y}&month={m}&day=0&base1=0&base2=1&base3=2")
CACHE = os.path.join(DATA, "calendar")
WEEKDAY_FA = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


def _month_events(jy, jm):
    """Return ({gregorian_iso: [events]}, source). Cached per Jalali month for 7 days."""
    path = os.path.join(CACHE, f"{jy}-{jm:02d}.json")
    cached = read_json(path)
    if cached and cached.get("fetched", "") >= (date.today() - timedelta(days=7)).isoformat():
        return cached["days"], cached["source"]
    r, err, _ = fetch(API.format(y=jy, m=jm), timeout=20)
    days = {}
    if r is not None and r.status_code == 200:
        try:
            for ev in r.json()["data"]["event_list"]:
                g = date(ev["gregorian_year"], ev["gregorian_month"], ev["gregorian_day"]).isoformat()
                days.setdefault(g, []).append({"title": ev["title"].strip(), "holiday": bool(ev["is_holiday"])})
            write_json(path, {"fetched": today_str(), "source": "time.ir", "days": days})
            return days, "time.ir"
        except (KeyError, ValueError, TypeError):
            pass
    # offline fallback
    import holidays
    start = jdatetime.date(jy, jm, 1).togregorian()
    ir = holidays.country_holidays("IR", years=[start.year, start.year + 1])
    for i in range(31):
        d = start + timedelta(days=i)
        if jdatetime.date.fromgregorian(date=d).month != jm:
            break
        if d in ir:
            days[d.isoformat()] = [{"title": ir[d], "holiday": True}]
    return days, "holidays-lib"


def calendar(days_ahead=30, site=None):
    days_cfg = ((site or {}).get("working_days") or {}).get("days") or {
        str(k): {"hours": ["09:00", "18:00"], "story_slots": ["09:00", "13:00", "16:00"], "telegram": ["10:30"]}
        for k in (5, 6, 0, 1, 2)}
    start = date.fromisoformat(today_str())
    months, events, sources = set(), {}, set()
    for i in range(days_ahead + 1):
        j = jdatetime.date.fromgregorian(date=start + timedelta(days=i))
        months.add((j.year, j.month))
    for jy, jm in sorted(months):
        ev, src = _month_events(jy, jm)
        events.update(ev)
        sources.add(src)

    out = []
    for i in range(days_ahead + 1):
        d = start + timedelta(days=i)
        j = jdatetime.date.fromgregorian(date=d)
        evs = events.get(d.isoformat(), [])
        holiday = any(e["holiday"] for e in evs) or d.weekday() == 4
        cfg = days_cfg.get(str(d.weekday()))
        working = bool(cfg) and not holiday
        out.append({"date": d.isoformat(), "jalali": j.strftime("%Y/%m/%d"),
                    "jalali_label": f"{j.day} {j.j_months_fa[j.month - 1]}",
                    "weekday_fa": WEEKDAY_FA[d.weekday()], "holiday": holiday,
                    "working": working, "events": [e["title"] for e in evs],
                    "hours": cfg["hours"] if working else None,
                    "slots": cfg["story_slots"] if working else [],
                    "telegram": cfg.get("telegram", []) if working else []})
    return {"source": sorted(sources), "days": out}
