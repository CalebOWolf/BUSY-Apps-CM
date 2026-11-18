"""
Luca Now Playing 🎵🐺, a Frutiger Aero "now playing" strip for the BUSY Bar.

Shows the song playing on this computer: Luca bops along in his headphones,
the title and artist scroll across a glossy Aero sky, and a progress bar
fills up. The back screen becomes "Luca Player", a Windows 7-style media
player window. The bar's buttons control your music:

    OK      play / pause
    Start   next song      (Luca hops)
    Back    previous song

Luca only appears while music plays. When it stops or pauses he stays for
2 minutes (--linger), then steps aside so the bar shows its usual screens.

    python now_playing.py                 # BUSY Bar on USB (10.0.4.20)
    python now_playing.py --host 192.168.1.42 --token YOUR_KEY   # over Wi-Fi
    python now_playing.py --demo          # try it with a pretend playlist
    python now_playing.py --install       # Linux: start automatically at login
    python now_playing.py --uninstall     # Linux: stop starting at login

Press Ctrl+C to stop; the app clears its screens on the way out.
Needs Pillow; button control also needs busylib (pip install pillow busylib).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import art
import media

APP = "luca_now_playing"
BUTTON_ACTIONS = {"ok": "toggle", "start": "next", "back": "previous"}
UNIT_NAME = "luca-now-playing.service"


class BarOffline(Exception):
    """The BUSY Bar didn't answer (unplugged, asleep, off Wi-Fi…)."""


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
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as err:
            detail = err.read().decode(errors="replace")
            raise BarOffline(f"it said {err.code} for {method} {path}: {detail}") from err
        except (urllib.error.URLError, OSError) as err:
            raise BarOffline(str(getattr(err, "reason", err))) from err
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


def minutes(text: str) -> float:
    """'2m', '2' or '1.5' → minutes; '30s' → seconds. Returns seconds."""
    value = text.strip().lower()
    unit = 1 if value.endswith("s") else 60
    try:
        seconds = float(value.rstrip("ms").strip()) * unit
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' isn't a time; try 2m, 5m or 30s")
    if seconds < 0:
        raise argparse.ArgumentTypeError("the time can't be negative")
    return seconds


class Screen:
    """What's on the bar right now, and what changes from frame to frame."""

    def __init__(self, bar_: BusyBar, player, linger: float):
        self.bar = bar_
        self.player = player
        self.linger = linger
        self.track = media.NOTHING
        self.last_playing = float("-inf")  # when music was last heard playing
        self.online = False                # artwork uploaded and the bar answering
        self.shown = False                 # is Luca on the bar right now?
        self.shown_key = None
        self.slot = 0                      # song art alternates between two file names
        self.strip_loop = 0
        self.offset = 0
        self.hold = 0
        self.hop_until = 0.0
        self.frame = 0
        self.refresh = asyncio.Event()

    @property
    def wanted(self) -> bool:
        """Show Luca while music plays, and for `linger` seconds after it stops."""
        if self.track.playing:
            return True
        return time.monotonic() - self.last_playing < self.linger

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
    """Ask the computer what's playing, about once a second."""
    last_key = None
    while True:
        try:
            track = await screen.player.read()
        except Exception as err:  # a player hiccup shouldn't stop the show
            print(f"⚠️  Couldn't read the music player: {err}")
            track = media.NOTHING
        if track.playing:
            screen.last_playing = time.monotonic()
        screen.track = track
        if track.key != last_key:
            if track.active:
                state = "▶" if track.playing else "⏸"
                print(f"  {state} {track.title}" + (f" - {track.artist}" if track.artist else ""))
            else:
                print("  ⏹ nothing playing")
            last_key = track.key
        screen.refresh.clear()
        try:
            await asyncio.wait_for(screen.refresh.wait(), timeout=1)
        except asyncio.TimeoutError:
            pass


async def animate(screen: Screen, fps: float) -> None:
    """Draw Luca while he's wanted, step aside when he isn't, and ride out
    the bar going away."""
    retry = 2
    while True:
        try:
            if screen.wanted:
                if not screen.online:
                    await asyncio.to_thread(screen.upload_static)
                    screen.online, screen.shown_key, retry = True, None, 2
                if screen.track.key != screen.shown_key:
                    await asyncio.to_thread(screen.show_song, screen.track)
                if not screen.shown:
                    print("🐺 Luca hops onto the bar")
                    screen.shown = True
                await asyncio.to_thread(screen.bar.draw, screen.elements())
                screen.frame += 1
                await asyncio.sleep(1 / fps)
            else:
                if screen.shown:
                    print("💤 Music stopped a while ago; Luca steps aside")
                    await asyncio.to_thread(screen.bar.clear)
                    screen.shown = False
                await asyncio.sleep(0.5)
        except BarOffline as err:
            if screen.online or retry == 2:
                print(f"🔌 Can't reach the BUSY Bar ({err}); I'll keep trying quietly")
            screen.online = screen.shown = False
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def listen(screen: Screen) -> None:
    """Follow the bar's live status stream and turn presses into music controls."""
    try:
        from busylib import AsyncBusyBar
        from busylib.features import ButtonEvent, input_events
    except ImportError:
        print("ℹ️  Install busylib (pip install busylib) to control music from the bar.")
        return

    client = AsyncBusyBar(screen.bar.host, token=screen.bar.token)
    delay = 2
    while True:
        try:
            async for message in client.stream_status_ws():
                delay = 2
                if not isinstance(message, dict) or not screen.shown:
                    continue  # buttons belong to the bar while Luca is away
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
        except Exception:  # the bar went away; the animate loop already says so
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


