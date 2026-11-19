#!/usr/bin/env python3
"""
Render the profile README cards as SVGs into cards/, each in a dark and a light
variant (<name>-dark.svg / <name>-light.svg), swapped by <picture> in the README.

Design language: monochrome print. Geist + Geist Mono, one cobalt accent, and three
textures only: 1-bit dithered images (Atkinson), halftone dots for data, and soft
ASCII glows. The only motion is an ordered-dither dissolve as things load.

GitHub shows these through <img>: CSS animations run, JS does not, external
resources do not load, so fonts and bitmaps are embedded as data URIs.

Inputs: data/content.json (copy), data/profile.json (fetch_data.py), assets/.
STATIC=1 renders end states (for previews).

    python scripts/render_cards.py
"""
import base64
import calendar
import datetime
import io
import json
import math
import os
from html import escape

import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "cards")
FONTS = os.path.join(ROOT, "fonts")
ASSETS = os.path.join(ROOT, "assets")
CONTENT = json.load(open(os.path.join(ROOT, "data", "content.json")))
DATA = json.load(open(os.path.join(ROOT, "data", "profile.json")))
STATIC = bool(os.environ.get("STATIC"))

W = 880        # GitHub README column at 100%
GAP = 12       # space between cards, baked into each canvas
R = 12         # card corner radius
PAD = 32

THEMES = {
    "dark": dict(
        surface="#0a0a0b", line="#1f1f23", ink="#ededef", soft="#a1a1a8", muted="#6e6e76",
        faint="#232327", accent="#5872ff", pix="#e6e6ea",
        glow=["#1e3fd8", "#38bdf8", "#a5d8ff", "#f6f8ff"],
    ),
    "light": dict(
        surface="#f5f5f3", line="#e3e3df", ink="#111113", soft="#4f4f56", muted="#8b8b92",
        faint="#dededa", accent="#1e3fd8", pix="#111113",
        glow=["#b9c7ff", "#6f88ff", "#2a48e6", "#0b1a8a"],
    ),
}

FONT_FILES = {
    "s4": ("Geist", 400, "geist-400.woff2"),
    "s5": ("Geist", 500, "geist-500.woff2"),
    "s6": ("Geist", 600, "geist-600.woff2"),
    "m4": ("Geist Mono", 400, "geistmono-400.woff2"),
    "m5": ("Geist Mono", 500, "geistmono-500.woff2"),
}
SANS = "Geist, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace"

# octicon star-fill (MIT), 16x16
STAR = ("M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 "
        "4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 "
        "6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z")

# ---------------------------------------------------------------- text
_metrics = {}


def measure(s, key, size, ls=0.0):
    if key not in _metrics:
        f = TTFont(os.path.join(FONTS, FONT_FILES[key][2]))
        _metrics[key] = (f.getBestCmap(), f["hmtx"].metrics, f["head"].unitsPerEm)
    cmap, hmtx, upm = _metrics[key]
    adv = sum(hmtx[cmap[ord(c)]][0] if ord(c) in cmap else upm * 0.55 for c in s)
    return adv * size / upm + ls * len(s)


def cap(key, size):
    """Cap height in px, from the embedded font (used to put text exactly on the card margins)."""
    f = TTFont(os.path.join(FONTS, FONT_FILES[key][2]))
    return f["OS/2"].sCapHeight / f["head"].unitsPerEm * size


def wrap(s, key, size, width):
    lines, line = [], ""
    for word in s.split():
        trial = f"{line} {word}".strip()
        if line and measure(trial, key, size) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + ([line] if line else [])


def fit(s, key, size, width):
    if measure(s, key, size) <= width:
        return s
    while s and measure(s + "…", key, size) > width:
        s = s[:-1]
    return s.rstrip(" ,·;") + "…"


def text(x, y, s, key, size, fill, anchor="start", ls=None, extra=""):
    fam, weight, _ = FONT_FILES[key]
    family = MONO if "Mono" in fam else SANS
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    l = f' letter-spacing="{ls}"' if ls is not None else ""
    return (f'<text x="{x:.2f}" y="{y:.2f}" font-family="{family}" font-weight="{weight}" '
            f'font-size="{size}" fill="{fill}"{a}{l} {extra}>{escape(s)}</text>')


def label(x, y, s, t, anchor="start", fill=None):
    return text(x, y, s.upper(), "m4", 10.5, fill or t["muted"], anchor=anchor, ls=1.2)


