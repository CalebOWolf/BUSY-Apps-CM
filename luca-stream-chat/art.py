"""
Artwork for Luca Stream Chat, drawn with Pillow.

Uploaded once:
  panel_<kind>_N.png  72x16 glossy panels: Twitch purple and YouTube red for
                      chat, and a sparkling gold one for alerts (subs, raids…)
  tile_<pose>_N.png   19x16 glass tile with streamer Luca in his headset:
                      reading chat, or hopping for joy at an alert
Per chat item:
  a text strip        "NAME  message" with the name in the chatter's color,
                      or "NEW SUB! NAME 7 MONTHS…" for alerts; long ones scroll
  the back screen     "Luca Chat", a Windows 7-style chat log

    python art.py      # writes previews into preview/
"""

from __future__ import annotations

import math
import random
import sys
import time as _time
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
TEXT_Y = 4
PANEL_FRAMES = 8
POSES = {"read": 2, "hop": 2}
LED_ALERT = "#FFD23CFF"

PANELS = {"twitch": ((175, 120, 255), (70, 20, 160)),
          "youtube": ((255, 110, 110), (150, 10, 20)),
          "alert": ((255, 225, 110), (200, 110, 0))}
HEADLINES = {"sub": "NEW SUB!", "resub": "RESUB!", "gift": "GIFT SUBS!", "raid": "RAID!",
             "bits": "CHEER!", "superchat": "SUPER CHAT!", "member": "NEW MEMBER!", "first": "FIRST CHAT!"}
ROLE_COLORS = {"owner": (255, 215, 90), "mod": (120, 200, 255), "member": (120, 255, 170)}
SHADOW = (30, 10, 50, 255)
GOLD = (255, 240, 150, 255)
MINT = (120, 255, 200, 255)


def panel(kind: str, frame: int) -> Image.Image:
    top, bottom = PANELS[kind]
    pulse = 0.5 + 0.5 * math.sin(frame / PANEL_FRAMES * 2 * math.pi)
    img = Image.new("RGB", (FRONT_W, FRONT_H))
    d = ImageDraw.Draw(img)
    for y in range(FRONT_H):
        c = lerp(top, bottom, y / (FRONT_H - 1))
        c = lerp(c, (255, 255, 255), (0.45 if y < 7 else 0.0) * (1 - y / 7))
        c = lerp(c, top, 0.2 * pulse)
        d.line([(0, y), (FRONT_W - 1, y)], fill=c)
    d.rectangle([AREA_X - 1, 0, FRONT_W - 1, FRONT_H - 1], outline=lerp(top, (255, 255, 255), 0.5))
    if kind == "alert":  # confetti sparkles that twinkle
        rnd = random.Random(frame)
        for _ in range(7):
            x, y = rnd.randrange(AREA_X + 1, FRONT_W - 1), rnd.randrange(1, FRONT_H - 1)
            c = rnd.choice([(255, 255, 255), (255, 120, 200), (120, 255, 200), (150, 180, 255)])
            d.point((x, y), fill=c)
            if rnd.random() < 0.4:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    d.point((x + dx, y + dy), fill=lerp(c, top, 0.5))
    return img


PALETTE = {"K": (28, 30, 44), "W": (255, 255, 255), "S": (190, 205, 230), "G": (150, 150, 158),
           "T": (40, 235, 175), "M": (8, 8, 12), "O": (245, 160, 80), "N": (225, 140, 115),
           "P": (255, 150, 160), "H": (45, 45, 70), "h": (170, 110, 255), "m": (90, 95, 115),
           "R": (255, 60, 80)}
