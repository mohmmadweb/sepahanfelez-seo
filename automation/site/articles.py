"""
Site articles: write → check → (approve) → publish through the panel → verify → record.

    python3 articles.py write [item_id]    # next planned article without a draft, or that item
    python3 articles.py publish <item_id>  # an approved (or, with SITE_AUTOPUBLISH=1, passing) draft
    python3 articles.py due                # publish whatever is due now (the hourly timer)

The plan (dashboard/data/latest/content_plan.json) says which product, which keyword and
which photo on which day. The writer is one `claude -p` call (Sonnet, no tools) given only
facts we hold: the factory's own details, the product names/specs from the live category
page, and real internal pages to link. Code then checks the draft (the «gate»): length,
keyword placement, internal links that exist, no prices, no phone numbers but the company's,
slug free and ≤30 characters. A draft that fails twice waits for a person.

Drafts live in dashboard/data/site/drafts/<item_id>.json; nothing is sent to the site until
the draft is approved in the dashboard, unless SITE_AUTOPUBLISH=1 (then a passing draft goes
out at its planned time). Every step is written to the item's «روند تولید» trace.
"""

import html
import json
import os
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE)))
import panel  # noqa: E402
import signature  # noqa: E402

ROOT = panel.ROOT
sys.path.insert(0, os.path.join(ROOT, "dashboard"))
from sf import trace  # noqa: E402
from sf.util import fetch, now_tehran, read_json, today_str, write_json  # noqa: E402

DRAFTS = os.path.join(panel.DATA, "drafts")
IMAGES = os.path.join(panel.DATA, "images")
COST = os.path.join(panel.DATA, "cost.json")
PLAN = os.path.join(ROOT, "dashboard", "data", "latest", "content_plan.json")
CRAWL = os.path.join(ROOT, "dashboard", "data", "latest", "crawl.json")
KEYWORDS = os.path.join(ROOT, "dashboard", "config", "keywords.json")
PHOTO_ROOT = "/home/ubuntu/projects/sepahanfelez-prototype/assets/products"
CLAUDE = os.path.expanduser("~/.local/bin/claude")
MAX_USD_CALL, MAX_USD_DAY = 1.0, 3.0
SITE = "https://sepahanfelez.ir"

FACTS = """- نام: فروشگاه اینترنتی صنایع مفتولی طلوع سپاهان (برند «سپاهان فلز»)، تولیدکننده‌ی مستقیم، اصفهان.
- سالن تولید ۳۰٬۰۰۰ متر مربع، ۲۰۰ نفر پرسنل.
- کارخانه‌ی ۲: اصفهان، کمربندی نجف‌آباد، شهرک صنعتی منتظریه، خیابان ۱۰۱.
- دفتر فروش تهران: بازار آهن شادآباد، بلوار شهید قربانخوانی، مجتمع پارس فلز، پلاک ۹.
- شماره‌های تماس: {phones} (فقط همین‌ها).
- قیمت روز همه‌ی کالاها در صفحه‌ی «قیمت لحظه‌ای» (/price) هر روز ساعت ۱۲:۳۰ به‌روز می‌شود؛ قیمت به ریال است."""


def phones():
    """The company's published numbers, from .env (SITE_CONTACT_PHONES, comma-separated) — not kept in the public repo."""
    panel.load_env()
    return [x.strip() for x in os.environ.get("SITE_CONTACT_PHONES", "").split(",") if x.strip()]


def facts():
    return FACTS.format(phones="، ".join(_fa(p) for p in phones()) or "—")


def allowed_phones():
    out = set()
    for p in phones():
        d = re.sub(r"\D", "", p)
        out |= {d, d[3:] if d.startswith("021") else d}
    return out

# product (plan slug) → blog category title in the panel
BLOG_CATEGORY = {"مش-جوشی-یا-مش-آهنی": "توری مش", "سیم-خاردار": "سیم خاردار", "مفتول-گالوانیزه": "سیم و مفتول",
                 "سیم-سیاه-و-آرماتور-بندی": "سیم و مفتول"}
ALLOWED_TAGS = {"h2", "h3", "p", "ul", "ol", "li", "strong", "em", "a", "table", "thead", "tbody", "tr", "th", "td", "br", "blockquote"}


