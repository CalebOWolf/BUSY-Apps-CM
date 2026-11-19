"""
Luca Now Playing 🎵🐺, a Frutiger Aero "now playing" strip for the BUSY Bar.

Shows the song playing on this computer: Luca bops along in his headphones,
the title and artist scroll across a glossy Aero sky, and a progress bar
fills up. The back screen becomes "Luca Player", a Windows 7-style media
player window. The bar's buttons control your music:

    OK      play / pause
    Start   next song      (Luca hops)
    Back    previous song
    Wheel   volume up / down

Luca only appears while music plays. When it stops or pauses he stays for
2 minutes (--linger), then steps aside so the bar shows its usual screens.

    python now_playing.py                 # BUSY Bar on USB (10.0.4.20)
    python now_playing.py --host 192.168.1.42 --token YOUR_KEY   # over Wi-Fi
    python now_playing.py --demo          # try it with a pretend playlist
    python now_playing.py --player spotify   # Linux: only ever show Spotify
    python now_playing.py --install       # Linux: start automatically at login
    python now_playing.py --uninstall     # Linux: stop starting at login

Press Ctrl+C to stop; the app clears its screens on the way out.
Needs Pillow; button control also needs busylib (pip install pillow busylib).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import os
import shutil
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import art  # noqa: E402
import media  # noqa: E402
import service  # noqa: E402
import visualizer  # noqa: E402
from busybar import BarOffline, BusyBar, image, input_events, is_press, is_wheel  # noqa: E402
from busybar import rect as bar  # noqa: E402

APP = "luca_now_playing"
SLIDE_FRAMES = 8          # how long a new title takes to slide in
SPARKLE_FRAMES = 12       # how long the song-change sparkles last
SPARKLES = [(24, 2, 0), (40, 12, 2), (55, 1, 4), (68, 10, 1), (33, 7, 5), (62, 5, 3)]
SPARKLE_COLORS = ["#FFF05AFF", "#FFFFFFFF", "#78FFC8FF", "#FF78C8FF"]
BUTTON_ACTIONS = {"ok": "toggle", "start": "next", "back": "previous"}
SERVICE = "luca-now-playing"


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

    def __init__(self, bar_: BusyBar, player, linger: float, volume: media.Volume):
        self.bar = bar_
        self.player = player
        self.linger = linger
        self.volume = volume
        self.pending_clicks = 0            # wheel clicks not yet applied
        self.volume_level: float | None = None
        self.volume_up = True
        self.volume_until = 0.0            # show the volume pop-up until then
        self.covers: dict[str, Image.Image | None] = {}
        self.reverse_wheel = False
        self.viz: visualizer.Visualizer | None = None
        self.slide: int | None = None      # frames into a new title sliding in
        self.sparkle: int | None = None    # frames into the song-change sparkles
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
        self.bar.upload_image("vol_icon.png", art.volume_icon())
        self.bar.upload_image("vol_up.png", art.volume_sign(True))
        self.bar.upload_image("vol_down.png", art.volume_sign(False))

    def cover(self, url: str) -> Image.Image | None:
        """The song's album art, fetched once per song; None if there's none."""
        if not url:
            return None
        if url not in self.covers:
            if len(self.covers) > 30:
                self.covers.clear()
            self.covers[url] = load_cover(url)
        return self.covers[url]

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
            track.title, track.artist, track.album, track.playing, self.cover(track.art_url)))
        had_song = self.shown_key is not None and bool(self.shown_key[0])
        new_song = self.shown_key is None or self.shown_key[:3] != track.key[:3]
        self.slot, self.strip_loop, self.shown_key = slot, loop, track.key
        if new_song:
            self.offset, self.hold = 0, 15
            if had_song and track.active:  # a new song: slide in, sparkle, hop!
                self.slide, self.sparkle = 0, 0
                self.hop_until = time.monotonic() + 1.2

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

        # A new title glides in from the right edge, easing to a stop.
        song_x = art.TEXT_X - self.offset
        if self.slide is not None:
            k = min(self.slide / SLIDE_FRAMES, 1.0)
            song_x = art.TEXT_X + round((art.FRONT_W - art.TEXT_X) * (1 - k) ** 2)
            self.slide = None if self.slide >= SLIDE_FRAMES else self.slide + 1

        els = [image("sky", f"bg_{self.frame % art.BG_FRAMES:02d}.png", 0, 0)]
        if self.viz and self.viz.enabled and t.playing:
            els += self.equalizer()
        els += [
            image("song", f"strip_{self.slot}.png", song_x, art.TEXT_Y),
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
        if self.sparkle is not None:
            els += self.sparkles()
        if now < self.volume_until:
            els += self.volume_popup()
        return els

    def equalizer(self) -> list[dict]:
        """Glassy equalizer bars rising behind the title, driven by cava."""
        els = []
        for i, level in enumerate(self.viz.levels):
            if level:
                els.append({"id": f"eq{i}", "type": "rectangle", "display": "front",
                            "x": art.TEXT_X + i * 4, "y": art.BAR_Y - level,
                            "width": 3, "height": level, "fill": "gradient_v",
                            "fill_colors": ["#F0FFFFE0", "#50F0BEB0"], "border_width": 0})
        return els

    def sparkles(self) -> list[dict]:
        """Little twinkling stars that pop around a new title."""
        els = []
        for i, (x, y, delay) in enumerate(SPARKLES):
            age = self.sparkle - delay
            if not 0 <= age < 6:
                continue
            r = (0, 1, 2, 1, 1, 0)[age]
            color = SPARKLE_COLORS[(i + age) % len(SPARKLE_COLORS)]
            els.append(bar(f"spark{i}h", x - r, y, 2 * r + 1, 1, color))
            if r:
                els.append(bar(f"spark{i}v", x, y - r, 1, 2 * r + 1, color))
        self.sparkle = None if self.sparkle >= SPARKLE_FRAMES else self.sparkle + 1
        return els

    def volume_popup(self) -> list[dict]:
        """A glossy glass panel over the title with a speaker and a level bar."""
        px, py, pw, ph = art.VOL_PANEL
        els = [
            {"id": "vol_panel", "type": "rectangle", "display": "front", "x": px, "y": py,
             "width": pw, "height": ph, "fill": "gradient_v",
             "fill_colors": ["#A0DCFFFF", "#0A50B4FF"], "border_width": 0},
            image("vol_icon", "vol_icon.png", px + 3, 4),
        ]
        bx, by, bw, bh = art.VOL_BAR
        els.append(bar("vol_track", bx, by, bw, bh, "#0A3278FF"))
        if self.volume_level is None:  # can't read the level: just show + or -
            els.append(image("vol_sign", "vol_up.png" if self.volume_up else "vol_down.png",
                             bx + bw // 2 - 3, 4))
        elif round(bw * min(self.volume_level, 1.0)):
            els.append(bar("vol_fill", bx, by, round(bw * min(self.volume_level, 1.0)), bh,
                           "#78FFC8FF"))
        return els


def load_cover(url: str) -> Image.Image | None:
    """Open album art from a file://, http(s):// or data: address."""
    try:
        if url.startswith("data:"):
            img = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
            img.load()
            return img
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme == "file":
            img = Image.open(urllib.request.url2pathname(parsed.path))
        elif parsed.scheme in ("http", "https"):
            with urllib.request.urlopen(url, timeout=5) as resp:
                img = Image.open(io.BytesIO(resp.read()))
        else:
            return None
        img.load()
        return img
    except Exception:
        return None


