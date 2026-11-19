#!/usr/bin/env python3
"""
Install your Luca apps for the BUSY Bar in one go (Linux, systemd).

    python install.py                     pick from a menu (Enter = all of them)
    python install.py --all               every app, asking only for what's needed
    python install.py now-playing clock   just these
    python install.py --list              what's available, and what's installed
    python install.py --uninstall clock   stop some (or --uninstall --all) starting at login

It makes Luca's Python environment (~/.venvs/luca), installs the Python
packages the chosen apps need, tells you about any Arch packages they need
(and can install them with pacman), then runs each app's own --install.
Each app's folder still has its own `--install` if you'd rather do one at a
time.

Answers can be given up front, so nothing is asked:

    python install.py --all --city "Berlin" --twitch yourchannel --yes

Uses only Python's standard library, so it runs with the system Python.
"""

from __future__ import annotations

import argparse
import getpass
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent
DEFAULT_VENV = Path.home() / ".venvs" / "luca"


@dataclass(eq=False)  # compared by identity, so apps can go in sets and dicts
class App:
    key: str                     # what you type: "now-playing"
    folder: str
    script: str
    service: str
    blurb: str
    pip: list[str] = field(default_factory=list)
    system: dict[str, str] = field(default_factory=dict)   # command → Arch package
    optional_system: dict[str, str] = field(default_factory=dict)


APPS = [
    App("now-playing", "luca-now-playing", "now_playing.py", "luca-now-playing",
        "your music, with Luca in headphones", ["pillow", "busylib"],
        {"playerctl": "playerctl"}, {"cava": "cava", "wpctl": "wireplumber"}),
    App("pc-stats", "luca-pc-stats", "pc_stats.py", "luca-pc-stats",
        "CPU, RAM, GPU and temperatures", ["pillow", "psutil", "busylib"]),
    App("notify-den", "luca-notify-den", "notify_den.py", "luca-notify-den",
        "your desktop notifications", ["pillow", "dbus-fast", "busylib"]),
    App("weather", "luca-weather-den", "weather_den.py", "luca-weather-den",
        "live local weather (asks for your city)", ["pillow", "busylib"]),
    App("pack-focus", "luca-pack-focus", "pack_focus.py", "luca-pack-focus",
        "a Pomodoro focus timer (selector on CUSTOM to start)", ["pillow", "busylib"]),
    App("clock", "luca-aero-clock", "aero_clock.py", "luca-aero-clock",
        "a desk clock with the real sky", ["pillow", "busylib"]),
    App("on-air", "luca-on-air", "on_air.py", "luca-on-air",
        "an ON AIR sign for OBS, calls and the camera", ["pillow", "busylib"],
        {"pactl": "libpulse"}),
    App("discord", "luca-discord", "luca_discord.py", "luca-discord",
        "Discord calls and messages", ["pillow", "dbus-fast", "busylib"], {"pactl": "libpulse"}),
    App("stream-chat", "luca-stream-chat", "stream_chat.py", "luca-stream-chat",
        "Twitch / YouTube live chat (asks for your channel)", ["pillow", "busylib"]),
    App("den", "luca-den", "luca_den.py", "luca-den",
        "lets stats, weather and clock take turns", ["pillow"]),
]
BY_KEY = {a.key: a for a in APPS}
ALWAYS_ON = {"pc-stats", "weather", "clock"}


# --------------------------------------------------------------------------
# Little helpers
# --------------------------------------------------------------------------
def say(msg: str = "") -> None:
    print(msg, flush=True)


def ask(prompt: str, default: str = "", secret: bool = False, yes: bool = False) -> str:
    """Ask a question (or take the default when --yes is given)."""
    if yes:
        return default
    hint = f" [{default}]" if default and not secret else ""
    try:
        answer = (getpass.getpass if secret else input)(f"  {prompt}{hint}: ").strip()
    except EOFError:
        answer = ""
    return answer or default


def confirm(prompt: str, default: bool = True, yes: bool = False) -> bool:
    if yes:
        return default
    answer = ask(f"{prompt} ({'Y/n' if default else 'y/N'})", yes=False).lower()
    return default if not answer else answer.startswith("y")


def unit_exists(name: str) -> bool:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return (config / "systemd" / "user" / f"{name}.service").exists()


def run(cmd: list[str], **kw) -> int:
    say("  $ " + " ".join(c if " " not in c else repr(c) for c in cmd))
    return subprocess.run(cmd, **kw).returncode


