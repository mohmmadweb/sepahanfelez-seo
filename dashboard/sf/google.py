"""
Search Console, GA4 and PageSpeed Insights.

Rule inherited from the Lenzit SEO OS: a collector that cannot reach its source
writes status="blocked" with the reason — never a zero. "0 clicks" and "we could
not ask" are different claims, and the dashboard shows them differently.

Google's API front-ends return 403 to our server's IP, so
these run in GitHub Actions. Credentials, in order of preference:
  GOOGLE_SERVICE_ACCOUNT        env var holding the JSON key itself (Actions secret)
  GOOGLE_APPLICATION_CREDENTIALS  path to the JSON key
  ~/.config/claude-seo/service_account.json
PageSpeed key: GOOGLE_API_KEY env var, or ~/.config/claude-seo/google-api.json.
"""

import json
import os
import urllib.parse
from datetime import date, timedelta

from .util import fetch, read_json

SA_FALLBACK = os.path.expanduser("~/.config/claude-seo/service_account.json")
KEY_FALLBACK = os.path.expanduser("~/.config/claude-seo/google-api.json")


def _credentials(scopes):
    try:
        from google.oauth2 import service_account
    except ImportError:
        return None, "google-auth not installed"
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
    try:
        if raw:
            return service_account.Credentials.from_service_account_info(json.loads(raw), scopes=scopes), None
        path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or SA_FALLBACK
        if os.path.exists(path):
            return service_account.Credentials.from_service_account_file(path, scopes=scopes), None
    except Exception as exc:                                          # noqa: BLE001
        return None, f"service account unusable: {type(exc).__name__}"
    return None, "no service account configured"


def _err(exc):
    msg = str(exc)
    if "<html" in msg.lower():
        msg = "HTML 403 from Google front-end (IP blocked — run in GitHub Actions)"
    return f"{type(exc).__name__}: {msg[:220]}"


# ---------------------------------------------------------------- Search Console
def collect_gsc(site, days=90):
    creds, reason = _credentials(["https://www.googleapis.com/auth/webmasters.readonly"])
    if not creds:
        return {"status": "blocked", "reason": reason}
    try:
        from googleapiclient.discovery import build
        svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        props = [s["siteUrl"] for s in svc.sites().list().execute().get("siteEntry", [])]
        wanted = [os.environ.get("GSC_PROPERTY"), site["gsc_property"], site["gsc_property_fallback"]]
        prop = next((p for p in wanted if p and p in props), None)
        if not prop:
            return {"status": "blocked",
                    "reason": "service account has no access to the sepahanfelez.ir property "
                              f"(visible: {', '.join(props) or 'none'})"}
        end = date.today() - timedelta(days=2)
        start = end - timedelta(days=days - 1)
        s28 = end - timedelta(days=27)

        def q(dimensions, start_date, rows=1000, **extra):
            body = {"startDate": start_date.isoformat(), "endDate": end.isoformat(),
                    "dimensions": dimensions, "rowLimit": rows, **extra}
            return svc.searchanalytics().query(siteUrl=prop, body=body).execute().get("rows", [])

        def rows(rs, keys):
            return [dict(zip(keys, r["keys"]), clicks=r["clicks"], impressions=r["impressions"],
                         ctr=round(r["ctr"] * 100, 2), position=round(r["position"], 1)) for r in rs]

        daily = rows(q(["date"], start), ["date"])
        queries = rows(q(["query"], s28, 2000), ["query"])
        pages = rows(q(["page"], s28, 1000), ["page"])
        pairs = rows(q(["query", "page"], s28, 5000), ["query", "page"])
        devices = rows(q(["device"], s28, 10), ["device"])
        # per-query daily positions for the tracked keyword set is done client-side from pairs;
        # a 7-day window gives the "this week" position next to the 28-day one.
        s7 = end - timedelta(days=6)
        queries7 = rows(q(["query"], s7, 2000), ["query"])

        sitemaps = []
        try:
            for sm in svc.sitemaps().list(siteUrl=prop).execute().get("sitemap", []):
                sitemaps.append({"path": sm.get("path"), "lastDownloaded": sm.get("lastDownloaded"),
                                 "errors": sm.get("errors"), "warnings": sm.get("warnings"),
                                 "submitted": sum(int(c.get("submitted", 0)) for c in sm.get("contents", [])),
                                 "indexed": sum(int(c.get("indexed", 0)) for c in sm.get("contents", []))})
        except Exception:                                             # noqa: BLE001
            pass

        return {"status": "ok", "property": prop, "window": [start.isoformat(), end.isoformat()],
                "daily": daily, "queries": queries, "queries_7d": queries7, "pages": pages,
                "pairs": pairs, "devices": devices, "sitemaps": sitemaps}
    except Exception as exc:                                          # noqa: BLE001
        return {"status": "blocked", "reason": _err(exc)}


