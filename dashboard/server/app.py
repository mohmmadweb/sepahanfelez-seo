"""
Live dashboard for sepahanfelezseo.lenzit.ir.

    .venv/bin/uvicorn dashboard.server.app:app --host 127.0.0.1 --port 8813

Listens on localhost only; reaches the internet through a Cloudflare Tunnel (HTTPS at the edge).
Everything under /api except /api/login needs the session cookie. The password is
SF_DASHBOARD_PASSWORD from .env; changing it there (or from the settings page) logs everyone out.
"""

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.dirname(HERE)
ROOT = os.path.dirname(DASH)
sys.path.insert(0, DASH)

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from sf import build, serp, trace  # noqa: E402
from sf.env import load_env  # noqa: E402
from sf.util import DATA, now_tehran, read_json, write_json  # noqa: E402

from . import drive_auth, envfile, social_jobs  # noqa: E402

load_env()
WEB = os.path.join(DASH, "web")
COOKIE = "sf_session"
SESSION_HOURS = 12
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


# ---------------------------------------------------------------- auth
def _key():
    # derived from both secrets: a password change invalidates every existing session
    pw = os.environ.get("SF_DASHBOARD_PASSWORD", "")
    return hashlib.sha256(("sf-session|" + os.environ.get("SF_STATE_KEY", "") + "|" + pw).encode()).digest()


def _sign(payload):
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    mac = hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{mac}"


def _verify(token):
    try:
        body, mac = token.rsplit(".", 1)
        if not hmac.compare_digest(mac, hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()):
            return None
        data = json.loads(base64.urlsafe_b64decode(body))
        return data if data.get("exp", 0) > time.time() else None
    except Exception:                                                # noqa: BLE001
        return None


_attempts = {}


def _ip(req):
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


@app.middleware("http")
async def guard(req: Request, call_next):
    path = req.url.path
    if path.startswith("/api/") and path != "/api/login":
        if not _verify(req.cookies.get(COOKIE, "")):
            return JSONResponse({"error": "login required"}, status_code=401)
        if req.method != "GET" and req.headers.get("x-requested-with") != "sf":
            return JSONResponse({"error": "bad request"}, status_code=403)       # CSRF: same-origin fetch only
    if path.startswith("/media/") and not _verify(req.cookies.get(COOKIE, "")):
        return JSONResponse({"error": "login required"}, status_code=401)
    resp = await call_next(req)
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    if path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.post("/api/login")
async def login(req: Request):
    ip = _ip(req)
    now = time.time()
    tries = [t for t in _attempts.get(ip, []) if now - t < 600]
    if len(tries) >= 6:
        return JSONResponse({"error": "تلاش زیاد؛ ۱۰ دقیقه‌ی دیگر امتحان کنید."}, status_code=429)
    body = await req.json()
    expected = os.environ.get("SF_DASHBOARD_PASSWORD", "")
    if not expected or not hmac.compare_digest(str(body.get("password", "")).encode(), expected.encode()):
        tries.append(now)
        _attempts[ip] = tries
        time.sleep(1)
        return JSONResponse({"error": "رمز درست نیست."}, status_code=401)
    _attempts.pop(ip, None)
    token = _sign({"exp": now + SESSION_HOURS * 3600, "n": uuid.uuid4().hex[:8]})
    resp = JSONResponse({"ok": True})
    secure = req.headers.get("x-forwarded-proto", req.url.scheme) == "https"
    resp.set_cookie(COOKIE, token, max_age=SESSION_HOURS * 3600, httponly=True, secure=secure,
                    samesite="strict", path="/")
    return resp


