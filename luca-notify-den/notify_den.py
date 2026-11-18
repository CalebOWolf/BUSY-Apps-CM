"""
Luca Notify Den 🔔🐺, your PC's desktop notifications on the BUSY Bar.

When a notification pops up on your PC (a Discord ping, a message, an email,
a finished download), Luca perks up on the bar with a "!" and the app name and
message scroll past on a glossy Frutiger Aero sky. The bar's notification
light glows in the app's color. The back screen becomes "Luca Inbox", a
Windows 7-style list of your latest notifications. Your usual pop-ups keep
working as before; Luca only watches.

    OK      dismiss (and clear anything waiting)
    Start   next notification
    Back    show the one before again
    Wheel   flip through recent notifications

Put the bar's selector on OFF (do not disturb) and Luca holds new
notifications quietly, then shows them when you switch back.

    python notify_den.py                  # BUSY Bar on USB (10.0.4.20)
    python notify_den.py --host 192.168.1.42 --token YOUR_KEY   # over Wi-Fi
    python notify_den.py --private        # show only the app name, not the message
    python notify_den.py --ignore spotify,steam
    python notify_den.py --demo           # made-up notifications, to try it out
    python notify_den.py --install        # start automatically at login
    python notify_den.py --uninstall      # stop starting at login

Linux only (it listens on D-Bus). Needs Pillow and dbus-fast; buttons also
need busylib (pip install pillow dbus-fast busylib).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import art  # noqa: E402
import service  # noqa: E402
import watcher  # noqa: E402
from busybar import (BarOffline, BusyBar, image, input_events, is_press,  # noqa: E402
                     is_selector, is_wheel, rect)

APP = "luca_notify_den"
SERVICE = "luca-notify-den"
HOLD_FRAMES = 12        # pause before a long message starts scrolling
ALERT_SECONDS = 1.5     # how long Luca stays perked up before he reads
MAX_WAITING = 5         # keep only the newest few while you're away or busy
MAX_SECONDS = 30        # the longest one notification stays up


class Den:
    def __init__(self, bar: BusyBar, show: float, private: bool, ignore: set[str],
                 priority: int, fps: float):
        self.bar, self.show, self.private = bar, show, private
        self.ignore, self.priority, self.fps = ignore, priority, fps
        self.waiting: deque = deque(maxlen=MAX_WAITING)
        self.history: deque = deque(maxlen=20)   # newest first
        self.current = None
        self.shown_at = 0.0
        self.online = False
        self.on_bar = False
        self.dnd = False
        self.slot = 0
        self.loop = 0
        self.offset = 0
        self.hold = 0
        self.light = False          # light the LED on the next frame
        self.frame = 0
        self.wake = asyncio.Event()

    # -- notifications in -----------------------------------------------------
    def arrive(self, note) -> None:
        if note.app.strip().lower() in self.ignore:
            return
        self.history.appendleft(note)
        self.waiting.append(note)
        where = " (held: do not disturb)" if self.dnd else ""
        print(f"  🔔 {note.app}: {note.summary}{where}")
        self.wake.set()

    # -- what's showing -----------------------------------------------------
    def duration(self) -> float:
        """Long enough to read: at least --show seconds, or one full scroll
        (but never more than MAX_SECONDS)."""
        scroll = (HOLD_FRAMES + self.loop) / self.fps + 1 if self.loop else 0
        return max(self.show, min(scroll, MAX_SECONDS))

    def present(self, note) -> None:
        """Upload this notification's strip and back screen, then show it."""
        slot = 1 - self.slot
        strip, loop = art.strip(note, self.private)
        self.bar.upload_image(f"strip_{slot}.png", strip)
        self.bar.upload_image(f"back_{slot}.png", art.back_screen(
            list(self.history), note, self.private, len(self.waiting) if self.dnd else 0))
        self.slot, self.loop, self.offset, self.hold = slot, loop, 0, HOLD_FRAMES
        self.current, self.shown_at, self.light = note, time.monotonic(), True

    def elements(self) -> list[dict]:
        note = self.current
        age = time.monotonic() - self.shown_at
        if age < ALERT_SECONDS:
            pose = "urgent" if note.urgency >= 2 else "alert"
            n = self.frame // 2 % 2
        else:
            pose, n = "reading", 0
        if self.loop:
            if self.hold:
                self.hold -= 1
            else:
                self.offset = (self.offset + 1) % self.loop
        els = [
            image("sky", f"sky_{self.frame % art.SKY_FRAMES}.png", 0, 0),
            image("msg", f"strip_{self.slot}.png", art.TEXT_X - self.offset, art.TEXT_Y),
            image("luca", f"tile_{pose}_{n}.png", 0, 0),
            image("inbox", f"back_{self.slot}.png", 0, 0, display="back"),
        ]
        for i in range(min(len(self.waiting), 3)):  # yellow dots: more waiting
            els.append(rect(f"more{i}", 17, 11 + i * 2, 1, 1, "#FFDC3CFF"))
        return els

    def upload_static(self) -> None:
        for i in range(art.SKY_FRAMES):
            self.bar.upload_image(f"sky_{i}.png", art.sky(i))
        for pose, n in art.TILE_POSES.items():
            for i in range(n):
                self.bar.upload_image(f"tile_{pose}_{i}.png", art.tile(pose, i))

    # -- buttons ----------------------------------------------------------------
    def browse(self, step: int) -> None:
        """Re-show a notification from the history (step +1 = older)."""
        notes = list(self.history)
        if not notes:
            return
        here = notes.index(self.current) if self.current in notes else -1
        self.waiting.appendleft(notes[max(0, min(len(notes) - 1, here + step))])
        self.current = None
        self.wake.set()


