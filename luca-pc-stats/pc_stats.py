"""
Luca PC Stats 📈🐺, your PC's vitals on the BUSY Bar in Frutiger Aero style.

The front strip cycles through CPU, RAM, GPU and temperature, each with a
glossy Aero gauge, while Luca reacts to the heat: happy when it's cool,
sweating when it's warm, tongue out when it's hot. The back screen becomes
"Luca Monitor", a Windows 7 Task Manager-style window with a CPU history
graph and every number at once.

    Start / Back   next / previous page
    Wheel          flip through the pages
    OK             pin this page (stop flipping on its own)

    python pc_stats.py                    # BUSY Bar on USB (10.0.4.20)
    python pc_stats.py --host 192.168.1.42 --token YOUR_KEY   # over Wi-Fi
    python pc_stats.py --demo             # made-up numbers, to try it out
    python pc_stats.py --install          # Linux: start automatically at login
    python pc_stats.py --uninstall        # Linux: stop starting at login

It draws at a low priority, so other apps (like Luca Now Playing) can take
the bar while they have something to show.
Needs Pillow and psutil; buttons also need busylib (pip install pillow psutil busylib).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import art  # noqa: E402
import service  # noqa: E402
import stats  # noqa: E402
from busybar import (BarOffline, BusyBar, image, input_events, is_press,  # noqa: E402
                     is_wheel, rect)

APP = "luca_pc_stats"
SERVICE = "luca-pc-stats"
PAGE_SECONDS = 5       # how long each page shows before flipping
MANUAL_HOLD = 20       # after you flip by hand, wait this long before flipping again


def to_f(c: float) -> float:
    return c * 9 / 5 + 32


class Front:
    """Which page is showing and what the front strip looks like right now."""

    def __init__(self, fahrenheit: bool = False):
        self.fahrenheit = fahrenheit
        self.snap = stats.Snapshot()
        self.page = 0
        self.pinned = False
        self.flipped_at = time.monotonic()
        self.hold_until = 0.0

    # -- pages ---------------------------------------------------------------
    def pages(self) -> list[str]:
        s = self.snap
        out = ["cpu", "ram"]
        if s.gpu is not None or s.gpu_temp is not None:
            out.append("gpu")
        if s.hottest is not None:
            out.append("temp")
        return out

    def current(self) -> str:
        pages = self.pages()
        return pages[self.page % len(pages)]

    def next_page(self, step: int = 1, by_hand: bool = False) -> None:
        self.page = (self.page + step) % len(self.pages())
        self.flipped_at = time.monotonic()
        if by_hand:
            self.hold_until = time.monotonic() + MANUAL_HOLD

    def tick(self) -> None:
        now = time.monotonic()
        if (not self.pinned and now >= self.hold_until
                and now - self.flipped_at >= PAGE_SECONDS):
            self.next_page()

    def update(self, snap: stats.Snapshot) -> None:
        self.snap = snap

    # -- what to show --------------------------------------------------------
    def value(self, page: str) -> tuple[str, float]:
        s = self.snap
        if page == "cpu":
            v = s.cpu
            return ("--", 0.0) if v is None else (f"{v:.0f}%", v / 100)
        if page == "ram":
            v = s.ram
            return ("--", 0.0) if v is None else (f"{v:.0f}%", v / 100)
        if page == "gpu":
            v = s.gpu
            if v is None:  # temperature only (some GPUs don't report load)
                return self.temp_text(s.gpu_temp)
            return f"{v:.0f}%", v / 100
        return self.temp_text(s.hottest)

    def temp_text(self, c: float | None) -> tuple[str, float]:
        if c is None:
            return "--", 0.0
        shown = to_f(c) if self.fahrenheit else c
        # Just "°" on the strip, so three-digit °F still fits next to the label;
        # the back screen spells out the unit.
        return f"{shown:.0f}°", max(0.0, min(1.0, (c - 30) / 65))

    def mood(self) -> str:
        hot = self.snap.hottest
        if hot is not None:
            return "cool" if hot < 55 else "ok" if hot < 70 else "warm" if hot < 82 else "hot"
        cpu = self.snap.cpu or 0
        return "cool" if cpu < 30 else "ok" if cpu < 60 else "warm" if cpu < 85 else "hot"

    def elements(self, frame: int) -> list[dict]:
        page = self.current()
        text, frac = self.value(page)
        els = [image("sky", f"sky_{frame % art.SKY_FRAMES}.png", 0, 0),
               image("label", f"label_{page}.png", *art.LABEL_XY)]

        x = art.VALUE_RIGHT - (sum(art.char_width(c) for c in text) - 1) + 1
        for i, ch in enumerate(text):
            els.append(image(f"c{i}", f"char_{art.char_name(ch)}.png", x, art.VALUE_Y))
            x += art.char_width(ch)

        gx, gy, gw, gh = art.GAUGE
        els.append(rect("gauge", gx, gy, gw, gh, "#0A3278FF"))
        fill = round(gw * max(0.0, min(1.0, frac)))
        if fill:
            els.append(rect("gauge_fill", gx, gy, fill, gh,
                            ["#50F0BEFF", art.gauge_color(frac)], gradient="h"))
            els.append(rect("gauge_shine", gx, gy, fill, 1, "#FFFFFF80"))

        dx, dy = art.DOTS_XY
        for i, p in enumerate(self.pages()):
            on = p == page
            color = ("#50F0BEFF" if self.pinned else "#FFFFFFFF") if on else "#5A8CC8FF"
            els.append(rect(f"dot{i}", dx + i * 3, dy, 1, 1, color))

        busy = (self.snap.cpu or 0) >= 50
        bob = (frame // (1 if busy else 2)) % 2  # Luca bops faster when the CPU works hard
        els.append(image("luca", f"tile_{self.mood()}_{bob}.png", 0, 0))
        return els

    def compose(self, frame: int) -> Image.Image:
        """Draw the elements locally, the way the bar would (for previews)."""
        assets = static_assets()
        out = Image.new("RGBA", (art.FRONT_W, art.FRONT_H), (0, 0, 0, 255))
        for e in self.elements(frame):
            if e["type"] == "image":
                out.alpha_composite(assets[e["path"]].convert("RGBA"), (e["x"], e["y"]))
            else:
                colors = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5, 7)) for c in e["fill_colors"]]
                layer = Image.new("RGBA", (e["width"], e["height"]))
                d = ImageDraw.Draw(layer)
                for xx in range(e["width"]):
                    t = xx / max(e["width"] - 1, 1) if e["fill"] == "gradient_h" else 0
                    c = colors[0] if len(colors) == 1 else art.lerp(colors[0], colors[1], t)
                    d.line([(xx, 0), (xx, e["height"] - 1)], fill=tuple(c))
                tmp = Image.new("RGBA", out.size, (0, 0, 0, 0))
                tmp.paste(layer, (e["x"], e["y"]))
                out.alpha_composite(tmp)
        return out.convert("RGB")


_ASSETS: dict[str, Image.Image] = {}


def static_assets() -> dict[str, Image.Image]:
    """Everything that's uploaded once, by file name."""
    if not _ASSETS:
        for i in range(art.SKY_FRAMES):
            _ASSETS[f"sky_{i}.png"] = art.sky(i)
        for mood in art.MOODS:
            for i in range(2):
                _ASSETS[f"tile_{mood}_{i}.png"] = art.tile(mood, i)
        for page in art.PAGES:
            _ASSETS[f"label_{page}.png"] = art.label(page)
        for ch in art.CHARS:
            _ASSETS[f"char_{art.char_name(ch)}.png"] = art.char(ch)
    return _ASSETS


