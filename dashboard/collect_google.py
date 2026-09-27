#!/usr/bin/env python3
"""
Runs in GitHub Actions (Google answers 403 to our server's IP): Search Console, GA4,
PageSpeed and URL Inspection → one bundle encrypted with SF_STATE_KEY → google.enc.
The server pulls that file (branch google-data) and decrypts it with the same key from .env.

Secrets it needs (GitHub → Settings → Secrets and variables → Actions):
  GOOGLE_SERVICE_ACCOUNT  the service-account JSON (same file GOOGLE_APPLICATION_CREDENTIALS points to)
  GOOGLE_API_KEY          same value as in .env
  SF_STATE_KEY            same value as in .env
  GA4_PROPERTY_ID         (variable, not secret) same value as in .env
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sf import google, vault  # noqa: E402
from sf.env import load_env  # noqa: E402
from sf.util import config, fetch, now_tehran  # noqa: E402

load_env()


def sitemap_urls(site):
    r, _, _ = fetch(site["url"] + "/sitemap.xml")
    return re.findall(r"<loc>\s*([^<\s]+)", r.text) if r is not None and r.status_code == 200 else []


def main(out="google.enc"):
    key = os.environ.get("SF_STATE_KEY")
    if not key:
        sys.exit("SF_STATE_KEY missing")
    site = config("site.json")
    bundle = {"collected_at": now_tehran().isoformat(timespec="minutes"),
              "gsc": google.collect_gsc(site), "ga4": google.collect_ga4(site), "psi": google.collect_psi(site)}
    if bundle["gsc"].get("status") == "ok":
        bundle["inspection"] = google.inspect_urls(site, sitemap_urls(site))
    for k in ("gsc", "ga4", "psi"):
        print(f"{k}: {bundle[k].get('status')} {bundle[k].get('reason') or ''}")
    with open(out, "wb") as fh:
        fh.write(vault.encrypt_json(bundle, key))
    print(f"→ {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
