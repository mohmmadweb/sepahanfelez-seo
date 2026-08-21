#!/usr/bin/env python3
"""Build the Sepahan Felez wordmark SVGs.

Persian text is shaped with HarfBuzz and written out as outlines, so the
rendered logo does not depend on the viewer having a Persian font.
"""
import sys

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

FONT = "/home/mlops/mohammad/ahanamn-src/public_html/fonts/IRANSansWeb_FaNum_Bold.ttf"

RED = "#b42332"
DARK = "#283264"
BLUE = "#495f9e"


class Shaper:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.data = f.read()
        self.face = hb.Face(self.data)
        self.hbfont = hb.Font(self.face)
        self.upem = self.face.upem
        self.tt = TTFont(path)
        self.glyphset = self.tt.getGlyphSet()
        self.order = self.tt.getGlyphOrder()

    def outline(self, text, size, direction="rtl", script="Arab", language="fa"):
        """Return (svg_path_d, advance_width) with the baseline at y=0,
        y growing downwards (SVG convention)."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.direction = direction
        buf.script = script
        buf.language = language
        hb.shape(self.hbfont, buf, {"kern": True, "liga": True})

        scale = size / self.upem
        x = 0.0
        parts = []
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            name = self.order[info.codepoint]
            pen = SVGPathPen(self.glyphset)
            self.glyphset[name].draw(pen)
            d = pen.getCommands()
            if d:
                # font units -> px, and flip Y (font Y is up, SVG Y is down)
                tx = (x + pos.x_offset * scale)
                ty = (-pos.y_offset * scale)
                parts.append(
                    f'<g transform="translate({tx:.3f},{ty:.3f}) '
                    f'scale({scale:.6f},{-scale:.6f})"><path d="{d}"/></g>'
                )
            x += pos.x_advance * scale
        return "".join(parts), x

    def width(self, text, size, **kw):
        return self.outline(text, size, **kw)[1]


def fit(sh, text, max_width, start_size, **kw):
    """Largest size at or below start_size whose outline fits max_width."""
    size = start_size
    while size > 4:
        d, w = sh.outline(text, size, **kw)
        if w <= max_width:
            return d, w, size
        size -= 0.5
    return d, w, size


def header_logo(sh):
    """Portrait mark, 216x404 — same box as the logo.png it replaces."""
    W, H = 216.0, 404.0

    fa_d, fa_w, _ = fit(sh, "سپاهان فلز", 168.0, 40.0)
    en_d, en_w, _ = fit(sh, "SEPAHAN FELEZ", 158.0, 17.0,
                        direction="ltr", script="Latn", language="en")

    # Outer shield: a vertical hexagon, mirroring the silhouette of the mark
    # it stands in for so the header layout is unchanged.
    shield = "M108,6 L204,58 L204,346 L108,398 L12,346 L12,58 Z"

    # Interior mark: a woven mesh — three warp bars crossed by three weft
    # bars, which is what the company actually manufactures.
    cx, cy, span, bar, gap = 108.0, 158.0, 116.0, 16.0, 34.0
    left, top = cx - span / 2, cy - span / 2
    mesh = []
    for i in range(3):
        off = i * gap
        # vertical (behind)
        mesh.append(f'<rect x="{left + off:.1f}" y="{top:.1f}" width="{bar}" '
                    f'height="{span}" rx="3" fill="{BLUE}"/>')
    for i in range(3):
        off = i * gap
        # horizontal (in front) — the over/under reads as weave
        mesh.append(f'<rect x="{left:.1f}" y="{top + off:.1f}" width="{span}" '
                    f'height="{bar}" rx="3" fill="{RED}"/>')
    mesh = "\n    ".join(mesh)

    fa_x = (W - fa_w) / 2
    fa_y = 288.0
    en_x = (W - en_w) / 2
    en_y = 320.0

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}" role="img" aria-label="سپاهان فلز">
  <title>سپاهان فلز</title>
  <path d="{shield}" fill="#ffffff" stroke="{DARK}" stroke-width="4"/>
  <g>
    {mesh}
  </g>
  <g fill="{DARK}" transform="translate({fa_x:.3f},{fa_y:.3f})">{fa_d}</g>
  <g fill="{BLUE}" transform="translate({en_x:.3f},{en_y:.3f})">{en_d}</g>
  <rect x="46" y="336" width="124" height="3" fill="{RED}"/>
</svg>
'''


def footer_logo(sh):
    """Wide banner, 1695x314 — same box as footer-logo2.png."""
    W, H = 1695.0, 314.0

    fa_d, fa_w, _ = fit(sh, "سپاهان فلز", 660.0, 108.0)
    en_d, en_w, _ = fit(sh, "SEPAHAN FELEZ", 560.0, 34.0,
                        direction="ltr", script="Latn", language="en")

    # Same silhouette as the footer-logo2.png it replaces, traced off it: white
    # across the top, the footer's blue below a curve that dives to the
    # baseline at both edges.
    wave = (f"M0,0 C{W*0.14:.0f},0 {W*0.16:.0f},253 {W*0.30:.0f},253 "
            f"L{W*0.72:.0f},253 "
            f"C{W*0.86:.0f},253 {W*0.88:.0f},0 {W:.0f},0 "
            f"L{W:.0f},{H:.0f} L0,{H:.0f} Z")

    fa_x = (W - fa_w) / 2
    fa_y = 128.0
    en_x = (W - en_w) / 2
    en_y = 218.0

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}" role="img" aria-label="سپاهان فلز">
  <title>سپاهان فلز</title>
  <rect width="{W:.0f}" height="{H:.0f}" fill="#ffffff"/>
  <path d="{wave}" fill="{BLUE}"/>
  <g fill="{DARK}" transform="translate({fa_x:.3f},{fa_y:.3f})">{fa_d}</g>
  <g fill="{RED}" transform="translate({en_x:.3f},{en_y:.3f})">{en_d}</g>
</svg>
'''


def main():
    sh = Shaper(FONT)
    out = sys.argv[1]
    with open(f"{out}/sepahanfelez-logo.svg", "w", encoding="utf-8") as f:
        f.write(header_logo(sh))
    with open(f"{out}/sepahanfelez-logo-footer.svg", "w", encoding="utf-8") as f:
        f.write(footer_logo(sh))
    print("written to", out)


if __name__ == "__main__":
    main()
