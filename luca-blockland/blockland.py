"""
Luca Blockland ⛏️🐺, for the BUSY Bar: while your Minecraft instance is
running, Luca (with a pickaxe) sits beside a blocky landscape that scrolls
by, under a day sky or a starry night (following your clock).

The front takes turns: your instance's name, a moment of just the scenery,
how long you've played, the scenery again. The back screen is a Windows
7-style "Luca Blockland" window with the instance, the time played and the
launcher. When the game closes, Luca steps aside.

    Start / Back   next / previous page
    OK             hide Luca until the next time you start the game

    python blockland.py                          # watches for "Wolf Howl"
    python blockland.py --instance "My World"    # another instance
    python blockland.py --instance "*"           # any Minecraft at all
    python blockland.py --demo                   # pretend the game is running
    python blockland.py --install / --uninstall  # Linux: start at login

Works with Prism Launcher, MultiMC, ATLauncher, CurseForge, the Modrinth app
and the official launcher (give the profile its own game folder named after
it). Linux. Needs Pillow; buttons need busylib (pip install pillow busylib).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import art  # noqa: E402
import service  # noqa: E402
import sources  # noqa: E402
from busybar import BarOffline, BusyBar, Scroller, image, input_events, is_press, is_wheel  # noqa: E402

APP = "luca_blockland"
SERVICE = "luca-blockland"
DEFAULT_INSTANCE = "Wolf Howl"
POLL_SECONDS = 3
HAPPY_SECONDS = 3                      # Luca cheers when the game starts
PAGES = ["name", "scenery", "time", "scenery"]
PAGE_SECONDS = {"name": 6, "scenery": 5, "time": 4}
DAY_HOURS = range(7, 19)


def sky_now() -> str:
    return "day" if datetime.now().hour in DAY_HOURS else "night"


class Blockland:
    def __init__(self, bar: BusyBar, instance: str, priority: int, fps: float):
        self.bar, self.instance, self.priority, self.fps = bar, instance, priority, fps
        self.game: sources.Game | None = None
        self.hidden_pid: int | None = None   # OK hides Luca until the next launch
        self.online = False
        self.on_bar = False
        self.skies: set[str] = set()         # which skies the bar has
        self.line = Scroller(bar, "line", art.AREA_X, art.TEXT_Y, art.AREA_W)
        self.line_text = None
        self.loop = self.offset = 0
        self.page = 0
        self.flipped_at = time.monotonic()
        self.happy_until = 0.0
        self.back_key = None
        self.back_slot = 0
        self.frame = 0
        self.light = False
        self.changed = asyncio.Event()

    @property
    def wanted(self) -> bool:
        return self.game is not None and self.game.pid != self.hidden_pid

    # -- pictures ----------------------------------------------------------------
    def upload_static(self) -> None:
        for pose, n in art.POSES.items():
            for i in range(n):
                self.bar.upload_image(f"tile_{pose}_{i}.png", art.tile(pose, i))
        self.skies.clear()
        self.line_text = self.back_key = None

    def upload_sky(self, sky: str) -> None:
        if sky not in self.skies:
            for i in range(art.SCENE_FRAMES):
                self.bar.upload_image(f"scene_{sky}_{i:02d}.png", art.scene(sky, i))
            self.skies.add(sky)

    def upload_back(self) -> None:
        g = self.game
        played = time.time() - g.started
        key = (g.pid, g.instance, int(played))
        if key != self.back_key:
            slot = 1 - self.back_slot
            started = datetime.fromtimestamp(g.started).strftime("%H:%M")
            self.bar.upload_image(f"back_{slot}.png",
                                  art.back_screen(g.instance, g.launcher, played, started))
            self.back_slot, self.back_key = slot, key

    # -- what to show -----------------------------------------------------------
    def page_name(self) -> str:
        return PAGES[self.page % len(PAGES)]

    def flip(self, step: int = 1) -> None:
        self.page, self.flipped_at = self.page + step, time.monotonic()
        self.offset = 0

    def elements(self) -> list[dict]:
        """Builds the frame; uploads the text line when it changes (call off the event loop)."""
        g, now = self.game, time.monotonic()
        page = self.page_name()
        long_name = page == "name" and self.loop
        if now - self.flipped_at >= PAGE_SECONDS[page] and not (long_name and self.offset):
            self.flip()
            page = self.page_name()
        sky = sky_now()
        self.upload_sky(sky)
        self.upload_back()

        els = [image("scene", f"scene_{sky}_{self.frame % art.SCENE_FRAMES:02d}.png", 0, 0)]
        if page != "scenery":
            text = g.instance if page == "name" else art.played_short(time.time() - g.started)
            if text != self.line_text:
                strip, self.loop = art.text_strip(text)
                self.line.set(strip)
                self.line_text, self.offset = text, 0
            elif self.loop:
                self.offset = (self.offset + 1) % self.loop
            els.append(self.line.element(art.AREA_X - self.offset))
        pose = "happy" if now < self.happy_until else "dig"
        els.append(image("luca", f"tile_{pose}_{(self.frame // 3) % art.POSES[pose]}.png", 0, 0))
        els.append(image("window", f"back_{self.back_slot}.png", 0, 0, display="back"))
        return els


async def watch(land: Blockland) -> None:
    while True:
        game = await asyncio.to_thread(sources.find, land.instance)
        old = land.game
        if game and (not old or old.pid != game.pid):
            print(f"  ⛏️  {game.instance} started" + (f" ({game.launcher})" if game.launcher else ""))
            land.light, land.page, land.flipped_at = True, 0, time.monotonic()
            land.happy_until = time.monotonic() + HAPPY_SECONDS
        elif old and not game:
            print(f"  🌙 {old.instance} closed after {art.played(time.time() - old.started)}")
        land.game = game
        land.changed.set()
        await asyncio.sleep(POLL_SECONDS)


async def demo(land: Blockland) -> None:
    land.game = sources.Game(1, land.instance, "Prism Launcher", time.time() - 3923)
    land.light, land.happy_until = True, time.monotonic() + HAPPY_SECONDS
    print(f"  ⛏️  {land.instance} started (pretend)")
    while True:
        await asyncio.sleep(3600)


async def animate(land: Blockland) -> None:
    retry = 2
    while True:
        try:
            if land.wanted:
                if not land.online:
                    await asyncio.to_thread(land.upload_static)
                    land.online, retry = True, 2
                led = art.LED_LAUNCH if land.light else None
                await asyncio.to_thread(lambda: land.bar.draw(land.elements(), land.priority, led))
                land.light, land.on_bar = False, True
                land.frame += 1
                await asyncio.sleep(1 / land.fps)
            else:
                if land.on_bar:
                    await asyncio.to_thread(land.bar.clear)
                    land.on_bar = False
                land.changed.clear()
                try:
                    await asyncio.wait_for(land.changed.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
        except BarOffline as err:
            if land.online or retry == 2:
                print(f"🔌 BUSY Bar trouble: {err}; I'll keep trying quietly")
            land.online = land.on_bar = False
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def listen(land: Blockland) -> None:
    async for event in input_events(land.bar):
        if not land.on_bar:
            continue
        if is_wheel(event):
            land.flip(1 if event.delta > 0 else -1)
        elif is_press(event):
            if event.button == "start":
                land.flip(1)
            elif event.button == "back":
                land.flip(-1)
            elif event.button == "ok" and land.game:
                land.hidden_pid = land.game.pid
                print("  🙈 Hidden until the next time you start the game")
                land.changed.set()


async def run(land: Blockland, args) -> None:
    await asyncio.gather(animate(land), listen(land), demo(land) if args.demo else watch(land))


def install(args) -> None:
    if args.demo:
        raise SystemExit("--install starts the real thing; leave out --demo.")
    service.check([
        ("Pillow (pip install pillow)", service.importable("PIL")),
        ("busylib (pip install busylib)", service.importable("busylib")),
    ], required={"Pillow (pip install pillow)"})
    command = [sys.executable, str(Path(__file__).resolve()), "--instance", args.instance,
               "--host", args.host, "--priority", str(args.priority), "--fps", str(args.fps)]
    service.install(SERVICE, "Luca Blockland for the BUSY Bar", command, args.token,
                    f"Luca now shows up on the BUSY Bar whenever {args.instance} is running.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", default=DEFAULT_INSTANCE,
                    help=f'your Minecraft instance\'s name (default "{DEFAULT_INSTANCE}"; "*" for any)')
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"),
                    help="API key, if HTTP access is set to 'key' mode (or set BUSYBAR_TOKEN)")
    ap.add_argument("--priority", type=int, default=55,
                    help="draw priority 1-100 (default 55: over music and the always-on apps)")
    ap.add_argument("--fps", type=float, default=4, help="animation speed (default 4)")
    ap.add_argument("--demo", action="store_true", help="pretend the game is running")
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

    bar = BusyBar(args.host, APP, args.token)
    land = Blockland(bar, args.instance, args.priority, args.fps)
    which = "any Minecraft" if args.instance.strip() == "*" else f'"{args.instance}"'
    print(f"⛏️  Luca Blockland: {'demo' if args.demo else 'watching for ' + which}")
    print(f"🐺 Luca shows up on the BUSY Bar at {args.host} while the game runs.")
    print("   Start/Back = page, OK = hide until the next launch. Ctrl+C to stop.")

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(run(land, args))
    except KeyboardInterrupt:
        pass
    finally:
        if land.on_bar:
            try:
                bar.clear()
            except BarOffline:
                pass
        print("\n🌙 Luca puts his pickaxe away.")


if __name__ == "__main__":
    main()
