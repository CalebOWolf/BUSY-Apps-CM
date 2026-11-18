"""
Artwork for Luca PC Stats, drawn with Pillow.

Uploaded once:
  sky_N.png          72x16 glossy Aero sky with a few drifting bubbles
  tile_<mood>_N.png  19x16 glass tile with Luca, who feels the heat:
                     cool (happy), ok, warm (sweating), hot (tongue out, flushed)
  label_<page>.png   the page names: CPU, RAM, GPU, TEMP
  char_<code>.png    single digits and symbols, so numbers can change every
                     second without uploading anything new
Re-drawn every couple of seconds:
  the back screen    "Luca Monitor", a Windows 7 Task Manager-style window

    python art.py      # writes previews into preview/
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from pixelart import GLYPHS, aero_sky, draw_text, led_preview, lerp, text_width  # noqa: E402
from pixelart import ui_font as font  # noqa: E402

HERE = Path(__file__).parent
FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80
TILE_W = 19
SKY_FRAMES = 8

# Front layout (to the right of Luca's tile)
LABEL_XY = (21, 1)
VALUE_RIGHT = 70           # numbers are right-aligned to this column
VALUE_Y = 1
GAUGE = (21, 10, 50, 4)    # x, y, w, h
DOTS_XY = (21, 15)         # page dots, 3 px apart

PAGES = ["cpu", "ram", "gpu", "temp"]
CHARS = "0123456789%°CF-."
MOODS = ["cool", "ok", "warm", "hot"]

MINT = (80, 240, 190)


# --------------------------------------------------------------------------
# Luca, feeling the heat
# --------------------------------------------------------------------------
PALETTE = {
    "K": (28, 30, 44), "W": (255, 255, 255), "S": (190, 205, 230),
    "G": (150, 150, 158), "T": (40, 235, 175), "M": (8, 8, 12),
    "O": (245, 160, 80), "N": (225, 140, 115), "P": (255, 150, 160),
    "R": (255, 110, 120),   # flushed cheeks
    "B": (120, 200, 255),   # sweat drop
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


def luca(mood: str) -> list[str]:
    rows = [list(r) for r in LUCA]
    if mood == "cool":    # ^^ happy eyes
        rows[6][3:5], rows[7][3:5] = "KK", "WW"
        rows[6][10:12], rows[7][10:12] = "SS", "MM"
    if mood in ("warm", "hot"):  # a sweat drop by his mint ear
        rows[2][15], rows[3][15], rows[4][15] = "B", "B", "B"
    if mood == "hot":     # flushed, tongue out, panting
        rows[9][2], rows[9][11] = "R", "R"
        rows[10][2], rows[10][11] = "R", "R"
        rows[13][6:9] = "PPP"
        rows[14][6:9] = "KPK"
    return ["".join(r) for r in rows]


def glass_tile() -> Image.Image:
    img = Image.new("RGBA", (TILE_W, FRONT_H))
    d = ImageDraw.Draw(img)
    for y in range(FRONT_H):
        c = lerp((90, 190, 250), (10, 60, 150), y / (FRONT_H - 1))
        if y < FRONT_H // 2:
            c = lerp(c, (255, 255, 255), 0.45 * (1 - y / (FRONT_H / 2)))
        d.line([(0, y), (TILE_W - 1, y)], fill=c + (255,))
    d.line([(TILE_W - 1, 0), (TILE_W - 1, FRONT_H - 1)], fill=(200, 240, 255, 255))
    return img


def tile(mood: str, frame: int) -> Image.Image:
    img = glass_tile()
    bob = frame % 2
    for y, row in enumerate(luca(mood)):
        for x, ch in enumerate(row):
            if ch != "." and 0 <= y + bob < FRONT_H:
                img.putpixel((x + 1, y + bob), PALETTE[ch] + (255,))
    return img


# --------------------------------------------------------------------------
# Sky, labels and characters
# --------------------------------------------------------------------------
def sky(frame: int) -> Image.Image:
    img = aero_sky(FRONT_W, FRONT_H)
    for bx, phase in ((30, 0), (47, 5), (63, 11)):
        p = (phase + frame * 22 / SKY_FRAMES) % 22
        x, y = bx + round(math.sin(p / 3)), round(FRONT_H + 2 - p)
        for X, Y in [(x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1)]:
            if 0 <= X < FRONT_W and 0 <= Y < FRONT_H:
                img.putpixel((X, Y), lerp(img.getpixel((X, Y)), (230, 250, 255), 0.4))
    return img


def label(page: str) -> Image.Image:
    text = page.upper()
    img = Image.new("RGBA", (text_width(text) + 2, 9), (0, 0, 0, 0))
    draw_text(img, text, 0, 0, color=MINT + (255,))
    return img


def char_name(ch: str) -> str:
    return {"%": "pct", "°": "deg", "-": "dash", ".": "dot"}.get(ch, ch)


def char(ch: str) -> Image.Image:
    img = Image.new("RGBA", (len(GLYPHS[ch][0]) + 1, 8), (0, 0, 0, 0))
    draw_text(img, ch, 0, 0)
    return img


def char_width(ch: str) -> int:
    return len(GLYPHS[ch][0]) + 1  # glyph plus its 1 px gap


def gauge_color(frac: float) -> str:
    """Mint when relaxed, sunny yellow when busy, red when maxed out."""
    if frac < 0.6:
        c = lerp((80, 240, 190), (180, 245, 120), frac / 0.6)
    elif frac < 0.85:
        c = lerp((180, 245, 120), (255, 215, 70), (frac - 0.6) / 0.25)
    else:
        c = lerp((255, 215, 70), (255, 80, 80), min(1, (frac - 0.85) / 0.15))
    return "#%02X%02X%02XFF" % c


# --------------------------------------------------------------------------
# Back screen: "Luca Monitor"
# --------------------------------------------------------------------------
def rate(bps: float | None) -> str:
    if bps is None:
        return "--"
    for unit, size in (("MB/s", 1e6), ("KB/s", 1e3)):
        if bps >= size:
            return f"{bps / size:.1f} {unit}"
    return f"{bps:.0f} B/s"


def fmt(value: float | None, suffix: str = "") -> str:
    return "--" if value is None else f"{value:.0f}{suffix}"


def back_screen(s, fahrenheit: bool = False) -> Image.Image:
    temp_unit = "°F" if fahrenheit else "°C"

    def temp(t):
        return None if t is None else (t * 9 / 5 + 32 if fahrenheit else t)

    img = Image.new("L", (BACK_W, BACK_H), 0)
    d = ImageDraw.Draw(img)
    for y in range(BACK_H):  # desktop glow
        for x in range(BACK_W):
            img.putpixel((x, y), int(60 * max(0, 1 - math.hypot(x - 140, y - 70) / 150)))

    wx0, wy0, wx1, wy1 = 2, 1, 157, 78
    d.rounded_rectangle([wx0, wy0, wx1, wy1], radius=5, fill=120, outline=230)
    for y in range(wy0 + 1, wy0 + 13):
        d.line([(wx0 + 2, y), (wx1 - 2, y)], fill=int(205 - (y - wy0) * 6))
    for sx in (66, 74, 124):
        d.line([(sx, wy0 + 1), (sx + 10, wy0 + 12)], fill=235)
    # title: a little wolf-paw "monitor" icon and the name
    d.rectangle([wx0 + 4, wy0 + 2, wx0 + 11, wy0 + 8], outline=20)
    d.line([(wx0 + 5, wy0 + 6), (wx0 + 7, wy0 + 4), (wx0 + 8, wy0 + 6), (wx0 + 10, wy0 + 3)], fill=20)
    d.text((wx0 + 15, wy0), "Luca Monitor", font=font(10), fill=20)
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

    # CPU usage history, Task Manager style: a dark grid with a bright line
    gx0, gy0, gx1, gy1 = cx0 + 3, cy0 + 12, cx0 + 56, cy1 - 3
    d.text((gx0, cy0 + 1), f"CPU {fmt(s.cpu, '%')}", font=font(9), fill=0)
    d.rectangle([gx0, gy0, gx1, gy1], fill=20, outline=60)
    for x in range(gx0 + 6, gx1, 6):
        d.line([(x, gy0 + 1), (x, gy1 - 1)], fill=45)
    for y in range(gy0 + 6, gy1, 6):
        d.line([(gx0 + 1, y), (gx1 - 1, y)], fill=45)
    hist = s.history[-(gx1 - gx0 - 1):]
    if len(hist) > 1:
        step = (gx1 - gx0 - 2) / max(len(hist) - 1, 1)
        pts = [(gx1 - 1 - (len(hist) - 1 - i) * step,
                gy1 - 1 - (v / 100) * (gy1 - gy0 - 2)) for i, v in enumerate(hist)]
        d.polygon(pts + [(pts[-1][0], gy1 - 1), (pts[0][0], gy1 - 1)], fill=70)
        d.line(pts, fill=255)

    # the numbers
    tx, ty = gx1 + 6, cy0 + 2
    rows = [
        ("CPU", fmt(temp(s.cpu_temp), temp_unit)),
        ("RAM", fmt(s.ram, "%") + ("" if s.ram_used is None else
                                  f"  {s.ram_used:.1f}/{s.ram_total:.0f}G")),
        ("GPU", f"{fmt(s.gpu, '%')}  {fmt(temp(s.gpu_temp), temp_unit)}"
         if (s.gpu is not None or s.gpu_temp is not None) else "--"),
        ("Down", rate(s.net_down)),
        ("Up", rate(s.net_up)),
    ]
    for i, (name, value) in enumerate(rows):
        y = ty + i * 11
        d.text((tx, y), name, font=font(9), fill=60)
        d.text((tx + 29, y), value, font=font(9), fill=0)

    return img.point(lambda v: (v // 17) * 17)


# --------------------------------------------------------------------------
# Previews
# --------------------------------------------------------------------------
def main() -> None:
    from stats import DemoStats
    from pc_stats import Front

    preview = HERE / "preview"
    preview.mkdir(exist_ok=True)
    demo = DemoStats()
    front = Front(fahrenheit=False)
    frames = []
    for i in range(48):
        demo.t0 -= 0.6  # fast-forward through the demo's hot spell
        snap = demo.read()
        front.update(snap)
        if i % 12 == 0:
            front.next_page()
        frames.append(led_preview(front.compose(i)))
    frames[0].save(preview / "front.gif", save_all=True, append_images=frames[1:],
                   duration=180, loop=0)
    back_screen(snap).resize((BACK_W * 4, BACK_H * 4), Image.NEAREST).save(preview / "back.png")
    moods = Image.new("RGB", (TILE_W * 4 * 8 + 30, FRONT_H * 8), (40, 40, 40))
    for k, mood in enumerate(MOODS):
        moods.paste(led_preview(tile(mood, 0).convert("RGB"), 8), (k * (TILE_W * 8 + 10), 0))
    moods.save(preview / "moods.png")
    print(f"Wrote previews to {preview}")


if __name__ == "__main__":
    main()
