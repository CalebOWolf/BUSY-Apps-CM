"""
Luca Weather Den ⛅🐺, live local weather on the BUSY Bar in Frutiger Aero style.

The front strip shows the sky outside (sunshine, stars, drifting clouds,
fog, rain, snow or a thunderstorm), with Luca dressed for it: shades in the
sun, an umbrella in the rain, a scarf when it's cold, dozing at night. The
temperature, today's high and low, the chance of rain and your city take
turns beside him. The back screen becomes a Windows 7-style weather gadget
with the next three days.

    Start / Back   next / previous page
    Wheel          flip through the pages
    OK             check the weather again now

    python weather_den.py --city "Berlin"
    python weather_den.py --city "Portland, Oregon" --fahrenheit
    python weather_den.py --lat 52.52 --lon 13.41
    python weather_den.py --demo          # a tour through every kind of weather
    python weather_den.py --city Berlin --install    # Linux: start at login
    python weather_den.py --uninstall

Weather from Open-Meteo (free, no account or key). Needs Pillow; buttons also
need busylib (pip install pillow busylib).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import art  # noqa: E402
import service  # noqa: E402
from turns import TurnTaker  # noqa: E402
import weather  # noqa: E402
from busybar import BarOffline, BusyBar, image, input_events, is_press, is_wheel  # noqa: E402

APP = "luca_weather_den"
SERVICE = "luca-weather-den"
PAGE_SECONDS = 5
MANUAL_HOLD = 20
STALE_AFTER = 45 * 60      # call the reading old after 45 minutes without an update


def load_cached_report() -> weather.Report | None:
    try:
        data = json.loads(weather.CACHE.read_text()).get("report")
        if not data:
            return None
        data["place"] = weather.Place(**data["place"])
        data["days"] = [weather.Day(**d) for d in data["days"]]
        return weather.Report(**data)
    except (OSError, ValueError, TypeError, KeyError):
        return None


def save_report(report: weather.Report) -> None:
    cache = weather._read_cache()
    cache["report"] = asdict(report)
    weather._write_cache(cache)


class Den:
    def __init__(self, bar: BusyBar, priority: int, fps: float):
        self.bar, self.priority, self.fps = bar, priority, fps
        self.report: weather.Report | None = None
        self.online = False
        self.scene_uploaded: str | None = None
        self.shown_report: weather.Report | None = None
        self.shown_stale = False
        self.slot = 0
        self.pages = 0
        self.page = 0
        self.flipped_at = time.monotonic()
        self.hold_until = 0.0
        self.frame = 0
        self.refresh_now = asyncio.Event()

    @property
    def stale(self) -> bool:
        return self.report is not None and time.time() - self.report.fetched > STALE_AFTER

    def upload_static(self) -> None:
        for outfit in art.OUTFITS:
            for i in range(2):
                self.bar.upload_image(f"tile_{outfit}_{i}.png", art.tile(outfit, i))
        self.scene_uploaded = None

    def show(self, report: weather.Report) -> None:
        """Upload the sky (if the weather changed), the pages and the gadget."""
        key = art.scene_key(report.condition, report.is_day)
        if key != self.scene_uploaded:
            for i in range(art.SCENE_FRAMES):
                self.bar.upload_image(f"scene_{i:02d}.png", art.scene(key, i))
            self.scene_uploaded = key
        slot = 1 - self.slot
        texts = art.page_texts(report)
        for i, pieces in enumerate(texts):
            self.bar.upload_image(f"page_{slot}_{i}.png", art.page_image(pieces))
        self.bar.upload_image(f"back_{slot}.png", art.back_screen(report, self.stale))
        self.slot, self.pages = slot, len(texts)
        self.page %= self.pages
        self.shown_report, self.shown_stale = report, self.stale

    def flip(self, step: int = 1, by_hand: bool = False) -> None:
        if self.pages:
            self.page = (self.page + step) % self.pages
        self.flipped_at = time.monotonic()
        if by_hand:
            self.hold_until = time.monotonic() + MANUAL_HOLD

    def elements(self) -> list[dict]:
        now = time.monotonic()
        if now >= self.hold_until and now - self.flipped_at >= PAGE_SECONDS:
            self.flip()
        outfit = art.outfit(self.report)
        return [
            image("sky", f"scene_{self.frame % art.SCENE_FRAMES:02d}.png", 0, 0),
            image("words", f"page_{self.slot}_{self.page}.png", art.TEXT_X, art.TEXT_Y),
            image("luca", f"tile_{outfit}_{self.frame // 6 % 2}.png", 0, 0),
            image("gadget", f"back_{self.slot}.png", 0, 0, display="back"),
        ]


async def follow_weather(den: Den, get_report, every: float) -> None:
    """Check the weather every few minutes (or right away when asked)."""
    failures = 0
    while True:
        try:
            report = await asyncio.to_thread(get_report)
            den.report, failures = report, 0
            save_report(report)
            print(f"  ⛅ {report.place.name}: {report.temp:.0f}{report.unit}, "
                  f"{weather.describe(report.condition, report.is_day)}")
        except Exception as err:  # no internet, or Open-Meteo is having a moment
            failures += 1
            if failures == 1:
                print(f"⚠️  Couldn't get the weather ({err}); showing the last reading for now")
        den.refresh_now.clear()
        wait = every if failures == 0 else min(60 * 2 ** failures, every)
        try:
            await asyncio.wait_for(den.refresh_now.wait(), timeout=wait)
        except asyncio.TimeoutError:
            pass


async def animate(den: Den) -> None:
    retry = 2
    turn = TurnTaker(APP, den.bar)
    while True:
        try:
            if not await asyncio.to_thread(turn.check):
                await asyncio.sleep(0.5)  # another app's turn (Luca's Den)
                continue
            if den.report is None:
                await asyncio.sleep(0.5)  # nothing to show until the first reading
                continue
            if not den.online:
                await asyncio.to_thread(den.upload_static)
                den.online, retry, den.shown_report = True, 2, None
                print("🐺 Luca is watching the sky")
            if den.report is not den.shown_report or den.stale != den.shown_stale:
                await asyncio.to_thread(den.show, den.report)
            await asyncio.to_thread(den.bar.draw, den.elements(), den.priority)
            den.frame += 1
            await asyncio.sleep(1 / den.fps)
        except BarOffline as err:
            if den.online or retry == 2:
                print(f"🔌 Can't reach the BUSY Bar ({err}); I'll keep trying quietly")
            den.online = False
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def listen(den: Den) -> None:
    async for event in input_events(den.bar):
        if not den.online:
            continue
        if is_wheel(event):
            den.flip(1 if event.delta > 0 else -1, by_hand=True)
        elif is_press(event):
            if event.button == "start":
                den.flip(1, by_hand=True)
            elif event.button == "back":
                den.flip(-1, by_hand=True)
            elif event.button == "ok":
                print("  🔄 Checking the weather again")
                den.refresh_now.set()


async def run(den: Den, get_report, every: float) -> None:
    await asyncio.gather(follow_weather(den, get_report, every), animate(den), listen(den))


def install(args) -> None:
    if args.demo:
        raise SystemExit("--install starts the real thing; leave out --demo.")
    if not args.city and args.lat is None:
        raise SystemExit("Tell me where you are first, e.g. --city \"Berlin\" --install")
    service.check([
        ("Pillow (pip install pillow)", service.importable("PIL")),
        ("busylib (pip install busylib)", service.importable("busylib")),
    ], required={"Pillow (pip install pillow)"})
    command = [sys.executable, str(Path(__file__).resolve()), "--host", args.host,
               "--refresh", str(args.refresh), "--priority", str(args.priority),
               "--fps", str(args.fps)]
    if args.city:
        command += ["--city", args.city]
    else:
        command += ["--lat", str(args.lat), "--lon", str(args.lon), "--name", args.name]
    if args.fahrenheit:
        command.append("--fahrenheit")
    service.install(SERVICE, "Luca Weather Den for the BUSY Bar", command, args.token,
                    "Luca now shows the weather from login.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", help='where you are, e.g. "Berlin" or "Portland, Oregon"')
    ap.add_argument("--lat", type=float, help="latitude, instead of --city")
    ap.add_argument("--lon", type=float, help="longitude, instead of --city")
    ap.add_argument("--name", default="Home", help="what to call the place with --lat/--lon")
    ap.add_argument("--fahrenheit", action="store_true", help="°F and mph")
    ap.add_argument("--refresh", type=float, default=10, metavar="MINUTES",
                    help="how often to check the weather (default 10)")
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"),
                    help="API key, if HTTP access is set to 'key' mode (or set BUSYBAR_TOKEN)")
    ap.add_argument("--priority", type=int, default=15,
                    help="draw priority 1-100; lower lets other apps go first (default 15)")
    ap.add_argument("--fps", type=float, default=6, help="animation speed (default 6)")
    ap.add_argument("--demo", action="store_true", help="a tour through every kind of weather")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true",
                       help="Linux: start automatically at login (systemd user service)")
    group.add_argument("--uninstall", action="store_true", help="Linux: stop starting at login")
    args = ap.parse_args()
    if (args.lat is None) != (args.lon is None):
        ap.error("give both --lat and --lon")
    if not 1 <= args.priority <= 100:
        ap.error("--priority must be between 1 and 100")
    if args.refresh < 1:
        ap.error("--refresh must be at least 1 minute (Open-Meteo updates every 15)")

    if args.install:
        return install(args)
    if args.uninstall:
        return service.uninstall(SERVICE)

    bar = BusyBar(args.host, APP, args.token)
    den = Den(bar, args.priority, args.fps)
    if args.demo:
        step = [0]

        def get_report():
            step[0] += 1
            return weather.demo(step[0] - 1, args.fahrenheit)
        every = 8.0
        print("⛅ Demo: touring through every kind of weather")
    else:
        if args.lat is not None:
            place = weather.Place(args.name, args.lat, args.lon)
        elif args.city:
            try:
                place = weather.find_place(args.city)
            except OSError as err:
                raise SystemExit(f"Couldn't look up '{args.city}' ({err}). Are you online? "
                                 "You can also give --lat and --lon.")
        else:
            ap.error('tell me where you are with --city "Berlin" (or --lat and --lon), or try --demo')
        den.report = load_cached_report()
        if den.report and (den.report.place != place or den.report.fahrenheit != args.fahrenheit):
            den.report = None  # that was somewhere else

        def get_report():
            return weather.fetch(place, args.fahrenheit)
        every = args.refresh * 60
        where = f"{place.name}" + (f" ({place.region})" if place.region else "")
        print(f"⛅ Weather for {where}, checked every {args.refresh:g} minutes")
    print(f"🐺 Showing on the BUSY Bar at {args.host}.")
    print("   Start/Back or the wheel = change page, OK = check again. Ctrl+C to stop.")

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(run(den, get_report, every))
    except KeyboardInterrupt:
        pass
    finally:
        if den.online:
            try:
                bar.clear()
            except BarOffline:
                pass
        print("\n🌙 Luca heads back into his den.")


if __name__ == "__main__":
    main()
