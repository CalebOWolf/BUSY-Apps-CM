"""
Reads what's playing on this computer, controls it, and turns the volume.

  Linux    any MPRIS player, through `playerctl`. Follows every player
           live, so changes show up the moment they happen, and picks the
           one that's actually playing (or the one you pin with --player)
  macOS    Spotify or Apple Music, through AppleScript (osascript)
  Windows  any app in the Windows media overlay, through `winsdk`
  --demo   a pretend playlist, for trying the app without music
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Track:
    title: str = ""
    artist: str = ""
    album: str = ""
    playing: bool = False
    position: float = 0.0        # seconds into the song, when it was read
    duration: float = 0.0        # 0 when the player doesn't say
    read_at: float = 0.0         # time.monotonic() of the reading
    art_url: str = ""            # file://, http(s):// or "" for none
    player: str = ""             # which app it came from

    @property
    def active(self) -> bool:
        return bool(self.title)

    @property
    def key(self) -> tuple:
        """Changes whenever the screens need redrawing."""
        return (self.title, self.artist, self.album, self.playing, self.art_url)

    def position_now(self) -> float:
        pos = self.position + (time.monotonic() - self.read_at if self.playing else 0)
        return min(pos, self.duration) if self.duration else pos


NOTHING = Track()


def _run(cmd: list[str], timeout: float = 3) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _num(text: str) -> float:
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return 0.0


# --------------------------------------------------------------------------
# Linux
# --------------------------------------------------------------------------
LINE_LIMIT = 64 * 1024 * 1024


class LinuxPlayer:
    """
    Keeps `playerctl --follow` running for every player, so it hears about a
    new song, a pause or a skip the moment it happens, then picks the player
    to show: the pinned one if given, else whichever started playing most
    recently, else the one paused most recently.
    """

    name = "Linux (playerctl)"
    FIELDS = ("playerName", "status", "title", "artist", "album", "position",
              "mpris:length", "mpris:artUrl")
    FORMAT = "\t".join("{{%s}}" % f for f in FIELDS)
    RESYNC = 5  # seconds between position check-ups (seeks, drift)

    def __init__(self, pinned: str | None = None):
        self.pinned = pinned.lower() if pinned else None
        self.players: dict[str, dict] = {}   # name -> latest reading
        self.notify: asyncio.Event | None = None
        self._task: asyncio.Task | None = None
        self._last_resync = 0.0
        if self.pinned:
            self.name += f", pinned to {pinned}"

    # -- following ---------------------------------------------------------
    def _matches_pin(self, name: str) -> bool:
        # Players can carry an instance suffix, like "firefox.instance_1_42".
        return name.lower().split(".")[0] == self.pinned or name.lower().startswith(self.pinned)

    def _ingest(self, line: str) -> None:
        parts = line.rstrip("\n").split("\t")
        if len(parts) < len(self.FIELDS) or not parts[0]:
            return
        name, status, title, artist, album, pos, length, art = parts[: len(self.FIELDS)]
        now = time.monotonic()
        old = self.players.get(name, {})
        started = old.get("started", 0.0)
        if status == "Playing" and old.get("status") != "Playing":
            started = now
        self.players[name] = {
            "status": status, "started": started, "seen": now,
            "track": Track(title, artist, album, status == "Playing", _num(pos) / 1e6,
                           _num(length) / 1e6, now, art, name),
        }
        if self.notify:
            self.notify.set()

    async def _follow(self) -> None:
        while True:
            proc = await asyncio.create_subprocess_exec(
                "playerctl", "--all-players", "--follow", "metadata", "--format", self.FORMAT,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                limit=LINE_LIMIT)  # some players send album art inline, megabytes long
            try:
                assert proc.stdout
                async for raw in proc.stdout:
                    try:
                        self._ingest(raw.decode(errors="replace"))
                    except Exception as err:  # one odd line shouldn't stop Luca listening
                        print(f"⚠️  Skipped a playerctl line I couldn't read: {err}")
            except (ValueError, asyncio.LimitOverrunError):
                pass  # an even bigger line: restart playerctl below
            finally:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
            await asyncio.sleep(2)  # playerctl exited; start it again

    async def _resync(self) -> None:
        """Forget players that closed, and refresh positions after seeks."""
        listed = await asyncio.to_thread(_run, ["playerctl", "--list-all"])
        alive = set(listed.split()) if listed else set()
        for name in list(self.players):
            if name not in alive:
                del self.players[name]
        for name in alive:
            line = await asyncio.to_thread(
                _run, ["playerctl", "-p", name, "metadata", "--format", self.FORMAT])
            if line:
                self._ingest(line)

    # -- choosing ----------------------------------------------------------
    def _choose(self) -> str | None:
        candidates = {n: p for n, p in self.players.items()
                      if p["status"] in ("Playing", "Paused") and p["track"].title}
        if self.pinned:
            candidates = {n: p for n, p in candidates.items() if self._matches_pin(n)}
        if not candidates:
            return None
        playing = [n for n, p in candidates.items() if p["status"] == "Playing"]
        if playing:
            return max(playing, key=lambda n: candidates[n]["started"])
        return max(candidates, key=lambda n: candidates[n]["seen"])

    async def read(self) -> Track:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._follow())
            await asyncio.sleep(0.3)  # let the first readings arrive
        if time.monotonic() - self._last_resync > self.RESYNC:
            self._last_resync = time.monotonic()
            await self._resync()
        name = self._choose()
        return self.players[name]["track"] if name else NOTHING

    async def control(self, action: str) -> None:
        verb = {"toggle": "play-pause", "next": "next", "previous": "previous"}[action]
        name = self._choose()
        cmd = ["playerctl", "-p", name, verb] if name else ["playerctl", verb]
        await asyncio.to_thread(_run, cmd)
        await asyncio.sleep(0.2)
        await self._resync()


# --------------------------------------------------------------------------
# macOS
# --------------------------------------------------------------------------
_MAC_SCRIPT = """
on readApp(appName)
  if application appName is running then
    tell application appName
      if player state is stopped then return ""
      set t to current track
      set st to "paused"
      if player state is playing then set st to "playing"
      set d to duration of t
      set art to ""
      if appName is "Spotify" then set art to artwork url of t
      return st & tab & (name of t) & tab & (artist of t) & tab & (album of t) & tab & (player position as text) & tab & (d as text) & tab & art
    end tell
  end if
  return ""
