# sepahanfelez.ir — Session Handoff

_Last updated 2026-08-07, covering four sessions: the CI/CD build-out, the brand
cleanup, a full UI/UX + front-end + back-end audit, and the implementation of
that audit's four-wave roadmap._

_Read this before `sepahanfelez.ir-audit/FULL-AUDIT-REPORT.md`. That report is
still the best description of the site's **content** problems but its technical
findings are now largely fixed — see §2 and §3._

---

## 0. If you read nothing else

0. **The server answers to any hostname, and the whole site was live on
   `emaratnews.ir` because of it.** Closed 2026-08-08 by `092237cb` +
   `7d0416ed` — see §13. The same root cause had already poisoned the sitemap
   on 2026-08-06 and was fixed only at the sitemap. Do not remove the
   canonical-host block at the top of `public_html/.htaccess`, and **do not
   turn its 410 back into a redirect** — the rule is host-blind by necessity,
   so a redirect points other people's domains at ours. That shipped for eleven
   minutes and the owner caught it.
1. **One commit is pushed but not deployed: `3b0c0ce4`.** Everything else is
   live. The deploy pipeline stalls (§7.1) and needs a manual **Run workflow**.
   Check with the one-liner in §10 before assuming anything about what is live.
2. **The deploy pipeline stalled twice in one evening.** A run hangs, and
   because `cancel-in-progress: false` every later push queues behind it
   forever. If a deploy has not landed in 20 minutes: cancel the hung run,
   then Run workflow. §7.1.
3. **Never pick a "did it deploy?" marker without checking it did not already
   exist.** This was got wrong three times in one session, each time producing a
   confident and false "it's live". Use `Last-Modified` on `app.css`. §10.
4. **`sidemenu.js` is not built by webpack.** It is a hand-kept copy in
   `public_html/`, and it has to be. Editing the source alone ships nothing.
   §6.1 — this shipped an invisible mobile menu to production.
5. **Sizing rules must never set `display`.** A tap-target rule put the burger
   menu on every desktop page by beating the rule that hides it. §6.2.
6. **Measuring is not looking.** Three visible regressions shipped while
   font sizes, tap targets and scroll widths were all being measured correctly.
   Open the site at 375px and *look* at it. §6.
7. **PHP 8.1 is ready but must be switched in cPanel first, not in composer.**
   The wrong order killed this site once already. §8.1, and the step-by-step in
   **`reports/PHP81-RUNBOOK.md`**.
8. **The remaining PHP 8.1 risk is cPanel's extension list, not the code.**
   cPanel keeps enabled extensions *per PHP version* and does not carry them
   across a switch. `zip` off breaks the Excel import, `gd` breaks image
   uploads, the `xml*` family breaks `sitemap.xml` — all with perfectly good
   code. Check the Extensions tab before pressing Apply. Runbook has the list.
9. **`phpunit` passing under 8.1 proves almost nothing about deprecations** —
   `handleDeprecation()` returns early under `runningUnitTests()`. The question
   is asked properly in `tests/php81-deprecation-probe.php`. Answer: zero.

---

## 1. Where things stand

| Workstream | State |
|---|---|
| SEO audit | ✅ `sepahanfelez.ir-audit/FULL-AUDIT-REPORT.md` — read §1 of the previous handoff for its two misdiagnoses |
| Technical audit | ✅ `reports/گزارش-تحلیل-سپاهان-فلز.pdf` — 16pp, UI/UX + front-end + back-end, scored 46/100 |
| Wave 1–3 | ✅ implemented, deployed, verified. `reports/گزارش-بهبود-سپاهان-فلز.pdf` |
| Wave 4 (schema) | 🟡 product + category pages live; `/price` still waiting on `3b0c0ce4` — the deploy is stuck, not the code |
| Wave 4 (PHP 8.1) | ✅ **switched 2026-08-07.** 14/14 probes green, zero regressions, 13 of 14 pages byte-identical to the 7.4 baseline. `reports/PHP81-RUNBOOK.md` |
| DB indexes | ⬜ SQL written, must be run by hand in phpMyAdmin |
| CI/CD pipeline | ⚠️ works but stalls; see §7.1 |

