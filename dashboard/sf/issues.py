"""
Turn the day's data into a ranked list of problems, each with a fix.

Severity: critical > high > medium > low. Each issue carries a stable `id` so the
dashboard can show when it first appeared and when it was resolved.
"""

import re
from collections import defaultdict

from .util import decode_url, norm

SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
INDEXABLE = {"home", "price", "category", "product", "article", "static", "category-index", "blog-index"}


def _short(url):
    return decode_url(url).replace("https://sepahanfelez.ir", "") or "/"


def page_targets(keywords_cfg, overrides=None):
    """{canonical url: {"primary": kw, "secondary": [...], "product_id": n}} from keywords.json."""
    from .util import canon_url
    out = {}
    if not keywords_cfg and not overrides:
        return out
    keywords_cfg = keywords_cfg or {}
    for p in keywords_cfg.get("products", []):
        u = p.get("target_url")
        if u:
            out[canon_url(u)] = {"primary": p.get("primary"), "secondary": p.get("secondary", []),
                                 "product_id": p.get("id"), "name": p.get("name_fa")}
    by_url = defaultdict(list)
    for k in keywords_cfg.get("keywords", []):
        if k.get("target_url"):
            by_url[canon_url(k["target_url"])].append(k)
    for u, kws in by_url.items():
        if u in out:
            continue
        kws.sort(key=lambda k: (-(k.get("seen_count") or 0), k.get("suggest_rank") or 99))
        out[u] = {"primary": kws[0]["kw"], "secondary": [k["kw"] for k in kws[1:5]], "product_id": None}
    for path, t in (overrides or {}).items():
        out[canon_url("https://sepahanfelez.ir" + path)] = {"product_id": None, **t}
    return out


def kw_in(kw, text):
    if not kw or not text:
        return False
    nk, nt = norm(kw), norm(text)
    if nk in nt:
        return True
    # all significant words present (Persian word order varies: «قیمت توری مرغی» vs «توری مرغی قیمت»)
    words = [w for w in nk.split() if len(w) > 1 and w not in {"و", "در", "از", "به", "با", "برای"}]
    return bool(words) and all(w in nt for w in words)


