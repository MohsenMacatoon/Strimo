"""Draws Strimo's app icon (assets/strimo.ico + strimo.png) with Pillow."""

import math
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")
S = 1024  # draw big, scale down


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def make() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # rounded-square background with a vertical gradient
    bg = Image.new("RGBA", (S, S))
    top, bottom = (31, 36, 48, 255), (13, 15, 20, 255)
    px = bg.load()
    for y in range(S):
        c = lerp(top, bottom, y / S)
        for x in range(S):
            px[x, y] = c
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((40, 40, S - 40, S - 40), radius=220, fill=255)
    img.paste(bg, (0, 0), mask)

    # soft glow behind the ring
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((210, 210, S - 210, S - 210), fill=(34, 195, 166, 120))
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    img = Image.alpha_composite(img, Image.composite(glow, Image.new("RGBA", (S, S)), mask))

    # gradient ring (teal -> cyan), open at the top-right like a rotate arrow
    ring = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    cx = cy = S / 2
    r_out, width = 330, 70
    c1, c2 = (34, 195, 166, 255), (56, 189, 248, 255)
    start, end = -60, 250  # degrees, leave a gap
    steps = 240
    for i in range(steps):
        a0 = start + (end - start) * i / steps
        a1 = start + (end - start) * (i + 1.5) / steps
        rd.arc((cx - r_out, cy - r_out, cx + r_out, cy + r_out), a0, a1, fill=lerp(c1, c2, i / steps), width=width)
    # arrow head at the end of the arc
    ang = math.radians(end)
    mid_r = r_out - width / 2
    hx, hy = cx + mid_r * math.cos(ang), cy + mid_r * math.sin(ang)
    tang = ang + math.pi / 2
    size = 95
    p1 = (hx + size * math.cos(tang), hy + size * math.sin(tang))
    p2 = (hx + 0.9 * size * math.cos(ang), hy + 0.9 * size * math.sin(ang))
    p3 = (hx - 0.9 * size * math.cos(ang), hy - 0.9 * size * math.sin(ang))
    rd.polygon([p1, p2, p3], fill=c2)
    img = Image.alpha_composite(img, ring)

    # white play triangle
    tri = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    td = ImageDraw.Draw(tri)
    td.polygon([(cx - 95, cy - 150), (cx + 165, cy), (cx - 95, cy + 150)], fill=(240, 244, 248, 255))
    tri = tri.filter(ImageFilter.GaussianBlur(1.5))
    img = Image.alpha_composite(img, tri)
    return img


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    big = make()
    big.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT, "strimo.png"))
    sizes = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]
    big.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, "strimo.ico"), sizes=sizes)
    print("icon written to", OUT)


if __name__ == "__main__":
    main()
