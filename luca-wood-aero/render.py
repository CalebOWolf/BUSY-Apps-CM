"""
Renders the artwork for the Luca Wood Aero app.

  front_00.png … front_NN.png  72x16 RGB frames for the front LED strip:
                               a glossy Frutiger Aero sky, a green hill, drifting
                               bubbles, a pixel Luca head and "LUCA WOOD".
  back.png                     160x80 picture for the back screen (16 shades of
                               grey): a Windows 7 Aero window with Luca's
                               portrait inside.

It also writes upscaled previews into preview/ so you can see the result
without a BUSY Bar plugged in.

    python render.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).parent
OUT = HERE / "build"
PREVIEW = HERE / "preview"
PORTRAIT = HERE / "assets" / "luca.png"

FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80
FRAMES = 16

# --------------------------------------------------------------------------
# Luca's palette
# --------------------------------------------------------------------------
PALETTE = {
    "K": (28, 30, 44),      # outline
    "W": (255, 255, 255),   # fur
    "S": (190, 205, 230),   # fur shade (blue-ish, like the art)
    "G": (150, 150, 158),   # grey ear
    "T": (40, 235, 175),    # mint ear / spots
    "M": (8, 8, 12),        # black eye mask
    "O": (245, 160, 80),    # amber eye
    "N": (225, 140, 115),   # nose
    "P": (255, 150, 160),   # tongue
}

# 16x16 pixel Luca, front-facing and grinning (the 🐺 of the app).
LUCA_ICON = [
    "KK...........KK.",
    "KGK.........KTK.",
    "KGGKKKKKKKKKTTK.",
    "KGWWWWWWWWWWWTK.",
    "KWWWWWWWWWWWWWK.",
    "KWWWWWWWWMMMMWK.",
    "KWWOOWWWMMOOMWK.",
    "KWWOKWWWMMOKMWK.",
    "KWWWWWWWWMMMWWK.",
    ".KWWWWNNNWWWWK..",
    ".KWWTWNNNWTWWK..",
    "..KWWWWKWWWWK...",
    "..KWWKPPPKWWK...",
    "...KWWKKKWWK....",
    "....KWWWWWWK....",
    ".....KKKKKK.....",
]

# 5x7 pixel letters for the name (crisp on a 16-pixel-tall LED strip).
GLYPHS = {
    "L": ["X....", "X....", "X....", "X....", "X....", "X....", "XXXXX"],
    "U": ["X...X", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."],
    "C": [".XXXX", "X....", "X....", "X....", "X....", "X....", ".XXXX"],
    "A": [".XXX.", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"],
    "W": ["X...X", "X...X", "X...X", "X.X.X", "X.X.X", "XX.XX", "X...X"],
    "O": [".XXX.", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."],
    "D": ["XXXX.", "X...X", "X...X", "X...X", "X...X", "X...X", "XXXX."],
}


def lerp(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def draw_icon(img: Image.Image, x0: int, y0: int, bob: int = 0) -> None:
    px = img.load()
    for y, row in enumerate(LUCA_ICON):
        for x, ch in enumerate(row):
            yy = y0 + y + bob
            if ch != "." and 0 <= yy < img.height:
                px[x0 + x, yy] = PALETTE[ch]


def draw_text(img: Image.Image, text: str, x: int, y: int) -> None:
    """Glossy white pixel text with a deep-blue drop shadow."""
    px = img.load()
    for pass_, (dx, dy) in enumerate([(1, 1), (0, 0)]):
        cx = x
        for ch in text:
            if ch == " ":
                cx += 3
                continue
            for gy, row in enumerate(GLYPHS[ch]):
                for gx, on in enumerate(row):
                    if on == "X":
                        X, Y = cx + gx + dx, y + gy + dy
                        if 0 <= X < img.width and 0 <= Y < img.height:
                            if pass_ == 0:
                                px[X, Y] = (0, 30, 90)
                            else:
                                # top rows brighter: a glassy shine on the letters
                                px[X, Y] = (255, 255, 255)
            cx += 6


def aero_sky(w: int, h: int) -> Image.Image:
    """Bright Aero sky with a glass highlight across the top half."""
    img = Image.new("RGB", (w, h))
    px = img.load()
    top, bottom = (120, 215, 255), (0, 95, 200)
    for y in range(h):
        t = y / (h - 1)
        c = lerp(top, bottom, t)
        if y < h // 2:  # glossy shine band
            c = lerp(c, (255, 255, 255), 0.35 * (1 - y / (h / 2)))
        for x in range(w):
            px[x, y] = c
    return img


def green_hill(img: Image.Image) -> None:
    px = img.load()
    w, h = img.size
    for x in range(w):
        top = h - 2.5 + 1.5 * math.cos((x - 58) / 9.0)  # a rolling hill on the right
        for y in range(h):
            if y >= top:
                depth = (y - top) / 4
                px[x, y] = lerp((140, 235, 60), (20, 140, 40), min(depth, 1))
            elif y >= top - 1:
                px[x, y] = lerp(px[x, y], (210, 255, 150), 0.6)  # sunlit edge


BUBBLES = [  # (x, speed, phase, radius)
    (24, 1.0, 0.0, 1), (33, 0.7, 5.0, 2), (44, 1.2, 9.0, 1),
    (52, 0.8, 2.0, 2), (62, 1.1, 12.0, 1), (68, 0.6, 7.0, 1), (18, 0.9, 13.0, 1),
]


def draw_bubbles(img: Image.Image, frame: int) -> None:
    d = ImageDraw.Draw(img)
    px = img.load()
    span = FRONT_H + 6
    for bx, speed, phase, r in BUBBLES:
        t = (phase + frame * speed * span / FRAMES) % span
        by = FRONT_H + 2 - t
        x = bx + round(math.sin((t + phase) / 3))
        y = round(by)
        if r == 1:
            for X, Y in [(x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1)]:
                if 0 <= X < FRONT_W and 0 <= Y < FRONT_H:
                    px[X, Y] = lerp(px[X, Y], (230, 250, 255), 0.55)
        else:
            d.ellipse([x - r, y - r, x + r, y + r], outline=(225, 248, 255))
        if 0 <= x - 1 < FRONT_W and 0 <= y - 1 < FRONT_H:
            px[x - 1 if r > 1 else x, y - 1] = (255, 255, 255)  # specular glint


def front_frame(frame: int) -> Image.Image:
    img = aero_sky(FRONT_W, FRONT_H)
    green_hill(img)
    draw_bubbles(img, frame)
    bob = 1 if (frame // (FRAMES // 4)) % 2 else 0  # Luca bounces happily
    draw_icon(img, 1, 0, bob=bob)
    draw_text(img, "LUCA WOOD", 19, 4)
    return img


# --------------------------------------------------------------------------
# Back screen: a Windows 7 Aero window
# --------------------------------------------------------------------------
def font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def back_frame() -> Image.Image:
    img = Image.new("L", (BACK_W, BACK_H), 0)
    d = ImageDraw.Draw(img)

    # Desktop: soft radial glow with floating bubbles (Aero wallpaper vibes)
    for y in range(BACK_H):
        for x in range(BACK_W):
            dist = math.hypot(x - 120, y - 10) / 150
            img.putpixel((x, y), int(70 * max(0, 1 - dist)))
    for bx, by, r in [(8, 70, 5), (150, 66, 7), (138, 8, 3), (20, 12, 3)]:
        d.ellipse([bx - r, by - r, bx + r, by + r], outline=110)
        d.point((bx - r // 2, by - r // 2), fill=230)

    # Window frame (glass border)
    wx0, wy0, wx1, wy1 = 4, 2, 155, 77
    d.rounded_rectangle([wx0, wy0, wx1, wy1], radius=5, fill=120, outline=230)
    # glass gradient across the frame
    for y in range(wy0 + 1, wy0 + 14):
        shade = int(205 - (y - wy0) * 6)
        d.line([(wx0 + 2, y), (wx1 - 2, y)], fill=shade)
    # diagonal Aero light streaks on the title glass
    for sx in (30, 38, 100):
        d.line([(sx, wy0 + 1), (sx + 10, wy0 + 13)], fill=235)
    # title text
    d.text((wx0 + 18, wy0 + 1), "About Luca", font=font(11), fill=20)
    # little wolf icon in the title bar (greyscale version of the LED icon)
    icon = Image.new("RGB", (16, 16), (0, 0, 0))
    draw_icon(icon, 0, 0)
    icon_l = icon.convert("L").resize((12, 12), Image.NEAREST)
    mask = icon.convert("L").point(lambda v: 255 if v else 0).resize((12, 12), Image.NEAREST)
    img.paste(icon_l, (wx0 + 4, wy0 + 1), mask)

    # caption buttons: minimise, maximise, and the famous glowing close button
    bx = wx1 - 46
    for i, w in enumerate((12, 12, 20)):
        fill = 245 if i == 2 else 175
        d.rounded_rectangle([bx, wy0 + 1, bx + w, wy0 + 9], radius=2, fill=fill, outline=40)
        cx, cy = bx + w // 2, wy0 + 5
        if i == 0:
            d.line([(cx - 2, cy + 2), (cx + 2, cy + 2)], fill=30)
        elif i == 1:
            d.rectangle([cx - 2, cy - 2, cx + 2, cy + 2], outline=30)
        else:
            d.line([(cx - 2, cy - 2), (cx + 2, cy + 2)], fill=10, width=1)
            d.line([(cx - 2, cy + 2), (cx + 2, cy - 2)], fill=10, width=1)
        bx += w + 1

    # client area
    cx0, cy0, cx1, cy1 = wx0 + 3, wy0 + 15, wx1 - 3, wy1 - 3
    d.rectangle([cx0, cy0, cx1, cy1], fill=235, outline=60)

    # portrait
    port = Image.open(PORTRAIT).convert("RGBA")
    bg = Image.new("RGBA", port.size, (255, 255, 255, 255))
    port = Image.alpha_composite(bg, port).convert("L")
    side = cy1 - cy0 - 3
    port = port.crop((60, 20, 1140, 1100))  # Luca's face
    port = port.resize((side, side), Image.LANCZOS)
    port = ImageOps.autocontrast(port, cutoff=1)
    img.paste(port, (cx0 + 2, cy0 + 2))
    d.rectangle([cx0 + 1, cy0 + 1, cx0 + side + 2, cy0 + side + 2], outline=40)

    # info panel
    tx = cx0 + side + 8
    d.text((tx, cy0 + 3), "Luca Wood", font=font(12), fill=0)
    d.text((tx, cy0 + 18), "Species: wolf", font=font(9), fill=55)
    d.text((tx, cy0 + 29), "Status: howling", font=font(9), fill=55)
    # Aero progress bar, "Being awesome..."
    py = cy0 + 45
    d.rounded_rectangle([tx, py, cx1 - 6, py + 7], radius=2, fill=200, outline=60)
    d.rounded_rectangle([tx + 1, py + 1, tx + int((cx1 - 6 - tx) * 0.8), py + 6],
                        radius=2, fill=110)
    d.line([(tx + 2, py + 2), (tx + int((cx1 - 6 - tx) * 0.8) - 1, py + 2)], fill=200)

    # snap to the back screen's 16 shades of grey
    return img.point(lambda v: (v // 17) * 17)


# --------------------------------------------------------------------------
# Previews
# --------------------------------------------------------------------------
def led_preview(frame: Image.Image, scale: int = 10) -> Image.Image:
    """Upscale as round LEDs, roughly how it looks on the real strip."""
    w, h = frame.size
    out = Image.new("RGB", (w * scale, h * scale), (10, 10, 14))
    d = ImageDraw.Draw(out)
    for y in range(h):
        for x in range(w):
            c = frame.getpixel((x, y))
            d.ellipse([x * scale + 1, y * scale + 1, x * scale + scale - 2,
                       y * scale + scale - 2], fill=c)
    return out


def main() -> None:
    OUT.mkdir(exist_ok=True)
    PREVIEW.mkdir(exist_ok=True)

    frames = [front_frame(i) for i in range(FRAMES)]
    for i, f in enumerate(frames):
        f.save(OUT / f"front_{i:02d}.png")
    leds = [led_preview(f) for f in frames]
    leds[0].save(PREVIEW / "front.gif", save_all=True, append_images=leds[1:],
                 duration=150, loop=0)
    leds[0].save(PREVIEW / "front.png")

    back = back_frame()
    back.save(OUT / "back.png")
    back.resize((BACK_W * 4, BACK_H * 4), Image.NEAREST).save(PREVIEW / "back.png")
    print(f"Rendered {len(frames)} front frames + back screen into {OUT}")


if __name__ == "__main__":
    main()
