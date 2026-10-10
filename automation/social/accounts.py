"""
Accounts: any number of accounts per network, added and removed from the dashboard.

  registry  automation/sessions/accounts.json (chmod 600, gitignored): id, net, label, phone /
            username, default flag. Not secret, but private.
  secrets   in .env as SF_ACCT_<ID>_PASSWORD / _TOTP / _PROXY (Instagram); nothing secret in the registry.
  session   automation/sessions/<net>/<id>/ — browser profile, Telegram .session, Instagram device,
            LinkedIn token. Deleting an account deletes this folder and its .env lines.

The first load migrates the single-account setup (phones in .env, sessions/<net>/) into the registry.
"""

import json
import os
import re
import secrets
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SESSIONS = os.path.join(ROOT, "automation", "sessions")
REG = os.path.join(SESSIONS, "accounts.json")
sys.path.insert(0, os.path.join(ROOT, "dashboard"))
from sf.env import get  # noqa: E402

NETS = {"telegram": "تلگرام", "instagram": "اینستاگرام", "linkedin": "لینکدین", "bale": "بله",
        "eitaa": "ایتا", "rubika": "روبیکا", "whatsapp": "واتساپ"}
NEEDS = {"telegram": ["phone"], "bale": ["phone"], "eitaa": ["phone"], "rubika": ["phone"], "whatsapp": ["phone"],
         "instagram": ["username", "password"], "linkedin": []}
SECRET_FIELDS = ("password", "totp", "proxy")
LEGACY_PHONE = {"telegram": "TELEGRAM_PHONE", "bale": "BALE_PHONE", "eitaa": "EITAA_PHONE", "rubika": "RUBIKA_PHONE",
                "whatsapp": "WHATSAPP_PHONE"}


def _norm_phone(p):
    d = re.sub(r"\D", "", p or "")
    if d.startswith("0098"):
        d = d[4:]
    elif d.startswith("98"):
        d = d[2:]
    d = d.lstrip("0")
    if not re.fullmatch(r"9\d{9}", d):
        raise ValueError("شماره‌ی موبایل ایران به شکل ۰۹۱۲۳۴۵۶۷۸۹ لازم است.")
    return "+98" + d


def _save(rows):
    os.makedirs(SESSIONS, mode=0o700, exist_ok=True)
    tmp = REG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, REG)


def _migrate():
    rows = []
    for net, var in LEGACY_PHONE.items():
        if get(var):
            rows.append({"id": f"{net[:2]}{secrets.token_hex(3)}", "net": net, "label": "حساب اصلی",
                         "phone": _norm_phone(get(var)), "default": True, "created": time.time(), "migrated": True})
    if get("INSTAGRAM_USERNAME"):
        rows.append({"id": f"in{secrets.token_hex(3)}", "net": "instagram", "label": "حساب اصلی",
                     "username": get("INSTAGRAM_USERNAME").lstrip("@"), "default": True, "created": time.time(), "migrated": True,
                     "legacy_secrets": True})
    # old single-account session folders → the migrated account's folder
    for r in rows:
        old = os.path.join(SESSIONS, r["net"])
        if os.path.isdir(old):
            new = os.path.join(old, r["id"])
            os.makedirs(new, mode=0o700, exist_ok=True)
            for f in os.listdir(old):
                src = os.path.join(old, f)
                if src != new and not re.fullmatch(r"[a-z]{2}[0-9a-f]{6}", f):
                    shutil.move(src, os.path.join(new, f))
    _save(rows)
    return rows


def load():
    if not os.path.exists(REG):
        return _migrate()
    with open(REG, encoding="utf-8") as fh:
        return json.load(fh)


def get_account(acct_id):
    return next((a for a in load() if a["id"] == acct_id), None)


def for_net(net):
    return [a for a in load() if a["net"] == net]


def default(net):
    rows = for_net(net)
    return next((a for a in rows if a.get("default")), rows[0] if rows else None)


def secret(acct, field):
    """Instagram password/TOTP/proxy of this account from .env (migrated account falls back to the old names)."""
    v = get(f"SF_ACCT_{acct['id'].upper()}_{field.upper()}")
    if not v and acct.get("legacy_secrets"):
        v = get({"password": "INSTAGRAM_PASSWORD", "totp": "INSTAGRAM_TOTP_SECRET", "proxy": "INSTAGRAM_PROXY"}[field])
    return v