# ---------------------------------------------------------------- svg shell
CSS = """
@keyframes on{from{opacity:0}to{opacity:1}}
.fi{opacity:0;animation:on .9s ease both}
.dz{opacity:0;animation:on .28s ease-out both}
.fr{opacity:0}
@media (prefers-reduced-motion: reduce){.fi,.dz{animation:none;opacity:1}.nm circle,.fr{animation:none!important}.f0{opacity:1}}
"""
STATIC_CSS = ".fi,.dz{animation:none!important;opacity:1!important}.nm circle,.fr{animation:none!important}.f0{opacity:1!important}"


def font_face(keys):
    out = []
    for k in sorted(set(keys)):
        fam, weight, fn = FONT_FILES[k]
        b64 = base64.b64encode(open(os.path.join(FONTS, fn), "rb").read()).decode()
        out.append(f"@font-face{{font-family:'{fam}';font-weight:{weight};"
                   f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "".join(out)


def svg(w, h, body, fonts, aria, defs="", extra_css=""):
    style = font_face(fonts) + CSS + extra_css + (STATIC_CSS if STATIC else "")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.3f}" height="{h}" viewBox="0 0 {w:.3f} {h}" '
            f'role="img" aria-label="{escape(aria)}"><title>{escape(aria)}</title>'
            f"<defs>{defs}</defs><style>{style}</style>{body}</svg>")


def card(x, w, h, t, y=0):
    return (f'<rect x="{x + .5:.3f}" y="{y + .5}" width="{w - 1:.3f}" height="{h - 1}" rx="{R}" '
            f'fill="{t["surface"]}" stroke="{t["line"]}"/>')


def delay(s):
    return f'style="animation-delay:{s:.2f}s"'


def star(x, y, size, fill):
    return (f'<svg x="{x:.2f}" y="{y:.2f}" width="{size}" height="{size}" viewBox="0 0 16 16">'
            f'<path d="{STAR}" fill="{fill}"/></svg>')


_written = []


def write(name, content):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        f.write(content)
    _written.append((name, len(content)))


# ---------------------------------------------------------------- textures
def bayer(n=8):
    m = np.array([[0, 2], [3, 1]])
    while m.shape[0] < n:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return m


BAYER = bayer(8)  # 0..63, the reveal order for every dissolve


def atkinson(field):
    """1-bit Atkinson dither of a 0..1 float field."""
    a = field.astype(np.float32).copy()
    h, w = a.shape
    out = np.zeros((h, w), bool)
    for y in range(h):
        for x in range(w):
            old = a[y, x]
            new = 1.0 if old >= 0.5 else 0.0
            out[y, x] = new > 0
            err = (old - new) / 8
            for dx, dy in ((1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2)):
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and yy < h:
                    a[yy, xx] += err
    return out


def png_uri(bits, color):
    """bits -> 2-colour palette PNG (transparent / colour) as a data URI."""
    img = Image.fromarray(bits.astype(np.uint8), "P")
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    img.putpalette([0, 0, 0, r, g, b])
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True, transparency=0)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def dither_image(bits, x, y, px, color, start=0.2, layers=8, step=0.09):
    """Draw a 1-bit bitmap at pixel size px, revealed in ordered-dither layers."""
    h, w = bits.shape
    rank = BAYER[np.arange(h)[:, None] % 8, np.arange(w)[None, :] % 8] * layers // 64
    out = []
    for k in range(layers):
        layer = bits & (rank == k)
        out.append(f'<image class="dz" x="{x:.2f}" y="{y:.2f}" width="{w * px:.2f}" '
                   f'height="{h * px:.2f}" preserveAspectRatio="none" style="image-rendering:pixelated;'
                   f'animation-delay:{start + k * step:.2f}s" href="{png_uri(layer, color)}"/>')
    return "".join(out)