def _fa(s):
    return str(s).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _now():
    return now_tehran().isoformat(timespec="seconds")


def draft_path(item_id):
    return os.path.join(DRAFTS, f"{item_id}.json")


def load(item_id):
    return read_json(draft_path(item_id), None)


def save(d):
    os.makedirs(DRAFTS, exist_ok=True)
    d["updated"] = _now()
    write_json(draft_path(d["id"]), d)
    return d


def all_drafts():
    if not os.path.isdir(DRAFTS):
        return []
    out = [read_json(os.path.join(DRAFTS, f), {}) for f in sorted(os.listdir(DRAFTS)) if f.endswith(".json")]
    return sorted([d for d in out if d], key=lambda d: (d.get("date", ""), d.get("time", "")))


def autopublish():
    panel.load_env()
    return os.environ.get("SITE_AUTOPUBLISH", "0").strip() == "1"


# ------------------------------------------------------------------ context for the writer
def _plan_items():
    return [i for i in (read_json(PLAN, {}) or {}).get("items", []) if i.get("kind") == "article"]


def _product(item):
    kw = read_json(KEYWORDS, {}) or {}
    return next((p for p in kw.get("products", []) if p.get("priority") == item.get("product_rank")), {})


def _moves():
    """Old → new paths once the URL fix has run, so links point straight at the final address."""
    return (read_json(os.path.join(panel.DATA, "urlfix_plan.json"), {}) or {}).get("moves", {}) \
        if read_json(os.path.join(panel.DATA, "urlfix_result.json"), None) else {}


def link_targets(item):
    """Real pages on the site the article may link to: {path: title}."""
    crawl = read_json(CRAWL, {}) or {}
    mv = _moves()
    out = {"/price": "قیمت لحظه‌ای همه‌ی کالاها", "/about": "درباره‌ی کارخانه", "/contact": "تماس با فروش"}
    slug = (item.get("media") or "").split("/")[0]
    for p in crawl.get("pages", []):
        if p.get("status") != 200:
            continue
        path = urllib.parse.unquote(p["path"]).rstrip("/")
        path = mv.get(path, path)
        h1 = p["h1"][0] if isinstance(p.get("h1"), list) and p["h1"] else (p.get("title") or "")
        if path.startswith("/blog/") and path.count("/") == 3:
            out[path] = h1
        elif path.startswith("/category/") and path.count("/") == 2:
            out[path] = h1
        elif slug and path.startswith(f"/category/{slug}/"):
            out[path] = h1
    return out


def catalog_facts(item, product):
    """Product names (they carry the specs: چشمه، قطر مفتول، عرض) and headings of the target category page."""
    target = product.get("target_url") or ""
    path = urllib.parse.unquote(urllib.parse.urlsplit(target).path).rstrip("/")
    crawl = read_json(CRAWL, {}) or {}
    names, heads = [], []
    for p in crawl.get("pages", []):
        u = urllib.parse.unquote(p["path"]).rstrip("/")
        h1 = p["h1"][0] if isinstance(p.get("h1"), list) and p["h1"] else ""
        if path and u.startswith(path + "/") and h1:
            names.append(h1)
        if u == path:
            heads = (p.get("h2") or [])[:12]
    return {"category_page": path, "products_in_catalog": names[:30], "category_page_headings": heads}


# ------------------------------------------------------------------ the gate
def _text(body):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body or ""))).strip()


