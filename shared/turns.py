"""
Taking turns on the bar, for the "always on" apps (PC Stats, Weather Den,
Aero Clock).

Without Luca's Den running, nothing changes: every app shows whenever it
likes and the highest priority wins. With Luca's Den running, it writes
whose turn it is; an always-on app in its rotation only shows during its own
turn and steps aside otherwise. Apps that show only when something happens
(music, notifications, calls, focus rounds) never wait for a turn.
"""

from __future__ import annotations

import json
import time

from busybar import PRESENCE_DIR, BusyBar, mark_running

TURN_FILE = PRESENCE_DIR / "turn.json"
FRESH = 4  # seconds: if Den stops updating this, everyone goes back to normal


def write_turn(app: str | None, rotation: list[str], until: float) -> None:
    try:
        PRESENCE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = TURN_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"app": app, "rotation": rotation, "until": until,
                                   "updated": time.time()}))
        tmp.replace(TURN_FILE)
    except OSError:
        pass


def read_turn() -> dict | None:
    try:
        data = json.loads(TURN_FILE.read_text())
    except (OSError, ValueError):
        return None
    return data if time.time() - data.get("updated", 0) < FRESH else None


def my_turn(app: str) -> bool:
    data = read_turn()
    if not data or app not in data.get("rotation", []):
        return True
    return data.get("app") == app


class TurnTaker:
    """Call check() before drawing each frame: it says "I'm here" to Luca's
    Den now and then, and returns False (after clearing the screen once)
    while it's another app's turn."""

    def __init__(self, app: str, bar: BusyBar):
        self.app, self.bar = app, bar
        self.away = False
        self._beat = 0.0

    def check(self) -> bool:
        now = time.time()
        if now - self._beat > 3:
            mark_running(self.app)
            self._beat = now
        if my_turn(self.app):
            self.away = False
            return True
        if not self.away:
            self.away = True
            self.bar.clear()  # may raise BarOffline; the app's own loop handles that
        return False