Live right now: all pages 200, ~0.8s, zero JS errors, mobile body text 16px,
mobile header 49px, menu opens with 18 links, burger hidden on desktop.

---

## 2. What this session changed

Five commits, `edb4c0cf` → `3b0c0ce4`, 142 files.

### The headline numbers (measured on the live site, mobile 375×812)

| | before | after |
|---|---|---|
| body text | 8.4px | **16px** |
| header height | 262px | **49px** |
| text under 14px, `/price` | 189 | **15** |
| tap targets under 44px, `/price` | 92 | **5** |
| unnamed icon controls, `/price` | 24 | **3** |
| JS errors per page | 8–10 | **0** |
| login page weight | 1423 KB | **89 KB** |
| blog JS (vendor cached) | 596 KB | **50 KB** |
| the "live" clock | frozen on 16:45:22 | ticking |

### The changes that matter most

- **Typography is decoupled from layout.** `_media-Queries.scss` set the root
  font-size in absolute px per breakpoint (6px below 375) to shrink the
  *layout*; because every length is a rem, it shrank the text too. The root is
  in percent now (so the browser's own text-size setting works — WCAG 1.4.4),
  and text resolves against `--type-unit` in `_tokens.scss`, which is pinned to
  the same absolute size at every width. **Do not put a body-range font-size
  back on a raw rem** — a guard fails the build if you do.
- **The price table becomes cards below 768px.** `min-width: 992px` in a 375px
  viewport meant a phone showed the product name and nothing else. Labels come
  from `data-label` on each cell, so the markup stays one table.
- **One shared vendor bundle** (`mix.extract`). Six entry points were each
  carrying their own jQuery/Bootstrap/Popper/Slick. `manifest.js` must load
  before `vendor.js` before everything else — the layout does this with
  `defer` (which preserves order; `async` would not).
- **Auth screens rebuilt** off the Metronic theme onto a 5.7 KB stylesheet and
  ~40 lines of vanilla JS.
- **Product/Offer schema** on product pages and category pages. §4.
- Sitemap generation deferred to once per request (`SitemapQueue`), menu tree
  cached 6h with explicit flush, three cache-key bugs fixed, security headers,
  auth throttling, OTP invalidation, SVG uploads closed.

Full narrative in the three PDFs under `reports/`.

---

## 3. Bugs found and fixed that predate this session

Worth knowing because they say something about where the rot is:

- **Three view composers could take the whole site down.** `FaviconComposer`,
  `CompanyNameComposer` and `PhoneComposer` each did `Model::first()->column`
  with no null check. An empty `general_settings` or `information` row meant
  **every page** 500'd — including the login page an administrator would need
  to fix it.
- **The desktop menu's third level never rendered.** `$category->child()` with
  parentheses hands the view a relation builder, not the collection.
- **The printed price quote carried the previous owner's logo** and a phone
  number matching nothing in `config/brand.php`. `ScrubLegacyBrand` rewrites
  text, so an `<img>` survives it untouched.
- **Print column-hiding only ever worked on row one.** `print-js`
  `ignoreElements` matches ids, and those ids were repeated on every row.
- **A fresh database could not be migrated.** `routes/web.php` queries the
  `redirects` table while artisan is still loading route files.
- **Laravel's default `ExampleTest` had always failed** (`GET /` cannot be 200
  on an empty database) and `php artisan test || vendor/bin/phpunit` in CI hid
  it — `artisan test` does not exist on Laravel 8, so the `||` always fired.

Still not fixed, from the previous handoff: `SliderController@update` validates
`image` as `required` while keeping the existing one, so a slider's link cannot
be changed without re-uploading the file.

---

## 4. Structured data

`app/Support/Schema.php`. Product pages emit `Product` + `Offer` + `Brand`;
`/price` and category pages emit an `ItemList` of summary `Product`s.

**Everything deliberately omitted is a decision, not an oversight:**

