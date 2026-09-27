"""
Publishing calendar: what goes out, where, when, about which product, with which photo.

This is the scheduler the content automation will execute. It is deterministic
(same inputs → same plan) so the dashboard can show the next two weeks before a
single post is generated, and the owner can correct the mix before it runs.

Rules
- Stories: 3 per working day at the calendar's slots (Sat–Wed 09/13/16, Thu 09/11/12:40),
  on Instagram + Rubika + Eitaa + Bale + WhatsApp status.
- Channels (Telegram, Bale, Eitaa, Rubika): news, today's price after the 12:30 update,
  and one content post (Sat–Wed 10:30/12:30/17:30, Thu 10:00/12:30).
- Site article: ramped — 3/week for the first two weeks, 5/week for weeks 3–4,
  then one per working day. Each article targets one priority product.
- Products rotate by the owner's priority list, weighted (priority 1 appears
  most). A photo is never reused within 10 days.
- Occasions from time.ir that match the industry become «فصلی/مناسبتی» slots.
"""

import os
from datetime import date

from .util import config, read_json

CONTENT_TYPES = [
    {"id": "news", "fa": "خبری", "goal": "مرجع بودن؛ اخبار فولاد، مفتول، قیمت‌ها و بازار ساخت‌وساز"},
    {"id": "product", "fa": "معرفی محصول", "goal": "کاربرد و موارد مصرف هر محصول با عکس واقعی"},
    {"id": "factory", "fa": "معرفی کارخانه", "goal": "دو کارخانه، ۳۰٬۰۰۰ متر سالن، ۲۰۰ پرسنل"},
    {"id": "howto", "fa": "آموزشی-کاربردی", "goal": "راهنمای انتخاب، نصب، محاسبه‌ی متراژ و وزن"},
    {"id": "product_focus", "fa": "محصول‌محور", "goal": "یک مشخصه‌ی فنی (چشمه، قطر مفتول، گالوانیزه گرم) در یک پیام"},
    {"id": "bts", "fa": "پشت‌صحنه", "goal": "خط تولید، قرقره‌ها، بارگیری، کنترل کیفیت"},
    {"id": "usecase", "fa": "کاربرد واقعی", "goal": "پروژه‌ی واقعی: مرغداری، باغ، حصار کارخانه، دیوار گابیون"},
    {"id": "compare", "fa": "مقایسه‌ای", "goal": "گالوانیزه گرم/سرد، پرسی/جوشی، حلقوی/خطی"},
    {"id": "trust", "fa": "اعتمادساز", "goal": "قیمت درب کارخانه، استاندارد، ارسال، تماس مستقیم با کارخانه"},
    {"id": "seasonal", "fa": "فصلی/مناسبتی", "goal": "مناسبت‌های تقویم (روز استاندارد، روز ایمنی، فصل حصارکشی باغ)"},
    {"id": "faq", "fa": "پرسش و پاسخ", "goal": "سؤال‌های واقعی مشتری‌ها و کوئری‌های سرچ کنسول"},
]

# story position in the day → content types it rotates through
# (first = reach, second = product, third = trust/convert). Times come from the calendar:
# Sat–Wed 09:00/13:00/16:00, Thursday 09:00/11:00/12:40.
STORY_ROTATION = [
    ["news", "howto", "seasonal", "faq", "compare"],
    ["product", "product_focus", "usecase", "product", "compare"],
    ["bts", "trust", "factory", "usecase", "trust"],
]
TELEGRAM_KINDS = [("خبری", "اخبار بازار فولاد و مفتول (منابع کارفرما)", "needs-sources"),
                  ("قیمت روز", "جدول قیمت امروز پس از به‌روزرسانی ۱۲:۳۰", "planned"),
                  ("آموزشی-کاربردی", "پست محتوایی کانال (آموزشی / پرسش و پاسخ)", "planned")]
ARTICLE_TYPES = ["howto", "compare", "product", "usecase", "faq", "howto", "trust"]

