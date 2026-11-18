"""
Luca Pack Focus 🌕🐺, a Pomodoro-style focus timer for the BUSY Bar.

Focus for 25 minutes while a moon waxes from new to full beside the
countdown. When it's full, Luca howls and it's time for a 5-minute break
under a sunset sky. After every 4th round you get a long 15-minute break
under the stars. The back screen becomes "Luca Focus", a Windows 7-style
timer window that keeps count of today's focus rounds. While you focus,
Luca Notify Den holds your notifications until the break.

    Start   start / pause
    OK      skip to the next part
    Back    start this part over
    Wheel   add or take away a minute (before starting, or while paused)

    python pack_focus.py                         # 25 / 5 / 15 minutes, 4 rounds
    python pack_focus.py --focus 50m --break 10m --long 30m --rounds 3
    python pack_focus.py --auto                  # roll into the next part by itself
    python pack_focus.py --install               # Linux: start at login, wait in the background
    python pack_focus.py --uninstall

Started at login (--install), it waits out of sight: move the bar's selector to
CUSTOM to bring Luca up, then press Start. Needs Pillow; buttons also need
busylib (pip install pillow busylib).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import art  # noqa: E402
import service  # noqa: E402
from busybar import (BarOffline, BusyBar, image, input_events, is_press,  # noqa: E402
                     is_selector, is_wheel, rect)

APP = "luca_pack_focus"
SERVICE = "luca-pack-focus"
HOWL_SECONDS = 5
WAIT_TIMEOUT = 10 * 60   # in the background: step aside if nobody starts the next part
SUMMON = "custom"        # the selector position that brings Luca up
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
STATS_FILE = CACHE_DIR / "luca-pack-focus.json"
# Other apps (Luca Notify Den) read this to stay quiet while you focus.
HUSH_FILE = Path(os.environ.get("XDG_RUNTIME_DIR") or CACHE_DIR) / "luca-focus.json"


def minutes(text: str) -> float:
    """'25m', '25' or '1.5' → minutes; '90s' → seconds. Returns seconds."""
    value = text.strip().lower()
    unit = 1 if value.endswith("s") else 60
    try:
        seconds = float(value.rstrip("ms").strip()) * unit
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' isn't a time; try 25m, 5m or 90s")
    if seconds < 1:
        raise argparse.ArgumentTypeError("the time has to be more than zero")
    return seconds


class Today:
    """How many focus rounds and minutes you've done today (kept across restarts)."""

    def __init__(self):
        self.sessions, self.minutes, self.day = 0, 0.0, date.today().isoformat()
        try:
            data = json.loads(STATS_FILE.read_text())
            if data.get("date") == self.day:
                self.sessions, self.minutes = data["sessions"], data["minutes"]
        except (OSError, ValueError, KeyError):
            pass

    def add(self, seconds: float) -> None:
        if self.day != date.today().isoformat():  # a new day
            self.sessions, self.minutes, self.day = 0, 0.0, date.today().isoformat()
        self.sessions += 1
        self.minutes += seconds / 60
        try:
            STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATS_FILE.write_text(json.dumps({"date": self.day, "sessions": self.sessions,
                                              "minutes": round(self.minutes, 1)}))
        except OSError:
            pass


