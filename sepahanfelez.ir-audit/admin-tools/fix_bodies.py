#!/usr/bin/env python3
"""Clean the old brand out of the rich-text fields.

These are article and category bodies written by hand over years. They name
«آهن امن» in prose and, more importantly, link to ahanamn.com — a domain that
does not resolve, so every one of those internal links is dead for a visitor.
Rewriting only the host keeps the path, and the paths still exist here because
this site is a copy of that one; spot-checked, /blog/... returns 200.

The substitutions are exactly the ones ScrubLegacyBrand already applies at
render time, so nothing visible changes — this just moves the fix from the
response into the database.

`body` and `intro` are CKEditor 4 fields, and CKEditor patches `form.submit`
itself, so a programmatic submit still calls updateElement() and overwrites
anything written straight into the textarea. Verified on /admin/article/3/edit:
`form.submit` is not native. Those two fields therefore go through
CKEDITOR.instances[...].getData()/setData(); everything else is a plain input.

    fix_bodies.py plan | apply
"""
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

BASE = "https://sepahanfelez.ir"
HERE = os.path.dirname(os.path.abspath(__file__))

NAME_FA = re.compile(r"آهن[\s‌]*امن")
HOST = re.compile(r"https?://(?:www\.)?ahanamn\.(?:com|org)", re.I)
LATIN = re.compile(r"ahan([\s._\-]?)amn", re.I)

# Laravel's max: rules on the fields being touched.
LIMITS = {"description": 500, "meta_keywords": 191, "meta_description": 260,
          "meta_title": 170, "video": 500}

TEXT_FIELDS = ("body", "intro", "description", "meta_keywords",
               "meta_title", "meta_description")


def latin_sub(m):
    joined = m.group(1) == ""
    word = "sepahanfelez" if joined else "sepahan felez"
    if m.group(0).isupper():
        return word.upper()
    if m.group(0)[0].isupper():
        return "SepahanFelez" if joined else "Sepahan Felez"
    return word


def clean(v):
    v = NAME_FA.sub("سپاهان فلز", v)
    v = HOST.sub("https://sepahanfelez.ir", v)     # host only; path survives
    v = v.replace("sepahanfelez.com", "sepahanfelez.ir")
    return LATIN.sub(latin_sub, v)


def is_dirty(v):
    return isinstance(v, str) and clean(v) != v


def run(dry):
    targets = ([("category", i) for i in
                (34, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
                 18, 19, 20, 21, 22, 25, 26, 27, 28, 29)]
               + [("article", i) for i in json.load(open(os.path.join(HERE, "articles.json")))]
               + [("article-category", i) for i in (1, 2, 3, 4, 5, 7, 8, 9, 11, 12)])

    changed = skipped = 0
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1500, "height": 1000})
        ctx.add_cookies([{"name": k, "value": v, "domain": "sepahanfelez.ir", "path": "/"}
                         for k, v in json.load(open(os.path.join(HERE, "cookies.json"))).items()])
        pg = ctx.new_page()

        for kind, rid in targets:
            path = f"{BASE}/admin/{kind}/{rid}/edit"
            pg.goto(path, wait_until="domcontentloaded", timeout=120000)
            if "/login" in pg.url:
                raise SystemExit("session expired")

            pg.wait_for_timeout(1200)   # let CKEditor attach

            def raw(name):
                return pg.evaluate(
                    """n => {
                        if (typeof CKEDITOR !== 'undefined' && CKEDITOR.instances[n])
                            return CKEDITOR.instances[n].getData();
                        const e = document.querySelector(`[name="${n}"]`);
                        return e ? e.value : null;
                    }""", name)

            def write(name, value):
                pg.evaluate("""([n, v]) => {
                    if (typeof CKEDITOR !== 'undefined' && CKEDITOR.instances[n]) {
                        CKEDITOR.instances[n].setData(v);
                        CKEDITOR.instances[n].updateElement();
                        return;
                    }
                    const e = document.querySelector(`[name="${n}"]`);
                    e.value = v;
                    e.dispatchEvent(new Event('input',  {bubbles:true}));
                    e.dispatchEvent(new Event('change', {bubbles:true}));
                }""", [name, value])

            upd, notes = {}, []
            for name in TEXT_FIELDS:
                v = raw(name)
                if v is None or not is_dirty(v):
                    continue
                new = clean(v)
                lim = LIMITS.get(name)
                if lim and len(new) > lim:
                    notes.append(f"{name} would be {len(new)}/{lim} chars - SKIPPED")
                    continue
                upd[name] = new

            # A video hosted on the dead domain has no counterpart here
            # (/videos/... is 404), so point at nothing rather than at a 404.
            vid = raw("video")
            if vid and HOST.search(vid):
                upd["video"] = ""

            if not upd and not notes:
                continue

            title = (raw("title") or "")[:36]
            print(f"  {kind} {rid} — {title}")
            for n in notes:
                print(f"      ! {n}")
            for k, v in upd.items():
                old = raw(k)
                hits = len(NAME_FA.findall(old)) + len(HOST.findall(old)) + len(LATIN.findall(old))
                print(f"      {k}: {hits} occurrence(s), {len(old)} -> {len(v)} chars")
            if not upd:
                skipped += 1
                continue
            if dry:
                changed += 1
                continue

            for k, v in upd.items():
                write(k, v)
                back = raw(k)
                if back != v:
                    print(f"      ! {k}: write did not take ({len(back or '')} vs {len(v)})")

            form = pg.evaluate_handle(
                """n => document.querySelector(`[name="${n}"]`).form""",
                list(upd)[0]).as_element()
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
            changed += 1

        print(f"\n{'would change' if dry else 'changed'}: {changed}   "
              f"records with a field left alone: {skipped}")
        ctx.close()
        b.close()


if __name__ == "__main__":
    run(dry=(len(sys.argv) < 2 or sys.argv[1] != "apply"))