# owner's priority list → site category slug (photos live under the same slug)
PRIORITY = [
    (1, "توری مرغی", "توری-مرغی"),
    (2, "توری جوشی ریزبافت گالوانیزه", "توری-جوشی--گالوانیزه-رول"),
    (3, "توری پرسی", "توری-پرسی"),
    (4, "مش جوشی", "مش-جوشی-یا-مش-آهنی"),
    (5, "توری حصاری (فنس)", "توری-حصاری"),
    (6, "توری گابیون", "توری-گابیون"),
    (7, "مفتول گالوانیزه", "مفتول-گالوانیزه"),
    (8, "سیم خاردار رشته‌ای", "سیم-خاردار"),
    (9, "سیم خاردار حلقوی سوزنی", "سیم-خاردار"),
    (10, "سیم رابیتس‌بندی گالوانیزه", "مفتول-گالوانیزه"),
    (11, "سیم اسکوپ / سیم گلخانه (تأیید شود)", "مفتول-گالوانیزه"),
    (12, "توری فرنگی", "توری-فرنگی"),
    (13, "سیم آرماتوربندی", "سیم-سیاه-و-آرماتور-بندی"),
]
INDUSTRY_OCCASIONS = ["استاندارد", "ایمنی", "آتش", "صنعت", "معدن", "کارگر", "مهندس", "کشاورز", "روستا",
                      "درختکاری", "منابع طبیعی", "صادرات", "ساخت", "بنا", "مسکن", "پدافند", "نوروز", "یلدا",
                      "حمل و نقل", "دامپزشکی", "محیط زیست", "زمین"]

PHOTO_ROOT = "/home/ubuntu/projects/sepahanfelez-prototype/assets/products"
FACTORY_MEDIA = [
    "banner-karkhane/عکس-خط-تولید-بدون-آدم.jpg", "banner-karkhane/عکس-قرقره-ها-بدون-آدم.jpg",
    "banner-karkhane/دو-خط-تولید-کامل.jpg", "toloue-sepahan1/طلوع-سپاهان1-عکس-هوایی.jpg",
    "toloue-sepahan2/طلوع-سپاهان2-عکس-هوایی.jpg", "toloue-sepahan1/طلوع-سپاهان1-ویدئو-هلیکوپتری.mp4",
    "toloue-sepahan2/طلوع-سپاهان2-ویدئو-هلیکوپتری.mp4", "videos/2396tehran-office.mp4",
]


def _weighted_cycle():
    """Priority 1 appears ~3× as often as priority 13."""
    seq = []
    for rank, name, slug in PRIORITY:
        reps = 3 if rank <= 4 else 2 if rank <= 9 else 1
        seq.extend([(rank, name, slug)] * reps)
    # interleave so the same product never runs back to back
    out, pool = [], seq[:]
    while pool:
        for item in list(dict.fromkeys(pool)):
            out.append(item)
            pool.remove(item)
    return out


def _photos():
    """Scan the photo folders where they exist (our server) and snapshot the index into
    config/photo_library.json, so runs elsewhere (GitHub Actions) plan with the same photos."""
    from .util import CONFIG, write_json
    path = os.path.join(CONFIG, "photo_library.json")
    if not os.path.isdir(PHOTO_ROOT):
        return (read_json(path, {}) or {}).get("by_category", {})
    lib = {}
    for slug in sorted(os.listdir(PHOTO_ROOT)):
        lib[slug] = sorted((f for f in os.listdir(os.path.join(PHOTO_ROOT, slug)) if f.startswith("photo-")),
                           key=lambda f: int("".join(c for c in f if c.isdigit()) or 0))
    write_json(path, {"source": "sepahanfelez-prototype/assets/products (public at sepahanfelez.lenzit.ir)",
                      "by_category": lib})
    return lib


