"""
The content calendar, carried out on the networks.

    python3 publisher.py prepare   # make tomorrow's (and today's missing) items: copy + image
    python3 publisher.py due       # publish what is approved and due (every 10 min, 09–18 Tehran)
    python3 publisher.py tick      # both — what the timer runs

Per plan item (dashboard/data/latest/content_plan.json):
  story    → one 1080×1920 card (product photo from Drive + short copy), to every network in the
             item's list plus Telegram: Instagram (real story), Telegram (real story), Bale / Eitaa /
             Rubika / WhatsApp (their web apps have no story button: the card is delivered to
             Saved Messages for a one-tap repost, recorded as «sent-to-operator»).
  telegram → a channel post on Telegram, Bale, Eitaa, Rubika: «قیمت روز» from the site's own price
             table after 12:30, «خبری» from the site's own news (new articles) until the owner gives
             news sources, otherwise a teaching/FAQ post with a 1080×1350 card.
  article  → after the article is live: a short summary + link on LinkedIn and the Telegram channel.

Copy is written by one `claude -p` call per item from facts we hold (catalog names, factory facts),
never prices except those read from the site's price page. Each item waits for approval in the
dashboard unless SOCIAL_AUTOPUBLISH=1. A network without a logged-in default account is skipped
and noted — nothing is retried blindly. Every send goes through actions.act → safety (caps, gaps,
24h pause) → publishing history («تاریخچه‌ی انتشار») and the item's trace.
"""

import html
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "site"))
sys.path.insert(0, os.path.join(ROOT, "dashboard"))

import signature  # noqa: E402
from sf import trace  # noqa: E402
from sf.env import load_env  # noqa: E402
from sf.util import DATA, fetch, now_tehran, read_json, today_str, write_json  # noqa: E402

QUEUE = os.path.join(DATA, "social", "queue")
CARDS = os.path.join(DATA, "social", "cards")
PLAN = os.path.join(DATA, "latest", "content_plan.json")
PHOTOS_DRIVE = os.path.join(DATA, "photos")
PHOTOS_PROTO = "/home/ubuntu/projects/sepahanfelez-prototype/assets/products"
NET_FA = {"اینستاگرام": "instagram", "روبیکا": "rubika", "ایتا": "eitaa", "بله": "bale", "واتساپ": "whatsapp",
          "تلگرام": "telegram", "لینکدین": "linkedin"}
FA_NET = {v: k for k, v in NET_FA.items()}
WINDOW_H = 3            # an approved item more than 3 hours late is not sent (stale story / price)

# No two stories alike: each one takes an angle not used for the same product in the last two weeks,
# a layout different from the previous story, a photo not used in two weeks, and copy that the
# similarity check finds different from everything sent in the last three weeks.
ANGLES = [
    ("mistake", "یک اشتباه رایج در انتخاب یا نصب و راه درستش"),
    ("question", "یک سؤال کوتاه از مخاطب که جوابش در خود استوری است"),
    ("number", "یک عدد یا مشخصه‌ی واقعی از کاتالوگ (چشمه، قطر مفتول، عرض، وزن رول) و معنی‌اش برای خریدار"),
    ("compare", "مقایسه‌ی دو نوع یا دو سایز از همین محصول و این‌که هرکدام برای چه کاری است"),
    ("usecase", "یک کاربرد مشخص (مرغداری، باغ، بالکن، حصار کارخانه، ساختمان) و نکته‌ی اجرایی‌اش"),
    ("checklist", "چک‌لیست سه‌قدمی پیش از خرید"),
    ("myth", "یک باور غلط رایج و واقعیت فنی‌اش"),
    ("care", "نگهداری و عمر بیشتر محصول در هوای باز"),
    ("factory", "از دل کارخانه: تولید مستقیم، سالن ۳۰٬۰۰۰ متری، کنترل کیفیت (فقط واقعیت‌های داده‌شده)"),
]
LAYOUTS = ["classic"]      # the owner chose this one template for everything (11-10); variety comes from copy and photo
JITTER_MIN = (-12, 22)  # minutes around the planned slot, different every day, never before 09:00


def _tokens(t):
    t = re.sub(r"[^\w\u0600-\u06FF ]", " ", (t or "").replace("\u200c", " "))
    return {w for w in t.split() if len(w) > 2}


def _similar(a, b):
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / max(1, min(len(ta), len(tb)))


def recent(days=21):
    since = (datetime.fromisoformat(today_str()) - timedelta(days=days)).date().isoformat()
    return [q for q in all_items() if q.get("date", "") >= since and q.get("status") not in ("rejected",)]


def _copy_of(q):
    c = q.get("card") or {}
    return " ".join([c.get("title", ""), " ".join(c.get("points", [])), q.get("text", "")])


def pick_angle(item, rec, skip=()):
    """An angle not used today on any story, nor for this product in the last two weeks."""
    import hashlib
    today = {q.get("angle") for q in rec if q.get("date") == item.get("date") and q.get("angle")}
    prod = {q.get("angle") for q in rec if q.get("product") == item.get("product") and q.get("angle")}
    free = [a for a in ANGLES if a[0] not in today and a[0] not in skip]
    pref = [a for a in free if a[0] not in prod] or free or ANGLES
    if item.get("type") in ("معرفی کارخانه", "پشت‌صحنه") and any(a[0] == "factory" for a in pref):
        return next(a for a in ANGLES if a[0] == "factory")
    pref = [a for a in pref if a[0] != "factory"] or pref
    return pref[int(hashlib.md5(item["id"].encode()).hexdigest(), 16) % len(pref)]