class Timer:
    """The Pomodoro rhythm: focus, break, focus, break… long break."""

    def __init__(self, lengths: dict[str, float], rounds: int, auto: bool):
        self.lengths, self.rounds, self.auto = dict(lengths), rounds, auto
        self.today = Today()
        self.done_rounds = 0          # focus rounds finished in this cycle
        self.begin("focus")

    def begin(self, phase: str) -> None:
        self.phase, self.total = phase, self.lengths[phase]
        self.remaining, self.state = self.total, "idle"   # idle, running, paused, done
        self.ends_at = 0.0
        self.howl_until = 0.0
        self.idle_since = time.monotonic()

    def left(self) -> float:
        if self.state == "running":
            return max(0.0, self.ends_at - time.monotonic())
        return self.remaining

    @property
    def focusing(self) -> bool:
        return self.phase == "focus" and self.state == "running"

    def toggle(self) -> None:
        if self.state in ("idle", "paused"):
            self.ends_at, self.state = time.monotonic() + self.remaining, "running"
        elif self.state == "running":
            self.remaining, self.state = self.left(), "paused"
            self.idle_since = time.monotonic()
        elif self.state == "done":  # pressed during the howl: go straight on
            self.advance(start=True)

    def next_phase(self) -> str:
        if self.phase != "focus":
            return "focus"
        return "long" if self.done_rounds >= self.rounds else "short"

    def advance(self, start: bool = False) -> None:
        if self.phase == "long":
            self.done_rounds = 0  # a fresh cycle after the long break
        self.begin(self.next_phase())
        if start or self.auto:
            self.toggle()

    def skip(self) -> None:
        if self.phase == "focus" and self.state != "done":
            self.done_rounds = min(self.done_rounds + 1, self.rounds)  # skipping still counts the round
        self.advance()

    def reset(self) -> None:
        self.begin(self.phase)

    def adjust(self, minutes_: int) -> bool:
        if self.state not in ("idle", "paused"):
            return False
        self.remaining = max(60.0, self.remaining + minutes_ * 60)
        if self.state == "idle":
            self.total = self.remaining
        else:
            self.total = max(self.total, self.remaining)
        return True

    def tick(self) -> str | None:
        """Move time along; returns "finished" when a part just ended."""
        now = time.monotonic()
        if self.state == "running" and self.left() <= 0:
            self.state, self.remaining, self.howl_until = "done", 0.0, now + HOWL_SECONDS
            if self.phase == "focus":
                self.done_rounds += 1
                self.today.add(self.total)
            return "finished"
        if self.state == "done" and now >= self.howl_until:
            self.advance()
        return None


