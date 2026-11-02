"""
Photos from the owner's Drive folder → data/photos/<category slug>/, kept as an exact mirror.

The folder (DRIVE_PRODUCTS_FOLDER_ID in .env) is read with the project's service account, so no
Google login is needed: the owner shares the folder with the service account's e-mail as Viewer.
Every run lists the whole tree and compares it with the last run (data/photos/manifest.json):
  - a new or changed photo is downloaded;
  - a photo deleted on Drive is deleted here too, so the content plan stops using it.

Folder names are free text («توری مرغی», «Chicken wire», «عکس کارخانه»…) at any depth; a photo
belongs to the nearest folder above it whose name matches a category. «_factory» collects the
factory/production-line folders; «_docs» (old price lists, documents) and «_logo» are kept but never
used as content photos. Anything else lands in _unmatched/<folder> and is listed in the
dashboard for a decision.
"""

import os
import re

from .util import DATA, norm, now_tehran, read_json, write_json

PHOTOS = os.path.join(DATA, "photos")
MANIFEST = os.path.join(PHOTOS, "manifest.json")
CATEGORIES = {
    "توری-مرغی": ["مرغی", "chicken", "poultry"],
    "توری-جوشی-گالوانیزه-رول": ["جوشی رول", "ریزبافت", "جوشی گالوانیزه", "توری جوشی", "welded roll"],
    "توری-پرسی": ["پرسی", "woven", "crimped"],
    "مش-جوشی-یا-مش-آهنی": ["مش", "mesh"],
    "توری-حصاری": ["حصاری", "فنس", "fence", "chain"],
    "توری-گابیون": ["گابیون", "gabion"],
    "مفتول-گالوانیزه": ["مفتول گالوانیزه", "سیم گالوانیزه", "رابیتس", "اسکوپ", "گلخانه", "galvanized wire"],
    "سیم-خاردار": ["خاردار", "barbed", "razor"],
    "توری-فرنگی": ["فرنگی", "خرگوشی"],
    "سیم-سیاه-و-آرماتور-بندی": ["آرماتور", "سیاه", "annealed", "black wire"],
    "توری-کششی": ["کششی", "لوزی", "expanded"],
    "_factory": ["کارخانه", "خط تولید", "سوله", "تولید", "انبار", "بارگیری", "factory", "production"],
    "_logo": ["لوگو", "logo", "برند"],
    "_docs": ["document", "documents", "مدارک", "سند", "اسناد", "لیست قیمت", "price list"],
}
# never used as content photos: documents (old price lists with handwriting), logos, unmatched
NOT_CONTENT = ("_docs", "_logo", "_unmatched")
# the plan used the old slugs before the URL clean-up; keep reading photos synced under them
ALIASES = {"توری-جوشی--گالوانیزه-رول": "توری-جوشی-گالوانیزه-رول", "توری-کششی(expanded-metal)": "توری-کششی"}
IMAGE_MIME = ("image/jpeg", "image/png", "image/webp", "image/heic")
FOLDER = "application/vnd.google-apps.folder"


def match(name):
    n = norm(name)
    best, score = None, 0
    for slug, words in CATEGORIES.items():
        s = sum(len(w) for w in words if norm(w) in n)
        if s > score:
            best, score = slug, s
    return best


