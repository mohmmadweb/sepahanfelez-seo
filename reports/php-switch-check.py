#!/usr/bin/env python3
"""
Snapshot the live site's behaviour so a PHP-version switch can be proved safe
instead of assumed safe.

    python3 php-switch-check.py before.json      # while cPanel is still on 7.4
    ... flip cPanel to 8.1 ...
    python3 php-switch-check.py after.json
    python3 php-switch-check.py --diff before.json after.json

Every request is a GET. Nothing here places an order, sends an SMS, or writes a
row. The five paths that DO write — cart, order, payment, Excel import, admin
panel — are deliberately absent and must be walked by hand; SESSION-HANDOFF §8.1.

The comparison is on a *normalised* body: CSRF tokens, the live clock and
cache-busting query strings are stripped first, because those differ between two
requests on the same PHP version and would drown the real signal.
"""

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://sepahanfelez.ir"
TIMEOUT = 45

# Each probe names the PHP-8 risk it stands in for. A probe that cannot fail
# differently across versions is not worth the request.
PROBES = [
    # path, label, why this one, substrings that must be present on a 200
    ("/", "home",
     "view composers, cached menu tree, slider",
     ["<title", "سپاهان"]),
    ("/price", "price-list",
     "the biggest query; jalali dates; price formatting",
     ["<table", "قیمت"]),
    ("/category/", "category-list",
     "category tree recursion",
     ["<title"]),
    ("/category/" + urllib.parse.quote("سیم-خاردار"), "category-page",
     "Product/Offer schema, chart bootstrapping",
     ['"@type": "ItemList"', '"@type": "Offer"']),
    ("/blog", "blog-index", "pagination, article excerpts", ["<title"]),
    # 410 on purpose — /news is retired and served Gone from the redirects
    # table. Probed anyway: if it starts 200ing or 500ing, something changed.
    ("/news", "news-gone", "the retired section still answers 410", [], 410),
    ("/about", "about", "static page + layout", ["<title"]),
    ("/contact", "contact", "form rendering, CSRF", ["<form"]),
    ("/login", "login", "the rebuilt auth screen", ["<form"]),
    ("/register", "register", "the rebuilt auth screen", ["<form"]),
    ("/cart", "cart", "session driver round-trip", ["<title"]),
    ("/sitemap.xml", "sitemap",
     "ext-xml / ext-xmlwriter — laravelium/sitemap",
     ["<urlset", "<loc>"]),
    ("/robots.txt", "robots", "served at all", ["User-agent"]),
    # "حصاری" and not "سیم": the controller returns only leaf categories, so a
    # parent's name matches the LIKE and is then filtered back out to []. A
    # probe that returns an empty list on a healthy site proves nothing.
    ("/api/category-search/" + urllib.parse.quote("حصاری"), "search-api",
     "ext-mbstring on Persian input; JSON encoding",
     ['"title"']),
]

# Applied before hashing. Order matters: the broadest last.
NOISE = [
    (re.compile(rb'name="_token"\s+value="[^"]*"'), b'name="_token" value="X"'),
    (re.compile(rb'csrf-token"\s+content="[^"]*"'), b'csrf-token" content="X"'),
    (re.compile(rb'\bXSRF-TOKEN=[^;"\s]+'), b'XSRF-TOKEN=X'),
    (re.compile(rb'\?id=[0-9a-f]{8,}'), b'?id=X'),          # mix versioning
    (re.compile(rb'\b\d{2}:\d{2}:\d{2}\b'), b'HH:MM:SS'),   # the live clock
    (re.compile(rb'<!--.*?-->', re.S), b''),
]

# A PHP 8 fatal that Laravel cannot catch prints as raw text before the layout,
# so the page can be a 200 and still be broken.
PHP_NOISE = re.compile(
    r"(Fatal error|Parse error|Uncaught \w*Error|Deprecated:|"
    r"Warning: Undefined|Whoops)")


def normalise(body: bytes) -> bytes:
    for pattern, repl in NOISE:
        body = pattern.sub(repl, body)
    return body


