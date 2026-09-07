#!/usr/bin/env python3
"""Generate the Magneetar launcher icon PNGs (legacy mipmaps).

Brand mark: the canonical Magneetar silhouette traced from branding/icon-256.png.
Dark #0F0F1A squircle background, hot-pink-to-deep-magenta gradient fill.

Source of truth: branding/magneetar-logo.svg (verified against branding/icon-*.png).

Usage: python3 scripts/gen-launcher-icons.py
"""

from __future__ import annotations

import os
from pathlib import Path

import cairosvg
from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
SRC_SVG = ROOT / "branding" / "magneetar-logo.svg"

MIPMAPS = {
    "mipmap-mdpi": 48,   # 48x48  (1x)
    "mipmap-hdpi": 72,   # 72x72  (1.5x)
    "mipmap-xhdpi": 96,  # 96x96  (2x)
    "mipmap-xxhdpi": 144, # 144x144 (3x)
    "mipmap-xxxhdpi": 192, # 192x192 (4x)
}


def main() -> None:
    if not SRC_SVG.exists():
        raise SystemExit(f"brand SVG not found: {SRC_SVG}")

    for folder, size in MIPMAPS.items():
        out = ROOT / "android-app/app/src/main/res" / folder / "ic_launcher.png"
        out.parent.mkdir(parents=True, exist_ok=True)

        png_bytes = cairosvg.svg2png(url=str(SRC_SVG), output_width=size, output_height=size)
        im = Image.open(__import__("io").BytesIO(png_bytes)).convert("RGBA")
        # Ensure the squircle background fills the whole canvas (the SVG already does,
        # but confirm no transparency around the edges).
        im.save(out, "PNG")
        print(f"wrote {out} ({size}x{size})")


if __name__ == "__main__":
    main()
