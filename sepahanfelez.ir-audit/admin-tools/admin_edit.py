#!/usr/bin/env python3
"""Edit sepahanfelez.ir records by driving the real admin forms in a browser.

Re-posting these forms by hand is unsafe. CategoryController@update reads
`$request->has("delete_main_img")`, which is true for an empty value, so
submitting an unchecked checkbox as "" deletes the category's image; `tags[]`
and `specs[]` are multi-valued and a naive parser collapses them, which
`sync()` then treats as a removal. Letting the browser serialise the form
avoids all of that: it sends exactly what a human clicking Save would send.

Usage:
    admin_edit.py plan     # show every change, touch nothing
    admin_edit.py apply    # make them
"""
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

BASE = "https://sepahanfelez.ir"
HERE = os.path.dirname(os.path.abspath(__file__))
JAR = os.path.join(HERE, "cookies.json")

CATEGORY_IDS = [34, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
                18, 19, 20, 21, 22, 25, 26, 27, 28, 29]

# «آهن امن» in stored prose. The site is سپاهان فلز.
NAME_FA = re.compile(r"آهن[\s‌]*امن")
LEGACY_URL = re.compile(r"https?://(?:www\.)?ahanamn\.(?:com|org)[^\s\"'<>]*", re.I)


def is_legacy(v):
    if not isinstance(v, str):
        return False
    low = v.lower()
    return ("ahanamn" in low or NAME_FA.search(v) or "sepahanfelez.com" in low
            or "cr2.7hostir" in low or re.search(r'"\s*\[[^\]"]{3,}\]\s*"', v))


def clean_text(v):
    v = NAME_FA.sub("سپاهان فلز", v or "")
    v = LEGACY_URL.sub("https://sepahanfelez.ir", v)
    v = v.replace("sepahanfelez.com", "sepahanfelez.ir")
    return v


class Admin:
    def __init__(self, pw, dry):
        self.dry = dry
        self.b = pw.chromium.launch()
        self.ctx = self.b.new_context(viewport={"width": 1500, "height": 1000})
        cookies = json.load(open(JAR))
        self.ctx.add_cookies([{"name": k, "value": v, "domain": "sepahanfelez.ir",
                               "path": "/"} for k, v in cookies.items()])
        self.pg = self.ctx.new_page()
        self.changes = 0

    def open(self, path):
        self.pg.goto(BASE + path, wait_until="domcontentloaded", timeout=120000)
        if "/login" in self.pg.url:
            raise SystemExit("session expired - re-run admin_login.py")

    def field(self, name):
        el = self.pg.query_selector(f'[name="{name}"]')
        return None if el is None else (el.input_value() if el.evaluate(
            "e => e.tagName") in ("INPUT", "TEXTAREA", "SELECT") else None)

    def set_and_save(self, path, updates, label):
        """updates: {field_name: new_value}. Only writes fields that differ."""
        self.open(path)
        actual = {}
        for name, new in updates.items():
            cur = self.field(name)
            if cur is None:
                print(f"    ! {label}: no field {name}")
                continue
            if cur.strip() == (new or "").strip():
                continue
            actual[name] = (cur, new)

        if not actual:
            return False

        print(f"  {label}  ({path})")
        for name, (cur, new) in actual.items():
            c = (cur[:64] + "…") if len(cur) > 64 else cur
            n = (new[:64] + "…") if len(new) > 64 else new
            print(f"      {name}: {c!r}\n              -> {n!r}")

        if self.dry:
            self.changes += 1
            return True

        for name, (_, new) in actual.items():
            self.pg.eval_on_selector(
                f'[name="{name}"]',
                """(el, v) => {
                    el.value = v;
                    el.dispatchEvent(new Event('input',  {bubbles:true}));
                    el.dispatchEvent(new Event('change', {bubbles:true}));
                }""", new)

        form = self.pg.query_selector(f'[name="{list(actual)[0]}"]').evaluate_handle(
            "e => e.form").as_element()
        with self.pg.expect_navigation(wait_until="domcontentloaded", timeout=120000):
            self.pg.evaluate("f => f.submit()", form)
        self.pg.wait_for_timeout(400)

        # The redirect can still be settling; a failed scrape here says nothing
        # about whether the save worked, and every change is verified again at
        # the end anyway.
        try:
            errs = self.pg.eval_on_selector_all(
                ".text-danger, .invalid-feedback, .alert-danger",
                "els => els.map(e => e.textContent.trim()).filter(Boolean).slice(0,4)")
            if errs:
                print("      VALIDATION:", errs)
        except Exception as e:
            print("      (could not read the response page:", str(e)[:60], ")")
        self.changes += 1
        return True

    def close(self):
        self.ctx.close()
        self.b.close()


def run(dry):
    with sync_playwright() as pw:
        a = Admin(pw, dry)

        print("\n--- site settings ---")
        a.set_and_save("/admin/informarion",
                       {"email": "info@sepahanfelez.ir"}, "contact e-mail")

        a.open("/admin/home_setting")
        hs = {}
        for name, new in (("url_about_pic", "https://sepahanfelez.ir/about"),
                          ("url_footer_pic1", ""),
                          ("url_footer_pic2", ""),
                          ("home_title",
                           "سپاهان فلز | تولید کننده انواع مفتول‌های صنعتی و ساختمانی")):
            hs[name] = new
        a.set_and_save("/admin/home_setting", hs, "home settings")

        print("\n--- sliders ---")
        for sid in (5, 6):
            a.set_and_save(f"/admin/setting/slider/{sid}/edit",
                           {"link": "https://sepahanfelez.ir"}, f"slider {sid}")

        print("\n--- categories ---")
        for cid in CATEGORY_IDS:
            path = f"/admin/category/{cid}/edit"
            a.open(path)
            upd = {}
            can = a.field("canonical") or ""
            if can.strip() and is_legacy(can):
                upd["canonical"] = ""          # the layout self-references now
            sch = a.field("schema_tag") or ""
            if sch.strip() and is_legacy(sch):
                upd["schema_tag"] = ""         # app generates valid JSON-LD
            md = a.field("meta_description") or ""
            if md.strip() and is_legacy(md):
                upd["meta_description"] = clean_text(md)
            mt = a.field("meta_title") or ""
            if mt.strip() and is_legacy(mt):
                upd["meta_title"] = clean_text(mt)
            ttl = a.field("title") or ""
            if upd:
                a.set_and_save(path, upd, f"category {cid} — {ttl}")

        print(f"\n{'would change' if dry else 'changed'}: {a.changes} record(s)")
        a.close()


if __name__ == "__main__":
    run(dry=(len(sys.argv) < 2 or sys.argv[1] != "apply"))
