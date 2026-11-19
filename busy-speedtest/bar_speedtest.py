"""
BUSY Speedtest 📶, a simple internet speed test for the BUSY Bar.

Tests your ping, download and upload speed (against Cloudflare's speed test
servers) and shows the results: the front strip takes turns showing each
reading, and the back screen shows all three at once. While a test runs you
see the speed climb live, with a progress line along the bottom.

    OK      run the test again
    Back    show the next reading

    python bar_speedtest.py                 # test now, then every 60 minutes
    python bar_speedtest.py --every 15      # test every 15 minutes (0 = only on OK)
    python bar_speedtest.py --no-bar        # just run one test in the terminal
    python bar_speedtest.py --install       # Linux: start automatically at login
    python bar_speedtest.py --uninstall

Needs Pillow; buttons also need busylib (pip install pillow busylib).
--no-bar needs nothing but Python.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))
sys.path.insert(0, str(HERE))
from tester import DEFAULT_SERVER, Result, SpeedTest, TestFailed, format_speed  # noqa: E402

APP = "busy_speedtest"
SERVICE = "busy-speedtest"
PAGE_FOR = 4          # seconds each reading stays on the front strip
LED_DONE = "#3CC8FFFF"


def describe(result: Result) -> str:
    down, up = format_speed(result.down_mbps), format_speed(result.up_mbps)
    return (f"↓ {down[0]} {down[1].capitalize()}   ↑ {up[0]} {up[1].capitalize()}   "
            f"ping {result.ping_ms:.0f} ms (±{result.jitter_ms:.0f})"
            + (f"   via {result.server}" if result.server else ""))


# --------------------------------------------------------------------------
# On the bar
# --------------------------------------------------------------------------
class SpeedApp:
    def __init__(self, bar, test: SpeedTest, every: float, priority: int):
        self.bar, self.test, self.every, self.priority = bar, test, every, priority
        self.result: Result | None = None
        self.error = ""
        self.running = False
        self.next_test = 0.0          # monotonic time of the next automatic test
        self.page = 0
        self.page_since = time.monotonic()
        self.flash = False
        self.online = False
        self.slot = 0

    # -- testing -----------------------------------------------------------
    def start_test(self) -> None:
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._test, daemon=True, name="speedtest").start()

    def _test(self) -> None:
        print("📶 Testing…", flush=True)
        try:
            self.result = self.test.run()
            self.error = ""
            self.flash = True
            self.page, self.page_since = 0, time.monotonic()
            print("   " + describe(self.result), flush=True)
        except TestFailed as err:
            self.error = str(err)
            print(f"⚠️  The test failed: {err}", flush=True)
        finally:
            self.running = False
            self.next_test = time.monotonic() + self.every * 60 if self.every else float("inf")

    # -- what to show ------------------------------------------------------
    def front_image(self):
        import art
        t = self.test
        if self.running:
            if t.phase == "ping":
                value = f"{t.live_ping:.0f} MS" if t.live_ping else "..."
                return art.front("PING", value, art.PING, t.progress)
            if t.phase in ("download", "upload"):
                color, arrow = (art.DOWN, "↓") if t.phase == "download" else (art.UP, "↑")
                number, unit = format_speed(t.live_mbps)
                return art.front(f"{arrow} {t.phase}", f"{number} {unit}", color, t.progress)
            return art.front("SPEEDTEST", "STARTING", art.WHITE, 0.0)
        if self.result is None:
            if self.error:
                return art.front("NO CONNECTION", "OK = RETRY", art.ERROR)
            return art.front("SPEEDTEST", "OK = START", art.WHITE)
        r = self.result
        pages = [
            ("↓ DOWNLOAD", " ".join(format_speed(r.down_mbps)), art.DOWN),
            ("↑ UPLOAD", " ".join(format_speed(r.up_mbps)), art.UP),
            ("PING", f"{r.ping_ms:.0f} MS", art.PING),
        ]
        if self.error:
            pages.append(("LAST TEST", "FAILED", art.ERROR))
        label, value, color = pages[self.page % len(pages)]
        return art.front(label, value, color)

    def back_image(self):
        import art
        state = "testing" if self.running else ("error" if self.error else "done")
        return art.back(self.result, state, self.error[:40])

    def frame(self) -> list[dict]:
        """Upload this moment's pictures and say where they go (runs off the event loop)."""
        from busybar import image
        now = time.monotonic()
        if not self.running and now - self.page_since >= PAGE_FOR:
            self.page, self.page_since = self.page + 1, now
        # two slots, so the bar never shows a picture halfway through replacing it
        self.slot = 1 - self.slot
        self.bar.upload_image(f"front_{self.slot}.png", self.front_image())
        self.bar.upload_image(f"back_{self.slot}.png", self.back_image())
        return [image("front", f"front_{self.slot}.png", 0, 0),
                image("back", f"back_{self.slot}.png", 0, 0, display="back")]


