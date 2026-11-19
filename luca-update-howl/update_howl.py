"""
Luca Update Howl 📦🐺, Arch updates on the BUSY Bar (via checkupdates and paru).

Every 30 minutes Luca checks what's waiting: the official repos (with
checkupdates, which never touches your real package database) and the AUR
(paru -Qua). He pops up for 20 seconds when something new arrives, howling
for a kernel update, and puts on a hard hat when you need to reboot. Right
after you update (paru), he checks again, so the count drops by itself.

While updates are waiting and Luca's Den is running, he also takes his turn
with the clock, weather and stats. When everything's fresh he stays out of
the way. Nothing is ever installed for you: updating is still `paru`.

The front takes turns: "6 UPDATES", "AUR 2", the big ones (kernel, drivers,
systemd…), "REBOOT". The back screen is a Windows 7-style "Luca Update Howl"
window with the list.

    Start / Back   next / previous page
    OK             hide until something changes

    python update_howl.py
    python update_howl.py --every 60m --no-aur
    python update_howl.py --demo                # pretend updates, a reboot, then all fresh
    python update_howl.py --install / --uninstall

Arch Linux. Needs pacman-contrib (checkupdates) and paru for the AUR, plus
Pillow; buttons need busylib (pip install pillow busylib).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import art  # noqa: E402
import service  # noqa: E402
import updates  # noqa: E402
from busybar import BarOffline, BusyBar, Scroller, image, input_events, is_press, is_wheel  # noqa: E402
from turns import TurnTaker, read_turn  # noqa: E402

APP = "luca_update_howl"
SERVICE = "luca-update-howl"
POP_SECONDS = 20          # how long Luca shows himself when there's news
PAGE_SECONDS = 4
SETTLE_SECONDS = 15       # after paru touches the package database, wait for it to finish
POP_PRIORITY_BONUS = 12   # pop-ups go a little higher than his turns


def parse_time(text: str) -> float:
    """"30m", "2h", "90" (minutes) → seconds."""
    text = text.strip().lower()
    unit = {"s": 1, "m": 60, "h": 3600}.get(text[-1:], None)
    value = float(text[:-1] if unit else text)
    return value * (unit or 60)


class Howl:
    def __init__(self, bar: BusyBar, priority: int, fps: float):
        self.bar, self.priority, self.fps = bar, priority, fps
        self.status: updates.Status | None = None
        self.turn = TurnTaker(APP, bar)
        self.pop_until = 0.0
        self.howl_until = 0.0
        self.hidden_key = None
        self.online = False
        self.on_bar = False
        self.line = Scroller(bar, "line", art.AREA_X, art.TEXT_Y, art.AREA_W)
        self.line_key = None
        self.loop = self.offset = 0
        self.page = 0
        self.flipped_at = time.monotonic()
        self.back_key = None
        self.back_slot = 0
        self.frame = 0
        self.led: str | None = None
        self.changed = asyncio.Event()

    # -- what there is to say -----------------------------------------------------
    def key(self):
        s = self.status
        return None if s is None else (tuple((u.name, u.new) for u in s.updates), s.reboot)

    def mood(self) -> str:
        s = self.status
        return "reboot" if s.reboot else "updates" if s.updates else "fresh"

    def pages(self) -> list[tuple[str, tuple, str]]:
        """(text, color, pose) for each page."""
        s = self.status
        howling = time.monotonic() < self.howl_until
        pose = "hardhat" if s.reboot else "howl" if howling else "calm" if s.updates else "happy"
        out = []
        if s.reboot:
            out.append(("REBOOT", art.WHITE, "hardhat"))
        out.append((art.count_text(len(s.updates)), art.WHITE, pose))
        if s.aur:
            out.append((f"AUR {len(s.aur)}", art.SOFT, pose))
        names = [u.name for u in (s.big or s.updates)][:5]
        if names:
            out.append(("  ".join(names), art.SOFT, pose))
        if s.error and not s.updates:
            out.append(("CHECK FAILED", art.SOFT, "calm"))
        return out

    @property
    def popping(self) -> bool:
        return time.monotonic() < self.pop_until

    def has_news_to_share(self) -> bool:
        s = self.status
        return s is not None and bool(s.updates or s.reboot) and self.key() != self.hidden_key

    def wanted(self) -> tuple[bool, int]:
        """(show now?, at what priority). Called off the event loop: it may
        clear the screen when it isn't our turn."""
        if self.status is None or self.key() == self.hidden_key:
            return False, self.priority
        if self.popping:
            return True, self.priority + POP_PRIORITY_BONUS
        if self.has_news_to_share() and read_turn() is not None:  # Luca's Den is running
            return self.turn.check(), self.priority
        return False, self.priority

    # -- pictures ----------------------------------------------------------------
    def upload_static(self) -> None:
        for mood in art.MOODS:
            for i in range(art.SIGN_FRAMES):
                self.bar.upload_image(f"sign_{mood}_{i}.png", art.sign(mood, i))
        for pose, n in art.POSES.items():
            for i in range(n):
                self.bar.upload_image(f"tile_{pose}_{i}.png", art.tile(pose, i))
        self.line_key = self.back_key = None

    def upload_back(self) -> None:
        key = (self.key(), self.status.checked, bool(self.status.error))
        if key != self.back_key:
            slot = 1 - self.back_slot
            self.bar.upload_image(f"back_{slot}.png", art.back_screen(self.status, time.time()))
            self.back_slot, self.back_key = slot, key

    def flip(self, step: int = 1) -> None:
        self.page, self.flipped_at, self.offset = self.page + step, time.monotonic(), 0

    def elements(self) -> list[dict]:
        pages = self.pages()
        if time.monotonic() - self.flipped_at >= PAGE_SECONDS and not (self.loop and self.offset):
            self.flip()
        text, color, pose = pages[self.page % len(pages)]
        if (text, color) != self.line_key:
            strip, self.loop = art.text_strip(text, color)
            self.line.set(strip)
            self.line_key, self.offset = (text, color), 0
        elif self.loop:
            self.offset = (self.offset + 2) % self.loop
        self.upload_back()
        mood = self.mood()
        return [image("sign", f"sign_{mood}_{self.frame % art.SIGN_FRAMES}.png", 0, 0),
                self.line.element(art.AREA_X - self.offset),
                image("luca", f"tile_{pose}_{(self.frame // 3) % art.POSES[pose]}.png", 0, 0),
                image("window", f"back_{self.back_slot}.png", 0, 0, display="back")]

    # -- news ----------------------------------------------------------------------
    def take(self, new: updates.Status) -> None:
        old, self.status = self.status, new
        old_names = {(u.name, u.new) for u in old.updates} if old else set()
        fresh = [u for u in new.updates if (u.name, u.new) not in old_names]
        kernel = any(u.kernel for u in fresh)
        reboot_now = new.reboot and not (old and old.reboot)
        if fresh or reboot_now:
            self.pop_until = time.monotonic() + POP_SECONDS
            self.howl_until = self.pop_until if kernel else 0.0
            self.led = art.LED["reboot"] if reboot_now else art.LED["updates"]
            self.page, self.flipped_at = 0, time.monotonic()
        n = len(new.updates)
        if fresh:
            print(f"  📦 {n} update{'s' if n != 1 else ''} waiting ({len(new.repo)} repo, {len(new.aur)} AUR)"
                  + (": 🐺 a new kernel! Awoo" if kernel else ""))
        elif old and n < len(old.updates):
            print("  ✨ All updated!" if n == 0 else f"  📦 {n} left to update")
        if reboot_now:
            print(f"  ⛑️  Reboot to finish the kernel update (running {new.running_kernel})")
        if new.error:
            print(f"  ⚠️  Couldn't check everything: {new.error}")
        self.changed.set()


