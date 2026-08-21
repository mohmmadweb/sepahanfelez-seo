#!/usr/bin/env python3
"""Log in to sepahanfelez.ir as the owner.

Login is phone + a 6-digit SMS code that is valid for two minutes, so this runs
in two steps:

    admin_login.py request 09928639836     # sends the SMS
    admin_login.py verify  123456          # completes the login

Cookies persist in cookies.json between the two.
"""
import json
import os
import re
import sys

import requests

BASE = "https://sepahanfelez.ir"
JAR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.json")

s = requests.Session()
s.headers["User-Agent"] = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def load():
    if os.path.exists(JAR):
        for k, v in json.load(open(JAR)).items():
            s.cookies.set(k, v, domain="sepahanfelez.ir")


def save():
    json.dump(s.cookies.get_dict(), open(JAR, "w"))


def token(html):
    m = re.search(r'name="_token"\s+value="([^"]+)"', html)
    if not m:
        m = re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
    return m.group(1) if m else None


def errors(html):
    return re.findall(r'<(?:small|div|li)[^>]*(?:danger|invalid|error)[^>]*>\s*(.*?)\s*</', html)


def request_code(mobile):
    r = s.get(f"{BASE}/login", timeout=40)
    t = token(r.text)
    print("GET /login", r.status_code, "csrf", "ok" if t else "MISSING")

    r = s.post(f"{BASE}/submit-phone", data={"_token": t, "mobile": mobile},
               timeout=60, allow_redirects=True)
    save()
    print("POST /submit-phone ->", r.status_code, r.url)
    if "verify-phone" in r.url:
        print("\nSMS sent. Send me the 6-digit code, then run: verify <code>")
    else:
        print("\nDid not reach the verify step. Messages on the page:")
        for e in errors(r.text)[:6]:
            print("  ", re.sub(r"<[^>]+>", "", e)[:200])


def verify(code):
    load()
    r = s.get(f"{BASE}/verify-phone", timeout=40)
    t = token(r.text)
    print("GET /verify-phone", r.status_code, "csrf", "ok" if t else "MISSING")
    if "verify" not in r.url:
        print("  redirected to", r.url, "- the session was lost, request a new code")
        return

    r = s.post(f"{BASE}/verify-phone", data={"_token": t, "code": code},
               timeout=90, allow_redirects=True)
    save()
    print("POST /verify-phone ->", r.status_code, r.url)
    for e in errors(r.text)[:6]:
        txt = re.sub(r"<[^>]+>", "", e).strip()
        if txt:
            print("   msg:", txt[:200])

    a = s.get(f"{BASE}/admin", timeout=60, allow_redirects=True)
    print("GET /admin ->", a.status_code, a.url, len(a.content), "bytes")
    if "/login" in a.url:
        print("   not authenticated")
    else:
        m = re.search(r"<title>(.*?)</title>", a.text, re.S)
        print("   title:", (m.group(1).strip()[:120] if m else "?"))
        save()


if __name__ == "__main__":
    load()
    if sys.argv[1] == "request":
        request_code(sys.argv[2])
    elif sys.argv[1] == "verify":
        verify(sys.argv[2])
    elif sys.argv[1] == "check":
        a = s.get(f"{BASE}/admin", timeout=60, allow_redirects=True)
        print("GET /admin ->", a.status_code, a.url, len(a.content), "bytes")
