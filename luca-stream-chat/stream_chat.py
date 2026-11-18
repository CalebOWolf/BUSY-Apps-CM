"""
Luca Stream Chat 💜🐺, your Twitch or YouTube live chat on the BUSY Bar.

Chat messages scroll across a glossy Twitch-purple (or YouTube-red) panel,
each name in the chatter's own color, while streamer Luca reads along in his
headset. Subs, resubs, gift subs, raids, cheers, Super Chats, new members
and first-time chatters get a sparkling gold alert, a happy Luca hop and a
gold glow from the bar's light. The back screen becomes "Luca Chat", a
Windows 7-style chat log. When chat goes quiet, Luca steps aside (and your
ON AIR sign from Luca On Air comes back).

    OK      quiet: hide chat for 5 minutes (alerts still show)
    Start   skip to the next message

    python stream_chat.py --twitch yourchannel            # no login needed
    python stream_chat.py --youtube VIDEO_ID --youtube-key YOUR_API_KEY
    python stream_chat.py --twitch yourchannel --alerts-only
    python stream_chat.py --demo
    python stream_chat.py --twitch yourchannel --install  # Linux: start at login

Links in chat show as [link], and the usual bots (Nightbot, StreamElements…)
are skipped. Needs Pillow; buttons need busylib (pip install pillow busylib).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import art  # noqa: E402
import chat_sources as cs  # noqa: E402
import service  # noqa: E402
from busybar import (BarOffline, BusyBar, image, input_events, is_press, is_wheel,  # noqa: E402
                     mark_running, stop_running)
from quiet import QUIET_FILES  # noqa: E402

APP = "luca_stream_chat"
SERVICE = "luca-stream-chat"
CHAT_SECONDS = 4         # each chat message shows at least this long…
ALERT_SECONDS = 6        # …and each alert this long
MAX_CHAT = 8             # but never longer than this…
MAX_ALERT = 9
BUSY_CHAT = 2.5          # …and only this long when more is waiting
SCROLL_STEP = 3
HOLD_FRAMES = 8
MAX_WAITING_CHAT = 3     # in a busy chat, keep only the newest few
SNOOZE_SECONDS = 5 * 60


def live_now() -> bool:
    """Is Luca On Air saying you're live or recording?"""
    path, flag = QUIET_FILES["onair"]
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    return bool(data.get(flag)) and time.time() - data.get("updated", 0) < 5


class Chatbox:
    def __init__(self, bar: BusyBar, platforms: str, alerts_only: bool, only_live: bool,
                 prio_chat: int, prio_alert: int, fps: float):
        self.bar, self.platforms, self.alerts_only, self.only_live = bar, platforms, alerts_only, only_live
        self.prio_chat, self.prio_alert, self.fps = prio_chat, prio_alert, fps
        self.queue: asyncio.Queue = asyncio.Queue()
        self.chat: deque = deque(maxlen=MAX_WAITING_CHAT)
        self.alerts: deque = deque(maxlen=20)
        self.history: deque = deque(maxlen=20)
        self.current = None
        self.shown_at = 0.0
        self.slot = 0
        self.loop = self.offset = self.hold = 0
        self.online = False
        self.on_bar = False
        self.snooze_until = 0.0
        self.back_slot = 0
        self.back_dirty = True
        self.frame = 0
        self.led = None
        self.wake = asyncio.Event()

    def upload_static(self) -> None:
        for kind in art.PANELS:
            for i in range(art.PANEL_FRAMES):
                self.bar.upload_image(f"panel_{kind}_{i}.png", art.panel(kind, i))
        for pose, n in art.POSES.items():
            for i in range(n):
                self.bar.upload_image(f"tile_{pose}_{i}.png", art.tile(pose, i))
        self.back_dirty = True

    def next_item(self):
        if self.alerts:
            return self.alerts.popleft()
        if self.chat and time.monotonic() >= self.snooze_until and not self.alerts_only:
            return self.chat.popleft()
        return None

    def present(self, item) -> None:
        slot = 1 - self.slot
        strip, loop = art.strip(item)
        self.bar.upload_image(f"line_{slot}.png", strip)
        self.slot, self.loop, self.offset, self.hold = slot, loop, 0, HOLD_FRAMES
        self.current, self.shown_at = item, time.monotonic()
        if item.alert:
            self.led = art.LED_ALERT
        self.back_dirty = True

    def upload_back(self) -> None:
        if self.back_dirty:
            slot = 1 - self.back_slot
            self.bar.upload_image(f"back_{slot}.png", art.back_screen(list(self.history), self.platforms))
            self.back_slot, self.back_dirty = slot, False

    def duration(self) -> float:
        """Long enough to read, but chat moves along when more is waiting."""
        scroll = (HOLD_FRAMES + self.loop / SCROLL_STEP) / self.fps + 0.5 if self.loop else 0
        if self.current.alert:
            if self.alerts:  # more alerts lined up (a raid, a gift train…): keep them moving
                return max(3.5, min(scroll, 5))
            return max(ALERT_SECONDS, min(scroll, MAX_ALERT))
        if self.alerts or len(self.chat) >= 2:
            return BUSY_CHAT
        return max(CHAT_SECONDS, min(scroll, MAX_CHAT))

    def elements(self) -> list[dict]:
        item = self.current
        if self.loop:
            if self.hold:
                self.hold -= 1
            else:
                self.offset = (self.offset + SCROLL_STEP) % self.loop
        kind = "alert" if item.alert else item.platform
        pose = "hop" if item.alert else "read"
        return [image("panel", f"panel_{kind}_{self.frame % art.PANEL_FRAMES}.png", 0, 0),
                image("line", f"line_{self.slot}.png", art.AREA_X - self.offset, art.TEXT_Y),
                image("luca", f"tile_{pose}_{(self.frame // 3) % 2}.png", 0, 0),
                image("log", f"back_{self.back_slot}.png", 0, 0, display="back")]