async def watch(howl: Howl, every: float, aur: bool) -> None:
    last_check = 0.0
    touched_at = None
    while True:
        now = time.time()
        if updates.packages_changed_since(last_check) and last_check:
            touched_at = touched_at or now  # paru is (probably) running: let it finish
        due = now - last_check >= every
        settled = touched_at and now - touched_at >= SETTLE_SECONDS \
            and not updates.packages_changed_since(now - SETTLE_SECONDS)
        if due or settled:
            touched_at = None
            last_check = time.time()
            howl.take(await asyncio.to_thread(updates.check, aur))
        await asyncio.sleep(5)


async def demo(howl: Howl) -> None:
    status = art.demo_status()
    howl.take(status)
    await asyncio.sleep(POP_SECONDS + 4)
    howl.take(updates.Status(reboot=True, running_kernel="6.12.1-arch1-1", checked=time.time()))
    await asyncio.sleep(POP_SECONDS + 4)
    howl.take(updates.Status(checked=time.time()))
    howl.pop_until = time.monotonic() + 8  # show "all fresh" once
    while True:
        await asyncio.sleep(3600)


async def animate(howl: Howl) -> None:
    retry = 2
    while True:
        try:
            show, priority = await asyncio.to_thread(howl.wanted)
            if show:
                if not howl.online:
                    await asyncio.to_thread(howl.upload_static)
                    howl.online, retry = True, 2
                led, howl.led = howl.led, None
                await asyncio.to_thread(lambda: howl.bar.draw(howl.elements(), priority, led))
                howl.on_bar = True
                howl.frame += 1
                await asyncio.sleep(1 / howl.fps)
            else:
                if howl.on_bar and not howl.turn.away:
                    await asyncio.to_thread(howl.bar.clear)
                howl.on_bar = False
                howl.changed.clear()
                try:
                    await asyncio.wait_for(howl.changed.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
        except BarOffline as err:
            if howl.online or retry == 2:
                print(f"🔌 BUSY Bar trouble: {err}; I'll keep trying quietly")
            howl.online = howl.on_bar = False
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def listen(howl: Howl) -> None:
    async for event in input_events(howl.bar):
        if not howl.on_bar:
            continue
        if is_wheel(event):
            howl.flip(1 if event.delta > 0 else -1)
        elif is_press(event):
            if event.button == "start":
                howl.flip(1)
            elif event.button == "back":
                howl.flip(-1)
            elif event.button == "ok":
                howl.hidden_key, howl.pop_until = howl.key(), 0.0
                print("  🙈 Hidden until something changes")
                howl.changed.set()


async def run(howl: Howl, args) -> None:
    source = demo(howl) if args.demo else watch(howl, args.every, not args.no_aur)
    await asyncio.gather(animate(howl), listen(howl), source)


def install(args) -> None:
    if args.demo:
        raise SystemExit("--install starts the real thing; leave out --demo.")
    service.check([
        ("Pillow (pip install pillow)", service.importable("PIL")),
        ("busylib (pip install busylib)", service.importable("busylib")),
        ("checkupdates (sudo pacman -S pacman-contrib)", bool(shutil.which("checkupdates"))),
        ("paru, for AUR updates", bool(shutil.which("paru")) or args.no_aur),
    ], required={"Pillow (pip install pillow)"})
    command = [sys.executable, str(Path(__file__).resolve()), "--every", args.every_text,
               "--host", args.host, "--priority", str(args.priority), "--fps", str(args.fps)]
    if args.no_aur:
        command.append("--no-aur")
    service.install(SERVICE, "Luca Update Howl for the BUSY Bar", command, args.token,
                    "Luca now keeps an eye on your Arch updates from login.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--every", default="30m", metavar="TIME",
                    help="how often to check, e.g. 30m, 2h (default 30m)")
    ap.add_argument("--no-aur", action="store_true", help="only the official repos (skip paru -Qua)")
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"),
                    help="API key, if HTTP access is set to 'key' mode (or set BUSYBAR_TOKEN)")
    ap.add_argument("--priority", type=int, default=18,
                    help="draw priority on his Den turns (default 18; pop-ups go 12 higher)")
    ap.add_argument("--fps", type=float, default=6, help="animation speed (default 6)")
    ap.add_argument("--demo", action="store_true", help="pretend: updates, a reboot, then all fresh")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true",
                       help="Linux: start automatically at login (systemd user service)")
    group.add_argument("--uninstall", action="store_true", help="Linux: stop starting at login")
    args = ap.parse_args()
    if not 1 <= args.priority <= 100 - POP_PRIORITY_BONUS:
        ap.error(f"--priority must be between 1 and {100 - POP_PRIORITY_BONUS}")
    args.every_text = args.every
    try:
        args.every = parse_time(args.every)
    except ValueError:
        ap.error("--every takes a time like 30m or 2h")
    if args.every < 300:
        ap.error("--every must be at least 5m (it goes online each time)")
    if args.install:
        return install(args)
    if args.uninstall:
        return service.uninstall(SERVICE)

    bar = BusyBar(args.host, APP, args.token)
    howl = Howl(bar, args.priority, args.fps)
    if not args.demo:
        if not shutil.which("checkupdates"):
            print("💡 Install pacman-contrib for checkupdates: sudo pacman -S pacman-contrib")
        if not shutil.which("paru") and not args.no_aur:
            print("💡 paru isn't installed, so AUR updates are skipped.")
    print(f"📦 Luca Update Howl: {'demo' if args.demo else 'checking every ' + args.every_text}")
    print(f"🐺 He pops up on the BUSY Bar at {args.host} when there are new updates.")
    print("   Start/Back = page, OK = hide until something changes. Ctrl+C to stop.")

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(run(howl, args))
    except KeyboardInterrupt:
        pass
    finally:
        if howl.on_bar:
            try:
                bar.clear()
            except BarOffline:
                pass
        print("\n🌙 Luca stops watching the mirrors.")


if __name__ == "__main__":
    main()