| | | why |
|---|---|---|
| `priceCurrency` | **IRR** | the site quotes in ریال. `IRT` is the toman and is not an ISO 4217 code — it would advertise every price at a tenth |
| no `offers` when price ≤ 0 | | "price on application" rows store 0/null |
| no `aggregateRating` / `review` | | there are comments but no ratings anywhere |
| no `priceValidUntil` | | past date → Google drops the offer; future date → a claim nobody can stand behind |
| no `shippingDetails` / return policy | | B2B supplier quoting by phone; no published policy to cite |
| `name` is the product title alone | | the cell prints "{category} {product}" and many titles already begin with the category |

All three blocks are built inside **`Schema::safely()`**. A throw inside an
`@php` block is a 500, not a missing `<script>`, and these are three of the
busiest routes. Failure costs the markup and nothing else.

**Trap:** the markup is only half of it. `PriceListController` selects an
explicit column list, and `slug` was not on it — so the "no slug, no url" guard
correctly skipped all twenty rows and `/price` published nothing, silently,
while category and product pages worked. `slug`, `image` and `status` are on
the select now and a guard checks it.

---

## 5. Tests — run these before you push anything

```bash
cd /home/mlops/mohammad/ahanamn-src

# 34 feature tests (auth, caching, security headers, schema, smoke)
docker run --rm --user $(id -u):$(id -g) -v "$PWD":/app -w /app -e HOME=/tmp \
    php:7.4-cli vendor/bin/phpunit

# 183 checks: compiles all 133 Blade templates, brand scrubbing
docker run --rm --user $(id -u):$(id -g) -v "$PWD":/app -w /app \
    php:7.4-cli php tests/brand-scrub-check.php tests/fixtures/*.html

# 61 static guards, no database needed
docker run --rm --user $(id -u):$(id -g) -v "$PWD":/app -w /app \
    php:7.4-cli php tests/frontend-check.php

# assets
docker run --rm --user $(id -u):$(id -g) -v "$PWD":/app -w /app -e HOME=/tmp \
    node:16-bullseye npx mix --production
```

`vendor/` currently has dev dependencies installed (needed for phpunit). If it
ever needs reinstalling:

```bash
docker run --rm --user $(id -u):$(id -g) -v "$PWD":/app -w /app \
    -e HOME=/tmp -e COMPOSER_HOME=/tmp/composer composer:2 \
    composer install --no-interaction --no-scripts --prefer-dist \
                     --no-progress --ignore-platform-req="ext-*"
```

**`tests/frontend-check.php` is the important one.** Each guard asserts the
absence of something that was measurably broken and would come back silently.
It strips comments before scanning — without that it fails on its own
documentation, which is exactly what happened the first time it ran.

---

## 6. Traps this session created and then fixed

These three shipped to production. All three would have been caught by opening
the site at 375px and looking at it.

### 6.1 `sidemenu.js` is not part of the build ⚠️ permanent trap

`webpack.mix.js` does not process `resources/site/js/scripts/sidemenu.js`.
`public_html/files/js/sidemenu.js` is a hand-kept copy, and **it has to stay
that way**: the header calls `openNav()` from an inline `onclick`, and a
webpack module would scope that function away.

A CSS rule was written against a class the updated script added. The script
never shipped. The mobile menu opened `visibility: hidden` on every phone —
the primary navigation on mobile, gone, for about an hour.

```bash
cp resources/site/js/scripts/sidemenu.js public_html/files/js/sidemenu.js
```

A guard now fails if the two diverge.

### 6.2 Sizing rules must not set `display`

A tap-target block listed `.navbar-toggler` alongside `.cart`/`.user` and gave
them `display: inline-flex`. That block is unscoped and imported last, so it
beat `@media (min-width: 993px) { .navbar-toggler { display: none } }` and put
a burger on every desktop page. Anything touching the toggler now lives inside
a `max-width` query, and a guard enforces it.

### 6.3 `.logo.big-logo` beats `header .logo`

`scrollEffects.js` adds `big-logo` at scroll top, and two classes beat one. A
mobile override of `height: 4.4rem` lost to it and rendered at 200px — and
`position: static` took the logo out of the desktop's absolute positioning and
stacked it *above* the red bar, because the anchor is the first child of
`<header>`. Header height on a phone: 262px. Match `.logo.big-logo` explicitly.

