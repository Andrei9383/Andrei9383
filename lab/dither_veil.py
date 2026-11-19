"""
Dither Veil, parked for later (removed from the hero on 2026-11-19).

A port of reactbits' DitherVeil (https://reactbits.dev/animations/dither-veil) to a static,
JS-free SVG: a soft brush wanders over a 1-bit dithered image and reveals the photo beneath
it through a Bayer-thresholded edge with a thin cobalt rim; a periodic "strike" shockwave
ring stands in for click bursts. Rendered examples: lab/hero-veil-dark.svg, -light.svg.

Checked in Chromium and Firefox (Safari untested). Notes from building it:
  - filter and mask ids must differ (a shared id silently drops the mask in Chromium);
  - keep alpha exactly 1 through the arithmetic composite, or Firefox drops the photo;
  - the Bayer tile's minimum must exceed 1/64 or its lowest cell passes at zero.

To use it again, in render_cards.hero():
    from lab.dither_veil import dither_veil   (with scripts/ on sys.path)
    veil, vdefs = dither_veil(t, mode, ax, 1, aw, (h - 2) // px * px, cell=px)
and append `veil` inside the hero's clip group, `vdefs` to its defs.
"""
import base64
import io
import math
import os
import sys

import numpy as np
from PIL import Image, ImageFilter, ImageOps

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from render_cards import ASSETS, BAYER, delay  # noqa: E402


def photo_uri(mode, t, w, h):
    """The un-dithered avatar for the veil to reveal: the photo itself in dark mode, its
    negative toned from paper to ink in light mode (so it matches the inverted dither)."""
    img = Image.open(os.path.join(ASSETS, "bolt.jpg")).convert("RGB").filter(ImageFilter.MaxFilter(3))
    img = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    if mode == "dark":  # same grade as the dither, so the reveal reads as the same bolt, sharper
        rgb = np.asarray(img, np.float32) / 255
        img = Image.fromarray((np.clip((rgb - 0.05) / 0.62, 0, 1) * 255).astype(np.uint8))
    if mode == "light":
        lum = np.asarray(img.convert("L"), np.float32)[..., None] / 255
        lum = np.clip((lum - 0.05) / 0.6, 0, 1)
        paper = np.array([int(t["surface"][i:i + 2], 16) for i in (1, 3, 5)], np.float32)
        ink = np.array([int(t["ink"][i:i + 2], 16) for i in (1, 3, 5)], np.float32)
        img = Image.fromarray((paper + (ink - paper) * lum).astype(np.uint8))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def bayer_tile_uri(cell):
    tile = ((BAYER + 2) / 66 * 255).astype(np.uint8)  # min > 1/64 so nothing passes at zero
    img = Image.fromarray(tile, "L").resize((8 * cell, 8 * cell), Image.Resampling.NEAREST)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def wander_path(x0, y0, w, h, n=240):
    """A closed Lissajous-style path (after DitherVeil's wanderAt, made periodic so it loops)."""
    pts = []
    for i in range(n + 1):
        a = 2 * math.pi * i / n
        px = 0.5 + 0.30 * math.sin(a) + 0.07 * math.sin(3 * a + 0.6)
        py = 0.46 + 0.27 * math.sin(2 * a + 1.1) + 0.06 * math.cos(5 * a)
        pts.append(f"{x0 + px * w:.1f},{y0 + py * h:.1f}")
    return "M" + " L".join(pts) + " Z"


