#!/usr/bin/env python3
"""
Branded story/post renderer: product photo + Persian copy → 1080×1920 story or 1080×1350 post.

Rendered through headless Chromium so Persian shaping, the Estedad font and RTL are exact
(Pillow without libraqm breaks Persian letters). Brand rules from the site: red only for
contact, prices in ریال, the company's numbers from .env (SITE_CONTACT_PHONES; the mobile goes on the
card), sepahanfelez.ir.

    ~/.venvs/pw/bin/python automation/render_card.py cards.json out_dir/
cards.json: [{"id", "format": "story|post", "layout": "classic|full|bold", "type", "title", "points": [...], "photo", "cta"}]
"""

import base64
import html
import json
import mimetypes
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO = "/home/ubuntu/projects/sepahanfelez-seo/media/proto"
FONT_DIR = os.path.join(os.path.dirname(HERE), "dashboard", "web", "fonts")
LOGO = os.path.join(PROTO, "assets", "brand", "logo.svg")
SIZES = {"story": (1080, 1920), "post": (1080, 1350)}


def data_uri(path):
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as fh:
        return f"data:{mime};base64,{base64.b64encode(fh.read()).decode()}"


def fa_digits(s):
    return str(s).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def card_phone():
    """The mobile from SITE_CONTACT_PHONES (.env) — kept out of this public repo — spaced for reading."""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "dashboard"))
    from sf.env import load_env
    load_env()
    nums = [re.sub(r"\D", "", x) for x in os.environ.get("SITE_CONTACT_PHONES", "").split(",") if x.strip()]
    mob = next((n for n in nums if n.startswith("09")), nums[0] if nums else "")
    return fa_digits(f"{mob[:4]} {mob[4:7]} {mob[7:]}" if len(mob) == 11 else mob)


# Story viewers (Bale, Instagram, WhatsApp, Telegram) draw their own bars over a story — progress bar and name at
# the top, reply box at the bottom — and taller phones crop the sides. Everything that matters stays inside
# x 110…970, y 250…1650; the edges keep only the background colour.
SAFE = {"top": 250, "bottom": 270, "side": 110}
STORY_SAFE = f"""
body.story .top{{padding:{SAFE['top']}px {SAFE['side']}px 0}}
body.story .photo{{margin:36px {SAFE['side']}px 0;height:600px}}
body.story h1{{margin:38px {SAFE['side']}px 0;font-size:62px}}
body.story ul{{margin:18px {SAFE['side']}px 0;font-size:34px;line-height:1.7}}
body.story .cta{{left:{SAFE['side']}px;right:{SAFE['side']}px;bottom:{SAFE['bottom']}px;border-radius:30px;padding:30px 44px}}
body.story.tight .photo{{height:500px}}
body.story.tight h1{{font-size:54px}}
body.story.tight ul{{font-size:31px}}
"""


def cta_text(cta):
    """The footer's call to action — never a number (the phone is printed once, next to it)."""
    cta = (cta or "").strip()
    if not cta or re.search(r"[0-9۰-۹]", cta) or len(cta) > 24:
        return "استعلام قیمت روز"
    return cta