def ascii_rows(field, x, y, lh, size, ramp_colors):
    """Gradient-ASCII rows: a 0..1 field drawn with ' .=+xX0S8#@', coloured along the cobalt ramp."""
    chars = " .=+xX0S8#@"
    rows = []
    h, w = field.shape
    for r in range(h):
        spans = []  # [tone, text]
        for c in range(w):
            v = field[r, c]
            ch = chars[min(len(chars) - 1, int(v * len(chars)))]
            tone = min(len(ramp_colors) - 1, int(v * len(ramp_colors)))
            if ch == " ":
                if spans:
                    spans[-1][1] += " "
                else:
                    spans.append([tone, " "])
            elif spans and (spans[-1][0] == tone or not spans[-1][1].strip()):
                spans[-1][0] = tone
                spans[-1][1] += ch
            else:
                spans.append([tone, ch])
        if not any(s.strip() for _, s in spans):
            continue
        spans[-1][1] = spans[-1][1].rstrip()
        ts = "".join(f'<tspan fill="{ramp_colors[tn]}">{escape(s)}</tspan>' for tn, s in spans)
        rows.append(f'<text x="{x:.2f}" y="{y + (r + 1) * lh:.2f}" font-family="{MONO}" font-size="{size}" '
                    f'xml:space="preserve">{ts}</text>')
    return "".join(rows)


def ascii_loop(make_field, frames, period, x, y, lh, size, ramp_colors, seed=0):
    """A looping Gradient-ASCII animation: `frames` pre-rendered fields shown one after another
    (CSS step animation, no JS), with a little per-frame character shimmer."""
    rng = np.random.default_rng(seed)
    out = []
    for f in range(frames):
        field = make_field(f / frames)
        field = np.clip(field + (rng.random(field.shape) - 0.5) * 0.09 * (field > 0.06), 0, 0.999)
        d = -(frames - f) * period / frames
        out.append(f'<g class="fr f{f}" style="animation-delay:{d:.3f}s">'
                   f'{ascii_rows(field, x, y, lh, size, ramp_colors)}</g>')
    css = (f"@keyframes fr{{0%{{opacity:1}}{100 / frames:.4f}%{{opacity:0}}100%{{opacity:0}}}}"
           f".fr{{animation:fr {period}s steps(1,end) infinite}}")
    return "".join(out), css


# ---------------------------------------------------------------- illustrations
def lightning_bits(wpx, hpx):
    img = Image.open(os.path.join(ASSETS, "bolt.jpg")).convert("L")
    img = img.filter(ImageFilter.MaxFilter(3))
    img = ImageOps.fit(img, (wpx, hpx), Image.Resampling.BOX, centering=(0.5, 0.5))
    a = np.asarray(img, np.float32) / 255
    a = np.clip((a - 0.07) / 0.7, 0, 1)
    return atkinson(a)


def field_spectrogram(w, h, seed=3):
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 1, w)[None, :]
    f = np.linspace(1, 0, h)[:, None]
    a = rng.random((h, w)) * 0.22
    for hz in (0.12, 0.24):  # mains hum
        a = a + 0.18 * np.exp(-((f - hz) / 0.006) ** 2)
    for tc, f0, sp, width in ((0.16, 0.62, 0.20, 0.05), (0.43, 0.44, 0.16, 0.08), (0.66, 0.74, 0.14, 0.06), (0.88, 0.55, 0.22, 0.04)):
        for harm, gain in ((1, 1.0), (0.5, 0.55)):
            curve = f0 * harm + sp * harm * -np.tanh((t - tc) / width) * 0.5
            env = np.exp(-((t - tc) / 0.22) ** 2)
            a = a + gain * env * np.exp(-((f - curve) / 0.016) ** 2)
    return np.clip(a, 0, 1)


def field_forecast(w, h):
    x = np.linspace(0, 3, w)[None, :]
    y = np.linspace(1, 0, h)[:, None]
    day = np.clip(np.sin((x % 1) * np.pi), 0, None) ** 1.6
    p50 = 0.12 + 0.68 * day * (1 - 0.08 * np.floor(x))
    sigma = 0.035 + 0.11 * day * (x / 3)
    band = np.exp(-((y - p50) / sigma) ** 2 / 2) * 0.75
    line = np.exp(-((y - p50) / 0.012) ** 2)
    return np.clip(band + line, 0, 1)


def field_wind(w, h):
    x = np.linspace(0, 1, w)[None, :]
    y = np.linspace(0, 1, h)[:, None]
    warp = 0.10 * np.sin(x * 7.0 + 0.6) + 0.05 * np.sin(x * 15.0 + y * 4) + 0.18 * y * x
    s = np.sin((y + warp) * 2 * np.pi * 8.5)
    lines = np.clip(s, 0, 1) ** 10
    fade = np.clip(1.15 - np.abs(x - 0.55) * 1.4, 0, 1)
    return np.clip(lines * (0.35 + 0.75 * fade), 0, 1)