def inspect_urls(site, urls, limit=40):
    """URL Inspection API: index status per page (2000/day quota; we use ≤40)."""
    creds, reason = _credentials(["https://www.googleapis.com/auth/webmasters.readonly"])
    if not creds:
        return {"status": "blocked", "reason": reason}
    try:
        from googleapiclient.discovery import build
        svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        props = [s["siteUrl"] for s in svc.sites().list().execute().get("siteEntry", [])]
        wanted = [os.environ.get("GSC_PROPERTY"), site["gsc_property"], site["gsc_property_fallback"]]
        prop = next((p for p in wanted if p and p in props), None)
        if not prop:
            return {"status": "blocked", "reason": "no GSC property access"}
        out = {}
        for u in urls[:limit]:
            try:
                res = svc.urlInspection().index().inspect(body={
                    "inspectionUrl": urllib.parse.quote(u, safe=":/"), "siteUrl": prop}).execute()
                ir = res.get("inspectionResult", {}).get("indexStatusResult", {})
                out[u] = {"verdict": ir.get("verdict"), "coverage": ir.get("coverageState"),
                          "lastCrawl": ir.get("lastCrawlTime"), "googleCanonical": ir.get("googleCanonical")}
            except Exception as exc:                                  # noqa: BLE001
                out[u] = {"error": _err(exc)}
        return {"status": "ok", "urls": out}
    except Exception as exc:                                          # noqa: BLE001
        return {"status": "blocked", "reason": _err(exc)}


# ---------------------------------------------------------------- GA4
def collect_ga4(site, days=90):
    prop = os.environ.get("GA4_PROPERTY_ID") or os.environ.get("GA4_PROPERTY") or site.get("ga4_property")
    if not prop:
        return {"status": "blocked", "reason": "GA4 property id not set (.env → GA4_PROPERTY_ID)"}
    creds, reason = _credentials(["https://www.googleapis.com/auth/analytics.readonly"])
    if not creds:
        return {"status": "blocked", "reason": reason}
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
        client = BetaAnalyticsDataClient(credentials=creds)
        prop = prop if str(prop).startswith("properties/") else f"properties/{prop}"
        rng = [DateRange(start_date=f"{days}daysAgo", end_date="yesterday")]

        def report(dims, mets, limit=1000):
            resp = client.run_report(RunReportRequest(
                property=prop, date_ranges=rng, limit=limit,
                dimensions=[Dimension(name=d) for d in dims], metrics=[Metric(name=m) for m in mets]))
            return [dict(zip(dims + mets, [v.value for v in r.dimension_values] +
                             [float(v.value) for v in r.metric_values])) for r in resp.rows]

        daily = report(["date", "sessionDefaultChannelGroup"], ["sessions", "totalUsers"])
        landing = report(["landingPagePlusQueryString", "sessionDefaultChannelGroup"],
                         ["sessions", "engagementRate", "keyEvents"], 500)
        events = report(["eventName"], ["eventCount"], 100)
        sources = report(["sessionSource", "sessionMedium"], ["sessions"], 50)
        devices = report(["deviceCategory"], ["sessions"], 10)
        cities = report(["city"], ["sessions"], 30)
        return {"status": "ok", "property": prop, "daily": daily, "landing": landing,
                "events": events, "sources": sources, "devices": devices, "cities": cities}
    except Exception as exc:                                          # noqa: BLE001
        return {"status": "blocked", "reason": _err(exc)}


# ---------------------------------------------------------------- PageSpeed Insights
def collect_psi(site):
    key = os.environ.get("GOOGLE_API_KEY") or (read_json(KEY_FALLBACK, {}) or {}).get("api_key")
    results, blocked = [], None
    for url in site["psi_urls"]:
        for strategy in ("mobile", "desktop"):
            api = ("https://www.googleapis.com/pagespeedonline/v5/runPagespeed?"
                   + urllib.parse.urlencode({"url": url, "strategy": strategy, "locale": "fa"})
                   + "&category=performance&category=seo&category=accessibility&category=best-practices"
                   + (f"&key={key}" if key else ""))
            r, err, _ = fetch(api, timeout=150)
            if r is None or r.status_code != 200:
                reason = err or f"HTTP {r.status_code}"
                if r is not None and "<html" in r.text[:200].lower():
                    reason = "HTML 403 from Google front-end (IP blocked — run in GitHub Actions)"
                elif r is not None:
                    try:
                        reason = r.json().get("error", {}).get("message", reason)[:200]
                    except ValueError:
                        pass
                blocked = reason
                results.append({"url": url, "strategy": strategy, "status": "blocked", "reason": reason})
                continue
            d = r.json()
            lr = d.get("lighthouseResult", {})
            cats = {k: round((v.get("score") or 0) * 100) for k, v in lr.get("categories", {}).items()}
            au = lr.get("audits", {})
            field = d.get("loadingExperience", {}).get("metrics", {})
            results.append({
                "url": url, "strategy": strategy, "status": "ok", "scores": cats,
                "lab": {k: au.get(k, {}).get("numericValue") for k in
                        ("largest-contentful-paint", "cumulative-layout-shift", "total-blocking-time",
                         "first-contentful-paint", "speed-index", "server-response-time")},
                "field": {k: {"p75": v.get("percentile"), "category": v.get("category")}
                          for k, v in field.items()},
                "field_overall": d.get("loadingExperience", {}).get("overall_category"),
                "opportunities": sorted(
                    [{"id": k, "title": a.get("title"), "savings_ms": a.get("details", {}).get("overallSavingsMs")}
                     for k, a in au.items()
                     if a.get("details", {}).get("type") == "opportunity"
                     and (a.get("details", {}).get("overallSavingsMs") or 0) > 150],
                    key=lambda x: -(x["savings_ms"] or 0))[:6],
            })
    ok = any(r["status"] == "ok" for r in results)
    return {"status": "ok" if ok else "blocked", "reason": None if ok else blocked, "results": results}
