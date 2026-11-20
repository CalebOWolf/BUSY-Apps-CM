"""
Luca Circles 🎯🐺, for when you're clicking circles in osu!, on the BUSY Bar.

While you play, Luca (focused, on pink glass) sits beside your live combo and
accuracy, with rings rippling across a violet-to-magenta background and a
progress line for the song. A miss flashes red and Luca goes >_<. On the
results screen it turns gold with your rank, and Luca cheers for an S. In the
menus the song you've picked scrolls by. The back screen is a Windows
7-style "Luca Circles" window with the map, your hits and pp.

The live numbers come from tosu (free, https://github.com/tosuapp/tosu),
which reads osu! (stable through Wine, and lazer) and serves it on your own
PC. Without it, Luca still shows up while osu! is open.

    OK   hide Luca until you next open osu!

    python circles.py
    python circles.py --tosu 127.0.0.1:24050    # where tosu is (that's the default)
    python circles.py --demo                    # pretend: a song, a miss, an S
    python circles.py --install / --uninstall   # Linux: start at login

Needs Pillow; buttons need busylib (pip install pillow busylib).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import art  # noqa: E402
import service  # noqa: E402
import sources  # noqa: E402
from busybar import BarOffline, BusyBar, Scroller, image, input_events, is_press, rect  # noqa: E402

APP = "luca_circles"
SERVICE = "luca-circles"
POLL = 0.125               # how often to ask tosu (it's on your own PC)
PROCESS_EVERY = 3          # seconds between looks for the osu! process
MISS_SECONDS = 0.8
CHEER_SECONDS = 4
BREAK_WORTH_MENTIONING = 50


class Circles:
    def __init__(self, bar: BusyBar, priority: int, fps: float):
        self.bar, self.priority, self.fps = bar, priority, fps
        self.live: sources.Live | None = None
        self.osu_open = False
        self.hidden = False
        self.online = False
        self.on_bar = False
        self.line = Scroller(bar, "line", art.AREA_X, art.TEXT_Y + 2, art.AREA_W)
        self.line_key = None
        self.loop = self.offset = 0
        self.miss_until = 0.0
        self.cheer_until = 0.0
        self.back_key = None
        self.back_slot = 0
        self.back_due = 0.0
        self.frame = 0
        self.led: str | None = None
        self.changed = asyncio.Event()

    @property
    def wanted(self) -> bool:
        playing = self.live is not None and self.live.state == "play"
        return (self.osu_open or playing) and not self.hidden

    # -- news from the game ---------------------------------------------------------
    def take(self, new: sources.Live | None) -> None:
        old, self.live = self.live, new
        if new is None:
            return
        now = time.monotonic()
        if new.state == "play":
            restarted = old is None or old.state != "play" or new.time_ms + 1500 < old.time_ms
            if restarted:
                stars = f" {new.stars:.2f}*" if new.stars else ""
                print(f"  🎵 Playing: {new.song}" + (f" [{new.version}]" if new.version else "") + stars)
            elif new.misses > old.misses or (old.combo >= 20 and new.combo < old.combo):
                self.miss_until = now + MISS_SECONDS
                if old.combo >= BREAK_WORTH_MENTIONING:
                    print(f"  💥 Combo break at {old.combo}x")
        elif new.state == "results" and (old is None or old.state != "results"):
            rank = art.rank_label(new.rank)
            print(f"  🏁 {rank or 'Done'}: {art.accuracy_text(new.accuracy)}, {new.max_combo}x"
                  + (f", {new.pp:.0f}pp" if new.pp else ""))
            if rank in art.GOOD_RANKS:
                self.cheer_until, self.led = now + CHEER_SECONDS, art.LED_RESULTS
        self.changed.set()

    # -- pictures ---------------------------------------------------------------
    def upload_static(self) -> None:
        for mood in art.MOODS:
            for i in range(art.BG_FRAMES):
                self.bar.upload_image(f"bg_{mood}_{i}.png", art.bg(mood, i))
        for pose, n in art.POSES.items():
            for i in range(n):
                self.bar.upload_image(f"tile_{pose}_{i}.png", art.tile(pose, i))
        for ch in art.CHARS:
            for color in art.COLORS:
                self.bar.upload_image(f"ch_{art.char_name(ch)}_{color}.png", art.char(ch, color))
        self.line_key = self.back_key = None

    def upload_back(self) -> None:
        if time.monotonic() < self.back_due:
            return
        live = self.live
        key = None if live is None else (live.state, live.title, live.version, live.combo, live.misses,
                                          round(live.accuracy, 2), round(live.pp), int(live.progress * 30))
        if key != self.back_key:
            slot = 1 - self.back_slot
            self.bar.upload_image(f"back_{slot}.png", art.back_screen(live, live is None))
            self.back_slot, self.back_key = slot, key
        self.back_due = time.monotonic() + 1

    def text_line(self, text: str, color: str = "w") -> dict:
        if (text, color) != self.line_key:
            strip, self.loop = art.text_strip(text, color)
            self.line.set(strip)
            self.line_key, self.offset = (text, color), 0
        elif self.loop:
            self.offset = (self.offset + 1) % self.loop
        return self.line.element(art.AREA_X - self.offset)

    def chars(self, prefix: str, text: str, x: int, color: str) -> list[dict]:
        els = []
        for i, ch in enumerate(text):
            els.append(image(f"{prefix}{i}", f"ch_{art.char_name(ch)}_{color}.png", x, art.TEXT_Y))
            x += art.char_width(ch)
        return els

    def elements(self) -> list[dict]:
        """Builds the frame; may upload the text line or back screen (call off the event loop)."""
        live, now = self.live, time.monotonic()
        self.upload_back()
        f = self.frame
        if live is not None and live.state == "play":
            missed = now < self.miss_until
            mood, pose = ("miss", "miss") if missed else ("play", "focus")
            combo_t, acc_t = art.play_texts(live.combo, live.accuracy)
            fill = max(1, int((art.AREA_W - 3) * live.progress))
            els = [image("bg", f"bg_{mood}_{f % art.BG_FRAMES}.png", 0, 0),
                   *self.chars("c", combo_t, art.COMBO_X, "w"),
                   *self.chars("a", acc_t, art.FRONT_W - 2 - art.width(acc_t), "p"),
                   rect("track", art.AREA_X + 1, art.BAR_Y, art.AREA_W - 3, 1, "#50145AFF"),
                   rect("fill", art.AREA_X + 1, art.BAR_Y, fill, 1, "#FF8CDCFF")]
        elif live is not None and live.state == "results":
            rank = art.rank_label(live.rank)
            good = rank in art.GOOD_RANKS
            pose = "cheer" if now < self.cheer_until or good else "miss" if rank == "F" else "chill"
            mood = "results"
            els = [image("bg", f"bg_{mood}_{f % art.BG_FRAMES}.png", 0, 0),
                   self.text_line(f"{rank}  {art.accuracy_text(live.accuracy)}".strip())]
        else:
            mood, pose = "menu", "chill"
            text = live.song if live is not None and live.song else "OSU!"
            els = [image("bg", f"bg_{mood}_{f % art.BG_FRAMES}.png", 0, 0), self.text_line(text, "w")]
        n = art.POSES[pose]
        els.append(image("luca", f"tile_{pose}_{(f // 3) % n}.png", 0, 0))
        els.append(image("window", f"back_{self.back_slot}.png", 0, 0, display="back"))
        return els


async def watch(c: Circles, tosu: sources.Tosu) -> None:
    last_look, said_basic = 0.0, False
    while True:
        if time.monotonic() - last_look >= PROCESS_EVERY:
            was, c.osu_open = c.osu_open, await asyncio.to_thread(sources.osu_running)
            last_look = time.monotonic()
            if c.osu_open and not was:
                print("  🎯 osu! is open")
            elif was and not c.osu_open:
                print("  🌙 osu! closed")
                c.hidden = False  # OK's hiding lasts until the game closes
        live = await asyncio.to_thread(tosu.read) if c.osu_open else None
        if c.osu_open and live is None and not said_basic:
            print("  ℹ️  No tosu, so no live combo: see the README to set it up")
            said_basic = True
        if live is not None:
            said_basic = False
        c.take(live)
        await asyncio.sleep(POLL if c.osu_open else 1)


async def demo(c: Circles) -> None:
    c.osu_open = True
    song = dict(artist="Camellia", title="Some Song", version="Insane", stars=5.43, length_ms=60000)
    c.take(sources.Live(state="select", **song))
    await asyncio.sleep(4)
    acc, combo, misses, t0 = 100.0, 0, 0, time.monotonic()
    while (t := (time.monotonic() - t0) * 1000) < 20000:
        combo += 3
        if 9000 < t < 9200 and not misses:
            misses, combo, acc = 1, 0, acc - 0.6
        acc = max(95.0, acc - 0.004)
        c.take(sources.Live(state="play", combo=combo, max_combo=max(combo, 160), accuracy=acc,
                            h300=combo, h100=2, misses=misses, pp=round(combo * 0.8),
                            time_ms=t * 3, **song))
        await asyncio.sleep(0.125)
    c.take(sources.Live(state="results", combo=0, max_combo=212, accuracy=98.42, h300=500, h100=9,
                        misses=1, pp=196, rank="S", **song))
    while True:
        await asyncio.sleep(3600)


async def animate(c: Circles) -> None:
    retry = 2
    while True:
        try:
            if c.wanted:
                if not c.online:
                    await asyncio.to_thread(c.upload_static)
                    c.online, retry = True, 2
                led, c.led = c.led, None
                await asyncio.to_thread(lambda: c.bar.draw(c.elements(), c.priority, led))
                c.on_bar = True
                c.frame += 1
                await asyncio.sleep(1 / c.fps)
            else:
                if c.on_bar:
                    await asyncio.to_thread(c.bar.clear)
                    c.on_bar = False
                c.changed.clear()
                try:
                    await asyncio.wait_for(c.changed.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
        except BarOffline as err:
            if c.online or retry == 2:
                print(f"🔌 BUSY Bar trouble: {err}; I'll keep trying quietly")
            c.online = c.on_bar = False
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def listen(c: Circles) -> None:
    async for event in input_events(c.bar):
        if c.on_bar and is_press(event) and event.button == "ok":
            c.hidden = True
            print("  🙈 Hidden until you next open osu!")
            c.changed.set()


async def run(c: Circles, args) -> None:
    await asyncio.gather(animate(c), listen(c), demo(c) if args.demo else watch(c, sources.Tosu(args.tosu)))


def install(args) -> None:
    if args.demo:
        raise SystemExit("--install starts the real thing; leave out --demo.")
    service.check([
        ("Pillow (pip install pillow)", service.importable("PIL")),
        ("busylib (pip install busylib)", service.importable("busylib")),
    ], required={"Pillow (pip install pillow)"})
    command = [sys.executable, str(Path(__file__).resolve()), "--tosu", args.tosu,
               "--host", args.host, "--priority", str(args.priority), "--fps", str(args.fps)]
    service.install(SERVICE, "Luca Circles for the BUSY Bar", command, args.token,
                    "Luca now shows up on the BUSY Bar whenever osu! is open.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tosu", default="127.0.0.1:24050", help="where tosu serves (default 127.0.0.1:24050)")
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"),
                    help="API key, if HTTP access is set to 'key' mode (or set BUSYBAR_TOKEN)")
    ap.add_argument("--priority", type=int, default=57,
                    help="draw priority 1-100 (default 57: over music, Minecraft and the always-on apps)")
    ap.add_argument("--fps", type=float, default=8, help="animation speed (default 8)")
    ap.add_argument("--demo", action="store_true", help="pretend: pick a song, play it with a miss, get an S")
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
    c = Circles(bar, args.priority, args.fps)
    print(f"🎯 Luca Circles: {'demo' if args.demo else 'waiting for osu! (live stats from tosu at ' + args.tosu + ')'}")
    print(f"🐺 Luca shows up on the BUSY Bar at {args.host} while osu! is open.")
    print("   OK = hide until you next open osu!. Ctrl+C to stop.")

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(run(c, args))
    except KeyboardInterrupt:
        pass
    finally:
        if c.on_bar:
            try:
                bar.clear()
            except BarOffline:
                pass
        print("\n🌙 Luca puts the tablet pen down.")


if __name__ == "__main__":
    main()