def plan(cal, keywords_cfg=None, days=14):
    photos = _photos()
    ideas = {}
    for p in (keywords_cfg or {}).get("products", []):
        ideas[p["id"]] = list(p.get("article_ideas", []))
    cycle = _weighted_cycle()
    used_photo, ci, story_n, article_n = {}, 0, [0] * len(STORY_ROTATION), 0
    type_fa = {t["id"]: t["fa"] for t in CONTENT_TYPES}
    items = []
    working_seen = 0
    start = date.fromisoformat(cal["days"][0]["date"]) if cal.get("days") else date.today()

    for day in cal.get("days", [])[: days + 1]:
        if not day["working"]:
            continue
        working_seen += 1
        d = date.fromisoformat(day["date"])
        occasion = next((e for e in day["events"] if any(k in e for k in INDUSTRY_OCCASIONS)), None)

        def pick_photo(slug, day_idx):
            files = photos.get(slug) or []
            for f in files:
                last = used_photo.get((slug, f))
                if last is None or (day_idx - last) >= 10:
                    used_photo[(slug, f)] = day_idx
                    return f"{slug}/{f}"
            return f"{slug}/{files[0]}" if files else None

        day_idx = (d - start).days
        for pos, slot in enumerate(day.get("slots", [])[: len(STORY_ROTATION)]):
            rot = STORY_ROTATION[pos]
            ctype = rot[story_n[pos] % len(rot)]
            story_n[pos] += 1
            if pos == 0 and occasion:
                ctype = "seasonal"
            rank, name, slug = cycle[ci % len(cycle)]
            ci += 1
            media = pick_photo(slug, day_idx)
            if ctype in ("factory", "bts"):
                media = FACTORY_MEDIA[(day_idx + len(slot)) % len(FACTORY_MEDIA)]
            items.append({"date": day["date"], "jalali": day["jalali"], "weekday": day["weekday_fa"],
                          "time": slot, "kind": "story",
                          "channels": ["اینستاگرام", "روبیکا", "ایتا", "بله", "واتساپ"],
                          "type": type_fa[ctype], "product_rank": rank, "product": name,
                          "occasion": occasion if ctype == "seasonal" else None, "media": media,
                          "status": "planned"})

        for tpos, ttime in enumerate(day.get("telegram", [])[: len(TELEGRAM_KINDS)]):
            ttype, what, status = TELEGRAM_KINDS[tpos]
            items.append({"date": day["date"], "jalali": day["jalali"], "weekday": day["weekday_fa"],
                          "time": ttime, "kind": "telegram", "channels": ["تلگرام", "بله", "ایتا", "روبیکا"],
                          "type": ttype, "product": what, "product_rank": None, "media": None, "status": status})

        week = (d - start).days // 7
        per_week = 3 if week < 2 else 5 if week < 4 else 6
        weekday_pos = [5, 6, 0, 1, 2, 3].index(d.weekday()) if d.weekday() in (5, 6, 0, 1, 2, 3) else 0
        publish_days = {3: {0, 2, 4}, 5: {0, 1, 2, 3, 4}, 6: {0, 1, 2, 3, 4, 5}}[per_week]
        if weekday_pos in publish_days:
            rank, name, slug = PRIORITY[article_n % len(PRIORITY)]
            article_n += 1
            idea_list = ideas.get(rank) or []
            idea = idea_list.pop(0) if idea_list else None
            ctype = ARTICLE_TYPES[article_n % len(ARTICLE_TYPES)]
            items.append({"date": day["date"], "jalali": day["jalali"], "weekday": day["weekday_fa"],
                          "time": "11:00", "kind": "article", "channels": ["سایت", "تلگرام (خلاصه + لینک)"],
                          "type": idea["type"] if idea else type_fa[ctype], "product_rank": rank,
                          "product": name, "title": idea["title"] if idea else None,
                          "keyword": idea.get("keyword") if idea else None,
                          "media": pick_photo(slug, day_idx), "status": "planned"})
    return {"types": CONTENT_TYPES, "priority": [{"rank": r, "name": n, "slug": s,
                                                  "photos": len(photos.get(s, []))} for r, n, s in PRIORITY],
            "items": items}
