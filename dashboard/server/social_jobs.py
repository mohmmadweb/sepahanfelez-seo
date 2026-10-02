"""
Runs the login flows of automation/social/login.py from the web UI.

A flow needs a human in the middle (the code the network texts to the phone), so each login
runs in its own thread and talks through a WebIO object: when the flow asks for a code the
job goes to phase "waiting", the UI shows an input, and the answer travels back on a queue.
One login at a time — the networks send codes to the same phone and parallel logins confuse
both the person and the networks.
"""

import os
import queue
import sys
import threading
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "automation", "social"))
import login as L  # noqa: E402

NETS = {"eitaa": "ایتا", "bale": "بله", "rubika": "روبیکا", "whatsapp": "واتساپ",
        "telegram": "تلگرام", "instagram": "اینستاگرام"}
ANSWER_TIMEOUT = 300


class Job:
    def __init__(self, net, action):
        self.id = uuid.uuid4().hex[:10]
        self.net, self.action = net, action
        self.phase = "running"            # running | waiting | done | error
        self.prompt, self.secret, self.link_code = None, False, None
        self.messages, self.ok = [], None
        self.started = time.time()
        self.answers = queue.Queue()

    def view(self):
        return {"id": self.id, "net": self.net, "net_fa": NETS.get(self.net, self.net), "action": self.action,
                "phase": self.phase, "prompt": self.prompt, "secret": self.secret, "link_code": self.link_code,
                "messages": self.messages[-20:], "ok": self.ok, "elapsed": int(time.time() - self.started)}


class WebIO:
    def __init__(self, job):
        self.job = job

    def say(self, msg):
        self.job.messages.append(str(msg).strip())

    def ask(self, prompt, secret=False):
        j = self.job
        j.prompt, j.secret, j.phase = prompt, secret, "waiting"
        try:
            ans = j.answers.get(timeout=ANSWER_TIMEOUT)
        except queue.Empty:
            raise TimeoutError("۵ دقیقه کدی وارد نشد؛ دوباره «ورود» را بزنید.")
        j.prompt, j.secret, j.phase = None, False, "running"
        if ans is None:
            raise RuntimeError("لغو شد.")
        return ans.strip()

    def link_code(self, code, how):
        self.job.link_code = code
        self.say(how)


_lock = threading.Lock()
_current = None


def current():
    return _current.view() if _current else None


def start(net, action="login"):
    global _current
    if net not in NETS:
        raise ValueError("unknown network")
    with _lock:
        if _current and _current.phase in ("running", "waiting"):
            raise RuntimeError(f"ورود به {NETS[_current.net]} هنوز در جریان است.")
        job = _current = Job(net, action)

    def work():
        L.IO = WebIO(job)
        try:
            L.load_env()
            if action == "logout":
                import shutil
                shutil.rmtree(os.path.join(L.SESSIONS, net), ignore_errors=True)
                L.save_status(net, False, "logged out from dashboard")
                job.ok = True
                job.messages.append(f"از {NETS[net]} خارج شدید و نشست پاک شد.")
            elif action == "check":
                fn = {"telegram": L.check_telegram, "instagram": L.check_instagram}.get(net, lambda: L.check_web(net))
                job.ok = bool(fn())
                job.messages.append("وارد هستید." if job.ok else "وارد نیستید.")
            else:
                fn = {"telegram": L.login_telegram, "instagram": L.login_instagram}.get(net, lambda: L.login_web(net))
                job.ok = bool(fn())
            job.phase = "done"
        except SystemExit as exc:              # login.py exits with a message when .env is missing a value
            job.ok, job.phase = False, "error"
            job.messages.append(str(exc))
        except Exception as exc:               # noqa: BLE001
            job.ok, job.phase = False, "error"
            job.messages.append(f"{type(exc).__name__}: {str(exc)[:240]}")
            L.save_status(net, False, f"{type(exc).__name__}")
        finally:
            L.IO = L.TerminalIO()

    threading.Thread(target=work, daemon=True, name=f"social-{net}").start()
    return job.view()


def answer(text):
    if not _current or _current.phase != "waiting":
        raise RuntimeError("الان منتظر کدی نیستیم.")
    _current.answers.put(text)
    return _current.view()


def cancel():
    if _current and _current.phase == "waiting":
        _current.answers.put(None)
    return current()
