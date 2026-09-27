#!/usr/bin/env python3
"""
Branded story/post renderer: product photo + Persian copy → 1080×1920 story or 1080×1350 post.

Rendered through headless Chromium so Persian shaping, the Estedad font and RTL are exact
(Pillow without libraqm breaks Persian letters). Brand rules from the site: red only for
contact, prices in ریال, office 021-91326030, mobile 0913-300-6030, sepahanfelez.ir.

    ~/.venvs/pw/bin/python automation/render_card.py cards.json out_dir/
cards.json: [{"id", "format": "story|post", "type", "title", "points": [...], "photo", "cta"}]
"""

import base64
import html
import json
import mimetypes
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO = "/home/ubuntu/projects/sepahanfelez-prototype"
FONT_DIR = os.path.join(os.path.dirname(HERE), "dashboard", "web", "fonts")
LOGO = os.path.join(PROTO, "assets", "brand", "logo.svg")
SIZES = {"story": (1080, 1920), "post": (1080, 1350)}


def data_uri(path):
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as fh:
        return f"data:{mime};base64,{base64.b64encode(fh.read()).decode()}"


def fa_digits(s):
    return str(s).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def page(card):
    w, h = SIZES[card.get("format", "story")]
    story = card.get("format", "story") == "story"
    fonts = "".join(
        f"@font-face{{font-family:Estedad;src:url({data_uri(os.path.join(FONT_DIR, f'Estedad-{n}.woff2'))});font-weight:{wt}}}"
        for n, wt in (("Regular", 400), ("Medium", 500), ("Bold", 700)))
    photo = data_uri(card["photo"])
    points = "".join(f"<li>{html.escape(fa_digits(p))}</li>" for p in card.get("points", []))
    photo_h = 900 if story else 620
    return f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>
{fonts}
*{{box-sizing:border-box;margin:0}}
body{{width:{w}px;height:{h}px;font-family:Estedad;background:#F3F6FA;color:#0B1220;overflow:hidden;position:relative}}
.top{{display:flex;align-items:center;gap:22px;padding:{70 if story else 48}px 70px 0}}
.top img{{height:{110 if story else 90}px}}
.top b{{font-size:{46 if story else 40}px;font-weight:700;color:#123152;display:block;line-height:1.3}}
.top span{{font-size:26px;color:#4A5B70}}
.chip{{display:inline-block;margin:{46 if story else 30}px 70px 0;padding:6px 26px;border-radius:999px;background:#123152;color:#fff;font-size:28px;font-weight:500}}
.photo{{margin:{28 if story else 22}px 70px 0;height:{photo_h}px;border-radius:36px;overflow:hidden;box-shadow:0 20px 50px rgba(18,49,82,.18)}}
.photo img{{width:100%;height:100%;object-fit:cover;display:block}}
h1{{margin:{50 if story else 34}px 70px 0;font-size:{70 if story else 58}px;line-height:1.35;font-weight:700;color:#123152}}
ul{{margin:{26 if story else 16}px 70px 0;padding:0 40px 0 0;font-size:{36 if story else 32}px;line-height:1.75;color:#24344A}}
li::marker{{color:#123152}}
.cta{{position:absolute;left:0;right:0;bottom:0;background:#B42332;color:#fff;padding:{44 if story else 34}px 70px;display:flex;justify-content:space-between;align-items:center}}
.cta .t{{font-size:{40 if story else 34}px;font-weight:700}}
.cta .n{{font-size:{44 if story else 38}px;font-weight:700;direction:ltr}}
.cta .w{{font-size:26px;opacity:.9;direction:ltr;text-align:left}}
</style></head><body>
<div class="top"><img src="{data_uri(LOGO)}" alt=""><div><b>سپاهان فلز</b><span>صنایع مفتولی طلوع سپاهان</span></div></div>
<div class="chip">{html.escape(card.get("type", ""))}</div>
<div class="photo"><img src="{photo}" alt=""></div>
<h1>{html.escape(fa_digits(card["title"]))}</h1>
<ul>{points}</ul>
<div class="cta"><div class="t">{html.escape(card.get("cta", "استعلام قیمت روز"))}</div>
<div><div class="n">۰۹۱۳ ۳۰۰ ۶۰۳۰</div><div class="w">sepahanfelez.ir</div></div></div>
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
