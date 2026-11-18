"""
Artwork for Luca Discord, drawn with Pillow: glossy blurple Frutiger Aero.

Uploaded once:
  sign_<kind>_N.png   72x16 glossy panels that gently glow: blurple for voice,
                      a brighter one for new messages
  tile_<pose>_N.png   19x16 glass tile with Luca in a headset: listening,
                      talking (his mouth moves when you talk), muted, deafened,
                      and ears-up for a new message
  icon_<name>.png     a red crossed-out mic (muted) or headset (deafened),
                      and green sound waves for whoever's talking
  word_<name>.png     IN VOICE, MUTED, DEAFENED
  char_<c>.png        digits and ":" for the time in the call
When they change:
  name images         the channel, server and people's names
  message strips      the new message, scrolling
  the back screen     "Luca Discord", a Windows 7-style window

    python art.py      # writes previews into preview/
"""

from __future__ import annotations

import math
import sys
import time as _time
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
ICON_X = 64                 # where the muted/deafened icon sits
SIGN_FRAMES = 8
POSES = {"listen": 2, "talk": 2, "muted": 1, "deaf": 1, "alert": 2}
WORDS = {"voice": "IN VOICE", "muted": "MUTED", "deaf": "DEAFENED"}
BLURPLE = (88, 101, 242)
LED_VOICE = "#5865F2FF"
LED_MESSAGE = "#8C96FFFF"
SHADOW = (15, 18, 70, 255)
WHITE = (255, 255, 255, 255)
SOFT = (210, 215, 255, 255)   # author names and channel names


# --------------------------------------------------------------------------
# Panels
# --------------------------------------------------------------------------
def sign(kind: str, frame: int) -> Image.Image:
    top, bottom = ((150, 160, 255), (40, 45, 165)) if kind == "voice" else ((175, 185, 255), (70, 80, 210))
    pulse = 0.5 + 0.5 * math.sin(frame / SIGN_FRAMES * 2 * math.pi)
    img = Image.new("RGB", (FRONT_W, FRONT_H))
    d = ImageDraw.Draw(img)
    for y in range(FRONT_H):
        c = lerp(top, bottom, y / (FRONT_H - 1))
        c = lerp(c, (255, 255, 255), (0.45 if y < 7 else 0.0) * (1 - y / 7))  # glossy top
        c = lerp(c, top, 0.2 * pulse)
        d.line([(0, y), (FRONT_W - 1, y)], fill=c)
    d.rectangle([AREA_X - 1, 0, FRONT_W - 1, FRONT_H - 1], outline=lerp(top, (255, 255, 255), 0.4 + 0.3 * pulse))
    if kind == "message":  # a tiny speech bubble in the corner
        d.rounded_rectangle([FRONT_W - 8, 1, FRONT_W - 3, 5], radius=1, fill=(255, 255, 255))
        d.point((FRONT_W - 7, 6), fill=(255, 255, 255))
    return img


# --------------------------------------------------------------------------
# Luca in a headset
# --------------------------------------------------------------------------
PALETTE = {
    "K": (28, 30, 44), "W": (255, 255, 255), "S": (190, 205, 230),
    "G": (150, 150, 158), "T": (40, 235, 175), "M": (8, 8, 12),
    "O": (245, 160, 80), "N": (225, 140, 115), "P": (255, 150, 160),
    "H": (40, 44, 70),          # headset
    "h": BLURPLE,               # blurple glow on the cups
    "m": (90, 95, 120),         # mic boom
    "g": (60, 230, 120),        # mic light: green when it's live…
    "r": (255, 60, 70),         # …red when you're muted
    "Y": (255, 220, 60),        # "!" for a new message
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
    "..KWWKPPPKWWg...",
    "...KWWKKKWWK....",
    "....KWWWWWWK....",
    ".....KKKKKK.....",
]


def luca(pose: str, frame: int) -> list[str]:
    rows = [list(r) for r in LUCA]
    if pose == "talk" and frame % 2:
        rows[11][6:9] = "KKK"
        rows[12][6:9] = "PKP"
    elif pose == "muted":
        rows[12][12] = "r"
        rows[12][6:9] = "KKK"   # mouth closed
    elif pose == "deaf":
        rows[12][12] = "r"
        rows[6][3:5], rows[7][3:5] = "WW", "KK"   # eyes shut, can't hear a thing
        rows[6][10:12], rows[7][10:12] = "MM", "SS"
    elif pose == "alert":
        rows[6][3:5], rows[7][3:5] = "OO", "OO"
        rows[6][10:12], rows[7][10:12] = "OO", "OO"
    return ["".join(r) for r in rows]


