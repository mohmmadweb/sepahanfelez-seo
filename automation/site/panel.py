"""
The site's admin panel (sepahanfelez.ir/admin), driven through its own forms.

Nothing is written to the site's database directly: every change is typed into the form an
admin would use and saved with the same button, so the panel's own checks (slug unique, max
lengths, image upload) and cache flushes run as usual. Before a form is saved its current
values are kept in dashboard/data/site/backup/<date>/ so any change can be put back by hand.

Login is the panel's own: mobile → SMS code. The code is asked through IO (the dashboard's
login window). The session is kept in automation/sessions/site/panel.json and stays alive as
long as the panel is visited within SESSION_LIFETIME (3 days on the host) — the daily run
and the 15-minute health check both visit it, so one login lasts.

.env
  SITE_ADMIN_MOBILE   the admin's mobile (the code goes to it)
  SITE_PANEL_BASE     optional, default https://sepahanfelez.ir (stage for tests)
  SITE_GATE_PASSWORD  optional, only for the password-gated stage
"""

import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "dashboard"))
from sf.env import load_env  # noqa: E402

SESS_DIR = os.path.join(ROOT, "automation", "sessions", "site")
DATA = os.path.join(ROOT, "dashboard", "data", "site")
STATUS = os.path.join(DATA, "panel_status.json")
PAUSE = 1.5                      # between saves; the host is shared and slow


class NotLoggedIn(Exception):
    pass


class TerminalIO:
    def say(self, msg):
        print(msg, flush=True)

    def ask(self, prompt, secret=False):
        return input(prompt + " ").strip()


IO = TerminalIO()


def base():
    load_env()
    return (os.environ.get("SITE_PANEL_BASE") or "https://sepahanfelez.ir").rstrip("/")


def state_path():
    host = urllib.parse.urlparse(base()).netloc.replace(":", "_")
    return os.path.join(SESS_DIR, f"{host}.json")


def save_status(ok, detail=""):
    os.makedirs(DATA, exist_ok=True)
    st = {"logged_in": bool(ok), "detail": detail, "base": base(),
          "checked": datetime.now().astimezone().isoformat(timespec="seconds")}
    tmp = STATUS + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, STATUS)
    return st


def status():
    try:
        return json.load(open(STATUS, encoding="utf-8"))
    except (OSError, ValueError):
        return {"logged_in": False, "detail": "never"}


def enc(url):
    """Percent-encode the path of a URL: the panel's `url` validation refuses «؟» and the like."""
    u = urllib.parse.urlsplit(url)
    path = "/".join(urllib.parse.quote(urllib.parse.unquote(s), safe="") for s in u.path.split("/"))
    return urllib.parse.urlunsplit((u.scheme, u.netloc, path, u.query, ""))


