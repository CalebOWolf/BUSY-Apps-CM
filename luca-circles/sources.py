"""
What's happening in osu!, for Luca Circles.

Live numbers (combo, accuracy, hits, pp, the map, your rank) come from tosu
(https://github.com/tosuapp/tosu), a free helper that reads osu! (stable and
lazer) and serves it on your own PC at http://127.0.0.1:24050. Its JSON
comes in two shapes, the newer /json/v2 and the older gosumemory-style
/json; both are read here, defensively, into one Live.

Without tosu, Luca can still tell that osu! is open by looking at your
processes, just not what's happening in it.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# osu!'s screens, as numbered by the game (and tosu)
PLAYING, RESULTS = {2}, {7, 14, 18}
SELECTING = {4, 5, 6, 11, 12, 13, 15}


@dataclass
class Live:
    state: str = "menu"          # "play", "results", "select" or "menu"
    artist: str = ""
    title: str = ""
    version: str = ""            # the difficulty's name
    stars: float = 0.0
    combo: int = 0
    max_combo: int = 0
    accuracy: float = 100.0
    h300: int = 0
    h100: int = 0
    h50: int = 0
    misses: int = 0
    pp: float = 0.0
    rank: str = ""
    time_ms: float = 0.0
    length_ms: float = 0.0

    @property
    def song(self) -> str:
        return f"{self.artist} - {self.title}" if self.artist else self.title

    @property
    def progress(self) -> float:
        return max(0.0, min(1.0, self.time_ms / self.length_ms)) if self.length_ms > 0 else 0.0


def _get(data, *path, default=None):
    for key in path:
        if not isinstance(data, dict) or key not in data:
            return default
        data = data[key]
    return data


def _num(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _state(number) -> str:
    n = int(_num(number, -1))
    return ("play" if n in PLAYING else "results" if n in RESULTS
            else "select" if n in SELECTING else "menu")


def parse_v2(d: dict) -> Live:
    bm, play = d.get("beatmap") or {}, d.get("play") or {}
    state = _state(_get(d, "state", "number"))
    res = d.get("resultsScreen") or {}
    src = res if state == "results" and res else play
    hits = src.get("hits") or {}
    rank = _get(src, "rank", "current") if isinstance(src.get("rank"), dict) else src.get("rank")
    return Live(
        state=state,
        artist=bm.get("artist") or "", title=bm.get("title") or "", version=bm.get("version") or "",
        stars=_num(_get(bm, "stats", "stars", "total")),
        combo=int(_num(_get(play, "combo", "current"))),
        max_combo=int(_num(_get(src, "combo", "max") if "combo" in src else src.get("maxCombo"))),
        accuracy=_num(src.get("accuracy"), 100.0),
        h300=int(_num(hits.get("300"))), h100=int(_num(hits.get("100"))),
        h50=int(_num(hits.get("50"))), misses=int(_num(hits.get("0"))),
        pp=_num(_get(src, "pp", "current")),
        rank=str(rank or ""),
        time_ms=_num(_get(bm, "time", "live")),
        length_ms=_num(_get(bm, "time", "lastObject")) or _num(_get(bm, "time", "mp3Length")),
    )


def parse_v1(d: dict) -> Live:
    menu, gp = d.get("menu") or {}, d.get("gameplay") or {}
    state = _state(menu.get("state"))
    res = d.get("resultsScreen") or {}
    meta = _get(menu, "bm", "metadata") or {}
    hits = gp.get("hits") or {}
    if state == "results" and res:
        acc = _num(res.get("accuracy"), _num(gp.get("accuracy"), 100.0))
        h = res
        rank = res.get("grade") or _get(hits, "grade", "current")
        max_combo = res.get("maxCombo")
    else:
        acc, h = _num(gp.get("accuracy"), 100.0), hits
        rank = _get(hits, "grade", "current")
        max_combo = _get(gp, "combo", "max")
    return Live(
        state=state,
        artist=meta.get("artist") or "", title=meta.get("title") or "", version=meta.get("difficulty") or "",
        stars=_num(_get(menu, "bm", "stats", "fullSR")) or _num(_get(menu, "bm", "stats", "SR")),
        combo=int(_num(_get(gp, "combo", "current"))), max_combo=int(_num(max_combo)),
        accuracy=acc,
        h300=int(_num(h.get("300"))), h100=int(_num(h.get("100"))),
        h50=int(_num(h.get("50"))), misses=int(_num(h.get("0"))),
        pp=_num(_get(gp, "pp", "current")),
        rank=str(rank or ""),
        time_ms=_num(_get(menu, "bm", "time", "current")),
        length_ms=_num(_get(menu, "bm", "time", "full")) or _num(_get(menu, "bm", "time", "mp3")),
    )


class Tosu:
    def __init__(self, host: str = "127.0.0.1:24050"):
        self.base = f"http://{host}"
        self.v2 = True

    def read(self) -> Live | None:
        """The latest from tosu, or None if it isn't running."""
        for v2 in ([self.v2, not self.v2]):
            try:
                with urllib.request.urlopen(f"{self.base}/json{'/v2' if v2 else ''}", timeout=1) as r:
                    data = json.loads(r.read())
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict) or data.get("error"):
                continue
            self.v2 = v2
            return parse_v2(data) if v2 else parse_v1(data)
        return None


GAME_NAMES = ("osu!", "osu.exe", "osu-lazer", "osu.appimage")


def osu_running() -> bool:
    """Is osu! (lazer, or stable through Wine) open?"""
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            first = (entry / "cmdline").read_bytes().split(b"\0", 1)[0].decode(errors="replace").lower()
        except OSError:
            continue
        name = os.path.basename(first.replace("\\", "/"))
        if any(name == g or name.startswith(g) for g in GAME_NAMES) or "/osu-lazer/" in first:
            return True
    return False
