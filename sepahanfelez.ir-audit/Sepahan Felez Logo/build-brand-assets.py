#!/usr/bin/env python3
"""Build every brand asset the site serves, from the owner's logo artwork.

The SVG that came with the artwork is a poor auto-trace of the PNG. In
«سپاهان فلز» it welds spurious blocks between letters, breaks the baseline bar
into fragments and cuts 45-degree notches into square corners. Measured against
the 1728x3232 PNG at the size the header actually renders it, 3.59% of its
pixels are wrong.

So the vector is rebuilt here from the PNG instead:

  1. flatten the alpha onto white;
  2. posterise to the five colours the logo is really made of, which removes
     the anti-aliasing that would otherwise be traced as dozens of extra
     near-identical colour layers;
  3. trace with vtracer in polygon mode — the mark is flat-coloured and almost
     entirely straight-edged, so polygons beat splines on both fidelity and
     size.

That lands at 0.01% of pixels wrong at display size, in a smaller file.

Everything else — the footer lockup, the favicon, the social preview — is a
crop of that one trace, so they cannot drift apart. Re-run this if the logo is
ever replaced.

    pip install vtracer cairosvg pillow
    python build-brand-assets.py
"""
import os
import re
import sys

import cairosvg
import vtracer
from PIL import Image, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_PNG = os.path.join(HERE, "sepahan-felez-1728x3232.png")
SRC_SVG = os.path.join(HERE, "sepahan-felez.svg")
OUT = "/home/mlops/mohammad/ahanamn-src/public_html/assets/brand/"

# The logo's real palette, read off the source: white, dark maroon, red, the
# thin border blue-grey, and the navy of the wordmark.
PALETTE = [(0xff, 0xff, 0xff), (0x7d, 0x1e, 0x32), (0xb4, 0x23, 0x32),
           (0x8c, 0x92, 0xad), (0x28, 0x32, 0x64)]
BORDER = "#8C92AD"

BLUE, DARK = "#495f9e", "#283264"

W, H = 1728, 3232          # the trace's coordinate space
BOX_W, BOX_H = 216, 404    # the box the site lays the logo out in

# Ink bands, measured on the posterised source and expressed in trace units.
WORDMARK = (160, 1984, 1408, 536)   # «سپاهان فلز» + SEPAHAN FELEZ
CUBE = (264, 352, 1216, 1560)       # the isometric cube alone


def flatten(dst="/tmp/logo-flat.png"):
    im = Image.open(SRC_PNG).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    Image.alpha_composite(bg, im).convert("RGB").save(dst)
    return dst


def posterise(src, dst="/tmp/logo-posterised.png"):
    pal = Image.new("P", (1, 1))
    pal.putpalette([v for c in PALETTE for v in c] + [0] * (768 - 3 * len(PALETTE)))
    Image.open(src).convert("RGB").quantize(
        palette=pal, dither=Image.Dither.NONE).convert("RGB").save(dst)
    return dst


def trace(src, dst="/tmp/logo-traced.svg"):
    vtracer.convert_image_to_svg_py(
        src, dst, colormode="color", hierarchical="stacked", mode="polygon",
        color_precision=8, layer_difference=0, filter_speckle=8,
        corner_threshold=30, length_threshold=4.0, max_iterations=10,
        splice_threshold=45, path_precision=3)
    return dst


def inner(path):
    """The trace's contents, without its own <svg> wrapper, and with the
    off-white vtracer emits for the background normalised to pure white."""
    s = open(path, encoding="utf-8").read()
    s = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", s)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"^\s*<svg\b[^>]*>", "", s, count=1)
    s = re.sub(r"</svg>\s*$", "", s, count=1)
    return re.sub(r'fill="#FEFEFE"', 'fill="#ffffff"', s).strip()


def without_border(body):
    """Drop the thin hexagon outline. Its slanted top edges cut through any
    crop tight enough to isolate the cube."""
    return re.sub(r'<path[^>]*fill="' + BORDER + r'"[^>]*/>', "", body, flags=re.I)


def crop(body, box, x, y, w, h, uid):
    """Nest the trace in a sub-viewBox so only `box` of it shows."""
    bx, by, bw, bh = box
    body = re.sub(r'id="([\w-]+)"', rf'id="\1-{uid}"', body)
    body = re.sub(r"url\(#([\w-]+)\)", rf"url(#\1-{uid})", body)
    return (f'<svg x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'viewBox="{bx} {by} {bw} {bh}" preserveAspectRatio="xMidYMid meet" '
            f'overflow="hidden">{body}</svg>')


def header_logo(body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'width="{BOX_W}" height="{BOX_H}" role="img" aria-label="سپاهان فلز">\n'
            f'  <title>سپاهان فلز</title>\n{body}\n</svg>\n')