async def animate(app: SpeedApp) -> None:
    from busybar import BarOffline
    retry = 2
    while True:
        try:
            if not app.running and time.monotonic() >= app.next_test:
                app.start_test()
            elements = await asyncio.to_thread(app.frame)
            led = LED_DONE if app.flash else None
            await asyncio.to_thread(app.bar.draw, elements, app.priority, led)
            app.flash = False
            if not app.online:
                app.online, retry = True, 2
                print("📟 Showing on the BUSY Bar", flush=True)
            await asyncio.sleep(0.25 if app.running else 1.0)
        except BarOffline as err:
            if app.online or retry == 2:
                print(f"🔌 BUSY Bar trouble: {err}; I'll keep trying quietly", flush=True)
            app.online = False
            app.bar.forget_uploads()
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def listen(app: SpeedApp) -> None:
    from busybar import input_events, is_press
    async for event in input_events(app.bar):
        if not is_press(event):
            continue
        if event.button == "ok":
            app.start_test()
        elif event.button == "back" and not app.running:
            app.page, app.page_since = app.page + 1, time.monotonic()


async def run(app: SpeedApp) -> None:
    await asyncio.gather(animate(app), listen(app))


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------
def install(args) -> None:
    import service
    service.check([
        ("Pillow (pip install pillow)", service.importable("PIL")),
        ("busylib (pip install busylib)", service.importable("busylib")),
    ], required={"Pillow (pip install pillow)"})
    command = [sys.executable, str(Path(__file__).resolve()), "--host", args.host,
               "--priority", str(args.priority), "--every", str(args.every),
               "--seconds", str(args.seconds)]
    if args.server != DEFAULT_SERVER:
        command += ["--server", args.server]
    service.install(SERVICE, "BUSY Speedtest for the BUSY Bar", command, args.token,
                    "The speed test now runs on the bar from login.")


def terminal_only(test: SpeedTest) -> None:
    print("📶 Testing your connection (about 20 seconds)…")
    stop = threading.Event()

    def follow() -> None:
        while not stop.wait(0.5):
            if test.phase == "ping":
                line = f"   ping      {test.live_ping:6.0f} ms"
            elif test.phase in ("download", "upload"):
                n, u = format_speed(test.live_mbps)
                line = f"   {test.phase:9} {n:>6} {u.capitalize()}  {'▮' * int(test.progress * 20):20}"
            else:
                continue
            print("\r" + line.ljust(60), end="", flush=True)

    watcher = threading.Thread(target=follow, daemon=True)
    watcher.start()
    try:
        result = test.run()
    except TestFailed as err:
        stop.set()
        print(f"\r⚠️  The test failed: {err}".ljust(60))
        raise SystemExit(1)
    stop.set()
    watcher.join()
    print("\r" + " " * 60 + "\r", end="")
    down, up = format_speed(result.down_mbps), format_speed(result.up_mbps)
    print(f"   Download  {down[0]:>6} {down[1].capitalize()}")
    print(f"   Upload    {up[0]:>6} {up[1].capitalize()}")
    print(f"   Ping      {result.ping_ms:>6.0f} ms  (jitter {result.jitter_ms:.0f} ms)")
    if result.server:
        print(f"   Server    {result.server}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--every", type=float, default=60,
                    help="minutes between automatic tests (default 60; 0 = only when you press OK)")
    ap.add_argument("--seconds", type=float, default=8,
                    help="how long the download and upload parts each take (default 8)")
    ap.add_argument("--server", default=DEFAULT_SERVER,
                    help=f"speed test server (default {DEFAULT_SERVER})")
    ap.add_argument("--no-bar", action="store_true",
                    help="run one test and print the results here, without the bar")
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"),
                    help="API key, if HTTP access is set to 'key' mode (or set BUSYBAR_TOKEN)")
    ap.add_argument("--priority", type=int, default=30, help="draw priority 1-100 (default 30)")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true",
                       help="Linux: start automatically at login (systemd user service)")
    group.add_argument("--uninstall", action="store_true", help="Linux: stop starting at login")
    args = ap.parse_args()
    if not 1 <= args.priority <= 100:
        ap.error("--priority must be between 1 and 100")
    if args.every < 0 or args.seconds <= 0:
        ap.error("--every can't be negative, and --seconds must be more than 0")
    try:
        test = SpeedTest(args.server, args.seconds)
    except ValueError as err:
        ap.error(str(err))

    if args.no_bar:
        return terminal_only(test)
    if args.install:
        return install(args)
    if args.uninstall:
        import service
        return service.uninstall(SERVICE)

    try:
        import art  # noqa: F401  (needs Pillow)
    except ImportError:
        raise SystemExit("Pillow is needed to draw on the bar: pip install pillow "
                         "(or use --no-bar to test in the terminal)")
    from busybar import BarOffline, BusyBar
    bar = BusyBar(args.host, APP, args.token)
    app = SpeedApp(bar, test, args.every, args.priority)
    when = f"every {args.every:g} minutes" if args.every else "when you press OK"
    print(f"📶 BUSY Speedtest on the bar at {args.host}: testing now, then {when}.")
    print("   OK = test again, Back = next reading. Ctrl+C to stop.")

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(run(app))
    except KeyboardInterrupt:
        pass
    finally:
        if app.online:
            try:
                bar.clear()
            except BarOffline:
                pass
        print("\n👋 Speedtest stopped.")


if __name__ == "__main__":
    main()
