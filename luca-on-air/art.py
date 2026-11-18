"""
Artwork for Luca On Air, drawn with Pillow.

Uploaded once:
  sign_<mode>_N.png   72x16 glossy Aero signs that softly pulse: red for LIVE,
                      dark with a blinking red dot for REC, green for a call,
                      violet for the camera
  tile_<pose>_N.png   19x16 glass tile with Luca in a gaming headset
  word_<name>.png     ON AIR, LIVE, REC, PAUSED, IN CALL, CAM ON
  char_<c>.png        digits and ":" for the time on air
When it changes:
  app_<slot>.png      the app's name (DISCORD, ZOOM…)
  the back screen     "Luca On Air", a Windows 7-style status window

    python art.py      # writes previews into preview/
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from pixelart import GLYPHS, draw_text, led_preview, lerp, text_width, to_font_text  # noqa: E402
from pixelart import ui_font as font  # noqa: E402

HERE = Path(__file__).parent
FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80
TILE_W = 19
AREA_X, AREA_W = 20, 52
TEXT_Y = 4
SIGN_FRAMES = 8
MODES = ["live", "rec", "call", "cam"]
POSES = {"talk": 2, "live": 2, "smile": 2}
WORDS = {"onair": "ON AIR", "live": "LIVE", "rec": "REC", "paused": "PAUSED",
         "call": "IN CALL", "cam": "CAM ON"}
LED = {"live": "#FF2030FF", "rec": "#FF2030FF", "call": "#30E080FF", "cam": "#B060FFFF"}

WHITE = (255, 255, 255, 255)


# --------------------------------------------------------------------------
# Signs
# --------------------------------------------------------------------------
SIGN_COLORS = {
    "live": ((255, 90, 90), (150, 0, 20)),     # a glowing red ON AIR sign
    "rec": ((60, 60, 75), (15, 15, 25)),        # dark, with a red recording dot
    "call": ((90, 230, 150), (0, 110, 70)),     # friendly green
    "cam": ((190, 130, 255), (80, 20, 150)),    # violet
}


def sign(mode: str, frame: int) -> Image.Image:
    top, bottom = SIGN_COLORS[mode]
    pulse = 0.5 + 0.5 * math.sin(frame / SIGN_FRAMES * 2 * math.pi)
    img = Image.new("RGB", (FRONT_W, FRONT_H))
    d = ImageDraw.Draw(img)
    for y in range(FRONT_H):
        c = lerp(top, bottom, y / (FRONT_H - 1))
        c = lerp(c, (255, 255, 255), (0.45 if y < 7 else 0.0) * (1 - y / 7))  # glossy top
        if mode in ("live", "call", "cam"):
            c = lerp(c, top, 0.25 * pulse)  # a gentle glow, breathing
        d.line([(0, y), (FRONT_W - 1, y)], fill=c)
    # a bright rim, like a lit sign
    rim = lerp(top, (255, 255, 255), 0.5 + 0.3 * pulse)
    d.rectangle([AREA_X - 1, 0, FRONT_W - 1, FRONT_H - 1], outline=rim)
    if mode == "rec" and frame % 4 < 2:  # the blinking red dot
        d.ellipse([AREA_X + 2, 5, AREA_X + 7, 10], fill=(255, 40, 50))
        d.point((AREA_X + 3, 6), fill=(255, 170, 170))
    return img


# --------------------------------------------------------------------------
# Luca in a headset
# --------------------------------------------------------------------------
PALETTE = {
    "K": (28, 30, 44), "W": (255, 255, 255), "S": (190, 205, 230),
    "G": (150, 150, 158), "T": (40, 235, 175), "M": (8, 8, 12),
    "O": (245, 160, 80), "N": (225, 140, 115), "P": (255, 150, 160),
    "H": (45, 50, 70),       # headset band and cups
    "h": (255, 60, 80),      # glowing red accents on the cups
    "m": (90, 95, 115),      # mic boom
    "R": (255, 70, 80),      # the mic's red light
}
LUCA = [
    "KK...........KK.",
    "KGKHHHHHHHHHKTK.",
    "KGHKKKKKKKKKHTK.",
    "KGWWWWWWWWWWWTK.",
    "HWWWWWWWWWWWWWH.",
    "HWWWWWWWWMMMMWh.",
    "hWWOOWWWMMOOMWH.",
    "HWWOKWWWMMOKMWm.",
    "KWWWWWWWWMMMWWKm",
    ".KWWWWNNNWWWWK.m",
    ".KWWTWNNNWTWWKm.",
    "..KWWWWKWWWWKm..",
    "..KWWKPPPKWWR...",
    "...KWWKKKWWK....",
    "....KWWWWWWK....",
    ".....KKKKKK.....",
]


def luca(pose: str, frame: int) -> list[str]:
    rows = [list(r) for r in LUCA]
    if pose == "talk" and frame % 2:  # mouth moving as he talks
        rows[11][6:9] = "KKK"
        rows[12][6:9] = "PKP"
    elif pose == "live":  # bright, excited eyes
        rows[6][3:5], rows[7][3:5] = "OO", "OO"
        rows[6][10:12], rows[7][10:12] = "OO", "OO"
        if frame % 2:
            rows[12][12] = "h"  # the mic light flickers
    elif pose == "smile":  # ^^
        rows[6][3:5], rows[7][3:5] = "KK", "WW"
        rows[6][10:12], rows[7][10:12] = "SS", "MM"
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
    for y, row in enumerate(luca(pose, frame)):
        for x, ch in enumerate(row):
            if ch != ".":
                img.putpixel((x + 1, y), PALETTE[ch] + (255,))
    return img


# --------------------------------------------------------------------------
# Words, names and time
# --------------------------------------------------------------------------
def text_image(text: str, color=WHITE) -> Image.Image:
    text = to_font_text(text)
    while text and text_width(text) > AREA_W - 2:
        text = text[:-1]
    img = Image.new("RGBA", (max(1, text_width(text)) + 2, 9), (0, 0, 0, 0))
    draw_text(img, text, 0, 0, color=color, shadow=(40, 0, 10, 255))
    return img


def word(name: str) -> Image.Image:
    return text_image(WORDS[name])


CLOCK_CHARS = "0123456789:"


def char(ch: str) -> Image.Image:
    img = Image.new("RGBA", (len(GLYPHS[ch][0]) + 1, 8), (0, 0, 0, 0))
    draw_text(img, ch, 0, 0, shadow=(40, 0, 10, 255))
    return img


def char_name(ch: str) -> str:
    return "colon" if ch == ":" else ch


def char_width(ch: str) -> int:
    return len(GLYPHS[ch][0]) + 1


def word_width(name: str) -> int:
    return text_width(to_font_text(WORDS[name]))


def live_pieces(seconds: float) -> list:
    """"LIVE 12:34", or just the time once it no longer fits beside the word."""
    t = uptime(seconds)
    if word_width("live") + 4 + sum(char_width(c) for c in t) <= AREA_W - 2:
        return [("word", "live"), ("time", t)]
    return [("time", t)]


def display_name(app: str) -> str:
    return app.upper() if len(app) <= 3 else app.title()


def uptime(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


# --------------------------------------------------------------------------
# Back screen: "Luca On Air"
# --------------------------------------------------------------------------
TITLES = {"live": "LIVE", "rec": "Recording", "call": "In a call", "cam": "Camera on"}


def back_screen(status, now: float) -> Image.Image:
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
    d.ellipse([wx0 + 4, wy0 + 2, wx0 + 10, wy0 + 8], fill=20)  # a little "record" dot
    d.text((wx0 + 15, wy0), "Luca On Air", font=font(10), fill=20)
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

    mode = status.mode
    # a big status badge on the left
    bx0, by0, bx1, by1 = cx0 + 4, cy0 + 4, cx0 + 64, cy0 + 26
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=5, fill=40 if mode else 190, outline=0)
    d.line([(bx0 + 4, by0 + 2), (bx1 - 4, by0 + 2)], fill=110 if mode else 230)
    title = TITLES.get(mode, "Off air")
    d.text(((bx0 + bx1) // 2, (by0 + by1) // 2), title, font=font(11 if mode != "live" else 13),
           fill=255 if mode else 60, anchor="mm")
    since = status.stream_since if mode == "live" else status.record_since if mode == "rec" else None
    if since:
        d.text(((bx0 + bx1) // 2, by1 + 8), uptime(now - since), font=font(12), fill=0, anchor="ma")
    elif mode == "call" and status.call_app:
        d.text(((bx0 + bx1) // 2, by1 + 9), display_name(status.call_app), font=font(10), fill=0, anchor="ma")

    # what each source says
    tx, ty = cx0 + 72, cy0 + 4
    obs = ("not running" if not status.obs_connected else
           "streaming" if status.streaming else
           "recording (paused)" if status.recording_paused else
           "recording" if status.recording else "ready")
    rows = [("OBS", obs),
            ("Mic", ", ".join(display_name(a) for a in status.mic_apps) or "not in use"),
            ("Camera", ", ".join(display_name(a) for a in status.cam_apps) or "off")]
    for i, (name, value) in enumerate(rows):
        y = ty + i * 18
        d.text((tx, y), name, font=font(9), fill=60)
        d.text((tx, y + 8), fit(d, value, font(9), cx1 - tx - 3), font=font(9), fill=0)
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
def compose(mode: str, page: int, frame: int, seconds: float = 0, app: str = "") -> Image.Image:
    out = sign(mode, frame).convert("RGBA")
    pieces: list = []
    if mode == "live":
        pieces = [("word", "onair")] if page == 0 else live_pieces(seconds)
    elif mode == "rec":
        pieces = [("time", uptime(seconds))]  # the red dot says "recording"
    elif mode == "call":
        pieces = [("word", "call")] if page == 0 else [("text", app)]
    else:
        pieces = [("word", "cam")] if page == 0 else [("text", app)]
    imgs = []
    for kind, val in pieces:
        if kind == "word":
            imgs.append(word(val))
        elif kind == "text":
            imgs.append(text_image(val))
        else:
            for ch in val:
                imgs.append(char(ch))
    gap = 4 if len(pieces) > 1 else 0
    total = sum(i.width - 1 for i in imgs) + gap - (1 if imgs else 0)
    x = AREA_X + (AREA_W - total) // 2 + (4 if mode == "rec" else 0)
    for k, im in enumerate(imgs):
        out.alpha_composite(im, (x, TEXT_Y))
        x += im.width - 1
        if k == 0 and gap:
            x += gap
    pose = {"live": "live", "call": "talk"}.get(mode, "smile")
    out.alpha_composite(tile(pose, frame // 2), (0, 0))
    return out.convert("RGB")


def main() -> None:
    import time as _t
    from sources import Status

    preview = HERE / "preview"
    preview.mkdir(exist_ok=True)
    frames = []
    for i in range(16):
        frames.append(led_preview(compose("live", i // 8, i, 3723 + i // 2), 8))
    for i in range(10):
        frames.append(led_preview(compose("rec", 0, i, 754 + i // 2), 8))
    for i in range(12):
        frames.append(led_preview(compose("call", i // 6, i, app="Discord"), 8))
    frames[0].save(preview / "front.gif", save_all=True, append_images=frames[1:],
                   duration=220, loop=0, optimize=True)
    now = _t.time()
    s = Status(streaming=True, stream_since=now - 3723, obs_connected=True,
               mic_apps=["discord"], call_app="discord", cam_apps=["obs"])
    back_screen(s, now).resize((BACK_W * 4, BACK_H * 4), Image.NEAREST).save(preview / "back.png")
    sheet = Image.new("RGB", (3 * (TILE_W * 8 + 8), FRONT_H * 8), (40, 40, 40))
    for k, p in enumerate(POSES):
        sheet.paste(led_preview(tile(p, 1).convert("RGB"), 8), (k * (TILE_W * 8 + 8), 0))
    sheet.save(preview / "poses.png")
    print(f"Wrote previews to {preview}")


if __name__ == "__main__":
    main()
