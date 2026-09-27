"""
Daily competitor watch: sitemap size, new URLs since yesterday, homepage title.

The URL set of each competitor is kept in data/competitors/<id>.json so the next
run can say exactly which pages they published (and which they removed). That
diff is the most useful competitor signal we can get for free: it shows what
they are writing about, how often, and which product pages they are building.
"""

import gzip
import os
import re
import time
import urllib.parse

from .util import DATA, decode_url, fetch, read_json, today_str, write_json

_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_BLOG = re.compile(r"/(blog|mag|magazine|article|articles|news|post|posts|weblog|maghale|مقاله|مجله|اخبار)/|\?p=\d+", re.I)
_PRODUCT = re.compile(r"/(product|products|shop|محصول)/", re.I)
_CATEGORY = re.compile(r"/(product-category|category|categories|cat|دسته)/", re.I)


def _get(url):
    r, err, _ = fetch(url, timeout=30)
    if r is None or r.status_code != 200:
        return None, err or f"HTTP {r.status_code}"
    body = r.content
    if url.endswith(".gz") or body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except OSError:
            pass
    return body.decode("utf-8", "replace"), None


def sitemap_set(sitemaps, limit_children=60):
    urls, errors, todo, seen = set(), [], list(sitemaps), set()
    while todo and len(seen) < limit_children:
        sm = todo.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        text, err = _get(sm)
        time.sleep(0.6)
        if text is None:
            errors.append(f"{sm}: {err}")
            continue
        locs = _LOC.findall(text)
        if "<sitemapindex" in text:
            todo.extend(locs)
        else:
            urls.update(decode_url(u) for u in locs)
    return urls, errors


def classify(url):
    path = urllib.parse.urlsplit(url).path
    if _BLOG.search(url):
        return "blog"
    if _PRODUCT.search(path):
        return "product"
    if _CATEGORY.search(path):
        return "category"
    return "other"


def watch(log=print):
    cfg = read_json(os.path.join(os.path.dirname(DATA), "config", "competitors.json"), {}) or {}
    out = []
    for c in cfg.get("competitors", []):
        cid, domain = c["id"], c["domain"]
        store_path = os.path.join(DATA, "competitors", f"{cid}.json")
        prev = read_json(store_path, {}) or {}
        sitemaps = c.get("sitemaps") or [f"https://{domain}/sitemap.xml", f"https://{domain}/sitemap_index.xml"]
        urls, errors = sitemap_set(sitemaps)

        home, herr, secs = fetch(f"https://{domain}/", timeout=25)
        title = None
        if home is not None and home.status_code == 200:
            m = _TITLE.search(home.text)
            title = re.sub(r"\s+", " ", m.group(1)).strip() if m else None

        prev_urls = set(prev.get("urls", []))
        new = sorted(urls - prev_urls) if prev_urls else []
        gone = sorted(prev_urls - urls) if prev_urls and urls else []
        by_type = {}
        for u in urls:
            t = classify(u)
            by_type[t] = by_type.get(t, 0) + 1

        history = prev.get("history", [])
        history = [h for h in history if h["date"] != today_str()]
        history.append({"date": today_str(), "urls": len(urls), "new": len(new), "gone": len(gone),
                        "blog": by_type.get("blog", 0)})
        new_log = (prev.get("new_log", []) + [{"date": today_str(), "url": u, "type": classify(u)} for u in new])[-300:]

        write_json(store_path, {"id": cid, "domain": domain, "urls": sorted(urls) if urls else sorted(prev_urls),
                                "history": history[-400:], "new_log": new_log})
        out.append({"id": cid, "domain": domain, "reachable": home is not None and home.status_code < 500,
                    "home_status": home.status_code if home is not None else None, "home_seconds": secs,
                    "home_title": title, "home_error": herr, "sitemap_errors": errors[:3],
                    "urls_total": len(urls), "by_type": by_type, "new_today": new[:50], "gone_today": gone[:50],
                    "first_run": not prev_urls})
        log(f"  {domain}: {len(urls)} urls, +{len(new)} / -{len(gone)}")
    return {"date": today_str(), "competitors": out}
