"""
Crawl sepahanfelez.ir: sitemap + internal links, one polite request per second.

Every page gets the on-page facts the dashboard needs (title, description, H1,
canonical, robots, schema types, word count, images without alt, internal links)
plus site-level checks that have bitten this site before: foreign hostnames
serving our content (emaratnews.ir, 2026-08-08), www/http canonicalisation,
robots.txt, the sitemap itself, TLS expiry, and how stale the price table is.
"""

import hashlib
import json
import re
import socket
import ssl
import time
import urllib.parse
from collections import deque
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from .util import canon_url, config, decode_url, fetch, norm

_WORD = re.compile(r"[\w؀-ۿ]+")


def page_type(path, types):
    for t in types:
        if re.match(t["pattern"], path):
            return t["type"]
    return "other"


def _text(soup):
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return re.sub(r"\s+", " ", main.get_text(" ", strip=True))


def parse_page(url, html, host):
    soup = BeautifulSoup(html, "lxml")
    head_title = soup.title.get_text(strip=True) if soup.title else ""

    def meta(name=None, prop=None):
        tag = soup.find("meta", attrs={"name": name} if name else {"property": prop})
        return (tag.get("content") or "").strip() if tag else None

    canonical = None
    link = soup.find("link", rel=lambda v: v and "canonical" in v)
    if link and link.get("href"):
        canonical = urllib.parse.urljoin(url, link["href"])

    schema = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except (json.JSONDecodeError, TypeError):
            schema.append("INVALID")
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                t = node.get("@type")
                if t:
                    schema.extend(t if isinstance(t, list) else [t])
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
            elif isinstance(node, list):
                stack.extend(node)

    h1 = [h.get_text(" ", strip=True) for h in soup.find_all("h1")]
    h2 = [h.get_text(" ", strip=True) for h in soup.find_all("h2")]
    imgs = soup.find_all("img")
    no_alt = [i.get("src") or i.get("data-src") or "" for i in imgs if not (i.get("alt") or "").strip()]

    internal, external = set(), set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("tel:", "mailto:", "javascript:", "#", "whatsapp:")):
            continue
        absu = urllib.parse.urljoin(url, href).split("#")[0]
        p = urllib.parse.urlsplit(absu)
        if p.netloc.lower().removeprefix("www.") == host:
            internal.add(absu)
        elif p.scheme in ("http", "https"):
            external.add(p.netloc.lower())

    text = _text(soup)
    words = len(_WORD.findall(text))
    return {
        "title": head_title,
        "description": meta(name="description"),
        "robots": meta(name="robots"),
        "canonical": canonical,
        "og_title": meta(prop="og:title"),
        "og_image": meta(prop="og:image"),
        "h1": h1,
        "h2_count": len(h2),
        "h2": h2[:12],
        "words": words,
        "images": len(imgs),
        "images_no_alt": len(no_alt),
        "schema": sorted(set(schema)),
        "internal_links": sorted(internal),
        "external_domains": sorted(external),
        "tel_links": len(soup.select('a[href^="tel:"]')),
        "text_hash": hashlib.sha1(text.encode("utf-8")).hexdigest()[:12],
        "text_sample": text[:400],
    }


def sitemap_urls(site):
    out, err = [], None
    r, e, _ = fetch(site["url"] + "/sitemap.xml")
    if r is None or r.status_code != 200:
        return out, e or f"HTTP {r.status_code}"
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)
    lastmods = re.findall(r"<url>.*?</url>", r.text, flags=re.S)
    for block in lastmods:
        loc = re.search(r"<loc>\s*([^<\s]+)", block)
        lm = re.search(r"<lastmod>\s*([^<\s]+)", block)
        if loc:
            out.append({"url": loc.group(1), "lastmod": lm.group(1)[:10] if lm else None})
    if not out:
        out = [{"url": u, "lastmod": None} for u in locs]
    return out, err


