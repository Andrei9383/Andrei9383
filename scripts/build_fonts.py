#!/usr/bin/env python3
"""
One-off: turn the variable TTFs in fonts/src/ into small static, subset WOFF2 files
in fonts/, which render_cards.py embeds into each SVG as data URIs (an SVG shown
through <img> on GitHub cannot load external fonts).

Fonts (SIL OFL 1.1): Geist (text), Geist Mono (labels, numbers, ASCII).
Also writes fonts/geist-600.ttf, used by render_cards.py to rasterise the halftone name.

    python scripts/build_fonts.py
"""
import os

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = os.path.join(ROOT, "fonts", "src")
OUT = os.path.join(ROOT, "fonts")

# printable ASCII + the few typographic marks the cards use
CHARS = "".join(chr(c) for c in range(0x20, 0x7F)) + "·—–’‘“”…★↗→←↑↓●▲█░▒▓×"

JOBS = [
    ("Geist[wght].ttf", 400, "geist-400.woff2"),
    ("Geist[wght].ttf", 500, "geist-500.woff2"),
    ("Geist[wght].ttf", 600, "geist-600.woff2"),
    ("GeistMono[wght].ttf", 400, "geistmono-400.woff2"),
    ("GeistMono[wght].ttf", 500, "geistmono-500.woff2"),
    ("Geist[wght].ttf", 600, "geist-600.ttf"),
]

for src, wght, out in JOBS:
    font = TTFont(os.path.join(SRC, src))
    font = instancer.instantiateVariableFont(font, {"wght": wght})
    opts = subset.Options()
    opts.flavor = "woff2" if out.endswith("woff2") else None
    opts.layout_features = ["kern", "liga", "tnum"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    s = subset.Subsetter(opts)
    s.populate(text=CHARS)
    s.subset(font)
    path = os.path.join(OUT, out)
    font.flavor = opts.flavor
    font.save(path)
    cmap = font.getBestCmap()
    missing = [c for c in CHARS if ord(c) not in cmap]
    print(f"{out}: {os.path.getsize(path) // 1024} KB, missing: {''.join(missing) or '-'}")
