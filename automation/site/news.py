"""
Daily iron-market news on the site, in Sepahan Felez's own words and format — never a copy.

    python3 news.py collect          # read the sources, score what is new (no writing)
    python3 news.py write            # pick today's best story and write it (draft)
    python3 news.py publish <id>     # publish a draft through the panel
    python3 news.py due              # write today's piece if missing, publish what is due (hourly tick)

Sources, keywords and the publishing time live in dashboard/config/news_sources.json.
A headline is scored on product/market words (مفتول، توری، میلگرد، بازار آهن…); politics, war,
sport and gold are excluded. The best fresh story not close to anything published in the last
two weeks is fetched, its text extracted, and one `claude -p` call rewrites it in the house format:

    lead (one sentence) · «در یک نگاه» (3 bullets) · «جزئیات» (own words) ·
    «برداشت سپاهان فلز برای خریداران» (what it means for buyers of wire and mesh) · byline + source link

The gate refuses copying (no run of 9+ words from the source, <12% shared 5-word phrases), any
number that is not in the source, a missing source credit, links to pages that do not exist, and
the usual article rules. A story that fails twice is dropped and the next one is tried.
News is published automatically with SITE_AUTOPUBLISH=1 under the magazine category «اخبار بازار آهن».
"""

import email.utils
import html
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import articles  # noqa: E402
import panel  # noqa: E402
import signature  # noqa: E402

from sf import trace  # noqa: E402
from sf.util import DATA as SF_DATA, config, now_tehran, read_json, today_str, write_json  # noqa: E402

NEWS = os.path.join(panel.DATA, "news")
SEEN = os.path.join(NEWS, "seen.json")
PHOTOS = os.path.join(SF_DATA, "photos")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "fa-IR,fa;q=0.9"}
# product word → Drive photo folder, for the news cover
PHOTO_FOR = [("خاردار", "سیم-خاردار"), ("مرغ", "توری-مرغی"), ("فنس", "توری-حصاری"), ("حصار", "توری-حصاری"),
             ("گابیون", "توری-گابیون"), ("پرسی", "توری-پرسی"), ("مش", "مش-جوشی-یا-مش-آهنی"), ("مفتول", "مفتول-گالوانیزه"),
             ("گالوانیزه", "توری-جوشی-گالوانیزه-رول"), ("توری", "توری-جوشی-گالوانیزه-رول")]


def cfg():
    return config("news_sources.json", {}) or {}


def _fa(s):
    return articles._fa(s)


def _now():
    return now_tehran().isoformat(timespec="seconds")


def _get(url, timeout=25):
    import requests
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
    return r.text


def _clean(t):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<!\[CDATA\[|\]\]>", "", t or "")))).strip()


# ------------------------------------------------------------------ collect
def score(text):
    c = cfg()
    t = " " + re.sub(r"[^\w\u0600-\u06FF]+", " ", (text or "").replace("\u200c", " ")) + " "
    if any(f" {x.strip()} " in t for x in c.get("exclude", [])):      # whole words: «جام» must not hit «انجام»
        return 0
    # a keyword must start a word («توری» in «توری مرغی»، «فولادی» ok; never inside «رگولاتوری»)
    return sum(w for k, w in c.get("keywords", {}).items()
               if re.search(r"(?<![\w\u0600-\u06FF])" + re.escape(k.replace("\u200c", " ")), t))


def _rss(src):
    out = []
    for it in re.findall(r"<item>(.*?)</item>", _get(src["url"]), re.S):
        title = _clean((re.search(r"<title>(.*?)</title>", it, re.S) or [0, ""])[1])
        link = _clean((re.search(r"<link>(.*?)</link>", it, re.S) or [0, ""])[1])
        desc = _clean((re.search(r"<description>(.*?)</description>", it, re.S) or [0, ""])[1])[:400]
        pub = (re.search(r"<pubDate>(.*?)</pubDate>", it, re.S) or [0, ""])[1].strip()
        try:
            when = email.utils.parsedate_to_datetime(pub).astimezone(now_tehran().tzinfo).isoformat(timespec="minutes")
        except (TypeError, ValueError):
            when = None
        if title and link.startswith("http"):
            out.append({"title": title, "url": link, "summary": desc, "published": when})
    return out


