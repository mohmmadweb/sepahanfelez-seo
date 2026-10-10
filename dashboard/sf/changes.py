"""
«سیر تغییرات» — every change, why it was made, which number it should move, and whether it did.

Two sources:
  site      detected by comparing today's crawl with yesterday's: title, meta description, H1,
            content length (±15%), schema, status, new and removed pages. The metric is the page's
            position for its target keyword (search check) or its Search Console position/clicks.
  decision  logged from the dashboard (or by code): a choice we made — a new posting rhythm,
            a safety cap, a goal target. The metric is any goal metric.
After `eval_days` the change gets a verdict: مؤثر / بی‌اثر / بدتر — until then the dashboard shows
«تا X صبر می‌کنیم؛ فعلاً: …». Idea from Lenzit's changes.py; the site-drift half is SEO-specific.
"""

import json
import os
import uuid
from datetime import date, timedelta

from .util import DATA, canon_url, decode_url, now_tehran, read_json, today_str, write_json

PATH = os.path.join(DATA, "changes", "changes.json")
SNAP = os.path.join(DATA, "changes", "crawl_snapshot.json")
FIELD_FA = {"title": "عنوان", "description": "توضیحات متا", "h1": "H1", "words": "حجم متن", "schema": "داده‌ی ساختاریافته",
            "status": "وضعیت پاسخ", "new": "صفحه‌ی تازه", "removed": "صفحه حذف شد"}
METRIC_FA = {"page_pos": "رتبه‌ی صفحه برای کلمه‌ی هدفش", "page_gsc_pos": "رتبه‌ی میانگین صفحه در گوگل",
             "page_clicks": "کلیک گوگل صفحه (۲۸ روز)"}


def _load():
    return read_json(PATH, []) or []


def _save(rows):
    write_json(PATH, rows[-1000:])


def _page_snapshot(crawl):
    out = {}
    for p in crawl.get("pages", []):
        if p.get("status") != 200 or p.get("redirect_to"):
            continue
        out[p["url"]] = {"title": p.get("title") or "", "description": p.get("description") or "",
                         "h1": " | ".join(p.get("h1") or []), "words": p.get("words") or 0,
                         "schema": ",".join(p.get("schema") or []), "type": p.get("type")}
    return out


def page_metric(url):
    """(metric_key, value): search position for the page's keyword, else Search Console."""
    serp = read_json(os.path.join(DATA, "latest", "serp.json"), {}) or {}
    pos = [k.get("our_position") for k in serp.get("keywords", []) if k.get("target") and canon_url(k["target"]) == url]
    if pos:
        known = [p for p in pos if p]
        return "page_pos", (min(known) if known else 21)        # 21 = «outside the top 20»
    gsc = read_json(os.path.join(DATA, "latest", "gsc.json"), {}) or {}
    if gsc.get("status") == "ok":
        for r in gsc.get("pages", []):
            if canon_url(r["page"]) == url:
                return "page_gsc_pos", r["position"]
    return None, None


def metric_value(metric, ref=None):
    if metric in ("page_pos", "page_gsc_pos", "page_clicks"):
        if metric == "page_clicks":
            gsc = read_json(os.path.join(DATA, "latest", "gsc.json"), {}) or {}
            return next((r["clicks"] for r in gsc.get("pages", []) if canon_url(r["page"]) == ref), None)
        m, v = page_metric(ref)
        return v if m == metric else None
    from .goals import measure                                         # goal metrics
    t = date.fromisoformat(today_str())
    return measure(metric, t - timedelta(days=6), t)


def add(kind, title, why, metric=None, ref=None, direction="down", eval_days=14, before=None, field=None,
        old=None, new=None, source="code"):
    rows = _load()
    if before is None and metric:
        before = metric_value(metric, ref)
    row = {"id": uuid.uuid4().hex[:8], "date": today_str(), "ts": now_tehran().isoformat(timespec="seconds"),
           "kind": kind, "title": title, "why": why, "metric": metric, "metric_fa": METRIC_FA.get(metric, metric),
           "ref": ref, "direction": direction, "eval_on": (date.fromisoformat(today_str()) + timedelta(days=eval_days)).isoformat(),
           "before": before, "after": None, "current": before, "verdict": "waiting", "field": field,
           "old": (old or "")[:300] if isinstance(old, str) else old, "new": (new or "")[:300] if isinstance(new, str) else new,
           "source": source}
    rows.append(row)
    _save(rows)
    return row


def _detect_site_changes():
    crawl = read_json(os.path.join(DATA, "latest", "crawl.json"), {}) or {}
    if not crawl.get("pages"):
        return 0
    now = _page_snapshot(crawl)
    prev = read_json(SNAP)
    write_json(SNAP, now)
    if prev is None:
        return 0                                          # first run: baseline only
    n = 0
    for url, cur in now.items():
        old = prev.get(url)
        short = decode_url(url).replace("https://sepahanfelez.ir", "") or "/"
        m, _ = page_metric(url)
        if old is None:
            add("site", f"صفحه‌ی تازه: {short}", "صفحه‌ی جدید روی سایت منتشر شد", metric=m, ref=url, field="new", new=cur["title"])
            n += 1
            continue
        for f in ("title", "description", "h1", "schema"):
            if (old.get(f) or "") != (cur.get(f) or ""):
                add("site", f"{FIELD_FA[f]} عوض شد: {short}", "تغییر روی سایت زنده دیده شد", metric=m, ref=url,
                    field=f, old=old.get(f), new=cur.get(f))
                n += 1
        ow, nw = old.get("words") or 0, cur.get("words") or 0
        if ow and abs(nw - ow) / ow > 0.15:
            add("site", f"حجم متن {'بیشتر' if nw > ow else 'کمتر'} شد ({ow}→{nw} کلمه): {short}",
                "محتوای صفحه گسترش/کاهش یافت", metric=m, ref=url, field="words", old=ow, new=nw)
            n += 1
    for url in set(prev) - set(now):
        short = decode_url(url).replace("https://sepahanfelez.ir", "") or "/"
        add("site", f"صفحه از دسترس خارج شد: {short}", "در خزش امروز ۲۰۰ نداد یا دیگر لینک نمی‌شود", field="removed",
            old=prev[url].get("title"))
        n += 1
    return n


def _evaluate():
    rows = _load()
    today = today_str()
    for r in rows:
        if r["verdict"] not in ("waiting",) or not r.get("metric"):
            continue
        cur = metric_value(r["metric"], r.get("ref"))
        r["current"] = cur
        if today < r["eval_on"] or cur is None or r.get("before") is None:
            continue
        r["after"] = cur
        better = cur < r["before"] if r["direction"] == "down" else cur > r["before"]
        worse = cur > r["before"] if r["direction"] == "down" else cur < r["before"]
        r["verdict"] = "effective" if better else ("worse" if worse else "no_effect")
        r["evaluated_at"] = now_tehran().isoformat(timespec="seconds")
    _save(rows)
    return rows


def daily():
    n = _detect_site_changes()
    rows = _evaluate()
    eff = sum(1 for r in rows if r["verdict"] == "effective")
    return f"{n} تغییر تازه روی سایت · {len(rows)} تغییر ثبت‌شده · {eff} مؤثر"
