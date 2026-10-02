"""
Product photos from the owner's Drive (folder per category) → data/photos/<category slug>/.

Folder names on Drive are free text («توری مرغی», «Chicken wire», «سیم خاردار حلقوی»…), so
each is matched to a site category by its words; anything that does not match lands in
data/photos/_unmatched/<folder> and shows up in the dashboard for a manual decision.
"""

import json
import os
import subprocess

from .util import DATA, norm, now_tehran, write_json

PHOTOS = os.path.join(DATA, "photos")
CATEGORIES = {
    "توری-مرغی": ["مرغی", "chicken", "poultry"],
    "توری-جوشی--گالوانیزه-رول": ["جوشی رول", "ریزبافت", "جوشی گالوانیزه", "welded roll"],
    "توری-پرسی": ["پرسی", "woven", "crimped"],
    "مش-جوشی-یا-مش-آهنی": ["مش", "mesh"],
    "توری-حصاری": ["حصاری", "فنس", "fence", "chain"],
    "توری-گابیون": ["گابیون", "gabion"],
    "مفتول-گالوانیزه": ["مفتول گالوانیزه", "سیم گالوانیزه", "رابیتس", "اسکوپ", "galvanized wire"],
    "سیم-خاردار": ["خاردار", "barbed", "razor"],
    "توری-فرنگی": ["فرنگی", "خرگوشی"],
    "سیم-سیاه-و-آرماتور-بندی": ["آرماتور", "سیاه", "annealed", "black wire"],
    "توری-کششی(expanded-metal)": ["کششی", "لوزی", "expanded"],
}
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")


def match(folder):
    n = norm(folder)
    best, score = None, 0
    for slug, words in CATEGORIES.items():
        s = sum(len(w) for w in words if norm(w) in n)
        if s > score:
            best, score = slug, s
    return best


def sync(log=print):
    remote = os.environ.get("DRIVE_PHOTOS_REMOTE", "gdrive-sf:")
    folder = os.environ.get("DRIVE_PRODUCTS_FOLDER_ID")
    if not folder:
        return {"status": "blocked", "reason": "DRIVE_PRODUCTS_FOLDER_ID در .env خالی است"}
    base = ["rclone", "--drive-root-folder-id", folder]
    ls = subprocess.run(base + ["lsjson", "--dirs-only", remote], capture_output=True, text=True, timeout=120)
    if ls.returncode != 0:
        return {"status": "blocked", "reason": "درایو وصل نیست یا پوشه در دسترس نیست — از تب اتصالات «اتصال گوگل درایو» را بزنید",
                "detail": ls.stderr[-200:]}
    folders = json.loads(ls.stdout or "[]")
    report = []
    for f in folders:
        slug = match(f["Name"])
        dest = os.path.join(PHOTOS, slug or os.path.join("_unmatched", f["Name"]))
        os.makedirs(dest, exist_ok=True)
        r = subprocess.run(base + ["copy", f"{remote}{f['Name']}", dest, "--max-depth", "2",
                                   "--include", "*.{jpg,jpeg,png,webp,JPG,JPEG,PNG,WEBP}", "--transfers", "4"],
                           capture_output=True, text=True, timeout=1800)
        n = sum(1 for x in os.listdir(dest) if x.lower().endswith(IMAGE_EXT))
        report.append({"folder": f["Name"], "category": slug, "photos": n, "ok": r.returncode == 0})
        log(f"  {f['Name']} → {slug or 'نامشخص'} ({n} عکس)")
    out = {"status": "ok", "synced_at": now_tehran().isoformat(timespec="seconds"), "folders": report}
    write_json(os.path.join(DATA, "latest", "drive.json"), out)
    return out


def library():
    """{slug: [files]} from synced Drive photos (empty dict if nothing synced yet)."""
    lib = {}
    if os.path.isdir(PHOTOS):
        for slug in os.listdir(PHOTOS):
            d = os.path.join(PHOTOS, slug)
            if slug.startswith("_") or not os.path.isdir(d):
                continue
            files = sorted(x for x in os.listdir(d) if x.lower().endswith(IMAGE_EXT))
            if files:
                lib[slug] = files
    return lib