def _list(src):
    page = _get(src["url"])
    out, seen = [], set()
    for href, inner in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
        url = html.unescape(href).split("#")[0]
        if not re.match(src["link"], url) or url in seen:
            continue
        title = _clean(inner) or urllib.parse.unquote(url.rstrip("/").rsplit("/", 1)[-1]).replace("-", " ")
        if len(title) < 12:
            continue
        seen.add(url)
        out.append({"title": title, "url": url, "summary": "", "published": None})
    return out[:15]


def collect(say=print):
    """Read every source; keep relevant, fresh, unseen stories in seen.json with their score."""
    c = cfg()
    seen = read_json(SEEN, {}) or {}
    now = now_tehran()
    report = {}
    for src in c.get("sources", []):
        try:
            items = _rss(src) if src["kind"] == "rss" else _list(src)
            report[src["id"]] = {"ok": True, "items": len(items)}
        except Exception as exc:                                       # noqa: BLE001
            report[src["id"]] = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
            continue
        new = 0
        for it in items:
            if it["url"] in seen:
                continue
            s = score(it["title"] + " " + it["summary"])
            seen[it["url"]] = {**it, "source": src["id"], "source_name": src["name"], "score": s,
                               "first_seen": now.isoformat(timespec="minutes"), "used": None}
            new += 1
        report[src["id"]]["new"] = new
    cutoff = (now - timedelta(days=30)).isoformat()
    seen = {u: v for u, v in seen.items() if v["first_seen"] >= cutoff or v.get("used")}
    os.makedirs(NEWS, exist_ok=True)
    write_json(SEEN, seen)
    write_json(os.path.join(NEWS, "sources_status.json"), {"checked": _now(), "sources": report})
    say("منابع: " + "، ".join(f"{k} {'✓' if v['ok'] else '✗'}{_fa(v.get('new', 0))}" for k, v in report.items()))
    return report


def candidates():
    c = cfg()
    now = now_tehran()
    fresh = (now - timedelta(hours=c.get("max_age_hours", 48))).isoformat(timespec="minutes")
    recent = [d["fields"]["title"] + " " + (d.get("source", {}).get("title") or "") for d in all_drafts()
              if d.get("created", "") >= (now - timedelta(days=14)).isoformat()]
    out = []
    for v in (read_json(SEEN, {}) or {}).values():
        v["score"] = score(v["title"] + " " + v.get("summary", ""))   # today's keywords and rules, not those of when it was seen
        if v.get("used") or v["score"] < c.get("min_title_score", 3):
            continue
        if (v.get("published") or v["first_seen"]) < fresh:
            continue
        if any(_similar(v["title"], r) >= 0.5 for r in recent):
            continue
        out.append(v)
    return sorted(out, key=lambda v: (v["score"], v.get("published") or v["first_seen"]), reverse=True)


def _similar(a, b):
    tok = lambda t: {w for w in re.sub(r"[^\w؀-ۿ ]", " ", (t or "").replace("‌", " ")).split() if len(w) > 2}  # noqa: E731
    ta, tb = tok(a), tok(b)
    return len(ta & tb) / max(1, min(len(ta), len(tb)))


# ------------------------------------------------------------------ the source text
def page_date(raw):
    m = re.search(r'(?:article:published_time"\s+content|"datePublished"\s*:\s*|<time[^>]+datetime=)"?([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{5})', raw)
    return m.group(1) if m else None


