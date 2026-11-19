#!/usr/bin/env python3
"""Local preview: preview.html shows the README in GitHub's dark and light themes side by side.

    STATIC=1 python scripts/render_cards.py && python scripts/preview.py
    chromium --headless --screenshot=preview.png --window-size=1880,2400 preview.html
"""
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
md = open(os.path.join(ROOT, "README.md")).read()
md = re.sub(r"<!--.*?-->", "", md, flags=re.S)


def themed(mode):
    # resolve <picture> by hand, the way GitHub does for the viewer's theme
    return re.sub(r'<picture><source[^>]*srcset="([^"]*)-dark\.svg" /><img src="[^"]*-light\.svg"',
                  lambda m: f'<picture><img src="{m.group(1)}-{mode}.svg"', md)


page = """<!doctype html><meta charset="utf-8"><title>Profile preview</title>
<style>body{margin:0;display:flex;gap:40px;padding:30px;background:#888;font:14px system-ui}
.col{width:880px;padding:16px;border-radius:8px}.dark{background:#0d1117;color:#e6edf3}.light{background:#fff;color:#1f2328}
img{vertical-align:top;display:inline-block}a{color:#4493f8}p{text-align:center}</style>
<div class="col dark">%s</div><div class="col light">%s</div>""" % (themed("dark"), themed("light"))
open(os.path.join(ROOT, "preview.html"), "w").write(page)
print("wrote preview.html")