def pick_layout(item, rec):
    """A layout different from the last two cards of the same kind."""
    import hashlib
    last = [(q.get("card") or {}).get("layout") for q in sorted(rec, key=lambda q: (q.get("date", ""), q.get("at") or q.get("time", "")))
            if q.get("kind") == item["kind"]][-2:]
    start = int(hashlib.md5(item["id"].encode()).hexdigest(), 16) % len(LAYOUTS)
    for l in LAYOUTS[start:] + LAYOUTS[:start]:
        if l not in last:
            return l
    return LAYOUTS[start]


def jitter(item, base_time):
    """The planned slot ± a few minutes, stable for the item, different from day to day."""
    import hashlib
    lo, hi = JITTER_MIN
    off = lo + int(hashlib.md5((item["id"] + "t").encode()).hexdigest(), 16) % (hi - lo + 1)
    h, m = map(int, base_time.split(":"))
    t = datetime(2000, 1, 1, h, m) + timedelta(minutes=off)
    if t.hour < 9:
        t = t.replace(hour=9, minute=abs(off) % 15)
    return t.strftime("%H:%M")


def _now():
    return now_tehran().isoformat(timespec="seconds")


def _fa(s):
    return str(s).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _nets(name, default):
    load_env()
    return [n.strip() for n in os.environ.get(name, default).split(",") if n.strip() in FA_NET]


def story_nets():
    """Where every story goes (SOCIAL_STORY_NETS): a real story on each."""
    return _nets("SOCIAL_STORY_NETS", "instagram,telegram,whatsapp,bale,eitaa,rubika")


def channel_nets():
    """Where channel posts go (SOCIAL_CHANNEL_NETS): only networks where the company has a channel."""
    return _nets("SOCIAL_CHANNEL_NETS", "telegram")


def autopublish():
    load_env()
    return os.environ.get("SOCIAL_AUTOPUBLISH", "0").strip() == "1"


def path(item_id):
    return os.path.join(QUEUE, f"{item_id}.json")


def load(item_id):
    return read_json(path(item_id), None)


def save(q):
    os.makedirs(QUEUE, exist_ok=True)
    q["updated"] = _now()
    write_json(path(q["id"]), q)
    return q


def all_items():
    if not os.path.isdir(QUEUE):
        return []
    out = [read_json(os.path.join(QUEUE, f), {}) for f in os.listdir(QUEUE) if f.endswith(".json")]
    return sorted([q for q in out if q], key=lambda q: (q.get("date", ""), q.get("time", "")))


# ------------------------------------------------------------------ inputs we trust
def photo_for(item, used):
    """A photo that exists *now* for the item's category: Drive photos first (a photo deleted on
    Drive is gone from the library, so it is never picked), the prototype's as a fallback; factory
    photos lead for factory/behind-the-scenes items; unused in the last week if possible."""
    import hashlib
    from sf.drive_sync import ALIASES, library
    slug = (item.get("media") or "").split("/")[0]
    if slug == "drive":
        slug = (item.get("media") or "").split("/")[1]
    lib = library()
    real = ALIASES.get(slug, slug)
    cands = [os.path.join(PHOTOS_DRIVE, real, f) for f in lib.get(real, []) if os.path.isdir(os.path.join(PHOTOS_DRIVE, real))]
    if item.get("type") in ("معرفی کارخانه", "پشت‌صحنه") and lib.get("_factory"):
        cands = [os.path.join(PHOTOS_DRIVE, "_factory", f) for f in lib["_factory"]] + cands
    if not cands and slug and os.path.isdir(os.path.join(PHOTOS_PROTO, slug)):
        cands = [os.path.join(PHOTOS_PROTO, slug, f) for f in sorted(os.listdir(os.path.join(PHOTOS_PROTO, slug))) if f.startswith("photo-")]
    if not cands:                                      # the plan's media is a video or missing: the product's own photos
        from sf.drive_sync import match
        by_name = match(item.get("product") or "")
        if by_name and lib.get(by_name):
            cands = [os.path.join(PHOTOS_DRIVE, by_name, f) for f in lib[by_name]]
    pool = [c for c in cands if os.path.isfile(c) and c not in used] or [c for c in cands if os.path.isfile(c)]
    if not pool:
        return None
    return pool[int(hashlib.md5(item["id"].encode()).hexdigest(), 16) % len(pool)]


def _photo_folder_for(item):
    """The photo folder that belongs to an item's product (plan media folder, or matched from the product name)."""
    from sf.drive_sync import ALIASES, match
    media = item.get("media") or ""
    slug = media.split("/")[1] if media.startswith("drive/") else media.split("/")[0]
    if not slug or slug in ("videos", "toloue-sepahan1", "toloue-sepahan2", "banner-karkhane") or slug.endswith((".mp4", ".mov")):
        slug = match(item.get("product") or "") or ""
    return ALIASES.get(slug, slug)


def _photo_fits(photo, item):
    from sf.drive_sync import ALIASES
    want = _photo_folder_for(item)
    have = os.path.basename(os.path.dirname(photo or ""))
    return not want or ALIASES.get(have, have) == want or have == "_factory"


def catalog(item):
    import articles
    from sf import product_pages
    prod = articles._product({"product_rank": item.get("product_rank")})
    facts = articles.catalog_facts(item, prod) if prod else {"products_in_catalog": [], "category_page": "/price"}
    page = product_pages.facts(facts.get("category_page")) if prod else {}
    facts["page"] = page
    if page.get("products"):
        facts["products_in_catalog"] = page["products"]
    return prod, facts