### 6.4 A regex will not find `<img>` in a Blade template

`/<img[^>]*>/` looks right and is wrong: `src="{{ $slide->image() }}"` contains
a `>` in the arrow operator, so the match ends mid-attribute. A sweep written
that way corrupted 49 tags across 31 files. The Blade compile step caught it.
There is a working scanner in `tests/frontend-check.php` (`imgTags()`).

### 6.5 `??` in a test fixture can silently disable the test

`['price' => null]` fell through the null-coalescing default, so "a product
with no price gets no offer" was testing a product *with* a price. Two tests
passed and proved nothing. Use `array_key_exists`.

---

## 7. The deploy pipeline

Unchanged in design from the previous handoff (§4 there) — push to `main`,
GitHub Actions builds, snapshots the live tree, uploads only changed files via
the cPanel UAPI, health-checks five pages. `.github/deploy/` and `DEPLOYMENT.md`
in the repo.

### 7.1 It stalls ⚠️ partially fixed 2026-08-07, still stuck as of this writing

Observed timings: **17 min, then >50 min (stalled), then ~4 min once triggered
manually, then stalled again.** Then stalled again on 2026-08-07: three pushes
(`348fd360`, `aa307c38`, `4dbec17a`) and after 25 minutes nothing had landed.

The mechanism was traced in `aa307c38`, and it is not one hung request — the
uploader has always had a 120-second timeout and four attempts. It compounds:

1. cPanel serves an HTML interstitial **with a 200 on it** once rate-limited.
   `r.json()` raises, the bare `except` reads that as a transient blip, and the
   log says `Expecting value: line 1 column 1` — which names nothing.
2. `send()` collects upload failures instead of raising, so `ex.map` still runs
   **every remaining batch**, each paying its full retry budget against a limit
   none of them can outlast.
3. Worst: `read()` returns `None` when it cannot read `.deploy-state.json`, and
   `main()` reads `None` as "no recorded state" — which means **full sync of
   every file**. A rate limit while reading one small file escalates a
   twenty-file deploy into a few-thousand-request one, against the limiter that
   caused it. The likeliest way to get rate-limited is to have been
   rate-limited a moment earlier.

Fixed in `aa307c38`: the interstitial is recognised and named, a throttle flag
short-circuits later calls, `read()` refuses to imply a full sync while
throttled, and **`timeout-minutes: 30`** bounds the job so a bad run can no
longer block the queue until GitHub's 360-minute default. Seven offline checks
in `.github/deploy/test_cpanel_deploy.py`, run by CI.

**None of that helps a run already stuck** — the fix has to deploy first, and
it is queued behind the stall. Breaking the deadlock is still manual:

**If a deploy has not landed in 20 minutes:**

1. https://github.com/mohammad-kasiri/Ahanamn/actions
2. Open the run still showing in-progress → **Cancel workflow**
3. «Build & Deploy to sepahanfelez.ir» → **Run workflow** → branch `main`

Note the repo is **`mohammad-kasiri/Ahanamn`** — not under the `mohmmadweb`
account. `mohmmadweb` is only the SSH key and the commit identity. There is no
`gh` CLI and no API token on this box, so **the Actions tab cannot be read from
here at all**; the only signal available is polling the live site.

### 7.2 CI does not gate pushes to main

`ci.yml` runs on pull requests and on pushes to non-main branches
(`branches-ignore: [main, deploy]`). A direct push to `main` goes straight to
`deploy.yml` with nothing checking it. **Run the §5 suite locally first.**

### 7.3 New assets the pipeline must produce

Both workflows now assert these exist before deploying. A build that stops
producing `vendor.js` leaves the live site with no jQuery, which breaks the
cart, search, charts and slider at once.

```
public_html/files/js/manifest.js     ← webpack runtime, must load first
public_html/files/js/vendor.js       ← shared jQuery/Bootstrap/Popper/Slick
public_html/files/css/auth.css       ← the four auth screens
```

