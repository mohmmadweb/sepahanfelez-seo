"""
Clean URLs for the site's articles and categories, applied through the admin panel.

    python3 urlfix.py plan     # reads the panel, writes dashboard/data/site/urlfix_plan.json
    python3 urlfix.py apply    # does it (refuses unless the 301 middleware is live)

The map is automation/site/url_map.json. Order matters so no address is ever a 404:
  1. blog/product category slugs — articles and products under them are sent to the new
     category by the site's middleware the moment the slug changes;
  2. each article: new slug + category, then at once a 301 row old → new;
  3. links inside article bodies that point at an old address are rewritten to the new one;
  4. existing redirect rows: broken targets fixed, chains (a row pointing at an address that
     now moves) pointed straight at the final address.
Every form is backed up before it is saved (dashboard/data/site/backup/…). The result is
checked on the live site afterwards: each old address must answer 301 → new address 200.
"""

import json
import os
import re
import sys
import urllib.parse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.join(HERE, "url_map.json")
PLAN = os.path.join(panel.DATA, "urlfix_plan.json")
LOG = os.path.join(panel.DATA, "urlfix_log.jsonl")
CANARY = ("/category/khamoot", "/category/خاموت")     # an old panel row that only works with the new middleware


def _p(url):
    """Decoded path of a URL or path, no trailing slash."""
    path = urllib.parse.unquote(urllib.parse.urlsplit(url).path)
    return path.rstrip("/") or "/"


