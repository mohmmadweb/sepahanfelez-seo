# داشبورد رصد سئو و محتوای سپاهان فلز

**نشانی:** https://sepahanfelezseo.lenzit.ir — رمزدار (داده‌ها در مرورگر با رمز باز می‌شوند)، `noindex`.

## کلیدها و رمزها

همه‌ی کلیدها، رمزها و شماره‌ها **فقط** در `../.env` روی سرور هستند (chmod 600، در گیت نیست).
نام متغیرها و توضیحشان در `../.env.example`. کد هیچ مقداری را جایی نمی‌نویسد.

| کار | متغیر |
|---|---|
| رمز ورود داشبورد | `SF_DASHBOARD_PASSWORD` — بعد از تغییر: `run_daily.py --only build publish` |
| کلید رمزگذاری پشتیبان و داده‌ی گوگل | `SF_STATE_KEY` (همین مقدار در GitHub Secret) |

## جریان روزانه

1. **۰۶:۳۰ تهران — GitHub Actions** (`.github/workflows/google-data.yml`): سرچ کنسول، GA4،
   PageSpeed و URL Inspection → رمزگذاری با `SF_STATE_KEY` → شاخه‌ی `google-data`.
   (گوگل API را از IP سرور ما رد می‌کند؛ فقط همین بخش بیرون اجرا می‌شود.)
   Secrets لازم: `GOOGLE_SERVICE_ACCOUNT`، `GOOGLE_API_KEY`، `SF_STATE_KEY`؛ Variable: `GA4_PROPERTY_ID`.
2. **۰۷:۱۵ تهران — سرور** (`sepahanfelez-seo.timer` کاربر): `run_daily.py`
   - خزش sepahanfelez.ir (`sf/crawl.py`)، نقشه‌ی سایت رقبا (`sf/competitors.py`)
   - تقویم time.ir و صف انتشار (`sf/calendar_ir.py`، `sf/content_plan.py`)
   - داده‌ی گوگل از `google-data` (`sf/publish.py → pull_google`)
   - وضعیت ورود شبکه‌ها (`automation/social/login.py status`)
   - مشکلات و امتیاز (`sf/issues.py`) → ساخت صفحه‌ی رمزدار (`sf/build.py`) → gh-pages
   - پشتیبان رمزشده‌ی config و data در درایو: `gdrive:Backups/sepahanfelez-seo/`

```bash
cd dashboard
../.venv/bin/python run_daily.py                       # همه
../.venv/bin/python run_daily.py --skip crawl competitors
../.venv/bin/python run_daily.py --only build publish  # فقط ساخت و انتشار
```

`config/` (به‌جز `site.json`) و `data/` اطلاعات تجاری‌اند و در گیت نیستند؛ فقط در پشتیبان رمزشده.

## شبکه‌ها

`../automation/social/login.sh status|login <net>|logout <net>` — نشست‌ها در `../automation/sessions/`.
تاریخچه‌ی هر انتشار: `../automation/history.py → record()` → `data/published/<network>.jsonl` → تب «تاریخچه‌ی انتشار».

## چیزهایی که از کد پیدا نیست

- گوگل `searchconsole` و `pagespeedonline` را از IP سرور با ۴۰۳ HTML رد می‌کند؛ جستجوی google.com کپچا می‌دهد.
  Autocomplete و Trends کار می‌کنند.
- `requests.Response` در ۴xx مقدار False دارد؛ همیشه `r is not None`.
- پورت 8797 مال پروژه‌ی دیگری است؛ پیش‌نمایش محلی روی 8811.
- `publish_site` صفحه‌ی بدون رمز را منتشر نمی‌کند (اگر `SF_DASHBOARD_PASSWORD` خالی باشد خطا می‌دهد).

## حلقه‌ی مدیریت روزانه (۱۴۰۵/۰۷/۱۸، الگو از موتور محتوای لنزیت)

| بخش | ماژول | چه می‌کند |
|---|---|---|
| ماشین‌ها | `sf/machines.py` | هر مرحله‌ی اجرای روزانه زمان/نتیجه/خطا ثبت می‌کند (`data/machines.json`)؛ سلامت با «نتیجه» سنجیده می‌شود نه فقط exit code؛ نگهبان `sepahanfelez-health.timer` هر ۲ ساعت مرحله‌ی جامانده/خطادار را یک‌بار دوباره اجرا می‌کند (خطای ورود را نه) |
| برنامه و اهداف | `sf/goals.py` | هدف‌های ماه شمسی / هفته‌ی شنبه‌تا‌جمعه / امروز با عدد؛ کد می‌سنجد؛ «عقب» نسبت به زمانِ گذشته از شروع پیگیری؛ عدد هدف از داشبورد قابل تغییر (`config/goals.json`) |
| سیر تغییرات | `sf/changes.py` | تغییرهای سایت را از مقایسه‌ی خزش روزانه خودکار ثبت می‌کند و تصمیم‌ها را از داشبورد؛ بعد از N روز اثرش را روی رتبه‌ی صفحه / شاخص می‌سنجد |
| نتیجه‌ی محتوا | `sf/measure.py` | بازدید ۲۴ ساعت و ۷ روز هر پست تلگرام/اینستاگرام در برابر میانه‌ی همان قالب؛ فقط خواندنی |
| تحلیل امروز | `sf/brief.py` | واقعیت‌ها با کد → یک فراخوانی `claude -p` (sonnet، بدون ابزار، ≤۰٫۵$ هر بار، ≤۱$ در روز) → سرتیتر + بولت «چه شد — چرا — چه می‌کنیم» + ۴ چراغ + کارهای تو؛ اگر مدل نبود، متن با کد؛ آرشیو روزانه در `data/briefs/` |
