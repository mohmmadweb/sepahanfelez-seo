"""
Daily search-result check for the tracked keywords → our position + who else ranks.

Provider chain (first that works wins, and the dashboard says which one answered):
  1. Serper.dev       real Google results for Iran (gl=ir, hl=fa) — needs SERPER_API_KEY
  2. Startpage        Google's results through Startpage — free, region not guaranteed
  3. DuckDuckGo       Bing-based index — free, last resort
Google itself captcha-blocks this server.

Any domain that ranks in the top 10 for a tracked keyword and is not a known competitor
(or a marketplace/encyclopedia we ignore) becomes a *candidate*. The dashboard shows
candidates with the keywords and positions they hold, and the owner accepts or ignores them;
accepted ones join the daily sitemap watch.
"""

import json
import os
import random
import time
import urllib.parse

from .util import DATA, config, now_tehran, norm, read_json, today_str, write_json

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
OUR = "sepahanfelez.ir"
# never competitors: marketplaces, encyclopedias, video, social, maps, price aggregators
NOT_COMPETITORS = {"torob.com", "digikala.com", "divar.ir", "sheypoor.com", "wikipedia.org", "fa.wikipedia.org",
                   "aparat.com", "youtube.com", "instagram.com", "t.me", "basalam.com", "emalls.ir",
                   "google.com", "bing.com", "pinterest.com", "linkedin.com", "facebook.com", "namnak.com",
                   "chetor.com", "beytoote.com", "tebyan.net", "virgool.io", "bazaar.ir", "neshan.org",
                   "balad.ir", "snapp.market", "esam.ir", "takhfifan.com", "irancode.ir"}
CAND_PATH = os.path.join(DATA, "competitor_candidates.json")


def bare(host):
    host = (host or "").lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def tracked_keywords(limit=24):
    """Primary keyword of each priority product + head terms + top commercial keywords."""
    kw = config("keywords.json", {}) or {}
    out = []
    for p in kw.get("products", []):
        if p.get("primary"):
            out.append({"kw": p["primary"], "product": p["id"], "target": p.get("target_url")})
    for k in sorted((k for k in kw.get("keywords", []) if k.get("cluster") == "head"),
                    key=lambda k: -(k.get("seen_count") or 0))[:5]:
        out.append({"kw": k["kw"], "product": "head", "target": k.get("target_url")})
    extra = (config("site.json", {}) or {}).get("serp_extra_keywords", [])
    out += [{"kw": k, "product": "extra", "target": None} for k in extra]
    seen, uniq = set(), []
    for k in out:
        if norm(k["kw"]) not in seen:
            seen.add(norm(k["kw"]))
            uniq.append(k)
    return uniq[:limit]


# ---------------------------------------------------------------- providers
def _serper(q, key):
    import requests
    r = requests.post("https://google.serper.dev/search", timeout=30,
                      headers={"X-API-KEY": key, "Content-Type": "application/json"},
                      json={"q": q, "gl": "ir", "hl": "fa", "num": 30})
    r.raise_for_status()
    return [o["link"] for o in r.json().get("organic", [])]


