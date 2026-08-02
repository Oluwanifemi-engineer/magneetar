#!/usr/bin/env python3
"""Generate the Magneetar launcher icon PNGs (legacy mipmaps).

Design: magenta gradient tile with a white capital M — the same brand mark
as the dashboard/login pages and the adaptive-icon vector. Uses only the
standard library + PIL so it can run anywhere the server venv is present.

Usage: python3 scripts/gen-launcher-icons.py
"""

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
MIPMAPS = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}


def lerp_color(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def magenta_gradient(size: int) -> Image.Image:
    """Diagonal magenta gradient (top-left bright → bottom-right deep)."""
    top_left = (240, 58, 158)   # #F03A9E
    mid = (233, 30, 140)        # #E91E8C
    bottom_right = (139, 10, 94)  # #8B0A5E
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2.0 * (size - 1))
            if t < 0.45:
                local = t / 0.45
                px[x, y] = lerp_color(top_left, mid, local)
            else:
                local = (t - 0.45) / 0.55
                px[x, y] = lerp_color(mid, bottom_right, local)
    return img


def draw_m(img: Image.Image) -> None:
    """Draw the bold solid M centred on the tile (matches the web brand mark).

    Geometry mirrors the 120x120 brand SVG: M27 88 L27 38 L60 82 L93 38 L93 88
    — a thick rounded letterform with the middle V dipping DOWN (a real M, not
    the old bent/W shape whose centre peaked upward).
    """
    size = img.width
    draw = ImageDraw.Draw(img, "RGBA")

    pts = [(27, 88), (27, 38), (60, 82), (93, 38), (93, 88)]
    x_vals = [p[0] for p in pts]
    y_vals = [p[1] for p in pts]
    min_x, max_x = min(x_vals), max(x_vals)
    min_y, max_y = min(y_vals), max(y_vals)
    w, h = max_x - min_x, max_y - min_y

    scale = (size * 0.66) / max(w, h)
    ox = (size - w * scale) / 2 - min_x * scale
    oy = (size - h * scale) / 2 - min_y * scale
    scaled = [(x * scale + ox, y * scale + oy) for x, y in pts]

    # Subtle dark shadow below the M for polished depth
    shadow_stroke = max(3, int(size * 0.14))
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.line(
        [(x, y + max(2, size * 0.02)) for x, y in scaled],
        fill=(92, 7, 64, 90),
        width=shadow_stroke,
        joint="curve",
    )
    img.paste(shadow, (0, 0), shadow)

    stroke = max(3, int(size * 0.14))
    # Draw as a single continuous polyline with round joins/caps
    draw.line(scaled, fill=(255, 255, 255, 255), width=stroke, joint="curve")
    for x, y in scaled:
        r = stroke / 2
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 255))


def main() -> None:
    for folder, size in MIPMAPS.items():
        out = ROOT / "android-app/app/src/main/res" / folder / "ic_launcher.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        img = magenta_gradient(size)
        draw_m(img)
        img.save(out, "PNG")
        print(f"wrote {out} ({size}x{size})")


if __name__ == "__main__":
    main()