def _page_brief(facts):
    """The product's own page on the site, as the writer sees it."""
    p = facts.get("page") or {}
    if not p:
        return ""
    return (f"صفحه‌ی همین کالا در سایت (مرجع اصلی عنوان و متن؛ از همین واژه‌ها و مشخصات استفاده کن):\n"
            f"عنوان صفحه: {p.get('h1') or p.get('title')}\nتوضیح صفحه: {p.get('description')}\n"
            f"بخش‌های صفحه: {'، '.join(p.get('sections', [])[:8])}\n")


VOICE = ("لحن: رسمی و شرکتی (شرکت تولیدی)، بدون محاوره و شوخی؛ تیتر رسمی و دقیق. «سپاهان فلز» کارخانه است: "
         "واژه‌ی «کارگاه» را اصلاً به کار نبر. از «ما/کارخانه/تولید مستقیم» استفاده کن.")


def prices():
    """[(name, price text, unit)] from the site's price page, as shown to visitors."""
    r, _, _ = fetch("https://sepahanfelez.ir/price")
    if r is None or r.status_code != 200:
        return []
    out, seen = [], set()
    for row in re.findall(r"<tr.*?</tr>", r.text, re.S):
        name = re.search(r'<a [^>]*href="/category/[^"]+"[^>]*>(.*?)</a>', row, re.S)
        price = re.search(r'<b class="num">([^<]+)</b>\s*(?:<span class="riyal">([^<]+)</span>)?', row)
        if not (name and price):
            continue
        n = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", name.group(1)))).strip()
        unit = re.sub(r"\s+", " ", (price.group(2) or "ریال")).strip()
        tail = re.search(r'class="riyal">[^<]*</span>\s*(/\s*[^<]{1,20})', row)
        if tail:
            unit = f"{unit} {tail.group(1).strip()}"
        if n and n not in seen:
            seen.add(n)
            out.append((n, price.group(1).strip(), unit))
    return out


def recent_articles(days=2):
    """Site news and articles of the last days that the channels have not carried yet."""
    import history
    since = (now_tehran() - timedelta(days=days)).isoformat()
    shared = {q.get("link") for q in all_items() if q.get("kind") in ("share", "news-share")}
    return [r for r in history.load().get("site", []) if r.get("kind") in ("article", "news") and r.get("ts", "") >= since
            and r.get("url") and r.get("url") not in shared]


# ------------------------------------------------------------------ copy
def _llm(prompt):
    import articles
    out, cost = articles._llm(prompt)
    return out, cost


def _story_copy(item, prod, facts, angle, avoid, feedback=""):
    import articles
    return _llm(f"""متن یک استوری اینستاگرام/تلگرام برای «سپاهان فلز» (تولیدکننده‌ی توری و مفتول، اصفهان) بنویس.
نوع محتوا: {item.get('type')} · محصول: {item.get('product')} · مناسبت: {item.get('occasion') or '—'}
زاویه‌ی این استوری (حتماً همین): {angle[1]}
این‌ها در سه هفته‌ی اخیر رفته‌اند؛ تیتر و نکته‌ها باید کاملاً متفاوت باشند، نه بازنویسی همین‌ها:
{json.dumps(avoid[:25], ensure_ascii=False)}
{('ایراد نسخه‌ی قبلی: ' + feedback) if feedback else ''}
کلمات مرتبط: {'، '.join((prod or {}).get('secondary', [])[:6])}
کالاهای واقعی کاتالوگ (مشخصات در نامشان): {json.dumps(facts.get('products_in_catalog', [])[:15], ensure_ascii=False)}
{_page_brief(facts)}واقعیت‌های کارخانه: {articles.facts()}
{VOICE}
قواعد: هیچ قیمت و عددی که این‌جا نیست ننویس؛ ادعای ساختگی (گواهی، رتبه، «بهترین») نه؛ فارسی روشن؛ ارقام فارسی؛ در cta هیچ عدد یا شماره‌ای ننویس.
خروجی فقط JSON: {{"title": "تیتر حداکثر ۴۰ نویسه", "points": ["۲ یا ۳ نکته‌ی کوتاه، هر کدام حداکثر ۴۵ نویسه"],
"cta": "دعوت کوتاه حداکثر ۲۲ نویسه", "caption": "کپشن کوتاه ۱ تا ۲ جمله برای پیام همراه"}}""")


def _channel_copy(item, prod, facts, extra=""):
    import articles
    return _llm(f"""یک پست کانال تلگرام/بله/ایتا/روبیکا برای «سپاهان فلز» (تولیدکننده‌ی توری و مفتول، اصفهان) بنویس.
نوع: {item.get('type')} · موضوع: {item.get('product')}
{extra}
کالاهای واقعی کاتالوگ: {json.dumps(facts.get('products_in_catalog', [])[:15], ensure_ascii=False)}
{_page_brief(facts)}واقعیت‌های کارخانه: {articles.facts()}
{VOICE}
قواعد: ۴۰۰ تا ۸۰۰ نویسه؛ خط اول قلاب؛ ۳ تا ۵ خط کوتاه یا بولت؛ آخر یک خط «قیمت روز: sepahanfelez.ir/price» و شماره‌ی تماس؛
بدون قیمت عددی (مگر در داده‌ی بالا)؛ بدون ادعای ساختگی؛ ۲ تا ۴ هشتگ فارسی مرتبط در آخر؛ ارقام فارسی.
خروجی فقط JSON: {{"text": "متن کامل پست", "title": "تیتر کارت حداکثر ۴۰ نویسه", "points": ["۲ تا ۳ نکته‌ی کوتاه برای کارت"], "cta": "حداکثر ۲۲ نویسه"}}""")