def _log(**kw):
    os.makedirs(panel.DATA, exist_ok=True)
    kw["at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(kw, ensure_ascii=False) + "\n")


def middleware_live(p):
    """True when the site answers the canary old address with a 301 to its new one."""
    r = p.page.request.get(p.base + urllib.parse.quote(CANARY[0]), max_redirects=0)
    return r.status == 301 and _p(r.headers.get("location", "")) == CANARY[1]


def _link_variants(path):
    enc = "/".join(urllib.parse.quote(s, safe="") for s in path.split("/"))
    out = set()
    for host in ("https://sepahanfelez.ir", "http://sepahanfelez.ir", "https://www.sepahanfelez.ir",
                 "https://ahanamn.com", "http://ahanamn.com", "https://www.ahanamn.com", ""):
        for form in (path, enc, enc.lower()):
            out.add(host + form)
    return out


def rewrite_links(body, moves):
    """Replace href="old" with href="new" for every moved path (absolute, relative, encoded)."""
    changed = []

    def sub(m):
        href = m.group(2)
        old = _p(html_unescape(href))
        if old in moves:
            changed.append(old)
            return m.group(1) + moves[old] + m.group(3)
        return m.group(0)

    new = re.sub(r'(href=["\'])([^"\']+)(["\'])', sub, body or "")
    return new, changed


def html_unescape(s):
    import html
    return html.unescape(s)


def plan():
    m = json.load(open(MAP, encoding="utf-8"))
    with panel.Panel() as p:
        live = middleware_live(p)
        arts = p.articles()
        bcats = []
        for c in p.categories():
            _, v = p.form_values(f"/admin/article-category/{c['id']}/edit", f"/admin/article-category/{c['id']}")
            bcats.append({"id": c["id"], "title": v.get("title"), "slug": v.get("slug")})
        pcat_rows = p._rows("/admin/category")
        reds = p.redirects()
        bodies = {}
        for a in arts:
            _, v = p.form_values(f"/admin/article/{a['id']}/edit", f"/admin/article/{a['id']}")
            bodies[a["id"]] = v.get("body") or ""

    steps, moves = [], {}
    # 1. blog categories
    slug_to_id = {c["slug"]: c["id"] for c in bcats}
    for c in m["blog_categories"]:
        if c["new"] in slug_to_id:
            continue
        if c["old"] not in slug_to_id:
            steps.append({"kind": "missing", "what": f"دسته‌ی مجله «{c['old']}» در پنل نبود"})
            continue
        cid = slug_to_id.pop(c["old"])
        slug_to_id[c["new"]] = cid
        steps.append({"kind": "blog_category", "id": cid, "slug": c["new"], "from": f"/blog/{c['old']}",
                      "to": f"/blog/{c['new']}", "why": c["why"]})
        moves[f"/blog/{c['old']}"] = f"/blog/{c['new']}"
    # product categories (slug from the row's public link)
    for c in m["product_categories"]:
        row = next((r for r in pcat_rows if any(_p(h) == f"/category/{c['old']}" for h in r["links"] if h and "/admin/" not in h)), None)
        done = any(any(_p(h) == f"/category/{c['new']}" for h in r["links"] if h and "/admin/" not in h) for r in pcat_rows)
        if done:
            continue
        edit = row and next((h for h in row["links"] if re.search(r"/admin/category/\d+/edit", h or "")), None)
        if not edit:
            steps.append({"kind": "missing", "what": f"دسته‌ی کالای «{c['old']}» در پنل نبود"})
            continue
        steps.append({"kind": "product_category", "id": int(re.search(r"/category/(\d+)/edit", edit).group(1)),
                      "slug": c["new"], "from": f"/category/{c['old']}", "to": f"/category/{c['new']}", "why": c["why"]})
        moves[f"/category/{c['old']}"] = f"/category/{c['new']}"
    # 2. articles
    by_path = {a["path"]: a for a in arts}
    for a in m["articles"]:
        new_path = f"/blog/{a['category']}/{a['slug']}"
        if new_path in by_path:
            continue
        art = by_path.get(a["old"])
        if not art:
            steps.append({"kind": "missing", "what": f"مقاله‌ی {a['old']} در پنل نبود"})
            continue
        cid = slug_to_id.get(a["category"])
        if not cid:
            steps.append({"kind": "missing", "what": f"دسته‌ی «{a['category']}» برای {a['old']} نبود"})
            continue
        steps.append({"kind": "article", "id": art["id"], "title": art["title"], "slug": a["slug"], "category_id": cid,
                      "from": a["old"], "to": new_path, "why": a["why"]})
        moves[a["old"]] = new_path
    # 3. links inside bodies (after the moves are known)
    for aid, body in bodies.items():
        _, changed = rewrite_links(body, moves)
        if changed:
            title = next((a["title"] for a in arts if a["id"] == aid), "")
            steps.append({"kind": "body_links", "id": aid, "title": title, "links": sorted(set(changed))})
    # 4. redirect rows
    existing = {_p(r["from"]): r for r in reds}
    for frm, to in moves.items():
        if frm not in existing:
            steps.append({"kind": "redirect_add", "from": frm, "to": to})
    for fx in m["fix_redirect_targets"]:
        r = existing.get(_p(fx["from"]))
        if r and _p(r["to"]) != fx["to"]:
            steps.append({"kind": "redirect_fix", "id": r["id"], "from": _p(r["from"]), "to": moves.get(fx["to"], fx["to"]),
                          "was": _p(r["to"]), "why": fx["why"]})
    fixed = {_p(fx["from"]) for fx in m["fix_redirect_targets"]}
    for r in reds:
        tp = _p(r["to"])
        if tp in moves and _p(r["from"]) not in fixed:
            steps.append({"kind": "redirect_fix", "id": r["id"], "from": _p(r["from"]), "to": moves[tp], "was": tp,
                          "why": "زنجیره: مقصد این ردیف خودش جابه‌جا می‌شود"})
    out = {"at": datetime.now().astimezone().isoformat(timespec="seconds"), "base": panel.base(),
           "middleware_live": live, "steps": steps, "moves": moves,
           "keep_owner_redirects": m["keep_owner_redirects"], "merge_suggestions": m["merge_suggestions"],
           "counts": {k: sum(1 for s in steps if s["kind"] == k) for k in
                      ("blog_category", "product_category", "article", "body_links", "redirect_add", "redirect_fix", "missing")}}
    os.makedirs(panel.DATA, exist_ok=True)
    json.dump(out, open(PLAN, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out


def apply(say=print):
    pl = plan()
    if not pl["middleware_live"]:
        raise RuntimeError("میان‌افزار ۳۰۱ هنوز روی سایت زنده نیست (بسته‌ی sepahanfelez-redirects.zip). "
                           "بدون آن تغییر نشانی‌ها لینک‌های قدیمی را ۴۰۴ می‌کند؛ اعمال انجام نشد.")
    moves, base = pl["moves"], pl["base"]
    order = ["blog_category", "product_category", "article", "body_links", "redirect_fix"]
    done = 0
    with panel.Panel() as p:
        added = set()
        for kind in order:
            for s in [x for x in pl["steps"] if x["kind"] == kind]:
                try:
                    if kind == "blog_category":
                        p.edit_category(s["id"], {"slug": s["slug"]})
                    elif kind == "product_category":
                        p.edit_product_category(s["id"], {"slug": s["slug"]})
                    elif kind == "article":
                        _, cur = p.form_values(f"/admin/article/{s['id']}/edit", f"/admin/article/{s['id']}")
                        body, _ = rewrite_links(cur.get("body"), moves)
                        fields = {"slug": s["slug"], "category_id": s["category_id"]}
                        if body != cur.get("body"):
                            fields["body"] = body
                        p.edit_article(s["id"], fields)
                    elif kind == "body_links":
                        if any(x["kind"] == "article" and x["id"] == s["id"] for x in pl["steps"]):
                            continue                                  # already rewritten with its own move
                        _, cur = p.form_values(f"/admin/article/{s['id']}/edit", f"/admin/article/{s['id']}")
                        body, ch = rewrite_links(cur.get("body"), moves)
                        if ch:
                            p.edit_article(s["id"], {"body": body})
                    elif kind == "redirect_fix":
                        p.edit_redirect(s["id"], base + s["from"], base + s["to"])
                    # the 301 row right after the move, so the old address is never a dead end
                    if s.get("from") and s.get("to") and kind in ("blog_category", "product_category", "article"):
                        if s["from"] not in added:
                            p.add_redirect(base + s["from"], base + s["to"])
                            added.add(s["from"])
                    done += 1
                    _log(ok=True, **s)
                    say(f"✓ {kind}: {s.get('from') or s.get('title') or s.get('id')} → {s.get('to', '')}")
                except Exception as exc:                              # noqa: BLE001
                    _log(ok=False, error=str(exc)[:300], **s)
                    say(f"✗ {kind}: {s.get('from') or s.get('id')}: {str(exc)[:200]}")
        for s in [x for x in pl["steps"] if x["kind"] == "redirect_add" and x["from"] not in added]:
            try:
                p.add_redirect(base + s["from"], base + s["to"])
                done += 1
                _log(ok=True, **s)
            except Exception as exc:                                  # noqa: BLE001
                _log(ok=False, error=str(exc)[:300], **s)
                say(f"✗ redirect {s['from']}: {str(exc)[:200]}")
        verify = check_moves(p, moves)
    bad = [v for v in verify if not v["ok"]]
    say(f"بررسی روی سایت: {len(verify) - len(bad)} از {len(verify)} نشانی قدیمی درست ۳۰۱ می‌دهند.")
    res = {"applied": done, "verify": verify, "at": datetime.now().astimezone().isoformat(timespec="seconds")}
    json.dump(res, open(os.path.join(panel.DATA, "urlfix_result.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return res


def check_moves(p, moves):
    """Each old address → one 301 → the new address, which answers 200. Waits out the panel's 5-minute redirect cache once."""
    import time
    out = []
    for attempt in range(2):
        out = []
        for old, new in moves.items():
            r = p.page.request.get(p.base + urllib.parse.quote(old), max_redirects=0)
            loc = _p(r.headers.get("location", ""))
            r2 = p.page.request.get(p.base + urllib.parse.quote(new), max_redirects=0)
            out.append({"old": old, "new": new, "status": r.status, "location": loc, "new_status": r2.status,
                        "ok": r.status == 301 and loc == new and r2.status == 200})
        if all(x["ok"] for x in out) or attempt == 1:
            return out
        time.sleep(310)
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    r = plan() if cmd == "plan" else apply()
    print(json.dumps(r.get("counts") or {"applied": r.get("applied")}, ensure_ascii=False))