def gate(d, existing_slugs, targets):
    f = d.get("fields") or {}
    body = f.get("body") or ""
    text = _text(body)
    words = len(text.split())
    kw = (f.get("keyword") or "").strip()
    first_p = _text((re.search(r"<p[^>]*>(.*?)</p>", body, re.S) or [None, ""])[1])
    links = [urllib.parse.unquote(urllib.parse.urlsplit(h).path).rstrip("/") or "/"
             for h in re.findall(r'href=["\']([^"\']+)', body)
             if not urllib.parse.urlsplit(h).netloc or "sepahanfelez.ir" in urllib.parse.urlsplit(h).netloc]
    external = [h for h in re.findall(r'href=["\']([^"\']+)', body)
                if urllib.parse.urlsplit(h).netloc and "sepahanfelez.ir" not in urllib.parse.urlsplit(h).netloc]
    bad_links = [l for l in links if l not in targets]
    tags = {t.lower() for t in re.findall(r"</?([a-zA-Z0-9]+)", body)}
    digits = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    found_phones = {re.sub(r"\D", "", m) for m in re.findall(r"0\d{2,3}[\s\-]?\d{3,4}[\s\-]?\d{4}|09\d{9}", digits)}
    prices = re.findall(r"\d[\d,٬\.]*\s*(?:ریال|تومان)", digits)
    slug = f.get("slug") or ""
    checks = [
        ("طول متن", words >= 900, f"{_fa(words)} کلمه (حداقل ۹۰۰)"),
        ("کلمه‌ی کلیدی در عنوان", bool(kw) and kw in (f.get("title") or ""), kw),
        ("کلمه‌ی کلیدی در پاراگراف اول", bool(kw) and kw in first_p, ""),
        ("عنوان سئو", 20 <= len(f.get("meta_title") or "") <= 65, f"{_fa(len(f.get('meta_title') or ''))} نویسه (۲۰ تا ۶۵)"),
        ("توضیح متا", 110 <= len(f.get("meta_description") or "") <= 165, f"{_fa(len(f.get('meta_description') or ''))} نویسه (۱۱۰ تا ۱۶۵)"),
        ("خلاصه", 0 < len(f.get("description") or "") <= 500, ""),
        ("نامک", bool(re.fullmatch(r"[؀-ۿa-z0-9]+(-[؀-ۿa-z0-9]+)*", slug)) and len(slug) <= 30
         and slug not in existing_slugs, f"{slug} ({_fa(len(slug))} نویسه{'، تکراری' if slug in existing_slugs else ''})"),
        ("لینک داخلی", len(set(links)) >= 3 and not bad_links,
         f"{_fa(len(set(links)))} لینک" + (f"؛ نشانی ناموجود: {'، '.join(bad_links[:3])}" if bad_links else "")),
        ("لینک به صفحه‌ی محصول", d.get("category_page") in links, d.get("category_page") or ""),
        ("بدون لینک بیرونی", not external, "، ".join(external[:2])),
        ("بدون قیمت", not prices, "، ".join(prices[:2])),
        ("فقط شماره‌های شرکت", found_phones <= allowed_phones(), "، ".join(sorted(found_phones - allowed_phones()))),
        ("بدون «ارزش افزوده»", "ارزش افزوده" not in text, ""),
        ("امضای سپاهان فلز", signature.cfg()["factory_tip"] in body and signature.MARK in body,
         f"بخش «{signature.cfg()['factory_tip']}» و امضای تحریریه"),
        ("ساختار", "h2" in tags and tags <= ALLOWED_TAGS, "تگ‌های غیرمجاز: " + "، ".join(sorted(tags - ALLOWED_TAGS)) if tags - ALLOWED_TAGS else ""),
    ]
    return [{"name": n, "ok": bool(ok), "detail": det} for n, ok, det in checks]


# ------------------------------------------------------------------ writing
def _llm(prompt):
    led = read_json(COST, {}) or {}
    day = led.setdefault(today_str(), {"usd": 0.0, "runs": 0})
    if day["usd"] >= MAX_USD_DAY:
        raise RuntimeError("سقف هزینه‌ی امروز نوشتن مقاله پر شده")
    cmd = [CLAUDE, "-p", prompt, "--model", "sonnet", "--max-turns", "1", "--output-format", "json", "--strict-mcp-config",
           "--disallowedTools", "Bash", "Write", "Edit", "Read", "Glob", "Grep", "NotebookEdit", "WebFetch", "WebSearch", "Agent", "Task",
           "--max-budget-usd", str(MAX_USD_CALL)]
    os.makedirs(panel.DATA, exist_ok=True)
    r = subprocess.run(cmd, cwd=panel.DATA, capture_output=True, text=True, timeout=900)
    res = json.loads(r.stdout or "{}")
    cost = float(res.get("total_cost_usd") or 0)
    day["usd"] = round(day["usd"] + cost, 4)
    day["runs"] += 1
    write_json(COST, dict(sorted(led.items())[-90:]))
    m = re.search(r"\{.*\}", str(res.get("result") or ""), re.S)
    if not m:
        raise RuntimeError("خروجی مدل JSON نبود")
    return json.loads(m.group(0)), cost


