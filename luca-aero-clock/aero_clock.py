"""
Luca Aero Clock 🕰️🐺, a glossy Frutiger Aero desk clock for the BUSY Bar.

Big glossy digits on a sky that follows the real time of day: stars and the
moon (in its real phase tonight), a violet dawn, the sun crossing the sky,
a golden sunset. Luca keeps you company: coffee in the morning, sunny by
day, cozy in the evening, a nightcap when it's late, and a little howl on
the hour. Every so often the date takes a turn. The back screen becomes a
Windows 7-style analog clock gadget with sunrise and sunset times.

    OK      show the date
    Start   Luca howls
    Back    switch between 24-hour and 12-hour time

    python aero_clock.py                  # uses Weather Den's place, or guesses
    python aero_clock.py --lat 52.52 --lon 13.41 --12h
    python aero_clock.py --no-chime       # no howl on the hour
    python aero_clock.py --install        # Linux: start automatically at login
    python aero_clock.py --uninstall

Needs Pillow; buttons also need busylib (pip install pillow busylib).
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
from turns import TurnTaker  # noqa: E402
import sky  # noqa: E402
from busybar import BarOffline, BusyBar, image, input_events, is_press  # noqa: E402

APP = "luca_aero_clock"
SERVICE = "luca-aero-clock"
FPS = 2                   # two frames a second: the colon blinks with the seconds
DATE_EVERY = 30           # show the date for a moment every 30 seconds…
DATE_FOR = 4              # …for 4 seconds
HOWL_FOR = 4
CHIME_HOURS = range(8, 22)  # howl on the hour from 08:00 to 21:00


class Clock:
    def __init__(self, bar: BusyBar, lat: float, lon: float, hour24: bool, chime: bool,
                 priority: int):
        self.bar, self.lat, self.lon = bar, lat, lon
        self.hour24, self.chime, self.priority = hour24, chime, priority
        self.online = False
        self.sky_minute = None
        self.sky_slot = 0
        self.sun_day = None
        self.rise = self.set_ = None
        self.elev = 0.0
        self.back_slot = 0
        self.date_until = 0.0
        self.howl_until = 0.0
        self.chimed_hour = None
        self.frame = 0
        self.light = False

    def upload_static(self) -> None:
        for ch in art.BIG_CHARS:
            self.bar.upload_image(f"big_{'colon' if ch == ':' else ch}.png", art.big_char(ch))
        for mood, n in art.MOODS.items():
            for i in range(n):
                self.bar.upload_image(f"tile_{mood}_{i}.png", art.tile(mood, i))
        self.sky_minute = None

    def refresh_sky(self, now: datetime) -> None:
        """Once a minute: redraw the sky and the date for right now."""
        stamp = now.replace(second=0, microsecond=0)
        if stamp == self.sky_minute:
            return
        if now.date() != self.sun_day:
            self.rise, self.set_ = sky.sun_times(now.date(), self.lat, self.lon, now.tzinfo)
            self.sun_day = now.date()
        self.elev = sky.sun_elevation(now, self.lat, self.lon)
        frac = None
        if self.rise and self.set_ and self.rise <= now <= self.set_:
            frac = (now - self.rise) / (self.set_ - self.rise)
        phase = sky.moon_phase(now)
        slot = 1 - self.sky_slot
        for i in range(2):
            self.bar.upload_image(f"sky_{slot}_{i}.png", art.sky(self.elev, frac, phase, i))
        self.bar.upload_image(f"date_{slot}.png", art.date_image(now))
        self.sky_slot, self.sky_minute = slot, stamp

    def upload_back(self, now: datetime) -> None:
        slot = 1 - self.back_slot
        self.bar.upload_image(f"back_{slot}.png", art.back_screen(now, self.rise, self.set_, self.hour24))
        self.back_slot = slot

    def elements(self, now: datetime) -> list[dict]:
        mono = time.monotonic()
        if self.chime and now.minute == 0 and now.hour in CHIME_HOURS and self.chimed_hour != now.hour:
            self.chimed_hour, self.howl_until, self.light = now.hour, mono + HOWL_FOR, True
            print(f"  🐺 Awoo! It's {now.strftime('%H:%M')}")
        if now.second % DATE_EVERY == DATE_EVERY - DATE_FOR and mono > self.date_until:
            self.date_until = mono + DATE_FOR
        els = [image("sky", f"sky_{self.sky_slot}_{self.frame % 2}.png", 0, 0)]
        if mono < self.date_until:
            els.append(image("date", f"date_{self.sky_slot}.png", art.AREA_X, 0))
        else:
            text = now.strftime("%H:%M") if self.hour24 else now.strftime("%I:%M").lstrip("0")
            for i, (ch, x) in enumerate(art.time_layout(text)):
                if ch == ":" and self.frame % 2:
                    continue  # the colon blinks once a second
                els.append(image(f"d{i}", f"big_{'colon' if ch == ':' else ch}.png", x, art.CLOCK_Y))
        mood = "howl" if mono < self.howl_until else art.mood_for(now, self.elev > 0)
        els.append(image("luca", f"tile_{mood}_{self.frame % 2}.png", 0, 0))
        els.append(image("gadget", f"back_{self.back_slot}.png", 0, 0, display="back"))
        return els


async def animate(clock: Clock) -> None:
    retry = 2
    turn = TurnTaker(APP, clock.bar)
    while True:
        try:
            if not await asyncio.to_thread(turn.check):
                await asyncio.sleep(0.5)  # another app's turn (Luca's Den)
                continue
            now = datetime.now().astimezone()
            if not clock.online:
                await asyncio.to_thread(clock.upload_static)
                clock.online, retry = True, 2
                print("🐺 Luca is keeping time")
            await asyncio.to_thread(clock.refresh_sky, now)
            if clock.frame % 2 == 0:
                await asyncio.to_thread(clock.upload_back, now)
            led = "#FFE678FF" if clock.light else None
            await asyncio.to_thread(clock.bar.draw, clock.elements(now), clock.priority, led)
            clock.light = False
            clock.frame += 1
            # wake on the half second, so the colon ticks in step with the real seconds
            await asyncio.sleep(0.5 - (time.time() % 0.5) + 0.01)
        except BarOffline as err:
            if clock.online or retry == 2:
                print(f"🔌 Can't reach the BUSY Bar ({err}); I'll keep trying quietly")
            clock.online = False
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def listen(clock: Clock) -> None:
    async for event in input_events(clock.bar):
        if not is_press(event):
            continue
        if event.button == "ok":
            clock.date_until = time.monotonic() + DATE_FOR
        elif event.button == "start":
            clock.howl_until = time.monotonic() + HOWL_FOR
        elif event.button == "back":
            clock.hour24 = not clock.hour24
            clock.sky_minute = None  # redraw the gadget's times too
            print(f"  🕰️  {'24' if clock.hour24 else '12'}-hour time")


async def run(clock: Clock) -> None:
    await asyncio.gather(animate(clock), listen(clock))


def install(args) -> None:
    service.check([
        ("Pillow (pip install pillow)", service.importable("PIL")),
        ("busylib (pip install busylib)", service.importable("busylib")),
    ], required={"Pillow (pip install pillow)"})
    command = [sys.executable, str(Path(__file__).resolve()), "--host", args.host,
               "--priority", str(args.priority)]
    if args.lat is not None:
        command += ["--lat", str(args.lat), "--lon", str(args.lon)]
    if args.twelve:
        command.append("--12h")
    if args.no_chime:
        command.append("--no-chime")
    service.install(SERVICE, "Luca Aero Clock for the BUSY Bar", command, args.token,
                    "Luca now keeps time on the bar from login.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat", type=float, help="latitude, for the sun's real path")
    ap.add_argument("--lon", type=float, help="longitude, for the sun's real path")
    ap.add_argument("--12h", dest="twelve", action="store_true", help="12-hour time")
    ap.add_argument("--no-chime", action="store_true", help="no howl on the hour")
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"),
                    help="API key, if HTTP access is set to 'key' mode (or set BUSYBAR_TOKEN)")
    ap.add_argument("--priority", type=int, default=10,
                    help="draw priority 1-100 (default 10: everything else goes first)")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true",
                       help="Linux: start automatically at login (systemd user service)")
    group.add_argument("--uninstall", action="store_true", help="Linux: stop starting at login")
    args = ap.parse_args()
    if (args.lat is None) != (args.lon is None):
        ap.error("give both --lat and --lon")
    if not 1 <= args.priority <= 100:
        ap.error("--priority must be between 1 and 100")

    if args.install:
        return install(args)
    if args.uninstall:
        return service.uninstall(SERVICE)

    if args.lat is not None:
        lat, lon, where = args.lat, args.lon, f"{args.lat:.2f}, {args.lon:.2f}"
    else:
        lat, lon, where = sky.guess_place()
    bar = BusyBar(args.host, APP, args.token)
    clock = Clock(bar, lat, lon, not args.twelve, not args.no_chime, args.priority)
    now = datetime.now().astimezone()
    rise, set_ = sky.sun_times(now.date(), lat, lon, now.tzinfo)
    print(f"🕰️  Aero Clock. Sun's path for {where}" + (
        f": sunrise {rise:%H:%M}, sunset {set_:%H:%M}" if rise and set_ else ""))
    print(f"🐺 Showing on the BUSY Bar at {args.host}.")
    print("   OK = date, Start = howl, Back = 12/24-hour. Ctrl+C to stop.")

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(run(clock))
    except KeyboardInterrupt:
        pass
    finally:
        if clock.online:
            try:
                bar.clear()
            except BarOffline:
                pass
        print("\n🌙 Luca stops the clock.")


if __name__ == "__main__":
    main()