def field_photo(path, w, h, centering=(0.5, 0.5)):
    img = Image.open(path).convert("L")
    img = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS, centering=centering)
    img = ImageOps.autocontrast(img, cutoff=2)
    return np.asarray(img, np.float32) / 255


def glow_field(w, h, shape, phase=0.0, cell_w=4.8, cell_h=9.4):
    """Soft glow shapes for the tiles (0..1 per character cell), in true pixel proportions.
    phase in [0, 1) moves the shape along a seamless loop."""
    xs = ((np.arange(w) + .5) / w * 2 - 1) * (w * cell_w) / (h * cell_h)
    ys = (np.arange(h) + .5) / h * 2 - 1
    X, Y = xs[None, :], ys[:, None]
    th = 2 * np.pi * phase
    if shape == "rise":      # light rising off the bottom edge, breathing and drifting
        v = (np.exp(-((X - 0.35 * np.sin(th)) / (1.25 + 0.2 * np.cos(th))) ** 2)
             * np.exp((Y - 1) * (1.75 - 0.45 * np.sin(th))))
    elif shape == "pinch":   # a horizontal lens with a wave running through it
        yc = Y - 0.12 * np.sin(X * 1.6 - th)
        v = np.exp(-(yc / ((0.16 + 0.10 * X * X) * (1 + 0.3 * np.sin(th)))) ** 2) * np.exp(-(X / 2.0) ** 2)
    else:                    # eclipse: a ring with a bright arc travelling around it
        r = np.sqrt(X ** 2 + Y ** 2)
        ang = np.arctan2(Y, X)
        v = np.exp(-((r - 0.74) / 0.15) ** 2) * (0.35 + 0.65 * (0.5 + 0.5 * np.cos(ang - th)) ** 1.5)
    return np.clip(v * 0.98, 0, 0.999)


# ---------------------------------------------------------------- data
DAYS = DATA["days"]
STARS = {k: v["stargazerCount"] for k, v in DATA["repos"].items()}
TOTAL = DATA["total"]
TODAY = datetime.date.fromisoformat(DAYS[-1]["date"])


def fmt(n):
    return f"{n:,}"


def subst(s):
    return (s.replace("{stars}", fmt(STARS.get(CONTENT["tiles"][0]["repo"], 0)))
             .replace("{blucast_stars}", fmt(STARS.get("Andrei9383/Blucast", 0))))


# ---------------------------------------------------------------- contour (after benday)
def _edt1d(f):
    """Felzenszwalb & Huttenlocher 1D squared distance transform."""
    n = len(f)
    d = np.zeros(n)
    v = np.zeros(n, int)
    z = np.zeros(n + 1)
    k, z[0], z[1] = 0, -1e20, 1e20
    for q in range(1, n):
        s_ = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k])
        while s_ <= z[k]:
            k -= 1
            s_ = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k])
        k += 1
        v[k], z[k], z[k + 1] = q, s_, 1e20
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        d[q] = (q - v[k]) ** 2 + f[v[k]]
    return d


def distance_inside(mask):
    """Exact Euclidean distance from each inside pixel to the nearest outside one."""
    g = np.where(mask, 1e20, 0.0)
    g = np.array([_edt1d(col) for col in g.T]).T
    g = np.array([_edt1d(row) for row in g])
    return np.sqrt(g)


CONTOUR_SPEED = 0.75   # benday's contour at 3/4 speed
CONTOUR_BANDS = 32


def contour_css(cls, bands, frames=24):
    """benday 'contour': w = (sin(2.2t - 6.5d) + 1) / 2, g = w^1.6, alpha .16+.84g, size grows with g.
    One keyframe loop sampled from that, and each depth band d gets its phase as a delay."""
    period = 2 * math.pi / (2.2 * CONTOUR_SPEED)
    steps = []
    for i in range(frames + 1):
        u = i / frames
        g = ((math.sin(2 * math.pi * u) + 1) / 2) ** 1.6
        steps.append(f"{u * 100:.2f}%{{opacity:{0.3 + 0.7 * g:.3f};transform:scale({0.62 + 0.48 * g:.3f})}}")
    css = (f"@keyframes ct{{{''.join(steps)}}}"
           f".{cls} circle{{transform-box:fill-box;transform-origin:center;animation:ct {period:.3f}s linear infinite}}")
    for b in range(bands):
        d = (b + 0.5) / bands
        lag = d * 6.5 / (2.2 * CONTOUR_SPEED)
        css += f".c{b} circle{{animation-delay:{lag - period * math.ceil(lag / period):.3f}s}}"
    return css