async def follow_music(screen: Screen) -> None:
    """Ask the computer what's playing, about once a second."""
    last_key = None
    while True:
        screen.refresh.clear()
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
    """Turn the bar's button presses and wheel turns into music controls."""
    async for event in input_events(screen.bar):
        if not screen.shown:
            continue  # buttons belong to the bar while Luca is away
        if is_wheel(event) and screen.volume.available:
            clicks = -event.delta if screen.reverse_wheel else event.delta
            screen.pending_clicks += clicks
            screen.volume_up = clicks > 0
            screen.volume_until = time.monotonic() + 1.5
        elif is_press(event):
            action = BUTTON_ACTIONS.get(event.button)
            if not action:
                continue
            print(f"  {event.button.upper()} pressed → {action}")
            if action != "toggle":
                screen.hop_until = time.monotonic() + 1.2
            await screen.player.control(action)
            await asyncio.sleep(0.3)  # give the player a moment
            screen.refresh.set()


async def turn_volume(screen: Screen) -> None:
    """Apply wheel clicks in small batches, so a fast spin doesn't queue up."""
    screen.volume_level = await asyncio.to_thread(screen.volume.level)
    while True:
        await asyncio.sleep(0.08)
        if screen.pending_clicks:
            clicks, screen.pending_clicks = screen.pending_clicks, 0
            screen.volume_level = await asyncio.to_thread(screen.volume.change, clicks)
            screen.volume_until = time.monotonic() + 1.5


