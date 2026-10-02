"""Assemble data/latest/* into one data.js and copy the web app into site/."""

import json
import os
import shutil

from .util import CONFIG, DATA, ROOT, config, jalali, now_tehran, read_json

WEB = os.path.join(ROOT, "web")
SITE = os.path.join(ROOT, "site")


def _l(name, default=None):
    return read_json(os.path.join(DATA, "latest", f"{name}.json"), default)


GATE_HTML = """<div id="gate" style="max-width:380px;margin:12vh auto;padding:0 16px">
<form id="gate-form" class="card" style="padding:22px">
<h2 class="sec" style="margin-top:0">ورود به داشبورد</h2>
<p class="ink2 small">داده‌های این صفحه رمزگذاری شده‌اند.</p>
<label class="small" for="gate-pass">رمز</label>
<input id="gate-pass" type="password" autocomplete="current-password" required
 style="width:100%;margin:6px 0 10px;padding:8px 10px;border:1px solid var(--border-2);border-radius:8px;background:var(--surface);min-height:42px">
<label class="small" style="display:flex;gap:6px;align-items:center;margin-bottom:12px"><input id="gate-remember" type="checkbox" checked> روی این دستگاه به خاطر بسپار</label>
<button type="submit" class="theme-btn" style="background:var(--steel);width:100%;min-height:42px">باز کردن</button>
<p id="gate-msg" class="small" role="status" style="margin:10px 0 0;color:var(--critical)"></p>
</form></div>
"""


def encrypt(plaintext, passphrase, version, iterations=310_000):
    """AES-256-GCM with a PBKDF2-SHA256 key — the same parameters lock.js uses via WebCrypto."""
    import base64
    import hashlib
    import secrets
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations, 32)
    ct = AESGCM(key).encrypt(iv, plaintext.encode("utf-8"), None)
    b = lambda x: base64.b64encode(x).decode()  # noqa: E731
    return {"salt": b(salt), "iv": b(iv), "iter": iterations, "ct": b(ct), "v": version}


def integrations(gsc, ga4, psi, crawl, comp, cal):
    def st(d):
        if not d:
            return "pending", "هنوز اجرا نشده"
        if d.get("status") == "ok":
            return ("stale", f"آخرین داده‌ی سالم {d.get('collected_at', '')[:10]}") if d.get("stale") else ("ok", d.get("collected_at", "")[:16].replace("T", " "))
        return "blocked", d.get("reason") or ""
    rows = [
        {"id": "crawl", "name": "خزنده‌ی سایت (روزانه)", "group": "سئو", "status": "ok" if crawl else "pending",
         "detail": f"{len(crawl.get('pages', []))} صفحه، {crawl.get('duration_s')} ثانیه" if crawl else ""},
        {"id": "gsc", "name": "Google Search Console", "group": "سئو", **dict(zip(("status", "detail"), st(gsc)))},
        {"id": "ga4", "name": "Google Analytics 4", "group": "سئو", **dict(zip(("status", "detail"), st(ga4)))},
        {"id": "psi", "name": "PageSpeed Insights + CrUX", "group": "سئو", **dict(zip(("status", "detail"), st(psi)))},
        {"id": "competitors", "name": "رصد رقبا (نقشه‌ی سایت روزانه)", "group": "سئو",
         "status": "ok" if comp and comp.get("competitors") else "pending",
         "detail": f"{len((comp or {}).get('competitors', []))} رقیب" if comp else ""},
        {"id": "timeir", "name": "تقویم رسمی (time.ir)", "group": "زمان‌بندی",
         "status": "ok" if cal and "time.ir" in cal.get("source", []) else "stale" if cal else "pending",
         "detail": "، ".join(cal.get("source", [])) if cal else ""},
    ]
    social = read_json(os.path.join(DATA, "social_status.json"), {}) or {}
    for r in (config("integrations.json", {}) or {}).get("manual", []):
        s = social.get(r["id"])
        if s is not None:
            r = dict(r, status="ok" if s.get("logged_in") else r["status"],
                     detail=(f"وارد شده — بررسی {s.get('checked', '')[:16].replace('T', ' ')}" if s.get("logged_in") else r["detail"]))
        rows.append(r)
    return rows


def published_history(per_network=500):
    """automation/history.py writes dashboard/data/published/<network>.jsonl; read them here."""
    out = {}
    pub = os.path.join(DATA, "published")
    for net in ("site", "telegram", "bale", "eitaa", "rubika", "whatsapp", "instagram"):
        rows = []
        path = os.path.join(pub, f"{net}.jsonl")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        out[net] = rows[-per_network:]
    return out