def footer_banner(body):
    """1695x314 — the box footer-logo2.png occupied, and the same silhouette:
    white across the top, the footer's blue below a curve that dives to the
    baseline at both edges. The cube sits beside the wordmark because a
    portrait mark dropped whole into a band this wide is a thumbnail."""
    w, h = 1695, 314
    wave = (f"M0,0 C{int(w*0.14)},0 {int(w*0.16)},253 {int(w*0.30)},253 "
            f"L{int(w*0.72)},253 C{int(w*0.86)},253 {int(w*0.88)},0 {w},0 "
            f"L{w},{h} L0,{h} Z")
    cube_h, word_h = 176, 150
    cube_w = cube_h * (CUBE[2] / CUBE[3])
    word_w = word_h * (WORDMARK[2] / WORDMARK[3])
    gap = 34
    x0 = (w - (cube_w + gap + word_w)) / 2
    mark = (crop(without_border(body), CUBE, x0, 30, cube_w, cube_h, "fc")
            + crop(body, WORDMARK, x0 + cube_w + gap,
                   30 + (cube_h - word_h) / 2, word_w, word_h, "fw"))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}" role="img" aria-label="سپاهان فلز">\n'
            f'  <title>سپاهان فلز</title>\n'
            f'  <rect width="{w}" height="{h}" fill="#ffffff"/>\n'
            f'  <path d="{wave}" fill="{BLUE}"/>\n  {mark}\n</svg>\n')


def favicon(body):
    mark = crop(without_border(body), CUBE, 8, 8, 48, 48, "fav")
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
            'width="64" height="64" role="img" aria-label="سپاهان فلز">\n'
            '  <title>سپاهان فلز</title>\n'
            '  <rect width="64" height="64" rx="10" fill="#ffffff"/>\n'
            f'  {mark}\n</svg>\n')


def og_image(body, tagline):
    w, h = 1200, 630
    logo = crop(body, (0, 0, W, H), (w - 225) / 2, 42, 225, 420, "og")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}">\n'
            f'  <rect width="{w}" height="{h}" fill="#ffffff"/>\n'
            f'  <rect width="{w}" height="12" fill="#b42332"/>\n'
            f'  <rect y="{h-12}" width="{w}" height="12" fill="{DARK}"/>\n'
            f'  {logo}\n  {tagline}\n</svg>\n')


def report(svg, label, reference):
    """Error against the source raster at the size the header renders it."""
    cairosvg.svg2png(url=svg, write_to="/tmp/score.png", output_width=147,
                     output_height=275, background_color="white")
    a = Image.open("/tmp/score.png").convert("RGB")
    b = Image.open(reference).convert("RGB").resize((147, 275), Image.LANCZOS)
    hist = ImageChops.difference(a, b).convert("L").histogram()
    total = sum(hist)
    mean = sum(i * n for i, n in enumerate(hist)) / total
    over = 100 * sum(n for i, n in enumerate(hist) if i > 60) / total
    print(f"  {label:22s} mean {mean:5.2f}   pixels off >60: {over:5.2f}%   "
          f"{os.path.getsize(svg)/1024:6.1f} KB")


def main():
    flat = flatten()
    body = inner(trace(posterise(flat)))

    open(OUT + "sepahanfelez-logo.svg", "w", encoding="utf-8").write(header_logo(body))
    open(OUT + "sepahanfelez-logo-footer.svg", "w", encoding="utf-8").write(footer_banner(body))
    open(OUT + "favicon.svg", "w", encoding="utf-8").write(favicon(body))

    sys.path.insert(0, os.environ.get("SHAPER_DIR", HERE))
    from make_logo import Shaper, fit
    sh = Shaper("/home/mlops/mohammad/ahanamn-src/public_html/fonts/IRANSansWeb_FaNum_Bold.ttf")
    sub_d, sub_w, _ = fit(sh, "تولیدکننده مفتول، توری و سیم خاردار", 860, 40)
    url_d, url_w, _ = fit(sh, "sepahanfelez.ir", 420, 32,
                          direction="ltr", script="Latn", language="en")
    tagline = (f'<g fill="{DARK}" transform="translate({(1200-sub_w)/2:.2f},528)">{sub_d}</g>'
               f'<g fill="#b42332" transform="translate({(1200-url_w)/2:.2f},582)">{url_d}</g>')

    open("/tmp/og.svg", "w", encoding="utf-8").write(og_image(body, tagline))
    cairosvg.svg2png(url="/tmp/og.svg", write_to=OUT + "og-image.png",
                     output_width=1200, output_height=630, background_color="white")
    for size in (32, 180):
        cairosvg.svg2png(url=OUT + "favicon.svg", write_to=f"{OUT}favicon-{size}.png",
                         output_width=size, output_height=size)

    print("fidelity at the size the header renders the mark:")
    report(SRC_SVG, "supplied SVG", flat)
    report(OUT + "sepahanfelez-logo.svg", "rebuilt from the PNG", flat)


if __name__ == "__main__":
    main()