`.gitignore` swallows all of `public_html` and `*.png`, so anything new under
there needs `git add -f`. Miss one and the reference ships without the file.

---

## 8. Blocked on the owner

### 8.1 PHP 8.1 — the order is what matters

**Full procedure: `reports/PHP81-RUNBOOK.md`.** Summary of the evidence, all
re-measured 2026-08-07:

```
7861 vendor files linted under PHP 8.1        →  0 parse errors
app/config/database/routes/tests under 8.1    →  0 parse errors
34 phpunit tests under 7.4 AND 8.1            →  all pass, both
61 frontend guards under 7.4 AND 8.1          →  all pass, both
183 brand/blade checks under 7.4 AND 8.1      →  all pass, both
every composer.lock package's php constraint  →  ^7.x || ^8.0, none excludes 8
12 real HTTP requests dispatched on both      →  identical status codes,
                                                 0 deprecations on 8.1,
                                                 0 diagnostics new on 8.1
.htaccess PHP handler block                   →  none, so the switch takes effect
laravel/framework constraint                  →  ^7.3|^8.0
```

Two things worth carrying forward:

- **Deprecations cost nothing here.** `config/logging.php` declares no
  `deprecations` channel, so Laravel points it at the `null` driver and
  discards them. No log growth, nothing rendered. Do not "fix" this first.
- **The real risk moved.** It is not the code — it is that cPanel keeps its
  enabled-extension list per PHP version and does not carry it across. `zip`,
  `gd`, `xml`/`dom`/`simplexml`/`xmlreader`/`xmlwriter`, `mbstring`, `curl`,
  `bcmath`, `fileinfo`, `openssl`, `pdo_mysql`. Confirm on the Extensions tab
  **before** pressing Apply.

**8.1 specifically, not higher.** PHP 8.2 deprecated dynamic properties and
Laravel 8 leans on them heavily.

```
✅ safe:   flip cPanel 7.4 → 8.1 while vendor stays pinned to 7.4
           (7.4-compatible code runs fine on 8.1)
❌ fatal:  deploy an 8.1-resolved vendor tree to a 7.4 server
```

The second is what killed the site on 2026-08-06 (`ramsey/uuid` shipped PHP 8
syntax; every request died with a parse error before Laravel could log it).
So: **cPanel MultiPHP Manager first, verify, and only then consider touching
`config.platform.php`.** Do not change it before the server is confirmed.

The test suite does **not** cover the cart, order placement, the payment
gateway, the Excel import or the admin panel. PHP 8 behaviour changes (null
into string functions, etc.) surface exactly there. Walk those five paths by
hand after the switch.

### 8.2 Database indexes — biggest cheap win left

`database/sql/2026_08_06_add_missing_indexes.sql`, run in phpMyAdmin against
`ahanamnc_DB`. Twelve indexes; before them the whole `prices` table is sorted
on every request. There is a matching migration that checks for each index
first, so applying both is harmless.

### 8.3 Also outstanding

- **Price freshness.** The heading says «لحظه ای», the column says «۲ ماه پیش».
  Not a bug — a business decision, and now more visible because Google reads
  these pages as products with prices.
- **Confirm `APP_URL` on the server** so `TrustHosts` can be uncommented
  (line 17 of `app/Http/Kernel.php`). Switching it on blind risks 403ing the
  site.
- **Two broken images**, both data not code, both fixable in the admin panel:
  the article «توری صفحات فلزی» (`/blog/net`) stores `no-pic.jpg`, which does
  not exist; the product «سیم خاردار سوزنی قطر ۹۰» stores a filename with no
  file behind it. `public_html/images/` is outside what the pipeline may write.
- **Real social accounts** — all four stored profiles belonged to the old brand
  and are switched off. Fill them in `/admin/social`.
- **Rotate the cPanel password and the GitHub PAT** (from the previous handoff,
  still outstanding).
- **Ask 7hostir for SSH.** Still the single biggest simplification available:
  it would let `artisan migrate` run on deploy and remove most of §7.

---

## 9. Access

