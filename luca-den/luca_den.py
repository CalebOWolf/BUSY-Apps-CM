"""
Luca's Den 🏠🐺, the home base for all your Luca apps.

Takes turns: the "always on" apps (PC Stats, Weather Den, Aero Clock) each
get the bar for a minute in turn, instead of the highest priority always
winning. Between turns Luca waves you over to the next one with a glossy
"channel switch" card. Apps that only show up when something happens
(music, notifications, calls, focus rounds, ON AIR, chat) still jump in
over the top whenever they need to.

Check on everything: `--status` lists every Luca app, whether it's set to
start at login, whether it's running, and its priority.

    python luca_den.py                          # stats → weather → clock (→ updates), 60 s each
    python luca_den.py --apps clock,weather --seconds 120
    python luca_den.py --status
    python luca_den.py --install / --uninstall  # Linux: start at login

Only apps that are actually running take part, so leave one out by not
running it. Needs Pillow (pip install pillow).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import art  # noqa: E402
import service  # noqa: E402
from busybar import BarOffline, BusyBar, image, is_running  # noqa: E402
from turns import write_turn  # noqa: E402

APP = "luca_den"
SERVICE = "luca-den"
CARD_SECONDS = 1.6
REPO = Path(__file__).resolve().parent.parent

ROTATING = {"stats": "luca_pc_stats", "weather": "luca_weather_den", "clock": "luca_aero_clock",
            "updates": "luca_update_howl"}  # Update Howl only joins while updates are waiting

# Every Luca app: (folder, script, service name, app id, default priority, what it shows)
ALL_APPS = [
    ("luca-wood-aero", "luca_aero.py", None, "luca_wood_aero", "50", "Luca reacting to the buttons"),
    ("luca-now-playing", "now_playing.py", "luca-now-playing", "luca_now_playing", "50", "when music plays"),
    ("luca-pc-stats", "pc_stats.py", "luca-pc-stats", "luca_pc_stats", "20", "always (takes turns)"),
    ("luca-notify-den", "notify_den.py", "luca-notify-den", "luca_notify_den", "70", "on a notification"),
    ("luca-weather-den", "weather_den.py", "luca-weather-den", "luca_weather_den", "15", "always (takes turns)"),
    ("luca-pack-focus", "pack_focus.py", "luca-pack-focus", "luca_pack_focus", "60", "while you focus"),
    ("luca-aero-clock", "aero_clock.py", "luca-aero-clock", "luca_aero_clock", "10", "always (takes turns)"),
    ("luca-on-air", "on_air.py", "luca-on-air", "luca_on_air", "65", "when you're live / in a call"),
    ("luca-discord", "luca_discord.py", "luca-discord", "luca_discord", "64/70", "in a call / on a message"),
    ("luca-stream-chat", "stream_chat.py", "luca-stream-chat", "luca_stream_chat", "66/68", "on chat and alerts"),
    ("luca-blockland", "blockland.py", "luca-blockland", "luca_blockland", "55", "while Minecraft runs"),
    ("luca-update-howl", "update_howl.py", "luca-update-howl", "luca_update_howl", "18/30",
     "on new updates / its turn"),
    ("luca-den", "luca_den.py", "luca-den", "luca_den", "25", "between turns"),
]


class Den:
    def __init__(self, bar: BusyBar, apps: list[str], seconds: float, priority: int):
        self.bar, self.apps, self.seconds, self.priority = bar, apps, seconds, priority
        self.current: str | None = None
        self.until = 0.0
        self.online = False
        self.on_bar = False

    def present(self) -> list[str]:
        """The apps in the rotation that are running right now."""
        return [a for a in self.apps if is_running(a, fresh=20)]

    def upload_cards(self) -> None:
        for app in self.apps:
            for i in range(art.CARD_FRAMES):
                self.bar.upload_image(f"card_{app}_{i}.png", art.card(app, i))

    async def show_card(self, app: str, rotation: list[str]) -> None:
        """The channel switch: everyone steps aside, Luca waves you to `app`."""
        write_turn(APP, rotation, time.time() + CARD_SECONDS)
        if not self.online:
            await asyncio.to_thread(self.upload_cards)
            self.online = True
        await asyncio.to_thread(self.bar.upload_image, "back.png",
                                art.back_screen(rotation, app, int(self.seconds)))
        frames = int(CARD_SECONDS * 8)
        for i in range(frames):
            k = min(i, art.CARD_FRAMES - 1) if i < art.CARD_FRAMES else art.CARD_FRAMES - 2 + i % 2
            await asyncio.to_thread(self.bar.draw, [
                image("card", f"card_{app}_{k}.png", 0, 0),
                image("window", "back.png", 0, 0, display="back")], self.priority)
            self.on_bar = True
            write_turn(APP, rotation, time.time() + CARD_SECONDS)
            await asyncio.sleep(1 / 8)
        await asyncio.to_thread(self.bar.clear)
        self.on_bar = False


async def rotate(den: Den) -> None:
    retry, said = 2, None
    while True:
        try:
            here = den.present()
            if said != here:
                names = ", ".join(art.THEMES.get(a, (a,))[0].title() for a in here) or "none yet"
                print(f"  🏠 Taking turns: {names}")
                said = here
            if len(here) <= 1:
                # nobody to take turns with: let the one app (if any) show all the time
                den.current = here[0] if here else None
                write_turn(den.current, den.apps if here else [], time.time() + 5)
                await asyncio.sleep(1)
                continue
            now = time.time()
            if den.current not in here or now >= den.until:
                order = [a for a in den.apps if a in here]
                nxt = order[(order.index(den.current) + 1) % len(order)] if den.current in order else order[0]
                await den.show_card(nxt, den.apps)
                den.current, den.until = nxt, time.time() + den.seconds
                print(f"  ▶  {art.THEMES.get(nxt, (nxt,))[0].title()}")
            write_turn(den.current, den.apps, den.until)
            await asyncio.sleep(1)
            retry = 2
        except BarOffline as err:
            if den.online or retry == 2:
                print(f"🔌 BUSY Bar trouble: {err}; still taking turns, I'll keep trying quietly")
            den.online = den.on_bar = False
            den.current, den.until = here[0] if here else None, time.time() + den.seconds
            write_turn(den.current, den.apps, den.until)
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


# --------------------------------------------------------------------------
# --status
# --------------------------------------------------------------------------
def service_state(name: str | None) -> tuple[str, str]:
    if not name:
        return "-", "-"
    installed = "yes" if service.unit_path(name).exists() else "no"
    if not shutil.which("systemctl"):
        return installed, "?"
    out = subprocess.run(["systemctl", "--user", "is-active", f"{name}.service"],
                         capture_output=True, text=True).stdout.strip() or "?"
    return installed, out


def status() -> None:
    rows = [("App", "Start at login", "Service", "Shows", "Priority")]
    for folder, script, svc, app_id, prio, shows in ALL_APPS:
        if not (REPO / folder / script).exists():
            continue
        installed, active = service_state(svc)
        if is_running(app_id):
            active = "running" if active in ("?", "-", "inactive") else active
        rows.append((folder, installed, active, shows, prio))
    widths = [max(len(r[i]) for r in rows) for i in range(5)]
    for k, r in enumerate(rows):
        print("  " + "  ".join(c.ljust(w) for c, w in zip(r, widths)))
        if k == 0:
            print("  " + "  ".join("-" * w for w in widths))
    print("\n  Start one at login:   ~/.venvs/luca/bin/python <folder>/<app>.py --install")
    print("  Watch one:            journalctl --user -u <service> -f")


def install(args) -> None:
    service.check([("Pillow (pip install pillow)", service.importable("PIL"))],
                  required={"Pillow (pip install pillow)"})
    command = [sys.executable, str(Path(__file__).resolve()), "--host", args.host,
               "--apps", args.apps, "--seconds", str(args.seconds), "--priority", str(args.priority)]
    service.install(SERVICE, "Luca's Den for the BUSY Bar", command, args.token,
                    "Your always-on Luca apps now take turns.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apps", default="stats,weather,clock,updates",
                    help="which always-on apps take turns, in order: stats, weather, clock")
    ap.add_argument("--seconds", type=float, default=60, help="how long each turn lasts (default 60)")
    ap.add_argument("--status", action="store_true", help="list every Luca app and whether it's running")
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"),
                    help="API key, if HTTP access is set to 'key' mode (or set BUSYBAR_TOKEN)")
    ap.add_argument("--priority", type=int, default=25,
                    help="draw priority of the switch cards (default 25, just above the always-on apps)")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true",
                       help="Linux: start automatically at login (systemd user service)")
    group.add_argument("--uninstall", action="store_true", help="Linux: stop starting at login")
    args = ap.parse_args()

    if args.status:
        return status()
    names = [a.strip().lower() for a in args.apps.split(",") if a.strip()]
    unknown = [n for n in names if n not in ROTATING]
    if unknown or not names:
        ap.error(f"--apps takes {', '.join(ROTATING)} (got {', '.join(unknown) or 'nothing'})")
    if args.seconds < 10:
        ap.error("--seconds must be at least 10")
    if args.install:
        return install(args)
    if args.uninstall:
        return service.uninstall(SERVICE)

    bar = BusyBar(args.host, APP, args.token)
    den = Den(bar, [ROTATING[n] for n in names], args.seconds, args.priority)
    print(f"🏠 Luca's Den: {', '.join(names)} take turns, {args.seconds:g} s each.")
    print("   Only apps that are running take part. Ctrl+C to stop (everyone goes back to normal).")

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(rotate(den))
    except KeyboardInterrupt:
        pass
    finally:
        write_turn(None, [], 0)  # release everyone straight away
        if den.on_bar:
            try:
                bar.clear()
            except BarOffline:
                pass
        print("\n🌙 Den closed: the apps go back to showing whenever they like.")


if __name__ == "__main__":
    main()