def glass_tile() -> Image.Image:
    img = Image.new("RGBA", (TILE_W, FRONT_H))
    d = ImageDraw.Draw(img)
    for y in range(FRONT_H):
        c = lerp((130, 140, 255), (30, 35, 140), y / (FRONT_H - 1))
        if y < FRONT_H // 2:
            c = lerp(c, (255, 255, 255), 0.45 * (1 - y / (FRONT_H / 2)))
        d.line([(0, y), (TILE_W - 1, y)], fill=c + (255,))
    d.line([(TILE_W - 1, 0), (TILE_W - 1, FRONT_H - 1)], fill=(210, 215, 255, 255))
    return img


def tile(pose: str, frame: int) -> Image.Image:
    img = glass_tile()
    hop = -1 if pose == "alert" and frame % 2 else 0
    for y, row in enumerate(luca(pose, frame)):
        for x, ch in enumerate(row):
            if ch != "." and 0 <= y + hop < FRONT_H:
                img.putpixel((x + 1, y + hop), PALETTE[ch] + (255,))
    if pose == "alert":
        for y in (1, 2, 3, 4, 6):
            img.putpixel((17, y), PALETTE["Y"] + (255,))
    return img


# --------------------------------------------------------------------------
# Icons
# --------------------------------------------------------------------------
MIC = ["..XXX..", "..XXX..", "..XXX..", ".XXXXX.", "...X...", "..XXX..", "......."]
HEADSET = [".XXXXX.", "X.....X", "X.....X", "XX...XX", "XX...XX", ".......", "......."]


def crossed(shape: list[str]) -> Image.Image:
    img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    for pass_, color in ((0, SHADOW), (1, WHITE)):  # a navy shadow, then the white icon
        for y, row in enumerate(shape):
            for x, ch in enumerate(row):
                if ch == "X":
                    X, Y = (x + 1, y + 1) if pass_ == 0 else (x, y)
                    if X < 8 and Y < 8:
                        img.putpixel((X, Y), color)
    for k in range(7):  # the red slash
        img.putpixel((k, 6 - k), (255, 60, 70, 255))
        if k < 6:
            img.putpixel((k + 1, 6 - k), (255, 60, 70, 255))
    return img


def waves(frame: int) -> Image.Image:
    """Green sound waves beside whoever's talking."""
    img = Image.new("RGBA", (6, 9), (0, 0, 0, 0))
    green = (90, 255, 140, 255)
    arcs = [[(0, 3), (1, 4), (0, 5)], [(2, 2), (3, 3), (3, 4), (3, 5), (2, 6)],
            [(4, 1), (5, 2), (5, 3), (5, 4), (5, 5), (5, 6), (4, 7)]]
    for i, arc in enumerate(arcs[: 2 + frame % 2]):
        for x, y in arc:
            img.putpixel((x, y), green if i < 2 else (90, 255, 140, 170))
    return img


# --------------------------------------------------------------------------
# Words, names, time, and the message strip
# --------------------------------------------------------------------------
def text_image(text: str, color=WHITE, width: int = AREA_W - 2) -> Image.Image:
    text = to_font_text(text)
    while text and text_width(text) > width:
        text = text[:-1]
    img = Image.new("RGBA", (max(1, text_width(text)) + 2, 9), (0, 0, 0, 0))
    draw_text(img, text, 0, 0, color=color, shadow=SHADOW)
    return img


def word(name: str) -> Image.Image:
    return text_image(WORDS[name])


CLOCK_CHARS = "0123456789:"


def char(ch: str) -> Image.Image:
    img = Image.new("RGBA", (len(GLYPHS[ch][0]) + 1, 8), (0, 0, 0, 0))
    draw_text(img, ch, 0, 0, shadow=SHADOW)
    return img


def char_name(ch: str) -> str:
    return "colon" if ch == ":" else ch


def char_width(ch: str) -> int:
    return len(GLYPHS[ch][0]) + 1