def analyse(site, crawl, keywords_cfg=None, gsc=None, psi=None, known=None):
    th = site["thresholds"]
    issues = []

    def add(iid, sev, cat, title, detail, fix, urls=None, source="crawl"):
        issues.append({"id": iid, "severity": sev, "category": cat, "title": title, "detail": detail,
                       "fix": fix, "urls": [_short(u) for u in (urls or [])][:40],
                       "count": len(urls or []) or 1, "source": source})

    pages = [p for p in crawl["pages"]]
    ok = [p for p in pages if p["status"] == 200 and not p.get("redirect_to")]
    idx = [p for p in ok if p["type"] in INDEXABLE]

    # ---- site-level
    c = crawl["checks"]
    for f in c.get("foreign_hosts", []):
        if f.get("serves_our_content"):
            add(f"foreign-{f['host']}", "critical", "فنی", f"سایت روی دامنه‌ی غریبه‌ی {f['host']} هم باز می‌شود",
                "محتوای تکراری روی دامنه‌ی دیگر با ما برای همان کلمات رقابت می‌کند (همان مشکل ۱۷ مرداد).",
                "بلوک canonical-host در ابتدای public_html/.htaccess را بررسی کنید؛ باید ۴۱۰ بدهد.")
    tls = c.get("tls", {})
    if tls.get("days_left") is not None and tls["days_left"] < 21:
        add("tls-expiry", "critical" if tls["days_left"] < 7 else "high", "فنی",
            f"گواهی SSL تا {tls['days_left']} روز دیگر منقضی می‌شود",
            f"تاریخ انقضا {tls['expires']} ({tls.get('issuer')}). اگر AutoSSL تمدید نکند سایت از دسترس خارج می‌شود.",
            "در cPanel → SSL/TLS Status وضعیت AutoSSL را چک کنید؛ مسیر /.well-known/ نباید ۴۱۰ بدهد.")
    if c.get("robots", {}).get("status") != 200:
        add("robots", "high", "فنی", "robots.txt در دسترس نیست", str(c.get("robots")), "فایل robots.txt را برگردانید.")
    if crawl["sitemap"].get("error"):
        add("sitemap-error", "critical", "ایندکس", "نقشه‌ی سایت خوانده نشد", crawl["sitemap"]["error"],
            "/sitemap.xml را بررسی کنید.")

    # ---- status
    broken = [p for p in pages if p["status"] != 200 and not p.get("redirect_to")]
    if broken:
        add("broken-pages", "critical", "فنی", f"{len(broken)} صفحه‌ی لینک‌شده خطا می‌دهد",
            "این نشانی‌ها از داخل سایت لینک شده‌اند ولی ۴۰۴/۵۰۰ برمی‌گردانند: "
            + "، ".join(f"{_short(p['url'])} ({p['status'] or p['error']}) ← از {len(p.get('linked_from', []))}+ صفحه"
                       for p in broken[:6]),
            "یا صفحه را برگردانید، یا لینک را از منو/محتوا بردارید، یا ۳۰۱ به نزدیک‌ترین صفحه بزنید.",
            [p["url"] for p in broken])
    redirects = [p for p in pages if p.get("redirect_to")]
    if redirects:
        add("internal-redirects", "medium", "لینک داخلی", f"{len(redirects)} لینک داخلی به نشانی ریدایرکت‌شده",
            "هر لینک داخلی که از ریدایرکت رد می‌شود بودجه‌ی خزش هدر می‌دهد و اعتبار لینک را کم می‌کند: "
            + "، ".join(f"{_short(p['url'])} → {_short(p['redirect_to'])}" for p in redirects[:5]),
            "لینک‌ها را مستقیم به نشانی نهایی بدهید (در منو و بدنه‌ی مقاله‌ها).",
            [p["url"] for p in redirects])

    # ---- test / junk pages
    junk = [p for p in ok if re.search(r"تست|test|lorem|مسعود", decode_url(p["url"]), re.I)
            or (p["type"] == "category" and not p.get("title"))]
    if junk:
        add("junk-pages", "high", "محتوا", f"{len(junk)} صفحه‌ی آزمایشی/بی‌عنوان روی سایت زنده",
            "این صفحات عنوان ندارند یا اسمشان آزمایشی است و برخی از منوی همه‌ی صفحات لینک می‌گیرند: "
            + "، ".join(f"{_short(p['url'])} (ورودی {p['inlinks']})" for p in junk[:6]),
            "از پنل غیرفعال یا حذف کنید؛ اگر محتوای واقعی دارند عنوان و توضیح بنویسید. "
            "خوب است که noindex هستند، ولی لینک منو به آن‌ها اعتبار صفحات اصلی را هدر می‌دهد.",
            [p["url"] for p in junk])
        # every other check is about real pages; junk would only inflate them
        idx = [p for p in idx if p not in junk]

    # ---- titles & descriptions
    def group(check):
        return [p for p in idx if check(p)]

    missing_title = group(lambda p: not (p.get("title") or "").strip())
    if missing_title:
        add("title-missing", "high", "متا", f"{len(missing_title)} صفحه بدون عنوان (title)",
            "بدون title گوگل خودش عنوان می‌سازد و معمولاً بد.", "در پنل برای هر صفحه meta_title بنویسید.",
            [p["url"] for p in missing_title])
    titles = defaultdict(list)
    for p in idx:
        if p.get("title"):
            titles[norm(p["title"])].append(p["url"])
    dup = {t: us for t, us in titles.items() if len(us) > 1}
    if dup:
        allu = [u for us in dup.values() for u in us]
        add("title-duplicate", "high", "متا", f"{len(allu)} صفحه با عنوان تکراری ({len(dup)} گروه)",
            "صفحاتی که عنوان یکسان دارند با هم رقابت می‌کنند (کنیبالیزیشن): "
            + " | ".join(f"«{t[:50]}» ×{len(us)}" for t, us in list(dup.items())[:4]),
            "برای هر صفحه عنوان یکتا با کلمه‌ی کلیدی خودش بنویسید.", allu)
    long_t = group(lambda p: len(p.get("title") or "") > th["title_max"])
    if long_t:
        add("title-long", "low", "متا", f"{len(long_t)} عنوان بلندتر از {th['title_max']} کاراکتر",
            "در نتایج گوگل بریده می‌شود و انتهای عنوان (معمولاً برند) دیده نمی‌شود.",
            "کلمه‌ی کلیدی اول، برند آخر، حداکثر ~۶۰ کاراکتر.", [p["url"] for p in long_t])
    short_t = group(lambda p: 0 < len(p.get("title") or "") < th["title_min"])
    if short_t:
        add("title-short", "medium", "متا", f"{len(short_t)} عنوان خیلی کوتاه",
            "فضای عنوان برای کلمات کلیدی فرعی استفاده نشده.", "عنوان را به ۴۰–۶۰ کاراکتر برسانید.",
            [p["url"] for p in short_t])
    no_desc = group(lambda p: not (p.get("description") or "").strip())
    if no_desc:
        add("desc-missing", "medium", "متا", f"{len(no_desc)} صفحه بدون توضیحات متا",
            "گوگل تکه‌ای تصادفی از صفحه را به‌عنوان توضیح نشان می‌دهد؛ نرخ کلیک پایین می‌آید.",
            "۱۲۰–۱۶۰ کاراکتر با کلمه‌ی کلیدی و یک دعوت به اقدام (تماس/استعلام قیمت).",
            [p["url"] for p in no_desc])
    descs = defaultdict(list)
    for p in idx:
        if p.get("description"):
            descs[norm(p["description"])].append(p["url"])
    ddup = [u for us in descs.values() if len(us) > 1 for u in us]
    if ddup:
        add("desc-duplicate", "medium", "متا", f"{len(ddup)} صفحه با توضیحات متای تکراری",
            "توضیح تکراری یعنی گوگل صفحات را متمایز نمی‌بیند.", "برای هر صفحه توضیح اختصاصی بنویسید.", ddup)
    long_d = group(lambda p: len(p.get("description") or "") > th["desc_max"])
    if long_d:
        add("desc-long", "low", "متا", f"{len(long_d)} توضیح متای بلندتر از {th['desc_max']} کاراکتر",
            "بریده می‌شود.", "حداکثر ~۱۶۰ کاراکتر.", [p["url"] for p in long_d])

    # ---- headings
    no_h1 = group(lambda p: not p.get("h1"))
    if no_h1:
        add("h1-missing", "high", "ساختار", f"{len(no_h1)} صفحه بدون H1", "", "هر صفحه دقیقاً یک H1 با موضوع اصلی.",
            [p["url"] for p in no_h1])
    multi_h1 = group(lambda p: len(p.get("h1") or []) > 1)
    if multi_h1:
        add("h1-multiple", "low", "ساختار", f"{len(multi_h1)} صفحه با چند H1", "", "فقط یک H1 نگه دارید.",
            [p["url"] for p in multi_h1])

    # ---- robots / canonical
    noindex = group(lambda p: "noindex" in (p.get("robots") or "").lower())
    if noindex:
        add("noindex", "critical", "ایندکس", f"{len(noindex)} صفحه‌ی مهم noindex است",
            "این صفحات عمداً از گوگل حذف شده‌اند.", "اگر عمدی نیست، index_by_crawler را در پنل روشن کنید.",
            [p["url"] for p in noindex])
    from .util import canon_url
    bad_canon = group(lambda p: p.get("canonical") and canon_url(p["canonical"]) != p["url"])
    if bad_canon:
        add("canonical-other", "high", "ایندکس", f"{len(bad_canon)} صفحه canonical را به نشانی دیگری داده",
            "، ".join(f"{_short(p['url'])} → {_short(p['canonical'])}" for p in bad_canon[:4]),
            "canonical هر صفحه باید خودش باشد، مگر نسخه‌ی تکراری واقعی.", [p["url"] for p in bad_canon])
    no_canon = group(lambda p: not p.get("canonical"))
    if no_canon:
        add("canonical-missing", "medium", "ایندکس", f"{len(no_canon)} صفحه بدون canonical", "",
            "تگ canonical خودارجاع اضافه شود.", [p["url"] for p in no_canon])

    # ---- sitemap coverage & orphans
    not_in_sm = group(lambda p: not p["in_sitemap"] and p["type"] in {"category", "product", "article"}
                      and p not in junk)
    if not_in_sm:
        add("not-in-sitemap", "medium", "ایندکس", f"{len(not_in_sm)} صفحه‌ی زنده در نقشه‌ی سایت نیست",
            "گوگل این صفحات را فقط از راه لینک پیدا می‌کند و دیرتر ایندکس می‌کند.",
            "Sitemap::url() همه‌ی دسته‌ها/محصولات فعال را پوشش دهد.", [p["url"] for p in not_in_sm])
    orphan = group(lambda p: p["inlinks"] <= 1 and p["type"] in {"product", "article", "category"})
    if orphan:
        add("weak-inlinks", "medium", "لینک داخلی", f"{len(orphan)} صفحه با ۰–۱ لینک داخلی ورودی",
            "صفحه‌ای که از جای دیگر سایت لینک نمی‌گیرد برای گوگل کم‌اهمیت است.",
            "از مقاله‌های مرتبط و صفحه‌ی دسته به آن لینک بدهید (اتوماسیون مقاله این را خودکار انجام می‌دهد).",
            [p["url"] for p in orphan])

    # ---- content depth
    thin = []
    for p in idx:
        lim = th["thin_words"].get(p["type"])
        if lim and (p.get("words") or 0) < lim:
            thin.append(p)
    if thin:
        add("thin-content", "high" if any(p["type"] == "product" for p in thin) else "medium", "محتوا",
            f"{len(thin)} صفحه با محتوای کم",
            "، ".join(f"{_short(p['url'])} ({p.get('words')} کلمه)" for p in thin[:5]),
            "صفحه‌ی محصول: مشخصات، کاربرد، راهنمای خرید، پرسش‌وپاسخ. مقاله: حداقل ۸۰۰ کلمه با تصویر محصول.",
            [p["url"] for p in thin])

    # ---- images
    alt = [p for p in idx if (p.get("images_no_alt") or 0) > 0]
    if alt:
        n = sum(p["images_no_alt"] for p in alt)
        add("img-alt", "medium", "تصاویر", f"{n} تصویر بدون alt در {len(alt)} صفحه",
            "جستجوی تصویری گوگل برای محصولات مفتولی ترافیک خوبی دارد و alt سیگنال اصلی آن است.",
            "alt توصیفی فارسی با نام محصول (مثلاً «رول توری مرغی گالوانیزه عرض ۱۲۰»).", [p["url"] for p in alt])

    # ---- schema
    no_product_schema = [p for p in idx if p["type"] in {"product"} and "Product" not in (p.get("schema") or [])]
    if no_product_schema:
        add("schema-product", "high", "داده‌ی ساختاریافته", f"{len(no_product_schema)} صفحه‌ی محصول بدون Product schema",
            "", "Schema::product() در کیت لاراول.", [p["url"] for p in no_product_schema])
    cats_no_offer = [p for p in idx if p["type"] == "category" and "Product" not in (p.get("schema") or [])
                     and p not in junk]
    if cats_no_offer:
        add("schema-category", "medium", "داده‌ی ساختاریافته",
            f"{len(cats_no_offer)} صفحه‌ی دسته بدون ItemList محصولات",
            "فقط دسته‌ی سیم خاردار ItemList/Offer دارد؛ بقیه‌ی دسته‌ها چون محصولاتشان اسلاگ ندارند خالی می‌مانند.",
            "با اسلاگ‌دار شدن محصولات خودبه‌خود درست می‌شود.", [p["url"] for p in cats_no_offer])
    articles_no_schema = [p for p in idx if p["type"] == "article"
                          and not {"Article", "BlogPosting", "NewsArticle"} & set(p.get("schema") or [])]
    if articles_no_schema:
        add("schema-article", "medium", "داده‌ی ساختاریافته", f"{len(articles_no_schema)} مقاله بدون Article schema",
            "بدون آن تاریخ انتشار، نویسنده و تصویر مقاله برای گوگل مشخص نیست.",
            "BlogPosting با author، datePublished، dateModified، image.", [p["url"] for p in articles_no_schema])

    # ---- speed (lab, from our own fetch)
    slow = [p for p in ok if (p.get("seconds") or 0) > th["slow_seconds"]]
    if slow:
        add("slow-pages", "medium", "سرعت", f"{len(slow)} صفحه با زمان پاسخ بیش از {th['slow_seconds']} ثانیه",
            "، ".join(f"{_short(p['url'])} ({p['seconds']}s)" for p in slow[:5]),
            "ایندکس‌های دیتابیس + کش؛ سرور زیر بار است.", [p["url"] for p in slow])

    # ---- price freshness
    price = next((p for p in ok if p["type"] == "price"), None)
    if price and price.get("price_freshness", {}).get("freshest_days") is not None:
        days = price["price_freshness"]["freshest_days"]
        if days > th["stale_price_days"]:
            add("price-stale-live", "critical" if days > 60 else "high", "محتوا و اعتماد",
                f"جدیدترین قیمت در /price مال {days} روز پیش است",
                "سرتیتر صفحه «قیمت لحظه‌ای» است ولی همه‌ی ردیف‌ها ماه‌ها پیش تغییر کرده‌اند. رقبای اصلی (آهن ملل، فولاد توفیقی) قیمت همان روز دارند.",
                "قیمت‌ها را هر روز ۱۲:۳۰ به‌روز کنید؛ حتی اگر تغییری نیست تاریخ بررسی را ثبت کنید. ریشه‌ی فنی: دستور price:update در Kernel::schedule ثبت نشده و هاست cron ندارد.",
                [price["url"]])

    # ---- old brand (آهن امن) still visible in titles/descriptions/H1
    legacy = re.compile(r"آهن\s*امن|اهن\s*امن|ahan\s*-?\s*amn|ahanamn", re.I)
    old_brand = [p for p in idx if legacy.search(" ".join([p.get("title") or "", p.get("description") or "",
                                                           " ".join(p.get("h1") or []), p.get("og_title") or ""]))]
    if old_brand:
        add("old-brand-text", "high", "برند", f"{len(old_brand)} صفحه هنوز نام برند قدیمی «آهن امن» را در عنوان/توضیح دارد",
            "، ".join(f"{_short(p['url'])} ← «{(p.get('title') or '')[:60]}»" for p in old_brand[:5]),
            "در پنل، meta_title و meta_description این صفحات را با «سپاهان فلز» اصلاح کنید.", [p["url"] for p in old_brand])

    # ---- keyword targeting
    targets = page_targets(keywords_cfg, site.get("target_overrides"))
    miss_title, miss_h1 = [], []
    money = {"home", "price", "category", "product", "category-index"}
    for p in idx:
        t = targets.get(p["url"])
        # articles are judged by their own topic, not by whichever keyword happened to map to them
        if not t or not t.get("primary") or p["type"] not in money:
            continue
        p["target"] = t
        if not kw_in(t["primary"], p.get("title")):
            miss_title.append(p)
        if not any(kw_in(t["primary"], h) for h in (p.get("h1") or [])):
            miss_h1.append(p)
    if miss_title:
        add("kw-title", "high", "کلمه‌ی کلیدی", f"{len(miss_title)} صفحه کلمه‌ی کلیدی هدفش را در عنوان ندارد",
            "، ".join(f"{_short(p['url'])} ← «{p['target']['primary']}»" for p in miss_title[:5]),
            "کلمه‌ی کلیدی اصلی را در ابتدای meta_title بیاورید.", [p["url"] for p in miss_title])
    if miss_h1:
        add("kw-h1", "medium", "کلمه‌ی کلیدی", f"{len(miss_h1)} صفحه کلمه‌ی کلیدی هدفش را در H1 ندارد",
            "، ".join(f"{_short(p['url'])} ← «{p['target']['primary']}»" for p in miss_h1[:5]),
            "H1 = نام محصول + کلمه‌ی کلیدی اصلی.", [p["url"] for p in miss_h1])

    if keywords_cfg:
        gaps = [p for p in keywords_cfg.get("products", []) if not p.get("target_url")]
        if gaps:
            add("priority-no-page", "critical", "کلمه‌ی کلیدی",
                f"{len(gaps)} محصول اولویت‌دار کارفرما صفحه‌ی هدف ندارد",
                "، ".join(f"#{g['id']} {g['name_fa']}" for g in gaps),
                "برای هر کدام صفحه‌ی دسته یا محصول با محتوای کامل ساخته شود.", [], source="keywords")

    # ---- Search Console signals
    if gsc and gsc.get("status") == "ok":
        pages_gsc = {canon_url(p["page"]): p for p in gsc.get("pages", [])}
        low_ctr = [p for p in gsc.get("queries", []) if p["impressions"] >= 50 and p["position"] <= 10 and p["ctr"] < 2]
        if low_ctr:
            add("gsc-low-ctr", "high", "سرچ کنسول", f"{len(low_ctr)} کوئری در صفحه‌ی اول با CTR زیر ۲٪",
                "، ".join(f"«{q['query']}» (رتبه {q['position']}، {q['ctr']}٪)" for q in low_ctr[:5]),
                "عنوان و توضیح متای صفحه‌ی مربوط را جذاب‌تر کنید (عدد، قیمت، «درب کارخانه»).",
                [], source="gsc")
        striking = [q for q in gsc.get("queries", []) if 8 < q["position"] <= 20 and q["impressions"] >= 20]
        if striking:
            add("gsc-striking", "medium", "سرچ کنسول", f"{len(striking)} کوئری در رتبه‌ی ۹ تا ۲۰ (فرصت نزدیک)",
                "، ".join(f"«{q['query']}» ({q['position']})" for q in striking[:6]),
                "محتوای صفحه‌ی هدف را گسترش دهید و از مقاله‌های مرتبط لینک داخلی بدهید.", [], source="gsc")
        zero = [p for p in idx if p["url"] not in pages_gsc and p["type"] in {"category", "product", "article"}]
        if zero:
            add("gsc-no-impressions", "medium", "سرچ کنسول", f"{len(zero)} صفحه در ۲۸ روز هیچ ایمپرشنی نداشته",
                "یا ایندکس نشده‌اند یا برای هیچ کوئری‌ای رتبه ندارند.", "URL Inspection و بهبود محتوا/لینک داخلی.",
                [p["url"] for p in zero], source="gsc")

    # ---- PageSpeed
    if psi and psi.get("status") == "ok":
        poor = [r for r in psi["results"] if r["status"] == "ok" and r["strategy"] == "mobile"
                and r["scores"].get("performance", 100) < 50]
        if poor:
            add("psi-poor", "high", "سرعت", f"{len(poor)} قالب صفحه با امتیاز سرعت موبایل زیر ۵۰",
                "، ".join(f"{_short(r['url'])} ({r['scores']['performance']})" for r in poor),
                "فرصت‌های اصلی در تب «فنی و سرعت».", [r["url"] for r in poor], source="psi")

    # ---- known (manual) issues
    for k in (known or {}).get("issues", []):
        if k.get("status") == "done":
            continue
        issues.append({"id": f"known-{k['id']}", "severity": k["severity"], "category": k["category"],
                       "title": k["title"], "detail": k["detail"], "fix": k["fix"], "urls": [],
                       "count": 1, "source": "manual", "status": k.get("status")})

    issues.sort(key=lambda i: (SEV_ORDER[i["severity"]], -i["count"]))
    return issues


def health_score(issues, n_pages):
    """0–100. Critical issues cost most; per-page issues scale with how much of the site they touch."""
    weight = {"critical": 12, "high": 6, "medium": 2.5, "low": 1}
    penalty = 0
    for i in issues:
        if i["source"] == "manual":
            continue
        breadth = min(1.0, 0.35 + 0.65 * (i["count"] / max(n_pages, 1))) if i["urls"] else 1.0
        penalty += weight[i["severity"]] * breadth
    return max(0, round(100 - penalty))
