"""
Artwork for Luca Weather Den, drawn with Pillow.

  scene_<weather>_NN.png  72x16 animated skies: sunshine, stars and moon,
                          drifting clouds, fog, rain, snow, thunderstorms
  tile_<outfit>_N.png     19x16 glass tile with Luca dressed for the weather:
                          shades, umbrella, scarf, sleepy, hot, plain
  page_N.png              the words on the strip ("21° SUNNY", "H24° L13°"…)
  back screen             a Windows 7 desktop-gadget-style weather card

    python art.py      # writes previews into preview/
"""

from __future__ import annotations

import math
import random
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from pixelart import draw_text, led_preview, lerp, text_width, to_font_text  # noqa: E402
from pixelart import ui_font as font  # noqa: E402

import weather  # noqa: E402

HERE = Path(__file__).parent
FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80
TILE_W = 19
TEXT_X, TEXT_Y = 20, 4
TEXT_W = FRONT_W - TEXT_X
SCENE_FRAMES = 12
OUTFITS = ["plain", "shades", "hot", "umbrella", "scarf", "sleepy"]

WHITE = (255, 255, 255, 255)
MINT = (80, 240, 190, 255)


# --------------------------------------------------------------------------
# Skies
# --------------------------------------------------------------------------
def scene_key(cond: str, is_day: bool) -> str:
    """Which animated sky to use."""
    if cond in ("clear", "partly"):
        return f"{cond}_{'day' if is_day else 'night'}"
    return "rain" if cond == "drizzle" else cond


SCENES = ["clear_day", "clear_night", "partly_day", "partly_night", "cloudy", "fog",
          "rain", "snow", "storm"]


def gradient(top, bottom, shine=0.35) -> Image.Image:
    img = Image.new("RGB", (FRONT_W, FRONT_H))
    d = ImageDraw.Draw(img)
    for y in range(FRONT_H):
        c = lerp(top, bottom, y / (FRONT_H - 1))
        if y < FRONT_H // 2:
            c = lerp(c, (255, 255, 255), shine * (1 - y / (FRONT_H / 2)))
        d.line([(0, y), (FRONT_W - 1, y)], fill=c)
    return img


def put(img, x, y, c, alpha=1.0):
    if 0 <= x < img.width and 0 <= y < img.height:
        img.putpixel((x, y), lerp(img.getpixel((x, y)), c, alpha))


def cloud(img, x, y, color=(245, 250, 255), alpha=0.9):
    """A puffy 11x5 pixel cloud with a glossy top."""
    shape = ["...XXX.....", ".XXXXXXX...", "XXXXXXXXXX.", "XXXXXXXXXXX", ".XXXXXXXXX."]
    for dy, row in enumerate(shape):
        for dx, ch in enumerate(row):
            if ch == "X":
                shade = lerp(color, (180, 195, 215), dy / 6)
                put(img, x + dx, y + dy, shade, alpha)


def sun(img, frame, cx=63, cy=4):
    d = ImageDraw.Draw(img)
    for k in range(8):  # rays that gently twinkle
        a = k * math.pi / 4 + frame * 0.13
        r = 6 + (frame + k) % 2
        put(img, cx + round(r * math.cos(a)), cy + round(r * math.sin(a)), (255, 240, 150), 0.8)
    d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(255, 215, 70))
    d.ellipse([cx - 3, cy - 3, cx + 1, cy], fill=(255, 245, 170))  # glossy shine


def stars_and_moon(img, frame):
    rnd = random.Random(11)
    for _ in range(16):
        x, y, p = rnd.randrange(20, FRONT_W), rnd.randrange(11), rnd.random() * 6
        put(img, x, y, (255, 250, 210), 0.35 + 0.65 * abs(math.sin(frame / 2 + p)))
    d = ImageDraw.Draw(img)
    d.ellipse([60, 1, 69, 10], fill=(250, 240, 180))
    d.ellipse([62, 3, 64, 5], fill=(225, 215, 150))