class App:
    def __init__(self, bar: BusyBar, reader, front: Front, priority: int):
        self.bar, self.reader, self.front, self.priority = bar, reader, front, priority
        self.online = False
        self.slot = 0
        self.back_due = 0.0

    def upload_static(self) -> None:
        for name, img in static_assets().items():
            self.bar.upload_image(name, img)

    def upload_back(self) -> None:
        slot = 1 - self.slot
        self.bar.upload_image(f"back_{slot}.png",
                              art.back_screen(self.front.snap, self.front.fahrenheit))
        self.slot = slot


async def read_stats(app: App) -> None:
    while True:
        try:
            app.front.update(await asyncio.to_thread(app.reader.read))
        except Exception as err:  # a sensor hiccup shouldn't stop the show
            print(f"⚠️  Couldn't read the PC's stats: {err}")
        await asyncio.sleep(1)


async def animate(app: App, fps: float) -> None:
    frame, retry = 0, 2
    while True:
        try:
            if not app.online:
                await asyncio.to_thread(app.upload_static)
                await asyncio.to_thread(app.upload_back)
                app.online, retry = True, 2
                print("🐺 Luca is keeping an eye on your PC")
            if time.monotonic() >= app.back_due:
                await asyncio.to_thread(app.upload_back)
                app.back_due = time.monotonic() + 2
            app.front.tick()
            els = app.front.elements(frame)
            els.append(image("window", f"back_{app.slot}.png", 0, 0, display="back"))
            await asyncio.to_thread(app.bar.draw, els, app.priority)
            frame += 1
            await asyncio.sleep(1 / fps)
        except BarOffline as err:
            if app.online or retry == 2:
                print(f"🔌 Can't reach the BUSY Bar ({err}); I'll keep trying quietly")
            app.online = False
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def listen(app: App) -> None:
    async for event in input_events(app.bar):
        f = app.front
        if is_wheel(event):
            f.next_page(1 if event.delta > 0 else -1, by_hand=True)
        elif is_press(event):
            if event.button == "start":
                f.next_page(1, by_hand=True)
            elif event.button == "back":
                f.next_page(-1, by_hand=True)
            elif event.button == "ok":
                f.pinned = not f.pinned
                print(f"  📌 {'Pinned' if f.pinned else 'Unpinned'} the {f.current().upper()} page")


