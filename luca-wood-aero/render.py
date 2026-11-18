"""
Renders the artwork for the Luca Wood Aero app.

Every mood Luca can be in gets its own set of frames in build/:

  <mood>_NN.png   72x16 RGB frames for the front LED strip
  back_<mood>.png 160x80 picture for the back screen (16 shades of grey):
                  a Windows 7 Aero "About Luca" window whose status line
                  matches the mood

Moods: idle, howl (OK), wave (Back), yay (Start), look_left / look_right
(the wheel) and sleep (nobody has pressed anything for a while).

It also writes upscaled previews into preview/ so you can see the result
without a BUSY Bar plugged in.

    python render.py
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).parent
OUT = HERE / "build"
PREVIEW = HERE / "preview"
PORTRAIT = HERE / "assets" / "luca.png"

FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80

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
# Eyes live at rows 6-7: columns 3-4 (left) and 10-11 (right, in the mask).
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

# Eye shapes: (row 6, row 7) for the left eye, then the right eye.
EYES = {
    "open":   (("OO", "OK"), ("OO", "OK")),
    "left":   (("KO", "KO"), ("KO", "KO")),
    "right":  (("OK", "OK"), ("OK", "OK")),
    "closed": (("WW", "KK"), ("MM", "SS")),
    "wink":   (("WW", "KK"), ("OO", "OK")),
    "happy":  (("KK", "WW"), ("SS", "MM")),  # ^^ smiling eyes
}


def make_icon(eyes: str = "open", howl: bool = False) -> list[str]:
    rows = [list(r) for r in LUCA_ICON]
    (l6, l7), (r6, r7) = EYES[eyes]
    rows[6][3:5], rows[7][3:5] = l6, l7
    rows[6][10:12], rows[7][10:12] = r6, r7
    if howl:  # round "awoo" mouth
        rows[11][6:9] = "KKK"
        rows[12][6:9] = "PKP"
    return ["".join(r) for r in rows]


# Pixel letters for the words (crisp on a 16-pixel-tall LED strip).
GLYPHS = {
    "L": ["X....", "X....", "X....", "X....", "X....", "X....", "XXXXX"],
    "U": ["X...X", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."],
    "C": [".XXXX", "X....", "X....", "X....", "X....", "X....", ".XXXX"],
    "A": [".XXX.", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"],
    "W": ["X...X", "X...X", "X...X", "X.X.X", "X.X.X", "XX.XX", "X...X"],
    "O": [".XXX.", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."],
    "D": ["XXXX.", "X...X", "X...X", "X...X", "X...X", "X...X", "XXXX."],
    "H": ["X...X", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"],
    "E": ["XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "XXXXX"],
    "Y": ["X...X", "X...X", ".X.X.", "..X..", "..X..", "..X..", "..X.."],
    "Z": ["XXXXX", "....X", "...X.", "..X..", ".X...", "X....", "XXXXX"],
    "!": ["X", "X", "X", "X", "X", ".", "X"],
    "♥": [".X.X.", "XXXXX", "XXXXX", "XXXXX", ".XXX.", "..X..", "....."],
}
HEART = (255, 70, 120)


def lerp(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def put(img: Image.Image, x: int, y: int, c) -> None:
    if 0 <= x < img.width and 0 <= y < img.height:
        img.putpixel((x, y), c)


def draw_icon(img: Image.Image, x0: int, y0: int, icon: list[str] | None = None) -> None:
    for y, row in enumerate(icon or LUCA_ICON):
        for x, ch in enumerate(row):
            if ch != ".":
                put(img, x0 + x, y0 + y, PALETTE[ch])


def draw_text(img: Image.Image, text: str, x: int, y: int,
              color=(255, 255, 255), shadow=(0, 30, 90)) -> None:
    """Glossy pixel text with a drop shadow."""
    for pass_, (dx, dy) in enumerate([(1, 1), (0, 0)]):
        cx = x
        for ch in text:
            if ch == " ":
                cx += 3
                continue
            glyph = GLYPHS[ch]
            for gy, row in enumerate(glyph):
                for gx, on in enumerate(row):
                    if on == "X":
                        c = shadow if pass_ == 0 else (HEART if ch == "♥" else color)
                        put(img, cx + gx + dx, y + gy + dy, c)
            cx += len(glyph[0]) + 1


def gradient_sky(top, bottom, shine: float = 0.35) -> Image.Image:
    """An Aero sky with a glass highlight across the top half."""
    img = Image.new("RGB", (FRONT_W, FRONT_H))
    d = ImageDraw.Draw(img)
    for y in range(FRONT_H):
        c = lerp(top, bottom, y / (FRONT_H - 1))
        if y < FRONT_H // 2:
            c = lerp(c, (255, 255, 255), shine * (1 - y / (FRONT_H / 2)))
        d.line([(0, y), (FRONT_W - 1, y)], fill=c)
    return img


def day_sky() -> Image.Image:
    return gradient_sky((120, 215, 255), (0, 95, 200))


def night_sky(frame: int) -> Image.Image:
    img = gradient_sky((4, 8, 40), (20, 40, 110), shine=0.08)
    rnd = random.Random(7)
    for _ in range(14):  # twinkling stars
        x, y, p = rnd.randrange(FRONT_W), rnd.randrange(11), rnd.random() * 6
        b = 0.4 + 0.6 * abs(math.sin(frame / 3 + p))
        put(img, x, y, lerp((20, 30, 80), (255, 250, 210), b))
    d = ImageDraw.Draw(img)  # the big moon from Luca's portrait
    d.ellipse([60, 1, 69, 10], fill=(250, 240, 180))
    d.ellipse([62, 3, 64, 5], fill=(225, 215, 150))
    return img


def green_hill(img: Image.Image, night: bool = False) -> None:
    lit, dark, edge = ((140, 235, 60), (20, 140, 40), (210, 255, 150))
    if night:
        lit, dark, edge = (30, 90, 50), (5, 40, 25), (60, 130, 90)
    for x in range(FRONT_W):
        top = FRONT_H - 2.5 + 1.5 * math.cos((x - 58) / 9.0)
        for y in range(FRONT_H):
            if y >= top:
                img.putpixel((x, y), lerp(lit, dark, min((y - top) / 4, 1)))
            elif y >= top - 1:
                img.putpixel((x, y), lerp(img.getpixel((x, y)), edge, 0.6))


BUBBLES = [  # (x, speed, phase, radius)
    (24, 1.0, 0.0, 1), (33, 0.7, 5.0, 2), (44, 1.2, 9.0, 1),
    (52, 0.8, 2.0, 2), (62, 1.1, 12.0, 1), (68, 0.6, 7.0, 1), (18, 0.9, 13.0, 1),
]


def draw_bubbles(img: Image.Image, t: float, bubbles=BUBBLES) -> None:
    """t runs 0..1 over one loop of the animation."""
    d = ImageDraw.Draw(img)
    span = FRONT_H + 6
    for bx, speed, phase, r in bubbles:
        p = (phase + t * speed * span) % span
        x, y = bx + round(math.sin((p + phase) / 3)), round(FRONT_H + 2 - p)
        if r == 1:
            for X, Y in [(x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1)]:
                if 0 <= X < FRONT_W and 0 <= Y < FRONT_H:
                    img.putpixel((X, Y), lerp(img.getpixel((X, Y)), (230, 250, 255), 0.55))
        else:
            d.ellipse([x - r, y - r, x + r, y + r], outline=(225, 248, 255))
        put(img, x - 1 if r > 1 else x, y - 1, (255, 255, 255))  # specular glint


def mini_heart(img: Image.Image, x: int, y: int) -> None:
    for dx, dy in [(0, 0), (2, 0), (0, 1), (1, 1), (2, 1), (1, 2)]:
        put(img, x + dx, y + dy, HEART)


def mini_z(img: Image.Image, x: int, y: int, c) -> None:
    for dx, dy in [(0, 0), (1, 0), (2, 0), (1, 1), (0, 2), (1, 2), (2, 2)]:
        put(img, x + dx, y + dy, c)


# --------------------------------------------------------------------------
# Moods (front LED strip)
# --------------------------------------------------------------------------
def idle(n: int, i: int, eyes: str = "open") -> Image.Image:
    img = day_sky()
    green_hill(img)
    draw_bubbles(img, i / n)
    bob = 1 if (i // (n // 4)) % 2 else 0  # Luca bounces happily
    draw_icon(img, 1, bob, make_icon(eyes))
    draw_text(img, "LUCA WOOD", 19, 4)
    return img


def howl(n: int, i: int) -> Image.Image:
    """OK: Luca throws his head back and howls; sound rings ripple out."""
    img = day_sky()
    d = ImageDraw.Draw(img)
    for k in range(3):  # expanding rings behind him
        r = ((i / n) * 30 + k * 10) % 30
        c = lerp((255, 255, 255), (70, 160, 230), r / 30)
        d.ellipse([8 - r, 6 - r, 8 + r, 6 + r], outline=c)
    green_hill(img)
    shake = (-1, 0, 1, 0)[i % 4] if i < n - 3 else 0
    draw_icon(img, 1 + shake, -1, make_icon("closed", howl=True))
    letters = "AWOOO!"[: 2 + i * 5 // n]  # the howl grows
    draw_text(img, letters, 22, 4)
    return img


def wave(n: int, i: int) -> Image.Image:
    """Back: Luca winks and hearts float up."""
    img = day_sky()
    green_hill(img)
    draw_bubbles(img, i / n)
    for k, hx in enumerate((14, 17, 12)):
        hy = 14 - ((i + k * 4) * 18 // n) % 18
        mini_heart(img, hx + k, hy)
    draw_icon(img, 1, 0, make_icon("wink" if i % 6 < 4 else "open"))
    draw_text(img, "HEY ♥", 22, 4)
    return img


def yay(n: int, i: int) -> Image.Image:
    """Start: Luca jumps for joy, bubbles race up and sparkles pop."""
    img = day_sky()
    green_hill(img)
    fast = [(x, s * 3, p, r) for x, s, p, r in BUBBLES]
    draw_bubbles(img, i / n, fast)
    rnd = random.Random(i)
    for _ in range(8):
        put(img, rnd.randrange(18, FRONT_W), rnd.randrange(FRONT_H),
            rnd.choice([(255, 240, 90), (255, 255, 255), (255, 120, 200), (40, 235, 175)]))
    hop = (0, -1, -2, -3, -2, -1, 0, 0)[i % 8]
    draw_icon(img, 1, hop + 1, make_icon("happy"))
    draw_text(img, "YAY!", 26, 4 + (hop // 2))
    return img


def sleep(n: int, i: int) -> Image.Image:
    """Nobody's around: night falls, Luca dozes under the moon."""
    img = night_sky(i)
    green_hill(img, night=True)
    breathe = 1 if (i // (n // 2)) % 2 else 0
    draw_icon(img, 1, 1 + breathe, make_icon("closed"))
    for k in range(2):
        t = ((i + k * n // 2) % n) / n
        mini_z(img, 14 + round(t * 6), 8 - round(t * 8), lerp((200, 200, 255), (40, 50, 120), t))
    draw_text(img, "ZZZ", 26, 4, color=(190, 190, 255), shadow=(0, 0, 30))
    return img


MOODS = {  # name: (frame maker, frame count, loops?)
    "idle": (idle, 16, True),
    "howl": (howl, 14, False),
    "wave": (wave, 14, False),
    "yay": (yay, 16, False),
    "look_left": (lambda n, i: idle(n, i, "left"), 8, False),
    "look_right": (lambda n, i: idle(n, i, "right"), 8, False),
    "sleep": (sleep, 16, True),
}

STATUS = {
    "idle": "Status: chilling",
    "howl": "Status: AWOOO!",
    "wave": "Status: saying hi",
    "yay": "Status: partying",
    "look_left": "Status: curious",
    "look_right": "Status: curious",
    "sleep": "Status: sleeping",
}


# --------------------------------------------------------------------------
# Back screen: a Windows 7 Aero window
# --------------------------------------------------------------------------
def font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def back_frame(status: str, progress: float = 0.8) -> Image.Image:
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
    for y in range(wy0 + 1, wy0 + 14):  # glass gradient across the frame
        d.line([(wx0 + 2, y), (wx1 - 2, y)], fill=int(205 - (y - wy0) * 6))
    for sx in (30, 38, 100):  # diagonal Aero light streaks
        d.line([(sx, wy0 + 1), (sx + 10, wy0 + 13)], fill=235)
    d.text((wx0 + 18, wy0 + 1), "About Luca", font=font(11), fill=20)
    # little wolf icon in the title bar (greyscale version of the LED icon)
    icon = Image.new("RGB", (16, 16), (0, 0, 0))
    draw_icon(icon, 0, 0)
    mask = icon.convert("L").point(lambda v: 255 if v else 0).resize((12, 12), Image.NEAREST)
    img.paste(icon.convert("L").resize((12, 12), Image.NEAREST), (wx0 + 4, wy0 + 1), mask)

    # caption buttons: minimise, maximise, and the famous glowing close button
    bx = wx1 - 46
    for i, w in enumerate((12, 12, 20)):
        d.rounded_rectangle([bx, wy0 + 1, bx + w, wy0 + 9], radius=2,
                            fill=245 if i == 2 else 175, outline=40)
        cx, cy = bx + w // 2, wy0 + 5
        if i == 0:
            d.line([(cx - 2, cy + 2), (cx + 2, cy + 2)], fill=30)
        elif i == 1:
            d.rectangle([cx - 2, cy - 2, cx + 2, cy + 2], outline=30)
        else:
            d.line([(cx - 2, cy - 2), (cx + 2, cy + 2)], fill=10)
            d.line([(cx - 2, cy + 2), (cx + 2, cy - 2)], fill=10)
        bx += w + 1

    # client area
    cx0, cy0, cx1, cy1 = wx0 + 3, wy0 + 15, wx1 - 3, wy1 - 3
    d.rectangle([cx0, cy0, cx1, cy1], fill=235, outline=60)

    # portrait
    port = Image.open(PORTRAIT).convert("RGBA")
    port = Image.alpha_composite(Image.new("RGBA", port.size, "white"), port).convert("L")
    side = cy1 - cy0 - 3
    port = port.crop((60, 20, 1140, 1100)).resize((side, side), Image.LANCZOS)
    img.paste(ImageOps.autocontrast(port, cutoff=1), (cx0 + 2, cy0 + 2))
    d.rectangle([cx0 + 1, cy0 + 1, cx0 + side + 2, cy0 + side + 2], outline=40)

    # info panel
    tx = cx0 + side + 8
    d.text((tx, cy0 + 3), "Luca Wood", font=font(12), fill=0)
    d.text((tx, cy0 + 18), "Species: wolf", font=font(9), fill=55)
    d.text((tx, cy0 + 29), status, font=font(9), fill=55)
    py, end = cy0 + 45, cx1 - 6  # Aero progress bar
    d.rounded_rectangle([tx, py, end, py + 7], radius=2, fill=200, outline=60)
    fill_to = tx + 1 + int((end - tx - 2) * progress)
    d.rounded_rectangle([tx + 1, py + 1, fill_to, py + 6], radius=2, fill=110)
    d.line([(tx + 2, py + 2), (fill_to - 1, py + 2)], fill=200)

    return img.point(lambda v: (v // 17) * 17)  # the back screen's 16 greys


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
            d.ellipse([x * scale + 1, y * scale + 1, x * scale + scale - 2,
                       y * scale + scale - 2], fill=frame.getpixel((x, y)))
    return out


def main() -> None:
    OUT.mkdir(exist_ok=True)
    PREVIEW.mkdir(exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()

    manifest = {}
    for mood, (maker, n, loops) in MOODS.items():
        frames = [maker(n, i) for i in range(n)]
        names = []
        for i, f in enumerate(frames):
            names.append(f"{mood}_{i:02d}.png")
            f.save(OUT / names[-1])
        back = f"back_{mood}.png"
        back_frame(STATUS[mood], 1.0 if mood == "yay" else 0.8).save(OUT / back)
        manifest[mood] = {"frames": names, "back": back, "loop": loops}

        leds = [led_preview(f) for f in frames]
        leds[0].save(PREVIEW / f"{mood}.gif", save_all=True, append_images=leds[1:],
                     duration=140, loop=0)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))

    back_frame(STATUS["idle"]).resize((BACK_W * 4, BACK_H * 4), Image.NEAREST) \
        .save(PREVIEW / "back.png")
    total = sum(len(m["frames"]) + 1 for m in manifest.values())
    print(f"Rendered {len(manifest)} moods ({total} images) into {OUT}")


if __name__ == "__main__":
    main()
