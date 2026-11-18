"""
Luca Now Playing 🎵🐺, a Frutiger Aero "now playing" strip for the BUSY Bar.

Shows the song playing on this computer: Luca bops along in his headphones,
the title and artist scroll across a glossy Aero sky, and a progress bar
fills up. The back screen becomes "Luca Player", a Windows 7-style media
player window. The bar's buttons control your music:

    OK      play / pause
    Start   next song      (Luca hops)
    Back    previous song

    python now_playing.py                 # BUSY Bar on USB (10.0.4.20)
    python now_playing.py --host 192.168.1.42 --token YOUR_KEY   # over Wi-Fi
    python now_playing.py --demo          # try it with a pretend playlist

Press Ctrl+C to stop; the app clears its screens on the way out.
Needs Pillow; button control also needs busylib (pip install pillow busylib).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request

import art
import media

APP = "luca_now_playing"
BUTTON_ACTIONS = {"ok": "toggle", "start": "next", "back": "previous"}


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

    def upload_image(self, filename: str, image) -> None:
        buf = io.BytesIO()
        image.save(buf, "PNG")
        self.upload(filename, buf.getvalue())

    def draw(self, elements: list[dict], priority: int = 50) -> None:
        payload = {"application_name": APP, "priority": priority, "elements": elements}
        self._call("POST", "/display/draw", body=json.dumps(payload).encode(),
                   content_type="application/json")

    def clear(self) -> None:
        self._call("DELETE", "/display/draw", params={"application_name": APP})


def image(id_: str, path: str, x: int, y: int, display: str = "front") -> dict:
    return {"id": id_, "type": "image", "path": path, "display": display, "x": x, "y": y}


def bar(id_: str, x: int, y: int, w: int, h: int, color: str, display: str = "front") -> dict:
    return {"id": id_, "type": "rectangle", "display": display, "x": x, "y": y,
            "width": w, "height": h, "fill": "solid", "fill_colors": [color],
            "border_width": 0}


def clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


class Screen:
    """What's on the bar right now, and what changes from frame to frame."""

    def __init__(self, bar_: BusyBar, player):
        self.bar = bar_
        self.player = player
        self.track = media.NOTHING
        self.shown_key = None
        self.slot = 0              # song art alternates between two file names
        self.strip_loop = 0
        self.offset = 0
        self.hold = 0
        self.hop_until = 0.0
        self.frame = 0
        self.refresh = asyncio.Event()

    def upload_static(self) -> None:
        for i in range(art.BG_FRAMES):
            self.bar.upload_image(f"bg_{i:02d}.png", art.background(i))
        for pose, n in art.TILE_POSES.items():
            for i in range(n):
                self.bar.upload_image(f"tile_{pose}_{i}.png", art.tile(pose, i))

    def show_song(self, track: media.Track) -> None:
        """Render and upload this song's text strip and back screen."""
        slot = 1 - self.slot
        if track.active:
            text = f"{track.title} - {track.artist}" if track.artist else track.title
        else:
            text = "No music"
        strip, loop = art.text_strip(text, dim=not track.playing)
        self.bar.upload_image(f"strip_{slot}.png", strip)
        self.bar.upload_image(f"back_{slot}.png", art.back_screen(
            track.title, track.artist, track.album, track.playing))
        new_song = self.shown_key is None or self.shown_key[:3] != track.key[:3]
        self.slot, self.strip_loop, self.shown_key = slot, loop, track.key
        if new_song:
            self.offset, self.hold = 0, 15

    def elements(self) -> list[dict]:
        t = self.track
        now = time.monotonic()
        if not t.active:
            pose, n = "idle", 0
        elif now < self.hop_until:
            pose, n = "hop", self.frame // 2 % 4
        elif t.playing:
            pose, n = "play", self.frame // 3 % 4
        else:
            pose, n = "pause", 0

        # Scroll long titles while the music plays (with a pause at the start).
        if self.strip_loop and t.playing:
            if self.hold:
                self.hold -= 1
            else:
                self.offset += 1
                if self.offset >= self.strip_loop:
                    self.offset, self.hold = 0, 15

        els = [
            image("sky", f"bg_{self.frame % art.BG_FRAMES:02d}.png", 0, 0),
            image("song", f"strip_{self.slot}.png", art.TEXT_X - self.offset, art.TEXT_Y),
            image("luca", f"tile_{pose}_{n}.png", 0, 0),
            image("window", f"back_{self.slot}.png", 0, 0, display="back"),
        ]
        if t.active and t.duration:
            p = max(0.0, min(1.0, t.position_now() / t.duration))
            els.append(bar("track", art.TEXT_X, art.BAR_Y, art.TEXT_W, 1, "#0A3278FF"))
            if round(art.TEXT_W * p):
                els.append(bar("fill", art.TEXT_X, art.BAR_Y, round(art.TEXT_W * p), 1, "#78FFC8FF"))
            x0, y0, x1, y1 = art.BACK_BAR
            if round((x1 - x0) * p):
                els.append(bar("back_fill", x0, y0, round((x1 - x0) * p), y1 - y0 + 1,
                               "#5A5A5AFF", display="back"))
            tx, ty = art.BACK_TIME_XY
            els.append({"id": "time", "type": "text", "display": "back", "font": "small",
                        "text": f"{clock(t.position_now())} / {clock(t.duration)}",
                        "color": "#282828FF", "x": tx, "y": ty, "align": "top_right"})
        return els