Unchanged from the previous handoff. Repeated here because it is load-bearing:

- Repo `mohammad-kasiri/Ahanamn` (private), Laravel 8 / PHP 7.4.
  `git clone git@github-mohmmadweb:mohammad-kasiri/Ahanamn.git`.
  SSH alias in `~/.ssh/config`. **HTTPS clone and the GitHub REST API both 404
  from this box** — no token, no `gh`.
- Working copy `/home/mlops/mohammad/ahanamn-src`. Commit as
  `mohmmadweb <80682916+mohmmadweb@users.noreply.github.com>` — already set in
  the repo's git config.
- Admin panel: `/login` → owner's mobile → 6-digit SMS code, valid 2 minutes.
  **The code is now single-use and the routes are throttled** (`throttle:5,1`
  on verify, `throttle:3,10` on request), so do not fire them in a loop.
  Scripts in `sepahanfelez.ir-audit/admin-tools/`.
- **No shell, no database access.** Migrations do not run on deploy.
- **No PHP or Node locally — use Docker**, always with `--user $(id -u):$(id -g)`
  or `vendor/` ends up root-owned. Node 18+ breaks laravel-mix 6; use `node:16`.

---

## 10. How to verify what is actually live

**Never trust a marker without checking it did not already exist.** Three
"it's deployed" reports in one session were wrong because the grep string was
already in the old build (`logo.big-logo`, `1.143rem`, and once the whole file).

The only reliable signal:

```bash
curl -sI https://sepahanfelez.ir/files/css/app.css | grep -i last-modified
```

Compare it to when you pushed. Then confirm with a string that provably only
exists in the new build (`git show HEAD~1:public_html/files/css/app.css | grep -c '<marker>'`
must return 0).

Beyond that:

```bash
# structured data actually published
curl -s https://sepahanfelez.ir/price | grep -o '"@type": "[A-Za-z]*"' | sort | uniq -c
curl -s https://sepahanfelez.ir/category/سیم-خاردار | grep -o '"@type": "[A-Za-z]*"' | sort | uniq -c

# brand traces, canonicals, robots across the whole sitemap (~1 min)
cd /home/mlops/mohammad/sepahanfelez-seo && python3 sepahanfelez.ir-audit/trace_scan.py out.json
```

### Before/after harness for a server-side change

`reports/php-switch-check.py` — 14 probes against the live site, each standing
in for a specific risk (`sitemap.xml` for `ext-xml`, Persian search for
`ext-mbstring`, and so on). It normalises CSRF tokens, the live clock and
cache-busting query strings out of the body before hashing, so two runs are
comparable. Built for the PHP switch; reusable for anything server-side.

```bash
cd reports
python3 php-switch-check.py before.json     # then make the change
python3 php-switch-check.py after.json
python3 php-switch-check.py --diff before.json after.json
```

`reports/php74-baseline.json` is the 7.4 baseline — all 14 green, 2026-08-07.

Two notes, both learned by getting them wrong first:

- **`/news` answers 410 on purpose** and the probe records 410 as its expected
  status. Scored as a failure it drowns the run in a false alarm.
- **`/api/category-search/سیم` returns `[]` on a perfectly healthy site.** The
  controller returns only leaf categories, so a parent's name matches the
  `LIKE` and is then filtered straight back out. The probe uses `حصاری`.
  A probe that returns empty when everything works proves nothing.

### Browser verification harness

`reports/` carries the scripts used this session. They need a venv with
playwright (`~/.cache/ms-playwright` already has chromium):

```bash
python3 -m venv .venv && .venv/bin/pip install playwright pypdf pillow
```

- `audit.py` — the full 8-page × 2-device measurement (fonts, tap targets,
  contrast, CLS/LCP/TTFB, headings, forms, landmarks).
- `post-deploy.json`, `functional.json` — the numbers this handoff quotes.

Two lessons about that harness, both of which produced false alarms:

- **`window.jQuery` is undefined on purpose.** ProvidePlugin injects `$` into
  modules; it does not create a global. Asserting on the global reports a
  failure that is not one. Test the *feature* (does the slider have slides,
  does search return suggestions).