def fetch(path: str, required: list, expect: int = 200) -> dict:
    req = urllib.request.Request(BASE + path, headers={
        "User-Agent": "php-switch-check/1.0",
        "Accept-Language": "fa,en;q=0.8",
    })
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body, status = resp.read(), resp.status
    except urllib.error.HTTPError as exc:
        body, status = exc.read(), exc.code
    except Exception as exc:                       # noqa: BLE001 — a probe, not a library
        return {"status": 0, "error": f"{type(exc).__name__}: {exc}"}

    text = body.decode("utf-8", "replace")
    return {
        "status": status,
        "expect": expect,
        "bytes": len(body),
        "ms": round((time.time() - started) * 1000),
        "hash": hashlib.sha256(normalise(body)).hexdigest()[:16],
        "missing": [s for s in required if s not in text],
        "php_error": bool(PHP_NOISE.search(text)),
        "laravel_500": "Server Error" in text,
    }


def broken(r: dict) -> bool:
    return (r.get("status") != r.get("expect", 200) or r.get("php_error")
            or r.get("laravel_500") or r.get("missing"))


def run(out_path: str) -> int:
    results, failures = {}, []
    for probe in PROBES:
        path, label, why, required = probe[:4]
        expect = probe[4] if len(probe) > 4 else 200
        r = fetch(path, required, expect)
        r["why"] = why
        results[label] = r
        if broken(r):
            failures.append(label)
        note = ""
        if r.get("missing"):
            note = "  MISSING " + ", ".join(r["missing"])
        if r.get("php_error"):
            note += "  PHP ERROR IN BODY"
        print(f"{'FAIL' if broken(r) else 'ok  '} {label:16} "
              f"{r.get('status')} {r.get('bytes', 0):>8}B "
              f"{r.get('ms', 0):>5}ms  {why}{note}")

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print(f"\nwrote {out_path}")
    if failures:
        print("FAILING: " + ", ".join(failures))
        return 1
    return 0


def diff(before_path: str, after_path: str) -> int:
    before = json.load(open(before_path, encoding="utf-8"))
    after = json.load(open(after_path, encoding="utf-8"))
    regressions = 0

    for label in sorted(set(before) | set(after)):
        b, a = before.get(label, {}), after.get(label, {})
        bs, as_ = b.get("status"), a.get("status")
        bb, ab = b.get("bytes", 0), a.get("bytes", 0)
        hard, soft = [], []

        if bs != as_:
            hard.append(f"status {bs}→{as_}")
        if a.get("php_error") and not b.get("php_error"):
            hard.append("NEW PHP ERROR")
        if a.get("laravel_500") and not b.get("laravel_500"):
            hard.append("NEW 500")
        if a.get("missing") and not b.get("missing"):
            hard.append("LOST " + ", ".join(a["missing"]))
        # A page that lost a third of its weight usually lost a section to a
        # swallowed error, and still returns 200.
        if bb and ab and ab < bb * 0.66:
            hard.append(f"SHRANK {bb}→{ab}")
        # Content differing is expected on a live database. Worth printing,
        # never on its own a failure.
        if b.get("hash") and a.get("hash") and b["hash"] != a["hash"]:
            soft.append("content changed")

        regressions += bool(hard)
        mark = "!!" if hard else (" ~" if soft else "  ")
        print(f"{mark} {label:14} {bs!s:>5}→{as_!s:<5} {bb:>6}→{ab:<6} "
              f"{b.get('ms', 0):>5}→{a.get('ms', 0):<5}  "
              + "; ".join(hard + soft))

    print()
    if regressions:
        print(f"{regressions} regression(s). Roll cPanel back to 7.4 first, "
              f"then investigate. The rollback costs nothing.")
        return 1
    print("No regressions. 'content changed' is normal on a live database — "
          "open those pages and look at them anyway.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--diff":
        sys.exit(diff(sys.argv[2], sys.argv[3]))
    if len(sys.argv) == 2:
        sys.exit(run(sys.argv[1]))
    print(__doc__)
    sys.exit(2)