def _gate(text, extra_allowed=()):
    import articles
    digits = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    phones = {re.sub(r"\D", "", m) for m in re.findall(r"0\d{2,3}[\s\-]?\d{3,4}[\s\-]?\d{4}|09\d{9}", digits)}
    price = re.findall(r"\d[\d,٬\.]*\s*(?:ریال|تومان)", digits)
    informal = [w for w in ("میشه", "نمیشه", "اینو", "اونو", "چیه", "داری؟", "هستش", "بزنید رو", "رو ببینید") if w in text]
    checks = [("فقط شماره‌های شرکت", phones <= articles.allowed_phones(), "، ".join(phones - articles.allowed_phones())),
              ("بدون «کارگاه» (ما کارخانه‌ایم)", "کارگاه" not in text, ""),
              ("لحن رسمی", not informal and "!!" not in text, "، ".join(informal)),
              ("بدون قیمت ساختگی", not price or bool(extra_allowed), "، ".join(price[:2])),
              ("بدون «ارزش افزوده»", "ارزش افزوده" not in text, "")]
    return [{"name": n, "ok": bool(ok), "detail": d} for n, ok, d in checks]


# ------------------------------------------------------------------ prepare
def _render(card, fmt):
    import render_card
    card = dict(card, format=fmt)
    out = render_card.render([card], CARDS)
    return out[0] if out else None


def prepare_item(item, used, say=print):
    q = load(item["id"]) or {"id": item["id"], "created": _now()}
    if q.get("status") in ("approved", "done", "partial", "rejected"):
        return q
    q.update({k: item.get(k) for k in ("date", "jalali", "time", "type", "product", "kind")})
    prod, facts = catalog(item)
    q["plan_item"] = {k: v for k, v in item.items() if k != "_photo"}
    q["source_fp"] = (facts.get("page") or {}).get("fp")
    cost = 0.0
    rec = [r for r in recent() if r["id"] != item["id"]]
    if item["kind"] == "story":
        q["nets"] = story_nets()
        q["action"] = "story"
        photo = item.get("_photo") or photo_for(item, used)
        angle = pick_angle(item, rec)
        avoid = [(r.get("card") or {}).get("title", "") for r in rec if (r.get("card") or {}).get("title")]
        feedback, tried = "", []
        for attempt in (1, 2, 3):
            if attempt > 1:                           # too close to something recent: a different angle, not a reworded copy
                tried.append(angle[0])
                angle = pick_angle(item, rec, skip=tried)
            out, c = _story_copy(item, prod, facts, angle, avoid, feedback)
            cost += c
            copy = " ".join([str(out.get("title", "")), " ".join(map(str, out.get("points", []))), str(out.get("caption", ""))])
            near = max(rec, key=lambda r: _similar(copy, _copy_of(r)), default=None)
            score = _similar(copy, _copy_of(near)) if near else 0
            if score < 0.55:
                break
            feedback = f"خیلی شبیه «{(near.get('card') or {}).get('title', '')}» ({near['date']}) بود؛ زاویه و کلمات دیگری انتخاب کن"
        q["angle"], q["similarity"] = angle[0], round(score, 2)
        q["text"] = str(out.get("caption", "")).strip()
        card = {"id": item["id"], "type": item.get("type"), "title": out.get("title", ""), "points": out.get("points", [])[:3],
                "photo": photo, "cta": out.get("cta") or "استعلام قیمت روز", "layout": pick_layout(item, rec)}
        q["card"] = {k: card[k] for k in ("title", "points", "cta", "layout")}
        q["media"] = _render(card, "story") if photo else None
        q["photo"] = photo
        q["gate"] = _gate(" ".join([card["title"], " ".join(card["points"]), q["text"]]))
        q["gate"].append({"name": "عکس همان محصول", "ok": bool(photo) and _photo_fits(photo, item),
                          "detail": f"عکس از «{os.path.basename(os.path.dirname(photo or ''))}» برای «{item.get('product')}»"})
        q["gate"].append({"name": "تکراری نبودن", "ok": score < 0.55,
                          "detail": f"شباهت با نزدیک‌ترین مورد اخیر {round(score * 100)}٪" if near else ""})
        if not photo:
            q["gate"].append({"name": "عکس", "ok": False, "detail": "برای این دسته عکسی نیست"})
    elif item["kind"] == "telegram":
        q["nets"] = channel_nets()
        q["action"] = "post"
        if item.get("type") == "قیمت روز":
            rows = prices()
            if not rows:
                q.update(status="needs_fix", gate=[{"name": "جدول قیمت", "ok": False, "detail": "صفحه‌ی قیمت خوانده نشد"}])
                return save(q)
            lines = [f"▫️ {n}: {p} {u}" for n, p, u in rows[:12]]
            q["text"] = ("📊 قیمت امروز سپاهان فلز — " + _fa(item.get("jalali", "")) + "\n\n" + "\n".join(lines) +
                         "\n\nقیمت همه‌ی کالاها: sepahanfelez.ir/price\n#قیمت_روز #توری #مفتول")
            q["media"] = None
            q["after"] = "12:35"                                    # the site updates at 12:30
            q["gate"] = _gate(q["text"], extra_allowed=("prices",))
            q["source"] = "صفحه‌ی قیمت سایت"
        else:
            avoid = [(r.get("card") or {}).get("title", "") or (r.get("text") or "")[:80] for r in rec if r.get("kind") == "telegram"]
            extra = "این‌ها اخیراً در کانال رفته‌اند؛ موضوع و جمله‌ها نباید تکرار شوند: " + json.dumps(avoid[:20], ensure_ascii=False)
            if item.get("type") == "خبری":
                arts = recent_articles()
                if arts:
                    a = arts[-1]
                    what = "خبر بازار آهن در سایت" if a.get("kind") == "news" else "مقاله‌ی تازه در مجله‌ی سایت"
                    extra += f"\nخبر: {what} منتشر شد: «{a.get('text')}» — لینک: {a.get('url')} (همین لینک را در متن بگذار)"
                    q["source"], q["link"] = what, a.get("url")
                else:
                    item = dict(item, type="پرسش و پاسخ", product=item.get("product") if item.get("product_rank") else "توری و مفتول")
                    q["source"] = "منبع خبری تعریف نشده → پست پرسش و پاسخ"
            out, c = _channel_copy(item, prod, facts, extra)
            cost += c
            q["text"] = str(out.get("text", "")).strip()
            photo = item.get("_photo") or photo_for(dict(item, media=item.get("media") or (f"{(prod or {}).get('target_url', '').rsplit('/', 1)[-1]}/x" if prod else "")), used)
            card = {"id": item["id"], "type": item.get("type"), "title": out.get("title", ""), "points": out.get("points", [])[:3],
                    "photo": photo, "cta": out.get("cta") or "قیمت روز در سایت", "layout": pick_layout(item, rec)}
            q["card"] = {k: card[k] for k in ("title", "points", "cta", "layout")}
            q["media"] = _render(card, "post") if photo else None
            q["photo"] = photo
            q["gate"] = _gate(q["text"])
    q["text"] = signature.caption(q.get("text"))                # the house sign-off, visible in the queue preview
    q["at"] = jitter(item, q.get("after") or item.get("time", "09:00"))
    if q.get("photo"):
        used.add(q["photo"])
    q["cost_usd"] = round(q.get("cost_usd", 0) + cost, 3)
    q["status"] = "draft" if all(g["ok"] for g in q.get("gate", [])) else "needs_fix"
    q.setdefault("results", {})
    trace.step(item["id"], "write", "متن و تصویر آماده شد", (q.get("text") or "")[:120],
               decision=("در انتظار تأیید شما در داشبورد" if not autopublish() else "انتشار خودکار در زمان برنامه"),
               data={"nets": q["nets"], "usd": q["cost_usd"]})
    if q["status"] == "needs_fix":
        try:
            import alert
            bad = "، ".join(f"{g['name']} ({g['detail']})" if g.get("detail") else g["name"] for g in q["gate"] if not g["ok"])
            alert.send(f"fix:{item['id']}", "یک محتوای شبکه‌ها از کنترل کیفیت رد شد و منتشر نمی‌شود",
                       f"{item.get('type')} · {item.get('product') or ''} · {item.get('jalali') or item.get('date')}: {bad}",
                       "داشبورد → تولید محتوا → صف انتشار → همین مورد → «ویرایش» یا «دوباره بساز»", every_h=24 * 30)
        except Exception:                                              # noqa: BLE001
            pass
    say(f"آماده شد: {item['id']} ({q['status']})")
    return save(q)


