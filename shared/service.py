"""
Start an app automatically at login on Linux, as a systemd user service.

    service.install("luca-now-playing", "Luca Now Playing for the BUSY Bar",
                    [sys.executable, __file__, "--host", host], token=token)
    service.uninstall("luca-now-playing")
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path


def unit_path(name: str) -> Path:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config / "systemd" / "user" / f"{name}.service"


def quote(arg: str) -> str:
    """Quote one argument for a systemd unit file."""
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


def systemctl(*args: str) -> None:
    cmd = ["systemctl", "--user", *args]
    print("  $ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def require_systemd() -> None:
    if not sys.platform.startswith("linux") or not shutil.which("systemctl"):
        raise SystemExit("--install / --uninstall set up a systemd user service, so they "
                         "only work on Linux with systemd.")


def importable(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def check(requirements: list[tuple[str, bool]], required: set[str] = frozenset()) -> None:
    """Warn about missing pieces; stop if a required one is missing."""
    missing = [label for label, ok in requirements if not ok]
    if missing:
        print("⚠️  Not found for this Python, install first: " + ", ".join(missing))
        if any(label in required for label in missing):
            raise SystemExit(1)


def install(name: str, description: str, command: list[str], token: str | None = None,
            done_message: str = "", env: dict[str, str] | None = None) -> None:
    """`env` adds more private settings (like a password) the same way as the
    token: into the service file only, which only you can read."""
    require_systemd()
    lines = [
        "[Unit]",
        f"Description={description}",
        "",
        "[Service]",
        "ExecStart=" + " ".join(quote(a) for a in command),
        "Environment=PYTHONUNBUFFERED=1",
    ]
    if token:
        lines.append("Environment=" + quote(f"BUSYBAR_TOKEN={token}"))
    for key, value in (env or {}).items():
        if value:
            lines.append("Environment=" + quote(f"{key}={value}"))
    lines += ["Restart=on-failure", "RestartSec=10", "", "[Install]", "WantedBy=default.target", ""]

    path = unit_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    path.chmod(0o600)  # it may hold your API key
    print(f"📝 Wrote {path}")
    systemctl("daemon-reload")
    systemctl("enable", f"{name}.service")
    # restart (not just start): a re-install then runs the new code and settings right away
    systemctl("restart", f"{name}.service")
    print("✨ Done! " + (done_message or f"{description} now starts at login."))
    print(f"   Watch what it's up to:  journalctl --user -u {name} -f")


def uninstall(name: str) -> None:
    require_systemd()
    path = unit_path(name)
    if path.exists():
        systemctl("disable", "--now", f"{name}.service")
        path.unlink()
        systemctl("daemon-reload")
        print(f"🗑️  Removed {path}. It won't start at login any more.")
    else:
        print(f"Nothing to remove: {name} isn't set to start at login.")