end readApp
set r to readApp("Spotify")
if r is "" then set r to readApp("Music")
return r
"""


class MacPlayer:
    name = "macOS (Spotify / Apple Music)"

    def _app(self) -> str | None:
        for app in ("Spotify", "Music"):
            if _run(["osascript", "-e", f'application "{app}" is running']) == "true":
                state = _run(["osascript", "-e", f'tell application "{app}" to player state as text'])
                if state in ("playing", "paused"):
                    return app
        return None

    async def read(self) -> Track:
        out = await asyncio.to_thread(_run, ["osascript", "-e", _MAC_SCRIPT])
        parts = out.split("\t")
        if len(parts) < 6:
            return NOTHING
        state, title, artist, album, pos, dur = parts[:6]
        art = parts[6] if len(parts) > 6 else ""
        duration = _num(dur)
        if duration > 10_000:  # Spotify reports milliseconds, Music seconds
            duration /= 1000
        return Track(title, artist, album, state == "playing", _num(pos), duration,
                     time.monotonic(), art)

    async def control(self, action: str) -> None:
        verb = {"toggle": "playpause", "next": "next track", "previous": "previous track"}[action]
        app = await asyncio.to_thread(self._app)
        if app:
            await asyncio.to_thread(_run, ["osascript", "-e", f'tell application "{app}" to {verb}'])


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------
class WindowsPlayer:
    name = "Windows (media overlay)"

    def __init__(self):
        try:
            import winsdk.windows.media.control as control
            import winsdk.windows.storage.streams as streams
        except ImportError:
            try:  # newer split packages
                import winrt.windows.media.control as control
                import winrt.windows.storage.streams as streams
            except ImportError:
                raise SystemExit("On Windows, install winsdk first:  pip install winsdk")
        self._manager_cls = control.GlobalSystemMediaTransportControlsSessionManager
        self._streams = streams
        self._manager = None
        self._art_for: tuple | None = None
        self._art_url = ""

    async def _session(self):
        if self._manager is None:
            self._manager = await self._manager_cls.request_async()
        return self._manager.get_current_session()

    async def _thumbnail(self, props) -> str:
        """Save the cover art to a temp file once per song; '' if there's none."""
        song = (props.title, props.artist, props.album_title)
        if song == self._art_for:
            return self._art_url
        self._art_for, self._art_url = song, ""
        try:
            if props.thumbnail is None:
                return ""
            stream = await props.thumbnail.open_read_async()
            buf = self._streams.Buffer(stream.size)
            await stream.read_async(buf, buf.capacity, self._streams.InputStreamOptions.READ_AHEAD)
            path = Path(tempfile.gettempdir()) / "luca-now-playing-art"
            path.write_bytes(bytes(buf))
            self._art_url = path.as_uri() + f"#{hash(song)}"
        except Exception:
            pass
        return self._art_url

    async def read(self) -> Track:
        session = await self._session()
        if session is None:
            return NOTHING
        props = await session.try_get_media_properties_async()
        timeline = session.get_timeline_properties()
        status = int(session.get_playback_info().playback_status)  # 4 playing, 5 paused
        if status not in (4, 5) or not props.title:
            return NOTHING
        return Track(props.title, props.artist, props.album_title, status == 4,
                     timeline.position.total_seconds(), timeline.end_time.total_seconds(),
                     time.monotonic(), await self._thumbnail(props))

    async def control(self, action: str) -> None:
        session = await self._session()
        if session is None:
            return
        if action == "toggle":
            await session.try_toggle_play_pause_async()
        elif action == "next":
            await session.try_skip_next_async()
        else:
            await session.try_skip_previous_async()