def site_checks(site):
    host = site["host"]
    checks = {}

    # 1. robots.txt
    r, e, _ = fetch(site["url"] + "/robots.txt")
    checks["robots"] = {"status": r.status_code if r is not None else None, "error": e,
                        "has_sitemap": bool(r is not None and "sitemap:" in r.text.lower()),
                        "text": r.text[:1200] if r is not None else None}

    # 2. http -> https and www -> apex
    for label, url in (("http", f"http://{host}/"), ("www", f"https://www.{host}/")):
        r, e, _ = fetch(url, allow_redirects=False, timeout=15)
        checks[label] = {"status": r.status_code if r is not None else None,
                         "location": r.headers.get("Location") if r is not None else None, "error": e}

    # 3. foreign hostnames must NOT serve our site (410 is the intended answer)
    foreign = []
    for fh in site.get("foreign_hosts_must_refuse", []):
        r, e, _ = fetch(f"https://{fh}/price", allow_redirects=False, timeout=15)
        serves = bool(r is not None and r.status_code == 200 and ("سپاهان" in r.text or host in r.text))
        foreign.append({"host": fh, "status": r.status_code if r is not None else None,
                        "serves_our_content": serves, "error": e})
    checks["foreign_hosts"] = foreign

    # 4. TLS certificate expiry
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ss:
                cert = ss.getpeercert()
        exp = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        checks["tls"] = {"expires": exp.date().isoformat(),
                         "days_left": (exp - datetime.now(timezone.utc)).days,
                         "issuer": dict(x[0] for x in cert.get("issuer", [])).get("organizationName")}
    except Exception as exc:                                         # noqa: BLE001
        checks["tls"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    return checks


_AGO = re.compile(r"(\d+)\s*(دقیقه|ساعت|روز|هفته|ماه|سال)\s*پیش")
_UNIT_DAYS = {"دقیقه": 0, "ساعت": 0, "روز": 1, "هفته": 7, "ماه": 30, "سال": 365}


def price_freshness(html):
    """The /price table prints 'N ماه پیش' per row. Return the freshest row's age in days."""
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    text = norm(text)
    ages = [int(n) * _UNIT_DAYS[u] for n, u in _AGO.findall(text)]
    rows = len(ages)
    return {"rows_with_age": rows,
            "freshest_days": min(ages) if ages else None,
            "oldest_days": max(ages) if ages else None}


def crawl(site=None, log=print):
    site = site or config("site.json")
    host = site["host"]
    ccfg = site["crawl"]
    types = site["page_types"]
    started = time.time()

    sm, sm_err = sitemap_urls(site)
    sm_set = {canon_url(u["url"]) for u in sm}
    sm_lastmod = {canon_url(u["url"]): u["lastmod"] for u in sm}

    queue = deque([site["url"] + "/"] + [u["url"] for u in sm])
    seen, pages = set(), {}

    def allowed(u):
        p = urllib.parse.urlsplit(u)
        if p.netloc.lower().removeprefix("www.") != host or p.query:
            return False
        path = urllib.parse.unquote(p.path)
        if any(path.startswith(x) for x in ccfg["skip_prefixes"]):
            return False
        return not any(path.lower().endswith(x) for x in ccfg["skip_extensions"])

    while queue and len(pages) < ccfg["max_pages"]:
        url = queue.popleft()
        key = canon_url(url)
        if key in seen or not allowed(url):
            continue
        seen.add(key)
        r, err, secs = fetch(url)
        time.sleep(ccfg["delay_seconds"])
        path = urllib.parse.urlsplit(key).path or "/"
        rec = {"url": key, "path": path, "type": page_type(path.rstrip("/") or "/", types),
               "in_sitemap": key in sm_set, "sitemap_lastmod": sm_lastmod.get(key),
               "status": r.status_code if r is not None else None, "error": err, "seconds": secs,
               "final_url": canon_url(r.url) if r is not None else None,
               "redirected": bool(r is not None and r.history), "bytes": len(r.content) if r is not None else 0}
        if r is not None and r.history and canon_url(r.url) != key:
            # a redirect is its own finding (internal links should point at the target);
            # the target is crawled under its own URL
            rec["redirect_to"] = canon_url(r.url)
            rec["redirect_status"] = r.history[0].status_code
            queue.append(r.url)
        elif r is not None and r.status_code == 200 and "text/html" in r.headers.get("Content-Type", ""):
            rec.update(parse_page(r.url, r.text, host))
            if rec["type"] == "price":
                rec["price_freshness"] = price_freshness(r.text)
            for link in rec["internal_links"]:
                if canon_url(link) not in seen:
                    queue.append(link)
        pages[key] = rec
        if len(pages) % 25 == 0:
            log(f"  crawled {len(pages)} pages…")

    # incoming internal links, and who links to the pages that are not a clean 200
    inbound = {k: 0 for k in pages}
    linked_from = {k: [] for k in pages}
    for p in pages.values():
        for link in set(canon_url(l) for l in p.get("internal_links", [])):
            if link in inbound and link != p["url"]:
                inbound[link] += 1
                if len(linked_from[link]) < 5:
                    linked_from[link].append(p["url"])
    for k, p in pages.items():
        p["inlinks"] = inbound.get(k, 0)
        p["outlinks"] = len(p.get("internal_links", []))
        p.pop("internal_links", None)
        if p["status"] != 200 or p.get("redirect_to"):
            p["linked_from"] = linked_from.get(k, [])

    broken = [p for p in pages.values() if p["status"] != 200 and not p.get("redirect_to")]
    redirects = [p for p in pages.values() if p.get("redirect_to")]

    return {
        "crawled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_s": round(time.time() - started),
        "sitemap": {"count": len(sm), "error": sm_err,
                    "not_crawlable": [decode_url(u["url"]) for u in sm
                                      if canon_url(u["url"]) not in pages]},
        "checks": site_checks(site),
        "pages": sorted(pages.values(), key=lambda p: p["url"]),
        "broken": [{"url": p["url"], "status": p["status"], "error": p["error"],
                    "linked_from": p.get("linked_from", [])} for p in broken],
        "redirects": [{"url": p["url"], "to": p["redirect_to"], "status": p["redirect_status"],
                       "inlinks": p["inlinks"], "linked_from": p.get("linked_from", [])} for p in redirects],
    }
