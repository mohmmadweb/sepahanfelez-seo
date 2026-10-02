"""
Connect Google Drive as mohmmadweb@gmail.com from the dashboard (read-only), no terminal needed.

rclone's OAuth flow redirects the browser to http://127.0.0.1:53682 — on *this* server, which
the person's browser cannot reach. So:
  1. start(): run `rclone authorize drive` here and hand the person Google's sign-in URL
  2. they sign in; their browser ends on a "can't connect to 127.0.0.1" page
  3. finish(url): they paste that address; we replay it to rclone locally, rclone exchanges
     the code, and the token goes straight into rclone.conf as remote "gdrive-sf"
The token never passes through the browser or chat. Photos then sync from DRIVE_PRODUCTS_FOLDER_ID.
"""

import configparser
import json
import os
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request

REMOTE = "gdrive-sf"
_state = {"phase": "idle"}
_proc = None
_out = []


def _rclone_conf():
    p = subprocess.run(["rclone", "config", "file"], capture_output=True, text=True, timeout=20).stdout
    return p.strip().splitlines()[-1].strip()


def status():
    s = dict(_state)
    s["remote"] = REMOTE
    s["configured"] = REMOTE in subprocess.run(["rclone", "listremotes"], capture_output=True,
                                               text=True, timeout=20).stdout
    return s


def start():
    global _proc, _out
    if _proc and _proc.poll() is None:
        _proc.kill()
    _out = []
    _proc = subprocess.Popen(["rclone", "authorize", "drive", "--auth-no-open-browser", "--drive-scope", "drive.readonly"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    def pump():
        for line in _proc.stdout:
            _out.append(line)
    threading.Thread(target=pump, daemon=True).start()

    local = None
    for _ in range(60):
        m = re.search(r"(http://127\.0\.0\.1:53682/auth\?state=[\w-]+)", "".join(_out))
        if m:
            local = m.group(1)
            break
        time.sleep(0.5)
    if not local:
        _state.update(phase="error", message="rclone شروع نشد: " + "".join(_out)[-300:])
        return status()

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    try:
        urllib.request.build_opener(NoRedirect).open(local, timeout=10)
        google = None
    except urllib.error.HTTPError as e:
        google = e.headers.get("Location")
    if not google or "accounts.google.com" not in google:
        _state.update(phase="error", message="آدرس ورود گوگل ساخته نشد.")
        return status()
    _state.update(phase="waiting", auth_url=google, started=time.time(),
                  message="با mohmmadweb@gmail.com وارد شوید و دسترسی را Allow کنید. صفحه‌ی آخر خطای «اتصال برقرار نشد» می‌دهد؛ "
                          "آدرس همان صفحه را کامل کپی کنید و این‌جا بچسبانید.")
    return status()


def finish(pasted):
    if _state.get("phase") != "waiting" or not _proc or _proc.poll() is not None:
        raise RuntimeError("اول «اتصال» را بزنید؛ این مرحله منقضی شده است.")
    q = urllib.parse.urlsplit(pasted.strip())
    params = urllib.parse.parse_qs(q.query)
    if "code" not in params or "state" not in params:
        raise ValueError("این آدرس کد گوگل را ندارد؛ آدرس کامل صفحه‌ی آخر را بچسبانید.")
    local = "http://127.0.0.1:53682/?" + q.query
    try:
        urllib.request.urlopen(local, timeout=20).read()
    except Exception:                                         # noqa: BLE001
        pass
    for _ in range(60):
        if _proc.poll() is not None:
            break
        time.sleep(0.5)
    text = "".join(_out)
    m = re.search(r"--->\s*(\{.*?\})\s*<---", text, re.S)
    if not m:
        _state.update(phase="error", message="rclone توکن نداد: " + text[-300:])
        raise RuntimeError(_state["message"])
    token = json.loads(m.group(1))

    conf = _rclone_conf()
    cp = configparser.RawConfigParser()
    cp.read(conf)
    if not cp.has_section(REMOTE):
        cp.add_section(REMOTE)
    cp.set(REMOTE, "type", "drive")
    cp.set(REMOTE, "scope", "drive.readonly")
    cp.set(REMOTE, "token", json.dumps(token))
    with open(conf, "w") as fh:
        cp.write(fh)
    os.chmod(conf, 0o600)

    who = subprocess.run(["rclone", "lsjson", "-M", "--max-depth", "1", f"{REMOTE}:",
                          "--drive-root-folder-id", os.environ.get("DRIVE_ROOT_FOLDER_ID", "")],
                         capture_output=True, text=True, timeout=60)
    ok = who.returncode == 0
    _state.update(phase="done" if ok else "error", auth_url=None, connected_at=time.time(),
                  message="درایو وصل شد و پوشه‌ی سپاهان فلز خوانده شد." if ok else
                  "توکن ذخیره شد ولی پوشه خوانده نشد: " + who.stderr[-200:])
    return status()