LUCA = [
    "KK...........KK.",
    "KGKHHHHHHHHHKTK.",
    "KGHKKKKKKKKKHTK.",
    "KGWWWWWWWWWWWTK.",
    "HWWWWWWWWWWWWWH.",
    "HWWWWWWWWMMMMWh.",
    "hWWOKWWWMMOKMWH.",
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


def tile(pose: str, frame: int) -> Image.Image:
    img = Image.new("RGBA", (TILE_W, FRONT_H))
    d = ImageDraw.Draw(img)
    for y in range(FRONT_H):
        c = lerp((150, 120, 255), (40, 20, 130), y / (FRONT_H - 1))
        if y < FRONT_H // 2:
            c = lerp(c, (255, 255, 255), 0.45 * (1 - y / (FRONT_H / 2)))
        d.line([(0, y), (TILE_W - 1, y)], fill=c + (255,))
    d.line([(TILE_W - 1, 0), (TILE_W - 1, FRONT_H - 1)], fill=(225, 210, 255, 255))
    rows = [list(r) for r in LUCA]
    hop = 0
    if pose == "hop":  # ^^ eyes, open mouth, hopping
        rows[6][3:5], rows[7][3:5] = "KK", "WW"
        rows[6][10:12], rows[7][10:12] = "SS", "MM"
        rows[11][6:9] = "KKK"
        rows[12][6:9] = "PKP"
        hop = -1 if frame % 2 else 0
    elif frame % 2:  # reading chat: eyes flick along the line
        rows[6][3:5], rows[7][3:5] = "KO", "KO"
        rows[6][10:12], rows[7][10:12] = "KO", "KO"
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != "." and 0 <= y + hop < FRONT_H:
                img.putpixel((x + 1, y + hop), PALETTE[ch] + (255,))
    return img


def name_color(item) -> tuple:
    if item.role in ROLE_COLORS and (item.platform == "youtube" or not item.color):
        c = ROLE_COLORS[item.role]
    else:
        c = item.color or (230, 220, 255)
    return lerp(c, (255, 255, 255), 0.35) + (255,)  # brightened so it reads on the glossy panel


MAX_CHARS = 120
GAP = "     "


def strip(item) -> tuple[Image.Image, int]:
    pieces = []
    if item.alert:
        pieces.append((HEADLINES.get(item.alert, "ALERT!"), GOLD))
    pieces.append((to_font_text(item.name), name_color(item) if not item.alert else (255, 255, 255, 255)))
    if item.detail:
        pieces.append((to_font_text(item.detail), MINT))
    text = to_font_text(item.text or "")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rstrip() + "..."
    if text:
        pieces.append((text, (255, 255, 255, 255)))
    pieces = [(t, c) for t, c in pieces if t]
    full = "  ".join(t for t, _ in pieces)
    w = text_width(full)

    def paint(img, x):
        for t, c in pieces:
            draw_text(img, t, x, 0, color=c, shadow=SHADOW)
            x += text_width(t + "  ") + 1

    if w <= AREA_W:
        img = Image.new("RGBA", (AREA_W, 9), (0, 0, 0, 0))
        paint(img, (AREA_W - w) // 2)
        return img, 0
    loop = text_width(full + GAP) + 1
    img = Image.new("RGBA", (loop + w + 2, 9), (0, 0, 0, 0))
    paint(img, 0)
    paint(img, loop)
    return img, loop


def fit(d, text, f, width):
    import unicodedata
    text = "".join(c for c in text if ord(c) <= 0xFFFF and unicodedata.category(c) not in ("So", "Cs"))
    if d.textlength(text, font=f) <= width:
        return text
    while text and d.textlength(text + "…", font=f) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def back_screen(history: list, platform_names: str) -> Image.Image:
    img = Image.new("L", (BACK_W, BACK_H), 0)
    d = ImageDraw.Draw(img)
    for y in range(BACK_H):
        for x in range(BACK_W):
            img.putpixel((x, y), int(55 * max(0, 1 - math.hypot(x - 140, y - 10) / 150)))
    wx0, wy0, wx1, wy1 = 2, 1, 157, 78
    d.rounded_rectangle([wx0, wy0, wx1, wy1], radius=5, fill=120, outline=230)
    for y in range(wy0 + 1, wy0 + 13):
        d.line([(wx0 + 2, y), (wx1 - 2, y)], fill=int(205 - (y - wy0) * 6))
    d.rounded_rectangle([wx0 + 4, wy0 + 2, wx0 + 11, wy0 + 7], radius=1, fill=20)
    d.text((wx0 + 15, wy0), f"Luca Chat  ·  {platform_names}", font=font(10), fill=20)
    cx0, cy0, cx1, cy1 = wx0 + 3, wy0 + 14, wx1 - 3, wy1 - 3
    d.rectangle([cx0, cy0, cx1, cy1], fill=235, outline=60)
    if not history:
        d.text((cx0 + 6, cy0 + 22), "Waiting for chat…", font=font(10), fill=90)
        return img.point(lambda v: (v // 17) * 17)
    for i, item in enumerate(history[:5]):  # newest at the bottom, like a chat window
        y = cy1 - 11 - i * 11
        f = font(8)
        if item.alert:
            d.rectangle([cx0 + 1, y - 1, cx1 - 1, y + 9], fill=200)
            label = HEADLINES.get(item.alert, "").title().rstrip("!") + (f" {item.detail}" if item.detail else "")
            line = f"{item.name}: {label}" + (f" - {item.text}" if item.text else "")
        else:
            line = None
        nx = cx0 + 4
        name = fit(d, item.name, font(8), 50) + ":"
        if line:
            d.text((nx, y), fit(d, line, f, cx1 - nx - 4), font=f, fill=0)
        else:
            d.text((nx, y), name, font=f, fill=0)
            tx = nx + d.textlength(name, font=f) + 3
            d.text((tx, y), fit(d, item.text, f, cx1 - tx - 4), font=f, fill=60)
    return img.point(lambda v: (v // 17) * 17)


def main() -> None:
    from chat_sources import Chat
    preview = HERE / "preview"
    preview.mkdir(exist_ok=True)
    items = [Chat("twitch", "Kiro", "LUCA LOOKS SO GOOD ON THE BAR", (255, 105, 180)),
             Chat("twitch", "AeroFox", "awoo", (30, 144, 255), "bits", "500 bits"),
             Chat("twitch", "Bubbles", "7 months of howls!", None, "resub", "7 months"),
             Chat("twitch", "WolfPack", "", None, "raid", "42 viewers"),
             Chat("youtube", "Mod Max", "welcome everyone :)", role="mod")]
    frames = []
    for k, item in enumerate(items):
        st, loop = strip(item)
        kind = "alert" if item.alert else item.platform
        steps = list(range(0, 10 + loop, 4)) or [0]
        for i, s in enumerate(steps[:22] if loop else range(9)):
            off = max(0, (s if loop else 0) - 10) % (loop or 1)
            out = panel(kind, i).convert("RGBA")
            out.alpha_composite(st.crop((off, 0, off + AREA_W, 9)), (AREA_X, TEXT_Y))
            out.alpha_composite(tile("hop" if item.alert else "read", i), (0, 0))
            frames.append(led_preview(out.convert("RGB"), 6))
    frames[0].save(preview / "front.gif", save_all=True, append_images=frames[1:],
                   duration=160, loop=0, optimize=True)
    now = _time.time()
    hist = [Chat("twitch", "Mod Max", "welcome everyone :)", at=now),
            Chat("twitch", "WolfPack", "", alert="raid", detail="42 viewers", at=now - 20),
            Chat("twitch", "Bubbles", "7 months of howls!", alert="resub", detail="7 months", at=now - 40),
            Chat("twitch", "AeroFox", "awoo", alert="bits", detail="500 bits", at=now - 60),
            Chat("twitch", "Kiro", "luca looks so good on the bar", at=now - 80)]
    back_screen(hist, "Twitch").resize((BACK_W * 4, BACK_H * 4), Image.NEAREST).save(preview / "back.png")
    print(f"Wrote previews to {preview}")


if __name__ == "__main__":
    main()