def session_dir(acct):
    d = os.path.join(SESSIONS, acct["net"], acct["id"])
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def add(net, label="", phone=None, username=None, password=None, totp=None, proxy=None):
    from dashboard_env import set_secrets
    if net not in NETS:
        raise ValueError("شبکه‌ی ناشناخته")
    rows = load()
    row = {"id": f"{net[:2]}{secrets.token_hex(3)}", "net": net, "label": (label or "").strip()[:40] or NETS[net],
           "created": time.time(), "default": not any(r["net"] == net for r in rows)}
    if "phone" in NEEDS[net]:
        row["phone"] = _norm_phone(phone)
        if any(r["net"] == net and r.get("phone") == row["phone"] for r in rows):
            raise ValueError("این شماره در این شبکه قبلاً اضافه شده است.")
    if net == "instagram":
        u = (username or "").strip().lstrip("@")
        if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", u):
            raise ValueError("نام کاربری اینستاگرام نامعتبر است.")
        if not password:
            raise ValueError("رمز اینستاگرام لازم است.")
        if any(r["net"] == net and r.get("username", "").lower() == u.lower() for r in rows):
            raise ValueError("این حساب اینستاگرام قبلاً اضافه شده است.")
        row["username"] = u
        set_secrets({f"SF_ACCT_{row['id'].upper()}_PASSWORD": password,
                     f"SF_ACCT_{row['id'].upper()}_TOTP": (totp or "").replace(" ", ""),
                     f"SF_ACCT_{row['id'].upper()}_PROXY": (proxy or "").strip()})
    rows.append(row)
    _save(rows)
    return row


def update_secrets(acct_id, password=None, totp=None, proxy=None):
    from dashboard_env import set_secrets
    a = get_account(acct_id)
    if not a or a["net"] != "instagram":
        raise ValueError("حساب پیدا نشد")
    ch = {}
    for k, v in (("PASSWORD", password), ("TOTP", totp), ("PROXY", proxy)):
        if v is not None and v != "":
            ch[f"SF_ACCT_{acct_id.upper()}_{k}"] = v.strip()
    if ch:
        set_secrets(ch)
    return sorted(ch)


def remove(acct_id):
    from dashboard_env import set_secrets
    rows = load()
    a = next((r for r in rows if r["id"] == acct_id), None)
    if not a:
        raise ValueError("حساب پیدا نشد")
    shutil.rmtree(os.path.join(SESSIONS, a["net"], a["id"]), ignore_errors=True)
    set_secrets({f"SF_ACCT_{acct_id.upper()}_{f.upper()}": "" for f in SECRET_FIELDS}, drop=True)
    rows = [r for r in rows if r["id"] != acct_id]
    if a.get("default"):
        nxt = next((r for r in rows if r["net"] == a["net"]), None)
        if nxt:
            nxt["default"] = True
    _save(rows)
    st_path = os.path.join(ROOT, "dashboard", "data", "social_status.json")
    if os.path.exists(st_path):
        with open(st_path, encoding="utf-8") as fh:
            st = json.load(fh)
        st.pop(acct_id, None)
        with open(st_path, "w", encoding="utf-8") as fh:
            json.dump(st, fh, ensure_ascii=False, indent=1)
    return a


def set_default(acct_id):
    rows = load()
    a = next((r for r in rows if r["id"] == acct_id), None)
    if not a:
        raise ValueError("حساب پیدا نشد")
    for r in rows:
        if r["net"] == a["net"]:
            r["default"] = r["id"] == acct_id
    _save(rows)
    return a


def public(a):
    """What the dashboard may show: no secrets, only whether they are set."""
    out = {k: a.get(k) for k in ("id", "net", "label", "phone", "username", "default", "created")}
    out["net_fa"] = NETS[a["net"]]
    if a["net"] == "instagram":
        out["has_password"] = bool(secret(a, "password"))
        out["has_totp"] = bool(secret(a, "totp"))
        out["has_proxy"] = bool(secret(a, "proxy"))
    return out
