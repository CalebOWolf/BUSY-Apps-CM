"""
Artwork for Luca Aero Clock, drawn with Pillow.

Uploaded once:
  big_<c>.png        glossy double-size digits and ":" for the time
  tile_<mood>_N.png  19x16 glass tile with Luca through the day: sleepy in a
                     nightcap, coffee in the morning, sunny by day, cozy in the
                     evening, howling on the hour
Re-drawn every minute:
  sky_N.png          the real sky right now: night with the moon's actual
                     phase, dawn, the sun crossing the sky, golden sunset, dusk
  date.png           "WED / 18 NOV" for the date page
Re-drawn every second:
  the back screen    a Windows 7-style analog clock gadget

    python art.py      # writes previews into preview/
"""

from __future__ import annotations

import math
import random
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from pixelart import GLYPHS, draw_text, led_preview, lerp, text_width  # noqa: E402
from pixelart import ui_font as font  # noqa: E402

HERE = Path(__file__).parent
FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80
TILE_W = 19
AREA_X, AREA_W = 20, 52      # the part of the strip right of Luca's tile
CLOCK_Y = 1
MOODS = {"sleepy": 2, "coffee": 2, "sunny": 2, "cozy": 2, "howl": 2}
BIG_CHARS = "0123456789:"
MINT = (80, 240, 190, 255)


# --------------------------------------------------------------------------
# Big glossy digits (the 5x7 font at double size)
# --------------------------------------------------------------------------
def big_char(ch: str) -> Image.Image:
    rows = GLYPHS[ch]
    w, h = len(rows[0]) * 2, len(rows) * 2
    img = Image.new("RGBA", (w + 1, h + 1), (0, 0, 0, 0))
    for pass_ in (0, 1):  # a soft navy shadow, then the glossy digit
        for gy, row in enumerate(rows):
            for gx, on in enumerate(row):
                if on != "X":
                    continue
                for dy in range(2):
                    for dx in range(2):
                        y = gy * 2 + dy
                        if pass_ == 0:
                            img.putpixel((gx * 2 + dx + 1, y + 1), (0, 30, 90, 255))
                        else:  # bright white on top, cool glassy blue below
                            c = (255, 255, 255) if y < h / 2 else lerp((215, 240, 255), (160, 210, 255), (y - h / 2) / (h / 2))
                            img.putpixel((gx * 2 + dx, y), c + (255,))
    return img


def big_width(ch: str) -> int:
    return len(GLYPHS[ch][0]) * 2 + 2   # digit plus a 2 px gap


def time_layout(text: str) -> list[tuple[str, int]]:
    """(char, x) for each character, centred in the area right of Luca."""
    total = sum(big_width(c) for c in text) - 2
    x = AREA_X + (AREA_W - total) // 2
    out = []
    for c in text:
        out.append((c, x))
        x += big_width(c)
    return out


# --------------------------------------------------------------------------
# The sky right now
# --------------------------------------------------------------------------
def put(img, x, y, c, a=1.0):
    if 0 <= x < img.width and 0 <= y < img.height:
        img.putpixel((x, y), lerp(img.getpixel((x, y)), c, a))


def gradient(top, bottom, shine=0.3) -> Image.Image:
    img = Image.new("RGB", (FRONT_W, FRONT_H))
    d = ImageDraw.Draw(img)
    for y in range(FRONT_H):
        c = lerp(top, bottom, y / (FRONT_H - 1))
        if y < FRONT_H // 2:
            c = lerp(c, (255, 255, 255), shine * (1 - y / (FRONT_H / 2)))
        d.line([(0, y), (FRONT_W - 1, y)], fill=c)
    return img


# (elevation in degrees, top color, bottom color) blended between neighbours
SKY_STOPS = [
    (-18, (3, 6, 30), (12, 22, 70)),       # night
    (-8, (30, 25, 90), (120, 60, 130)),    # deep twilight: indigo to violet
    (-2, (80, 70, 160), (255, 130, 110)),  # dawn / dusk: violet to pink-orange
    (4, (110, 160, 230), (255, 175, 90)),  # golden hour
    (15, (110, 200, 255), (20, 120, 220)), # bright Aero day
    (90, (100, 195, 255), (0, 100, 210)),
]


