"""
Daily SEO work from Search Console: pages Google already shows on page one but people do not
click get a better title and description — proposed, approved in the dashboard, applied through
the panel, and judged 28 days later by the page's click-through rate.

    python3 seo_tasks.py propose     # daily step: up to 2 new proposals
    python3 seo_tasks.py apply <id>  # an approved proposal → panel

A page qualifies with ≥100 impressions in 28 days, average position ≤10 and CTR under 2%, and
no proposal for it in the last 45 days. The model is given the page's own top search queries
(from Search Console) and its current title/description, nothing else.
"""

import hashlib
import json
import os
import re
import sys
import urllib.parse
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import articles  # noqa: E402
import panel  # noqa: E402
from sf import trace  # noqa: E402
from sf.util import canon_url, read_json, today_str, write_json  # noqa: E402

DIR = os.path.join(panel.DATA, "seo")
GSC = os.path.join(panel.ROOT, "dashboard", "data", "latest", "gsc.json")
PER_DAY = 2


def _path(pid):
    return os.path.join(DIR, f"{pid}.json")


def all_proposals():
    if not os.path.isdir(DIR):
        return []
    return sorted((read_json(os.path.join(DIR, f), {}) for f in os.listdir(DIR) if f.endswith(".json")),
                  key=lambda p: p.get("created", ""), reverse=True)


def save(p):
    os.makedirs(DIR, exist_ok=True)
    p["updated"] = articles._now()
    write_json(_path(p["id"]), p)
    return p


def candidates(gsc):
    recent = {p["url"] for p in all_proposals()
              if p.get("created", "")[:10] >= (date.fromisoformat(today_str()) - timedelta(days=45)).isoformat()}
    crawl = read_json(articles.CRAWL, {}) or {}
    byurl = {canon_url(p["url"]): p for p in crawl.get("pages", []) if p.get("status") == 200}
    out = []
    for r in gsc.get("pages", []):
        u = canon_url(r["page"])
        path = urllib.parse.unquote(urllib.parse.urlsplit(u).path).rstrip("/")
        editable = (path.startswith("/blog/") and path.count("/") == 3) or (path.startswith("/category/") and path.count("/") == 2)
        if editable and u in byurl and u not in recent and r["impressions"] >= 100 and r["position"] <= 10 and r["ctr"] < 2:
            qs = sorted((q for q in gsc.get("pairs", []) if canon_url(q["page"]) == u), key=lambda q: -q["impressions"])[:6]
            out.append({"url": u, "path": path, "gsc": r, "queries": qs, "page": byurl[u]})
    return sorted(out, key=lambda c: -c["gsc"]["impressions"])


def _prompt(c):
    pg = c["page"]
    return f"""برای یک صفحه از سایت فروشگاه کارخانه‌ی «سپاهان فلز» (sepahanfelez.ir) عنوان سئو و توضیح متای تازه بنویس.
این صفحه در گوگل صفحه‌ی اول است ولی کم کلیک می‌خورد.

نشانی: {c['path']}
عنوان فعلی: {pg.get('title')}
توضیح فعلی: {pg.get('description')}
H1: {(pg.get('h1') or [''])[0] if isinstance(pg.get('h1'), list) else pg.get('h1')}
آمار ۲۸ روز: {c['gsc']['impressions']} نمایش، {c['gsc']['clicks']} کلیک، رتبه‌ی میانگین {c['gsc']['position']}
جستجوهای واقعی که این صفحه را نشان داده‌اند (نمایش/رتبه): {json.dumps([[q['query'], q['impressions'], q['position']] for q in c['queries']], ensure_ascii=False)}

قواعد: پرنمایش‌ترین جستجو در اول عنوان؛ عنوان ۴۰ تا ۶۰ نویسه؛ توضیح ۱۲۰ تا ۱۶۰ نویسه با یک دلیل روشن برای کلیک
(قیمت روز به‌روز، خرید مستقیم از کارخانه، مشخصات کامل — فقط آن‌چه واقعاً در این نوع صفحه هست)؛ بدون عدد قیمت؛ بدون ادعای ساختگی؛ ارقام فارسی.
خروجی فقط JSON: {{"meta_title": "…", "meta_description": "…", "why": "یک جمله: چه چیزی عوض شد و چرا"}}"""


