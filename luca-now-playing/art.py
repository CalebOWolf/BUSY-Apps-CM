"""
Artwork for Luca Now Playing: everything is drawn with Pillow.

Static pieces (uploaded once):
  bg_NN.png          72x16 glossy Aero sky with drifting bubbles
  tile_<pose>_N.png  19x16 glass tile with Luca in headphones
Per song (uploaded when the song or play state changes):
  a text strip       the scrolling "TITLE - ARTIST" in pixel letters
  a back screen      a 160x80 "Luca Player" Aero media window

    python art.py      # writes previews into preview/
"""

from __future__ import annotations

import math
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).parent
PORTRAIT = HERE / "assets" / "luca_small.png"

FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80
TILE_W = 19                      # Luca's glass tile; text slides under it
TEXT_X, TEXT_Y = 20, 4          # where the song text sits on the strip
TEXT_W = FRONT_W - TEXT_X       # visible text width
BAR_Y = 14                      # progress bar row on the strip
BG_FRAMES = 12
GAP = "   ♪   "                 # between repeats of a scrolling title

# --------------------------------------------------------------------------
# Pixel font (5x7, uppercase): crisp on a 16-pixel-tall LED strip
# --------------------------------------------------------------------------
_FONT_SRC = {
    "A": ".XXX. X...X X...X XXXXX X...X X...X X...X",
    "B": "XXXX. X...X X...X XXXX. X...X X...X XXXX.",
    "C": ".XXXX X.... X.... X.... X.... X.... .XXXX",
    "D": "XXXX. X...X X...X X...X X...X X...X XXXX.",
    "E": "XXXXX X.... X.... XXXX. X.... X.... XXXXX",
    "F": "XXXXX X.... X.... XXXX. X.... X.... X....",
    "G": ".XXXX X.... X.... X.XXX X...X X...X .XXXX",
    "H": "X...X X...X X...X XXXXX X...X X...X X...X",
    "I": "XXX .X. .X. .X. .X. .X. XXX",
    "J": "..XXX ...X. ...X. ...X. ...X. X..X. .XX..",
    "K": "X...X X..X. X.X.. XX... X.X.. X..X. X...X",
    "L": "X.... X.... X.... X.... X.... X.... XXXXX",
    "M": "X...X XX.XX X.X.X X.X.X X...X X...X X...X",
    "N": "X...X XX..X X.X.X X..XX X...X X...X X...X",
    "O": ".XXX. X...X X...X X...X X...X X...X .XXX.",
    "P": "XXXX. X...X X...X XXXX. X.... X.... X....",
    "Q": ".XXX. X...X X...X X...X X.X.X X..X. .XX.X",
    "R": "XXXX. X...X X...X XXXX. X.X.. X..X. X...X",
    "S": ".XXXX X.... X.... .XXX. ....X ....X XXXX.",
    "T": "XXXXX ..X.. ..X.. ..X.. ..X.. ..X.. ..X..",
    "U": "X...X X...X X...X X...X X...X X...X .XXX.",
    "V": "X...X X...X X...X X...X X...X .X.X. ..X..",
    "W": "X...X X...X X...X X.X.X X.X.X XX.XX X...X",
    "X": "X...X X...X .X.X. ..X.. .X.X. X...X X...X",
    "Y": "X...X X...X .X.X. ..X.. ..X.. ..X.. ..X..",
    "Z": "XXXXX ....X ...X. ..X.. .X... X.... XXXXX",
    "0": ".XXX. X...X X..XX X.X.X XX..X X...X .XXX.",
    "1": ".X. XX. .X. .X. .X. .X. XXX",
    "2": ".XXX. X...X ....X ...X. ..X.. .X... XXXXX",
    "3": "XXXX. ....X ....X .XXX. ....X ....X XXXX.",
    "4": "...X. ..XX. .X.X. X..X. XXXXX ...X. ...X.",
    "5": "XXXXX X.... XXXX. ....X ....X X...X .XXX.",
    "6": ".XXX. X.... X.... XXXX. X...X X...X .XXX.",
    "7": "XXXXX ....X ...X. ..X.. .X... .X... .X...",
    "8": ".XXX. X...X X...X .XXX. X...X X...X .XXX.",
    "9": ".XXX. X...X X...X .XXXX ....X ....X .XXX.",
    ".": ". . . . . . X",
    ",": ". . . . . X X",
    "!": "X X X X X . X",
    "?": ".XXX. X...X ....X ...X. ..X.. ..... ..X..",
    "'": "X X . . . . .",
    '"': "X.X X.X ... ... ... ... ...",
    "-": "... ... ... XXX ... ... ...",
    "&": ".XX.. X..X. .XX.. .X... X.X.X X..X. .XX.X",
    "(": ".X X. X. X. X. X. .X",
    ")": "X. .X .X .X .X .X X.",
    ":": ". X . . . X .",
    "/": "....X ...X. ...X. ..X.. .X... .X... X....",
    "+": "..... ..X.. ..X.. XXXXX ..X.. ..X.. .....",
    "#": ".X.X. XXXXX .X.X. .X.X. .X.X. XXXXX .X.X.",
    "@": ".XXX. X...X X.XXX X.X.X X.XXX X.... .XXXX",
    "*": "..... X.X.X .XXX. XXXXX .XXX. X.X.X .....",
    "_": "..... ..... ..... ..... ..... ..... XXXXX",
    "♪": "..XX. ..X.X ..X.. ..X.. XXX.. XXX.. .....",
}
GLYPHS = {ch: src.split() for ch, src in _FONT_SRC.items()}
SPACE_W = 3


