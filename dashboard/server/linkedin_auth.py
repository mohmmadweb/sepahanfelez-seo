"""
LinkedIn sign-in for publishing (official OAuth 2.0, "Share on LinkedIn" + OpenID Connect).

The owner creates an app at developer.linkedin.com once, puts LINKEDIN_CLIENT_ID /
LINKEDIN_CLIENT_SECRET in the settings page, and registers this redirect URL in the app:
    {PUBLIC_BASE_URL}/api/linkedin/callback
Then «اتصال لینکدین» → LinkedIn consent → back here; the token lands in
automation/sessions/linkedin/token.json (600). Member tokens last 60 days; the dashboard
shows the countdown and asks for a reconnect before it lapses.

The callback cannot rely on the dashboard cookie (SameSite=Strict cookies are not sent on a
redirect from linkedin.com), so it is authorised by a single-use `state` created by a
logged-in session, valid for 10 minutes.
"""

import json
import os
import secrets
import time
import urllib.parse

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOKEN_DIR = os.path.join(ROOT, "automation", "sessions", "linkedin")
_states = {}


def redirect_uri():
    base = os.environ.get("PUBLIC_BASE_URL", "https://sepahanfelezseo.lenzit.ir").rstrip("/")
    return f"{base}/api/linkedin/callback"


def start():
    cid = os.environ.get("LINKEDIN_CLIENT_ID")
    if not cid or not os.environ.get("LINKEDIN_CLIENT_SECRET"):
        raise ValueError("اول LINKEDIN_CLIENT_ID و LINKEDIN_CLIENT_SECRET را در تنظیمات وارد کنید.")
    state = secrets.token_urlsafe(24)
    _states[state] = time.time()
    scopes = ["openid", "profile", "w_member_social"]
    if os.environ.get("LINKEDIN_ORG_ID"):
        scopes.append("w_organization_social")
    q = urllib.parse.urlencode({"response_type": "code", "client_id": cid, "redirect_uri": redirect_uri(),
                                "state": state, "scope": " ".join(scopes)})
    return {"auth_url": f"https://www.linkedin.com/oauth/v2/authorization?{q}", "redirect_uri": redirect_uri()}


def callback(code, state):
    t = _states.pop(state or "", None)
    if not t or time.time() - t > 600:
        raise ValueError("این لینک منقضی یا نامعتبر است؛ از داشبورد دوباره «اتصال لینکدین» را بزنید.")
    r = requests.post("https://www.linkedin.com/oauth/v2/accessToken", timeout=30, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(),
        "client_id": os.environ["LINKEDIN_CLIENT_ID"], "client_secret": os.environ["LINKEDIN_CLIENT_SECRET"]})
    if r.status_code != 200:
        raise RuntimeError(f"LinkedIn token: {r.status_code} {r.text[:200]}")
    tok = r.json()
    me = requests.get("https://api.linkedin.com/v2/userinfo", timeout=30,
                      headers={"Authorization": f"Bearer {tok['access_token']}"}).json()
    data = {"access_token": tok["access_token"], "expires_at": time.time() + int(tok.get("expires_in", 0)),
            "scope": tok.get("scope"), "sub": me.get("sub"), "name": me.get("name"), "connected_at": time.time()}
    os.makedirs(TOKEN_DIR, mode=0o700, exist_ok=True)
    path = os.path.join(TOKEN_DIR, "token.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.chmod(path, 0o600)
    return {"name": data["name"], "days": int(int(tok.get("expires_in", 0)) / 86400)}