def propose(say=print):
    gsc = read_json(GSC, {}) or {}
    if gsc.get("status") != "ok":
        return []
    made = []
    for c in candidates(gsc)[:PER_DAY]:
        out, cost = articles._llm(_prompt(c))
        mt, md = str(out.get("meta_title", "")).strip(), str(out.get("meta_description", "")).strip()
        top = c["queries"][0]["query"] if c["queries"] else ""
        gate = [{"name": "طول عنوان", "ok": 30 <= len(mt) <= 65, "detail": str(len(mt))},
                {"name": "طول توضیح", "ok": 110 <= len(md) <= 165, "detail": str(len(md))},
                {"name": "جستجوی اصلی در عنوان", "ok": bool(top) and top in mt, "detail": top},
                {"name": "بدون قیمت", "ok": not re.search(r"\d[\d,٬]*\s*(ریال|تومان)", md + mt), "detail": ""}]
        pid = date.fromisoformat(today_str()).strftime("%Y%m%d") + "-" + hashlib.md5(c["url"].encode()).hexdigest()[:6]
        p = {"id": pid, "created": articles._now(), "url": c["url"], "path": c["path"], "gsc": c["gsc"], "queries": c["queries"],
             "old": {"meta_title": c["page"].get("title"), "meta_description": c["page"].get("description")},
             "new": {"meta_title": mt, "meta_description": md}, "why": out.get("why", ""), "gate": gate,
             "status": "draft" if all(g["ok"] for g in gate) else "needs_fix", "cost_usd": round(cost, 3)}
        trace.step("seo-" + pid, "brief", "فرصت از سرچ کنسول", f"{c['path']} — رتبه {c['gsc']['position']}، CTR {c['gsc']['ctr']}٪، {c['gsc']['impressions']} نمایش")
        trace.step("seo-" + pid, "write", "عنوان و توضیح تازه", mt, decision=p["why"])
        made.append(save(p))
        say(f"پیشنهاد: {c['path']} → {mt}")
    return made


def apply(pid, say=print):
    from sf import changes
    p = read_json(_path(pid), None)
    if not p or p.get("status") != "approved":
        raise RuntimeError("پیشنهاد تأییدشده‌ای با این شناسه نیست")
    with panel.Panel() as pn:
        if p["path"].startswith("/blog/"):
            art = next((a for a in pn.articles() if a["path"] == p["path"]), None)
            if not art:
                raise RuntimeError("مقاله در پنل پیدا نشد")
            pn.edit_article(art["id"], p["new"])
        else:
            row = next((r for r in pn._rows("/admin/category")
                        if any(urllib.parse.unquote(urllib.parse.urlsplit(h).path).rstrip("/") == p["path"] for h in r["links"] if h and "/admin/" not in h)), None)
            edit = row and next((h for h in row["links"] if re.search(r"/admin/category/\d+/edit", h or "")), None)
            if not edit:
                raise RuntimeError("دسته در پنل پیدا نشد")
            pn.edit_product_category(int(re.search(r"/category/(\d+)/edit", edit).group(1)), p["new"])
    p.update({"status": "applied", "applied_at": articles._now()})
    changes.add("meta", f"عنوان و توضیح تازه: {p['path']}", p.get("why") or "CTR پایین در صفحه‌ی اول گوگل",
                metric="page_ctr", ref=p["url"], direction="up", eval_days=28, field="meta",
                old=p["old"].get("meta_title"), new=p["new"]["meta_title"], source="gsc")
    trace.step("seo-" + pid, "publish", "در پنل ذخیره شد", p["path"], decision="اثر روی نرخ کلیک ۲۸ روز بعد سنجیده می‌شود.")
    say(f"✓ {p['path']}")
    return save(p)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "propose"
    print(propose() if cmd == "propose" else apply(sys.argv[2]))