def to_font_text(text: str) -> str:
    """Fold accents away and upper-case; anything the font lacks becomes '?'."""
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(c for c in folded if not unicodedata.combining(c)).upper()
    folded = folded.replace("—", "-").replace("–", "-").replace("’", "'").replace("‘", "'")
    folded = folded.replace("“", '"').replace("”", '"')
    return "".join(c if (c == " " or c in GLYPHS) else "?" for c in folded)


def text_width(text: str) -> int:
    w = 0
    for ch in text:
        w += SPACE_W if ch == " " else len(GLYPHS[ch][0]) + 1
    return max(w - 1, 0)


def draw_text(img: Image.Image, text: str, x: int, y: int,
              color=(255, 255, 255, 255), shadow=(0, 30, 90, 255)) -> None:
    px = img.load()
    for pass_, (dx, dy) in enumerate([(1, 1), (0, 0)]):
        cx = x
        for ch in text:
            if ch == " ":
                cx += SPACE_W
                continue
            for gy, row in enumerate(GLYPHS[ch]):
                for gx, on in enumerate(row):
                    X, Y = cx + gx + dx, y + gy + dy
                    if on == "X" and 0 <= X < img.width and 0 <= Y < img.height:
                        if pass_ == 0:
                            px[X, Y] = shadow
                        else:
                            px[X, Y] = (120, 255, 200, 255) if ch == "♪" else color
            cx += len(GLYPHS[ch][0]) + 1