def _browser_search(page, engine, q):
    if engine == "startpage":
        urls = []
        for pg in (1, 2):
            page.goto("https://www.startpage.com/do/search?lui=farsi&language=farsi&page=%d&query=%s"
                      % (pg, urllib.parse.quote(q)), timeout=40000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            got = page.eval_on_selector_all("a.result-title, a.w-gl__result-title", "els=>els.map(e=>e.href)")
            if not got:
                break
            urls += got
            time.sleep(random.uniform(2, 4))
        return urls
    if engine == "duckduckgo":
        page.goto("https://duckduckgo.com/?kl=ir-fa&q=" + urllib.parse.quote(q), timeout=40000,
                  wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        return page.eval_on_selector_all("article[data-testid=result] a[data-testid=result-title-a]",
                                         "els=>els.map(e=>e.href)")
    return []


def check(log=print):
    keywords = tracked_keywords()
    key = os.environ.get("SERPER_API_KEY")
    results, provider_used, errors = [], None, []
    page = browser = pw = None
    try:
        if not key:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            browser = pw.chromium.launch()
            page = browser.new_context(user_agent=UA, locale="fa-IR").new_page()
        queue = list(keywords)
        retried = set()
        while queue:
            k = queue.pop(0)
            urls, prov = [], None
            chain = ["serper"] if key else ["startpage", "duckduckgo"]
            for engine in chain:
                try:
                    urls = _serper(k["kw"], key) if engine == "serper" else _browser_search(page, engine, k["kw"])
                except Exception as exc:                                  # noqa: BLE001
                    errors.append(f"{engine}: {type(exc).__name__}")
                    urls = []
                if urls:
                    prov = engine
                    break
            if not urls and k["kw"] not in retried:
                retried.add(k["kw"])          # rate limit or captcha: one more try at the end of the run
                queue.append(k)
                time.sleep(random.uniform(8, 15))
                continue
            provider_used = provider_used or prov
            seen, ranked = set(), []
            for u in urls:
                d = bare(urllib.parse.urlsplit(u).netloc)
                if d and d not in seen:
                    seen.add(d)
                    ranked.append({"domain": d, "url": urllib.parse.unquote(u)})
            ours = next((i + 1 for i, r in enumerate(ranked) if r["domain"] == OUR), None)
            results.append({"kw": k["kw"], "product": k["product"], "target": k["target"], "provider": prov,
                            "checked_at": now_tehran().isoformat(timespec="seconds"),
                            "our_position": ours, "top": ranked[:20]})
            log(f"  «{k['kw']}» [{prov or '—'}] ما: {ours or '+۲۰'} · نفر اول: {ranked[0]['domain'] if ranked else '—'}")
            time.sleep(random.uniform(4, 8))
    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()

    snap = {"checked_at": now_tehran().isoformat(timespec="seconds"), "provider": provider_used,
            "provider_note": {"serper": "نتایج واقعی گوگل ایران (Serper)",
                              "startpage": "نتایج گوگل از راه Startpage — منطقه‌ی جستجو تضمین‌شده ایران نیست",
                              "duckduckgo": "نتایج DuckDuckGo (ایندکس Bing) — تقریبی"}.get(provider_used, "هیچ منبعی جواب نداد"),
            "errors": sorted(set(errors))[:6], "keywords": results}
    _history(snap)
    _candidates(snap)
    return snap


def _history(snap):
    path = os.path.join(DATA, "serp_history.json")
    hist = read_json(path, {}) or {}
    for r in snap["keywords"]:
        rows = [x for x in hist.get(r["kw"], []) if x["date"] != today_str()]
        rows.append({"date": today_str(), "ts": r["checked_at"], "pos": r["our_position"], "provider": r["provider"],
                     "top3": [t["domain"] for t in r["top"][:3]]})
        hist[r["kw"]] = rows[-365:]
    write_json(path, hist)
    snap["history"] = {k: v[-60:] for k, v in hist.items()}


def _candidates(snap):
    comp = config("competitors.json", {}) or {}
    known = {bare(c["domain"]) for c in comp.get("competitors", [])}
    store = read_json(CAND_PATH, {}) or {}
    ignored = set(store.get("ignored", []))
    cands = store.get("candidates", {})
    today = today_str()
    for r in snap["keywords"]:
        for pos, t in enumerate(r["top"][:10], 1):
            d = t["domain"]
            if d == OUR or d in known or d in ignored or d in NOT_COMPETITORS or any(d.endswith("." + x) for x in NOT_COMPETITORS):
                continue
            c = cands.setdefault(d, {"domain": d, "first_seen": snap["checked_at"], "keywords": {}})
            c["last_seen"] = snap["checked_at"]
            c["keywords"][r["kw"]] = {"pos": pos, "url": t["url"], "date": today}
    for d, c in cands.items():
        c["new"] = c["first_seen"][:10] == today
        c["keyword_count"] = len(c["keywords"])
        c["best_pos"] = min((v["pos"] for v in c["keywords"].values()), default=None)
    store.update({"candidates": cands, "ignored": sorted(ignored), "updated": snap["checked_at"]})
    write_json(CAND_PATH, store)


def decide(domain, action):
    """action: accept → add to competitors.json watch list; ignore → never suggest again."""
    domain = bare(domain)
    store = read_json(CAND_PATH, {}) or {}
    cand = store.get("candidates", {}).pop(domain, None)
    if action == "ignore":
        store["ignored"] = sorted(set(store.get("ignored", [])) | {domain})
    elif action == "accept":
        path_cfg = os.path.join(os.path.dirname(DATA), "config", "competitors.json")
        comp = read_json(path_cfg, {"competitors": []}) or {"competitors": []}
        if domain not in {bare(c["domain"]) for c in comp["competitors"]}:
            comp["competitors"].append({
                "id": domain.split(".")[0].replace("-", "_"), "name_fa": domain, "domain": domain, "threat": "medium",
                "source": "serp-discovery", "owner_products": [], "sitemaps": [], "product_pages": {},
                "notes_fa": "از رصد نتایج جستجو کشف شد: " + "، ".join(
                    f"«{k}» رتبه {v['pos']}" for k, v in (cand or {}).get("keywords", {}).items())[:400],
                "added_at": now_tehran().isoformat(timespec="seconds")})
            write_json(path_cfg, comp)
    write_json(CAND_PATH, store)
    return {"ok": True, "domain": domain, "action": action}