# ---------------------------------------------------------------- cards
def halftone_name(lines, x, y, size, line_gap, pitch, color, start):
    """Rasterise the name in Geist 600, then redraw it as a halftone dot field."""
    S = 4
    font = ImageFont.truetype(os.path.join(FONTS, "geist-600.ttf"), size * S)
    asc, desc = font.getmetrics()
    widths = [font.getbbox(l)[2] for l in lines]
    w4 = max(widths) + 8 * S
    h4 = int(asc + desc + (len(lines) - 1) * size * S * line_gap)
    img = Image.new("L", (w4, h4), 0)
    dr = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        dr.text((0, int(i * size * S * line_gap)), l, font=font, fill=255)
    img = img.crop(img.getbbox())  # ink only: no ascender air above the caps
    w4, h4 = img.size
    cw, ch = math.ceil(w4 / S / pitch), math.ceil(h4 / S / pitch)
    img = img.crop((0, 0, int(cw * pitch * S), int(ch * pitch * S)))
    small = np.asarray(img.resize((cw, ch), Image.Resampling.BOX), np.float32) / 255
    # depth of every dot inside the letters, measured on a 4x finer grid for smooth bands
    fine = np.asarray(img.resize((cw * 4, ch * 4), Image.Resampling.BOX), np.float32) / 255
    depth = distance_inside(fine > 0.5)
    depth = depth[2::4, 2::4][:ch, :cw] / max(1e-6, depth.max())
    bands = CONTOUR_BANDS
    groups = [[[] for _ in range(bands)] for _ in range(8)]
    rmax = pitch * 0.58
    for r in range(ch):
        for c in range(cw):
            v = small[r, c]
            if v < 0.1:
                continue
            band = min(bands - 1, int(depth[r, c] * bands))
            groups[BAYER[r % 8, c % 8] // 8][band].append(
                f'<circle cx="{x + c * pitch + pitch / 2:.1f}" cy="{y + r * pitch + pitch / 2:.1f}" '
                f'r="{rmax * math.sqrt(v):.2f}"/>')
    body = "".join(
        f'<g class="dz" {delay(start + k * 0.08)}>' +
        "".join(f'<g class="c{b}">{"".join(g)}</g>' for b, g in enumerate(bg) if g) + "</g>"
        for k, bg in enumerate(groups))
    # contour: a wave runs through the letters from their outline to their core, forever
    return f'<g class="nm" fill="{color}">{body}</g>', contour_css("nm", bands), ch * pitch