def _session():
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.path.expanduser("~/.config/claude-seo/service_account.json")
    creds = service_account.Credentials.from_service_account_file(path, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    return AuthorizedSession(creds), creds.service_account_email


def _children(s, folder_id):
    out, token = [], None
    while True:
        r = s.get("https://www.googleapis.com/drive/v3/files", timeout=60, params={
            "q": f"'{folder_id}' in parents and trashed = false", "pageSize": 1000, "pageToken": token,
            "fields": "nextPageToken, files(id, name, mimeType, md5Checksum, modifiedTime, size)",
            "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
        r.raise_for_status()
        j = r.json()
        out += j.get("files", [])
        token = j.get("nextPageToken")
        if not token:
            return out


def _walk(s, folder_id, trail=(), cat=None):
    """Yield (file, category or None, folder trail) for every image under folder_id."""
    for f in _children(s, folder_id):
        if f["mimeType"] == FOLDER:
            yield from _walk(s, f["id"], trail + (f["name"],), match(f["name"]) or cat)
        elif f["mimeType"] in IMAGE_MIME or f["name"].lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            yield f, cat, trail


def _local_name(f):
    base = re.sub(r"[\\/:*?\"<>|\s]+", "-", f["name"]).strip("-") or "photo"
    return f"{f['id'][:8]}-{base}"


def sync(log=print):
    folder = os.environ.get("DRIVE_PRODUCTS_FOLDER_ID")
    if not folder:
        return {"status": "blocked", "reason": "DRIVE_PRODUCTS_FOLDER_ID در .env خالی است"}
    try:
        s, email = _session()
        meta = s.get(f"https://www.googleapis.com/drive/v3/files/{folder}", params={"fields": "id,name", "supportsAllDrives": "true"}, timeout=60)
        if meta.status_code == 404:
            return {"status": "blocked", "reason": f"پوشه‌ی درایو با {email} به اشتراک گذاشته نشده (Share → Viewer)"}
        meta.raise_for_status()
        files = list(_walk(s, folder))
    except Exception as exc:                                           # noqa: BLE001
        return {"status": "blocked", "reason": f"درایو در دسترس نیست: {type(exc).__name__}: {str(exc)[:160]}"}

    old = read_json(MANIFEST, {}) or {}
    new, added, changed, removed = {}, 0, 0, 0
    for f, cat, trail in files:
        sub = cat or os.path.join("_unmatched", "-".join(trail) or "root")
        rel = os.path.join(sub, _local_name(f))
        new[f["id"]] = {"path": rel, "md5": f.get("md5Checksum"), "modified": f.get("modifiedTime"),
                        "name": f["name"], "folder": "/".join(trail)}
        prev = old.get(f["id"])
        dest = os.path.join(PHOTOS, rel)
        if prev and prev["path"] != rel and os.path.exists(os.path.join(PHOTOS, prev["path"])):
            os.remove(os.path.join(PHOTOS, prev["path"]))                # moved to another folder on Drive
        if prev and prev.get("md5") == f.get("md5Checksum") and prev["path"] == rel and os.path.exists(dest):
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        r = s.get(f"https://www.googleapis.com/drive/v3/files/{f['id']}", params={"alt": "media", "supportsAllDrives": "true"}, timeout=300)
        if r.status_code != 200:
            log(f"  ✗ {f['name']}: HTTP {r.status_code}")
            new.pop(f["id"])
            continue
        with open(dest + ".part", "wb") as fh:
            fh.write(r.content)
        os.replace(dest + ".part", dest)
        if prev:
            changed += 1
        else:
            added += 1
    for fid, prev in old.items():
        if fid not in new:
            p = os.path.join(PHOTOS, prev["path"])
            if os.path.exists(p):
                os.remove(p)
            removed += 1
    for root, dirs, fs in os.walk(PHOTOS, topdown=False):              # drop folders left empty
        if root != PHOTOS and not os.listdir(root):
            os.rmdir(root)
    write_json(MANIFEST, new)
    counts = {}
    for v in new.values():
        k = v["path"].split(os.sep)[0]
        counts[k] = counts.get(k, 0) + 1
    unmatched = sorted({v["folder"] for v in new.values() if v["path"].startswith("_unmatched")})
    out = {"status": "ok", "synced_at": now_tehran().isoformat(timespec="seconds"), "folder": meta.json().get("name"),
           "photos": len(new), "added": added, "changed": changed, "removed": removed,
           "by_category": counts, "unmatched_folders": unmatched}
    write_json(os.path.join(DATA, "latest", "drive.json"), out)
    log(f"  {len(new)} عکس · {added} تازه · {changed} عوض‌شده · {removed} حذف‌شده")
    return out


def library():
    """{slug: [files]} from the synced Drive photos (empty dict if nothing synced yet)."""
    lib = {}
    if os.path.isdir(PHOTOS):
        for slug in os.listdir(PHOTOS):
            d = os.path.join(PHOTOS, slug)
            if slug.startswith(NOT_CONTENT) or not os.path.isdir(d):
                continue
            files = sorted(x for x in os.listdir(d) if not x.endswith(".part") and x.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
            if files:
                lib[slug] = files
    for old, new in ALIASES.items():
        if new in lib:
            lib.setdefault(old, lib[new])
    return lib
