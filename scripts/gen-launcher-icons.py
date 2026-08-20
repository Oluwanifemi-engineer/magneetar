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


def dark_background(size: int) -> Image.Image:
    """Solid dark background (#0f0f1a)."""
    return Image.new("RGB", (size, size), (15, 15, 26))


def draw_m(img: Image.Image) -> None:
    """Draw the fused m/M-halves mark centred on the tile.

    The mark is a single continuous stroke:
      Left stem up → arch right → center stem down → diagonal up-right → right stem down
    Scaled from 512x512 viewBox to the target icon size.
    White stroke on dark background.
    """
    size = img.width
    draw = ImageDraw.Draw(img, "RGBA")

    # The fused path in 512x512 coordinate space
    path_512 = []
    path_512.append((124, 386))
    path_512.append((124, 186))
    arch_cp1 = (124, 106)
    arch_cp2 = (289, 106)
    arch_end = (289, 186)
    arch_start = (124, 186)
    for i in range(1, 21):
        t = i / 20.0
        u = 1.0 - t
        x = u**3 * arch_start[0] + 3 * u**2 * t * arch_cp1[0] + 3 * u * t**2 * arch_cp2[0] + t**3 * arch_end[0]
        y = u**3 * arch_start[1] + 3 * u**2 * t * arch_cp1[1] + 3 * u * t**2 * arch_cp2[1] + t**3 * arch_end[1]
        path_512.append((x, y))
    path_512.append((289, 386))
    path_512.append((389, 126))
    path_512.append((389, 386))

    # Scale from 512 space to icon size with padding
    x_vals = [p[0] for p in path_512]
    y_vals = [p[1] for p in path_512]
    min_x, max_x = min(x_vals), max(x_vals)
    min_y, max_y = min(y_vals), max(y_vals)
    w, h = max_x - min_x, max_y - min_y

    scale = (size * 0.72) / max(w, h)
    ox = (size - w * scale) / 2 - min_x * scale
    oy = (size - h * scale) / 2 - min_y * scale
    scaled = [(x * scale + ox, y * scale + oy) for x, y in path_512]

    # Draw the fused mark as a single white stroke
    stroke = max(2, int(size * 0.12))
    draw.line(scaled, fill=(255, 255, 255, 255), width=stroke, joint="curve")


def main() -> None:
    for folder, size in MIPMAPS.items():
        out = ROOT / "android-app/app/src/main/res" / folder / "ic_launcher.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        img = dark_background(size)
        draw_m(img)
        img.save(out, "PNG")
        print(f"wrote {out} ({size}x{size})")


if __name__ == "__main__":
    main()
