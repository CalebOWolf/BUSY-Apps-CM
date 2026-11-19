"""
Spotting a Minecraft instance that's running, by looking at your processes.

Every launcher starts the game as a Java process, and names the instance in
the game's folder or command line:

  Prism Launcher / MultiMC   .../instances/<name>/minecraft  (or .minecraft)
  ATLauncher                 .../instances/<name>
  CurseForge                 .../Instances/<name>
  the official launcher      --gameDir <the profile's game folder>

So a Java process is "the game" if its command line mentions Minecraft, and
"your instance" if the instance name appears in its folder or command line.
Linux only (reads /proc); nothing is sent anywhere.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

LAUNCHERS = [  # (a bit of the path or command line, the launcher's name)
    ("prismlauncher", "Prism Launcher"), ("polymc", "PolyMC"), ("multimc", "MultiMC"),
    ("atlauncher", "ATLauncher"), ("curseforge", "CurseForge"), ("modrinth", "Modrinth App"),
    ("gdlauncher", "GDLauncher"), ("technic", "Technic"), (".minecraft", "Minecraft Launcher"),
]
GAME_HINTS = ("net.minecraft", "minecraft", "cpw.mods", "fabricmc", "quiltmc", "neoforge")
INSTANCE_DIRS = re.compile(r"/[Ii]nstances/([^/]+)")


@dataclass
class Game:
    pid: int
    instance: str        # the name as the launcher spells it
    launcher: str
    started: float       # when the process started (time.time())


def _read(path: Path) -> str:
    try:
        return path.read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return ""


def _started(pid: int) -> float:
    """When the process started, from /proc (falls back to now)."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        ticks = int(fields[19])
        uptime = float(Path("/proc/uptime").read_text().split()[0])
        return time.time() - uptime + ticks / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return time.time()


def _instance_name(cwd: str, cmdline: str) -> str | None:
    for text in (cwd, cmdline):
        m = INSTANCE_DIRS.search(text)
        if m:
            return m.group(1)
    m = re.search(r"--gameDir\s+(\S+)", cmdline)
    if m:
        return Path(m.group(1)).name or None
    return None


def find(instance: str) -> Game | None:
    """The running game for this instance (or any instance, for "*")."""
    want = instance.strip().lower()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        cmdline = _read(entry / "cmdline")
        if not cmdline or "java" not in cmdline.split(" ", 1)[0].lower():
            continue
        low = cmdline.lower()
        if not any(h in low for h in GAME_HINTS):
            continue
        try:
            cwd = os.readlink(entry / "cwd")
        except OSError:
            cwd = ""
        where = f"{cwd} {cmdline}"
        if want != "*" and want not in where.lower():
            continue
        name = _instance_name(cwd, cmdline) or (instance if want != "*" else "Minecraft")
        if want != "*" and want not in name.lower():
            name = instance  # the folder is named differently: show what you asked for
        launcher = next((label for key, label in LAUNCHERS if key in where.lower()), "")
        pid = int(entry.name)
        return Game(pid, name, launcher, _started(pid))
    return None