- **Playwright's `type()` does not emit `keyup` for Persian text.** Live search
  looked broken and was not. Set `.value` and dispatch a real `KeyboardEvent`
  instead.

---

## 11. Measurement is still blind

Unchanged and still the highest-value unblock: **no Search Console and no GA4
access for this domain.** Everything in the reports is lab, not field.

Analytics is now one GA4 property configured in `config/brand.php`
(`analytics.ga4`) instead of two hard-coded ones fighting each other, and
Histats is gone. If `G-FPYB89P985` turns out to be the property the owner can
actually reach, swap the value there — do not add it back alongside.

---

## 12. Commit log, 2026-08-06/07

`327a77c4` → `3b0c0ce4`. All on `main`. `3b0c0ce4` is pushed but **not yet
deployed**.

| Commit | What |
|---|---|
| `edb4c0cf` | Waves 1–3: typography, price cards, auth screens, vendor bundle, security, caching, tests |
| `44d87e94` | The font preload that 404'd, auth text size, card labels |
| `e9b4c2cf` | Wave 4: Product/Offer/ItemList structured data |
| `d147bcda` | The mobile header and menu regressions from `edb4c0cf` |
| `3b0c0ce4` | The columns `/price` needs for its ItemList |
| `348fd360` | The PHP 8.1 probe and its diff tool. `tests/` only — not in the release tree, so it cannot reach the site. Pushed to carry `3b0c0ce4` out with it |
| `aa307c38` | Why the deploy pipeline stalls, and three fixes plus a 30-minute bound. §7.1 |
| `4dbec17a` | Every deploy now prints the server's PHP version and refuses an 8.x vendor tree on a 7.4 server. The only place that version is visible at all |

---

## 13. The duplicate site on emaratnews.ir — 2026-08-08

### What was wrong

The entire site was being served on **`emaratnews.ir`**. Not a scraped mirror —
the application itself, answering on that hostname: `/`, `/price` and `/blog`
all 200, and because Laravel builds every URL from the request host, the copy
rewrote its own internal links, assets, logo and `og:url` onto `emaratnews.ir`
and linked to itself all the way down. A complete second crawlable site
competing with our own domain for the same Persian keywords.

### Where it came from

Two independent facts had to meet, and both were already true:

1. **`emaratnews.ir` points at our server.** Its `A` record is
   `193.35.230.10` — our origin — and its SPF record names the same IP
   (`v=spf1 +a +mx +ip4:193.35.230.10 ~all`), so it is a leftover of this
   hosting account, not a stranger aiming a domain at us. Its nameservers are
   `cr1/cr2.7hostir.com`, the same host as the `cr2.7hostir.com` sitemap the
   original audit reported.
2. **The vhost is a catch-all and Laravel accepted any Host.** A request to
   `193.35.230.10` carrying a hostname nobody ever configured still gets the
   full site, 200. `App\Http\Middleware\TrustHosts` was commented out of the
   HTTP kernel, so nothing at the PHP layer objected either.

`sepahanfelez.ir` itself resolves to `185.88.177.22`, a CDN in front of that
origin (`server: api server`). The CDN forwards `Host: sepahanfelez.ir`
correctly — that is why the canonical domain was never affected.

**This is the same root cause as the poisoned sitemap on 2026-08-06**, where
all 58 entries were found pointing at `emaratnews.ir`. That was fixed by making
`Sitemap::url()` read `config/brand.php` instead of the request host. The host
itself was never closed, so the bug simply reappeared somewhere else.

### Why it was not worse

`rel=canonical`, `og:url`, `robots.txt` and `sitemap.xml` all read
`config/brand.php` rather than the request, so even on `emaratnews.ir` they
named `sepahanfelez.ir`. That is the only reason this stayed a
duplicate-content problem instead of a lost-domain one.

### The fix — `092237cb`, corrected by `7d0416ed`

**`public_html/.htaccess`, canonical-host block at the top.** Any host that is
not `sepahanfelez.ir` gets **410 Gone**.

