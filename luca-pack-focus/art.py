"""
Artwork for Luca Pack Focus, drawn with Pillow.

Uploaded once:
  sky_<phase>_N.png   72x16 skies: deep Aero blue for focus, a sunset for
                      short breaks, a starry night for the long break
  moon_NN.png         the moon, from new (00) to full (16), with a soft glow
  tile_<pose>_N.png   19x16 glass tile with Luca: focused, resting, howling,
                      paused, waiting
  char_<c>[_dim].png  digits and ":" (bright and dimmed) for the countdown
  word_<name>.png     FOCUS, BREAK, REST, AWOO!, START?
Re-drawn every second while running:
  the back screen     "Luca Focus", a Windows 7-style timer window

    python art.py      # writes previews into preview/
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from pixelart import GLYPHS, draw_text, led_preview, lerp, text_width  # noqa: E402
from pixelart import ui_font as font  # noqa: E402

HERE = Path(__file__).parent
FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80
TILE_W = 19
SKY_FRAMES = 8
MOON_STEPS = 16
CLOCK_XY = (22, 2)        # the countdown
WORD_XY = (22, 2)         # a word shown instead of the countdown
PAWS_XY = (22, 12)        # round markers under the countdown
MOON_XY = (59, 2)         # top-left of the 11x11 moon
PHASES = ["focus", "short", "long"]
POSES = {"focused": 2, "resting": 2, "howling": 2, "paused": 1, "waiting": 2}
WORDS = {"focus": "FOCUS", "break": "BREAK", "rest": "REST", "awoo": "AWOO!", "start": "START?"}

WHITE = (255, 255, 255, 255)
DIM = (150, 175, 210, 255)
MINT = (80, 240, 190, 255)


# --------------------------------------------------------------------------
# Skies
# --------------------------------------------------------------------------
def gradient(top, bottom, shine=0.3) -> Image.Image:
    img = Image.new("RGB", (FRONT_W, FRONT_H))
    d = ImageDraw.Draw(img)
    for y in range(FRONT_H):
        c = lerp(top, bottom, y / (FRONT_H - 1))
        if y < FRONT_H // 2:
            c = lerp(c, (255, 255, 255), shine * (1 - y / (FRONT_H / 2)))
        d.line([(0, y), (FRONT_W - 1, y)], fill=c)
    return img


def put(img, x, y, c, a=1.0):
    if 0 <= x < img.width and 0 <= y < img.height:
        img.putpixel((x, y), lerp(img.getpixel((x, y)), c, a))


def sky(phase: str, frame: int) -> Image.Image:
    if phase == "focus":  # calm deep Aero blue, a few slow bubbles
        img = gradient((70, 150, 235), (5, 45, 140), 0.3)
        for bx, p0 in ((34, 0), (48, 9)):
            p = (p0 + frame * 22 / SKY_FRAMES) % 22
            x, y = bx + round(math.sin(p / 3)), round(FRONT_H + 2 - p)
            for X, Y in [(x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1)]:
                put(img, X, Y, (220, 245, 255), 0.35)
    elif phase == "short":  # a warm sunset for a breather
        img = gradient((255, 170, 120), (150, 60, 140), 0.25)
        for x in range(20, FRONT_W):  # a soft glowing horizon
            put(img, x, 14, (255, 220, 150), 0.5)
            put(img, x, 15, (255, 200, 120), 0.35)
    else:  # the long break: a starry night
        img = gradient((5, 10, 45), (25, 40, 110), 0.08)
        rnd = random.Random(9)
        for _ in range(14):
            x, y, p = rnd.randrange(20, FRONT_W), rnd.randrange(14), rnd.random() * 6
            put(img, x, y, (255, 250, 210), 0.3 + 0.7 * abs(math.sin(frame / 2 + p)))
    return img


def moon(step: int) -> Image.Image:
    """An 11x11 moon waxing from new (0) to full (MOON_STEPS), with a halo."""
    img = Image.new("RGBA", (11, 11), (0, 0, 0, 0))
    frac = step / MOON_STEPS
    for y in range(11):
        for x in range(11):
            dx, dy = x - 5, y - 5
            r = math.hypot(dx, dy)
            if r <= 4.6:
                # a waxing moon: the shadow's edge sweeps from the right side to the left
                edge = 4.6 * math.cos(math.pi * frac) * math.sqrt(max(0.0, 1 - (dy / 4.6) ** 2))
                lit = frac >= 1 or (frac > 0 and dx > edge)
                if lit:
                    c = lerp((255, 245, 190), (235, 215, 150), (dx + dy + 8) / 16)
                    img.putpixel((x, y), c + (255,))
                else:
                    img.putpixel((x, y), (75, 90, 140, 235))  # the dark side, faintly lit
            elif r <= 5.4 and frac >= 1:
                img.putpixel((x, y), (255, 240, 170, 110))  # full moon glow
    if frac >= 0.5:  # a little crater
        img.putpixel((6, 4), (220, 200, 140, 255))
        img.putpixel((4, 6), (225, 205, 145, 255))
    return img


# --------------------------------------------------------------------------
# Luca
# --------------------------------------------------------------------------
PALETTE = {
    "K": (28, 30, 44), "W": (255, 255, 255), "S": (190, 205, 230),
    "G": (150, 150, 158), "T": (40, 235, 175), "M": (8, 8, 12),
    "O": (245, 160, 80), "N": (225, 140, 115), "P": (255, 150, 160),
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


def luca(pose: str, frame: int) -> list[str]:
    rows = [list(r) for r in LUCA]
    if pose == "focused":    # determined, half-lidded eyes
        rows[6][3:5], rows[6][10:12] = "WW", "MM"
        rows[7][3:5], rows[7][10:12] = "OK", "OK"
    elif pose == "resting":  # ^^ happy eyes
        rows[6][3:5], rows[7][3:5] = "KK", "WW"
        rows[6][10:12], rows[7][10:12] = "SS", "MM"
    elif pose == "howling":  # eyes shut, round "awoo" mouth
        rows[6][3:5], rows[7][3:5] = "WW", "KK"
        rows[6][10:12], rows[7][10:12] = "MM", "SS"
        rows[11][6:9] = "KKK"
        rows[12][6:9] = "PKP"
    elif pose == "waiting" and frame % 2:  # a blink while he waits for you
        rows[6][3:5], rows[7][3:5] = "WW", "KK"
        rows[6][10:12], rows[7][10:12] = "MM", "SS"
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
    lift = {"howling": -1 if frame % 2 else 0, "resting": frame % 2}.get(pose, 0)
    for y, row in enumerate(luca(pose, frame)):
        for x, ch in enumerate(row):
            if ch != "." and 0 <= y + lift < FRONT_H:
                img.putpixel((x + 1, y + lift), PALETTE[ch] + (255,))
    if pose == "paused":  # little pause bars by his ear
        for x in (16, 18):
            for y in range(1, 6):
                img.putpixel((x - 1, y), WHITE)
    return img


# --------------------------------------------------------------------------
# Text pieces
# --------------------------------------------------------------------------
CLOCK_CHARS = "0123456789:"


def char_name(ch: str) -> str:
    return "colon" if ch == ":" else ch


def char(ch: str, dim: bool = False) -> Image.Image:
    img = Image.new("RGBA", (len(GLYPHS[ch][0]) + 1, 8), (0, 0, 0, 0))
    draw_text(img, ch, 0, 0, color=DIM if dim else WHITE)
    return img


def char_width(ch: str) -> int:
    return len(GLYPHS[ch][0]) + 1


def word(name: str) -> Image.Image:
    text = WORDS[name]
    img = Image.new("RGBA", (text_width(text) + 2, 9), (0, 0, 0, 0))
    draw_text(img, text, 0, 0, color=MINT if name not in ("awoo",) else (255, 230, 120, 255))
    return img


def clock(seconds: float) -> str:
    s = max(0, int(math.ceil(seconds)))
    return f"{s // 60}:{s % 60:02d}" if s < 6000 else f"{s // 3600}:{s % 3600 // 60:02d}"


# --------------------------------------------------------------------------
# Back screen: "Luca Focus"
# --------------------------------------------------------------------------
PHASE_NAMES = {"focus": "Focus", "short": "Short break", "long": "Long break"}


def back_screen(phase: str, remaining: float, total: float, state: str,
                round_no: int, rounds: int, today_sessions: int, today_minutes: float) -> Image.Image:
    img = Image.new("L", (BACK_W, BACK_H), 0)
    d = ImageDraw.Draw(img)
    for y in range(BACK_H):
        for x in range(BACK_W):
            img.putpixel((x, y), int(60 * max(0, 1 - math.hypot(x - 140, y - 70) / 150)))

    wx0, wy0, wx1, wy1 = 2, 1, 157, 78
    d.rounded_rectangle([wx0, wy0, wx1, wy1], radius=5, fill=120, outline=230)
    for y in range(wy0 + 1, wy0 + 13):
        d.line([(wx0 + 2, y), (wx1 - 2, y)], fill=int(205 - (y - wy0) * 6))
    for sx in (62, 70, 122):
        d.line([(sx, wy0 + 1), (sx + 10, wy0 + 12)], fill=235)
    d.ellipse([wx0 + 4, wy0 + 2, wx0 + 11, wy0 + 9], fill=230, outline=20)  # moon icon
    d.ellipse([wx0 + 3, wy0 + 1, wx0 + 8, wy0 + 7], fill=200)
    d.text((wx0 + 15, wy0), "Luca Focus", font=font(10), fill=20)
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

    label = PHASE_NAMES[phase] + {"paused": "  (paused)", "idle": "  (ready)",
                                   "done": "  done!"}.get(state, "")
    d.text((cx0 + 5, cy0 + 2), label, font=font(9), fill=40)
    d.text((cx0 + 4, cy0 + 10), clock(remaining), font=font(24), fill=0)

    # round paws: one per focus round in this cycle
    for i in range(rounds):
        px, py = cx1 - 10 - (rounds - 1 - i) * 11, cy0 + 7
        filled = i < round_no
        d.ellipse([px - 3, py, px + 3, py + 5], fill=40 if filled else 210, outline=40)
        for k, ox in enumerate((-4, -1, 2, 5)):
            d.ellipse([px + ox - 1, py - 3 - (k in (1, 2)), px + ox, py - 2 - (k in (1, 2))],
                      fill=40 if filled else 170)

    # Aero progress bar
    px0, py0, px1, py1 = cx0 + 4, cy0 + 38, cx1 - 4, cy0 + 45
    d.rounded_rectangle([px0, py0, px1, py1], radius=3, fill=200, outline=60)
    done = 0 if total <= 0 else 1 - remaining / total
    fill = px0 + 1 + int((px1 - px0 - 2) * max(0, min(1, done)))
    if fill > px0 + 2:
        d.rounded_rectangle([px0 + 1, py0 + 1, fill, py1 - 1], radius=2, fill=100)
        d.line([(px0 + 2, py0 + 2), (fill - 1, py0 + 2)], fill=190)

    today = f"Today: {today_sessions} focus {'round' if today_sessions == 1 else 'rounds'}, " \
            f"{today_minutes:.0f} min"
    d.text((cx0 + 5, cy1 - 10), today, font=font(8), fill=60)
    return img.point(lambda v: (v // 17) * 17)


# --------------------------------------------------------------------------
# Previews
# --------------------------------------------------------------------------
def compose(phase, remaining, total, pose, frame, paws=(2, 4), word_name=None) -> Image.Image:
    out = sky(phase, frame).convert("RGBA")
    step = round(MOON_STEPS * (1 - remaining / total)) if phase == "focus" else MOON_STEPS
    out.alpha_composite(moon(step), MOON_XY)
    if word_name:
        out.alpha_composite(word(word_name), WORD_XY)
    else:
        x, y = CLOCK_XY
        for ch in clock(remaining):
            out.alpha_composite(char(ch), (x, y))
            x += char_width(ch)
    done, total_paws = paws
    for i in range(total_paws):
        c = MINT if i < done else (WHITE if i == done else (60, 90, 150, 255))
        for dx in range(2):
            out.putpixel((PAWS_XY[0] + i * 4 + dx, PAWS_XY[1] + 2), c)
    out.alpha_composite(tile(pose, frame), (0, 0))
    return out.convert("RGB")


def main() -> None:
    preview = HERE / "preview"
    preview.mkdir(exist_ok=True)
    frames = []
    total = 25 * 60
    for i in range(24):  # a fast-forwarded focus round
        rem = total * (1 - i / 23)
        frames.append(led_preview(compose("focus", rem, total, "focused", i), 8))
    for i in range(10):  # the moon is full: AWOO!
        frames.append(led_preview(compose("focus", 0, total, "howling", i, word_name="awoo"), 8))
    for i in range(14):  # a sunset break
        frames.append(led_preview(compose("short", 300 - i * 20, 300, "resting", i, (3, 4)), 8))
    frames[0].save(preview / "front.gif", save_all=True, append_images=frames[1:],
                   duration=170, loop=0, optimize=True)
    back_screen("focus", 14 * 60 + 32, 25 * 60, "running", 2, 4, 3, 75) \
        .resize((BACK_W * 4, BACK_H * 4), Image.NEAREST).save(preview / "back.png")
    print(f"Wrote previews to {preview}")


if __name__ == "__main__":
    main()