# --------------------------------------------------------------------------
# Choosing apps
# --------------------------------------------------------------------------
def show_list() -> None:
    say("Luca apps:\n")
    for i, a in enumerate(APPS, 1):
        mark = "✅ installed" if unit_exists(a.service) else "  "
        say(f"  {i:2}. {a.key:12} {a.blurb:52} {mark}")
    say("\n  (Luca Wood Aero is a toy you run by hand: see luca-wood-aero/README.md)")


def pick_from_menu() -> list[App]:
    show_list()
    say("\nWhich apps? Type numbers or names separated by spaces, or press Enter for all.")
    raw = ask("Apps", "all")
    if raw.lower() in ("all", "*", ""):
        return list(APPS)
    chosen = []
    for token in raw.replace(",", " ").split():
        if token.isdigit() and 1 <= int(token) <= len(APPS):
            chosen.append(APPS[int(token) - 1])
        elif token in BY_KEY:
            chosen.append(BY_KEY[token])
        else:
            say(f"  (skipping '{token}': not an app name)")
    return list(dict.fromkeys(chosen))


# --------------------------------------------------------------------------
# Setting up
# --------------------------------------------------------------------------
def ensure_venv(venv: Path, packages: set[str], skip_pip: bool) -> Path:
    python = venv / "bin" / "python"
    if not python.exists():
        say(f"\n🐍 Making Luca's Python environment in {venv}")
        venv.parent.mkdir(parents=True, exist_ok=True)
        if run([sys.executable, "-m", "venv", str(venv)]) != 0:
            raise SystemExit("Couldn't make the Python environment (on Arch: sudo pacman -S python).")
    if packages and not skip_pip:
        say(f"\n📦 Installing Python packages: {', '.join(sorted(packages))}")
        if run([str(python), "-m", "pip", "install", "--quiet", "--upgrade", *sorted(packages)]) != 0:
            raise SystemExit("pip couldn't install the packages. Are you online?")
    return python


def check_system(apps: list[App], yes: bool, skip: bool) -> None:
    needed = {pkg for a in apps for cmd, pkg in a.system.items() if not shutil.which(cmd)}
    nice = {pkg for a in apps for cmd, pkg in a.optional_system.items() if not shutil.which(cmd)}
    if not needed and not nice:
        return
    say("\n🐧 System packages:")
    if needed:
        say(f"   needed:   {' '.join(sorted(needed))}")
    if nice:
        say(f"   optional: {' '.join(sorted(nice))}  (the visualizer and volume wheel)")
    packages = sorted(needed | nice)
    if skip or not shutil.which("pacman"):
        say(f"   Install them with your package manager, e.g.  sudo pacman -S --needed {' '.join(packages)}")
        return
    if confirm(f"Install them now with  sudo pacman -S --needed {' '.join(packages)}", True, yes):
        run(["sudo", "pacman", "-S", "--needed", "--noconfirm", *packages])


def app_options(app: App, args, yes: bool) -> list[str] | None:
    """The extra settings each app needs. None means skip this app."""
    opts: list[str] = []
    if args.host:
        opts += ["--host", args.host]
    if args.token:
        opts += ["--token", args.token]
    k = app.key
    if k == "weather":
        city = args.city or ask("Your city for the weather (e.g. Berlin, or Portland, Oregon)", yes=yes)
        if not city:
            say("  ⏭️  Skipping Weather Den: it needs a city (--city)")
            return None
        opts += ["--city", city]
        if args.fahrenheit or confirm("Fahrenheit (°F) instead of °C?", False, yes):
            opts.append("--fahrenheit")
    elif k == "stream-chat":
        twitch = args.twitch or ask("Your Twitch channel name (blank to skip)", yes=yes)
        if not twitch:
            say("  ⏭️  Skipping Stream Chat: it needs a channel (--twitch). "
                "For YouTube, install it from its folder with your video ID.")
            return None
        opts += ["--twitch", twitch]
    elif k == "on-air":
        pw = args.obs_password if args.obs_password is not None else \
            ask("OBS WebSocket password (blank if none / no OBS)", secret=True, yes=yes)
        if pw:
            opts += ["--obs-password", pw]
    elif k == "discord":
        cid = args.discord_client_id or ask("Discord app Client ID for rich mode (blank = basic mode)", yes=yes)
        if cid:
            secret = args.discord_client_secret or ask("Discord app Client Secret", secret=True, yes=yes)
            if secret:
                opts += ["--client-id", cid, "--client-secret", secret]
                say("  💡 After installing, open Discord: it'll ask you once to Authorize Luca.")
    elif k == "pc-stats" and args.fahrenheit:
        opts.append("--fahrenheit")
    if k == "clock" and args.twelve_hour:
        opts.append("--12h")
    return opts


