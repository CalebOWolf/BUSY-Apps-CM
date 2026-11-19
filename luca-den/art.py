"""
Artwork for Luca's Den: the glossy "channel switch" cards shown between
turns, and the back-screen window listing the rotation.

    python art.py      # writes previews into preview/
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from pixelart import draw_text, led_preview, lerp  # noqa: E402
from pixelart import ui_font as font  # noqa: E402

HERE = Path(__file__).parent
FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80
TILE_W = 19
CARD_FRAMES = 6

# Each app in the rotation: its card color and a little pixel icon.
THEMES = {
    "luca_pc_stats": ("STATS", (60, 200, 160), "stats"),
    "luca_weather_den": ("WEATHER", (90, 170, 255), "weather"),
    "luca_aero_clock": ("CLOCK", (140, 120, 255), "clock"),
    "luca_update_howl": ("UPDATES", (40, 140, 230), "box"),
}
ICONS = {
    "stats": ["..........", "........XX", "........XX", ".....XX.XX", ".....XX.XX",
              "..XX.XX.XX", "..XX.XX.XX", "..XX.XX.XX", "XXXXXXXXXX"],
    "weather": ["...Y.Y....", "....YY....", "..YYYYY...", "..YYYY.WW.", "...YYWWWWW",
                "....WWWWWW", "...WWWWWWW", "....WWWWW.", ".........."],
    "box": ["..........", ".XXXXXXXX.", ".X..XX..X.", ".XXXXXXXX.", ".X......X.",
            ".X..YY..X.", ".X......X.", ".XXXXXXXX.", ".........."],
    "clock": ["..XXXXX...", ".X..X..X..", "X...X...X.", "X...X...X.", "X...XXX.X.",
              "X.......X.", ".X.....X..", "..XXXXX...", ".........."],
}
ICON_COLORS = {"X": (255, 255, 255), "Y": (255, 215, 70), "W": (245, 250, 255)}

PALETTE = {"K": (28, 30, 44), "W": (255, 255, 255), "S": (190, 205, 230), "G": (150, 150, 158),
           "T": (40, 235, 175), "M": (8, 8, 12), "O": (245, 160, 80), "N": (225, 140, 115),
           "P": (255, 150, 160)}
LUCA = [
    "KK...........KK.",
    "KGK.........KTK.",
    "KGGKKKKKKKKKTTK.",
    "KGWWWWWWWWWWWTK.",
    "KWWWWWWWWWWWWWK.",
    "KWWWWWWWWMMMMWK.",
    "KWWKKWWWMMSSMWK.",   # ^^ happy eyes
    "KWWWWWWWMMMMMWK.",
    "KWWWWWWWWMMMWWK.",
    ".KWWWWNNNWWWWK..",
    ".KWWTWNNNWTWWK..",
    "..KWWWWKWWWWK...",
    "..KWWKPPPKWWK...",
    "...KWWKKKWWK....",
    "....KWWWWWWK....",
    ".....KKKKKK.....",
]


def card(app: str, frame: int) -> Image.Image:
    """The switch card: slides in from the right, Luca waves you to the next app."""
    label, color, icon = THEMES.get(app, (app.replace("luca_", "").upper(), (80, 240, 190), "stats"))
    img = Image.new("RGB", (FRONT_W, FRONT_H))
    d = ImageDraw.Draw(img)
    top, bottom = lerp(color, (255, 255, 255), 0.35), lerp(color, (0, 20, 60), 0.55)
    for y in range(FRONT_H):
        c = lerp(top, bottom, y / (FRONT_H - 1))
        if y < 7:
            c = lerp(c, (255, 255, 255), 0.4 * (1 - y / 7))
        d.line([(0, y), (FRONT_W - 1, y)], fill=c)
    # slide the content in from the right over the first frames
    shift = round((FRONT_W - TILE_W) * max(0.0, 1 - frame / (CARD_FRAMES - 2)) ** 2)
    ix = TILE_W + 1 + shift
    for y, row in enumerate(ICONS[icon]):
        for x, ch in enumerate(row):
            if ch != "." and 0 <= ix + x < FRONT_W:
                img.putpixel((ix + x, 4 + y), ICON_COLORS[ch])
    layer = Image.new("RGBA", (FRONT_W, FRONT_H), (0, 0, 0, 0))
    draw_text(layer, label, ix + 11, 5, shadow=(0, 20, 60, 255))
    img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
    # Luca on the left, waving (his ear wiggles)
    for y, row in enumerate(LUCA):
        for x, ch in enumerate(row):
            if ch != ".":
                yy = y - (1 if frame % 2 and y < 3 and x > 8 else 0)
                if 0 <= yy:
                    img.putpixel((x + 1, yy), PALETTE[ch])
    d = ImageDraw.Draw(img)
    d.line([(TILE_W - 1, 0), (TILE_W - 1, FRONT_H - 1)], fill=(220, 240, 255))
    return img


def back_screen(rotation: list[str], current: str, seconds: int) -> Image.Image:
    img = Image.new("L", (BACK_W, BACK_H), 0)
    d = ImageDraw.Draw(img)
    for y in range(BACK_H):
        for x in range(BACK_W):
            img.putpixel((x, y), int(55 * max(0, 1 - math.hypot(x - 80, y - 40) / 140)))
    wx0, wy0, wx1, wy1 = 2, 1, 157, 78
    d.rounded_rectangle([wx0, wy0, wx1, wy1], radius=5, fill=120, outline=230)
    for y in range(wy0 + 1, wy0 + 13):
        d.line([(wx0 + 2, y), (wx1 - 2, y)], fill=int(205 - (y - wy0) * 6))
    d.text((wx0 + 15, wy0), "Luca's Den", font=font(10), fill=20)
    d.polygon([(wx0 + 4, wy0 + 9), (wx0 + 8, wy0 + 2), (wx0 + 12, wy0 + 9)], outline=20)  # a little den
    cx0, cy0, cx1, cy1 = wx0 + 3, wy0 + 14, wx1 - 3, wy1 - 3
    d.rectangle([cx0, cy0, cx1, cy1], fill=235, outline=60)
    d.text((cx0 + 4, cy0 + 2), f"Taking turns, {seconds} s each:", font=font(9), fill=40)
    for i, app in enumerate(rotation[:4]):
        y = cy0 + 14 + i * 11
        label = THEMES.get(app, (app,))[0].title()
        on = app == current
        if on:
            d.rounded_rectangle([cx0 + 2, y - 1, cx1 - 2, y + 9], radius=3, fill=190)
        d.text((cx0 + 8, y), ("▶ " if on else "   ") + label, font=font(9), fill=0 if on else 70)
        if on:
            d.text((cx1 - 6, y), "up now", font=font(8), fill=40, anchor="ra")
    return img.point(lambda v: (v // 17) * 17)


def main() -> None:
    preview = HERE / "preview"
    preview.mkdir(exist_ok=True)
    frames = [led_preview(card(app, f), 8) for app in THEMES for f in range(CARD_FRAMES + 4)]
    frames[0].save(preview / "cards.gif", save_all=True, append_images=frames[1:],
                   duration=140, loop=0, optimize=True)
    back_screen(list(THEMES), "luca_weather_den", 60).resize((BACK_W * 4, BACK_H * 4), Image.NEAREST) \
        .save(preview / "back.png")
    print(f"Wrote previews to {preview}")


if __name__ == "__main__":
    main()