class Panel:
    """with Panel() as p: p.articles() …  — one browser for a batch of reads/saves."""

    def __init__(self, need_login=True):
        self.base = base()
        self.need_login = need_login
        self.saved = 0
        self.backup_dir = os.path.join(DATA, "backup", datetime.now().strftime("%Y-%m-%d_%H%M%S"))

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(args=["--disable-gpu", "--disable-dev-shm-usage"])
        sp = state_path()
        self.ctx = self.browser.new_context(storage_state=sp if os.path.exists(sp) else None,
                                            viewport={"width": 1366, "height": 900}, locale="fa-IR")
        self.ctx.set_default_timeout(90000)
        self.page = self.ctx.new_page()
        self._gate()
        if self.need_login and not self.logged_in():
            raise NotLoggedIn("به پنل سایت وارد نیستید — از «اتصالات و تنظیمات» → «پنل سایت» وارد شوید.")
        return self

    def __exit__(self, *exc):
        try:
            if self.need_login and os.path.exists(state_path()):
                self.ctx.storage_state(path=state_path())          # keep the refreshed session cookie
        finally:
            self.browser.close()
            self._pw.stop()

    def _gate(self):
        pw = os.environ.get("SITE_GATE_PASSWORD")
        if pw:
            self.page.request.post(self.base + "/_staging/gate", form={"password": pw})

    # ---------------------------------------------------------------- navigation
    def go(self, path):
        for attempt in range(3):
            try:
                r = self.page.goto(self.base + path, wait_until="domcontentloaded")
                self.page.wait_for_timeout(500)
                if "/login" in self.page.url or "/verify" in self.page.url:
                    raise NotLoggedIn("نشست پنل سایت منقضی شده — دوباره وارد شوید.")
                if r and r.status >= 400:
                    raise RuntimeError(f"{path} → {r.status}")
                return r
            except NotLoggedIn:
                raise
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(4)

    def logged_in(self):
        try:
            r = self.page.goto(self.base + "/admin", wait_until="domcontentloaded")
        except Exception:                                            # noqa: BLE001
            return False
        return bool(r and r.status == 200 and "/admin" in self.page.url and "/login" not in self.page.url)

    # ---------------------------------------------------------------- reads
    def _rows(self, path):
        out, page = [], 1
        while True:
            self.go(f"{path}?page={page}" if page > 1 else path)
            rows = self.page.evaluate("""()=>[...document.querySelectorAll('table tbody tr')].map(r=>({
                cells:[...r.querySelectorAll('td')].map(t=>t.innerText.trim()),
                links:[...r.querySelectorAll('a')].map(a=>a.getAttribute('href')||'')}))""")
            out += rows
            nxt = self.page.locator(f".pagination a[href*='page={page + 1}']")
            if not rows or not nxt.count():
                return out
            page += 1

    def articles(self):
        """[{id, title, category, url, path}] — url is the live address as the panel links it."""
        res = []
        for r in self._rows("/admin/article"):
            edit = next((h for h in r["links"] if re.search(r"/admin/article/\d+/edit", h)), None)
            view = next((h for h in r["links"] if "/blog/" in h), None)
            if not edit:
                continue
            path = urllib.parse.unquote(urllib.parse.urlsplit(view).path) if view else ""
            res.append({"id": int(re.search(r"/article/(\d+)/edit", edit).group(1)),
                        "title": r["cells"][1] if len(r["cells"]) > 1 else "",
                        "category": r["cells"][2] if len(r["cells"]) > 2 else "",
                        "path": path, "url": view})
        return res

    def categories(self):
        res = []
        for r in self._rows("/admin/article-category"):
            edit = next((h for h in r["links"] if re.search(r"/admin/article-category/\d+/edit", h)), None)
            if edit:
                cid = int(re.search(r"/article-category/(\d+)/edit", edit).group(1))
                res.append({"id": cid, "title": r["cells"][1] if len(r["cells"]) > 1 else ""})
        return res

    def redirects(self):
        res = []
        for r in self._rows("/admin/redirect"):
            edit = next((h for h in r["links"] if re.search(r"/admin/redirect/\d+/edit", h)), None)
            if edit and len(r["cells"]) >= 3:
                res.append({"id": int(re.search(r"/redirect/(\d+)/edit", edit).group(1)),
                            "from": r["cells"][1], "to": r["cells"][2]})
        return res

    def form_values(self, path, action_part):
        self.go(path)
        f = self._form(action_part)
        return f, self._values(f)

    def _form(self, action_part):
        forms = self.page.locator("form")
        for i in range(forms.count()):
            f = forms.nth(i)
            act = f.get_attribute("action") or ""
            if action_part in act and "logout" not in act:
                return f
        raise RuntimeError(f"فرمی با {action_part} در {self.page.url} نبود")

    def _values(self, f):
        return f.evaluate("""f=>{const o={};f.querySelectorAll('input,textarea,select').forEach(e=>{
            if(!e.name||e.type==='file'||e.name==='_token'||e.name==='_method')return;
            if(e.multiple){o[e.name]=[...e.selectedOptions].map(x=>x.value);return}
            o[e.name]=e.type==='checkbox'?e.checked:e.value});
            f.querySelectorAll('textarea').forEach(t=>{if(window.CKEDITOR&&CKEDITOR.instances[t.id])o[t.name]=CKEDITOR.instances[t.id].getData()});
            return o}""")

    def category_options(self):
        """{category title: id} from the article form's select."""
        self.go("/admin/article/create")
        return self.page.evaluate("""()=>Object.fromEntries([...document.querySelectorAll('select[name=category_id] option')]
            .filter(o=>o.value).map(o=>[o.textContent.trim(), +o.value]))""")

    # ---------------------------------------------------------------- writes
    def _backup(self, kind, key, data):
        os.makedirs(self.backup_dir, exist_ok=True)
        f = os.path.join(self.backup_dir, kind + ".json")
        cur = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
        cur[str(key)] = data
        json.dump(cur, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def _set(self, f, fields, rich=("body",)):
        for name, val in fields.items():
            if name in rich and self.page.evaluate("()=>!!window.CKEDITOR"):
                tid = f.locator(f"textarea[name='{name}']").get_attribute("id")
                self.page.evaluate("([id,v])=>{const e=CKEDITOR.instances[id]; if(e){e.setData(v); e.updateElement();}"
                                   " else document.getElementById(id).value=v;}", [tid, val])
            else:
                f.evaluate("""(f,[n,v])=>{const e=f.querySelector('[name="'+n+'"]'); if(!e) throw new Error('no field '+n);
                    e.value=v; e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true}));}""",
                           [name, str(val)])

    def _submit(self, f):
        with self.page.expect_navigation(wait_until="domcontentloaded", timeout=180000) as nav:
            f.locator("[type=submit], button:not([type=button])").last.click(no_wait_after=True)
        resp = nav.value
        self.page.wait_for_timeout(600)
        errs = self.page.evaluate("()=>[...document.querySelectorAll('.invalid-feedback,.alert-danger,.text-danger')]"
                                  ".map(e=>e.innerText.trim()).filter(Boolean)")
        if (resp and resp.status >= 400) or errs:
            raise RuntimeError("پنل ذخیره نکرد: " + ("، ".join(errs)[:300] or f"HTTP {resp.status}"))
        self.saved += 1
        time.sleep(PAUSE)

    def edit_article(self, aid, fields, image=None):
        f, cur = self.form_values(f"/admin/article/{aid}/edit", f"/admin/article/{aid}")
        self._backup("articles", aid, cur)
        self._set(f, fields)
        if image:
            f.locator("input[type=file][name=image]").set_input_files(image)
        self._submit(f)

    def create_article(self, fields, image=None):
        self.go("/admin/article/create")
        f = self._form("/admin/article")
        self._set(f, fields)
        if image:
            f.locator("input[type=file][name=image]").set_input_files(image)
        self._submit(f)
        if "/create" in self.page.url:
            raise RuntimeError("پنل مقاله را نساخت (روی فرم ماند)")

    def create_category(self, fields):
        self.go("/admin/article-category/create")
        f = self._form("/admin/article-category")
        self._set(f, fields)
        self._submit(f)

    def edit_category(self, cid, fields):
        f, cur = self.form_values(f"/admin/article-category/{cid}/edit", f"/admin/article-category/{cid}")
        self._backup("categories", cid, cur)
        self._set(f, fields)
        self._submit(f)

    def edit_product_category(self, cid, fields):
        f, cur = self.form_values(f"/admin/category/{cid}/edit", f"/admin/category/{cid}")
        self._backup("product_categories", cid, cur)
        self._set(f, fields)
        self._submit(f)

    def add_redirect(self, frm, to):
        self.go("/admin/redirect")
        f = self._form("/admin/redirect")
        self._set(f, {"from": enc(frm), "to": enc(to)})
        self._submit(f)

    def edit_redirect(self, rid, frm, to):
        f, cur = self.form_values(f"/admin/redirect/{rid}/edit", f"/admin/redirect/{rid}")
        self._backup("redirects", rid, cur)
        self._set(f, {"from": enc(frm), "to": enc(to)})
        self._submit(f)


# -------------------------------------------------------------------- login / check
def login(mobile=None):
    load_env()
    mobile = (mobile or os.environ.get("SITE_ADMIN_MOBILE") or "").strip()
    if not mobile:
        raise ValueError("شماره‌ی موبایل مدیر سایت (SITE_ADMIN_MOBILE) خالی است.")
    os.makedirs(SESS_DIR, exist_ok=True)
    with Panel(need_login=False) as p:
        pg = p.page
        if p.logged_in():
            p.ctx.storage_state(path=state_path())
            IO.say("از قبل وارد هستید.")
            save_status(True, "ok")
            return True
        pg.goto(p.base + "/login", wait_until="domcontentloaded")
        pg.fill("input[name=mobile]", mobile)
        pg.click("button[type=submit]")
        pg.wait_for_load_state("domcontentloaded")
        if not pg.locator("input[name=code]").count():
            body = pg.locator("body").inner_text()
            if "بیش از حد" in body or "۴۲۹" in body or "429" in body:
                raise RuntimeError("سایت گفت درخواست‌ها بیش از حد بوده؛ چند دقیقه صبر کنید و دوباره «ورود» را بزنید.")
            raise RuntimeError("سایت فرم کد را نشان نداد — شماره را بررسی کنید.")
        IO.say("کد پیامکی به شماره‌ی مدیر فرستاده شد.")
        code = IO.ask("کد پیامکی ورود به پنل سایت:")
        pg.fill("input[name=code]", code)
        pg.click("button[type=submit]")
        pg.wait_for_load_state("domcontentloaded")
        ok = p.logged_in()
        if ok:
            p.ctx.storage_state(path=state_path())
            os.chmod(state_path(), 0o600)
        save_status(ok, "ok" if ok else "code rejected or not an admin")
        IO.say("✓ وارد پنل سایت شدید." if ok else "✗ ورود انجام نشد (کد اشتباه یا این شماره مدیر نیست).")
        return ok


def check():
    """Visit the panel (keeps the 3-day sliding session alive) and record the result.

    Only a redirect to /login counts as «logged out». A network error or a site outage keeps the
    last known state and is reported as «unreachable», so a bad minute never cries wolf."""
    if not os.path.exists(state_path()):
        save_status(False, "no session")
        return False
    prev = status()
    try:
        with Panel(need_login=False) as p:
            r = p.page.goto(p.base + "/admin", wait_until="domcontentloaded")
            if "/login" in p.page.url or "/verify" in p.page.url:
                ok = False
            elif r and r.status == 200:
                ok = True
                p.ctx.storage_state(path=state_path())
            else:
                raise RuntimeError(f"HTTP {r.status if r else '—'}")
    except Exception as exc:                                         # noqa: BLE001
        st = save_status(prev.get("logged_in", False), f"unreachable: {type(exc).__name__}")
        st["fails"] = int(prev.get("fails", 0)) + 1
        st["last_ok"] = prev.get("last_ok")
        json.dump(st, open(STATUS, "w", encoding="utf-8"), ensure_ascii=False)
        return st["logged_in"]
    st = save_status(ok, "ok" if ok else "logged out")
    st["last_ok"] = st["checked"] if ok else prev.get("last_ok")
    if not ok:
        st["since"] = prev.get("since") if not prev.get("logged_in") and prev.get("since") else st["checked"]
    json.dump(st, open(STATUS, "w", encoding="utf-8"), ensure_ascii=False)
    return ok


def logout():
    try:
        os.remove(state_path())
    except OSError:
        pass
    save_status(False, "logged out from dashboard")
    return True


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    print({"login": login, "check": check, "logout": logout}[cmd]())