class Pack:
    def __init__(self, bar: BusyBar, timer: Timer, priority: int, fps: float, background: bool):
        self.bar, self.timer, self.priority, self.fps = bar, timer, priority, fps
        self.background = background
        self.summoned = not background
        self.online = False
        self.on_bar = False
        self.slot = 0
        self.back_key = None
        self.frame = 0
        self.light = False

    @property
    def wanted(self) -> bool:
        t = self.timer
        if not self.background or self.summoned or t.state in ("running", "done"):
            return True
        # paused or waiting for the next part: stay a while, then step aside
        return time.monotonic() - t.idle_since < WAIT_TIMEOUT and (t.state == "paused" or t.done_rounds)

    def upload_static(self) -> None:
        for phase in art.PHASES:
            for i in range(art.SKY_FRAMES):
                self.bar.upload_image(f"sky_{phase}_{i}.png", art.sky(phase, i))
        for step in range(art.MOON_STEPS + 1):
            self.bar.upload_image(f"moon_{step:02d}.png", art.moon(step))
        for pose, n in art.POSES.items():
            for i in range(n):
                self.bar.upload_image(f"tile_{pose}_{i}.png", art.tile(pose, i))
        for ch in art.CLOCK_CHARS:
            self.bar.upload_image(f"char_{art.char_name(ch)}.png", art.char(ch))
            self.bar.upload_image(f"char_{art.char_name(ch)}_dim.png", art.char(ch, dim=True))
        for name in art.WORDS:
            self.bar.upload_image(f"word_{name}.png", art.word(name))
        self.back_key = None

    def upload_back(self) -> None:
        t = self.timer
        key = (t.phase, int(t.left()), t.state, t.done_rounds, t.today.sessions)
        if key == self.back_key:
            return
        slot = 1 - self.slot
        self.bar.upload_image(f"back_{slot}.png", art.back_screen(
            t.phase, t.left(), t.total, t.state, t.done_rounds, t.rounds,
            t.today.sessions, t.today.minutes))
        self.slot, self.back_key = slot, key

    def elements(self) -> list[dict]:
        t, f = self.timer, self.frame
        if t.phase == "focus":
            step = round(art.MOON_STEPS * (1 - t.left() / t.total)) if t.state != "done" else art.MOON_STEPS
        else:
            step = art.MOON_STEPS
        els = [image("sky", f"sky_{t.phase}_{f % art.SKY_FRAMES}.png", 0, 0),
               image("moon", f"moon_{step:02d}.png", *art.MOON_XY)]

        waiting = t.state == "idle" and (t.done_rounds or t.phase != "focus")
        if t.state == "done":
            els.append(image("word", "word_awoo.png", *art.WORD_XY))
        elif waiting and (f // (2 * self.fps)) % 2:  # "START?" takes turns with the time
            els.append(image("word", "word_start.png", *art.WORD_XY))
        else:
            blink_off = t.state == "paused" and (f // max(1, round(self.fps / 2))) % 2
            if not blink_off:
                dim = "_dim" if t.state in ("idle", "paused") else ""
                x, y = art.CLOCK_XY
                for i, ch in enumerate(art.clock(t.left())):
                    els.append(image(f"t{i}", f"char_{art.char_name(ch)}{dim}.png", x, y))
                    x += art.char_width(ch)

        px, py = art.PAWS_XY  # one paw marker per round of the cycle
        for i in range(t.rounds):
            if i < t.done_rounds:
                color = "#50F0BEFF"
            elif i == t.done_rounds and t.phase == "focus":
                color = "#FFFFFFFF" if t.state != "running" or (f // self.fps) % 2 else "#A0C8FFFF"
            else:
                color = "#3C5A96FF"
            els.append(rect(f"paw{i}", px + i * 4, py + 2, 2, 1, color))

        pose = {"done": "howling", "paused": "paused"}.get(t.state)
        if pose is None:
            if t.state == "running":
                pose = "focused" if t.phase == "focus" else "resting"
            else:
                pose = "waiting"
        n = art.POSES[pose]
        els.append(image("luca", f"tile_{pose}_{(f // max(1, round(self.fps / 2))) % n}.png", 0, 0))
        els.append(image("window", f"back_{self.slot}.png", 0, 0, display="back"))
        return els


def write_hush(focusing: bool) -> None:
    """Tell Luca Notify Den whether to hold notifications (refreshed every second)."""
    try:
        HUSH_FILE.parent.mkdir(parents=True, exist_ok=True)
        HUSH_FILE.write_text(json.dumps({"focusing": focusing, "updated": time.time()}))
    except OSError:
        pass


async def animate(pack: Pack) -> None:
    retry, last_hush = 2, 0.0
    while True:
        t = pack.timer
        if t.tick() == "finished":
            name = "Focus round" if t.phase == "focus" else art.PHASE_NAMES[t.phase]
            print(f"  🌕 {name} done! AWOO!  (today: {t.today.sessions} rounds)")
            pack.light = True
        if time.monotonic() - last_hush >= 1:
            await asyncio.to_thread(write_hush, t.focusing)
            last_hush = time.monotonic()
        try:
            if pack.wanted:
                if not pack.online:
                    await asyncio.to_thread(pack.upload_static)
                    pack.online, retry = True, 2
                await asyncio.to_thread(pack.upload_back)
                led = "#FFE678FF" if pack.light else None
                await asyncio.to_thread(pack.bar.draw, pack.elements(), pack.priority, led)
                pack.light, pack.on_bar = False, True
                pack.frame += 1
            elif pack.on_bar:
                await asyncio.to_thread(pack.bar.clear)
                pack.on_bar = False
            await asyncio.sleep(1 / pack.fps)
        except BarOffline as err:
            if pack.online or retry == 2:
                print(f"🔌 Can't reach the BUSY Bar ({err}); the timer keeps running, "
                      "I'll keep trying quietly")
            pack.online = pack.on_bar = False
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def listen(pack: Pack) -> None:
    async for event in input_events(pack.bar):
        t = pack.timer
        if is_selector(event):
            if pack.background:
                pack.summoned = event.position == SUMMON
                if pack.summoned:
                    print("  🐺 Summoned: press Start to begin")
            continue
        if not pack.on_bar:
            continue  # buttons belong to the bar while Luca is away
        if is_wheel(event):
            if t.adjust(1 if event.delta > 0 else -1):
                print(f"  ⏱️  {art.PHASE_NAMES[t.phase]}: {art.clock(t.left())}")
        elif is_press(event):
            if event.button == "start":
                t.toggle()
                print(f"  {'▶️  Go' if t.state == 'running' else '⏸️  Paused'}: "
                      f"{art.PHASE_NAMES[t.phase]} {art.clock(t.left())}")
            elif event.button == "ok":
                t.skip()
                print(f"  ⏭️  On to: {art.PHASE_NAMES[t.phase]}")
            elif event.button == "back":
                t.reset()
                print(f"  ↩️  Starting {art.PHASE_NAMES[t.phase].lower()} over")


async def run(pack: Pack) -> None:
    await asyncio.gather(animate(pack), listen(pack))


def install(args) -> None:
    service.check([
        ("Pillow (pip install pillow)", service.importable("PIL")),
        ("busylib (pip install busylib)", service.importable("busylib")),
    ], required={"Pillow (pip install pillow)", "busylib (pip install busylib)"})
    command = [sys.executable, str(Path(__file__).resolve()), "--host", args.host,
               "--focus", args.focus_text, "--break", args.break_text, "--long", args.long_text,
               "--rounds", str(args.rounds), "--priority", str(args.priority), "--background"]
    if args.auto:
        command.append("--auto")
    service.install(SERVICE, "Luca Pack Focus for the BUSY Bar", command, args.token,
                    "Luca waits in the background: move the bar's selector to CUSTOM to focus.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--focus", default="25m", metavar="TIME", help="focus length (default 25m)")
    ap.add_argument("--break", dest="short", default="5m", metavar="TIME",
                    help="short break (default 5m)")
    ap.add_argument("--long", default="15m", metavar="TIME", help="long break (default 15m)")
    ap.add_argument("--rounds", type=int, default=4,
                    help="focus rounds before a long break (default 4)")
    ap.add_argument("--auto", action="store_true", help="start the next part by itself")
    ap.add_argument("--background", action="store_true",
                    help="wait out of sight until the selector is moved to CUSTOM "
                         "(what --install uses)")
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"),
                    help="API key, if HTTP access is set to 'key' mode (or set BUSYBAR_TOKEN)")
    ap.add_argument("--priority", type=int, default=60,
                    help="draw priority 1-100 (default 60: over music and stats, "
                         "under notifications)")
    ap.add_argument("--fps", type=float, default=6, help="animation speed (default 6)")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true",
                       help="Linux: start at login and wait in the background")
    group.add_argument("--uninstall", action="store_true", help="Linux: stop starting at login")
    args = ap.parse_args()
    args.focus_text, args.break_text, args.long_text = args.focus, args.short, args.long
    try:
        lengths = {"focus": minutes(args.focus), "short": minutes(args.short),
                   "long": minutes(args.long)}
    except argparse.ArgumentTypeError as err:
        ap.error(str(err))
    if not 1 <= args.rounds <= 8:
        ap.error("--rounds must be between 1 and 8")
    if not 1 <= args.priority <= 100:
        ap.error("--priority must be between 1 and 100")

    if args.install:
        return install(args)
    if args.uninstall:
        return service.uninstall(SERVICE)

    bar = BusyBar(args.host, APP, args.token)
    timer = Timer(lengths, args.rounds, args.auto)
    pack = Pack(bar, timer, args.priority, args.fps, args.background)
    f, s, lg = (art.clock(lengths[k]) for k in ("focus", "short", "long"))
    print(f"🌕 Pack Focus: {f} focus, {s} break, {lg} long break after {args.rounds} rounds"
          + (" (rolls on by itself)" if args.auto else ""))
    if timer.today.sessions:
        print(f"   Today so far: {timer.today.sessions} rounds, {timer.today.minutes:.0f} min")
    if args.background:
        print(f"🐺 Waiting in the background: move the BUSY Bar's selector to {SUMMON.upper()}.")
    else:
        print(f"🐺 Luca is on the BUSY Bar at {args.host}. Press Start to begin.")
    print("   Start = start/pause, OK = skip, Back = start over, wheel = ±1 min. Ctrl+C to stop.")

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(run(pack))
    except KeyboardInterrupt:
        pass
    finally:
        try:
            HUSH_FILE.unlink()
        except OSError:
            pass
        if pack.on_bar:
            try:
                bar.clear()
            except BarOffline:
                pass
        print("\n🌙 The pack rests.")


if __name__ == "__main__":
    main()