def _prompt(item, product, facts, targets, existing, feedback=None):
    links = "\n".join(f"- {p} — {t}" for p, t in list(targets.items())[:60])
    same = [t for p, t in targets.items() if p.startswith("/blog/")]
    return f"""تو نویسنده‌ی ارشد محتوای فنی سایت فروشگاه کارخانه‌ی «سپاهان فلز» هستی. یک مقاله‌ی وبلاگ فارسی کامل، دقیق و کاربردی بنویس.

موضوع پیشنهادی: {item.get('title') or '—'}
کلمه‌ی کلیدی اصلی (عیناً در عنوان و پاراگراف اول بیاید): {item.get('keyword') or product.get('primary')}
کلمات مرتبط (طبیعی و بدون تکرار زورکی): {'، '.join(product.get('secondary', [])[:8])}
نوع محتوا: {item.get('type')}
محصول: {item.get('product')} — صفحه‌ی محصول در سایت: {facts['category_page']}

واقعیت‌های کارخانه (فقط همین‌ها؛ هیچ ادعا، آمار، گواهی یا استانداردی که این‌جا نیست نساز):
{facts()}

کالاهای همین دسته در کاتالوگ سایت (مشخصه‌ها در نامشان است؛ از همین‌ها مثال بزن):
{json.dumps(facts['products_in_catalog'], ensure_ascii=False)}

صفحه‌هایی که می‌توانی به آن‌ها لینک بدهی (فقط همین نشانی‌ها، نسبی، دقیقاً همین نوشتار):
{links}

مقاله‌هایی که از قبل هست (تکرارشان نکن، از زاویه‌ی تازه بنویس): {'، '.join(same[:40])}

قواعد:
- ۱۲۰۰ تا ۱۸۰۰ کلمه؛ مخاطب: خریدار عمده، پیمانکار، مرغدار، باغدار — زبان ساده و دقیق، جمله‌های کوتاه.
- ساختار HTML فقط با این تگ‌ها: h2, h3, p, ul, ol, li, strong, em, a, table, thead, tbody, tr, th, td. بدون h1 (عنوان جداست)، بدون style و class.
- پاراگراف اول دو سه جمله و کلمه‌ی کلیدی را دارد. حداقل ۴ زیرعنوان h2. اگر مقایسه یا مشخصه است، یک جدول.
- یک بخش «پرسش‌های پرتکرار» با ۳ تا ۵ پرسش (h3) و پاسخ کوتاه.
- امضای ما: پیش از پرسش‌های پرتکرار یک بخش با زیرعنوان دقیقاً «<h2>{signature.cfg()['factory_tip']}</h2>» و یک توصیه‌ی عملی از نگاه تولیدکننده (انبارداری، انتخاب سایز، نصب، کنترل کیفیت هنگام تحویل) — بدون آمار یا ادعای ساختگی. امضای پایانی تحریریه را ننویس؛ خودکار اضافه می‌شود.
- حداقل ۴ لینک داخلی: حتماً {facts['category_page']} و /price، و ۲ مقاله یا کالای مرتبط از فهرست بالا. متن لینک توصیفی باشد.
- هیچ قیمتی ننویس (نه عدد ریال/تومان)؛ برای قیمت به «قیمت لحظه‌ای» (/price) ارجاع بده. «ارزش افزوده» ننویس. «نوع کالا» بگو نه «کد کالا».
- هیچ لینک بیرونی، هیچ شماره‌ای جز شماره‌های بالا. نام رقبا را نبر.
- آخر مقاله یک جمله‌ی دعوت به تماس یا دیدن قیمت روز.
- ارقام داخل متن فارسی.

{('اصلاح لازم از بررسی قبلی: ' + feedback) if feedback else ''}

خروجی فقط یک JSON (بدون هیچ متن دیگر):
{{"title": "عنوان مقاله (حداکثر ۷۰ نویسه، کلمه‌ی کلیدی در آن)",
 "slug": "نامک فارسی کوتاه با خط‌تیره، حداکثر ۳۰ نویسه، بدون علامت سؤال؛ نباید یکی از این‌ها باشد: {', '.join(sorted(existing)[:60])}",
 "meta_title": "عنوان سئو ۴۰ تا ۶۰ نویسه",
 "meta_description": "توضیح متا ۱۲۰ تا ۱۶۰ نویسه با کلمه‌ی کلیدی و دعوت به کلیک",
 "description": "خلاصه‌ی ۲ تا ۳ جمله‌ای برای فهرست مجله (حداکثر ۴۰۰ نویسه)",
 "keyword": "کلمه‌ی کلیدی اصلی (حداکثر ۴۰ نویسه)",
 "meta_keywords": "۴ تا ۶ کلمه‌ی مرتبط با ویرگول",
 "body": "<h2>…</h2><p>…</p>…"}}"""