def prepare(days=1, say=print):
    plan = read_json(PLAN, {}) or {}
    today = today_str()
    last = (datetime.fromisoformat(today) + timedelta(days=days)).date().isoformat()
    used = {q.get("photo") for q in all_items() if q.get("date", "") >= (datetime.fromisoformat(today) - timedelta(days=14)).date().isoformat()}
    made = []
    for it in plan.get("items", []):
        if it["kind"] in ("story", "telegram") and today <= it["date"] <= last and not load(it["id"]):
            try:
                made.append(prepare_item(it, used, say=say))
            except Exception as exc:                                    # noqa: BLE001
                say(f"✗ {it['id']}: {type(exc).__name__}: {str(exc)[:160]}")
    return made


def share_article(draft):
    """After an article is live: a summary + link for LinkedIn and the Telegram channel, 30 minutes later."""
    when = now_tehran() + timedelta(minutes=30)
    url = urllib.parse.unquote(draft["url"])
    q = {"id": f"{draft['id']}-share", "created": _now(), "date": when.date().isoformat(), "time": when.strftime("%H:%M"),
         "kind": "share", "type": "مقاله‌ی تازه", "product": draft.get("product"), "action": "post", "nets": ["linkedin"] + channel_nets(),
         "text": signature.caption(f"📝 {draft['fields']['title']}\n\n{draft['fields'].get('description', '')}\n\nادامه در سایت: {url}"),
         "link": draft["url"], "media": draft.get("image"), "status": "approved", "results": {}, "gate": []}
    trace.step(q["id"], "plan", "اشتراک مقاله", url, decision="مقاله‌ی تأییدشده؛ خلاصه‌اش هم تأییدشده حساب می‌شود")
    return save(q)


def share_news(d):
    """A news piece is live: its own short channel post (Telegram, Bale, Eitaa, Rubika) + LinkedIn, 20 minutes later.
    Written from the news itself (lead + «در یک نگاه»), so it is never the same text as the site page."""
    when = now_tehran() + timedelta(minutes=20)
    url = urllib.parse.unquote(d["url"])
    body = d["fields"]["body"]
    lead = re.sub(r"<[^>]+>", "", (re.search(r"<p>(.*?)</p>", body, re.S) or [None, ""])[1]).strip()
    glance = re.search(r"در یک نگاه</h2>\s*<ul>(.*?)</ul>", body, re.S)
    bullets = [re.sub(r"<[^>]+>", "", li).strip() for li in re.findall(r"<li>(.*?)</li>", glance.group(1), re.S)] if glance else []
    text = (f"📰 {d['fields']['title']}\n\n{lead}\n\n" + "\n".join(f"▫️ {b}" for b in bullets[:3]) +
            f"\n\nتحلیل کامل و برداشت ما برای خریداران: {url}\nمنبع خبر: {d['source']['source_name']}")
    q = {"id": f"{d['id']}-share", "created": _now(), "date": when.date().isoformat(), "time": when.strftime("%H:%M"),
         "kind": "news-share", "type": "خبر بازار", "product": None, "action": "post",
         "nets": channel_nets() + ["linkedin"], "text": signature.caption(text),
         "link": d["url"], "media": d.get("image"), "status": "approved", "results": {}, "gate": []}
    trace.step(q["id"], "plan", "اشتراک خبر", url, decision="خبر از کنترل کیفیت گذشته؛ خلاصه‌اش خودکار در کانال‌ها می‌رود")
    return save(q)


