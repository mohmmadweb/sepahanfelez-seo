"""Shared helpers: HTTP, Persian text normalisation, Jalali dates, JSON IO."""

import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timezone, timedelta

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config")
DATA = os.path.join(ROOT, "data")
TEHRAN = timezone(timedelta(hours=3, minutes=30))

UA = ("Mozilla/5.0 (compatible; SepahanFelezSEO/1.0; +https://sepahanfelezseo.lenzit.ir) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

_session = None


def session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": UA, "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.5"})
    return _session


def fetch(url, timeout=25, allow_redirects=True, method="GET"):
    """Return (response | None, error | None, seconds)."""
    t0 = time.monotonic()
    try:
        r = session().request(method, url, timeout=timeout, allow_redirects=allow_redirects)
        return r, None, round(time.monotonic() - t0, 3)
    except requests.RequestException as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:160]}", round(time.monotonic() - t0, 3)


def now_tehran():
    return datetime.now(TEHRAN)


def today_str():
    return now_tehran().date().isoformat()


def jalali(d=None, fmt="%Y/%m/%d"):
    import jdatetime
    d = d or now_tehran().date()
    if isinstance(d, str):
        d = datetime.fromisoformat(d).date()
    return jdatetime.date.fromgregorian(date=d).strftime(fmt)


_AR = str.maketrans({"ي": "ی", "ك": "ک", "ة": "ه", "‌": " ", "‏": "", "‎": ""})
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def norm(text):
    """Normalise Persian text for matching: Arabic letters, ZWNJ, digits, spacing."""
    if not text:
        return ""
    t = text.translate(_AR).translate(_FA_DIGITS).lower()
    t = t.replace("-", " ").replace("_", " ")
    return re.sub(r"\s+", " ", t).strip()


def decode_url(url):
    return urllib.parse.unquote(url)


def canon_url(url):
    """Comparable form of a URL: decoded, no fragment, no trailing slash (except root)."""
    p = urllib.parse.urlsplit(urllib.parse.unquote(url.strip()))
    path = p.path.rstrip("/") or ""
    return urllib.parse.urlunsplit((p.scheme or "https", p.netloc.lower(), path, p.query, ""))


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def config(name, default=None):
    return read_json(os.path.join(CONFIG, name), default)