def clock(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


MAX_CHARS = 140
GAP = "     "


def message_strip(msg, private: bool = False) -> tuple[Image.Image, int]:
    """The author (soft blurple) then the message (white); long ones scroll."""
    author = to_font_text(msg.author)
    text = "NEW MESSAGE" if private else to_font_text(msg.text or "")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rstrip() + "..."
    full = f"{author}  {text}"
    w = text_width(full)

    def paint(img, x):
        draw_text(img, author, x, 0, color=SOFT, shadow=SHADOW)
        draw_text(img, text, x + text_width(author + "  ") + 1, 0, shadow=SHADOW)

    if w <= AREA_W:
        img = Image.new("RGBA", (AREA_W, 9), (0, 0, 0, 0))
        paint(img, (AREA_W - w) // 2)
        return img, 0
    loop = text_width(full + GAP) + 1
    img = Image.new("RGBA", (loop + w + 2, 9), (0, 0, 0, 0))
    paint(img, 0)
    paint(img, loop)
    return img, loop


# --------------------------------------------------------------------------
# Back screen: "Luca Discord"
# --------------------------------------------------------------------------
def fit(d, text, f, width):
    import unicodedata
    text = "".join(c for c in text if ord(c) <= 0xFFFF and unicodedata.category(c) not in ("So", "Cs"))
    if d.textlength(text, font=f) <= width:
        return text
    while text and d.textlength(text + "…", font=f) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def back_screen(voice, messages: list, private: bool = False) -> Image.Image:
    img = Image.new("L", (BACK_W, BACK_H), 0)
    d = ImageDraw.Draw(img)
    for y in range(BACK_H):
        for x in range(BACK_W):
            img.putpixel((x, y), int(55 * max(0, 1 - math.hypot(x - 20, y - 70) / 150)))
    wx0, wy0, wx1, wy1 = 2, 1, 157, 78
    d.rounded_rectangle([wx0, wy0, wx1, wy1], radius=5, fill=120, outline=230)
    for y in range(wy0 + 1, wy0 + 13):
        d.line([(wx0 + 2, y), (wx1 - 2, y)], fill=int(205 - (y - wy0) * 6))
    for sx in (68, 76, 124):
        d.line([(sx, wy0 + 1), (sx + 10, wy0 + 12)], fill=235)
    d.rounded_rectangle([wx0 + 4, wy0 + 2, wx0 + 11, wy0 + 7], radius=2, fill=20)  # a chat bubble
    d.point((wx0 + 5, wy0 + 8), fill=20)
    d.text((wx0 + 15, wy0), "Luca Discord", font=font(10), fill=20)
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

    if voice.active:
        title = f"# {voice.channel}" if voice.channel else "In a voice call"
        d.text((cx0 + 4, cy0 + 1), fit(d, title, font(10), 95), font=font(10), fill=0)
        if voice.since:
            stamp = clock(_time.time() - voice.since)
            d.text((cx1 - 4, cy0 + 2), stamp, font=font(9), fill=40, anchor="ra")
        if voice.guild:
            d.text((cx0 + 4, cy0 + 12), fit(d, voice.guild, font(8), cx1 - cx0 - 8), font=font(8), fill=70)
        if voice.rich:
            people = sorted(voice.members.values(), key=lambda m: (not m.talking, m.name.lower()))
            for i, m in enumerate(people[:6]):
                col, row = i % 2, i // 2
                x, y = cx0 + 4 + col * 74, cy0 + 23 + row * 12
                d.ellipse([x, y + 1, x + 8, y + 9], fill=0 if m.talking else 200, outline=40)
                if m.talking:  # a glowing "talking" ring
                    d.ellipse([x - 1, y, x + 9, y + 10], outline=0)
                d.text((x + 11, y), fit(d, m.name, font(9), 50), font=font(9), fill=0)
                if m.muted or m.deafened:
                    d.line([(x + 66, y + 2), (x + 70, y + 8)], fill=0, width=2)
            if len(people) > 6:
                d.text((cx1 - 4, cy1 - 1), f"+{len(people) - 6} more", font=font(8), fill=60, anchor="rb")
        else:
            d.text((cx0 + 4, cy0 + 26), "Discord is using your mic.", font=font(9), fill=40)
            d.text((cx0 + 4, cy0 + 38), "Set up rich mode to see who's", font=font(8), fill=80)
            d.text((cx0 + 4, cy0 + 47), "here and who's talking.", font=font(8), fill=80)
        state = "Deafened" if voice.self_deaf else "Muted" if voice.self_mute else ""
        if state:
            d.rounded_rectangle([cx1 - 46, cy0 + 11, cx1 - 3, cy0 + 20], radius=3, fill=40)
            d.text((cx1 - 25, cy0 + 15), state, font=font(8), fill=255, anchor="mm")
    elif messages:
        for i, m in enumerate(messages[:3]):
            y = cy0 + 1 + i * 19
            d.text((cx0 + 4, y + 1), fit(d, m.author, font(9), 90), font=font(9), fill=0)
            d.text((cx1 - 4, y + 2), _time.strftime("%H:%M", _time.localtime(m.at)), font=font(8), fill=70, anchor="ra")
            line = "New message" if private else (m.text or "")
            if m.where and not private:
                line = f"{m.where}: {line}"
            d.text((cx0 + 4, y + 10), fit(d, line, font(8), cx1 - cx0 - 8), font=font(8), fill=60)
    else:
        d.text((cx0 + 6, cy0 + 22), "All quiet on Discord", font=font(10), fill=90)
    return img.point(lambda v: (v // 17) * 17)


# --------------------------------------------------------------------------
# Previews
# --------------------------------------------------------------------------
def main() -> None:
    from discord_state import Member, Message, Voice

    preview = HERE / "preview"
    preview.mkdir(exist_ok=True)
    frames = []

    def frame(sig, k, pieces, pose, icon=None, scroll=None):
        out = sign(sig, k).convert("RGBA")
        if scroll is not None:
            strip, off = scroll
            out.alpha_composite(strip.crop((off, 0, off + AREA_W, 9)), (AREA_X, TEXT_Y))
        else:
            total = sum(p.width - 1 for p in pieces) + 2 * (len(pieces) - 1)
            x = AREA_X + ((ICON_X - 2 if icon else FRONT_W) - AREA_X - total) // 2
            for p in pieces:
                out.alpha_composite(p, (x, TEXT_Y))
                x += p.width + 1
        if icon:
            out.alpha_composite(icon, (ICON_X, TEXT_Y))
        out.alpha_composite(tile(pose, k), (0, 0))
        return led_preview(out.convert("RGB"), 6)

    for k in range(8):
        frames.append(frame("voice", k, [text_image("#general", SOFT)], "listen"))
    for k in range(10):  # Kiro talking
        frames.append(frame("voice", k, [text_image("Kiro"), waves(k)], "listen"))
    for k in range(8):  # you talking
        frames.append(frame("voice", k, [text_image("12:34")], "talk"))
    for k in range(8):  # muted
        frames.append(frame("voice", k, [word("muted")], "muted", crossed(MIC)))
    msg = Message("Kiro", "omg Luca looks so good on the bar!! come hang in voice", "#general · Pack Den")
    strip, loop = message_strip(msg)
    for k in range(0, 14 + loop, 5):
        frames.append(frame("message", k // 3, [], "alert" if k < 14 else "listen",
                            scroll=(strip, max(0, k - 14))))
    frames[0].save(preview / "front.gif", save_all=True, append_images=frames[1:],
                   duration=180, loop=0, optimize=True)

    v = Voice(active=True, channel="general", guild="Pack Den", since=_time.time() - 754,
              self_id="1", self_mute=True, rich=True)
    for i, (n, talk, mute) in enumerate([("Luca", False, True), ("Kiro", True, False),
                                         ("Aero Fox", False, False), ("Bubbles", False, True)]):
        v.members[str(i + 1)] = Member(str(i + 1), n, talk, mute)
    back_screen(v, []).resize((BACK_W * 4, BACK_H * 4), Image.NEAREST).save(preview / "back.png")
    sheet = Image.new("RGB", (len(POSES) * (TILE_W * 8 + 8), FRONT_H * 8), (40, 40, 40))
    for k, p in enumerate(POSES):
        sheet.paste(led_preview(tile(p, 1).convert("RGB"), 8), (k * (TILE_W * 8 + 8), 0))
    sheet.save(preview / "poses.png")
    print(f"Wrote previews to {preview}")


if __name__ == "__main__":
    main()
