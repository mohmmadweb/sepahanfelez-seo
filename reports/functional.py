"""
Functional smoke test of the live site.

A 200 says the server answered. It does not say the JavaScript ran, the vendor
bundle registered, the mobile menu opens, the price table reflowed into cards,
or the cart accepted anything. Those are the things that would actually be
"broken" after this deploy, and none of them show up in a status code.
"""
import asyncio, json
from playwright.async_api import async_playwright

BASE = "https://sepahanfelez.ir"
MOBILE = {"width": 375, "height": 812}
DESKTOP = {"width": 1440, "height": 900}
UA_M = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

results = {}


def note(key, ok, detail=""):
    results[key] = {"ok": bool(ok), "detail": detail}
    print(f"  {'PASS' if ok else 'FAIL'}  {key}" + (f"  — {detail}" if detail else ""), flush=True)


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=["--no-sandbox"])

        # ---------- 1. the vendor bundle actually registered ----------------
        ctx = await b.new_context(viewport=DESKTOP)
        pg = await ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
        await pg.goto(BASE + "/", wait_until="networkidle", timeout=60000)
        await pg.wait_for_timeout(2500)

        libs = await pg.evaluate("""() => ({
            jquery:    typeof window.jQuery !== 'undefined' && window.jQuery.fn ? window.jQuery.fn.jquery : null,
            bootstrap: typeof window.bootstrap !== 'undefined',
            slick:     !!(window.jQuery && window.jQuery.fn && window.jQuery.fn.slick),
            webpack:   typeof window.webpackChunk !== 'undefined' || typeof window.webpackJsonp !== 'undefined',
        })""")
        note("jQuery loaded from the shared vendor bundle", libs["jquery"], f"version {libs['jquery']}")
        note("Slick (the slider plugin) registered on jQuery", libs["slick"])
        note("no uncaught JS errors on the home page", len(errs) == 0, "; ".join(errs[:3]))

        # ---------- 2. the slider is alive --------------------------------
        slides = await pg.evaluate("""() => {
            const t = document.querySelector('.slick-track');
            return {initialised: !!t, count: document.querySelectorAll('.slick-slide').length};
        }""")
        note("home slider initialised", slides["initialised"], f"{slides['count']} slides")

        # ---------- 3. the clock actually ticks ---------------------------
        first = await pg.evaluate("() => (document.getElementById('time_counter2')||{}).textContent")
        await pg.wait_for_timeout(2200)
        second = await pg.evaluate("() => (document.getElementById('time_counter2')||{}).textContent")
        note("the live clock advances", bool(first) and bool(second) and first != second,
             f"{first!r} -> {second!r}")

        await pg.close()
        await ctx.close()

        # ---------- 4. mobile: the drawer opens ---------------------------
        ctx = await b.new_context(viewport=MOBILE, user_agent=UA_M)
        pg = await ctx.new_page()
        await pg.goto(BASE + "/", wait_until="networkidle", timeout=60000)
        await pg.wait_for_timeout(1800)

        before = await pg.evaluate("""() => {
            const m = document.getElementById('sideMenu');
            const cs = getComputedStyle(m);
            return {visibility: cs.visibility, transform: cs.transform};
        }""")
        await pg.click("#burger")
        await pg.wait_for_timeout(900)
        after = await pg.evaluate("""() => {
            const m = document.getElementById('sideMenu');
            const cs = getComputedStyle(m);
            const r = m.getBoundingClientRect();
            return {visibility: cs.visibility, onScreen: r.left < window.innerWidth - 10,
                    links: m.querySelectorAll('a').length};
        }""")
        note("mobile menu opens and is on screen",
             after["visibility"] == "visible" and after["onScreen"],
             f"visibility {before['visibility']} -> {after['visibility']}, {after['links']} links")

        # closing it again must not leave the page scrollable sideways
        close = await pg.query_selector("#closeBtn")
        if close:
            await close.click()
            await pg.wait_for_timeout(700)
        sw = await pg.evaluate("() => document.documentElement.scrollWidth")
        note("no horizontal scroll after closing the menu", sw <= 376, f"scrollWidth {sw}")

        # ---------- 5. the logo is present on mobile ----------------------
        logo = await pg.evaluate("""() => {
            const i = document.querySelector('header .logo');
            if (!i) return null;
            const r = i.getBoundingClientRect();
            return {w: Math.round(r.width), h: Math.round(r.height), src: (i.currentSrc||i.src).split('/').pop()};
        }""")
        note("brand mark visible in the mobile header", logo and logo["w"] > 0,
             f"{logo['w']}x{logo['h']} {logo['src']}" if logo else "not found")

        await pg.close()

        # ---------- 6. price table reflows into cards ---------------------
        pg = await ctx.new_page()
        await pg.goto(BASE + "/price", wait_until="networkidle", timeout=60000)
        await pg.wait_for_timeout(1500)
        cards = await pg.evaluate("""() => {
            const price = document.querySelector('td[data-label="قیمت لحظه ای"]');
            const buy = document.querySelector('td[data-label="خرید"] button, .buy-cell button');
            const vw = document.documentElement.clientWidth;
            const inView = el => { if (!el) return false; const r = el.getBoundingClientRect();
                                   return r.width > 0 && r.right <= vw + 2 && r.left >= -2; };
            return {
                rows: document.querySelectorAll('#price_diffrence_table tbody tr').length,
                priceVisible: inView(price),
                buyVisible: inView(buy),
                buyLabel: buy ? (buy.getAttribute('aria-label') || '').slice(0, 40) : null,
                labelShown: price ? getComputedStyle(price, '::before').content !== 'none' : false,
                scrollWidth: document.documentElement.scrollWidth,
            };
        }""")
        note("price rows render as cards with the price on screen",
             cards["priceVisible"] and cards["buyVisible"],
             f"{cards['rows']} rows, label shown: {cards['labelShown']}, scrollWidth {cards['scrollWidth']}")
        note("buy button carries an accessible name", bool(cards["buyLabel"]), cards["buyLabel"])

        # ---------- 7. add to cart still works -----------------------------
        cart = await pg.evaluate("""() => {
            const f = document.querySelector('td[data-label="خرید"] form, .buy-cell form');
            return f ? {action: f.action, method: f.method, hasToken: !!f.querySelector('input[name=_token]')} : null;
        }""")
        note("add-to-cart form is intact (action + CSRF token)",
             cart and cart["hasToken"] and "/cart/" in cart["action"],
             (cart or {}).get("action", "no form found"))

        await pg.close()

        # ---------- 8. the login page ------------------------------------
        pg = await ctx.new_page()
        lerrs = []
        pg.on("pageerror", lambda e: lerrs.append(str(e)[:120]))
        await pg.goto(BASE + "/login", wait_until="networkidle", timeout=60000)
        await pg.wait_for_timeout(1200)
        login = await pg.evaluate("""() => {
            const i = document.querySelector('input[name=mobile]');
            const l = i && i.id ? document.querySelector(`label[for="${i.id}"]`) : null;
            const btn = document.querySelector('.auth-submit');
            const img = document.querySelector('.brand-mark');
            return {
                field: !!i,
                label: l ? l.textContent.trim() : null,
                fontSize: i ? getComputedStyle(i).fontSize : null,
                bodySize: getComputedStyle(document.body).fontSize,
                button: btn ? Math.round(btn.getBoundingClientRect().height) : 0,
                logo: img ? (img.currentSrc || img.src).split('/').pop() : null,
                metronic: document.documentElement.innerHTML.includes('plugins.bundle'),
                weightKB: performance.getEntriesByType('resource')
                          .reduce((a, r) => a + (r.transferSize || 0), 0) / 1024,
            };
        }""")
        note("login form has a real label", bool(login["label"]), login["label"])
        note("login input clears the 16px iOS-zoom threshold",
             login["fontSize"] and float(login["fontSize"].replace("px", "")) >= 16, login["fontSize"])
        note("login submit is a 44px target", login["button"] >= 44, f"{login['button']}px")
        note("login no longer loads the admin theme", not login["metronic"],
             f"page weight {login['weightKB']:.0f} KB")
        note("login shows the Sepahan Felez mark", login["logo"] and "sepahanfelez" in login["logo"],
             login["logo"])
        note("no JS errors on the login page", len(lerrs) == 0, "; ".join(lerrs[:2]))

        await pg.close()
        await ctx.close()
        await b.close()

    json.dump(results, open("functional.json", "w"), ensure_ascii=False, indent=1)
    failed = [k for k, v in results.items() if not v["ok"]]
    print("\n" + ("ALL FUNCTIONAL CHECKS PASSED" if not failed
                  else f"{len(failed)} FAILED: " + ", ".join(failed)))

asyncio.run(main())
