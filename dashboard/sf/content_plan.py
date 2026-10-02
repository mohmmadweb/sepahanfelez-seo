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
    from .drive_sync import library
    from .util import CONFIG, write_json
    drive = library()
    if drive:                                  # owner's Drive photos win; prototype photos fill missing categories
        merged = {k: ["@d/" + f for f in v] for k, v in drive.items()}
        proto = _proto_photos()
        for k, v in proto.items():
            merged.setdefault(k, v)
        return merged
    return _proto_photos()


def _proto_photos():
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
    """Build the schedule and log, for every item, why it was planned the way it was."""
    from . import trace
    photos = _photos()
    ideas = {}
    for p in (keywords_cfg or {}).get("products", []):
        ideas[p["id"]] = list(p.get("article_ideas", []))
    cycle = _weighted_cycle()
    used_photo, ci, story_n, article_n = {}, 0, [0] * len(STORY_ROTATION), 0
    type_fa = {t["id"]: t["fa"] for t in CONTENT_TYPES}
    type_goal = {t["id"]: t["goal"] for t in CONTENT_TYPES}
    items = []
    start = date.fromisoformat(cal["days"][0]["date"]) if cal.get("days") else date.today()
    src = "، ".join(cal.get("source", [])) or "—"
    skipped = [d for d in cal.get("days", [])[: days + 1] if not d["working"]]

    for day in cal.get("days", [])[: days + 1]:
        if not day["working"]:
            continue
        d = date.fromisoformat(day["date"])
        occasion = next((e for e in day["events"] if any(k in e for k in INDUSTRY_OCCASIONS)), None)
        hours = "–".join(day.get("hours") or [])
        day_step = {"title": "انتخاب روز", "detail": f"{day['weekday_fa']} {day['jalali']} — روز کاری، ساعت کاری {hours}",
                    "decision": f"منبع تقویم: {src}. جمعه، تعطیلات رسمی و روزهای خارج از ساعت کاری کنار گذاشته می‌شوند.",
                    "data": {"events": day["events"], "skipped_non_working": [f"{x['weekday_fa']} {x['jalali']}" for x in skipped][:6]}}

        def pick_photo(slug, day_idx):
            files = photos.get(slug) or []
            for f in files:
                last = used_photo.get((slug, f))
                if last is None or (day_idx - last) >= 10:
                    used_photo[(slug, f)] = day_idx
                    path = f"drive/{slug}/{f[3:]}" if f.startswith("@d/") else f"{slug}/{f}"
                    reused = [x for x in files if used_photo.get((slug, x)) is not None and x != f]
                    return path, ("از پوشه‌ی گوگل درایو کارفرما — " if f.startswith("@d/") else "از عکس‌های پروتوتایپ (درایو هنوز همگام نشده) — ") + (f"اولین عکسِ «{slug}» که در ۱۰ روز گذشته استفاده نشده؛ "
                                           f"{len(files)} عکس در این دسته، {len(reused)} تای دیگر اخیراً استفاده شده‌اند.")
            if files:
                f0 = files[0]
                return (f"drive/{slug}/{f0[3:]}" if f0.startswith("@d/") else f"{slug}/{f0}"), f"همه‌ی {len(files)} عکس این دسته در ۱۰ روز اخیر استفاده شده‌اند؛ قدیمی‌ترین تکرار شد."
            return None, f"برای «{slug}» عکسی در کتابخانه نیست (پوشه‌ی درایو هنوز همگام نشده)."

        day_idx = (d - start).days
        for pos, slot in enumerate(day.get("slots", [])[: len(STORY_ROTATION)]):
            rot = STORY_ROTATION[pos]
            base = rot[story_n[pos] % len(rot)]
            story_n[pos] += 1
            ctype = "seasonal" if (pos == 0 and occasion) else base
            rank, name, slug = cycle[ci % len(cycle)]
            ci += 1
            media, photo_why = pick_photo(slug, day_idx)
            if ctype in ("factory", "bts"):
                media = FACTORY_MEDIA[(day_idx + len(slot)) % len(FACTORY_MEDIA)]
                photo_why = "نوع محتوا پشت‌صحنه/کارخانه است؛ از عکس‌ها و ویدئوهای کارخانه به‌نوبت استفاده می‌شود."
            item_id = f"{day['date']}-{slot.replace(':', '')}-story"
            items.append({"id": item_id, "date": day["date"], "jalali": day["jalali"], "weekday": day["weekday_fa"],
                          "time": slot, "kind": "story",
                          "channels": ["اینستاگرام", "روبیکا", "ایتا", "بله", "واتساپ"],
                          "type": type_fa[ctype], "product_rank": rank, "product": name,
                          "occasion": occasion if ctype == "seasonal" else None, "media": media,
                          "status": "planned"})
            pos_fa = ["اول (جذب مخاطب)", "دوم (معرفی محصول)", "سوم (اعتماد و تبدیل)"][pos]
            trace.replan(item_id, [
                day_step,
                {"title": "ساعت انتشار", "detail": f"ساعت {slot} — استوری {pos_fa} روز",
                 "decision": f"ساعت‌های استوری این روز: {' / '.join(day.get('slots', []))} (از تنظیمات ساعت کاری کارفرما)."},
                {"title": "نوع محتوا", "detail": f"«{type_fa[ctype]}» — {type_goal[ctype]}",
                 "decision": (f"مناسبت روز «{occasion}» به صنعت مربوط است، پس استوری اول به‌جای «{type_fa[base]}» مناسبتی شد."
                              if ctype != base else f"چرخه‌ی ثابت جایگاه {pos_fa}: {' ← '.join(type_fa[x] for x in rot)}؛ نوبت این بار: {type_fa[ctype]}."),
                 "alternatives": [type_fa[x] for x in rot if x != ctype]},
                {"title": "محصول", "detail": f"#{rank} {name}",
                 "decision": "چرخه‌ی وزن‌دار لیست اولویت کارفرما: اولویت ۱ تا ۴ سه بار، ۵ تا ۹ دو بار، ۱۰ تا ۱۳ یک بار در هر دور؛ محصول تکراری پشت سر هم نمی‌آید."},
                {"title": "عکس / ویدئو", "detail": media or "—", "decision": photo_why},
                {"title": "کانال‌ها", "detail": "اینستاگرام (خودکار با API رسمی) · روبیکا، ایتا، بله، واتساپ (یک‌لمسی: فایل ۱۰ دقیقه زودتر روی گوشی اپراتور)",
                 "decision": "این چهار پیام‌رسان API رسمی برای استوری ندارند."},
                {"title": "وضعیت", "detail": "برنامه‌ریزی شد — منتظر تولید متن و طراحی",
                 "decision": "تا وقتی تولید شروع نشده، این برنامه هر صبح دوباره با تقویم و عکس‌های تازه سنجیده می‌شود."},
            ])

        for tpos, ttime in enumerate(day.get("telegram", [])[: len(TELEGRAM_KINDS)]):
            ttype, what, status = TELEGRAM_KINDS[tpos]
            item_id = f"{day['date']}-{ttime.replace(':', '')}-channel"
            items.append({"id": item_id, "date": day["date"], "jalali": day["jalali"], "weekday": day["weekday_fa"],
                          "time": ttime, "kind": "telegram", "channels": ["تلگرام", "بله", "ایتا", "روبیکا"],
                          "type": ttype, "product": what, "product_rank": None, "media": None, "status": status})
            trace.replan(item_id, [
                day_step,
                {"title": "نوع پست کانال", "detail": f"«{ttype}» ساعت {ttime}",
                 "decision": f"پست‌های کانال این روز: {' / '.join(day.get('telegram', []))} — به ترتیب خبر، قیمت روز (بعد از به‌روزرسانی ۱۲:۳۰)، محتوای آموزشی."},
                {"title": "منبع", "detail": what,
                 "decision": "منابع خبری هنوز از کارفرما نرسیده؛ این پست تا آن موقع منتشر نمی‌شود." if status == "needs-sources" else "از داده‌ی خود سایت و تقویم محتوا."},
            ])

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
            media, photo_why = pick_photo(slug, day_idx)
            item_id = f"{day['date']}-1100-article"
            items.append({"id": item_id, "date": day["date"], "jalali": day["jalali"], "weekday": day["weekday_fa"],
                          "time": "11:00", "kind": "article", "channels": ["سایت", "تلگرام (خلاصه + لینک)"],
                          "type": idea["type"] if idea else type_fa[ctype], "product_rank": rank,
                          "product": name, "title": idea["title"] if idea else None,
                          "keyword": idea.get("keyword") if idea else None,
                          "media": media, "status": "planned"})
            trace.replan(item_id, [
                day_step,
                {"title": "سهمیه‌ی مقاله", "detail": f"هفته‌ی {week + 1} از شروع: {per_week} مقاله در هفته",
                 "decision": "رشد پلکانی: هفته‌ی ۱–۲ سه مقاله، ۳–۴ پنج مقاله، بعد هر روز کاری. کیفیت پیش از کمیت."},
                {"title": "محصول", "detail": f"#{rank} {name}", "decision": "مقاله‌ها به‌نوبت روی ۱۳ محصول اولویت‌دار کارفرما می‌چرخند."},
                {"title": "موضوع و کلمه‌ی کلیدی", "detail": (idea or {}).get("title") or "— (ایده‌ی آماده نماند)",
                 "decision": (f"اولین ایده‌ی استفاده‌نشده از تحقیق کلمات کلیدی این محصول؛ کلمه‌ی هدف: «{idea.get('keyword')}»."
                              if idea else "ایده‌های این محصول تمام شده؛ موضوع از شکاف‌های کلمات کلیدی انتخاب خواهد شد."),
                 "alternatives": [x["title"] for x in idea_list[:3]]},
                {"title": "عکس شاخص", "detail": media or "—", "decision": photo_why},
                {"title": "وضعیت", "detail": "برنامه‌ریزی شد — منتظر بریف و نوشتن", "decision": "در دو هفته‌ی اول، متن پیش از انتشار برای تأیید شما فرستاده می‌شود."},
            ])
    return {"types": CONTENT_TYPES, "priority": [{"rank": r, "name": n, "slug": s,
                                                  "photos": len(photos.get(s, []))} for r, n, s in PRIORITY],
            "items": items}