# ------------------------------------------------------------------ publish
def _logged(net):
    import accounts
    acct = accounts.default(net)
    st = (read_json(os.path.join(DATA, "social_status.json"), {}) or {}).get(acct["id"] if acct else "", {})
    return acct, bool(acct and st.get("logged_in"))


def _was_connected(acct):
    rows = (read_json(os.path.join(DATA, "connections.json"), {}) or {}).get("rows", [])
    row = next((r for r in rows if r.get("key") == f"acct:{acct['id']}"), {})
    return bool(row.get("last_ok"))


def _alert(net, q, detail, fix):
    """One message per network per 6 hours to the person who fixes it (automation/alert.py)."""
    try:
        import alert
        what = {"story": "استوری", "post": "پست"}.get(q.get("action"), q.get("action"))
        alert.send(f"pub:{net}", f"انتشار در {FA_NET.get(net, net)} انجام نشد",
                   f"{what} «{q.get('type') or ''}» برای {q.get('jalali') or q.get('date')} {q.get('at') or q.get('time') or ''}: {detail}", fix)
    except Exception:                                                  # noqa: BLE001
        pass


# per network: published (live) · sent-to-operator (in Saved Messages, one tap left) · waiting (account not
# signed in: rescheduled once it is) · failed (a person looks) · expired (its moment passed, not sent)
SETTLED = ("published", "sent-to-operator", "failed", "expired")
TIME_BOUND = ("قیمت روز", "خبری")    # worthless late: never rescheduled (a news share keeps 2 days)
CATCHUP_DAYS = 7          # missed evergreen items up to a week old are rescheduled once their account is back
CATCHUP_PER_DAY = 2       # … and at most this many a day (story caps are 4–6 a day, the plan uses 3), between 09:00 and 19:00, not on Friday


def _at(q):
    return datetime.fromisoformat(f"{q['date']}T{q.get('at') or q.get('after') or q.get('time', '09:00')}").replace(
        tzinfo=now_tehran().tzinfo)


def _res(q, net):
    return ((q.get("results") or {}).get(net) or {}).get("status")


def _pending(q):
    return [n for n in q.get("nets", []) if _res(q, n) not in SETTLED]


def _retarget(q):
    """Networks not yet reached follow today's setup (SOCIAL_STORY_NETS / SOCIAL_CHANNEL_NETS); reached ones stay."""
    want = story_nets() if q.get("action") == "story" else channel_nets() + (["linkedin"] if "linkedin" in q.get("nets", []) else [])
    done = [n for n in q.get("nets", []) if _res(q, n) in SETTLED]
    new = done + [n for n in want if n not in done]
    if new != q.get("nets"):
        q["nets"] = new
        for n in list((q.get("results") or {})):
            if n not in new:
                q["results"].pop(n)
        return True
    return False


def _settle(q):
    """Item status from its networks — «done» only when every network really has it live."""
    st = [_res(q, n) for n in q.get("nets", [])]
    if st and all(s == "published" for s in st):
        q["status"] = "done"
    elif any(s in ("published", "sent-to-operator") for s in st):
        q["status"] = "operator" if not _pending(q) and "sent-to-operator" in st and "failed" not in st and "expired" not in st else "partial"
    elif any(s in ("waiting", "skipped") for s in st):
        q["status"] = "waiting"
    elif st and all(s in ("expired", "failed") for s in st):
        q["status"] = "expired" if "failed" not in st else "partial"
    return q["status"]


def publish(q, say=print, force=False, nets=None):
    import random
    import time
    import actions
    sent = 0
    q.setdefault("results", {})
    for i, net in enumerate(nets or q.get("nets", [])):
        if i and sent:
            time.sleep(random.randint(25, 110))        # not the same second on every network
        prev = _res(q, net)
        if prev in ("published", "sent-to-operator", "expired") or (prev == "failed" and not force):
            continue                                   # a failure is looked at by a person, not retried every 10 minutes
        acct, ok = _logged(net)
        if not ok:
            q["results"][net] = {"status": "waiting", "at": _now(),
                                 "detail": "حساب وصل نیست — بعد از ورود دوباره زمان‌بندی و منتشر می‌شود"}
            if acct and _was_connected(acct):         # an account that was connected and dropped out (never connected: no alarm)
                _alert(net, q, "حساب از برنامه بیرون افتاده؛ این محتوا و بعدی‌ها منتظر می‌مانند و بعد از ورود دوباره زمان‌بندی می‌شوند",
                       "داشبورد → اتصالات و تنظیمات → همین حساب → «ورود»")
            continue
        try:
            res = actions.act(net, q["action"], text=signature.caption(q.get("text", "")), media=q.get("media"), link=q.get("link"),
                              item_id=q["id"], content_type=q.get("type"), product=q.get("product"), account=acct["id"])
            q["results"][net] = {"status": res.get("status"), "detail": res.get("detail", ""), "url": res.get("url"), "at": _now()}
            sent += 1
        except Exception as exc:                                       # noqa: BLE001
            if type(exc).__name__ == "Blocked":        # daily cap full or a 24h platform pause: not a failure, another day
                q["results"][net] = {"status": "waiting", "detail": f"{exc} — دوباره زمان‌بندی می‌شود", "at": _now()}
                q["retry_at"] = None
            elif type(exc).__name__ == "NotLoggedIn":  # the session ended between the check and the send
                q["results"][net] = {"status": "waiting", "at": _now(),
                                     "detail": "حساب وسط کار بیرون افتاد — بعد از ورود دوباره زمان‌بندی و منتشر می‌شود"}
                try:
                    import login as Lg
                    Lg.use(acct)
                    Lg.save_status(net, False, "logged out")
                    Lg.use(None)
                except Exception:                      # noqa: BLE001
                    pass
                _alert(net, q, "حساب از برنامه بیرون افتاده؛ انتشار در این شبکه متوقف است تا دوباره وارد شوید",
                       "داشبورد → اتصالات و تنظیمات → همین حساب → «ورود»")
            else:
                q["results"][net] = {"status": "failed", "detail": f"{type(exc).__name__}: {str(exc)[:200]}", "at": _now()}
        if q["results"][net]["status"] == "failed":
            _alert(net, q, "ارسال خطا داد: " + q["results"][net]["detail"],
                   "داشبورد → تولید محتوا → صف انتشار → همین مورد → «ارسال دوباره»؛ اگر تکرار شد «تست کامل» حساب")
        elif q["results"][net]["status"] == "sent-to-operator":
            _alert(net, q, "این استوری در «پیام‌های ذخیره‌شده»ی همین اپ آماده است؛ وب این اپ دکمه‌ی استوری ندارد",
                   "در گوشی همان پیام را باز کنید و با یک لمس به استوری بفرستید")
        say(f"{FA_NET.get(net, net)}: {q['results'][net]['status']}")
    _settle(q)
    q["published_at"] = _now() if sent else q.get("published_at")
    return save(q)


