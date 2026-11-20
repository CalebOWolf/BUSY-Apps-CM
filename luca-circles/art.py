"""
Artwork for Luca Circles, drawn with Pillow. All original pixel art, in this
repo's Frutiger Aero style.

Uploaded once:
  bg_<mood>_N.png     72x16 glossy backgrounds with rings rippling out:
                      violet-to-magenta while you play, a red flash on a
                      miss, gold on the results screen, soft lavender in the
                      menus
  tile_<pose>_N.png   19x16 pink glass tile with Luca: focused, ouch (a miss),
                      cheering, chilling
  ch_<c>_<color>.png  digits, ".", "%" and "X" in white and soft pink, so the
                      combo and accuracy change without uploading anything
When it changes:
  the text line       the song, or your rank on the results screen
  the back screen     "Luca Circles", a Windows 7-style window with the map
                      and your play

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
TEXT_Y = 2
COMBO_X = AREA_X + 1
BAR_Y = 13
BG_FRAMES = 8
MOODS = {  # top, bottom, ring color
    "play": ((150, 90, 255), (200, 20, 140), (255, 200, 245)),
    "miss": ((255, 90, 90), (140, 0, 30), (255, 200, 200)),
    "results": ((255, 220, 110), (200, 110, 0), (255, 250, 210)),
    "menu": ((220, 170, 255), (150, 80, 210), (255, 235, 255)),
}
POSES = {"focus": 2, "miss": 1, "cheer": 2, "chill": 2}
CHARS = "0123456789.%X"
COLORS = {"w": (255, 255, 255, 255), "p": (255, 190, 235, 255)}
SHADOW = (60, 0, 50, 255)
GAP = "     "
LED_RESULTS = "#FFD040FF"
GOOD_RANKS = {"S", "SH", "X", "XH", "SS", "SSH"}


# --------------------------------------------------------------------------
# Backgrounds with rippling rings
# --------------------------------------------------------------------------
RINGS = ((33, 8, 0), (52, 7, 3), (66, 9, 6))  # centre x, y, phase (frames)


def bg(mood: str, frame: int) -> Image.Image:
    top, bottom, ring = MOODS[mood]
    img = Image.new("RGBA", (FRONT_W, FRONT_H))
    d = ImageDraw.Draw(img)
    for y in range(FRONT_H):
        c = lerp(top, bottom, y / (FRONT_H - 1))
        if y < 7:
            c = lerp(c, (255, 255, 255), 0.35 * (1 - y / 7))  # glossy top
        d.line([(0, y), (FRONT_W - 1, y)], fill=c + (255,))
    glow = Image.new("RGBA", (FRONT_W, FRONT_H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for cx, cy, phase in RINGS:
        t = ((frame + phase) % BG_FRAMES) / BG_FRAMES     # 0 → 1 as the ring grows
        r = 1 + t * 8
        alpha = int(150 * (1 - t))
        g.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ring + (alpha,))
        if t < 0.3:  # a bright little "hit" in the middle as it starts
            g.ellipse([cx - 1, cy - 1, cx + 1, cy + 1], fill=ring + (int(200 * (1 - t / 0.3)),))
    img.alpha_composite(glow)
    d = ImageDraw.Draw(img)
    d.rectangle([AREA_X - 1, 0, FRONT_W - 1, FRONT_H - 1], outline=lerp(top, (255, 255, 255), 0.6) + (255,))
    return img.convert("RGB")


# --------------------------------------------------------------------------
# Luca
# --------------------------------------------------------------------------
PALETTE = {
    "K": (28, 30, 44), "W": (255, 255, 255), "S": (190, 205, 230),
    "G": (150, 150, 158), "T": (40, 235, 175), "M": (8, 8, 12),
    "O": (245, 160, 80), "N": (225, 140, 115), "P": (255, 150, 160),
    "B": (120, 210, 255),   # a little tear
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
    if pose == "focus":  # narrowed, determined eyes
        rows[6][3:5], rows[7][3:5] = "KK", "WW"
        rows[6][10:12], rows[7][10:12] = "KK", "MM"
        if frame % 2:
            rows[5][3:5] = "KK"  # a focused brow
    elif pose == "miss":  # >_<
        rows[6][3:5], rows[7][3:5] = "KW", "WK"
        rows[6][10:12], rows[7][10:12] = "MK", "KM"
        rows[8][3] = "B"
        rows[12][6:9] = "KKK"
    elif pose in ("cheer", "chill"):  # ^^
        rows[6][3:5], rows[7][3:5] = "KK", "WW"
        rows[6][10:12], rows[7][10:12] = "SS", "MM"
        if pose == "cheer" and frame % 2:
            rows[12][6:9] = "PPP"
    return ["".join(r) for r in rows]


def glass_tile() -> Image.Image:
    img = Image.new("RGBA", (TILE_W, FRONT_H))
    d = ImageDraw.Draw(img)
    for y in range(FRONT_H):
        c = lerp((255, 170, 230), (170, 40, 150), y / (FRONT_H - 1))  # pink glass
        if y < FRONT_H // 2:
            c = lerp(c, (255, 255, 255), 0.45 * (1 - y / (FRONT_H / 2)))
        d.line([(0, y), (TILE_W - 1, y)], fill=c + (255,))
    d.line([(TILE_W - 1, 0), (TILE_W - 1, FRONT_H - 1)], fill=(255, 225, 250, 255))
    return img


def tile(pose: str, frame: int) -> Image.Image:
    img = glass_tile()
    bounce = 1 if pose == "cheer" and frame % 2 else 0
    for y, row in enumerate(luca(pose, frame)):
        for x, ch in enumerate(row):
            if ch != "." and 0 <= y - bounce < FRONT_H:
                img.putpixel((x + 1, y - bounce), PALETTE[ch] + (255,))
    return img


# --------------------------------------------------------------------------
# Numbers and text
# --------------------------------------------------------------------------
def char_name(ch: str) -> str:
    return {".": "dot", "%": "pct"}.get(ch, ch)


def char(ch: str, color: str) -> Image.Image:
    img = Image.new("RGBA", (len(GLYPHS[ch][0]) + 2, 9), (0, 0, 0, 0))
    draw_text(img, ch, 0, 0, color=COLORS[color], shadow=SHADOW)
    return img


def char_width(ch: str) -> int:
    return len(GLYPHS[ch][0]) + 1


def accuracy_text(acc: float) -> str:
    """For the back screen: 98.91%."""
    return f"{acc:.2f}%" if acc < 100 else "100%"


def width(text: str) -> int:
    return sum(char_width(c) for c in text) - 1


def play_texts(combo: int, acc: float) -> tuple[str, str]:
    """The combo and accuracy for the front, squeezed to fit side by side:
    412X  98.9%, then 1234X  98.9, then 12345X  99."""
    combo_t = f"{combo}X"
    room = (FRONT_W - 2) - COMBO_X + 1 - width(combo_t) - 2
    for acc_t in (f"{acc:.1f}%" if acc < 100 else "100%",
                  f"{acc:.1f}" if acc < 100 else "100", f"{int(acc)}"):
        if width(acc_t) <= room:
            return combo_t, acc_t
    return combo_t, ""


def text_strip(text: str, color: str = "w") -> tuple[Image.Image, int]:
    text = to_font_text(text)
    w = text_width(text)
    if w <= AREA_W - 2:
        img = Image.new("RGBA", (AREA_W, 9), (0, 0, 0, 0))
        draw_text(img, text, (AREA_W - w) // 2, 0, color=COLORS[color], shadow=SHADOW)
        return img, 0
    loop = text_width(text + GAP)
    img = Image.new("RGBA", (loop + w + 2, 9), (0, 0, 0, 0))
    draw_text(img, text, 0, 0, color=COLORS[color], shadow=SHADOW)
    draw_text(img, text, loop, 0, color=COLORS[color], shadow=SHADOW)
    return img, loop


def rank_label(rank: str) -> str:
    """osu!'s rank letters, as players say them: X → SS, XH → SS (silver)."""
    r = rank.upper()
    return {"X": "SS", "XH": "SS", "SH": "S"}.get(r, r)


