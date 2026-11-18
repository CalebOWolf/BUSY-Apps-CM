"""
Luca Wood Aero 🐺, a Frutiger Aero / Windows 7 style app for the BUSY Bar.

Uploads the artwork from build/ to the bar, animates the front strip and
shows the Aero window on the back, and makes Luca react to the bar's controls:

    OK      Luca howls  "AWOOO!"
    Back    Luca winks  "HEY ♥"
    Start   Luca jumps  "YAY!"
    Wheel   Luca looks left / right
    (idle)  after a while Luca falls asleep under the moon; any press wakes him

    python render.py                      # once, to build the artwork
    python luca_aero.py                   # BUSY Bar on USB (10.0.4.20)
    python luca_aero.py --host 192.168.1.42 --token YOUR_KEY   # over Wi-Fi
    python luca_aero.py --den 5m          # nap after 5 minutes (default 10m)

Press Ctrl+C to stop; the app clears its screens on the way out.
Button reactions need the official `busylib` package (pip install busylib).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from busybar import BarOffline, BusyBar, image, input_events, is_press, is_wheel  # noqa: E402

APP = "luca_wood_aero"
BUILD = Path(__file__).parent / "build"

# What each control makes Luca do.
BUTTON_MOODS = {"ok": "howl", "back": "wave", "start": "yay"}


class Luca:
    """Which mood Luca is in and which frame comes next."""

    def __init__(self, manifest: dict, sleep_after: float):
        self.manifest = manifest
        self.sleep_after = sleep_after
        self.last_input = time.monotonic()
        self.set("idle")

    def set(self, mood: str) -> None:
        self.mood, self.frame = mood, 0

    def react(self, mood: str) -> None:
        self.last_input = time.monotonic()
        # Waking up from a nap always starts with a hello.
        self.set("wave" if self.mood == "sleep" else mood)

    def next_frame(self) -> tuple[str, str]:
        m = self.manifest[self.mood]
        if self.frame >= len(m["frames"]):
            if m["loop"]:
                self.frame = 0
            else:  # a reaction finished, back to chilling
                self.set("idle")
                m = self.manifest["idle"]
        if self.mood == "idle" and time.monotonic() - self.last_input > self.sleep_after:
            self.set("sleep")
            m = self.manifest["sleep"]
        name = m["frames"][self.frame]
        self.frame += 1
        return name, m["back"]


def upload_artwork(bar: BusyBar, manifest: dict) -> None:
    files = sorted({f for m in manifest.values() for f in [*m["frames"], m["back"]]})
    print(f"🐺 Uploading {len(files)} images to the BUSY Bar at {bar.host}…")
    for name in files:
        bar.upload(name, (BUILD / name).read_bytes())


async def animate(bar: BusyBar, luca: Luca, manifest: dict, fps: float) -> None:
    """Play Luca's frames, and ride out the bar going away (re-uploading the
    artwork when it comes back)."""
    online, retry = False, 2
    while True:
        try:
            if not online:
                await asyncio.to_thread(upload_artwork, bar, manifest)
                online, retry = True, 2
                print("✨ Luca is live! OK = howl, Back = hey, Start = yay, wheel = look around.")
            front, back = luca.next_frame()
            await asyncio.to_thread(bar.draw, [
                image("sky", front, 0, 0),
                image("window", back, 0, 0, display="back"),
            ])
            await asyncio.sleep(1 / fps)
        except BarOffline as err:
            if online or retry == 2:
                print(f"🔌 Can't reach the BUSY Bar ({err}); I'll keep trying quietly")
            online = False
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def listen(bar: BusyBar, luca: Luca) -> None:
    """Turn the bar's button presses and wheel turns into moods."""
    async for event in input_events(bar):
        if is_press(event):
            mood = BUTTON_MOODS.get(event.button)
            if mood:
                print(f"  {event.button.upper()} pressed → {mood}")
                luca.react(mood)
        elif is_wheel(event):
            luca.react("look_right" if event.delta > 0 else "look_left")


async def run(bar: BusyBar, luca: Luca, manifest: dict, fps: float) -> None:
    await asyncio.gather(animate(bar, luca, manifest, fps), listen(bar, luca))


def nap_time(text: str) -> float:
    """'10m', '10' or '2.5' → minutes; '90s' → seconds. Returns seconds."""
    value = text.strip().lower()
    unit = 1 if value.endswith("s") else 60
    number = value.rstrip("ms").strip()
    try:
        seconds = float(number) * unit
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' isn't a time; try 1m, 2m, 5m or 10m")
    if seconds <= 0:
        raise argparse.ArgumentTypeError("the nap time has to be more than zero")
    return seconds


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"),
                    help="API key, if HTTP access is set to 'key' mode (or set BUSYBAR_TOKEN)")
    ap.add_argument("--fps", type=float, default=7, help="animation speed")
    ap.add_argument("--den", type=nap_time, default="10m", metavar="TIME",
                    help="nap after this long without a press: 1m, 2m, 5m, 10m, "
                         "or any number of minutes; add 's' for seconds (default: 10m)")
    args = ap.parse_args()

    manifest_file = BUILD / "manifest.json"
    if not manifest_file.exists():
        raise SystemExit("No artwork yet. Run `python render.py` first.")
    manifest = json.loads(manifest_file.read_text())

    bar = BusyBar(args.host, APP, args.token)
    print("   Press Ctrl+C to stop.")
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(run(bar, Luca(manifest, args.den), manifest, args.fps))
    except KeyboardInterrupt:
        pass
    finally:
        try:
            bar.clear()
            print("\n🌙 Luca says goodnight. Screens cleared.")
        except BarOffline:
            print("\n🌙 Luca says goodnight.")


if __name__ == "__main__":
    main()