# --------------------------------------------------------------------------
# Demo
# --------------------------------------------------------------------------
class DemoPlayer:
    name = "demo playlist"
    SONGS = [
        ("Bubble Skies", "Luca Wood", "Frutiger Dreams", 187),
        ("Glass Meadow", "The Aero Pack", "Translucent", 214),
        ("Moonlight Howl", "Luca Wood", "Frutiger Dreams", 165),
        ("Café au Lait Clouds", "Vista Waves", "Desktop Weather", 201),
    ]

    def __init__(self):
        self.index, self.playing = 0, True
        self.started, self.paused_at = time.monotonic(), 0.0

    def _pos(self) -> float:
        return (time.monotonic() - self.started) if self.playing else self.paused_at

    async def read(self) -> Track:
        title, artist, album, dur = self.SONGS[self.index]
        if self._pos() >= dur:
            await self.control("next")
            return await self.read()
        art = (Path(__file__).parent / "assets" / "demo_art.png").as_uri() if self.index % 2 else ""
        return Track(title, artist, album, self.playing, self._pos(), dur,
                     time.monotonic(), art, "demo")

    async def control(self, action: str) -> None:
        if action == "toggle":
            if self.playing:
                self.paused_at = self._pos()
            else:
                self.started = time.monotonic() - self.paused_at
            self.playing = not self.playing
            return
        step = 1 if action == "next" else -1
        self.index = (self.index + step) % len(self.SONGS)
        self.started, self.paused_at, self.playing = time.monotonic(), 0.0, True


def detect(demo: bool = False, pinned: str | None = None):
    if demo:
        return DemoPlayer()
    if sys.platform == "darwin":
        return MacPlayer()
    if sys.platform.startswith("win"):
        return WindowsPlayer()
    if shutil.which("playerctl"):
        return LinuxPlayer(pinned)
    raise SystemExit("Couldn't find a way to read your music. On Linux, install playerctl, "
                     "or try the app with --demo.")


# --------------------------------------------------------------------------
# System volume (for the wheel)
# --------------------------------------------------------------------------
class Volume:
    """
    Turns the computer's main volume up or down by `step` per wheel click and
    says where it ended up (0..1), or None if it can't tell.
    """

    def __init__(self, step: float = 0.02):
        self.step = step
        if sys.platform.startswith("linux"):
            self.kind = "wpctl" if shutil.which("wpctl") else "pactl" if shutil.which("pactl") else None
        elif sys.platform == "darwin":
            self.kind = "mac"
        elif sys.platform.startswith("win"):
            self.kind = "windows"
        else:
            self.kind = None

    @property
    def available(self) -> bool:
        return self.kind is not None

    def change(self, clicks: int) -> float | None:
        if not clicks or not self.kind:
            return self.level()
        pct = round(abs(clicks) * self.step * 100)
        sign = "+" if clicks > 0 else "-"
        if self.kind == "wpctl":
            _run(["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", f"{pct}%{sign}"])
        elif self.kind == "pactl":
            _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{sign}{pct}%"])
        elif self.kind == "mac":
            _run(["osascript", "-e", "set volume output volume "
                  f"((output volume of (get volume settings)) {sign} {pct})"])
        elif self.kind == "windows":
            import ctypes  # tap the volume key; each tap is 2% on Windows
            key = 0xAF if clicks > 0 else 0xAE
            for _ in range(abs(clicks)):
                ctypes.windll.user32.keybd_event(key, 0, 0, 0)
                ctypes.windll.user32.keybd_event(key, 0, 2, 0)
        return self.level()

    def level(self) -> float | None:
        if self.kind == "wpctl":  # "Volume: 0.45" or "Volume: 0.45 [MUTED]"
            out = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"]).split()
            return _num(out[1]) if len(out) > 1 else None
        if self.kind == "pactl":  # "... front-left: 29491 /  45% / ..."
            out = _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
            pcts = [p for p in out.split() if p.endswith("%")]
            return _num(pcts[0][:-1]) / 100 if pcts else None
        if self.kind == "mac":
            out = _run(["osascript", "-e", "output volume of (get volume settings)"])
            return _num(out) / 100 if out else None
        return None