# --------------------------------------------------------------------------
# Back screen: "Luca Circles"
# --------------------------------------------------------------------------
def back_screen(live, basic: bool) -> Image.Image:
    img = Image.new("L", (BACK_W, BACK_H), 0)
    d = ImageDraw.Draw(img)
    for y in range(BACK_H):
        for x in range(BACK_W):
            img.putpixel((x, y), int(55 * max(0, 1 - math.hypot(x - 30, y - 10) / 150)))
    wx0, wy0, wx1, wy1 = 2, 1, 157, 78
    d.rounded_rectangle([wx0, wy0, wx1, wy1], radius=5, fill=120, outline=230)
    for y in range(wy0 + 1, wy0 + 13):
        d.line([(wx0 + 2, y), (wx1 - 2, y)], fill=int(205 - (y - wy0) * 6))
    for sx in (60, 68, 124):
        d.line([(sx, wy0 + 1), (sx + 10, wy0 + 12)], fill=235)
    d.ellipse([wx0 + 4, wy0 + 2, wx0 + 10, wy0 + 8], outline=20)    # a little ring icon
    d.ellipse([wx0 + 6, wy0 + 4, wx0 + 8, wy0 + 6], fill=20)
    d.text((wx0 + 15, wy0), "Luca Circles", font=font(10), fill=20)
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

    if basic or live is None:
        d.text(((cx0 + cx1) // 2, cy0 + 14), "osu! is open", font=font(13), fill=0, anchor="mm")
        d.text(((cx0 + cx1) // 2, cy0 + 34), "Run tosu for live combo,", font=font(9), fill=60, anchor="mm")
        d.text(((cx0 + cx1) // 2, cy0 + 44), "accuracy and the map", font=font(9), fill=60, anchor="mm")
        return img.point(lambda v: (v // 17) * 17)

    d.text((cx0 + 4, cy0 + 1), fit(d, live.title or "osu!", font(11), cx1 - cx0 - 8), font=font(11), fill=0)
    sub = live.artist + (f"  [{live.version}]" if live.version else "")
    d.text((cx0 + 4, cy0 + 13), fit(d, sub, font(8), cx1 - cx0 - 40), font=font(8), fill=60)
    if live.stars:
        d.text((cx1 - 4, cy0 + 13), f"{live.stars:.2f}*", font=font(8), fill=40, anchor="ra")

    if live.state in ("play", "results"):
        y = cy0 + 25
        if live.state == "results" and live.rank:
            d.rounded_rectangle([cx0 + 4, y, cx0 + 30, y + 22], radius=4, fill=40)
            d.text((cx0 + 17, y + 11), rank_label(live.rank), font=font(14), fill=255, anchor="mm")
            tx = cx0 + 36
        else:
            tx = cx0 + 4
        d.text((tx, y), f"{live.combo if live.state == 'play' else live.max_combo}x", font=font(12), fill=0)
        d.text((tx + 48, y), accuracy_text(live.accuracy), font=font(12), fill=0)
        d.text((tx, y + 13), f"300 {live.h300}  100 {live.h100}  50 {live.h50}  miss {live.misses}",
               font=font(8), fill=50)
        if live.pp:
            d.text((cx1 - 4, cy1 - 1), f"{live.pp:.0f}pp", font=font(10), fill=0, anchor="rd")
        if live.state == "play" and live.length_ms:
            bx0, bx1, by = cx0 + 4, cx1 - 44, cy1 - 5
            d.rectangle([bx0, by, bx1, by + 2], outline=80)
            d.rectangle([bx0, by, bx0 + int((bx1 - bx0) * live.progress), by + 2], fill=60)
    else:
        d.text((cx0 + 4, cy0 + 30), "Picking a map…" if live.state == "select" else "In the menus",
               font=font(10), fill=50)
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
def compose_play(frame: int, combo: int, acc: float, progress: float, mood: str = "play",
                 pose: str = "focus") -> Image.Image:
    out = bg(mood, frame).convert("RGBA")
    combo_t, acc_t = play_texts(combo, acc)
    x = COMBO_X
    for ch in combo_t:
        out.alpha_composite(char(ch, "w"), (x, TEXT_Y))
        x += char_width(ch)
    x = FRONT_W - 2 - width(acc_t)
    for ch in acc_t:
        out.alpha_composite(char(ch, "p"), (x, TEXT_Y))
        x += char_width(ch)
    d = ImageDraw.Draw(out)
    d.line([(AREA_X + 1, BAR_Y), (FRONT_W - 2, BAR_Y)], fill=(80, 20, 90, 255))
    d.line([(AREA_X + 1, BAR_Y), (AREA_X + 1 + int((AREA_W - 3) * progress), BAR_Y)], fill=(255, 140, 220, 255))
    out.alpha_composite(tile(pose, frame // 2), (0, 0))
    return out.convert("RGB")


def compose_text(mood: str, pose: str, frame: int, text: str) -> Image.Image:
    out = bg(mood, frame).convert("RGBA")
    strip, loop = text_strip(text)
    off = (frame * 2 % loop) if loop else 0
    out.alpha_composite(strip.crop((off, 0, off + AREA_W, 9)), (AREA_X, TEXT_Y + 2))
    out.alpha_composite(tile(pose, frame // 2), (0, 0))
    return out.convert("RGB")


def main() -> None:
    from sources import Live
    preview = HERE / "preview"
    preview.mkdir(exist_ok=True)
    frames = [led_preview(compose_text("menu", "chill", i, "CAMELLIA - SOME SONG"), 8) for i in range(16)]
    frames += [led_preview(compose_play(i, 100 + i * 3, 98.91 - i * 0.01, i / 40), 8) for i in range(16)]
    frames += [led_preview(compose_play(16 + i, 0, 98.6, 0.42, "miss", "miss"), 8) for i in range(4)]
    frames += [led_preview(compose_play(20 + i, i, 98.6, 0.43), 8) for i in range(8)]
    frames += [led_preview(compose_text("results", "cheer", i, "S  98.60%"), 8) for i in range(12)]
    frames[0].save(preview / "front.gif", save_all=True, append_images=frames[1:],
                   duration=150, loop=0, optimize=True)
    live = Live(state="play", artist="Camellia", title="Some Song", version="Insane", stars=5.43,
                combo=412, max_combo=412, accuracy=98.91, h300=530, h100=12, h50=1, misses=0,
                pp=212, time_ms=61000, length_ms=150000)
    back_screen(live, False).resize((BACK_W * 4, BACK_H * 4), Image.NEAREST).save(preview / "back.png")
    sheet = Image.new("RGB", (4 * (TILE_W * 8 + 8), FRONT_H * 8), (40, 40, 40))
    for k, p in enumerate(POSES):
        sheet.paste(led_preview(tile(p, 0).convert("RGB"), 8), (k * (TILE_W * 8 + 8), 0))
    sheet.save(preview / "poses.png")
    print(f"Wrote previews to {preview}")


if __name__ == "__main__":
    main()