async def follow_music(screen: Screen) -> None:
    while True:
        try:
            track = await screen.player.read()
        except Exception as err:  # a player hiccup shouldn't stop the show
            print(f"⚠️  Couldn't read the music player: {err}")
            track = media.NOTHING
        screen.track = track
        if track.key != screen.shown_key:
            if track.active:
                state = "▶" if track.playing else "⏸"
                print(f"  {state} {track.title}" + (f" - {track.artist}" if track.artist else ""))
            await asyncio.to_thread(screen.show_song, track)
        screen.refresh.clear()
        try:
            await asyncio.wait_for(screen.refresh.wait(), timeout=1)
        except asyncio.TimeoutError:
            pass


async def animate(screen: Screen, fps: float) -> None:
    while True:
        await asyncio.to_thread(screen.bar.draw, screen.elements())
        screen.frame += 1
        await asyncio.sleep(1 / fps)


async def listen(screen: Screen) -> None:
    """Follow the bar's live status stream and turn presses into music controls."""
    try:
        from busylib import AsyncBusyBar
        from busylib.features import ButtonEvent, input_events
    except ImportError:
        print("ℹ️  Install busylib (pip install busylib) to control music from the bar.")
        return

    client = AsyncBusyBar(screen.bar.host, token=screen.bar.token)
    delay = 1
    while True:
        try:
            async for message in client.stream_status_ws():
                delay = 1
                if not isinstance(message, dict):
                    continue
                for event in input_events(message):
                    if isinstance(event, ButtonEvent) and event.is_press:
                        action = BUTTON_ACTIONS.get(event.button)
                        if not action:
                            continue
                        print(f"  {event.button.upper()} pressed → {action}")
                        if action != "toggle":
                            screen.hop_until = time.monotonic() + 1.2
                        await screen.player.control(action)
                        await asyncio.sleep(0.3)  # give the player a moment
                        screen.refresh.set()
        except Exception as err:
            print(f"⚠️  Lost the button stream ({err}); retrying in {delay}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


async def run(screen: Screen, fps: float) -> None:
    screen.track = await screen.player.read()
    await asyncio.to_thread(screen.show_song, screen.track)
    await asyncio.gather(follow_music(screen), animate(screen, fps), listen(screen))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", help="API key, if HTTP access is set to 'key' mode")
    ap.add_argument("--fps", type=float, default=10, help="animation and scroll speed")
    ap.add_argument("--demo", action="store_true", help="use a pretend playlist")
    args = ap.parse_args()

    player = media.detect(args.demo)
    bar_ = BusyBar(args.host, args.token)
    screen = Screen(bar_, player)
    print(f"🎵 Listening to: {player.name}")
    print(f"🐺 Uploading artwork to the BUSY Bar at {args.host}…")
    screen.upload_static()
    print("✨ Luca is listening! OK = play/pause, Start = next, Back = previous.")
    print("   Press Ctrl+C to stop.")
    try:
        asyncio.run(run(screen, args.fps))
    except KeyboardInterrupt:
        pass
    finally:
        bar_.clear()
        print("\n🌙 Luca takes his headphones off. Screens cleared.")


if __name__ == "__main__":
    main()