def extract(url):
    """(main text of a news page — the container with the most paragraph text —, published date if shown)."""
    from bs4 import BeautifulSoup
    raw = _get(url)
    soup = BeautifulSoup(raw, "html.parser")
    for t in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
        t.decompose()
    best, best_len = None, 0
    for box in soup.find_all(["article", "div", "section"]):
        ps = [p.get_text(" ", strip=True) for p in box.find_all("p", recursive=True)]
        n = sum(len(p) for p in ps if len(p) > 40)
        if n > best_len:
            best, best_len = ps, n
    text = "\n".join(p for p in (best or []) if len(p) > 40)
    return re.sub(r"[ \t]+", " ", text).strip(), page_date(raw)


# ------------------------------------------------------------------ drafts
def draft_path(nid):
    return os.path.join(NEWS, "drafts", f"{nid}.json")


def load(nid):
    return read_json(draft_path(nid), None)


def save(d):
    d["updated"] = _now()
    os.makedirs(os.path.dirname(draft_path(d["id"])), exist_ok=True)
    write_json(draft_path(d["id"]), d)
    return d


def all_drafts():
    d = os.path.join(NEWS, "drafts")
    if not os.path.isdir(d):
        return []
    out = [read_json(os.path.join(d, f), {}) for f in sorted(os.listdir(d)) if f.endswith(".json")]
    return sorted([x for x in out if x], key=lambda x: x.get("created", ""))