def dither_veil(t, mode, x0, y0, w, h, cell=2, radius=74, loop=16.0, trail=8, rim=0.14):
    """DitherVeil without JS: a soft brush wanders over the dithered image and reveals the photo
    beneath it, through a Bayer-thresholded (so itself dithered) edge with a thin cobalt rim.
    Every few seconds a strike sends a shockwave ring out from where the bolt meets the water."""
    path = wander_path(x0, y0, w, h)
    brushes = []
    for k in range(trail):  # the head, then a fading tail lagging behind it
        lag = k * 0.16
        scale = 1 - k / (trail * 1.35)
        op = (1 - k / trail) ** 1.4
        brushes.append(
            f'<circle r="{radius * scale:.1f}" fill="url(#vb)" fill-opacity="{op:.2f}">'
            f'<animateMotion dur="{loop}s" repeatCount="indefinite" begin="{-lag - 2:.2f}s" path="{path}"/></circle>')
    bx, by = x0 + w * 0.56, y0 + h * 0.86
    burst = (f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="0" fill="none" stroke="#fff" stroke-width="34" stroke-opacity="0">'
             f'<animate attributeName="r" values="0;{w * 0.95:.0f};{w * 0.95:.0f}" keyTimes="0;.2;1" dur="8s" begin="2.6s" repeatCount="indefinite"/>'
             f'<animate attributeName="stroke-opacity" values="1;0;0" keyTimes="0;.2;1" dur="8s" begin="2.6s" repeatCount="indefinite"/></circle>')
    soft = f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#000"/>' + "".join(brushes) + burst
    bayer_uri = bayer_tile_uri(cell)

    def threshold(fid, gain, offset):
        # out = step(bayer, gain * soft - offset), as in DitherVeil's shader: arithmetic gives
        # gain*soft - bayer + k4 (clipped to 0..1), and a 64-step table keeps only the top step
        table = " ".join(["0"] * 63 + ["1"])
        return (f'<filter id="{fid}" filterUnits="userSpaceOnUse" primitiveUnits="userSpaceOnUse" x="{x0}" y="{y0}" '
                f'width="{w}" height="{h}" color-interpolation-filters="sRGB">'
                f'<feImage href="{bayer_uri}" x="{x0}" y="{y0}" width="{8 * cell}" height="{8 * cell}" result="b8"/>'
                f'<feTile in="b8" result="bt"/>'
                # scale colour only (alpha stays 1, which Firefox and Chrome then agree on), minus a hair
                # so the lowest Bayer level never passes at zero
                f'<feComponentTransfer in="SourceGraphic" result="sg"><feFuncR type="linear" slope="{gain:.4f}" intercept="{-offset - 0.02:.4f}"/>'
                f'<feFuncG type="linear" slope="{gain:.4f}" intercept="{-offset - 0.02:.4f}"/>'
                f'<feFuncB type="linear" slope="{gain:.4f}" intercept="{-offset - 0.02:.4f}"/></feComponentTransfer>'
                f'<feComposite in="sg" in2="bt" operator="arithmetic" k1="0" k2="1" k3="-1" k4="1"/>'
                f'<feComponentTransfer><feFuncR type="discrete" tableValues="{table}"/>'
                f'<feFuncG type="discrete" tableValues="{table}"/><feFuncB type="discrete" tableValues="{table}"/>'
                f'<feFuncA type="linear" slope="0" intercept="1"/></feComponentTransfer></filter>')

    defs = (f'<radialGradient id="vb"><stop offset="0" stop-color="#fff"/><stop offset=".45" stop-color="#fff" stop-opacity=".95"/>'
            f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
            # photo where soft >= bayer*(1-rim) + rim; cobalt rim where soft >= bayer*(1-rim)
            + threshold("vfp", 1 / (1 - rim), rim / (1 - rim)) + threshold("vfr", 1 / (1 - rim), 0.0) +
            f'<mask id="vmp" maskUnits="userSpaceOnUse" x="{x0}" y="{y0}" width="{w}" height="{h}"><g filter="url(#vfp)">{soft}</g></mask>'
            f'<mask id="vmr" maskUnits="userSpaceOnUse" x="{x0}" y="{y0}" width="{w}" height="{h}"><g filter="url(#vfr)">{soft}</g></mask>')
    ph = photo_uri(mode, t, int(w * 2), int(h * 2))
    body = (f'<g class="fi" {delay(1.4)}>'
            f'<rect mask="url(#vmr)" x="{x0}" y="{y0}" width="{w}" height="{h}" fill="{t["accent"]}"/>'
            f'<image mask="url(#vmp)" x="{x0}" y="{y0}" width="{w}" height="{h}" preserveAspectRatio="none" href="{ph}"/></g>')
    return body, defs