def scene(key: str, frame: int) -> Image.Image:
    t = frame / SCENE_FRAMES
    if key == "clear_day":
        img = gradient((120, 215, 255), (0, 105, 210))
        sun(img, frame)
    elif key == "clear_night":
        img = gradient((4, 8, 40), (20, 40, 110), 0.08)
        stars_and_moon(img, frame)
    elif key == "partly_day":
        img = gradient((120, 215, 255), (0, 105, 210))
        sun(img, frame, 60, 4)
        cloud(img, round(26 + 30 * t) % 60 + 12, 2)
        cloud(img, round(50 + 30 * t) % 60 + 12, 8, alpha=0.8)
    elif key == "partly_night":
        img = gradient((4, 8, 40), (20, 40, 110), 0.08)
        stars_and_moon(img, frame)
        cloud(img, round(30 + 30 * t) % 60 + 12, 6, (120, 130, 170), 0.85)
    elif key == "cloudy":
        img = gradient((150, 175, 205), (70, 95, 140), 0.25)
        for i, (x0, y) in enumerate(((20, 1), (44, 6), (62, 2))):
            cloud(img, round(x0 + 60 * t + i * 7) % 66 + 10, y, alpha=0.85)
    elif key == "fog":
        img = gradient((185, 195, 210), (120, 135, 155), 0.3)
        for band in range(3):
            y = 3 + band * 4
            for x in range(20, FRONT_W):
                a = 0.35 + 0.25 * math.sin((x + frame * (2 + band)) / 5)
                put(img, x, y, (235, 240, 245), a)
                put(img, x, y + 1, (235, 240, 245), a * 0.6)
    elif key in ("rain", "storm"):
        dark = key == "storm"
        img = gradient((70, 90, 130) if dark else (110, 140, 180),
                       (25, 35, 70) if dark else (40, 70, 130), 0.15)
        cloud(img, 26, 0, (150, 160, 185) if dark else (205, 215, 230), 0.9)
        cloud(img, 50, -1, (150, 160, 185) if dark else (205, 215, 230), 0.9)
        rnd = random.Random(3)
        for _ in range(22):  # slanted drops falling
            x0, y0 = rnd.randrange(20, FRONT_W + 8), rnd.randrange(FRONT_H)
            y = (y0 + frame * 2) % (FRONT_H + 4) - 2
            x = x0 - (frame * 2) // 3 - y // 3
            for k in range(2):
                put(img, x - k, y + k, (170, 215, 255), 0.85)
        if dark and frame in (3, 4):  # lightning
            img = Image.blend(img, Image.new("RGB", img.size, (255, 255, 230)), 0.55 if frame == 3 else 0.2)
            bolt = [(44, 3), (43, 5), (45, 6), (43, 9), (44, 10), (42, 13)]
            for x, y in bolt:
                put(img, x, y, (255, 250, 150))
    elif key == "snow":
        img = gradient((170, 190, 220), (90, 115, 160), 0.3)
        rnd = random.Random(5)
        for _ in range(18):
            x0, y0, p = rnd.randrange(20, FRONT_W), rnd.randrange(FRONT_H), rnd.random() * 6
            y = (y0 + frame) % (FRONT_H + 2) - 1
            x = x0 + round(1.5 * math.sin(frame / 2 + p))
            put(img, x, y, (255, 255, 255), 0.95)
    else:
        img = gradient((120, 215, 255), (0, 105, 210))
    return img


