"""
Pixel art helpers shared by every app in this repo.

  GLYPHS, draw_text(), text_width(), to_font_text()
                 a crisp 5x7 uppercase pixel font for the 16-pixel LED strip
  lerp()         blend two colors
  aero_sky()     a glossy Aero sky gradient
  ui_font()      a small smooth font for the back screen
  led_preview()  upscale a frame as round LEDs, for previews
"""

from __future__ import annotations

import unicodedata

from PIL import Image, ImageDraw, ImageFont

# 5x7 pixel font (uppercase)
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
    "%": "XX..X XX..X ...X. ..X.. .X... X..XX X..XX",
    "°": ".X. X.X .X. ... ... ... ...",
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



def lerp(a, b, t):
    """Blend color a toward b by t (0..1)."""
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def aero_sky(w: int, h: int, top=(120, 215, 255), bottom=(0, 95, 200),
             shine: float = 0.35) -> Image.Image:
    """A Frutiger Aero sky: a blue gradient with a glassy highlight on the top half."""
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        c = lerp(top, bottom, y / max(h - 1, 1))
        if y < h // 2:
            c = lerp(c, (255, 255, 255), shine * (1 - y / (h / 2)))
        d.line([(0, y), (w - 1, y)], fill=c)
    return img


def ui_font(size: int):
    """Pillow's built-in font at a size (fine for the 16-grey back screen)."""
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def led_preview(frame: Image.Image, scale: int = 10) -> Image.Image:
    """Upscale a front-strip frame as round LEDs, roughly how it looks on the bar."""
    frame = frame.convert("RGB")
    w, h = frame.size
    out = Image.new("RGB", (w * scale, h * scale), (10, 10, 14))
    d = ImageDraw.Draw(out)
    for y in range(h):
        for x in range(w):
            d.ellipse([x * scale + 1, y * scale + 1, x * scale + scale - 2,
                       y * scale + scale - 2], fill=frame.getpixel((x, y)))
    return out