def _expire(q, nets, why):
    for n in nets:
        q["results"][n] = {"status": "expired", "detail": why, "at": _now()}
    _settle(q)
    trace.step(q["id"], "publish", "زمانش گذشت", why)
    save(q)


CATCHUP_TIMES = ("11:20", "14:40")   # between the plan's slots (stories 9/13/16, channel 10:30/12:30/17:30)


def _next_slot(t, used):
    """The first catch-up time ≥ t, not on Friday, on a day with room left."""
    day = t.replace(second=0, microsecond=0)
    for _ in range(60):
        if day.weekday() != 4 and used.get(day.date().isoformat(), 0) < CATCHUP_PER_DAY:
            for hm in CATCHUP_TIMES:
                h, m = map(int, hm.split(":"))
                cand = day.replace(hour=h, minute=m)
                if cand >= t and not used.get(cand.isoformat(timespec="minutes")):
                    return cand
        day = (day + timedelta(days=1)).replace(hour=0, minute=0)
    return t


def reschedule(say=print):
    """Content that could not go out (account signed out, or never connected yet) is given a new time as soon as
    the account is back: oldest first, a few hours apart, a few a day — never a burst."""
    import hashlib
    now = now_tehran()
    logged = {n for n in FA_NET if _logged(n)[1]}
    if not logged:
        return []
    items = all_items()
    used, last = {}, now + timedelta(minutes=10)
    for q in items:
        if q.get("retry_at"):
            t = datetime.fromisoformat(q["retry_at"])
            if t > now:
                used[t.date().isoformat()] = used.get(t.date().isoformat(), 0) + 1
                last = max(last, t + timedelta(minutes=1))
    out = []
    for q in sorted(items, key=_at):
        if q.get("retry_at") or q.get("status") in ("done", "rejected", "needs_fix", "expired") or not _eligible(q):
            continue
        if _at(q) + timedelta(hours=WINDOW_H) > now:
            continue                                   # its own slot is still ahead or open
        ready = [n for n in _pending(q) if n in logged]
        if not ready:
            continue
        slot = _next_slot(last, used)
        used[slot.isoformat(timespec="minutes")] = 1
        used[slot.date().isoformat()] = used.get(slot.date().isoformat(), 0) + 1
        t = slot + timedelta(minutes=int(hashlib.md5(q["id"].encode()).hexdigest(), 16) % 13)
        q["retry_at"] = t.isoformat(timespec="minutes")
        last = slot + timedelta(minutes=1)
        trace.step(q["id"], "plan", "زمان تازه", f"{t.strftime('%Y-%m-%d %H:%M')} برای {', '.join(FA_NET[n] for n in ready)}",
                   decision="در زمان خودش حساب وصل نبود؛ حالا که وصل است دوباره زمان‌بندی شد")
        save(q)
        out.append(q)
    if out:
        say(f"زمان‌بندی دوباره: {len(out)} مورد عقب‌افتاده")
    return out


def _eligible(q):
    return q.get("status") in ("approved", "partial", "waiting", "operator") or (autopublish() and q.get("status") == "draft")


