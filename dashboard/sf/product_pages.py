"""
What the site itself says about a product: the category page's title, description, section headings and
the names of its products (they carry the specs). Copy for stories, posts and articles is written from
this, so it speaks the site's own language.

Read live from sepahanfelez.ir, at most every 3 hours per page (dashboard/data/latest/product_pages.json).
`fp` is a fingerprint of the words only — prices are left out, they change every day — so when the owner
edits a product or category page the fingerprint changes and content not yet published is rewritten.
"""

import hashlib
import re
import urllib.parse
from datetime import datetime, timedelta

from .util import DATA, fetch, now_tehran, read_json, write_json

CACHE = f"{DATA}/latest/product_pages.json"
SITE = "https://sepahanfelez.ir"
PRICE = re.compile(r"[\d۰-۹][\d۰-۹,٬\.]*\s*(?:ریال|تومان)[^،.\n]*|قیمت روز[^:،\n]*:\s*")


def _clean(t):
    t = re.sub(r"\s+", " ", PRICE.sub("", t or "")).strip(" :|،")
    return t.replace(" | سپاهان فلز", "").strip()


def _parse(html_text, path):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_text, "html.parser")
    meta = soup.find("meta", attrs={"name": "description"})
    h1 = soup.find("h1")
    sections = [_clean(h.get_text(" ", strip=True)) for h in soup.find_all("h2")][:12]
    names, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = urllib.parse.unquote(a["href"]).split("?")[0].rstrip("/")
        href = href.replace(SITE, "")
        if href.startswith(path + "/") and href.count("/") == path.count("/") + 1:
            n = _clean(a.get_text(" ", strip=True))
            if len(n) > 6 and n not in seen:
                seen.add(n)
                names.append(n)
    intro = ""
    for p in soup.find_all("p"):
        t = _clean(p.get_text(" ", strip=True))
        if len(t) > 80:
            intro = t[:600]
            break
    out = {"path": path, "title": _clean(soup.title.get_text() if soup.title else ""),
           "h1": _clean(h1.get_text(" ", strip=True) if h1 else ""),
           "description": _clean(meta["content"] if meta and meta.get("content") else ""),
           "intro": intro, "sections": [s for s in sections if s], "products": names[:30]}
    words = "|".join([out["h1"], out["description"], out["intro"], *out["sections"], *sorted(out["products"])])
    out["fp"] = hashlib.sha1(words.encode()).hexdigest()[:12]
    return out


def facts(path, max_age_h=3):
    """Facts for one category path (/category/<slug>); cached, refreshed live when older than max_age_h."""
    path = urllib.parse.unquote(urllib.parse.urlsplit(path).path).rstrip("/")
    if not path:
        return {}
    cache = read_json(CACHE, {}) or {}
    hit = cache.get(path)
    if hit and now_tehran() - datetime.fromisoformat(hit["fetched"]) < timedelta(hours=max_age_h):
        return hit
    r, _, _ = fetch(SITE + urllib.parse.quote(path))
    if r is None or r.status_code != 200:
        return hit or {}
    out = _parse(r.text, path)
    out["fetched"] = now_tehran().isoformat(timespec="minutes")
    if hit and hit.get("fp") != out["fp"]:
        out["changed"] = out["fetched"]                     # the owner edited the page since we last read it
        out["previous_fp"] = hit.get("fp")
    elif hit:
        out["changed"] = hit.get("changed")
    cache[path] = out
    write_json(CACHE, cache)
    return out