**`092237cb` first shipped this as a 301 to `sepahanfelez.ir`, and that was
wrong.** The rule has to be host-blind — we are the catch-all SSL vhost on a
shared server, so hostnames belonging to *other accounts* land here too — and a
301 aimed every one of them at our domain. Visiting `emaratnews.ir` sent you to
`sepahanfelez.ir`. Closing our own leak is not a licence to capture someone
else's traffic, and the owner caught it within the hour. `7d0416ed` replaced it
with a refusal.

- **410, not a redirect.** It is the only response correct for every host at
  once: our content stops existing anywhere but our own domain, and nobody
  else's visitors are taken. **Do not turn this back into a redirect** — the
  rule cannot know whose hostname it is looking at.
- **410, not 404.** "Permanently gone" is both true and the stronger
  de-indexing signal for the duplicate URLs.
- Host-blind, so every other domain aimed at this server is covered without
  anyone having to discover it first. `cr1.7hostir.com` and `cr2.7hostir.com`
  were serving the site too and are covered by the same line.
- **The one redirect left** is `www.sepahanfelez.ir` → apex. Our own hostname,
  plain canonicalisation, takes over nobody. It is NXDOMAIN today; the rule
  exists so that adding the record later cannot silently 410 us.
- **`/.well-known/` is exempt and must stay exempt.** cPanel's AutoSSL
  validates renewals over plain HTTP on the hostname being certified; refusing
  there fails the challenge and eventually expires the certificate.

What this gives up is the consolidation a 301 would have handed the duplicate's
accumulated signal. That was never worth much — `canonical`, `og:url`,
`robots.txt` and the sitemap on the duplicate all already named
`sepahanfelez.ir` — and it is not worth redirecting a stranger's domain for.

**`App\Http\Middleware\TrustHosts` back in the kernel** as the backstop for
when `.htaccess` is not in play — a rewrite module that fails to load, an
`.htaccess` lost to a restore or a hand-edit on the server. It reads the
allowlist from `config/brand.php`, **not** `APP_URL`, which is
`http://localhost` in the checked-in `.env`. The framework disables it when
`APP_ENV=local` or under phpunit, so it constrains production and nothing else.

### Verified

Against a real Apache in a container before pushing, and against the live site
after:

| | |
|---|---|
| `sepahanfelez.ir` `/`, `/price`, `/blog`, `/login`, assets, sitemap, robots | 200, unchanged, ~1.0s |
| `/cart` | 302 to `/login`, as before |
| canonical + `og:url` on `/price` | still `https://sepahanfelez.ir/price` |
| `emaratnews.ir` — every path tried | **410**, empty `Location` |
| `cr1`/`cr2.7hostir.com`, unknown hosts, bare IP | **410**, empty `Location` |
| the 410 body | Apache's own page — none of our content in it |
| `www.sepahanfelez.ir` | 301 to the apex, the only redirect in the file |
| ACME challenge path | 200, not refused |
| phpunit | 34/34 |

Both deploys landed in about a minute — the pipeline did not stall this time.

### Still open — needs the owner, not the code

1. **Search Console.** The 410 is what Google needs, but it only acts on
   recrawl. If `emaratnews.ir` URLs are in the index, the removal tool on that
   property is the fast path. Nothing here can be done without property access
   (§9 already lists Search Console as blocked).
2. **The hosting fault is not ours to fix, and the 410 does not fix it.** Our
   account is the catch-all SSL vhost on that server: any domain pointed at
   `193.35.230.10` without its own certificate lands on us, and now gets a 410
   from us. Note that `http://emaratnews.ir` (port 80) is answered by a
   *WordPress* site — `x-redirect-by: WordPress` — so that hostname does have
   its own account for HTTP and only falls through to us on HTTPS. The
   certificate served on 443 is `mnec.ir`, a third account, expired in 2024.
   Only 7hostir can make those hostnames reach their own accounts; all we can
   do from inside our docroot is stop answering for them.
3. **Ask why `emaratnews.ir` is aimed at this server at all.** If it belongs
   to the owner, removing the DNS record is the clean fix and the redirect
   becomes belt-and-braces.
