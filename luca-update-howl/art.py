"""
Artwork for Luca Update Howl, drawn with Pillow.

Uploaded once:
  sign_<mood>_N.png   72x16 glossy Aero backgrounds with a light sweeping
                      across: deep blue while updates wait, minty teal when
                      you're up to date, amber when it's time to reboot
  tile_<pose>_N.png   19x16 glass tile with Luca: calm, howling (a kernel
                      update!), happy (all up to date) or in a hard hat
                      (reboot needed)
When it changes:
  the text line       "12 UPDATES", "AUR 3", the big ones, "REBOOT"…
  the back screen     "Luca Update Howl", a Windows 7-style window

    python art.py      # writes previews into preview/
"""

from __future__ import annotations

import math
import sys
import time
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
SIGN_FRAMES = 8
MOODS = {  # top, bottom
    "updates": ((60, 170, 240), (10, 70, 160)),
    "fresh": ((110, 235, 200), (0, 120, 110)),
    "reboot": ((255, 200, 90), (175, 90, 0)),
}
POSES = {"calm": 2, "howl": 2, "happy": 2, "hardhat": 2}
LED = {"updates": "#2090FFFF", "kernel": "#2090FFFF", "reboot": "#FFA020FF"}
GAP = "     "
WHITE = (255, 255, 255, 255)
SOFT = (200, 235, 255, 255)
SHADOW = (5, 25, 70, 255)


# --------------------------------------------------------------------------
# Backgrounds
# --------------------------------------------------------------------------
def sign(mood: str, frame: int) -> Image.Image:
    top, bottom = MOODS[mood]
    img = Image.new("RGB", (FRONT_W, FRONT_H))
    px = img.load()
    sweep = -20 + frame * (FRONT_W + 40) / SIGN_FRAMES  # a soft light sweeping across
    for y in range(FRONT_H):
        base = lerp(top, bottom, y / (FRONT_H - 1))
        if y < 7:
            base = lerp(base, (255, 255, 255), 0.4 * (1 - y / 7))  # glossy top half
        for x in range(FRONT_W):
            glow = max(0.0, 1 - abs(x - y * 0.6 - sweep) / 8) * 0.35
            px[x, y] = lerp(base, (255, 255, 255), glow)
    d = ImageDraw.Draw(img)
    d.rectangle([AREA_X - 1, 0, FRONT_W - 1, FRONT_H - 1], outline=lerp(top, (255, 255, 255), 0.6))
    return img