def hero(t, mode):
    m = PAD + 4                      # one margin for top, left and bottom
    x = m
    first, last = CONTENT["name"]
    name, css, name_h = halftone_name([first, last], x - 2, m, 84, 0.9, 4.0, t["ink"], start=0.05)
    lines = wrap(CONTENT["tagline"], "s4", 16, 450)
    y_tag = m + name_h + 34 + cap("s4", 16)
    y_focus = y_tag + (len(lines) - 1) * 24 + 34
    h = int(round(y_focus + m))
    body = [card(0, W, h, t)]

    px = 2
    aw = 350
    bits = lightning_bits(aw // px, (h - 2) // px)
    ax = W - aw - 1
    defs = f'<clipPath id="hc"><rect x="1" y="1" width="{W - 2}" height="{h - 2}" rx="{R - 1}"/></clipPath>'
    body.append(f'<g clip-path="url(#hc)">{dither_image(bits, ax, 1, px, t["pix"], start=0.15)}</g>')

    body.append(name)
    for i, line in enumerate(lines):
        body.append(text(x, y_tag + i * 24, line, "s4", 16, t["soft"], extra=f'class="fi" {delay(0.5)}'))
    body.append(label(x, y_focus, CONTENT["focus"], t, fill=t["ink"]))
    aria = f"{first} {last}. {CONTENT['tagline']}"
    write(f"hero-{mode}.svg", svg(W, h + GAP, "".join(body), ["s4", "m4"], aria, defs, css))


def weeks_grid():
    first = datetime.date.fromisoformat(DAYS[0]["date"])
    off = (first.weekday() + 1) % 7  # sunday-first, like GitHub
    return [((i + off) // 7, (i + off) % 7, d) for i, d in enumerate(DAYS)]


def levels():
    nz = sorted(d["count"] for d in DAYS if d["count"])
    q = [nz[int(len(nz) * f)] for f in (0.25, 0.5, 0.75)] if nz else [1, 2, 3]
    return lambda c: 0 if c == 0 else 1 if c <= q[0] else 2 if c <= q[1] else 3 if c <= q[2] else 4


def heatmap(t, mode):
    y_title = PAD + cap("s5", 19)
    top = y_title + 22
    pitch = (W - 2 * PAD) / (weeks_grid()[-1][0] + 1)
    y_months = top + 7 * pitch + 26
    h = int(round(y_months + PAD))
    body = [card(0, W, h, t)]
    body.append(text(PAD, y_title, "Contributions", "s5", 19, t["ink"], ls=-0.3))
    cells = weeks_grid()
    ncols = cells[-1][0] + 1
    lvl = levels()
    radii = [1.1, 2.1, 3.1, 4.1, 5.1]
    k = pitch / 15.4
    groups = [[] for _ in range(8)]
    for col, row, d in cells:
        L = lvl(d["count"])
        cx, cy = PAD + col * pitch + pitch / 2, top + row * pitch + pitch / 2
        today = d["date"] == DAYS[-1]["date"]
        fill = t["accent"] if today else (t["faint"] if L == 0 else t["ink"])
        r = max(radii[L], 2.4) if today else radii[L]
        groups[BAYER[row % 8, col % 8] // 8].append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r * k:.2f}" fill="{fill}"/>')
    body += [f'<g class="dz" {delay(0.1 + i * 0.08)}>{"".join(g)}</g>' for i, g in enumerate(groups)]
    seen = set()
    for col, row, d in cells:
        dt = datetime.date.fromisoformat(d["date"])
        if dt.day == 1 and dt.month not in seen and col < ncols - 2:
            seen.add(dt.month)
            body.append(label(PAD + col * pitch + pitch / 2, y_months, calendar.month_abbr[dt.month], t,
                              anchor="middle"))
    aria = f"Contribution graph: {TOTAL} contributions in the last year"
    write(f"heatmap-{mode}.svg", svg(W, h + GAP, "".join(body), ["s5", "m4"], aria))


def months():
    totals = {}
    for d in DAYS:
        totals[d["date"][:7]] = totals.get(d["date"][:7], 0) + d["count"]
    out, y, m = [], TODAY.year, TODAY.month
    for _ in range(12):
        out.append((y, m, totals.get(f"{y:04d}-{m:02d}", 0)))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def year(t, mode):
    y_label = PAD + cap("m4", 10.5)
    y_num = y_label + 16 + cap("s6", 56)
    base = y_num + 116            # bottom of the dot columns
    y_months = base + 20
    h = int(round(y_months + PAD))
    body = [card(0, W, h, t)]
    body.append(label(PAD, y_label, "The last 12 months", t))
    num = fmt(TOTAL)
    body.append(text(PAD - 2, y_num, num, "s6", 56, t["ink"], ls=-2.2))
    body.append(text(PAD + measure(num, "s6", 56, -2.2) + 8, y_num, "contributions", "s4", 20, t["soft"], ls=-0.2))

    # Ben-Day columns: each month is a stack of dots
    ms = months()
    peak = max(ms, key=lambda m: m[2])
    left = PAD
    colw = (560 - PAD) / 12
    dot, per_row, max_rows = 6.0, 4, 13
    groups = [[] for _ in range(8)]
    for i, (yy, mm, v) in enumerate(ms):
        rows = max(1, round(max_rows * v / max(1, peak[2]))) if v else 0
        now = (yy, mm) == (TODAY.year, TODAY.month)
        fill = t["accent"] if (yy, mm) == peak[:2] else (t["muted"] if now else t["ink"])
        for r in range(rows):
            for c in range(per_row):
                cx = left + i * colw + c * dot + dot / 2
                cy = base - r * dot - dot / 2
                groups[BAYER[r % 8, (i * per_row + c) % 8] // 8].append(
                    f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{dot * 0.36:.2f}" fill="{fill}"/>')
        body.append(label(left + i * colw, y_months, calendar.month_abbr[mm], t))
        if (yy, mm) == peak[:2]:
            body.append(text(left + i * colw, base - rows * dot - 8, str(v), "m5", 10.5, t["accent"]))
    body += [f'<g class="dz" {delay(0.15 + k * 0.08)}>{"".join(g)}</g>' for k, g in enumerate(groups)]

    active = sum(1 for d in DAYS if d["count"])
    best = max(DAYS, key=lambda d: d["count"])
    bd = datetime.date.fromisoformat(best["date"])
    stats = [
        (f"{active}", f"/ {len(DAYS)}", "days with a contribution"),
        (str(best["count"]), "", f"on the busiest day · {calendar.month_abbr[bd.month]} {bd.day}"),
        (str(ms[-1][2]), "", f"so far in {calendar.month_name[TODAY.month]}"),
    ]
    sx = 616
    body.append(f'<line x1="{sx - 24}" x2="{sx - 24}" y1="{PAD}" y2="{h - PAD}" stroke="{t["line"]}"/>')
    first_y = PAD + cap("s6", 28)
    step = (y_months - 22 - first_y) / 2   # last caption lands on the month-label baseline
    for i, (big, small, caption) in enumerate(stats):
        y = first_y + i * step
        body.append(text(sx, y, big, "s6", 28, t["ink"], ls=-0.8))
        if small:
            body.append(text(sx + measure(big, "s6", 28, -0.8) + 6, y, small, "s4", 16, t["muted"]))
        body.append(label(sx, y + 22, caption, t))
    aria = f"{TOTAL} contributions in the last 12 months; {active} active days; busiest day {best['count']}"
    write(f"year-{mode}.svg", svg(W, h + GAP, "".join(body), ["s4", "s6", "m4", "m5"], aria))


def tiles(t, mode):
    cw = (W - 2 * GAP) / 3
    ip = 22                                      # tile inner padding (sides, below divider, bottom)
    y_lab = 112 + ip + cap("m4", 10.5)
    y_val = y_lab + 36
    y_txt = y_val + 25
    nlines = max(len(wrap(subst(tl["text"]), "s4", 12.5, cw - 2 * ip)[:3]) for tl in CONTENT["tiles"])
    h = int(round(y_txt + (nlines - 1) * 17 + ip + 2))
    shapes = ["rise", "pinch", "eclipse"]
    for i, tile in enumerate(CONTENT["tiles"]):
        x = [0, GAP / 3, 2 * GAP / 3][i]
        body = [card(x, cw, h, t)]
        fs, lh = 8, 9.4
        cols, rows = int((cw - 24) / (fs * 0.6)), 10
        loop, css = ascii_loop(lambda ph, sh=shapes[i]: glow_field(cols, rows, sh, ph), 30, 5.0,
                               x + 12, 10, lh, fs, t["glow"], seed=i)
        body.append(f'<g class="fi" {delay(0.2 + i * 0.15)}>{loop}</g>')
        body.append(f'<line x1="{x + 1}" x2="{x + cw - 1}" y1="112.5" y2="112.5" stroke="{t["line"]}"/>')
        body.append(label(x + ip, y_lab, tile["label"], t))
        body.append(text(x + cw - ip, y_lab + 1, "↗", "m4", 12, t["muted"], anchor="end"))
        body.append(text(x + ip - 1, y_val, subst(tile["value"]), "s6", 26, t["ink"], ls=-0.7))
        for j, line in enumerate(wrap(subst(tile["text"]), "s4", 12.5, cw - 44)[:3]):
            body.append(text(x + ip, y_txt + j * 17, line, "s4", 12.5, t["soft"]))
        aria = f"{tile['label']}: {subst(tile['value'])}. {subst(tile['text'])}"
        write(f"tile-{i}-{mode}.svg", svg(W / 3, h + GAP, "".join(body), ["s4", "s6", "m4"], aria, extra_css=css))


def section_title(t, mode, name, title, note):
    h = 58
    body = [text(2, 38, title, "s5", 19, t["ink"], ls=-0.3), label(W - 2, 37, note, t, anchor="end")]
    write(f"title-{name}-{mode}.svg", svg(W, h, "".join(body), ["s5", "m4"], title))


ILLUSTRATIONS = {
    "Blucast": lambda w, h: field_photo(os.path.join(ASSETS, "blucast.jpg"), w, h),
    "AudioBolt": field_spectrogram,
    "WattSentry": field_forecast,
    "WindMon": field_wind,
}
_bits_cache = {}


def projects(t, mode):
    cw = (W - GAP) / 2
    h = 296
    ih = 140
    px = 2
    for i, p in enumerate(CONTENT["projects"]):
        x = 0 if i % 2 == 0 else GAP / 2
        body = [card(x, cw, h, t)]
        key = p["name"]
        if key not in _bits_cache:
            _bits_cache[key] = atkinson(ILLUSTRATIONS[key](int((cw - 2) // px), ih // px))
        cid = f"pc{i}"
        r = R - 1
        defs = (f'<clipPath id="{cid}"><path d="M{x + 1:.2f},{ih} V{r + 1} a{r},{r} 0 0 1 {r},-{r} '
                f'H{x + cw - 1 - r:.2f} a{r},{r} 0 0 1 {r},{r} V{ih} Z"/></clipPath>')
        body.append(f'<g clip-path="url(#{cid})">{dither_image(_bits_cache[key], x + 1, 1, px, t["pix"], start=0.1 + i * 0.1)}</g>')
        body.append(f'<line x1="{x + 1}" x2="{x + cw - 1}" y1="{ih + .5}" y2="{ih + .5}" stroke="{t["line"]}"/>')
        y0 = ih + 36
        body.append(text(x + 22, y0, p["name"], "s6", 18, t["ink"], ls=-0.3))
        meta_r = x + cw - 22
        stars = STARS.get(p["repo"], 0)
        if stars:
            s = fmt(stars)
            body.append(text(meta_r, y0 - 1, s, "m4", 11, t["muted"], anchor="end"))
            meta_r -= measure(s, "m4", 11) + 15
            body.append(star(meta_r, y0 - 10.5, 11, t["muted"]))
            meta_r -= 10
        body.append(text(meta_r, y0 - 1, p["lang"].upper(), "m4", 10.5, t["muted"], anchor="end", ls=1.0))
        for j, line in enumerate(wrap(p["pitch"], "s4", 13, cw - 44)[:3]):
            body.append(text(x + 22, y0 + 26 + j * 19, line, "s4", 13, t["soft"]))
        body.append(label(x + 22, h - 22, p["tag"], t))
        aria = f"{p['name']}: {p['pitch']}"
        write(f"project-{key.lower()}-{mode}.svg", svg(W / 2, h + GAP, "".join(body), ["s4", "s6", "m4"], aria, defs))


def log(t, mode):
    rows = CONTENT["log"]
    y_title = PAD + cap("s5", 19)
    step, top = 34, y_title + 42
    h = int(round(top + (len(rows) - 1) * step + PAD))
    body = [card(0, W, h, t)]
    body.append(text(PAD, y_title, "Log", "s5", 19, t["ink"], ls=-0.3))
    body.append(label(W - PAD, y_title, "projects and hackathons, newest first", t, anchor="end"))
    last = None
    for i, (yr, name, desc) in enumerate(rows):
        y = top + i * step
        body.append(f'<line x1="{PAD}" x2="{W - PAD}" y1="{y - 22.5}" y2="{y - 22.5}" stroke="{t["line"]}"/>')
        if yr != last:
            body.append(text(PAD, y, yr, "m4", 11.5, t["muted"]))
            last = yr
        nx = PAD + 72
        body.append(text(nx, y, name, "s5", 14, t["ink"]))
        dx = nx + 220
        body.append(text(dx, y, fit(subst(desc), "s4", 13, W - PAD - dx), "s4", 13, t["muted"]))
    aria = "Log: " + "; ".join(f"{y} {n}: {subst(d)}" for y, n, d in rows)
    write(f"log-{mode}.svg", svg(W, h + GAP, "".join(body), ["s4", "s5", "m4"], aria))


def main():
    for mode, t in THEMES.items():
        hero(t, mode)
        heatmap(t, mode)
        year(t, mode)
        tiles(t, mode)
        section_title(t, mode, "building", "Selected work", "4 projects")
        projects(t, mode)
        log(t, mode)
    for name, size in _written:
        print(f"wrote cards/{name} ({size // 1024} KB)")


if __name__ == "__main__":
    main()