async def collect(box: Chatbox) -> None:
    while True:
        item = await box.queue.get()
        box.history.appendleft(item)
        box.back_dirty = True
        if box.only_live and not await asyncio.to_thread(live_now):
            continue
        if item.alert:
            print(f"  ✨ {art.HEADLINES.get(item.alert, item.alert)} {item.name} {item.detail}".rstrip())
            box.alerts.append(item)
        else:
            box.chat.append(item)
        box.wake.set()


async def animate(box: Chatbox) -> None:
    retry, last_beat = 2, 0.0
    while True:
        if time.monotonic() - last_beat > 3:
            await asyncio.to_thread(mark_running, APP)
            last_beat = time.monotonic()
        try:
            if box.current and time.monotonic() - box.shown_at >= box.duration():
                box.current = None
            if box.current is None:
                item = box.next_item()
                if item:
                    if not box.online:
                        await asyncio.to_thread(box.upload_static)
                        box.online, retry = True, 2
                    await asyncio.to_thread(box.present, item)
            if box.current:
                await asyncio.to_thread(box.upload_back)
                prio = box.prio_alert if box.current.alert else box.prio_chat
                await asyncio.to_thread(box.bar.draw, box.elements(), prio, box.led)
                box.led, box.on_bar = None, True
                box.frame += 1
                await asyncio.sleep(1 / box.fps)
            else:
                if box.on_bar:  # chat went quiet: step aside
                    await asyncio.to_thread(box.bar.clear)
                    box.on_bar = False
                box.wake.clear()
                try:
                    await asyncio.wait_for(box.wake.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
        except BarOffline as err:
            if box.online or retry == 2:
                print(f"🔌 Can't reach the BUSY Bar ({err}); I'll keep trying quietly")
            box.online = box.on_bar = False
            box.current = None
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def listen(box: Chatbox) -> None:
    async for event in input_events(box.bar):
        if is_press(event) and event.button == "ok":
            box.snooze_until = time.monotonic() + SNOOZE_SECONDS
            box.chat.clear()
            if box.current and not box.current.alert:
                box.current = None
            print("  🤫 Chat hidden for 5 minutes (alerts still show)")
        elif (is_press(event) and event.button == "start") or is_wheel(event):
            box.current = None
        box.wake.set()


async def demo(queue: asyncio.Queue) -> None:
    script = [
        (1, cs.Chat("twitch", "Kiro", "LUCA LOOKS SO GOOD ON THE BAR", (255, 105, 180))),
        (4, cs.Chat("twitch", "AeroFox", "awoo!!", (30, 144, 255))),
        (3, cs.Chat("twitch", "NewPup", "hi! first time here", (0, 255, 127), "first")),
        (5, cs.Chat("twitch", "Bubbles", "7 months of howls!", (255, 215, 0), "resub", "7 months")),
        (7, cs.Chat("twitch", "AeroFox", "", (30, 144, 255), "bits", "500 bits")),
        (7, cs.Chat("twitch", "WolfPack", "", None, "raid", "42 viewers")),
        (7, cs.Chat("youtube", "Mod Max", "welcome raiders :)", role="mod")),
    ]
    while True:
        for delay, item in script:
            await asyncio.sleep(delay)
            item.at = time.time()
            queue.put_nowait(item)
        await asyncio.sleep(15)


async def run(box: Chatbox, args) -> None:
    tasks = [collect(box), animate(box), listen(box)]
    if args.demo:
        tasks.append(demo(box.queue))
    if args.twitch:
        tasks.append(cs.twitch(args.twitch, box.queue, not args.show_links))
    if args.youtube:
        tasks.append(cs.youtube(args.youtube, args.youtube_key, box.queue, not args.show_links, args.youtube_api))
    await asyncio.gather(*tasks)


def install(args) -> None:
    if args.demo:
        raise SystemExit("--install starts the real thing; leave out --demo.")
    service.check([("Pillow (pip install pillow)", service.importable("PIL")),
                   ("busylib (pip install busylib)", service.importable("busylib"))],
                  required={"Pillow (pip install pillow)"})
    command = [sys.executable, str(Path(__file__).resolve()), "--host", args.host,
               "--priority-chat", str(args.priority_chat), "--priority-alert", str(args.priority_alert),
               "--fps", str(args.fps)]
    if args.twitch:
        command += ["--twitch", args.twitch]
    if args.youtube:
        command += ["--youtube", args.youtube]
    for flag in ("alerts_only", "only_live", "show_links"):
        if getattr(args, flag):
            command.append("--" + flag.replace("_", "-"))
    service.install(SERVICE, "Luca Stream Chat for the BUSY Bar", command, args.token,
                    "Luca now shows your stream chat from login.",
                    env={"YOUTUBE_API_KEY": args.youtube_key or ""})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--twitch", metavar="CHANNEL", help="Twitch channel to read (no login needed)")
    ap.add_argument("--youtube", metavar="VIDEO_ID", help="the YouTube live stream's video ID")
    ap.add_argument("--youtube-key", default=os.environ.get("YOUTUBE_API_KEY"),
                    help="a YouTube Data API key (or set YOUTUBE_API_KEY)")
    ap.add_argument("--youtube-api", default=cs.YOUTUBE_API, help=argparse.SUPPRESS)
    ap.add_argument("--alerts-only", action="store_true", help="only subs, raids, cheers and so on")
    ap.add_argument("--only-live", action="store_true",
                    help="only show while Luca On Air says you're live or recording")
    ap.add_argument("--show-links", action="store_true", help="show links instead of [link]")
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"),
                    help="the BUSY Bar's API key, if HTTP access is set to 'key' mode (or set BUSYBAR_TOKEN)")
    ap.add_argument("--priority-chat", type=int, default=66, help="draw priority for chat (default 66)")
    ap.add_argument("--priority-alert", type=int, default=68, help="draw priority for alerts (default 68)")
    ap.add_argument("--fps", type=float, default=8, help="animation speed (default 8)")
    ap.add_argument("--demo", action="store_true", help="pretend chat, subs and a raid")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true",
                       help="Linux: start automatically at login (systemd user service)")
    group.add_argument("--uninstall", action="store_true", help="Linux: stop starting at login")
    args = ap.parse_args()
    if args.uninstall:
        return service.uninstall(SERVICE)
    if not (args.twitch or args.youtube or args.demo):
        ap.error("tell me whose chat to show: --twitch CHANNEL and/or --youtube VIDEO_ID (or try --demo)")
    if args.youtube and not args.youtube_key:
        ap.error("YouTube needs an API key: --youtube-key KEY (see the README for getting one)")
    for p in (args.priority_chat, args.priority_alert):
        if not 1 <= p <= 100:
            ap.error("priorities must be between 1 and 100")
    if args.install:
        return install(args)

    names = " + ".join(n for n, on in (("Twitch", args.twitch), ("YouTube", args.youtube),
                                        ("demo", args.demo)) if on)
    bar = BusyBar(args.host, APP, args.token)
    box = Chatbox(bar, names, args.alerts_only, args.only_live, args.priority_chat,
                  args.priority_alert, args.fps)
    print(f"💜 Luca Stream Chat: {names}" + (" (alerts only)" if args.alerts_only else ""))
    print(f"🐺 Chat pops up on the BUSY Bar at {args.host}. OK = hide chat 5 min, Start = skip.")

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(run(box, args))
    except KeyboardInterrupt:
        pass
    finally:
        stop_running(APP)
        if box.on_bar:
            try:
                bar.clear()
            except BarOffline:
                pass
        print("\n🌙 Luca signs off chat.")


if __name__ == "__main__":
    main()