def sky_colors(elev: float):
    elev = max(SKY_STOPS[0][0], min(SKY_STOPS[-1][0], elev))
    for (e0, t0, b0), (e1, t1, b1) in zip(SKY_STOPS, SKY_STOPS[1:]):
        if e0 <= elev <= e1:
            k = (elev - e0) / (e1 - e0)
            return lerp(t0, t1, k), lerp(b0, b1, k)
    return SKY_STOPS[-1][1], SKY_STOPS[-1][2]


def draw_moon(img, phase: float, cx: int = 64, cy: int = 4, r: float = 3.6):
    """The moon as it really looks tonight (waxing lit on the right)."""
    for y in range(-4, 5):
        for x in range(-4, 5):
            if math.hypot(x, y) > r:
                continue
            k = math.sqrt(max(0.0, 1 - (y / r) ** 2)) * r
            edge = k * math.cos(2 * math.pi * phase)
            lit = x > edge if phase < 0.5 else x < -edge
            put(img, cx + x, cy + y, (250, 240, 185) if lit else (60, 70, 110), 1.0 if lit else 0.6)


def sky(elev: float, sun_frac: float | None, moon_phase: float, frame: int) -> Image.Image:
    """`sun_frac` is how far the sun is across today's sky (0 sunrise, 1 sunset)."""
    top, bottom = sky_colors(elev)
    img = gradient(top, bottom, 0.3 if elev > 4 else 0.12)
    if elev < -6:  # stars fade in as it gets dark
        a = min(1.0, (-6 - elev) / 8)
        rnd = random.Random(21)
        for _ in range(18):
            x, y, p = rnd.randrange(AREA_X, FRONT_W), rnd.randrange(12), rnd.random() * 6
            put(img, x, y, (255, 250, 215), a * (0.35 + 0.65 * abs(math.sin(frame * 1.7 + p))))
    if elev < 2:
        draw_moon(img, moon_phase)
    if sun_frac is not None and elev > -3:
        x = round(AREA_X + 2 + sun_frac * (AREA_W - 6))
        y = round(13 - max(0.0, min(1.0, (elev + 3) / 50)) * 10)
        warm = elev < 8
        body = (255, 160, 70) if warm else (255, 215, 70)
        d = ImageDraw.Draw(img)
        for k in range(8):  # a soft glow
            a = k * math.pi / 4 + frame * 0.4
            put(img, x + round(5 * math.cos(a)), y + round(5 * math.sin(a)), (255, 235, 160), 0.5)
        d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=body)
        d.ellipse([x - 2, y - 2, x, y], fill=(255, 245, 190))
        if warm:  # a glowing horizon
            for xx in range(AREA_X, FRONT_W):
                put(img, xx, 15, (255, 190, 110), 0.5)
    return img


