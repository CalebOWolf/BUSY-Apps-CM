"""
What the speed test looks like: plain text on black, one color per reading.

  front(label, value, color, progress)   the 72x16 LED strip
  back(result, state)                    the 160x80 back screen
"""

from __future__ import annotations

import time

from PIL import Image, ImageDraw

from pixelart import GLYPHS, draw_text, text_width, ui_font

FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80

DOWN = (60, 200, 255)
UP = (255, 170, 40)
PING = (120, 235, 140)
WHITE = (235, 235, 235)
DIM = (110, 110, 110)
ERROR = (255, 80, 80)
BLACK = (0, 0, 0)
SHADOW = (0, 0, 0, 255)

# two arrows for the strip, drawn in the same 5x7 style as the font
GLYPHS.setdefault("↓", "..X.. ..X.. ..X.. ..X.. X.X.X .XXX. ..X..".split())
GLYPHS.setdefault("↑", "..X.. .XXX. X.X.X ..X.. ..X.. ..X.. ..X..".split())


def front(label: str, value: str, color=WHITE, progress: float | None = None,
          value_color=WHITE) -> Image.Image:
    """Two lines: a colored label on top and the reading below, both
    centered, with a thin progress line along the bottom while testing."""
    img = Image.new("RGB", (FRONT_W, FRONT_H), BLACK)
    for line, y, c in ((label, 0, color), (value, 8, value_color)):
        line = _fit(line)
        draw_text(img, line, (FRONT_W - text_width(line)) // 2, y, color=(*c, 255), shadow=SHADOW)
    if progress is not None:
        d = ImageDraw.Draw(img)
        d.line([(0, 15), (FRONT_W - 1, 15)], fill=_dim(color, 0.2))
        filled = round(progress * FRONT_W)
        if filled:
            d.line([(0, 15), (filled - 1, 15)], fill=color)
    return img


def _fit(line: str) -> str:
    line = "".join(c if c == " " or c in GLYPHS else "?" for c in line.upper())
    while line and text_width(line) > FRONT_W:
        line = line[:-1]
    return line


def _dim(c, t: float):
    return tuple(int(x * t) for x in c)


def back(result, state: str, detail: str = "") -> Image.Image:
    """A simple results card: download, upload, ping, and when it was tested."""
    img = Image.new("RGB", (BACK_W, BACK_H), BLACK)
    d = ImageDraw.Draw(img)
    title, small, big = ui_font(12), ui_font(10), ui_font(14)
    d.text((4, 2), "Speedtest", font=title, fill=(255, 255, 255))
    status = {"testing": "testing…", "error": "failed"}.get(state, "")
    if status:
        d.text((BACK_W - 4, 2), status, font=small, fill=(180, 180, 180), anchor="ra")
    d.line([(4, 17), (BACK_W - 5, 17)], fill=(90, 90, 90))

    if result is None:
        msg = detail or ("Running the first test…" if state == "testing" else "Press OK to test")
        d.text((BACK_W // 2, 46), msg, font=small, fill=(200, 200, 200), anchor="mm")
        return img

    from tester import format_speed
    down, up = format_speed(result.down_mbps), format_speed(result.up_mbps)
    rows = [
        ("Download", down[0], down[1].capitalize()),
        ("Upload", up[0], up[1].capitalize()),
        ("Ping", f"{result.ping_ms:.0f}", f"ms  ±{result.jitter_ms:.0f}"),
    ]
    y = 20
    for name, number, unit in rows:
        d.text((4, y + 2), name, font=small, fill=(170, 170, 170))
        d.text((112, y), number, font=big, fill=(255, 255, 255), anchor="ra")
        d.text((116, y + 3), unit, font=small, fill=(170, 170, 170))
        y += 15

    when = time.strftime("%H:%M", time.localtime(result.finished))
    foot = f"Tested {when}" + (f" · {result.server}" if result.server else "")
    if state == "error" and detail:
        foot = f"Last try failed: {detail}"
    d.text((4, BACK_H - 11), foot[:34], font=small, fill=(130, 130, 130))
    return img