# --------------------------------------------------------------------------
# Luca, dressed for the weather
# --------------------------------------------------------------------------
PALETTE = {
    "K": (28, 30, 44), "W": (255, 255, 255), "S": (190, 205, 230),
    "G": (150, 150, 158), "T": (40, 235, 175), "M": (8, 8, 12),
    "O": (245, 160, 80), "N": (225, 140, 115), "P": (255, 150, 160),
    "L": (25, 35, 80),      # sunglass lenses
    "U": (40, 235, 175),    # umbrella (mint, like his ear)
    "u": (170, 255, 225),   # umbrella shine
    "R": (225, 50, 70),     # cozy red scarf
    "r": (255, 120, 130),   # scarf stripe
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


def luca(outfit: str, frame: int) -> list[str]:
    rows = [list(r) for r in LUCA]
    if outfit in ("shades", "hot"):  # cool sunglasses with a glint
        rows[6][2:13] = "LLLLKKKLLLL"
        rows[7][2:13] = "LLLL...LLLL"
        rows[7][6:9] = "WWW" if False else rows[7][6:9]
        rows[7][6], rows[7][7], rows[7][8] = "W", "W", "M"
        rows[6][3 if frame % 2 else 4] = "W"
    if outfit == "hot":  # sweat drop and tongue out
        rows[2][15], rows[3][15], rows[4][15] = "B", "B", "B"
        rows[13][6:9] = "PPP"
        rows[14][6:9] = "KPK"
    if outfit == "sleepy":  # eyes closed, dozing
        rows[6][3:5], rows[7][3:5] = "WW", "KK"
        rows[6][10:12], rows[7][10:12] = "MM", "SS"
    if outfit == "scarf":  # a cozy red scarf with a tail
        rows[13] = list("...RrRrRrRR.....")
        rows[14] = list("....KWWWWWRR....")
        rows[15] = list(".....KKKKKRK....")
    if outfit == "umbrella":  # a mint umbrella over his head
        rows[0] = list("....UUuUUUU.....")
        rows[1] = list("..UUUUuUUUUUU...")
        rows[2] = list(".UUUUUUUUUUUUU..") if frame % 2 == 0 else list(".UuUUUUUUUUUUU..")
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


def tile(outfit: str, frame: int) -> Image.Image:
    img = glass_tile()
    bob = 1 if outfit == "sleepy" and frame % 2 else 0  # breathing while he dozes
    for y, row in enumerate(luca(outfit, frame)):
        for x, ch in enumerate(row):
            if ch != "." and 0 <= y + bob < FRONT_H:
                img.putpixel((x + 1, y + bob), PALETTE[ch] + (255,))
    return img


def outfit(report) -> str:
    c, cond = report.celsius, report.condition
    if cond in ("rain", "drizzle", "storm"):
        return "umbrella"
    if cond == "snow" or c <= 3:
        return "scarf"
    if report.is_day and cond in ("clear", "partly"):
        if c >= 28:
            return "hot"
        if c >= 15:
            return "shades"
    if not report.is_day:
        return "sleepy"
    return "plain"


# --------------------------------------------------------------------------
# The words on the strip
# --------------------------------------------------------------------------
WORDS = {"clear": ("SUNNY", "CLEAR"), "partly": ("PARTLY", "PARTLY"), "cloudy": ("CLOUDY",) * 2,
         "fog": ("FOGGY",) * 2, "drizzle": ("DRIZZLE",) * 2, "rain": ("RAIN",) * 2,
         "snow": ("SNOW",) * 2, "storm": ("STORM",) * 2}


def deg(t: float) -> str:
    return f"{t:.0f}°"


def page_texts(report) -> list[list[tuple[str, tuple]]]:
    """Each page is a list of (text, color) pieces, drawn left to right."""
    word = WORDS.get(report.condition, ("",) * 2)[0 if report.is_day else 1]
    now = deg(report.temp)
    pages = []
    if text_width(f"{now} {word}") <= TEXT_W:
        pages.append([(now, WHITE), (" " + word, MINT)])
    else:
        pages += [[(now, WHITE)], [(word, MINT)]]
    if report.days:
        today = report.days[0]
        pages.append([("H", MINT), (deg(today.high), WHITE), (" L", MINT), (deg(today.low), WHITE)])
        if today.rain_chance:
            label = "SNOW" if today.condition == "snow" else "RAIN"
            pages.append([(label + " ", MINT), (f"{today.rain_chance:.0f}%", WHITE)])
    if report.feels is not None and abs(report.feels - report.temp) >= 3:
        pages.append([("FEELS ", MINT), (deg(report.feels), WHITE)])
    city = to_font_text(report.place.name)
    while city and text_width(city) > TEXT_W:
        city = city[:-1]
    pages.append([(city, WHITE)])
    return pages


def page_image(pieces) -> Image.Image:
    total = text_width("".join(t for t, _ in pieces))
    img = Image.new("RGBA", (TEXT_W, 9), (0, 0, 0, 0))
    x = (TEXT_W - total) // 2
    for text, color in pieces:
        draw_text(img, to_font_text(text), x, 0, color=color)
        x += text_width(to_font_text(text)) + (1 if text and not text.endswith(" ") else 0)
        if text.endswith(" "):
            x += 1
    return img


# --------------------------------------------------------------------------
# Back screen: a Windows 7 weather gadget
# --------------------------------------------------------------------------
def icon(d: ImageDraw.ImageDraw, cond: str, is_day: bool, x: int, y: int, s: float = 1.0):
    """A little greyscale weather icon centred on (x, y)."""
    def r(v):
        return round(v * s)
    if cond in ("clear", "partly"):
        if is_day:
            for k in range(8):
                a = k * math.pi / 4
                d.line([(x + r(9) * math.cos(a), y + r(9) * math.sin(a)),
                        (x + r(12) * math.cos(a), y + r(12) * math.sin(a))], fill=60, width=max(1, r(2)))
            d.ellipse([x - r(7), y - r(7), x + r(7), y + r(7)], fill=90, outline=30)
            d.ellipse([x - r(5), y - r(5), x + r(1), y - r(1)], fill=200)
        else:
            d.ellipse([x - r(8), y - r(8), x + r(8), y + r(8)], fill=200, outline=60)
            d.ellipse([x - r(3), y - r(8), x + r(11), y + r(5)], fill=235)
    if cond != "clear" and cond != "fog":
        cx, cy = (x + r(3), y + r(4)) if cond == "partly" else (x, y)
        shade = 120 if cond in ("storm", "rain", "drizzle") else 180
        for ox, oy, rr in ((-6, 1, 6), (1, -3, 8), (8, 2, 5)):
            d.ellipse([cx + r(ox - rr), cy + r(oy - rr), cx + r(ox + rr), cy + r(oy + rr)],
                      fill=shade, outline=40)
        d.rectangle([cx + r(-6), cy + r(1), cx + r(8), cy + r(7)], fill=shade)
        d.line([(cx + r(-11), cy + r(7)), (cx + r(12), cy + r(7))], fill=40)
        if cond in ("rain", "drizzle", "storm"):
            for k in range(3):
                d.line([(cx + r(-5 + 6 * k), cy + r(10)), (cx + r(-7 + 6 * k), cy + r(15))], fill=30)
        if cond == "storm":
            d.polygon([(cx + r(1), cy + r(8)), (cx + r(-3), cy + r(15)), (cx, cy + r(14)),
                       (cx - r(2), cy + r(20)), (cx + r(4), cy + r(12)), (cx + r(1), cy + r(12))], fill=255)
        if cond == "snow":
            for k in range(3):
                px, py = cx + r(-5 + 6 * k), cy + r(12)
                d.text((px - 2, py - 4), "*", font=font(10), fill=30)
    if cond == "fog":
        for k in range(4):
            yy = y + r(-6 + 4 * k)
            d.line([(x + r(-11 + 2 * (k % 2)), yy), (x + r(11 - 2 * (k % 2)), yy)], fill=70, width=max(1, r(2)))


def back_screen(report, stale: bool = False) -> Image.Image:
    img = Image.new("L", (BACK_W, BACK_H), 0)
    d = ImageDraw.Draw(img)
    for y in range(BACK_H):  # desktop glow
        for x in range(BACK_W):
            img.putpixel((x, y), int(55 * max(0, 1 - math.hypot(x - 130, y - 10) / 150)))

    # the gadget: a rounded glass card with a glossy top half
    gx0, gy0, gx1, gy1 = 3, 2, 156, 77
    d.rounded_rectangle([gx0, gy0, gx1, gy1], radius=8, fill=150, outline=235)
    for y in range(gy0 + 2, gy0 + 34):
        d.line([(gx0 + 3, y), (gx1 - 3, y)], fill=int(215 - (y - gy0) * 2))
    d.line([(gx0 + 8, gy0 + 1), (gx1 - 8, gy0 + 1)], fill=250)

    # current weather
    icon(d, report.condition, report.is_day, gx0 + 22, gy0 + 20, 1.15)
    d.text((gx0 + 42, gy0 + 3), f"{report.temp:.0f}°", font=font(26), fill=10)
    tx = gx0 + 92
    d.text((tx, gy0 + 4), fit(d, report.place.name, font(11), gx1 - tx - 4), font=font(11), fill=0)
    d.text((tx, gy0 + 17), fit(d, weather.describe(report.condition, report.is_day), font(9),
                               gx1 - tx - 4), font=font(9), fill=40)
    extra = []
    if report.feels is not None:
        extra.append(f"Feels {report.feels:.0f}°")
    if report.humidity is not None:
        extra.append(f"{report.humidity:.0f}%")
    d.text((tx, gy0 + 28), "  ".join(extra), font=font(8), fill=60)

    # forecast strip: the next three days
    fy = gy0 + 40
    d.line([(gx0 + 6, fy - 2), (gx1 - 6, fy - 2)], fill=200)
    days = report.days[1:4] or report.days[:3]
    col = (gx1 - gx0 - 8) / max(len(days), 1)
    for i, day in enumerate(days):
        cx = round(gx0 + 4 + col * i + col / 2)
        name = date.fromisoformat(day.date).strftime("%a")
        d.text((cx, fy), name, font=font(9), fill=20, anchor="ma")
        icon(d, day.condition, True, cx - 14, fy + 19, 0.55)
        d.text((cx + 2, fy + 13), f"{day.high:.0f}°", font=font(9), fill=0)
        d.text((cx + 2, fy + 23), f"{day.low:.0f}°", font=font(9), fill=80)
    if stale:
        d.text((gx1 - 6, gy1 - 3), "offline", font=font(8), fill=70, anchor="rb")
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
def compose(report, frame: int, page: int = 0) -> Image.Image:
    out = scene(scene_key(report.condition, report.is_day), frame).convert("RGBA")
    pages = page_texts(report)
    out.alpha_composite(page_image(pages[page % len(pages)]), (TEXT_X, TEXT_Y))
    out.alpha_composite(tile(outfit(report), frame // 3), (0, 0))
    return out.convert("RGB")


def main() -> None:
    preview = HERE / "preview"
    preview.mkdir(exist_ok=True)
    frames = []
    for step in range(len(weather.DEMO_TOUR)):
        rep = weather.demo(step)
        for f in range(12):
            frames.append(led_preview(compose(rep, f, f // 6), 8))
    frames[0].save(preview / "front.gif", save_all=True, append_images=frames[1:],
                   duration=150, loop=0, optimize=True)
    back_screen(weather.demo(1)).resize((BACK_W * 4, BACK_H * 4), Image.NEAREST) \
        .save(preview / "back.png")
    sheet = Image.new("RGB", (len(OUTFITS) * (TILE_W * 8 + 8), FRONT_H * 8), (40, 40, 40))
    for k, o in enumerate(OUTFITS):
        sheet.paste(led_preview(tile(o, 0).convert("RGB"), 8), (k * (TILE_W * 8 + 8), 0))
    sheet.save(preview / "outfits.png")
    print(f"Wrote previews to {preview}")


if __name__ == "__main__":
    main()
