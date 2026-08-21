#!/usr/bin/env python3
"""Clear the old brand out of the article records.

Same approach as the categories: drive the real form in a browser so it
serialises exactly what a human clicking Save would send. `body` is a CKEditor
field — it is deliberately left untouched, and submitting the form
programmatically bypasses CKEditor's sync hook, so the textarea posts back the
value the server rendered, unchanged.

    fix_articles.py plan | apply
"""
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

BASE = "https://sepahanfelez.ir"
HERE = os.path.dirname(os.path.abspath(__file__))

NAME_FA = re.compile(r"آهن[\s‌]*امن")
LEGACY_URL = re.compile(r"https?://(?:www\.)?ahanamn\.(?:com|org)[^\s\"'<>]*", re.I)
PLACEHOLDER = re.compile(r'"\s*\[[^\]"]{3,}\]\s*"')


def is_legacy(v):
    if not isinstance(v, str):
        return False
    low = v.lower()
    return ("ahanamn" in low or NAME_FA.search(v) or "sepahanfelez.com" in low
            or "cr2.7hostir" in low or PLACEHOLDER.search(v))


def clean(v):
    v = NAME_FA.sub("سپاهان فلز", v or "")
    v = LEGACY_URL.sub("https://sepahanfelez.ir", v)
    return v.replace("sepahanfelez.com", "sepahanfelez.ir")


def run(dry):
    ids = json.load(open(os.path.join(HERE, "articles.json")))
    done = 0
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1500, "height": 1000})
        ctx.add_cookies([{"name": k, "value": v, "domain": "sepahanfelez.ir", "path": "/"}
                         for k, v in json.load(open(os.path.join(HERE, "cookies.json"))).items()])
        pg = ctx.new_page()

        for aid in ids:
            path = f"{BASE}/admin/article/{aid}/edit"
            pg.goto(path, wait_until="domcontentloaded", timeout=120000)
            if "/login" in pg.url:
                raise SystemExit("session expired")

            def val(name):
                el = pg.query_selector(f'[name="{name}"]')
                return None if el is None else el.input_value()

            upd = {}
            for name in ("canonical", "schema_tag"):
                v = val(name)
                if v and v.strip() and is_legacy(v):
                    upd[name] = ""            # the app generates both correctly now
            for name in ("meta_title", "meta_description"):
                v = val(name)
                if v and v.strip() and is_legacy(v):
                    upd[name] = clean(v)

            if not upd:
                continue

            title = (val("title") or "")[:38]
            print(f"  article {aid} — {title}")
            for k, v in upd.items():
                old = val(k)
                print(f"      {k}: {old[:62]!r}\n              -> {v[:62]!r}")
            if dry:
                done += 1
                continue

            for k, v in upd.items():
                pg.eval_on_selector(f'[name="{k}"]', """(el, v) => {
                    el.value = v;
                    el.dispatchEvent(new Event('input',  {bubbles:true}));
                    el.dispatchEvent(new Event('change', {bubbles:true}));
                }""", v)

            form = pg.query_selector(f'[name="{list(upd)[0]}"]').evaluate_handle(
                "e => e.form").as_element()
            with pg.expect_navigation(wait_until="domcontentloaded", timeout=120000):
                pg.evaluate("f => f.submit()", form)
            pg.wait_for_timeout(300)
            try:
                errs = pg.eval_on_selector_all(
                    ".text-danger, .alert-danger",
                    "e => e.map(x => x.textContent.trim()).filter(Boolean).slice(0,3)")
                if errs:
                    print("      VALIDATION:", errs)
            except Exception:
                pass
            done += 1

        print(f"\n{'would change' if dry else 'changed'}: {done} article(s)")
        ctx.close()
        b.close()


if __name__ == "__main__":
    run(dry=(len(sys.argv) < 2 or sys.argv[1] != "apply"))