# --------------------------------------------------------------------------
# Luca
# --------------------------------------------------------------------------
PALETTE = {
    "K": (28, 30, 44), "W": (255, 255, 255), "S": (190, 205, 230),
    "G": (150, 150, 158), "T": (40, 235, 175), "M": (8, 8, 12),
    "O": (245, 160, 80), "N": (225, 140, 115), "P": (255, 150, 160),
    "Y": (255, 205, 40), "y": (200, 140, 0),   # hard hat
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
HARDHAT = [
    "....yYYYYYy.....",
    "...yYYYYYYYy....",
    "..yYYYYYYYYYy...",
    "yYYYYYYYYYYYYYy.",
]


def luca(pose: str, frame: int) -> list[str]:
    rows = [list(r) for r in LUCA]
    if pose in ("happy", "howl"):  # ^^
        rows[6][3:5], rows[7][3:5] = "KK", "WW"
        rows[6][10:12], rows[7][10:12] = "SS", "MM"
    if pose == "howl":  # snout up, mouth open: AWOO
        rows[11][5:10] = "WKKKW"
        rows[12][5:10] = "KPPPK" if frame % 2 else "KPKPK"
    if pose == "calm" and frame % 2:  # a slow blink
        rows[6][3:5], rows[7][3:5] = "WW", "KK"
        rows[6][10:12], rows[7][10:12] = "MM", "KK"
    if pose == "hardhat":
        for y, row in enumerate(HARDHAT):
            for x, ch in enumerate(row):
                if ch != ".":
                    rows[y][x] = ch
        if frame % 2:
            rows[1][6] = "W"  # a glint on the hat
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
    if pose == "howl" and frame % 2:  # little "sound" ticks
        for x, y in ((17, 9), (18, 8), (17, 12), (18, 13)):
            img.putpixel((x, y), (255, 255, 255, 255))
    return img


# --------------------------------------------------------------------------
# The text line
# --------------------------------------------------------------------------
def text_strip(text: str, color=WHITE) -> tuple[Image.Image, int]:
    """Centred if it fits; otherwise two copies with a gap, and how far to
    scroll before it repeats."""
    text = to_font_text(text)
    w = text_width(text)
    if w <= AREA_W - 2:
        img = Image.new("RGBA", (AREA_W, 9), (0, 0, 0, 0))
        draw_text(img, text, (AREA_W - w) // 2, 0, color=color, shadow=SHADOW)
        return img, 0
    loop = text_width(text + GAP)
    img = Image.new("RGBA", (loop + w + 2, 9), (0, 0, 0, 0))
    draw_text(img, text, 0, 0, color=color, shadow=SHADOW)
    draw_text(img, text, loop, 0, color=color, shadow=SHADOW)
    return img, loop


def count_text(n: int) -> str:
    return "ALL FRESH" if n == 0 else f"{n} UPDATE" + ("" if n == 1 else "S")


# --------------------------------------------------------------------------
# Back screen: "Luca Update Howl"
# --------------------------------------------------------------------------
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
    for sx in (70, 78, 124):
        d.line([(sx, wy0 + 1), (sx + 10, wy0 + 12)], fill=235)
    # a little package box icon
    d.rectangle([wx0 + 4, wy0 + 3, wx0 + 10, wy0 + 9], fill=170, outline=20)
    d.line([(wx0 + 4, wy0 + 5), (wx0 + 10, wy0 + 5)], fill=20)
    d.line([(wx0 + 7, wy0 + 3), (wx0 + 7, wy0 + 5)], fill=20)
    d.text((wx0 + 15, wy0), "Luca Update Howl", font=font(10), fill=20)
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

    n = len(status.updates)
    head = "All up to date!" if n == 0 else f"{n} update{'s' if n != 1 else ''}"
    d.text((cx0 + 4, cy0 + 1), head, font=font(12), fill=0)
    if n:
        split = f"{len(status.repo)} repo, {len(status.aur)} AUR" if status.aur_checked \
            else f"{len(status.repo)} repo"
        d.text((cx1 - 4, cy0 + 4), split, font=font(9), fill=70, anchor="ra")
    y = cy0 + 15
    rows = 4
    if status.reboot:
        d.rectangle([cx0 + 2, y, cx1 - 2, y + 9], fill=40)
        d.text((cx0 + 5, y), "Reboot to finish the kernel update", font=font(9), fill=255)
        y, rows = y + 11, 3
    for u in status.updates[:rows]:
        name = ("* " if u.big else "") + u.name + (" (AUR)" if u.aur else "")
        d.text((cx0 + 4, y), fit(d, name, font(9), 80), font=font(9), fill=0)
        d.text((cx1 - 4, y), fit(d, u.new, font(9), 60), font=font(9), fill=60, anchor="ra")
        y += 9
    foot = cy1 - 10
    if n > rows:
        d.text((cx0 + 4, foot), f"...and {n - rows} more", font=font(8), fill=80)
    if status.checked:
        when = time.strftime("%H:%M", time.localtime(status.checked))
        d.text((cx1 - 3, foot), ("check failed " if status.error else "checked ") + when,
               font=font(8), fill=100, anchor="ra")
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
def compose(mood: str, pose: str, frame: int, text: str, color=WHITE) -> Image.Image:
    out = sign(mood, frame).convert("RGBA")
    strip, loop = text_strip(text, color)
    off = (frame * 2 % loop) if loop else 0
    out.alpha_composite(strip.crop((off, 0, off + AREA_W, 9)), (AREA_X, TEXT_Y))
    out.alpha_composite(tile(pose, frame // 2), (0, 0))
    return out.convert("RGB")


def demo_status():
    from updates import Status, Update
    return Status(updates=[
        Update("linux", "6.12.1.arch1-1", "6.12.3.arch1-1"),
        Update("mesa", "1:24.3.0-1", "1:24.3.1-1"),
        Update("firefox", "133.0-1", "133.0.3-1"),
        Update("python", "3.13.0-1", "3.13.1-1"),
        Update("vesktop-bin", "1.5.3-1", "1.5.4-1", aur=True),
        Update("prismlauncher", "9.1-1", "9.2-1", aur=True),
    ], reboot=False, running_kernel="6.12.1-arch1-1", checked=time.time())


def main() -> None:
    preview = HERE / "preview"
    preview.mkdir(exist_ok=True)
    frames = [led_preview(compose("updates", "howl", i, "6 UPDATES"), 8) for i in range(12)]
    frames += [led_preview(compose("updates", "calm", i, "LINUX  MESA", SOFT), 8) for i in range(24)]
    frames += [led_preview(compose("reboot", "hardhat", i, "REBOOT"), 8) for i in range(12)]
    frames += [led_preview(compose("fresh", "happy", i, "UP TO DATE"), 8) for i in range(12)]
    frames[0].save(preview / "front.gif", save_all=True, append_images=frames[1:],
                   duration=200, loop=0, optimize=True)
    back_screen(demo_status(), time.time()).resize((BACK_W * 4, BACK_H * 4), Image.NEAREST) \
        .save(preview / "back.png")
    sheet = Image.new("RGB", (4 * (TILE_W * 8 + 8), FRONT_H * 8), (40, 40, 40))
    for k, p in enumerate(POSES):
        sheet.paste(led_preview(tile(p, 0).convert("RGB"), 8), (k * (TILE_W * 8 + 8), 0))
    sheet.save(preview / "poses.png")
    print(f"Wrote previews to {preview}")


if __name__ == "__main__":
    main()