def _image(item):
    """Plan photo → JPEG ≤1200px, ≤1.9 MB (the host's upload limit is 2 MB)."""
    from PIL import Image
    rel = (item.get("media") or "").replace("drive/", "")
    src = os.path.join(PHOTO_ROOT, rel)
    if not rel or not os.path.exists(src):
        return None
    os.makedirs(IMAGES, exist_ok=True)
    out = os.path.join(IMAGES, f"{item['id']}.jpg")
    im = Image.open(src).convert("RGB")
    im.thumbnail((1200, 1200))
    for q in (85, 78, 70, 60):
        im.save(out, "JPEG", quality=q, optimize=True, progressive=True)
        if os.path.getsize(out) < 1_900_000:
            break
    return out


def next_item():
    have = {d["id"] for d in all_drafts()}
    today = today_str()
    for it in _plan_items():
        if it["date"] >= today and it["id"] not in have:
            return it
    return None


def write(item_id=None, say=print):
    item = next((i for i in _plan_items() if i["id"] == item_id), None) if item_id else next_item()
    if not item:
        raise RuntimeError("مقاله‌ی برنامه‌ریزی‌شده‌ای بدون پیش‌نویس نمانده" if not item_id else f"{item_id} در برنامه نیست")
    product = _product(item)
    facts = catalog_facts(item, product)
    targets = link_targets(item)
    existing = {p.rsplit("/", 1)[-1] for p in targets if p.startswith("/blog/")}
    existing |= {d["fields"].get("slug") for d in all_drafts() if d.get("fields") and d["id"] != item["id"]}
    d = load(item["id"]) or {"id": item["id"], "created": _now()}
    d.update({"date": item["date"], "jalali": item.get("jalali"), "time": item.get("time", "11:00"), "product": item.get("product"),
              "product_slug": (item.get("media") or "").split("/")[0], "type": item.get("type"), "plan_title": item.get("title"),
              "category_page": facts["category_page"], "blog_category": BLOG_CATEGORY.get((item.get("media") or "").split("/")[0], "توری")})
    trace.step(item["id"], "brief", "بریف مقاله", f"کلمه‌ی کلیدی «{item.get('keyword')}» · {_fa(len(facts['products_in_catalog']))} کالای کاتالوگ · {_fa(len(targets))} صفحه‌ی قابل لینک",
               decision="فقط واقعیت‌های کارخانه و کاتالوگ خود سایت به نویسنده داده شد؛ بدون قیمت.")
    feedback, cost = None, 0.0
    for attempt in (1, 2):
        say(f"نوشتن (تلاش {_fa(attempt)})…")
        out, c = _llm(_prompt(item, product, facts, targets, existing, feedback))
        cost += c
        d["fields"] = {k: str(out.get(k) or "").strip() for k in
                       ("title", "slug", "meta_title", "meta_description", "description", "keyword", "meta_keywords", "body")}
        d["fields"]["slug"] = re.sub(r"[\s_]+", "-", d["fields"]["slug"]).strip("-").replace("؟", "")
        d["fields"]["body"] = signature.article_byline(d["fields"]["body"])
        d["gate"] = gate(d, existing, targets)
        failed = [g for g in d["gate"] if not g["ok"]]
        trace.step(item["id"], "write", f"نوشته شد (تلاش {_fa(attempt)})", d["fields"]["title"],
                   data={"words": len(_text(d["fields"]["body"]).split()), "usd": round(c, 3)})
        trace.step(item["id"], "qa", "کنترل کیفیت", "همه قبول" if not failed else "رد: " + "، ".join(g["name"] for g in failed),
                   decision=None if not failed else "یک بار دیگر با همین ایرادها نوشته می‌شود." if attempt == 1 else "منتظر اصلاح دستی.")
        if not failed:
            break
        feedback = "؛ ".join(f"{g['name']}: {g['detail']}" for g in failed)
    d["image"] = _image(item)
    d["cost_usd"] = round(cost + d.get("cost_usd", 0), 3)
    d["status"] = "draft" if not [g for g in d["gate"] if not g["ok"]] else "needs_fix"
    trace.step(item["id"], "approve", "منتظر تأیید" if d["status"] == "draft" else "نیاز به اصلاح",
               "انتشار خودکار در زمان برنامه" if autopublish() and d["status"] == "draft" else "در داشبورد «تأیید و انتشار» را بزنید")
    say(f"پیش‌نویس: {d['fields']['title']} — {d['status']}")
    return save(d)