async def run(screen: Screen, fps: float) -> None:
    screen.player.notify = screen.refresh  # players that hear changes live wake us up
    await asyncio.gather(follow_music(screen), animate(screen, fps), listen(screen),
                         turn_volume(screen), screen.viz.run())


# --------------------------------------------------------------------------
# Start at login (Linux, systemd user service)
# --------------------------------------------------------------------------
def install(args) -> None:
    if args.demo:
        raise SystemExit("--install starts the real thing; leave out --demo.")
    service.check([
        ("playerctl (sudo pacman -S playerctl)", bool(shutil.which("playerctl"))),
        ("Pillow (pip install pillow)", service.importable("PIL")),
        ("busylib (pip install busylib)", service.importable("busylib")),
    ], required={"Pillow (pip install pillow)"})
    command = [sys.executable, str(Path(__file__).resolve()),
               "--host", args.host, "--linger", args.linger_text, "--fps", str(args.fps)]
    if args.player:
        command += ["--player", args.player]
    if args.reverse_wheel:
        command += ["--reverse-wheel"]
    if args.visualizer != "auto":
        command += ["--visualizer", args.visualizer]
    service.install(SERVICE, "Luca Now Playing for the BUSY Bar", command, args.token,
                    "Luca now starts at login and appears whenever you play music.")


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
    ap.add_argument("--player", metavar="NAME",
                    help="Linux: only show this player, e.g. spotify, firefox, vlc "
                         "(default: whichever is playing)")
    ap.add_argument("--visualizer", choices=["auto", "on", "off"], default="auto",
                    help="equalizer bars behind the title, using cava "
                         "(default: auto, on when cava is installed)")
    ap.add_argument("--reverse-wheel", action="store_true",
                    help="flip which way the wheel turns the volume")
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
        return service.uninstall(SERVICE)

    player = media.detect(args.demo, args.player)
    bar_ = BusyBar(args.host, APP, args.token)
    volume = media.Volume()
    screen = Screen(bar_, player, args.linger, volume)
    screen.reverse_wheel = args.reverse_wheel
    screen.viz = visualizer.Visualizer(args.visualizer)
    print(f"🎵 Listening to: {player.name}")
    if not volume.available:
        print("ℹ️  Couldn't find wpctl or pactl, so the wheel won't change the volume.")
    if screen.viz.enabled:
        print("📊 Visualizer on (cava)")
    elif args.visualizer == "auto":
        print("ℹ️  Install cava (sudo pacman -S cava) for equalizer bars behind the title.")
    print(f"🐺 Luca appears on the BUSY Bar at {args.host} whenever music plays.")
    print("   OK = play/pause, Start = next, Back = previous, wheel = volume. Ctrl+C to stop.")

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