async def run(screen: Screen, fps: float) -> None:
    await asyncio.gather(follow_music(screen), animate(screen, fps), listen(screen))


# --------------------------------------------------------------------------
# Start at login (Linux, systemd user service)
# --------------------------------------------------------------------------
def unit_path() -> Path:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config / "systemd" / "user" / UNIT_NAME


def systemd_quote(arg: str) -> str:
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


def systemctl(*args: str) -> None:
    cmd = ["systemctl", "--user", *args]
    print("  $ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def require_systemd() -> None:
    if not sys.platform.startswith("linux") or not shutil.which("systemctl"):
        raise SystemExit("--install / --uninstall set up a systemd user service, so they "
                         "only work on Linux with systemd.")


def install(args) -> None:
    require_systemd()
    if args.demo:
        raise SystemExit("--install starts the real thing; leave out --demo.")
    missing = [name for name, ok in [
        ("playerctl (sudo pacman -S playerctl)", shutil.which("playerctl")),
        ("Pillow (pip install pillow)", _importable("PIL")),
        ("busylib (pip install busylib)", _importable("busylib")),
    ] if not ok]
    if missing:
        print("⚠️  Not found for this Python, install first: " + ", ".join(missing))
        if not _importable("PIL"):
            raise SystemExit(1)

    command = [sys.executable, str(Path(__file__).resolve()),
               "--host", args.host, "--linger", args.linger_text, "--fps", str(args.fps)]
    lines = [
        "[Unit]",
        "Description=Luca Now Playing for the BUSY Bar",
        "",
        "[Service]",
        "ExecStart=" + " ".join(systemd_quote(a) for a in command),
        "Environment=PYTHONUNBUFFERED=1",
    ]
    if args.token:
        lines.append("Environment=" + systemd_quote(f"BUSYBAR_TOKEN={args.token}"))
    lines += ["Restart=on-failure", "RestartSec=10", "", "[Install]", "WantedBy=default.target", ""]

    path = unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    path.chmod(0o600)  # it may hold your API key
    print(f"📝 Wrote {path}")
    systemctl("daemon-reload")
    systemctl("enable", "--now", UNIT_NAME)
    print("✨ Done! Luca now starts at login and appears whenever you play music.")
    print(f"   Watch what he's up to:  journalctl --user -u {UNIT_NAME} -f")


def uninstall() -> None:
    require_systemd()
    path = unit_path()
    if path.exists():
        systemctl("disable", "--now", UNIT_NAME)
        path.unlink()
        systemctl("daemon-reload")
        print(f"🗑️  Removed {path}. Luca won't start at login any more.")
    else:
        print("Nothing to remove: Luca isn't set to start at login.")


def _importable(module: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(module) is not None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"),
                    help="API key, if HTTP access is set to 'key' mode "
                         "(or set BUSYBAR_TOKEN)")
    ap.add_argument("--fps", type=float, default=10, help="animation and scroll speed")
    ap.add_argument("--linger", default="2m", metavar="TIME",
                    help="how long Luca stays after the music stops: 2m, 5m, 30s, 0 "
                         "(default: 2m)")
    ap.add_argument("--demo", action="store_true", help="use a pretend playlist")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true",
                       help="Linux: start automatically at login (systemd user service)")
    group.add_argument("--uninstall", action="store_true",
                       help="Linux: stop starting at login")
    args = ap.parse_args()
    args.linger_text = args.linger
    try:
        args.linger = minutes(args.linger)
    except argparse.ArgumentTypeError as err:
        ap.error(f"argument --linger: {err}")

    if args.install:
        return install(args)
    if args.uninstall:
        return uninstall()

    player = media.detect(args.demo)
    bar_ = BusyBar(args.host, args.token)
    screen = Screen(bar_, player, args.linger)
    print(f"🎵 Listening to: {player.name}")
    print(f"🐺 Luca appears on the BUSY Bar at {args.host} whenever music plays.")
    print("   OK = play/pause, Start = next, Back = previous. Ctrl+C to stop.")

    # systemd stops services with SIGTERM: treat it like Ctrl+C so we clean up.
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(run(screen, args.fps))
    except KeyboardInterrupt:
        pass
    finally:
        if screen.shown:
            try:
                bar_.clear()
            except BarOffline:
                pass
        print("\n🌙 Luca takes his headphones off.")


if __name__ == "__main__":
    main()