# ------------------------------------------------------------------ publishing
def publish(item_id, say=print, force=False):
    d = load(item_id)
    if not d:
        raise RuntimeError("پیش‌نویس پیدا نشد")
    if d.get("status") == "published":
        return d
    if not force and d.get("status") != "approved" and not (autopublish() and d.get("status") == "draft"):
        raise RuntimeError("این پیش‌نویس هنوز تأیید نشده")
    import history
    from sf import changes
    with panel.Panel() as p:
        cats = p.category_options()
        cid = cats.get(d["blog_category"]) or next((v for k, v in cats.items() if d["blog_category"] in k), None)
        if not cid:
            raise RuntimeError(f"دسته‌ی مجله «{d['blog_category']}» در پنل نبود")
        existing = {a["path"].rsplit("/", 1)[-1] for a in p.articles()}
        if d["fields"]["slug"] in existing:
            raise RuntimeError("این نامک الان در سایت هست — دوباره بنویسید یا نامک را عوض کنید")
        f = dict(d["fields"])
        f["body"] = signature.article_byline(f["body"])         # drafts written before the signature get it too
        f["category_id"] = cid
        say("ارسال به پنل سایت…")
        p.create_article(f, image=d.get("image"))
        art = next((a for a in p.articles() if a["path"].rsplit("/", 1)[-1] == f["slug"]), None)
        if not art:
            raise RuntimeError("پنل ذخیره کرد ولی مقاله در فهرست پیدا نشد")
        url = p.base + urllib.parse.quote(art["path"])
        r = p.page.request.get(url)
        live = r.status == 200
    d.update({"status": "published", "published_at": _now(), "url": url, "article_id": art["id"], "live_check": r.status})
    history.record("site", "article", content_type=d.get("type"), product=d.get("product"), text=f["title"],
                   media=d.get("image"), url=url, plan_ref=d["id"])
    trace.step(d["id"], "publish", "منتشر شد", url, decision="نشانی زنده بررسی شد: " + ("۲۰۰" if live else str(r.status)))
    changes.add("article", f"مقاله‌ی تازه: {f['title']}", "از برنامه‌ی محتوا؛ اثرش روی بازدید صفحه‌ی محصول سنجیده می‌شود",
                ref=d["category_page"], eval_days=28, new=url, source="site")
    say(f"✓ منتشر شد: {urllib.parse.unquote(url)}")
    save(d)
    try:                                                    # summary + link on LinkedIn and the Telegram channel
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "social"))
        import publisher
        publisher.share_article(d)
    except Exception as exc:                                # noqa: BLE001
        say(f"اشتراک در شبکه‌ها آماده نشد: {exc}")
    return d


def due(say=print):
    """Publish approved (or auto) drafts whose planned time has come. Runs hourly in working hours."""
    now = now_tehran().strftime("%Y-%m-%dT%H:%M")
    out = []
    for d in all_drafts():
        ok = d.get("status") == "approved" or (autopublish() and d.get("status") == "draft")
        if ok and f"{d['date']}T{d.get('time', '11:00')}" <= now:
            try:
                out.append(publish(d["id"], say=say))
            except Exception as exc:                                   # noqa: BLE001
                d["last_error"] = str(exc)[:300]
                save(d)
                say(f"✗ {d['id']}: {exc}")
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "write"
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "write":
        write(arg)
    elif cmd == "publish":
        publish(arg, force="--force" in sys.argv)
    elif cmd == "due":
        due()
