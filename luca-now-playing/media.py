"""
Reads what's playing on this computer and controls it.

  macOS    Spotify or Apple Music, through AppleScript (osascript)
  Windows  any app that shows up in the Windows media overlay (Spotify,
           browsers, Media Player…), through the `winsdk` package
  Linux    any MPRIS player, through `playerctl`
  --demo   a pretend playlist, for trying the app without music
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass


@dataclass
class Track:
    title: str = ""
    artist: str = ""
    album: str = ""
    playing: bool = False
    position: float = 0.0        # seconds into the song, when it was read
    duration: float = 0.0        # 0 when the player doesn't say
    read_at: float = 0.0         # time.monotonic() of the reading

    @property
    def active(self) -> bool:
        return bool(self.title)

    @property
    def key(self) -> tuple:
        """Changes whenever the screens need redrawing."""
        return (self.title, self.artist, self.album, self.playing)

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
      return st & tab & (name of t) & tab & (artist of t) & tab & (album of t) & tab & (player position as text) & tab & (d as text)
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
        duration = _num(dur)
        if duration > 10_000:  # Spotify reports milliseconds, Music seconds
            duration /= 1000
        return Track(title, artist, album, state == "playing", _num(pos), duration, time.monotonic())

    async def control(self, action: str) -> None:
        verb = {"toggle": "playpause", "next": "next track", "previous": "previous track"}[action]
        app = await asyncio.to_thread(self._app)
        if app:
            await asyncio.to_thread(_run, ["osascript", "-e", f'tell application "{app}" to {verb}'])


# --------------------------------------------------------------------------
# Linux
# --------------------------------------------------------------------------
class LinuxPlayer:
    name = "Linux (playerctl)"
    FORMAT = "{{status}}\t{{title}}\t{{artist}}\t{{album}}\t{{position}}\t{{mpris:length}}"

    async def read(self) -> Track:
        out = await asyncio.to_thread(_run, ["playerctl", "metadata", "--format", self.FORMAT])
        parts = out.split("\t")
        if len(parts) < 6 or parts[0] not in ("Playing", "Paused"):
            return NOTHING
        status, title, artist, album, pos, length = parts[:6]
        return Track(title, artist, album, status == "Playing",
                     _num(pos) / 1e6, _num(length) / 1e6, time.monotonic())

    async def control(self, action: str) -> None:
        verb = {"toggle": "play-pause", "next": "next", "previous": "previous"}[action]
        await asyncio.to_thread(_run, ["playerctl", verb])


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------
class WindowsPlayer:
    name = "Windows (media overlay)"

    def __init__(self):
        try:
            from winsdk.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as Manager,
            )
        except ImportError:
            try:
                from winrt.windows.media.control import (  # newer split packages
                    GlobalSystemMediaTransportControlsSessionManager as Manager,
                )
            except ImportError:
                raise SystemExit("On Windows, install winsdk first:  pip install winsdk")
        self._manager_cls = Manager
        self._manager = None

    async def _session(self):
        if self._manager is None:
            self._manager = await self._manager_cls.request_async()
        return self._manager.get_current_session()

    async def read(self) -> Track:
        session = await self._session()
        if session is None:
            return NOTHING
        props = await session.try_get_media_properties_async()
        timeline = session.get_timeline_properties()
        status = int(session.get_playback_info().playback_status)  # 4 playing, 5 paused
        if status not in (4, 5) or not props.title:
            return NOTHING
        pos = timeline.position.total_seconds()
        end = timeline.end_time.total_seconds()
        return Track(props.title, props.artist, props.album_title, status == 4,
                     pos, end, time.monotonic())

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
        return Track(title, artist, album, self.playing, self._pos(), dur, time.monotonic())

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


def detect(demo: bool = False):
    if demo:
        return DemoPlayer()
    if sys.platform == "darwin":
        return MacPlayer()
    if sys.platform.startswith("win"):
        return WindowsPlayer()
    if shutil.which("playerctl"):
        return LinuxPlayer()
    raise SystemExit("Couldn't find a way to read your music. On Linux, install playerctl, "
                     "or try the app with --demo.")
