"""
Artwork for Luca Blockland, drawn with Pillow.

Uploaded once (for the time of day you're playing in):
  scene_<sky>_NN.png  72x16 blocky landscape that scrolls by: grassy hills,
                      dirt, stone, little trees and a pond, under a daytime
                      Aero-blue sky with square clouds or a starry night with
                      a square moon
  tile_<pose>_N.png   19x16 glass tile with Luca holding a pickaxe
When it changes:
  the text line       your instance's name, then how long you've played
  the back screen     "Luca Blockland", a Windows 7-style window

All the art is original pixel art in this repo's Frutiger Aero style.

    python art.py      # writes previews into preview/
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from pixelart import draw_text, led_preview, lerp, text_width, to_font_text  # noqa: E402
from pixelart import ui_font as font  # noqa: E402

HERE = Path(__file__).parent
FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80
TILE_W = 19
AREA_X, AREA_W = 20, 52
TEXT_Y = 1
SCENE_FRAMES = 48          # the landscape loops every 48 frames (1 px a frame)
SKIES = ("day", "night")
POSES = {"dig": 2, "happy": 2}
GAP = "     "
LED_LAUNCH = "#40E070FF"   # a friendly green blink when the game starts

WHITE = (255, 255, 255, 255)
SHADOW = (10, 30, 20, 255)


# --------------------------------------------------------------------------
# The landscape
# --------------------------------------------------------------------------
GRASS = (95, 200, 70)
GRASS_DARK = (60, 150, 50)
DIRT = (140, 95, 55)
DIRT_DARK = (105, 70, 40)
STONE = (125, 128, 135)
STONE_DARK = (95, 98, 105)
WOOD = (110, 75, 40)
LEAVES = (50, 150, 60)
LEAVES_LIGHT = (100, 205, 90)
WATER = (60, 140, 230)
WATER_LIGHT = (150, 210, 255)


def _terrain() -> list[int]:
    """Ground height (in pixels from the bottom) for each column of one loop,
    in 2-pixel steps so it reads as blocks."""
    rng = random.Random(11)
    heights, h = [], 4
    for _ in range(SCENE_FRAMES // 2):
        h = max(3, min(9, h + rng.choice((-2, -2, 0, 2, 2))))
        heights += [h, h]
    heights[-4:] = [heights[0]] * 4  # join up with the start of the loop
    return heights


TERRAIN = _terrain()
TREES = (9, 31)       # columns (in one loop) where little trees grow
POND = range(40, 46)  # a dip filled with water


def _ground_at(col: int) -> int:
    h = TERRAIN[col % SCENE_FRAMES]
    return 2 if (col % SCENE_FRAMES) in POND else h


def sky(kind: str) -> Image.Image:
    img = Image.new("RGB", (FRONT_W, FRONT_H))
    d = ImageDraw.Draw(img)
    top, bottom = ((70, 160, 245), (185, 230, 255)) if kind == "day" else ((5, 10, 40), (35, 45, 95))
    for y in range(FRONT_H):
        c = lerp(top, bottom, y / (FRONT_H - 1))
        if kind == "day" and y < 6:
            c = lerp(c, (255, 255, 255), 0.25 * (1 - y / 6))  # Aero gloss
        d.line([(0, y), (FRONT_W - 1, y)], fill=c)
    return img


def scene(kind: str, frame: int) -> Image.Image:
    img = sky(kind)
    px = img.load()
    shift = frame % SCENE_FRAMES
    if kind == "day":
        # a square sun, and square clouds drifting at half speed
        for y in range(1, 5):
            for x in range(62, 66):
                px[x, y] = (255, 240, 150) if 0 < y < 4 and 62 < x < 65 else (255, 210, 90)
        cshift = (frame // 2) % 24
        for cx, cy, w in ((4, 2, 8), (16, 4, 6)):
            for k in range(3):
                x0 = (cx - cshift + k * 24) % 72
                for x in range(x0, x0 + w):
                    for y in (cy, cy + 1):
                        if 0 <= x < FRONT_W:
                            px[x, y] = (250, 252, 255) if y == cy else (220, 235, 250)
    else:
        rng = random.Random(3)
        for _ in range(16):
            x, y = rng.randrange(FRONT_W), rng.randrange(8)
            if (x + frame // 3) % 5:  # some twinkle
                px[x, y] = (230, 235, 255)
        for y in range(1, 5):
            for x in range(60, 64):
                px[x, y] = (235, 240, 255) if not (x == 61 and y == 2) else (190, 200, 225)

    for x in range(FRONT_W):
        col = x + shift
        h = _ground_at(col)
        top = FRONT_H - h
        pond = (col % SCENE_FRAMES) in POND
        for y in range(top, FRONT_H):
            depth = y - top
            if pond and depth == 0:
                c = WATER_LIGHT if (col + frame // 2) % 4 == 0 else WATER
            elif depth == 0:
                c = GRASS
            elif depth == 1:
                c = GRASS_DARK if (col + y) % 3 == 0 else DIRT
            elif depth >= 5:
                c = STONE_DARK if (col * 7 + y * 3) % 5 == 0 else STONE
            else:
                c = DIRT_DARK if (col * 5 + y * 3) % 7 == 0 else DIRT
            if kind == "night":
                c = lerp(c, (10, 15, 45), 0.35)
            px[x, y] = c
    # little trees: a trunk and a square of leaves
    for tree in TREES:
        for k in (0, 1):
            x0 = tree - shift + k * SCENE_FRAMES
            ground = FRONT_H - _ground_at(tree)
            for y in range(ground - 3, ground):
                if 0 <= x0 < FRONT_W:
                    px[x0, y] = lerp(WOOD, (10, 15, 45), 0.35) if kind == "night" else WOOD
            for y in range(ground - 7, ground - 3):
                for x in range(x0 - 2, x0 + 3):
                    if 0 <= x < FRONT_W and 0 <= y:
                        c = LEAVES_LIGHT if (x + y) % 3 == 0 else LEAVES
                        px[x, y] = lerp(c, (10, 15, 45), 0.35) if kind == "night" else c
    return img


# --------------------------------------------------------------------------
# Luca with a pickaxe
# --------------------------------------------------------------------------
PALETTE = {
    "K": (28, 30, 44), "W": (255, 255, 255), "S": (190, 205, 230),
    "G": (150, 150, 158), "T": (40, 235, 175), "M": (8, 8, 12),
    "O": (245, 160, 80), "N": (225, 140, 115), "P": (255, 150, 160),
    "B": (120, 80, 40),     # pickaxe handle
    "I": (235, 240, 250),   # pickaxe head, shiny white-silver
}
LUCA = [
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
# (x, y, color) in tile pixels, just right of Luca's face
PICK_UP = [(15, 3, "I"), (16, 2, "I"), (17, 2, "I"), (18, 3, "I"), (16, 3, "B"),
           (16, 4, "B"), (16, 5, "B"), (16, 6, "B"), (16, 7, "B"), (16, 8, "B")]
PICK_DOWN = [(15, 7, "I"), (16, 6, "I"), (17, 6, "I"), (18, 7, "I"), (16, 7, "B"),
             (16, 8, "B"), (16, 9, "B"), (16, 10, "B"), (16, 11, "B"), (16, 12, "B")]


def luca(pose: str, frame: int) -> list[str]:
    rows = [list(r) for r in LUCA]
    if pose == "happy":  # ^^
        rows[6][3:5], rows[7][3:5] = "KK", "WW"
        rows[6][10:12], rows[7][10:12] = "SS", "MM"
    elif pose == "dig" and frame % 2:  # a blink between swings
        rows[6][3:5], rows[7][3:5] = "WW", "KK"
        rows[6][10:12], rows[7][10:12] = "MM", "KK"
    return ["".join(r) for r in rows]


def glass_tile() -> Image.Image:
    img = Image.new("RGBA", (TILE_W, FRONT_H))
    d = ImageDraw.Draw(img)
    for y in range(FRONT_H):
        c = lerp((120, 215, 130), (20, 110, 60), y / (FRONT_H - 1))  # a leafy green glass
        if y < FRONT_H // 2:
            c = lerp(c, (255, 255, 255), 0.45 * (1 - y / (FRONT_H / 2)))
        d.line([(0, y), (TILE_W - 1, y)], fill=c + (255,))
    d.line([(TILE_W - 1, 0), (TILE_W - 1, FRONT_H - 1)], fill=(210, 255, 220, 255))
    return img


def tile(pose: str, frame: int) -> Image.Image:
    img = glass_tile()
    for y, row in enumerate(luca(pose, frame)):
        for x, ch in enumerate(row):
            if ch != ".":
                img.putpixel((x + 1, y), PALETTE[ch] + (255,))
    for x, y, ch in (PICK_DOWN if pose == "dig" and frame % 2 else PICK_UP):
        img.putpixel((x, y), PALETTE[ch] + (255,))
    return img


# --------------------------------------------------------------------------
# The text line
# --------------------------------------------------------------------------
def text_strip(text: str) -> tuple[Image.Image, int]:
    """The text as a transparent strip, centred if it fits. If not, two
    copies with a gap, and how far to scroll before it repeats."""
    text = to_font_text(text)
    w = text_width(text)
    if w <= AREA_W - 2:
        img = Image.new("RGBA", (AREA_W, 9), (0, 0, 0, 0))
        draw_text(img, text, (AREA_W - w) // 2, 0, shadow=SHADOW)
        return img, 0
    loop = text_width(text + GAP)
    img = Image.new("RGBA", (loop + w + 2, 9), (0, 0, 0, 0))
    draw_text(img, text, 0, 0, shadow=SHADOW)
    draw_text(img, text, loop, 0, shadow=SHADOW)
    return img, loop


def played(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def played_short(seconds: float) -> str:
    """For the front, which updates once a minute: 47M, 1H 05M."""
    m = max(0, int(seconds)) // 60
    return f"{m // 60}H {m % 60:02d}M" if m >= 60 else f"{m}M"


# --------------------------------------------------------------------------
# Back screen: "Luca Blockland"
# --------------------------------------------------------------------------
def back_screen(instance: str, launcher: str, seconds: float, started: str) -> Image.Image:
    img = Image.new("L", (BACK_W, BACK_H), 0)
    d = ImageDraw.Draw(img)
    for y in range(BACK_H):
        for x in range(BACK_W):
            img.putpixel((x, y), int(55 * max(0, 1 - math.hypot(x - 30, y - 10) / 150)))
    wx0, wy0, wx1, wy1 = 2, 1, 157, 78
    d.rounded_rectangle([wx0, wy0, wx1, wy1], radius=5, fill=120, outline=230)
    for y in range(wy0 + 1, wy0 + 13):
        d.line([(wx0 + 2, y), (wx1 - 2, y)], fill=int(205 - (y - wy0) * 6))
    for sx in (66, 74, 124):
        d.line([(sx, wy0 + 1), (sx + 10, wy0 + 12)], fill=235)
    # a little grass block icon
    d.rectangle([wx0 + 4, wy0 + 2, wx0 + 10, wy0 + 8], fill=60, outline=20)
    d.rectangle([wx0 + 4, wy0 + 2, wx0 + 10, wy0 + 4], fill=170)
    d.text((wx0 + 15, wy0), "Luca Blockland", font=font(10), fill=20)
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
    cx0, cy0, cx1, cy1 = wx0 + 3, wy0 + 14, wx1 - 3, wy1 - 3
    d.rectangle([cx0, cy0, cx1, cy1], fill=235, outline=60)

    # blocky hills along the bottom of the window
    for x in range(cx0 + 1, cx1):
        h = 2 + TERRAIN[(x // 2) % SCENE_FRAMES] // 2
        d.line([(x, cy1 - h), (x, cy1 - 1)], fill=150)
        d.point((x, cy1 - h), fill=90)

    d.text((cx0 + 6, cy0 + 3), "Now playing", font=font(9), fill=80)
    d.text((cx0 + 6, cy0 + 12), fit(d, instance, font(14), cx1 - cx0 - 12), font=font(14), fill=0)
    d.text((cx0 + 6, cy0 + 30), f"for {played(seconds)}", font=font(11), fill=30)
    info = f"{launcher}  ·  since {started}" if launcher else f"since {started}"
    d.text((cx0 + 6, cy0 + 43), fit(d, info, font(9), cx1 - cx0 - 12), font=font(9), fill=60)
    return img.point(lambda v: (v // 17) * 17)


def fit(d, text, f, width):
    if d.textlength(text, font=f) <= width:
        return text
    while text and d.textlength(text + "…", font=f) > width:
        text = text[:-1]
    return text.rstrip() + "…"


# --------------------------------------------------------------------------
# Previews
# --------------------------------------------------------------------------
def compose(kind: str, frame: int, text: str) -> Image.Image:
    out = scene(kind, frame).convert("RGBA")
    if text:
        strip, loop = text_strip(text)
        off = (frame % loop) if loop else 0
        out.alpha_composite(strip.crop((off, 0, off + AREA_W, 9)), (AREA_X, TEXT_Y))
    out.alpha_composite(tile("dig", frame // 2), (0, 0))
    return out.convert("RGB")


def main() -> None:
    preview = HERE / "preview"
    preview.mkdir(exist_ok=True)
    frames = [led_preview(compose("day", i, "WOLF HOWL"), 8) for i in range(24)]
    frames += [led_preview(compose("day", 24 + i, ""), 8) for i in range(16)]
    frames += [led_preview(compose("day", 24 + i, "1H 05M"), 8) for i in range(12)]
    frames += [led_preview(compose("night", i, "WOLF HOWL"), 8) for i in range(24)]
    frames[0].save(preview / "front.gif", save_all=True, append_images=frames[1:],
                   duration=200, loop=0, optimize=True)
    back_screen("Wolf Howl", "Prism Launcher", 3923, "19:02").resize(
        (BACK_W * 4, BACK_H * 4), Image.NEAREST).save(preview / "back.png")
    print(f"Wrote previews to {preview}")


if __name__ == "__main__":
    main()