# ------------------------------------------------------------------ the gate
def _digits(t):
    return (t or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٬٫", "0123456789,."))


def _numbers(t):
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", _digits(t))}


def _words(t):
    return re.sub(r"[^\w؀-ۿ ]", " ", (t or "").replace("‌", " ")).split()


def copy_check(text, source):
    """(longest shared run of words, share of 5-word phrases taken from the source)."""
    a, b = _words(text), _words(source)
    sb = {tuple(b[i:i + 5]) for i in range(len(b) - 4)}
    grams = [tuple(a[i:i + 5]) for i in range(len(a) - 4)]
    shared = sum(1 for g in grams if g in sb) / max(1, len(grams))
    longest, bset = 0, set()
    for n in range(6, 40):
        bset = {tuple(b[i:i + n]) for i in range(len(b) - n + 1)}
        if any(tuple(a[i:i + n]) in bset for i in range(len(a) - n + 1)):
            longest = n
        else:
            break
    return longest, shared


def gate(d, existing_slugs, targets):
    f = d.get("fields") or {}
    body = f.get("body") or ""
    text = articles._text(body)
    src = d["source"]
    words = len(text.split())
    allowed_nums = _numbers(src["text"] + " " + src["title"]) | {str(i) for i in range(0, 13)} | {"30000", "200"}
    own_nums = _numbers(articles._text(signature._strip_block(body, signature.NEWS_MARK)) + " " + f.get("title", ""))
    invented = sorted(own_nums - allowed_nums, key=len, reverse=True)
    longest, shared = copy_check(text, src["text"])
    links = [urllib.parse.unquote(urllib.parse.urlsplit(h).path).rstrip("/") or "/"
             for h in re.findall(r'href=["\']([^"\']+)', body)
             if not urllib.parse.urlsplit(h).netloc or "sepahanfelez.ir" in urllib.parse.urlsplit(h).netloc]
    external = [h for h in re.findall(r'href=["\']([^"\']+)', body)
                if urllib.parse.urlsplit(h).netloc and "sepahanfelez.ir" not in urllib.parse.urlsplit(h).netloc]
    bad_links = [l for l in links if l not in targets]
    tags = {t.lower() for t in re.findall(r"</?([a-zA-Z0-9]+)", body)}
    digits = _digits(text)
    found_phones = {re.sub(r"\D", "", m) for m in re.findall(r"0\d{2,3}[\s\-]?\d{3,4}[\s\-]?\d{4}|09\d{9}", digits)}
    slug = f.get("slug") or ""
    c = signature.cfg()
    checks = [
        ("کپی نبودن", longest < 9 and shared < 0.12,
         f"طولانی‌ترین تکه‌ی مشترک با منبع {_fa(longest)} کلمه · {_fa(round(shared * 100))}٪ عبارت‌های ۵کلمه‌ای مشترک"),
        ("عدد ساختگی نه", not invented, "عددهایی که در منبع نیست: " + "، ".join(_fa(x) for x in invented[:4]) if invented else "همه‌ی عددها از منبع"),
        ("عنوان خودمان", _similar(f.get("title", ""), src["title"]) < 0.7, f"منبع: {src['title'][:60]}"),
        ("قالب خبر سپاهان فلز", "در یک نگاه" in body and c["news_take"] in body, "«در یک نگاه» و «" + c["news_take"] + "»"),
        ("امضا و ذکر منبع", signature.NEWS_MARK in body and src["url"] in body, src["source_name"]),
        ("طول متن", 280 <= words <= 1000, f"{_fa(words)} کلمه (۲۸۰ تا ۱۰۰۰)"),
        ("لینک داخلی", len(set(links)) >= 2 and "/price" in links and not bad_links,
         f"{_fa(len(set(links)))} لینک" + (f"؛ ناموجود: {'، '.join(bad_links[:3])}" if bad_links else "")),
        ("فقط لینک منبع بیرونی", all(h == src["url"] for h in external), "، ".join(external[:2])),
        ("عنوان سئو", 20 <= len(f.get("meta_title") or "") <= 65, f"{_fa(len(f.get('meta_title') or ''))} نویسه"),
        ("توضیح متا", 100 <= len(f.get("meta_description") or "") <= 165, f"{_fa(len(f.get('meta_description') or ''))} نویسه"),
        ("نامک", bool(re.fullmatch(r"[؀-ۿa-z0-9]+(-[؀-ۿa-z0-9]+)*", slug)) and len(slug) <= 30 and slug not in existing_slugs,
         f"{slug} ({_fa(len(slug))} نویسه)"),
        ("فقط شماره‌های شرکت", found_phones <= articles.allowed_phones(), "، ".join(sorted(found_phones - articles.allowed_phones()))),
        ("ساختار", "h2" in tags and tags <= articles.ALLOWED_TAGS, "، ".join(sorted(tags - articles.ALLOWED_TAGS))),
    ]
    return [{"name": n, "ok": bool(ok), "detail": det} for n, ok, det in checks]


# ------------------------------------------------------------------ writing
def _prompt(src, targets, existing, feedback=None):
    c = signature.cfg()
    links = "\n".join(f"- {p} — {t}" for p, t in list(targets.items())[:50])
    return f"""تو دبیر خبر «{c['brand']}» ({c['about']}) هستی. خبر زیر را بخوان و یک خبر کاملاً تازه با کلمات و ساختار خودمان بنویس — نه ترجمه یا بازنویسی جمله‌به‌جمله.

اگر این خبر به بازار آهن، فولاد، مفتول، سیم، توری، مصالح یا خریداران این کالاها ربط واقعی ندارد، فقط بنویس {{"skip": true, "reason": "…"}}.

منبع: {src['source_name']} — {src['url']}
تیتر منبع: {src['title']}
متن منبع:
{src['text'][:7000]}

قالب ثابت خبر {c['brand']} (HTML، فقط تگ‌های h2, h3, p, ul, li, strong, a, table, thead, tbody, tr, th, td):
1. <p> لید: یک جمله‌ی کوتاه که می‌گوید چه شد و چرا برای بازار مهم است.
2. <h2>در یک نگاه</h2> + <ul> با ۳ بولت کوتاه از واقعیت‌های خبر.
3. <h2>جزئیات</h2> + ۲ یا ۳ پاراگراف با جمله‌بندی خودت؛ ترتیب و زاویه با منبع فرق کند.
4. <h2>{c['news_take']}</h2> + ۱ یا ۲ پاراگراف: این خبر برای خریدار مفتول، سیم و توری (پیمانکار، مرغدار، باغدار، فروشنده) چه معنایی دارد؛ محتاط و بدون پیش‌بینی عددی؛ به «قیمت لحظه‌ای» (/price) و یک صفحه‌ی محصول مرتبط از فهرست زیر لینک بده.
امضای پایانی و ذکر منبع را ننویس؛ خودکار اضافه می‌شود.

قواعد سخت:
- هیچ عدد، درصد، تاریخ یا رقمی که در متن منبع نیست ننویس. قیمت محصولات ما را ننویس.
- هیچ جمله‌ای از منبع را عیناً نیاور؛ حتی ۸ کلمه‌ی پشت‌سرهم یکسان نباشد.
- نام رقبا و فروشگاه‌های دیگر را نیاور (جز نام منبع که خودکار می‌آید). ادعای ساختگی درباره‌ی کارخانه‌ی ما نه.
- ۳۵۰ تا ۷۰۰ کلمه؛ فارسی روان؛ ارقام فارسی.
- لینک‌ها فقط این نشانی‌ها (نسبی، دقیقاً همین نوشتار):
{links}

{('ایرادهای نسخه‌ی قبل که باید رفع شود: ' + feedback) if feedback else ''}

خروجی فقط یک JSON:
{{"title": "تیتر خبر با کلمات خودمان (حداکثر ۷۰ نویسه)",
 "slug": "نامک فارسی کوتاه با خط‌تیره، حداکثر ۳۰ نویسه؛ نه یکی از: {', '.join(sorted(existing)[:40])}",
 "meta_title": "عنوان سئو ۴۰ تا ۶۰ نویسه",
 "meta_description": "توضیح متا ۱۲۰ تا ۱۶۰ نویسه",
 "description": "خلاصه‌ی ۲ جمله‌ای برای فهرست مجله",
 "keyword": "کلمه‌ی کلیدی اصلی خبر (حداکثر ۴۰ نویسه)",
 "meta_keywords": "۴ تا ۶ کلمه با ویرگول",
 "body": "<p>…</p><h2>در یک نگاه</h2>…"}}"""


def _photo(d):
    """A Drive product photo that matches the story, not used by a news piece in the last 14 days → JPEG ≤1200px."""
    import hashlib
    from PIL import Image
    from sf import drive_sync
    lib = drive_sync.library()
    text = d["fields"].get("title", "") + " " + d["source"]["title"]
    slug = next((s for w, s in PHOTO_FOR if w in text and s in lib), None)
    since = (now_tehran() - timedelta(days=14)).isoformat()
    used = {x.get("photo_src") for x in all_drafts() if x.get("created", "") >= since}
    pool = [(slug, f) for f in lib.get(slug, [])] if slug else [(k, f) for k, fs in lib.items() for f in fs]
    pool = [x for x in pool if os.path.join(*x) not in used] or pool
    if not pool:
        return None, None
    k, f = pool[int(hashlib.md5(d["id"].encode()).hexdigest(), 16) % len(pool)]
    src = os.path.join(PHOTOS, k, f)
    os.makedirs(articles.IMAGES, exist_ok=True)
    out = os.path.join(articles.IMAGES, f"{d['id']}.jpg")
    im = Image.open(src).convert("RGB")
    im.thumbnail((1200, 1200))
    for q in (85, 78, 70, 60):
        im.save(out, "JPEG", quality=q, optimize=True, progressive=True)
        if os.path.getsize(out) < 1_900_000:
            break
    return out, os.path.join(k, f)


def targets():
    t = articles.link_targets({})
    return t


def write(say=print):
    c = cfg()
    tg = targets()
    existing = {p.rsplit("/", 1)[-1] for p in tg if p.startswith("/blog/")}
    existing |= {x["fields"].get("slug") for x in all_drafts() if x.get("fields")}
    seen = read_json(SEEN, {}) or {}
    tried = 0
    for cand in candidates():
        if tried >= 3:
            break
        tried += 1
        nid = f"{today_str()}-news-{len([x for x in all_drafts() if x['id'].startswith(today_str())]) + 1}"
        try:
            text, when = extract(cand["url"])
        except Exception as exc:                                       # noqa: BLE001
            seen[cand["url"]]["used"] = f"unreadable: {type(exc).__name__}"
            continue
        if when and when[:16] < (now_tehran() - timedelta(hours=c.get("max_age_hours", 48))).strftime("%Y-%m-%dT%H:%M"):
            seen[cand["url"]]["used"] = f"old: {when[:10]}"
            continue
        if len(text.split()) < 120 or score(cand["title"] + " " + text[:4000]) < c.get("min_score", 6):
            seen[cand["url"]]["used"] = "too short or off-topic"
            continue
        d = {"id": nid, "created": _now(), "date": today_str(), "time": c.get("time", "10:00"), "kind": "news",
             "source": {**{k: cand[k] for k in ("title", "url", "source_name", "published", "score")}, "text": text[:9000]}}
        trace.step(nid, "brief", "انتخاب خبر", f"{cand['source_name']}: {cand['title']}",
                   decision=f"امتیاز ربط {_fa(cand['score'])}؛ بالاترین خبر تازه‌ی غیرتکراری",
                   data={"url": cand["url"]})
        feedback, cost, skipped = None, 0.0, False
        for attempt in (1, 2):
            say(f"نوشتن خبر (تلاش {_fa(attempt)}): {cand['title'][:60]}")
            out, cst = articles._llm(_prompt(d["source"], tg, existing, feedback))
            cost += cst
            if out.get("skip"):
                skipped = True
                trace.step(nid, "qa", "کنار گذاشته شد", str(out.get("reason", ""))[:200])
                break
            d["fields"] = {k: str(out.get(k) or "").strip() for k in
                           ("title", "slug", "meta_title", "meta_description", "description", "keyword", "meta_keywords", "body")}
            d["fields"]["slug"] = re.sub(r"[\s_]+", "-", d["fields"]["slug"]).strip("-").replace("؟", "")
            d["fields"]["body"] = signature.news_byline(d["fields"]["body"], cand["source_name"], cand["url"])
            d["gate"] = gate(d, existing, tg)
            failed = [g for g in d["gate"] if not g["ok"]]
            trace.step(nid, "qa", "کنترل کیفیت خبر", "همه قبول" if not failed else "رد: " + "، ".join(g["name"] for g in failed),
                       data={"usd": round(cst, 3)})
            if not failed:
                break
            feedback = "؛ ".join(f"{g['name']}: {g['detail']}" for g in failed)
        seen[cand["url"]]["used"] = nid
        write_json(SEEN, seen)
        if skipped:
            continue
        d["cost_usd"] = round(cost, 3)
        if [g for g in d["gate"] if not g["ok"]]:
            d["status"] = "dropped"
            save(d)
            say(f"✗ رد شد: {d['fields']['title']}")
            continue
        d["image"], d["photo_src"] = _photo(d)
        d["status"] = "draft"
        save(d)
        say(f"✓ پیش‌نویس خبر: {d['fields']['title']}")
        return d
    write_json(SEEN, seen)
    return None


# ------------------------------------------------------------------ publishing
def ensure_category(p):
    c = cfg()
    cats = p.category_options()
    cid = cats.get(c["category"])
    if cid:
        return cid
    p.create_category({"title": c["category"], "slug": c["category_slug"], "keyword": "اخبار بازار آهن",
                       "meta_title": "اخبار بازار آهن، فولاد و مفتول | سپاهان فلز",
                       "meta_description": "خبرهای روز بازار آهن، فولاد، مفتول و توری با تحلیل کوتاه سپاهان فلز برای خریداران عمده، پیمانکاران و فروشندگان.",
                       "meta_keywords": "اخبار بازار آهن، اخبار فولاد، بازار مفتول، قیمت آهن"})
    cid = p.category_options().get(c["category"])
    if not cid:
        raise RuntimeError("دسته‌ی «اخبار بازار آهن» ساخته نشد")
    return cid


def publish(nid, say=print, force=False):
    import history
    d = load(nid)
    if not d:
        raise RuntimeError("خبر پیدا نشد")
    if d.get("status") == "published":
        return d
    if not force and d.get("status") != "approved" and not (articles.autopublish() and d.get("status") == "draft"):
        raise RuntimeError("این خبر تأیید نشده")
    with panel.Panel() as p:
        cid = ensure_category(p)
        if d["fields"]["slug"] in {a["path"].rsplit("/", 1)[-1] for a in p.articles()}:
            d["fields"]["slug"] = (d["fields"]["slug"][:26] + "-" + now_tehran().strftime("%m%d"))[:30]
        f = dict(d["fields"], category_id=cid)
        say("ارسال خبر به پنل سایت…")
        p.create_article(f, image=d.get("image"))
        art = next((a for a in p.articles() if a["path"].rsplit("/", 1)[-1] == f["slug"]), None)
        if not art:
            raise RuntimeError("پنل ذخیره کرد ولی خبر در فهرست پیدا نشد")
        url = p.base + urllib.parse.quote(art["path"])
        r = p.page.request.get(url)
    d.update({"status": "published", "published_at": _now(), "url": url, "article_id": art["id"], "live_check": r.status})
    history.record("site", "news", content_type="خبر", text=f["title"], media=d.get("image"), url=url, plan_ref=d["id"])
    trace.step(d["id"], "publish", "منتشر شد", url, decision="نشانی زنده بررسی شد: " + str(r.status))
    say(f"✓ خبر منتشر شد: {urllib.parse.unquote(url)}")
    save(d)
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "social"))
        import publisher
        publisher.share_news(d)
    except Exception as exc:                                           # noqa: BLE001
        say(f"اشتراک خبر در کانال‌ها آماده نشد: {exc}")
    return d


