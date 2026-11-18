"""
Artwork for Luca Notify Den, drawn with Pillow.

Uploaded once:
  sky_N.png          72x16 glossy Aero sky with drifting bubbles
  tile_<pose>_N.png  19x16 glass tile with Luca:
                     alert (ears up, a yellow "!", hopping), urgent (a red "!"),
                     reading (eyes on the message)
Per notification:
  a text strip       "APP  SUMMARY - BODY" in pixel letters, app name in its color
  the back screen    "Luca Inbox", a Windows 7-style list of recent notifications

    python art.py      # writes previews into preview/
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from pixelart import aero_sky, draw_text, led_preview, lerp, text_width, to_font_text  # noqa: E402
from pixelart import ui_font as font  # noqa: E402

HERE = Path(__file__).parent
FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80
TILE_W = 19
TEXT_X, TEXT_Y = 20, 4
TEXT_W = FRONT_W - TEXT_X
SKY_FRAMES = 8
GAP = "     "
MAX_CHARS = 140         # longest message shown on the strip

# App colors for the name on the strip and the bar's notification light.
APP_COLORS = {
    "discord": (88, 101, 242), "vesktop": (88, 101, 242), "webcord": (88, 101, 242),
    "firefox": (255, 113, 57), "chromium": (66, 133, 244), "chrome": (66, 133, 244),
    "google chrome": (66, 133, 244), "brave": (251, 84, 43),
    "thunderbird": (10, 132, 255), "evolution": (10, 132, 255),
    "telegram": (38, 165, 228), "telegramdesktop": (38, 165, 228),
    "signal": (58, 118, 240), "slack": (224, 30, 90), "element": (13, 189, 139),
    "steam": (102, 192, 244), "spotify": (30, 215, 96),
}
DEFAULT_COLOR = (80, 240, 190)


def app_color(app: str) -> tuple[int, int, int]:
    return APP_COLORS.get(app.strip().lower(), DEFAULT_COLOR)


def hex_color(rgb: tuple[int, int, int]) -> str:
    return "#%02X%02X%02XFF" % rgb


# --------------------------------------------------------------------------
# Luca
# --------------------------------------------------------------------------
PALETTE = {
    "K": (28, 30, 44), "W": (255, 255, 255), "S": (190, 205, 230),
    "G": (150, 150, 158), "T": (40, 235, 175), "M": (8, 8, 12),
    "O": (245, 160, 80), "N": (225, 140, 115), "P": (255, 150, 160),
    "Y": (255, 220, 60), "R": (255, 70, 80),
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
TILE_POSES = {"alert": 2, "urgent": 2, "reading": 2}


def luca(pose: str) -> list[str]:
    rows = [list(r) for r in LUCA]
    if pose in ("alert", "urgent"):  # wide eyes: big amber, no pupils
        rows[6][3:5], rows[7][3:5] = "OO", "OO"
        rows[6][10:12], rows[7][10:12] = "OO", "OO"
        rows[12][6:9] = "KKK"  # a little surprised "o" mouth
    else:  # reading: eyes glance right toward the message
        rows[6][3:5], rows[7][3:5] = "OK", "OK"
        rows[6][10:12], rows[7][10:12] = "OK", "OK"
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


def tile(pose: str, frame: int) -> Image.Image:
    img = glass_tile()
    hop = -1 if pose in ("alert", "urgent") and frame % 2 else 0
    for y, row in enumerate(luca(pose)):
        for x, ch in enumerate(row):
            if ch != "." and 0 <= y + hop < FRONT_H:
                img.putpixel((x + 1, y + hop), PALETTE[ch] + (255,))
    if pose in ("alert", "urgent"):  # a "!" beside his ear
        mark = PALETTE["R" if pose == "urgent" else "Y"] + (255,)
        if pose == "alert" or frame % 2 == 0:  # urgent blinks
            for y in (1, 2, 3, 4, 6):
                img.putpixel((17, y), mark)
    return img


def sky(frame: int) -> Image.Image:
    img = aero_sky(FRONT_W, FRONT_H)
    for bx, phase in ((28, 0), (44, 7), (58, 3), (68, 12)):
        p = (phase + frame * 22 / SKY_FRAMES) % 22
        x, y = bx + round(math.sin(p / 3)), round(FRONT_H + 2 - p)
        for X, Y in [(x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1)]:
            if 0 <= X < FRONT_W and 0 <= Y < FRONT_H:
                img.putpixel((X, Y), lerp(img.getpixel((X, Y)), (230, 250, 255), 0.4))
    return img


# --------------------------------------------------------------------------
# The message strip
# --------------------------------------------------------------------------
def message_text(note, private: bool) -> tuple[str, str]:
    """(app part, message part) as the strip shows them."""
    app = to_font_text(note.app)
    if private:
        return app, "NEW NOTIFICATION"
    msg = to_font_text(note.summary + (f" - {note.body}" if note.body else ""))
    if len(msg) > MAX_CHARS:  # a long email body: the start is enough for the bar
        msg = msg[:MAX_CHARS].rstrip() + "..."
    return app, msg


def strip(note, private: bool = False) -> tuple[Image.Image, int]:
    """
    The notification as a transparent strip: the app name in its own color,
    then the message in white. Long ones repeat after a gap so they scroll
    seamlessly; the second value is the loop length (0 means it fits).
    """
    app, msg = message_text(note, private)
    color = lerp(app_color(note.app), (255, 255, 255), 0.35) + (255,)  # brighter on the sky
    full = f"{app}  {msg}"
    w = text_width(full)

    def paint(img, x):
        draw_text(img, app, x, 0, color=color)
        draw_text(img, msg, x + text_width(app + "  ") + 1, 0)

    if w <= TEXT_W:
        img = Image.new("RGBA", (TEXT_W, 9), (0, 0, 0, 0))
        paint(img, 0)
        return img, 0
    loop = text_width(full + GAP) + 1
    img = Image.new("RGBA", (loop + w + 2, 9), (0, 0, 0, 0))
    paint(img, 0)
    paint(img, loop)
    return img, loop


# --------------------------------------------------------------------------
# Back screen: "Luca Inbox"
# --------------------------------------------------------------------------
def plain(text: str) -> str:
    """Drop emoji and symbols the back screen's font can't draw."""
    import unicodedata
    kept = "".join(c for c in text if ord(c) <= 0xFFFF and unicodedata.category(c) not in ("So", "Cs"))
    return " ".join(kept.split())


def fit(d: ImageDraw.ImageDraw, text: str, f, width: int) -> str:
    text = plain(text)
    if d.textlength(text, font=f) <= width:
        return text
    while text and d.textlength(text + "…", font=f) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def back_screen(notes: list, current=None, private: bool = False, held: int = 0) -> Image.Image:
    """`notes` newest first; `current` is highlighted; `held` counts notifications
    waiting while the bar is on do-not-disturb."""
    img = Image.new("L", (BACK_W, BACK_H), 0)
    d = ImageDraw.Draw(img)
    for y in range(BACK_H):
        for x in range(BACK_W):
            img.putpixel((x, y), int(60 * max(0, 1 - math.hypot(x - 20, y - 70) / 150)))

    wx0, wy0, wx1, wy1 = 2, 1, 157, 78
    d.rounded_rectangle([wx0, wy0, wx1, wy1], radius=5, fill=120, outline=230)
    for y in range(wy0 + 1, wy0 + 13):
        d.line([(wx0 + 2, y), (wx1 - 2, y)], fill=int(205 - (y - wy0) * 6))
    for sx in (62, 70, 122):
        d.line([(sx, wy0 + 1), (sx + 10, wy0 + 12)], fill=235)
    # a little envelope icon
    d.rectangle([wx0 + 4, wy0 + 3, wx0 + 11, wy0 + 8], outline=20)
    d.line([(wx0 + 4, wy0 + 3), (wx0 + 7, wy0 + 6), (wx0 + 11, wy0 + 3)], fill=20)
    title = "Luca Inbox" + (f"  ({held} waiting)" if held else "")
    d.text((wx0 + 15, wy0), title, font=font(10), fill=20)
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
    if not notes:
        d.text((cx0 + 6, cy0 + 22), "No notifications yet", font=font(10), fill=90)
        return img.point(lambda v: (v // 17) * 17)

    row_h = 19
    for i, note in enumerate(notes[:3]):
        y = cy0 + 1 + i * row_h
        if note is current:  # the one on the front strip: a glassy highlight
            d.rectangle([cx0 + 1, y, cx1 - 1, y + row_h - 1], fill=190)
            d.line([(cx0 + 1, y), (cx1 - 1, y)], fill=225)
        stamp = time.strftime("%H:%M", time.localtime(note.at))
        tw = d.textlength(stamp, font=font(8))
        d.text((cx0 + 4, y + 1), fit(d, note.app, font(9), cx1 - cx0 - tw - 14), font=font(9), fill=0)
        d.text((cx1 - 4 - tw, y + 2), stamp, font=font(8), fill=70)
        line = "New notification" if private else (note.summary + (f" - {note.body}" if note.body else ""))
        d.text((cx0 + 4, y + 10), fit(d, line, font(8), cx1 - cx0 - 8), font=font(8), fill=60)
        if note.urgency >= 2:
            d.rectangle([cx0 + 1, y + 1, cx0 + 2, y + row_h - 2], fill=0)  # urgent marker
    return img.point(lambda v: (v // 17) * 17)


# --------------------------------------------------------------------------
# Previews
# --------------------------------------------------------------------------
def main() -> None:
    from watcher import DEMO, Notification

    preview = HERE / "preview"
    preview.mkdir(exist_ok=True)
    now = time.time()
    notes = [Notification(a, s, b, 2 if i == 3 else 1, now - i * 260)
             for i, (a, s, b) in enumerate(DEMO[:5])]
    note = notes[0]
    st, loop = strip(note)
    frames = []
    for i in range(0, 15 + loop + 10, 3):
        out = sky(i // 2).convert("RGBA")
        off = max(0, min(i - 15, loop))
        out.alpha_composite(st.crop((off, 0, off + TEXT_W, 9)), (TEXT_X, TEXT_Y))
        pose = "alert" if i < 16 else "reading"
        out.alpha_composite(tile(pose, i // 3), (0, 0))
        frames.append(led_preview(out.convert("RGB")))
    frames[0].save(preview / "front.gif", save_all=True, append_images=frames[1:],
                   duration=160, loop=0, optimize=True)
    back_screen(notes, current=note).resize((BACK_W * 4, BACK_H * 4), Image.NEAREST) \
        .save(preview / "back.png")
    poses = Image.new("RGB", (3 * (TILE_W * 8 + 10), FRONT_H * 8), (40, 40, 40))
    for k, pose in enumerate(TILE_POSES):
        poses.paste(led_preview(tile(pose, 0).convert("RGB"), 8), (k * (TILE_W * 8 + 10), 0))
    poses.save(preview / "poses.png")
    print(f"Wrote previews to {preview}")


if __name__ == "__main__":
    main()