async def run(app: App, fps: float) -> None:
    await asyncio.gather(read_stats(app), animate(app, fps), listen(app))


def install(args) -> None:
    if args.demo:
        raise SystemExit("--install starts the real thing; leave out --demo.")
    service.check([
        ("psutil (pip install psutil)", service.importable("psutil")),
        ("Pillow (pip install pillow)", service.importable("PIL")),
        ("busylib (pip install busylib)", service.importable("busylib")),
    ], required={"psutil (pip install psutil)", "Pillow (pip install pillow)"})
    command = [sys.executable, str(Path(__file__).resolve()), "--host", args.host,
               "--fps", str(args.fps), "--priority", str(args.priority)]
    if args.fahrenheit:
        command.append("--fahrenheit")
    service.install(SERVICE, "Luca PC Stats for the BUSY Bar", command, args.token,
                    "Luca now keeps an eye on your PC from login.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"),
                    help="API key, if HTTP access is set to 'key' mode (or set BUSYBAR_TOKEN)")
    ap.add_argument("--fps", type=float, default=4, help="animation speed (default 4)")
    ap.add_argument("--priority", type=int, default=20,
                    help="draw priority 1-100; lower lets other apps go first (default 20)")
    ap.add_argument("--fahrenheit", action="store_true", help="show temperatures in °F")
    ap.add_argument("--demo", action="store_true", help="show made-up numbers")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true",
                       help="Linux: start automatically at login (systemd user service)")
    group.add_argument("--uninstall", action="store_true", help="Linux: stop starting at login")
    args = ap.parse_args()
    if not 1 <= args.priority <= 100:
        ap.error("--priority must be between 1 and 100")

    if args.install:
        return install(args)
    if args.uninstall:
        return service.uninstall(SERVICE)

    reader = stats.DemoStats() if args.demo else stats.Stats()
    bar = BusyBar(args.host, APP, args.token)
    app = App(bar, reader, Front(args.fahrenheit), args.priority)
    gpu = {"nvidia": "NVIDIA (nvidia-smi)", "amd": "AMD (amdgpu)", "demo": "demo"}.get(
        reader.gpu_source, "none found")
    print(f"📈 Watching CPU, RAM, temperatures and network. GPU: {gpu}")
    print(f"🐺 Showing on the BUSY Bar at {args.host}.")
    print("   Start/Back or the wheel = change page, OK = pin page. Ctrl+C to stop.")

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(run(app, args.fps))
    except KeyboardInterrupt:
        pass
    finally:
        if app.online:
            try:
                bar.clear()
            except BarOffline:
                pass
        print("\n🌙 Luca stops watching. Screens cleared.")


if __name__ == "__main__":
    main()