def due(say=print):
    now = now_tehran()
    out = []
    for q in all_items():
        st = q.get("status")
        if st in ("done", "rejected", "needs_fix", "expired"):
            continue
        at = _at(q)
        if _retarget(q):
            _settle(q)
            save(q)
        if not _eligible(q):
            if st == "draft" and now > at + timedelta(hours=WINDOW_H):
                q["status"] = "expired"
                trace.step(q["id"], "publish", "منقضی شد", f"تا {WINDOW_H} ساعت بعد از زمانش تأیید نشد")
                save(q)
                try:
                    import alert
                    alert.send("expired", "محتوای شبکه‌ها بدون تأیید ماند و منتشر نشد",
                               f"«{q.get('type') or ''}» {q.get('date')} {q.get('at') or q.get('time') or ''} تا {WINDOW_H} ساعت بعد از زمانش تأیید نشد.",
                               "داشبورد → تولید محتوا → صف انتشار → «تأیید همه‌ی این روز»؛ یا SOCIAL_AUTOPUBLISH=1 در «تنظیمات» تا بدون تأیید برود")
                except Exception:                                      # noqa: BLE001
                    pass
            continue
        pending = _pending(q)
        if not pending:
            if _settle(q) != st:
                save(q)
            continue
        if at <= now <= at + timedelta(hours=WINDOW_H):
            out.append(publish(q, say=say, nets=pending))          # its own slot (an account that is back mid-slot still gets it)
        elif now > at + timedelta(hours=WINDOW_H):
            late = [n for n in pending if _res(q, n) is None]       # tried at its slot? no — the timer was off: same as waiting
            if q.get("type") in TIME_BOUND or q.get("kind") == "news-share" and now > at + timedelta(days=2):
                _expire(q, pending, "زمانش گذشت و در آن موقع حساب وصل نبود؛ این نوع محتوا دیر منتشر نمی‌شود")
            elif at < now - timedelta(days=CATCHUP_DAYS):
                _expire(q, pending, f"بیش از {CATCHUP_DAYS} روز منتظر ورود حساب ماند")
            elif q.get("retry_at") and datetime.fromisoformat(q["retry_at"]) <= now:
                q["retry_at"] = None
                out.append(publish(q, say=say, nets=pending))
            elif late:
                for n in late:
                    q["results"][n] = {"status": "waiting", "at": _now(), "detail": "در زمان خودش ارسال نشد — منتظر زمان‌بندی دوباره"}
                _settle(q)
                save(q)
    reschedule(say=say)
    return out


def drive_refresh(say=print, every_h=3):
    """Pick up photos the owner added or deleted on Drive within a few hours, not only at 07:15."""
    from sf import drive_sync
    last = (read_json(os.path.join(DATA, "latest", "drive.json"), {}) or {}).get("synced_at")
    if last and now_tehran() - datetime.fromisoformat(last) < timedelta(hours=every_h):
        return None
    r = drive_sync.sync(log=lambda *_: None)
    if r.get("status") == "ok":
        say(f"درایو: {r['photos']} عکس · {r['added']} تازه · {r['removed']} حذف‌شده")
    return r


def _plan_item_of(q):
    """The plan item a queue item was made from (kept since 11-10; rebuilt for older ones)."""
    if q.get("plan_item"):
        return q["plan_item"]
    plan = (read_json(PLAN, {}) or {}).get("items", [])
    hit = next((i for i in plan if i["id"] == q["id"]), None)
    if hit:
        return hit
    same = [i for i in plan if i.get("product") == q.get("product")]
    rank = next((i.get("product_rank") for i in same if i.get("product_rank")), None)
    media = next((i.get("media") for i in same if i.get("media")), None)        # tells photo_for which product's photos
    return {"id": q["id"], "date": q.get("date"), "jalali": q.get("jalali"), "time": q.get("time"), "type": q.get("type"),
            "product": q.get("product"), "kind": "story" if q.get("action") == "story" else "telegram",
            "channels": [], "product_rank": rank, "media": media}


def _unsent(q):
    return q.get("kind") in ("story", "telegram") and q.get("status") not in ("done", "rejected", "expired", "operator") \
        and not any(_res(q, n) in ("published", "sent-to-operator") for n in q.get("nets", []))


def rewrite(q, why, say=print, used=None):
    """Write an unsent item again from today's facts (same photo, same time)."""
    item = _plan_item_of(q)
    item = dict(item, _photo=q.get("photo") if _photo_fits(q.get("photo"), item) else None)   # the plan may have moved the slot to another product
    if item.get("type") in TIME_BOUND:
        return None
    trace.step(q["id"], "write", "بازنویسی", why)
    keep = {k: q.get(k) for k in ("retry_at", "results", "at")}
    q2 = prepare_item(item, used if used is not None else set(), say=say)
    for k, v in keep.items():
        if v:
            q2[k] = v
    _settle(q2) if q2.get("results") else None
    return save(q2)


def watch_pages(say=print, every_h=3):
    """The owner edited a product or category page → its content not yet published is written again from it."""
    from sf import product_pages
    state = os.path.join(DATA, "social", "page_watch.json")
    last = (read_json(state, {}) or {}).get("at")
    if last and now_tehran() - datetime.fromisoformat(last) < timedelta(hours=every_h):
        return []
    done = []
    for q in all_items():
        if not _unsent(q) or not q.get("source_fp"):
            continue
        prod, facts = catalog(_plan_item_of(q))
        fp = (facts.get("page") or {}).get("fp")
        if fp and fp != q["source_fp"]:
            r = rewrite(q, f"صفحه‌ی «{q.get('product')}» در سایت عوض شده بود؛ متن از روی صفحه‌ی تازه نوشته شد", say=say)
            if r:
                done.append(r["id"])
    write_json(state, {"at": now_tehran().isoformat(timespec="minutes"), "rewritten": done})
    if done:
        say(f"صفحه‌ی محصول عوض شده بود: {len(done)} محتوا دوباره نوشته شد")
    return done


def tick(say=print):
    now = now_tehran()
    try:
        drive_refresh(say=say)
    except Exception as exc:                                           # noqa: BLE001
        say(f"درایو: {exc}")
    if now.hour >= 7:
        prepare(days=1, say=say)
        try:
            watch_pages(say=say)
        except Exception as exc:                                       # noqa: BLE001
            say(f"پایش صفحه‌ها: {exc}")
    return due(say=say)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tick"
    {"prepare": lambda: prepare(), "due": lambda: due(), "tick": lambda: tick(),
     "reschedule": lambda: (due(), reschedule())}[cmd]()