def assemble():
    """Everything the UI shows, as one dict. Served live by server/app.py, or baked by build()."""
    site = config("site.json")
    crawl = _l("crawl", {}) or {}
    gsc, ga4, psi = _l("gsc", {}), _l("ga4", {}), _l("psi", {})
    comp_watch = _l("competitors", {}) or {}
    cal = _l("calendar", {}) or {}
    comp_cfg = config("competitors.json", {}) or {}
    histories = {}
    for c in comp_cfg.get("competitors", []):
        d = read_json(os.path.join(DATA, "competitors", f"{c['id']}.json"), {}) or {}
        histories[c["id"]] = {"history": d.get("history", [])[-120:], "new_log": d.get("new_log", [])[-60:]}

    # trim GSC pairs to what the UI uses
    if gsc and gsc.get("status") == "ok":
        gsc = dict(gsc)
        gsc["pairs"] = sorted(gsc.get("pairs", []), key=lambda r: -r["impressions"])[:3000]

    data = {
        "generated": now_tehran().isoformat(timespec="minutes"),
        "generated_jalali": jalali(fmt="%Y/%m/%d"),
        "site": {k: site[k] for k in ("name_fa", "url", "host", "ga4_measurement_id", "brand_terms", "thresholds",
                                      "page_types", "working_days")},
        "crawl": crawl,
        "issues": _l("issues", {}) or {},
        "issues_log": read_json(os.path.join(DATA, "issues_log.json"), {}),
        "history": read_json(os.path.join(DATA, "history.json"), []),
        "keywords": config("keywords.json", {}) or {},
        "competitors": {"config": comp_cfg, "watch": comp_watch, "history": histories},
        "gsc": gsc, "ga4": ga4, "psi": psi, "inspection": _l("inspection", {}),
        "calendar": cal, "content_plan": _l("content_plan", {}),
        "roadmap": config("roadmap.json", {}) or {},
        "automation": config("automation.json", {}) or {},
        "integrations": integrations(gsc, ga4, psi, crawl, comp_watch, cal),
        "published": published_history(),
        "social_status": read_json(os.path.join(DATA, "social_status.json"), {}),
    }
    data["serp"] = _l("serp", {}) or {}
    data["competitor_candidates"] = read_json(os.path.join(DATA, "competitor_candidates.json"), {}) or {}
    data["runs"] = read_json(os.path.join(DATA, "runs.json"), {}) or {}
    data["traces"] = traces_index()
    return data


def traces_index():
    """item id → number of logged steps (the popup fetches the full trace on demand)."""
    tdir = os.path.join(DATA, "traces")
    out = {}
    if os.path.isdir(tdir):
        for f in os.listdir(tdir):
            if f.endswith(".jsonl"):
                with open(os.path.join(tdir, f), encoding="utf-8") as fh:
                    out[f[:-6]] = sum(1 for _ in fh)
    return out


def build():
    data = assemble()
    site = config("site.json")
    if os.path.isdir(SITE):
        shutil.rmtree(SITE)
    shutil.copytree(WEB, SITE)
    version = now_tehran().strftime("%Y%m%d%H%M")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    idx = os.path.join(SITE, "index.html")
    with open(idx, encoding="utf-8") as fh:
        html = fh.read()
    passphrase = os.environ.get("SF_DASHBOARD_PASSWORD") or os.environ.get("SF_PASSPHRASE")
    if passphrase:
        # protected build: only ciphertext is published; lock.js asks for the password and decrypts
        with open(os.path.join(SITE, "data.enc.js"), "w", encoding="utf-8") as fh:
            fh.write("window.SF_ENC=" + json.dumps(encrypt(payload, passphrase, version)) + ";")
        gate = (GATE_HTML + f'<script src="data.enc.js?v={version}"></script><script src="lock.js?v={version}"></script>')
        html = html.replace('<script src="data.js?v=0"></script>\n<script src="app.js?v=1"></script>', gate)
        assert "lock.js" in html, "index.html script tags changed; update build.py"
    else:
        with open(os.path.join(SITE, "data.js"), "w", encoding="utf-8") as fh:
            fh.write("window.SF=" + payload + ";")
        html = html.replace("data.js?v=0", f"data.js?v={version}")
        os.remove(os.path.join(SITE, "lock.js"))
    with open(idx, "w", encoding="utf-8") as fh:
        fh.write(html)
    with open(os.path.join(SITE, "CNAME"), "w") as fh:
        fh.write("sepahanfelezseo.lenzit.ir\n")
    with open(os.path.join(SITE, "robots.txt"), "w") as fh:
        fh.write("User-agent: *\nDisallow: /\n")
    open(os.path.join(SITE, ".nojekyll"), "w").close()
    return SITE
