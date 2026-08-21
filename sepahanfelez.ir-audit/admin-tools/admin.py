#!/usr/bin/env python3
"""Read and edit sepahanfelez.ir through its admin panel.

Every controller here re-saves the whole form, so a partial POST would blank
whatever it left out. `submit()` therefore always reads the form first, keeps
every field exactly as it was, and changes only the keys it is asked to.
"""
import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

BASE = "https://sepahanfelez.ir"
HERE = os.path.dirname(os.path.abspath(__file__))
JAR = os.path.join(HERE, "cookies.json")

s = requests.Session()
s.headers["User-Agent"] = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
if os.path.exists(JAR):
    for k, v in json.load(open(JAR)).items():
        s.cookies.set(k, v, domain="sepahanfelez.ir")


def save_cookies():
    json.dump(s.cookies.get_dict(), open(JAR, "w"))


def get(path):
    r = s.get(BASE + path, timeout=90)
    save_cookies()
    if "/login" in r.url:
        raise SystemExit("session expired - log in again")
    return r


def soup(path):
    return BeautifulSoup(get(path).text, "html.parser")


def read_form(path, form_selector=None):
    """Return (action, method, fields) for a form on an admin page."""
    d = soup(path)
    form = d.select_one(form_selector) if form_selector else None
    if form is None:
        forms = [f for f in d.find_all("form") if f.find("input", {"name": "_token"})]
        if not forms:
            raise SystemExit(f"no token-bearing form on {path}")
        form = max(forms, key=lambda f: len(f.find_all(["input", "textarea", "select"])))

    fields = {}
    for el in form.find_all(["input", "textarea", "select"]):
        name = el.get("name")
        if not name:
            continue
        if el.name == "input":
            t = (el.get("type") or "text").lower()
            if t in ("submit", "button", "file", "image", "reset"):
                continue
            if t in ("checkbox", "radio"):
                if el.has_attr("checked"):
                    fields[name] = el.get("value", "on")
                fields.setdefault(name, fields.get(name))
                continue
            fields[name] = el.get("value", "")
        elif el.name == "textarea":
            fields[name] = el.text
        else:
            opt = el.find("option", selected=True) or el.find("option")
            fields[name] = opt.get("value", "") if opt else ""

    action = form.get("action") or (BASE + path)
    method = fields.get("_method", form.get("method", "post")).upper()
    return action, method, fields


def submit(path, changes, form_selector=None, dry=True):
    action, method, fields = read_form(path, form_selector)

    before = {k: fields.get(k) for k in changes}
    fields = {k: ("" if v is None else v) for k, v in fields.items()}
    fields.update(changes)

    print(f"\n  {path}")
    for k, v in changes.items():
        b = before.get(k)
        b = (b[:70] + "…") if isinstance(b, str) and len(b) > 70 else b
        n = (v[:70] + "…") if isinstance(v, str) and len(v) > 70 else v
        print(f"    {k}:  {b!r}  ->  {n!r}")
    if dry:
        print("    [dry run]")
        return None

    r = s.post(action, data=fields, timeout=120, allow_redirects=True)
    save_cookies()
    print(f"    POST {action} -> {r.status_code} {r.url}")
    errs = re.findall(r'<small class="text-danger">\s*(.*?)\s*</small>', r.text, re.S)
    for e in errs[:5]:
        print("    ERROR:", re.sub(r"<[^>]+>", "", e).strip()[:200])
    return r


def dump_form(path, keys=None):
    _, _, fields = read_form(path)
    print(f"\n=== {path} ===")
    for k, v in fields.items():
        if k in ("_token", "_method"):
            continue
        if keys and k not in keys:
            continue
        v = "" if v is None else str(v)
        flag = ""
        low = v.lower()
        if "ahanamn" in low or "آهن امن" in v or "sepahanfelez.com" in low:
            flag = "   <-- LEGACY"
        print(f"  {k:26s} = {v[:110]!r}{flag}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        dump_form(p)