def due(say=print, can_publish=True):
    """Hourly: collect, write today's piece once its time is near, publish what is due."""
    c = cfg()
    now = now_tehran()
    if now.weekday() in c.get("skip_weekdays", []):
        return []
    today = [x for x in all_drafts() if x.get("date") == today_str() and x.get("status") not in ("dropped", "sample")]
    if len(today) < c.get("per_day", 1) and now.strftime("%H:%M") >= "08:00":
        write(say=say)                                    # sources are read every hour by tick.py
    out = []
    if not can_publish:
        return out
    for d in all_drafts():
        ok = d.get("status") == "approved" or (articles.autopublish() and d.get("status") == "draft")
        if ok and d.get("date") == today_str() and d.get("time", "10:00") <= now.strftime("%H:%M"):
            try:
                out.append(publish(d["id"], say=say))
            except Exception as exc:                                   # noqa: BLE001
                d["last_error"] = str(exc)[:300]
                save(d)
                try:
                    sys.path.insert(0, os.path.dirname(HERE))
                    import alert
                    alert.send("site:publish", "انتشار خبر روی سایت انجام نشد",
                               f"«{(d.get('fields') or {}).get('title', d['id'])}»: {str(exc)[:200]}",
                               "داشبورد → تولید محتوا → همین خبر → «انتشار همین حالا»؛ اگر پنل وارد نیست اول «پنل سایت» → «ورود»")
                except Exception:                                      # noqa: BLE001
                    pass
                say(f"✗ {d['id']}: {exc}")
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "due"
    if cmd == "collect":
        collect()
    elif cmd == "candidates":
        for v in candidates()[:15]:
            print(v["score"], v["source_name"], v["title"][:80], v.get("published"))
    elif cmd == "write":
        write()
    elif cmd == "publish":
        publish(sys.argv[2], force="--force" in sys.argv)
    else:
        due()