def text_strip(text: str, dim: bool = False) -> tuple[Image.Image, int]:
    """
    The song text as a transparent strip, 9 pixels tall (letters + shadow).
    Long text is repeated after a gap so it can scroll seamlessly; the second
    value is how far to scroll before it loops (0 means it fits, no scroll).
    """
    text = to_font_text(text)
    w = text_width(text)
    color = (170, 200, 230, 255) if dim else (255, 255, 255, 255)
    if w <= TEXT_W:
        img = Image.new("RGBA", (TEXT_W, 9), (0, 0, 0, 0))
        draw_text(img, text, (TEXT_W - w) // 2, 0, color)
        return img, 0
    loop = text_width(text + GAP) + 1
    full = text + GAP + text
    img = Image.new("RGBA", (text_width(full) + 2, 9), (0, 0, 0, 0))
    draw_text(img, full, 0, 0, color)
    return img, loop


# --------------------------------------------------------------------------
# Luca with headphones
# --------------------------------------------------------------------------
PALETTE = {
    "K": (28, 30, 44), "W": (255, 255, 255), "S": (190, 205, 230),
    "G": (150, 150, 158), "T": (40, 235, 175), "M": (8, 8, 12),
    "O": (245, 160, 80), "N": (225, 140, 115), "P": (255, 150, 160),
    "H": (60, 70, 95),      # headphone band
    "C": (40, 235, 175),    # mint ear cups (to match his ear)
}
LUCA = [
    "KK...........KK.",
    "KGKHHHHHHHHHKTK.",
    "KGHKKKKKKKKKHTK.",
    "KGWWWWWWWWWWWTK.",
    "CWWWWWWWWWWWWWC.",
    "CWWWWWWWWMMMMWC.",
    "CWWOOWWWMMOOMWC.",
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
EYES = {
    "open":   (("OO", "OK"), ("OO", "OK")),
    "closed": (("WW", "KK"), ("MM", "SS")),
    "happy":  (("KK", "WW"), ("SS", "MM")),
}


def luca(eyes: str = "open") -> list[str]:
    rows = [list(r) for r in LUCA]
    (l6, l7), (r6, r7) = EYES[eyes]
    rows[6][3:5], rows[7][3:5] = l6, l7
    rows[6][10:12], rows[7][10:12] = r6, r7
    return ["".join(r) for r in rows]


def lerp(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def glass_tile() -> Image.Image:
    """A 19x16 glossy Aero glass tile for Luca to sit on."""
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
    if pose == "play":    # bopping to the beat, a note floats up
        bob, eyes = (0, 1, 0, 1)[frame % 4], ("open", "open", "happy", "open")[frame % 4]
    elif pose == "hop":   # skipped a song: a happy hop
        bob, eyes = (0, -1, -2, -1)[frame % 4], "happy"
    elif pose == "pause":
        bob, eyes = 0, "open"
    else:                 # idle: nothing playing, Luca dozes in his headphones
        bob, eyes = 1, "closed"
    for y, row in enumerate(luca(eyes)):
        for x, ch in enumerate(row):
            if ch != "." and 0 <= y + bob < FRONT_H:
                img.putpixel((x + 1, y + bob), PALETTE[ch] + (255,))
    return img


TILE_POSES = {"play": 4, "hop": 4, "pause": 1, "idle": 1}


# --------------------------------------------------------------------------
# Volume pop-up (shown for a moment when the wheel turns)
# --------------------------------------------------------------------------
VOL_PANEL = (TILE_W, 0, FRONT_W - TILE_W, FRONT_H)   # x, y, w, h: covers the text area
VOL_BAR = (31, 6, 38, 4)                             # x, y, w, h of the level bar
SPEAKER = [
    "...X....",
    "..XX.X..",
    "XXXX..X.",
    "XXXX..X.",
    "XXXX..X.",
    "..XX.X..",
    "...X....",
]


def volume_icon() -> Image.Image:
    """A little white speaker with a drop shadow."""
    img = Image.new("RGBA", (10, 8), (0, 0, 0, 0))
    for y, row in enumerate(SPEAKER):
        for x, ch in enumerate(row):
            if ch == "X":
                img.putpixel((x + 1, y + 1), (0, 30, 90, 255))  # shadow
    for y, row in enumerate(SPEAKER):
        for x, ch in enumerate(row):
            if ch == "X":
                img.putpixel((x, y), (255, 255, 255, 255))
    return img


def volume_sign(up: bool) -> Image.Image:
    """A mint + or -, for when the volume level can't be read."""
    img = Image.new("RGBA", (7, 7), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line([(0, 3), (6, 3)], fill=(120, 255, 200, 255))
    if up:
        d.line([(3, 0), (3, 6)], fill=(120, 255, 200, 255))
    return img


# --------------------------------------------------------------------------
# Background sky
# --------------------------------------------------------------------------
BUBBLES = [(26, 1.0, 0.0, 1), (35, 0.7, 5.0, 2), (46, 1.2, 9.0, 1),
           (54, 0.8, 2.0, 2), (63, 1.1, 12.0, 1), (69, 0.6, 7.0, 1)]


def background(frame: int) -> Image.Image:
    img = Image.new("RGB", (FRONT_W, FRONT_H))
    d = ImageDraw.Draw(img)
    for y in range(FRONT_H):
        c = lerp((120, 215, 255), (0, 95, 200), y / (FRONT_H - 1))
        if y < FRONT_H // 2:
            c = lerp(c, (255, 255, 255), 0.35 * (1 - y / (FRONT_H / 2)))
        d.line([(0, y), (FRONT_W - 1, y)], fill=c)
    span = FRONT_H + 6
    for bx, speed, phase, r in BUBBLES:
        p = (phase + frame / BG_FRAMES * speed * span) % span
        x, y = bx + round(math.sin((p + phase) / 3)), round(FRONT_H + 2 - p)
        if r == 1:
            for X, Y in [(x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1)]:
                if 0 <= X < FRONT_W and 0 <= Y < FRONT_H:
                    img.putpixel((X, Y), lerp(img.getpixel((X, Y)), (230, 250, 255), 0.45))
        else:
            d.ellipse([x - r, y - r, x + r, y + r], outline=(200, 235, 255))
        if 0 <= x < FRONT_W and 0 <= y - 1 < FRONT_H:
            img.putpixel((x, y - 1), (255, 255, 255))
    return img


# --------------------------------------------------------------------------
# Back screen: "Luca Player", an Aero media player window
# --------------------------------------------------------------------------
# Progress bar geometry on the back screen (the fill is drawn live by the bar).
BACK_BAR = (52, 57, 149, 59)  # x0, y0, x1, y1
BACK_TIME_XY = (150, 63)      # right edge of the time text


def font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def fit(d: ImageDraw.ImageDraw, text: str, f, width: int) -> str:
    if d.textlength(text, font=f) <= width:
        return text
    while text and d.textlength(text + "…", font=f) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def back_screen(title: str, artist: str, album: str, playing: bool,
                cover: Image.Image | None = None) -> Image.Image:
    img = Image.new("L", (BACK_W, BACK_H), 0)
    d = ImageDraw.Draw(img)
    for y in range(BACK_H):  # desktop glow
        for x in range(BACK_W):
            img.putpixel((x, y), int(60 * max(0, 1 - math.hypot(x - 30, y - 70) / 150)))

    wx0, wy0, wx1, wy1 = 2, 1, 157, 78
    d.rounded_rectangle([wx0, wy0, wx1, wy1], radius=5, fill=120, outline=230)
    for y in range(wy0 + 1, wy0 + 13):
        d.line([(wx0 + 2, y), (wx1 - 2, y)], fill=int(205 - (y - wy0) * 6))
    for sx in (60, 68, 120):
        d.line([(sx, wy0 + 1), (sx + 10, wy0 + 12)], fill=235)
    d.text((wx0 + 14, wy0), "Luca Player", font=font(10), fill=20)
    # a little music note icon
    d.ellipse([wx0 + 4, wy0 + 6, wx0 + 7, wy0 + 9], fill=20)
    d.line([(wx0 + 7, wy0 + 2), (wx0 + 7, wy0 + 8)], fill=20)
    d.line([(wx0 + 7, wy0 + 2), (wx0 + 10, wy0 + 3)], fill=20)
    bx = wx1 - 46  # caption buttons
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

    # client area
    cx0, cy0, cx1, cy1 = wx0 + 3, wy0 + 14, wx1 - 3, wy1 - 3
    d.rectangle([cx0, cy0, cx1, cy1], fill=235, outline=60)

    # album art, or Luca's portrait when the song has none
    if cover is not None:
        src = Image.alpha_composite(Image.new("RGBA", cover.size, "white"), cover.convert("RGBA"))
        art = ImageOps.autocontrast(ImageOps.fit(src.convert("L"), (36, 36), Image.LANCZOS), cutoff=1)
    else:
        art = Image.open(PORTRAIT).convert("L").resize((36, 36), Image.LANCZOS)
    img.paste(art, (cx0 + 3, cy0 + 3))
    d.rectangle([cx0 + 2, cy0 + 2, cx0 + 39, cy0 + 39], outline=40)

    tx, tw = cx0 + 44, cx1 - (cx0 + 44) - 3
    d.text((tx, cy0 + 2), fit(d, title or "Nothing playing", font(12), tw), font=font(12), fill=0)
    d.text((tx, cy0 + 17), fit(d, artist, font(9), tw), font=font(9), fill=50)
    d.text((tx, cy0 + 27), fit(d, album, font(9), tw), font=font(9), fill=90)

    # progress track (the fill is drawn on top by the app as it plays)
    x0, y0, x1, y1 = BACK_BAR
    d.rounded_rectangle([x0 - 1, y0 - 1, x1 + 1, y1 + 1], radius=2, fill=200, outline=70)

    # transport: previous, the big glossy play/pause orb, next
    oy, ox = cy1 - 8, cx0 + 21
    for dx in (-14, 14):  # small buttons
        d.ellipse([ox + dx - 5, oy - 5, ox + dx + 5, oy + 5], fill=190, outline=50)
    for k, s in ((-1, -14), (1, 14)):  # ⏮ ⏭ triangles
        cx = ox + s
        pts = [(cx - 3 * k, oy - 3), (cx - 3 * k, oy + 3), (cx + 2 * k, oy)]
        d.polygon(pts, fill=30)
        d.line([(cx + 3 * k, oy - 3), (cx + 3 * k, oy + 3)], fill=30)
    d.ellipse([ox - 7, oy - 7, ox + 7, oy + 7], fill=110, outline=20)
    d.chord([ox - 6, oy - 6, ox + 6, oy + 6], 180, 360, fill=170)  # glass shine
    if playing:  # show pause bars while it plays
        d.rectangle([ox - 3, oy - 4, ox - 1, oy + 4], fill=255)
        d.rectangle([ox + 1, oy - 4, ox + 3, oy + 4], fill=255)
    else:
        d.polygon([(ox - 2, oy - 4), (ox - 2, oy + 4), (ox + 4, oy)], fill=255)

    return img.point(lambda v: (v // 17) * 17)


# --------------------------------------------------------------------------
# Previews (what the strip looks like, composed the way the bar draws it)
# --------------------------------------------------------------------------
def compose_front(bg: Image.Image, strip: Image.Image, offset: int, tile_img: Image.Image,
                  progress: float | None) -> Image.Image:
    out = bg.convert("RGBA")
    out.alpha_composite(strip.crop((offset, 0, offset + TEXT_W, 9)), (TEXT_X, TEXT_Y))
    out.alpha_composite(tile_img, (0, 0))
    if progress is not None:
        d = ImageDraw.Draw(out)
        d.line([(TEXT_X, BAR_Y), (FRONT_W - 1, BAR_Y)], fill=(10, 50, 120))
        w = round(TEXT_W * progress)
        if w:
            d.line([(TEXT_X, BAR_Y), (TEXT_X + w - 1, BAR_Y)], fill=(120, 255, 200))
    return out.convert("RGB")


def led_preview(frame: Image.Image, scale: int = 10) -> Image.Image:
    w, h = frame.size
    out = Image.new("RGB", (w * scale, h * scale), (10, 10, 14))
    d = ImageDraw.Draw(out)
    for y in range(h):
        for x in range(w):
            d.ellipse([x * scale + 1, y * scale + 1, x * scale + scale - 2,
                       y * scale + scale - 2], fill=frame.getpixel((x, y)))
    return out


def main() -> None:
    preview = HERE / "preview"
    preview.mkdir(exist_ok=True)
    strip, loop = text_strip("Bubble Skies - Luca Wood")
    frames = []
    for i in range(0, loop + 1, 2):
        f = compose_front(background(i // 2 % BG_FRAMES), strip, i,
                          tile("play", i // 4), 0.2 + 0.4 * i / loop)
        frames.append(led_preview(f))
    frames[0].save(preview / "front.gif", save_all=True, append_images=frames[1:],
                   duration=140, loop=0)
    back = back_screen("Bubble Skies", "Luca Wood", "Frutiger Dreams", True)
    d = ImageDraw.Draw(back)
    x0, y0, x1, y1 = BACK_BAR
    d.rectangle([x0, y0, x0 + int((x1 - x0) * 0.45), y1], fill=90)
    d.text((BACK_TIME_XY[0], BACK_TIME_XY[1]), "1:24 / 3:07", font=font(9), fill=40, anchor="ra")
    back.resize((BACK_W * 4, BACK_H * 4), Image.NEAREST).save(preview / "back.png")
    paused = compose_front(background(0), text_strip("Bubble Skies - Luca Wood", dim=True)[0],
                           0, tile("pause", 0), 0.45)
    led_preview(paused).save(preview / "paused.png")
    print(f"Wrote previews to {preview}")


if __name__ == "__main__":
    main()