@app.post("/api/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@app.get("/api/me")
async def me():
    return {"ok": True, "now": now_tehran().isoformat(timespec="seconds")}


# ---------------------------------------------------------------- data
@app.get("/api/data")
async def data():
    return build.assemble()


@app.get("/api/trace/{item_id}")
async def get_trace(item_id: str):
    steps = trace.read(item_id)
    if not steps:
        raise HTTPException(404, "برای این محتوا هنوز روندی ثبت نشده.")
    return {"id": item_id, "steps": steps, "stages": trace.STAGES}


# ---------------------------------------------------------------- settings (.env)
@app.get("/api/env")
async def env_view():
    return envfile.view()


@app.post("/api/env")
async def env_update(req: Request):
    body = await req.json()
    try:
        changed = envfile.update(body.get("values", {}))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    resp = JSONResponse({"ok": True, "changed": changed})
    if "CLOUDFLARE_TUNNEL_TOKEN" in changed:
        subprocess.run(["systemctl", "--user", "restart", "sepahanfelez-tunnel.service"], timeout=30, check=False)
    if "SF_DASHBOARD_PASSWORD" in changed:
        resp.delete_cookie(COOKIE, path="/")          # session key changed; log in again with the new password
    return resp


# ---------------------------------------------------------------- social logins
@app.get("/api/social/job")
async def social_job():
    return {"job": social_jobs.current(), "status": read_json(os.path.join(DATA, "social_status.json"), {})}


@app.post("/api/social/{net}/{action}")
async def social_action(net: str, action: str):
    if action not in ("login", "logout", "check"):
        raise HTTPException(404)
    try:
        return social_jobs.start(net, action)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/social/answer")
async def social_answer(req: Request):
    body = await req.json()
    try:
        return social_jobs.answer(str(body.get("answer", "")))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/social/cancel")
async def social_cancel():
    return {"job": social_jobs.cancel()}


# ---------------------------------------------------------------- Google Drive (mohmmadweb@gmail.com)
@app.get("/api/drive")
async def drive_status():
    s = drive_auth.status()
    s["sync"] = read_json(os.path.join(DATA, "latest", "drive.json"), {})
    return s


@app.post("/api/drive/start")
async def drive_start():
    return drive_auth.start()


@app.post("/api/drive/finish")
async def drive_finish(req: Request):
    body = await req.json()
    try:
        s = drive_auth.finish(str(body.get("url", "")))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc))
    if s.get("phase") == "done":
        envfile.update({"DRIVE_PHOTOS_REMOTE": f"{drive_auth.REMOTE}:"})
        _start_run(["drive", "calendar"])
    return s


# ---------------------------------------------------------------- competitors
@app.post("/api/competitors/{domain}/{action}")
async def competitor_decide(domain: str, action: str):
    if action not in ("accept", "ignore"):
        raise HTTPException(404)
    return serp.decide(domain, action)


# ---------------------------------------------------------------- manual runs
STEPS = {"crawl": "خزش سایت", "competitors": "نقشه‌ی سایت رقبا", "serp": "نتایج جستجو و رقبای تازه",
         "drive": "عکس‌های درایو", "calendar": "تقویم و برنامه‌ی محتوا", "google": "داده‌ی گوگل",
         "social": "وضعیت ورود شبکه‌ها", "analyse": "تحلیل مشکلات", "backup": "پشتیبان"}
_run_lock = threading.Lock()
RUNS = os.path.join(DATA, "runs.json")


def _start_run(steps):
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(409, "یک اجرای دیگر در جریان است.")
    rid = now_tehran().strftime("%Y%m%d-%H%M%S")
    runs = read_json(RUNS, {}) or {}
    runs[rid] = {"id": rid, "steps": steps, "started": now_tehran().isoformat(timespec="seconds"), "state": "running"}
    write_json(RUNS, dict(sorted(runs.items())[-30:]))

    def work():
        try:
            p = subprocess.run([sys.executable, os.path.join(DASH, "run_daily.py"), "--only", *steps, "analyse"],
                               cwd=DASH, capture_output=True, text=True, timeout=3600)
            out, rc = (p.stdout + p.stderr)[-4000:], p.returncode
        except Exception as exc:                                         # noqa: BLE001
            out, rc = str(exc), -1
        finally:
            _run_lock.release()
        runs = read_json(RUNS, {}) or {}
        runs[rid].update(state="done" if rc == 0 else "error", finished=now_tehran().isoformat(timespec="seconds"),
                         log=out)
        write_json(RUNS, runs)
    threading.Thread(target=work, daemon=True).start()
    return runs[rid]


@app.post("/api/run")
async def run_steps(req: Request):
    body = await req.json()
    steps = [s for s in body.get("steps", []) if s in STEPS]
    if not steps:
        raise HTTPException(400, "مرحله‌ای انتخاب نشده")
    return _start_run(steps)


@app.get("/api/runs")
async def runs():
    return {"steps": STEPS, "runs": read_json(RUNS, {}) or {}, "busy": _run_lock.locked()}


# ---------------------------------------------------------------- media + static
@app.get("/media/photos/{slug}/{name}")
async def media(slug: str, name: str):
    base = os.path.realpath(os.path.join(DATA, "photos"))
    path = os.path.realpath(os.path.join(base, slug, name))
    if not path.startswith(base + os.sep) or not os.path.isfile(path):
        raise HTTPException(404)
    return FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})


@app.get("/robots.txt")
async def robots():
    return HTMLResponse("User-agent: *\nDisallow: /\n", media_type="text/plain")


@app.get("/")
async def index():
    return FileResponse(os.path.join(WEB, "index.html"), headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=WEB), name="web")
