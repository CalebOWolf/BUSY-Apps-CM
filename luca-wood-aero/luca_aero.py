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
    python luca_aero.py --howl 5m         # nap after 5 minutes (default 10m)

Press Ctrl+C to stop; the app clears its screens on the way out.
Button reactions need the official `busylib` package (pip install busylib).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

APP = "luca_wood_aero"
BUILD = Path(__file__).parent / "build"

# What each control makes Luca do.
BUTTON_MOODS = {"ok": "howl", "back": "wave", "start": "yay"}


class BusyBar:
    def __init__(self, host: str, token: str | None = None):
        self.host = host
        self.base = f"http://{host}/api"
        self.token = token

    def _call(self, method: str, path: str, params: dict | None = None,
              body: bytes | None = None, content_type: str | None = None) -> dict:
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, data=body, method=method)
        if content_type:
            req.add_header("Content-Type", content_type)
        if self.token:
            req.add_header("X-API-Token", self.token)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as err:
            detail = err.read().decode(errors="replace")
            raise SystemExit(f"BUSY Bar said {err.code} for {method} {path}: {detail}")
        return json.loads(raw) if raw else {}

    def upload(self, filename: str, data: bytes) -> None:
        self._call("POST", "/assets/upload",
                   params={"application_name": APP, "file": filename},
                   body=data, content_type="application/octet-stream")

    def draw(self, elements: list[dict], priority: int = 50) -> None:
        payload = {"application_name": APP, "priority": priority, "elements": elements}
        self._call("POST", "/display/draw", body=json.dumps(payload).encode(),
                   content_type="application/json")

    def clear(self) -> None:
        self._call("DELETE", "/display/draw", params={"application_name": APP})


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


async def animate(bar: BusyBar, luca: Luca, fps: float) -> None:
    while True:
        front, back = luca.next_frame()
        await asyncio.to_thread(bar.draw, [
            {"id": "sky", "type": "image", "path": front, "display": "front", "x": 0, "y": 0},
            {"id": "window", "type": "image", "path": back, "display": "back", "x": 0, "y": 0},
        ])
        await asyncio.sleep(1 / fps)


async def listen(bar: BusyBar, luca: Luca) -> None:
    """Follow the bar's live status stream and turn presses into moods."""
    try:
        from busylib import AsyncBusyBar
        from busylib.features import ButtonEvent, EncoderEvent, input_events
    except ImportError:
        print("ℹ️  Install busylib (pip install busylib) to make Luca react to buttons.")
        return

    client = AsyncBusyBar(bar.host, token=bar.token)
    delay = 1
    while True:
        try:
            async for message in client.stream_status_ws():
                delay = 1
                if not isinstance(message, dict):
                    continue
                for event in input_events(message):
                    if isinstance(event, ButtonEvent) and event.is_press:
                        mood = BUTTON_MOODS.get(event.button)
                        if mood:
                            print(f"  {event.button.upper()} pressed → {mood}")
                            luca.react(mood)
                    elif isinstance(event, EncoderEvent) and event.delta:
                        luca.react("look_right" if event.delta > 0 else "look_left")
        except Exception as err:  # connection dropped: try again, gently
            print(f"⚠️  Lost the button stream ({err}); retrying in {delay}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


async def run(bar: BusyBar, luca: Luca, fps: float) -> None:
    await asyncio.gather(animate(bar, luca, fps), listen(bar, luca))


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
    ap.add_argument("--token", help="API key, if HTTP access is set to 'key' mode")
    ap.add_argument("--fps", type=float, default=7, help="animation speed")
    ap.add_argument("--howl", type=nap_time, default="10m", metavar="TIME",
                    help="nap after this long without a press: 1m, 2m, 5m, 10m, "
                         "or any number of minutes; add 's' for seconds (default: 10m)")
    args = ap.parse_args()

    manifest_file = BUILD / "manifest.json"
    if not manifest_file.exists():
        raise SystemExit("No artwork yet. Run `python render.py` first.")
    manifest = json.loads(manifest_file.read_text())

    bar = BusyBar(args.host, args.token)
    files = sorted({f for m in manifest.values() for f in [*m["frames"], m["back"]]})
    print(f"🐺 Uploading {len(files)} images to the BUSY Bar at {args.host}…")
    for name in files:
        bar.upload(name, (BUILD / name).read_bytes())

    print("✨ Luca is live! OK = howl, Back = hey, Start = yay, wheel = look around.")
    print("   Press Ctrl+C to stop.")
    try:
        asyncio.run(run(bar, Luca(manifest, args.howl), args.fps))
    except KeyboardInterrupt:
        pass
    finally:
        bar.clear()
        print("\n🌙 Luca says goodnight. Screens cleared.")


if __name__ == "__main__":
    main()
