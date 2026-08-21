#!/usr/bin/env python3
"""Crawl sepahanfelez.ir and report every remaining trace of the Ahan Amn brand.

Usage: trace_scan.py [out.json]
"""
import json
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "https://sepahanfelez.ir"

# Every way the old brand shows up. Key -> regex.
PATTERNS = {
    "domain_com": re.compile(r"ahanamn\.com", re.I),
    "domain_org": re.compile(r"ahanamn\.org", re.I),
    "word_latin": re.compile(r"ahan[\s._-]?amn", re.I),
    "word_fa": re.compile(r"آهن\s*امن"),
    "social_handle": re.compile(r"(instagram|aparat|linkedin|telegram|t\.me|tg://)[^\"'<>\s]*ahanamn", re.I),
    "dead_email_domain": re.compile(r"sepahanfelez\.com"),
    "staging_host": re.compile(r"cr2\.7hostir\.com", re.I),
    # only inside JSON-LD; a bare [...] matches ordinary JavaScript
    "schema_placeholder": re.compile(
        r'<script type="application/ld\+json">[\s\S]*?"\s*\[[^\]"]{3,}\]\s*"[\s\S]*?</script>'),
    "jalali_date": re.compile(r'"date(Published|Modified)"\s*:\s*"1[34]\d\d-'),
}

session = requests.Session()
session.headers["User-Agent"] = "Mozilla/5.0 (compatible; SepahanFelezAudit/1.0)"


def discover():
    """Sitemap URLs + the index pages the sitemap omits + a few known extras."""
    urls = {BASE + p for p in ("/", "/price", "/about", "/contact", "/blog", "/category")}
    try:
        sm = session.get(BASE + "/sitemap.xml", timeout=30).text
        urls |= set(re.findall(r"<loc>([^<]+)</loc>", sm))
    except Exception as e:  # pragma: no cover
        print("sitemap fetch failed:", e, file=sys.stderr)

    # The three categories that were noindexed are absent from the sitemap.
    for slug in ("سیم-خاردار", "توری-گابیون", "سیم-خاردار/سیم-خاردار-حلقوی-90"):
        urls.add(BASE + "/category/" + urllib.parse.quote(slug, safe="/"))
    return sorted(urls)


def scan_one(url):
    rec = {"url": urllib.parse.unquote(url), "hits": {}}
    try:
        r = session.get(url, timeout=45)
    except Exception as e:
        rec["error"] = str(e)
        return rec
    rec["status"] = r.status_code
    body = r.text
    rec["bytes"] = len(r.content)

    for name, rx in PATTERNS.items():
        found = rx.findall(body)
        if found:
            snippets = []
            for m in list(rx.finditer(body))[:6]:
                snippets.append(body[max(0, m.start() - 60):m.end() + 60].replace("\n", " "))
            rec["hits"][name] = {"count": len(found), "samples": snippets}

    can = re.search(r'<link rel="canonical" href="([^"]*)"', body)
    rec["canonical"] = can.group(1) if can else None
    rob = re.search(r'<meta name="robots" content="([^"]*)"', body)
    rec["robots"] = rob.group(1) if rob else None
    rec["ld_json_blocks"] = len(re.findall(r'application/ld\+json', body))
    return rec


def main():
    urls = discover()
    print(f"scanning {len(urls)} URLs", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(scan_one, urls))

    # extra non-HTML assets
    extras = {}
    for path in ("/robots.txt", "/sitemap.xml", "/llms.txt"):
        try:
            r = session.get(BASE + path, timeout=30)
            extras[path] = {
                "status": r.status_code,
                "traces": {n: len(rx.findall(r.text)) for n, rx in PATTERNS.items() if rx.findall(r.text)},
                "body": r.text if len(r.text) < 4000 else r.text[:4000],
            }
        except Exception as e:
            extras[path] = {"error": str(e)}

    out = {"pages": results, "assets": extras}
    dest = sys.argv[1] if len(sys.argv) > 1 else "trace-scan.json"
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # ---- summary ----
    totals = {}
    pages_with = {}
    for rec in results:
        for name, h in rec.get("hits", {}).items():
            totals[name] = totals.get(name, 0) + h["count"]
            pages_with[name] = pages_with.get(name, 0) + 1
    print("\n=== TRACE SUMMARY ===")
    print(f"pages scanned: {len(results)}   non-200: "
          f"{[ (r['url'], r.get('status') or r.get('error')) for r in results if r.get('status') != 200 ]}")
    if not totals:
        print("NO TRACES FOUND ✅")
    for name in PATTERNS:
        if name in totals:
            print(f"  {name:22s} {totals[name]:5d} hits across {pages_with[name]:3d} pages")

    cans = {}
    for r in results:
        c = r.get("canonical")
        if c is None:
            k = "(missing)"
        elif c == "":
            k = "(empty)"
        elif "ahanamn" in c:
            k = "ahanamn.com"
        elif c.rstrip("/") == r["url"].rstrip("/") or urllib.parse.unquote(c).rstrip("/") == r["url"].rstrip("/"):
            k = "self-referencing OK"
        else:
            k = "other: " + c
        cans[k] = cans.get(k, 0) + 1
    print("\ncanonical distribution:")
    for k, v in sorted(cans.items(), key=lambda x: -x[1]):
        print(f"  {v:3d}  {k}")

    robs = {}
    for r in results:
        robs[r.get("robots")] = robs.get(r.get("robots"), 0) + 1
    print("\nrobots meta distribution:")
    for k, v in sorted(robs.items(), key=lambda x: -x[1]):
        print(f"  {v:3d}  {k}")

    print("\nassets:")
    for p, d in extras.items():
        print(f"  {p}: status={d.get('status')} traces={d.get('traces')}")
    print(f"\nfull detail -> {dest}")


if __name__ == "__main__":
    main()
