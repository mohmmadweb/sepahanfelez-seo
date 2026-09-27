"""
Server-side hand-offs: pull the encrypted Google bundle, publish the encrypted dashboard
to gh-pages, back up config + history (encrypted) to Drive.

Git pushes use the machine's stored credentials for the mohmmadweb account
(`-c credential.helper=store`); nothing here reads or prints a token.
"""

import os
import shutil
import subprocess
from datetime import date, timedelta

from . import vault
from .util import CONFIG, DATA, ROOT, now_tehran

REPO_DIR = os.path.dirname(ROOT)
REMOTE = "https://github.com/mohmmadweb/sepahanfelez-seo.git"
GIT_AUTH = ["-c", "credential.helper=", "-c", "credential.helper=store"]
IDENTITY = ["-c", "user.name=mohmmadweb", "-c", "user.email=80682916+mohmmadweb@users.noreply.github.com"]


def _git(args, cwd=REPO_DIR, check=True):
    return subprocess.run(["git", *GIT_AUTH, *IDENTITY, *args], cwd=cwd, check=check,
                          capture_output=True, text=True, timeout=180)


def pull_google():
    """google-data branch → decrypted dict, or {"status": "blocked", reason} if unavailable."""
    key = os.environ.get("SF_STATE_KEY")
    if not key:
        return {"status": "blocked", "reason": "SF_STATE_KEY missing in .env"}
    r = _git(["fetch", "-q", REMOTE, "google-data"], check=False)
    if r.returncode != 0:
        return {"status": "blocked", "reason": "google-data branch not available yet (Actions has not run)"}
    blob = subprocess.run(["git", "show", "FETCH_HEAD:google.enc"], cwd=REPO_DIR, capture_output=True, timeout=60).stdout
    try:
        return {"status": "ok", "bundle": vault.decrypt_json(blob, key)}
    except Exception as exc:                                           # noqa: BLE001
        return {"status": "blocked", "reason": f"cannot decrypt google.enc ({type(exc).__name__}) — SF_STATE_KEY differs from the GitHub secret?"}


def publish_site(site_dir):
    """Force-push the built site as an orphan gh-pages commit (no history of dashboards kept)."""
    if not os.path.exists(os.path.join(site_dir, "data.enc.js")):
        raise RuntimeError("refusing to publish an unencrypted dashboard — set SF_DASHBOARD_PASSWORD in .env")
    if os.path.exists(os.path.join(site_dir, "data.js")):
        raise RuntimeError("plaintext data.js present in site/ — refusing to publish")
    work = os.path.join(DATA, ".publish")
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(site_dir, work)
    _git(["init", "-q", "-b", "gh-pages"], cwd=work)
    _git(["add", "-A"], cwd=work)
    _git(["commit", "-qm", f"dashboard {now_tehran().isoformat(timespec='minutes')}"], cwd=work)
    r = _git(["push", "-qf", REMOTE, "gh-pages"], cwd=work, check=False)
    shutil.rmtree(work, ignore_errors=True)
    if r.returncode != 0:
        raise RuntimeError(f"push failed: {r.stderr.strip()[:300]}")
    return "gh-pages"


def backup(keep_days=14):
    """config/ + data/ → encrypted tarball → Drive (rclone), keeping the last `keep_days`."""
    key = os.environ.get("SF_STATE_KEY")
    remote = os.environ.get("RCLONE_REMOTE", "gdrive:")
    if not key:
        return "skipped: SF_STATE_KEY missing"
    blob = vault.encrypt_bytes(vault.tar_dirs([CONFIG, DATA], ROOT), key)
    local = os.path.join(os.path.dirname(DATA), ".backup")
    os.makedirs(local, exist_ok=True)
    name = f"state-{date.today().isoformat()}.enc"
    path = os.path.join(local, name)
    with open(path, "wb") as fh:
        fh.write(blob)
    dest = f"{remote}Backups/sepahanfelez-seo/"
    r = subprocess.run(["rclone", "copyto", path, dest + name], capture_output=True, text=True, timeout=300)
    old = (date.today() - timedelta(days=keep_days)).isoformat()
    for f in os.listdir(local):
        if f.startswith("state-") and f[6:16] < old:
            os.remove(os.path.join(local, f))
    return f"{dest}{name}" if r.returncode == 0 else f"drive upload failed: {r.stderr.strip()[-200:]}"