async def collect(den: Den, source) -> None:
    async for note in source:
        den.arrive(note)


async def animate(den: Den) -> None:
    retry = 2
    while True:
        try:
            if den.current and time.monotonic() - den.shown_at >= den.duration():
                den.current = None  # done reading this one
            if den.current is None and den.waiting and not den.dnd:
                if not den.online:
                    await asyncio.to_thread(den.upload_static)
                    den.online, retry = True, 2
                await asyncio.to_thread(den.present, den.waiting.popleft())
            if den.current:
                led = art.hex_color(art.app_color(den.current.app)) if den.light else None
                await asyncio.to_thread(den.bar.draw, den.elements(), den.priority, led)
                den.light, den.on_bar = False, True
                den.frame += 1
                await asyncio.sleep(1 / den.fps)
            else:
                if den.on_bar:  # nothing left to show: step aside
                    await asyncio.to_thread(den.bar.clear)
                    den.on_bar = False
                den.wake.clear()
                try:
                    await asyncio.wait_for(den.wake.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
        except BarOffline as err:
            if den.online or retry == 2:
                print(f"🔌 Can't reach the BUSY Bar ({err}); I'll keep trying quietly")
            den.online = den.on_bar = False
            if den.current:  # show it again once the bar is back
                den.waiting.appendleft(den.current)
                den.current = None
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def listen(den: Den) -> None:
    async for event in input_events(den.bar):
        if is_selector(event):
            was, den.dnd = den.dnd, event.position == "off"
            if den.dnd != was:
                print("  🌙 Do not disturb: holding notifications" if den.dnd
                      else f"  ☀️  Back! {len(den.waiting)} waiting")
                if den.dnd and den.current:  # hush right away
                    den.current = None
                den.wake.set()
            continue
        if not den.on_bar:
            continue  # buttons belong to the bar while Luca is away
        if is_wheel(event):
            den.browse(1 if event.delta > 0 else -1)
        elif is_press(event):
            if event.button == "ok":
                den.waiting.clear()
                den.current = None
                print("  ✅ Dismissed")
            elif event.button == "start":
                den.current = None  # on to the next one (or step aside)
            elif event.button == "back":
                den.browse(1)
            den.wake.set()


async def run(den: Den, source) -> None:
    await asyncio.gather(collect(den, source), animate(den), listen(den))


def install(args) -> None:
    if args.demo:
        raise SystemExit("--install starts the real thing; leave out --demo.")
    service.check([
        ("dbus-fast (pip install dbus-fast)",
         service.importable("dbus_fast") or service.importable("dbus_next")),
        ("Pillow (pip install pillow)", service.importable("PIL")),
        ("busylib (pip install busylib)", service.importable("busylib")),
    ], required={"dbus-fast (pip install dbus-fast)", "Pillow (pip install pillow)"})
    command = [sys.executable, str(Path(__file__).resolve()), "--host", args.host,
               "--show", str(args.show), "--priority", str(args.priority), "--fps", str(args.fps)]
    if args.private:
        command.append("--private")
    if args.ignore:
        command += ["--ignore", args.ignore]
    service.install(SERVICE, "Luca Notify Den for the BUSY Bar", command, args.token,
                    "Luca now watches for notifications from login.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"),
                    help="API key, if HTTP access is set to 'key' mode (or set BUSYBAR_TOKEN)")
    ap.add_argument("--show", type=float, default=8, metavar="SECONDS",
                    help="show each notification at least this long (default 8)")
    ap.add_argument("--private", action="store_true",
                    help="show only which app it's from, not the message")
    ap.add_argument("--ignore", default="", metavar="APPS",
                    help="comma-separated app names to skip, e.g. spotify,steam")
    ap.add_argument("--priority", type=int, default=70,
                    help="draw priority 1-100; higher shows over other apps (default 70)")
    ap.add_argument("--fps", type=float, default=10, help="animation and scroll speed")
    ap.add_argument("--demo", action="store_true", help="show made-up notifications")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true",
                       help="start automatically at login (systemd user service)")
    group.add_argument("--uninstall", action="store_true", help="stop starting at login")
    args = ap.parse_args()
    if not 1 <= args.priority <= 100:
        ap.error("--priority must be between 1 and 100")

    if args.install:
        return install(args)
    if args.uninstall:
        return service.uninstall(SERVICE)
    if not args.demo and not sys.platform.startswith("linux"):
        raise SystemExit("Luca Notify Den listens on Linux's D-Bus; try --demo elsewhere.")

    ignore = {a.strip().lower() for a in args.ignore.split(",") if a.strip()}
    bar = BusyBar(args.host, APP, args.token)
    den = Den(bar, args.show, args.private, ignore, args.priority, args.fps)
    source = watcher.demo() if args.demo else watcher.watch()
    print("🔔 Listening for notifications" + (" (made-up ones)" if args.demo else " on D-Bus"))
    if ignore:
        print(f"   Skipping: {', '.join(sorted(ignore))}")
    print(f"🐺 Luca pops up on the BUSY Bar at {args.host} when one arrives.")
    print("   OK = dismiss, Start = next, Back / wheel = earlier ones. Ctrl+C to stop.")

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(run(den, source))
    except KeyboardInterrupt:
        pass
    finally:
        if den.on_bar:
            try:
                bar.clear()
            except BarOffline:
                pass
        print("\n🌙 Luca curls up in his den.")


if __name__ == "__main__":
    main()