def page(card):
    w, h = SIZES[card.get("format", "story")]
    story = card.get("format", "story") == "story"
    fonts = "".join(
        f"@font-face{{font-family:Estedad;src:url({data_uri(os.path.join(FONT_DIR, f'Estedad-{n}.woff2'))});font-weight:{wt}}}"
        for n, wt in (("Regular", 400), ("Medium", 500), ("Bold", 700)))
    photo = data_uri(card["photo"])
    points = "".join(f"<li>{html.escape(fa_digits(p))}</li>" for p in card.get("points", []))
    photo_h = 960 if story else 660
    h1 = f'<h1>{html.escape(fa_digits(card["title"]))}</h1>'
    head_first, head_after = (h1, "") if card.get("layout") == "bold" else ("", h1)
    return f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>
{fonts}
*{{box-sizing:border-box;margin:0}}
body{{width:{w}px;height:{h}px;font-family:Estedad;background:#F3F6FA;color:#0B1220;overflow:hidden;position:relative}}
.top{{display:flex;align-items:center;gap:22px;padding:{70 if story else 48}px 70px 0}}
.top img{{height:{110 if story else 90}px}}
.top b{{font-size:{46 if story else 40}px;font-weight:700;color:#123152;display:block;line-height:1.3}}
.top span{{font-size:26px;color:#4A5B70}}
.chip{{display:inline-block;margin:{46 if story else 30}px 70px 0;padding:6px 26px;border-radius:999px;background:#123152;color:#fff;font-size:28px;font-weight:500}}
.photo{{margin:{60 if story else 40}px 70px 0;height:{photo_h}px;border-radius:36px;overflow:hidden;box-shadow:0 20px 50px rgba(18,49,82,.18)}}
.photo img{{width:100%;height:100%;object-fit:cover;display:block}}
h1{{margin:{50 if story else 34}px 70px 0;font-size:{70 if story else 58}px;line-height:1.35;font-weight:700;color:#123152}}
ul{{margin:{26 if story else 16}px 70px 0;padding:0 40px 0 0;font-size:{36 if story else 32}px;line-height:1.75;color:#24344A}}
li::marker{{color:#123152}}
/* layout «full»: the photo fills the card, copy on a dark gradient */
body.full .photo{{position:absolute;inset:0;margin:0;height:auto;border-radius:0;box-shadow:none}}
body.full .photo::after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(11,18,32,.55) 0%,rgba(11,18,32,0) 28%,rgba(11,18,32,0) 45%,rgba(11,18,32,.88) 78%)}}
body.full .top,body.full .chip,body.full h1,body.full ul{{position:relative;z-index:2}}
body.full .top b,body.full .top span,body.full h1,body.full ul{{color:#fff}}
body.full .top{{background:rgba(255,255,255,.0)}}
body.full .top img{{background:#fff;border-radius:18px;padding:6px}}
body.full h1{{position:absolute;left:0;right:0;bottom:{480 if story else 320}px}}
body.full ul{{position:absolute;left:0;right:0;bottom:{210 if story else 140}px}}
body.full li::marker{{color:#fff}}
body.full .chip{{background:#fff;color:#123152}}
/* layout «bold»: navy card, big headline first, smaller photo */
body.bold{{background:#123152;color:#fff}}
body.bold .top b,body.bold .top span{{color:#fff}}
body.bold .top img{{background:#fff;border-radius:18px;padding:6px}}
body.bold .chip{{background:#fff;color:#123152}}
body.bold h1{{color:#fff;font-size:{82 if story else 64}px;margin-top:{60 if story else 30}px}}
body.bold ul{{color:#DCE6F2}}
body.bold li::marker{{color:#fff}}
body.bold .photo{{height:{640 if story else 420}px;box-shadow:none;border:6px solid rgba(255,255,255,.18)}}
.cta{{position:absolute;left:0;right:0;bottom:0;background:#B42332;color:#fff;padding:{44 if story else 34}px 70px;display:flex;justify-content:space-between;align-items:center}}
.cta .t{{font-size:{40 if story else 34}px;font-weight:700}}
.cta .n{{font-size:{44 if story else 38}px;font-weight:700;direction:ltr}}
.cta .w{{font-size:26px;opacity:.9;direction:ltr;text-align:left}}
{STORY_SAFE if story else ""}
</style></head><body class="{html.escape(card.get("layout", "classic"))}{' story' if story else ''}">
<div class="top"><img src="{data_uri(LOGO)}" alt=""><div><b>سپاهان فلز</b><span>صنایع مفتولی طلوع سپاهان</span></div></div>
{head_first}<div class="photo"><img src="{photo}" alt=""></div>
{head_after}
<ul>{points}</ul>
<div class="cta"><div class="t">{html.escape(cta_text(card.get("cta")))}</div>
<div><div class="n">{html.escape(card_phone())}</div><div class="w">sepahanfelez.ir</div></div></div>
</body></html>"""


def render(cards, out_dir):
    from playwright.sync_api import sync_playwright
    os.makedirs(out_dir, exist_ok=True)
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for c in cards:
            w, h = SIZES[c.get("format", "story")]
            pg = b.new_page(viewport={"width": w, "height": h})
            pg.set_content(page(c), wait_until="load")
            pg.wait_for_timeout(300)
            if c.get("format", "story") == "story":
                for _ in range(2):
                    fit = pg.evaluate("""()=>{const r=s=>document.querySelector(s).getBoundingClientRect();
                        const els=['.top img','.top b','.photo','h1','ul','.cta'].map(r);
                        return {gap: r('.cta').top-r('ul').bottom, top: Math.min(...els.map(e=>e.top)),
                                bottom: Math.max(...els.map(e=>e.bottom)), left: Math.min(...els.map(e=>e.left)),
                                right: Math.max(...els.map(e=>e.right))}}""")
                    fit["safe"] = (fit["gap"] >= 24 and fit["top"] >= SAFE["top"] - 10 and fit["bottom"] <= 1920 - SAFE["bottom"] + 10
                                   and fit["left"] >= SAFE["side"] - 10 and fit["right"] <= 1080 - SAFE["side"] + 10)
                    if fit["safe"]:
                        break
                    pg.evaluate("document.body.classList.add('tight')")
                    pg.wait_for_timeout(150)
                c["fit"] = fit
            path = os.path.join(out_dir, f"{c['id']}.jpg")
            pg.screenshot(path=path, type="jpeg", quality=82)
            pg.close()
            out.append(path)
        b.close()
    return out


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as fh:
        cards = json.load(fh)
    for path in render(cards, sys.argv[2]):
        print(path)