def install(apps: list[App], args) -> None:
    yes = args.yes
    if not shutil.which("systemctl"):
        raise SystemExit("This installs systemd user services, so it needs Linux with systemd.")
    picked = {a.key for a in apps}
    if "den" not in picked and len(picked & ALWAYS_ON) >= 2:
        if confirm("You picked more than one always-on app. Add Luca's Den so they take turns?", True, yes):
            apps.append(BY_KEY["den"])
    say("\nAnswer a few questions (Enter keeps the default):")
    plans = []
    for a in apps:
        say(f"\n• {a.key}: {a.blurb}")
        opts = app_options(a, args, yes)
        if opts is not None:
            plans.append((a, opts))
    if not plans:
        raise SystemExit("Nothing to install.")

    packages = {p for a, _ in plans for p in a.pip}
    check_system([a for a, _ in plans], yes, args.no_system)
    python = ensure_venv(Path(args.venv).expanduser(), packages, args.no_pip)

    say("\n🐺 Setting up the apps to start at login:")
    done, failed = [], []
    for a, opts in plans:
        say(f"\n— {a.key}")
        code = run([str(python), str(REPO / a.folder / a.script), *opts, "--install"])
        (done if code == 0 else failed).append(a.key)

    say("\n" + "─" * 60)
    if done:
        say(f"✨ Installed: {', '.join(done)}")
    if failed:
        say(f"⚠️  Didn't work: {', '.join(failed)}  (scroll up for why; you can retry one with "
            f"`python install.py {failed[0]}`)")
    say("\nCheck on everything:  " + f"{python} {REPO / 'luca-den' / 'luca_den.py'} --status")
    say("Watch one:            journalctl --user -u luca-<app> -f")


def uninstall(apps: list[App], args) -> None:
    python = Path(args.venv).expanduser() / "bin" / "python"
    py = str(python) if python.exists() else sys.executable
    for a in apps:
        if unit_exists(a.service):
            say(f"\n— {a.key}")
            run([py, str(REPO / a.folder / a.script), "--uninstall"])
        else:
            say(f"  {a.key}: not installed")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("apps", nargs="*", metavar="APP", help=f"apps to install: {', '.join(BY_KEY)}")
    ap.add_argument("--all", action="store_true", help="every app")
    ap.add_argument("--list", action="store_true", help="list the apps and what's installed")
    ap.add_argument("--uninstall", action="store_true", help="stop the given apps starting at login")
    ap.add_argument("--yes", "-y", action="store_true", help="don't ask: use the answers given and defaults")
    ap.add_argument("--host", help="the BUSY Bar's address over Wi-Fi (default: USB)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"), help="the bar's API key, if it needs one")
    ap.add_argument("--city", help="Weather Den: your city")
    ap.add_argument("--fahrenheit", action="store_true", help="Weather / PC Stats: °F")
    ap.add_argument("--12h", dest="twelve_hour", action="store_true", help="Aero Clock: 12-hour time")
    ap.add_argument("--twitch", help="Stream Chat: your Twitch channel")
    ap.add_argument("--obs-password", default=None, help="On Air: OBS WebSocket password")
    ap.add_argument("--discord-client-id", help="Discord: your application's Client ID (rich mode)")
    ap.add_argument("--discord-client-secret", help="Discord: its Client Secret")
    ap.add_argument("--venv", default=str(DEFAULT_VENV), help=f"where Luca's Python lives (default {DEFAULT_VENV})")
    ap.add_argument("--no-pip", action="store_true", help="don't install Python packages")
    ap.add_argument("--no-system", action="store_true", help="don't offer to install Arch packages")
    args = ap.parse_args()

    unknown = [a for a in args.apps if a not in BY_KEY]
    if unknown:
        ap.error(f"unknown app(s): {', '.join(unknown)}. Choose from: {', '.join(BY_KEY)}")
    if args.list:
        return show_list()

    if args.all:
        apps = list(APPS)
    elif args.apps:
        apps = [BY_KEY[a] for a in dict.fromkeys(args.apps)]
    elif args.uninstall:
        ap.error("say which apps to uninstall, or --all")
    elif args.yes:
        ap.error("with --yes, say which apps (or --all)")
    else:
        say("🐺 Luca app installer\n")
        apps = pick_from_menu()
        if not apps:
            raise SystemExit("No apps picked.")
    if args.uninstall:
        return uninstall(apps, args)
    install(apps, args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