# --------------------------------------------------------------------------
# Luca through the day
# --------------------------------------------------------------------------
PALETTE = {
    "K": (28, 30, 44), "W": (255, 255, 255), "S": (190, 205, 230),
    "G": (150, 150, 158), "T": (40, 235, 175), "M": (8, 8, 12),
    "O": (245, 160, 80), "N": (225, 140, 115), "P": (255, 150, 160),
    "C": (170, 70, 210), "c": (255, 255, 255),    # purple nightcap and its pom-pom
    "B": (150, 90, 50), "b": (240, 240, 240),     # coffee mug
    "z": (200, 210, 255),
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


def luca(mood: str, frame: int) -> list[str]:
    rows = [list(r) for r in LUCA]
    closed = (("WW", "KK"), ("MM", "SS"))
    happy = (("KK", "WW"), ("SS", "MM"))
    if mood == "sleepy":
        (l6, l7), (r6, r7) = closed
        rows[0] = list("...........cc...")
        rows[1] = list(".........CCcc...")
        rows[2] = list("KGGKKKCCCCCCCK..")  # a floppy nightcap
    elif mood in ("cozy", "sunny") or (mood == "coffee" and frame % 2):
        (l6, l7), (r6, r7) = happy if mood != "coffee" else closed
    elif mood == "howl":
        (l6, l7), (r6, r7) = closed
        rows[11][6:9] = "KKK"
        rows[12][6:9] = "PKP"
    else:
        return ["".join(r) for r in rows]
    rows[6][3:5], rows[7][3:5] = l6, l7
    rows[6][10:12], rows[7][10:12] = r6, r7
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
    lift = -1 if mood == "howl" and frame % 2 else (frame % 2 if mood == "sleepy" else 0)
    for y, row in enumerate(luca(mood, frame)):
        for x, ch in enumerate(row):
            if ch != "." and 0 <= y + lift < FRONT_H:
                img.putpixel((x + 1, y + lift), PALETTE[ch] + (255,))
    if mood == "coffee":  # a steaming mug beside him
        for x, y, ch in [(15, 11, "b"), (16, 11, "b"), (17, 11, "b"), (15, 12, "B"), (16, 12, "B"),
                         (17, 12, "B"), (18, 12, "b"), (15, 13, "B"), (16, 13, "B"), (17, 13, "B"),
                         (18, 13, "b"), (15, 14, "B"), (16, 14, "B"), (17, 14, "B")]:
            img.putpixel((x, y), PALETTE[ch] + (255,))
        img.putpixel((16 + frame % 2, 9), (230, 230, 240, 255))  # steam
        img.putpixel((16, 8 - frame % 2), (200, 200, 220, 255))
    if mood == "sleepy":  # a little z
        for x, y in [(15, 5), (16, 5), (17, 5), (16, 6), (15, 7), (16, 7), (17, 7)]:
            img.putpixel((x, y - frame % 2), PALETTE["z"] + (255,))
    return img


def mood_for(now: datetime, sun_up: bool) -> str:
    h = now.hour
    if h >= 23 or h < 6:
        return "sleepy"
    if h < 10:
        return "coffee"
    if sun_up and h < 18:
        return "sunny"
    return "cozy"


# --------------------------------------------------------------------------
# Date page
# --------------------------------------------------------------------------
def date_image(now: datetime) -> Image.Image:
    img = Image.new("RGBA", (AREA_W, 16), (0, 0, 0, 0))
    top = now.strftime("%A").upper()
    if text_width(top) > AREA_W - 2:
        top = now.strftime("%a").upper()
    bottom = f"{now.day} {now.strftime('%b').upper()}"
    draw_text(img, top, (AREA_W - text_width(top)) // 2, 0, color=MINT)
    draw_text(img, bottom, (AREA_W - text_width(bottom)) // 2, 8)
    return img


# --------------------------------------------------------------------------
# Back screen: a Windows 7 clock gadget
# --------------------------------------------------------------------------
def back_screen(now: datetime, rise: datetime | None, set_: datetime | None,
                hour24: bool = True) -> Image.Image:
    img = Image.new("L", (BACK_W, BACK_H), 0)
    d = ImageDraw.Draw(img)
    for y in range(BACK_H):
        for x in range(BACK_W):
            img.putpixel((x, y), int(55 * max(0, 1 - math.hypot(x - 120, y - 40) / 140)))

    # the round glass clock face
    cx, cy, r = 40, 40, 36
    d.ellipse([cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2], fill=70, outline=230)
    for rr in range(r, 0, -1):  # a soft radial shine
        shade = int(245 - 60 * (rr / r) ** 2)
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=shade)
    d.chord([cx - r + 4, cy - r + 2, cx + r - 4, cy + 4], 180, 360, fill=250)  # glossy top
    for i in range(60):
        a = math.radians(i * 6 - 90)
        inner = r - (6 if i % 5 == 0 else 3)
        d.line([(cx + inner * math.cos(a), cy + inner * math.sin(a)),
                (cx + (r - 1) * math.cos(a), cy + (r - 1) * math.sin(a))],
               fill=30 if i % 5 == 0 else 120, width=2 if i % 15 == 0 else 1)
    for n, (dx, dy) in {"12": (0, -1), "3": (1, 0), "6": (0, 1), "9": (-1, 0)}.items():
        d.text((cx + dx * (r - 13), cy + dy * (r - 13)), n, font=font(9), fill=40, anchor="mm")

    def hand(angle_deg, length, width, shade):
        a = math.radians(angle_deg - 90)
        d.line([(cx - 4 * math.cos(a), cy - 4 * math.sin(a)),
                (cx + length * math.cos(a), cy + length * math.sin(a))], fill=shade, width=width)
    sec = now.second
    minute = now.minute + sec / 60
    hour = now.hour % 12 + minute / 60
    hand(hour * 30, r - 16, 4, 20)
    hand(minute * 6, r - 7, 3, 35)
    hand(sec * 6, r - 4, 1, 110)
    d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=20)
    d.ellipse([cx - 1, cy - 1, cx + 1, cy + 1], fill=200)

    # the date and digital time, on a glass panel
    px0, py0, px1, py1 = 84, 6, 156, 74
    d.rounded_rectangle([px0, py0, px1, py1], radius=6, fill=140, outline=220)
    for y in range(py0 + 2, py0 + 24):
        d.line([(px0 + 3, y), (px1 - 3, y)], fill=int(210 - (y - py0) * 2.5))
    mid = (px0 + px1) // 2
    d.text((mid, py0 + 4), now.strftime("%A"), font=font(11), fill=10, anchor="ma")
    d.text((mid, py0 + 18), f"{now.day} {now.strftime('%B')}", font=font(9), fill=30, anchor="ma")
    if hour24:
        digital = now.strftime("%H:%M:%S")
    else:
        digital = now.strftime("%I:%M:%S").lstrip("0") + now.strftime(" %p").lower()
    d.text((mid, py0 + 32), digital, font=font(14), fill=0, anchor="ma")
    fmt = "%H:%M" if hour24 else "%I:%M"
    if rise and set_:
        d.text((mid, py0 + 51), f"Sunrise {rise.strftime(fmt).lstrip('0')}", font=font(8), fill=50, anchor="ma")
        d.text((mid, py0 + 60), f"Sunset {set_.strftime(fmt).lstrip('0')}", font=font(8), fill=50, anchor="ma")
    return img.point(lambda v: (v // 17) * 17)


# --------------------------------------------------------------------------
# Previews
# --------------------------------------------------------------------------
def compose(now: datetime, elev: float, sun_frac, phase: float, frame: int, show_date=False,
            mood: str | None = None, hour24: bool = True) -> Image.Image:
    out = sky(elev, sun_frac, phase, frame).convert("RGBA")
    if show_date:
        out.alpha_composite(date_image(now), (AREA_X, 0))
    else:
        text = now.strftime("%H:%M") if hour24 else now.strftime("%I:%M").lstrip("0")
        for ch, x in time_layout(text):
            if ch == ":" and frame % 2:
                continue  # the colon blinks with the seconds
            out.alpha_composite(big_char(ch), (x, CLOCK_Y))
    out.alpha_composite(tile(mood or mood_for(now, 0 < elev), frame), (0, 0))
    return out.convert("RGB")


def main() -> None:
    from datetime import timedelta, timezone
    import sky as skycalc

    preview = HERE / "preview"
    preview.mkdir(exist_ok=True)
    tz = timezone(timedelta(hours=1))
    day = datetime(2026, 11, 24, 0, 0, tzinfo=tz)  # a full-moon day in Berlin
    lat, lon = 52.52, 13.41
    rise, set_ = skycalc.sun_times(day.date(), lat, lon, tz)
    frames = []
    for i, minutes in enumerate(range(5 * 60, 24 * 60 + 60, 25)):  # a whole day, fast-forwarded
        now = day + timedelta(minutes=minutes % (24 * 60))
        elev = skycalc.sun_elevation(now, lat, lon)
        frac = None
        if rise and set_ and rise <= now <= set_ + timedelta(minutes=30):
            frac = min(1.0, (now - rise) / (set_ - rise))
        phase = skycalc.moon_phase(now)
        mood = "howl" if now.minute < 25 and now.hour == 12 else None
        frames.append(led_preview(compose(now, elev, frac, phase, i, show_date=(i % 12 == 11),
                                          mood=mood), 8))
    frames[0].save(preview / "front.gif", save_all=True, append_images=frames[1:],
                   duration=220, loop=0, optimize=True)
    back_screen(day.replace(hour=14, minute=32, second=7), rise, set_) \
        .resize((BACK_W * 4, BACK_H * 4), Image.NEAREST).save(preview / "back.png")
    sheet = Image.new("RGB", (len(MOODS) * (TILE_W * 8 + 8), FRONT_H * 8), (40, 40, 40))
    for k, m in enumerate(MOODS):
        sheet.paste(led_preview(tile(m, 0).convert("RGB"), 8), (k * (TILE_W * 8 + 8), 0))
    sheet.save(preview / "moods.png")
    print(f"Wrote previews to {preview}")


if __name__ == "__main__":
    main()
