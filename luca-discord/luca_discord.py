"""
Luca Discord 💬🐺, your Discord on the BUSY Bar in glossy blurple Aero.

  Voice    while you're in a call: the channel and server, how long you've
           been in, and who's talking right now (green sound waves by their
           name). Luca wears a headset and his mouth moves when YOU talk. If
           you're muted or deafened, a red crossed-out mic or headset says so
  Messages DMs, mentions and server messages pop up and scroll by; Luca's
           ears perk up and the bar's light glows blurple
  Back     "Luca Discord", a Windows 7-style window: who's in the call (and
           who's talking), or your latest messages

Rich mode (recommended) uses Discord's own local RPC with a free Discord
application you make once; basic mode needs nothing and still shows calls
(while Discord uses your mic) and messages (from desktop notifications).

    OK      in a call: mute / unmute yourself (rich mode)   with a message: dismiss
    Start   next page / next message
    Back    previous page

    python luca_discord.py --client-id ID --client-secret SECRET   # rich mode
    python luca_discord.py --basic                                  # no setup
    python luca_discord.py --private      # never show what messages say
    python luca_discord.py --demo         # a pretend call and some messages
    python luca_discord.py --install / --uninstall                  # start at login

While it runs, Luca Notify Den and Luca On Air leave Discord to it. Messages
wait while you focus (Pack Focus), are live (On Air), or the selector is on
OFF. Needs Pillow and dbus-fast; buttons need busylib
(pip install pillow dbus-fast busylib).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import signal
import sys
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import art  # noqa: E402
import discord_rpc  # noqa: E402
import discord_state as ds  # noqa: E402
import service  # noqa: E402
from busybar import (BarOffline, BusyBar, Scroller, image, input_events, is_press, is_selector,  # noqa: E402
                     is_wheel, mark_running, stop_running)
from quiet import quiet_reason  # noqa: E402

APP = "luca_discord"
SERVICE = "luca-discord"
PAGE_SECONDS = 4
ALERT_SECONDS = 1.5
MAX_SECONDS = 15        # a message never hides your call for longer than this
SCROLL_STEP = 2         # pixels a frame: messages scroll briskly
HOLD_FRAMES = 12


class Bar:
    def __init__(self, bar: BusyBar, voice: ds.Voice, show: float, private: bool,
                 prio_voice: int, prio_message: int, fps: float):
        self.bar, self.voice, self.show, self.private = bar, voice, show, private
        self.line = Scroller(bar, "msg", art.AREA_X, art.TEXT_Y, art.AREA_W)
        self.prio_voice, self.prio_message, self.fps = prio_voice, prio_message, fps
        self.messages: asyncio.Queue = asyncio.Queue()
        self.waiting: deque = deque(maxlen=5)
        self.history: deque = deque(maxlen=20)
        self.current: ds.Message | None = None
        self.shown_at = 0.0
        self.strip_slot = 0
        self.loop = self.offset = self.hold = 0
        self.texts: dict[str, str] = {}       # text → uploaded file name
        self.online = False
        self.on_bar = False
        self.page = 0
        self.flipped_at = time.monotonic()
        self.back_slot = 0
        self.back_due = 0.0
        self.dnd = False
        self.quiet: str | None = None
        self.frame = 0
        self.led: str | None = None
        self.was_active = False
        self.rich: ds.Rich | None = None
        self.wake = asyncio.Event()

    # -- uploads -------------------------------------------------------------
    def upload_static(self) -> None:
        for kind in ("voice", "message"):
            for i in range(art.SIGN_FRAMES):
                self.bar.upload_image(f"sign_{kind}_{i}.png", art.sign(kind, i))
        for pose, n in art.POSES.items():
            for i in range(n):
                self.bar.upload_image(f"tile_{pose}_{i}.png", art.tile(pose, i))
        self.bar.upload_image("icon_muted.png", art.crossed(art.MIC))
        self.bar.upload_image("icon_deaf.png", art.crossed(art.HEADSET))
        for i in range(2):
            self.bar.upload_image(f"icon_waves_{i}.png", art.waves(i))
        for name in art.WORDS:
            self.bar.upload_image(f"word_{name}.png", art.word(name))
        for ch in art.CLOCK_CHARS:
            self.bar.upload_image(f"char_{art.char_name(ch)}.png", art.char(ch))
        self.texts.clear()

    def text_file(self, text: str, soft: bool = False, width: int = art.AREA_W - 2) -> tuple[str, int]:
        """Upload a name or label once; returns (file, width)."""
        key = f"{text}|{soft}|{width}"
        if key not in self.texts:
            name = "txt_" + hashlib.md5(key.encode()).hexdigest()[:10] + ".png"
            self.bar.upload_image(name, art.text_image(text, art.SOFT if soft else art.WHITE, width))
            self.texts[key] = name
        shown = art.to_font_text(text)
        while shown and art.text_width(shown) > width:
            shown = shown[:-1]
        return self.texts[key], art.text_width(shown)

    def present(self, msg: ds.Message) -> None:
        slot = 1 - self.strip_slot
        strip, loop = art.message_strip(msg, self.private)
        self.line.set(strip)
        self.strip_slot, self.loop, self.offset, self.hold = slot, loop, 0, HOLD_FRAMES
        self.current, self.shown_at, self.led = msg, time.monotonic(), art.LED_MESSAGE
        self.back_due = 0.0

    def upload_back(self) -> None:
        if time.monotonic() < self.back_due:
            return
        slot = 1 - self.back_slot
        self.bar.upload_image(f"back_{slot}.png", art.back_screen(self.voice, list(self.history), self.private))
        self.back_slot, self.back_due = slot, time.monotonic() + 1

    # -- what to show ---------------------------------------------------------
    def duration(self) -> float:
        scroll = (HOLD_FRAMES + self.loop / SCROLL_STEP) / self.fps + 1 if self.loop else 0
        return max(self.show, min(scroll, MAX_SECONDS))

    def message_elements(self) -> list[dict]:
        if self.loop:
            if self.hold:
                self.hold -= 1
            else:
                self.offset = (self.offset + SCROLL_STEP) % self.loop
        alert = time.monotonic() - self.shown_at < ALERT_SECONDS
        pose = "alert" if alert else "listen"
        return [image("sign", f"sign_message_{self.frame % art.SIGN_FRAMES}.png", 0, 0),
                self.line.element(art.AREA_X - self.offset),
                image("luca", f"tile_{pose}_{(self.frame // 3) % 2 if alert else 0}.png", 0, 0)]

    def voice_pages(self) -> list[list[tuple]]:
        v = self.voice
        timer = [("clock", art.clock(time.time() - (v.since or time.time())))]
        if not v.rich:
            return [[("word", "voice")], timer]
        pages = [[("text", f"#{v.channel}", True)]]
        if v.guild:
            pages.append([("text", v.guild, False)])
        pages.append(timer)
        if len(v.members) > 1:
            pages.append([("text", f"{len(v.members)} HERE", True)])
        return pages

    def voice_elements(self) -> list[dict]:
        v = self.voice
        icon = "deaf" if v.self_deaf else "muted" if v.self_mute else None
        right = (art.ICON_X - 2) if icon else art.FRONT_W
        talker = v.talker if v.rich else None
        if talker:
            pieces = [("text", talker.name, False), ("waves",)]
        else:
            pages = self.voice_pages()
            if time.monotonic() - self.flipped_at >= PAGE_SECONDS:
                self.page, self.flipped_at = self.page + 1, time.monotonic()
            pieces = pages[self.page % len(pages)]

        placed = []  # (file, width) for each piece
        for p in pieces:
            if p[0] == "word":
                placed.append([(f"word_{p[1]}.png", art.text_width(art.to_font_text(art.WORDS[p[1]])))])
            elif p[0] == "text":
                placed.append([self.text_file(p[1], p[2], right - art.AREA_X - (10 if talker else 2))])
            elif p[0] == "waves":
                placed.append([(f"icon_waves_{(self.frame // 2) % 2}.png", 6)])
            else:  # the call timer, digit by digit
                placed.append([(f"char_{art.char_name(c)}.png", art.char_width(c) - (1 if i == len(p[1]) - 1 else 0))
                               for i, c in enumerate(p[1])])
        total = sum(w for group in placed for _, w in group) + 3 * (len(placed) - 1)
        x = art.AREA_X + (right - art.AREA_X - total) // 2
        els = [image("sign", f"sign_voice_{self.frame % art.SIGN_FRAMES}.png", 0, 0)]
        n = 0
        for group in placed:
            for file, w in group:
                els.append(image(f"p{n}", file, x, art.TEXT_Y))
                x += w
                n += 1
            x += 3
        if icon:
            els.append(image("icon", f"icon_{icon}.png", art.ICON_X, art.TEXT_Y))
        if v.self_deaf:
            pose = "deaf"
        elif v.self_mute:
            pose = "muted"
        elif v.rich and v.i_am_talking:
            pose = "talk"
        else:
            pose = "listen"
        frame = (self.frame // 2) % art.POSES[pose]
        els.append(image("luca", f"tile_{pose}_{frame}.png", 0, 0))
        return els

    def hushed(self) -> bool:
        return self.dnd or bool(self.quiet)


async def collect(app: Bar) -> None:
    while True:
        msg = await app.messages.get()
        app.history.appendleft(msg)
        app.back_due = 0.0
        held = " (held)" if app.hushed() else ""
        print(f"  💬 {msg.author}{f' in {msg.where}' if msg.where else ''}{held}")
        app.waiting.append(msg)
        app.wake.set()


async def animate(app: Bar) -> None:
    retry, last_beat = 2, 0.0
    while True:
        now = time.monotonic()
        if now - last_beat > 3:
            await asyncio.to_thread(mark_running, APP)
            app.quiet = await asyncio.to_thread(quiet_reason)
            last_beat = now
        v = app.voice
        if v.active and not app.was_active:
            app.led, app.page, app.flipped_at = art.LED_VOICE, 0, now
        app.was_active = v.active
        try:
            if app.current and now - app.shown_at >= app.duration():
                app.current = None
            if app.current is None and app.waiting and not app.hushed():
                if not app.online:
                    await asyncio.to_thread(app.upload_static)
                    app.online, retry = True, 2
                await asyncio.to_thread(app.present, app.waiting.popleft())
            if app.current or v.active:
                if not app.online:
                    await asyncio.to_thread(app.upload_static)
                    app.online, retry = True, 2
                if app.current:
                    els, prio = await asyncio.to_thread(app.message_elements), app.prio_message
                else:
                    els, prio = await asyncio.to_thread(app.voice_elements), app.prio_voice
                await asyncio.to_thread(app.upload_back)
                els.append(image("window", f"back_{app.back_slot}.png", 0, 0, display="back"))
                await asyncio.to_thread(app.bar.draw, els, prio, app.led)
                app.led, app.on_bar = None, True
                app.frame += 1
                await asyncio.sleep(1 / app.fps)
            else:
                if app.on_bar:
                    await asyncio.to_thread(app.bar.clear)
                    app.on_bar = False
                app.wake.clear()
                try:
                    await asyncio.wait_for(app.wake.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
        except BarOffline as err:
            if app.online or retry == 2:
                print(f"🔌 Can't reach the BUSY Bar ({err}); I'll keep trying quietly")
            app.online = app.on_bar = False
            if app.current:
                app.waiting.appendleft(app.current)
                app.current = None
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def listen(app: Bar) -> None:
    async for event in input_events(app.bar):
        if is_selector(event):
            app.dnd = event.position == "off"
            if app.dnd and app.current:
                app.current = None
            app.wake.set()
            continue
        if app.current:  # a message is showing
            if is_press(event) and event.button == "ok":
                app.waiting.clear()
                app.current = None
            elif (is_press(event) and event.button == "start") or is_wheel(event):
                app.current = None
            app.wake.set()
        elif app.voice.active:
            if is_wheel(event):
                app.page += 1 if event.delta > 0 else -1
            elif is_press(event):
                if event.button == "ok":
                    if app.rich and app.rich.connected:
                        try:
                            was_muted = app.voice.self_mute
                            await app.rich.toggle_mute()
                            print(f"  🎙️  {'Unmuted' if was_muted else 'Muted'}")
                        except Exception as err:
                            print(f"⚠️  Couldn't change mute ({err})")
                elif event.button == "start":
                    app.page += 1
                elif event.button == "back":
                    app.page -= 1
            app.flipped_at = time.monotonic()


async def demo(app: Bar) -> None:
    v = app.voice
    await asyncio.sleep(1)
    app.messages.put_nowait(ds.Message("Kiro", "omg Luca looks so good on the bar!! hop in voice?", "#general · Pack Den"))
    await asyncio.sleep(9)
    v.active, v.rich, v.channel, v.guild, v.since, v.self_id = True, True, "hangout", "Pack Den", time.time(), "1"
    for uid, name in (("1", "Luca"), ("2", "Kiro"), ("3", "Aero Fox")):
        v.members[uid] = ds.Member(uid, name)
    app.wake.set()
    while True:
        for uid, secs in (("2", 3), ("1", 2), ("3", 2), (None, 4)):
            for m in v.members.values():
                m.speaking = m.id == uid
                if m.speaking:
                    m.spoke_at = time.monotonic()
            await asyncio.sleep(secs)
        v.self_mute = not v.self_mute
        if not v.self_mute:
            app.messages.put_nowait(ds.Message("Aero Fox", "brb grabbing snacks", "#hangout · Pack Den"))


async def run(app: Bar, args) -> None:
    on_change = app.wake.set
    tasks = [collect(app), animate(app), listen(app)]
    if args.demo:
        tasks.append(demo(app))
    else:
        if args.client_id and args.client_secret and not args.basic:
            def make_rpc(handler):
                return discord_rpc.DiscordRPC(args.client_id, args.client_secret, args.redirect_uri,
                                              handler, api=args.api)
            app.rich = ds.Rich(app.voice, app.messages, make_rpc, on_change)
            tasks.append(app.rich.run())
        tasks.append(ds.basic_voice(app.voice, app.rich, on_change))
        try:
            from notifications import watch
            tasks.append(ds.desktop_messages(app.messages, app.rich, watch()))
        except SystemExit as err:
            print(f"ℹ️  {err} (desktop notifications won't show)")
    await asyncio.gather(*tasks)


def install(args) -> None:
    if args.demo:
        raise SystemExit("--install starts the real thing; leave out --demo.")
    service.check([
        ("Pillow (pip install pillow)", service.importable("PIL")),
        ("dbus-fast (pip install dbus-fast)", service.importable("dbus_fast") or service.importable("dbus_next")),
        ("busylib (pip install busylib)", service.importable("busylib")),
    ], required={"Pillow (pip install pillow)"})
    if args.client_id and args.client_secret and not discord_rpc.TOKEN_FILE.exists():
        print("💡 Run it once by hand first (without --install), so you can click Authorize in Discord.")
    command = [sys.executable, str(Path(__file__).resolve()), "--host", args.host,
               "--show", str(args.show), "--fps", str(args.fps),
               "--priority-voice", str(args.priority_voice), "--priority-message", str(args.priority_message)]
    if args.private:
        command.append("--private")
    if args.basic:
        command.append("--basic")
    if args.redirect_uri != "http://localhost":
        command += ["--redirect-uri", args.redirect_uri]
    service.install(SERVICE, "Luca Discord for the BUSY Bar", command, args.token,
                    "Luca now shows your Discord from login.",
                    env={"DISCORD_CLIENT_ID": args.client_id or "",
                         "DISCORD_CLIENT_SECRET": args.client_secret or ""})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client-id", default=os.environ.get("DISCORD_CLIENT_ID"),
                    help="your Discord application's Client ID (rich mode; or set DISCORD_CLIENT_ID)")
    ap.add_argument("--client-secret", default=os.environ.get("DISCORD_CLIENT_SECRET"),
                    help="its Client Secret (or set DISCORD_CLIENT_SECRET)")
    ap.add_argument("--redirect-uri", default="http://localhost",
                    help="the OAuth2 redirect you added to the application (default http://localhost)")
    ap.add_argument("--basic", action="store_true", help="skip Discord RPC, even if set up")
    ap.add_argument("--private", action="store_true", help="never show what messages say")
    ap.add_argument("--show", type=float, default=7, metavar="SECONDS",
                    help="show each message at least this long (default 7)")
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"),
                    help="the BUSY Bar's API key, if HTTP access is set to 'key' mode (or set BUSYBAR_TOKEN)")
    ap.add_argument("--priority-voice", type=int, default=64, help="draw priority in a call (default 64)")
    ap.add_argument("--priority-message", type=int, default=70, help="draw priority for messages (default 70)")
    ap.add_argument("--fps", type=float, default=8, help="animation speed (default 8)")
    ap.add_argument("--api", default=discord_rpc.API, help=argparse.SUPPRESS)
    ap.add_argument("--demo", action="store_true", help="a pretend call and some messages")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true",
                       help="Linux: start automatically at login (systemd user service)")
    group.add_argument("--uninstall", action="store_true", help="Linux: stop starting at login")
    args = ap.parse_args()
    for p in (args.priority_voice, args.priority_message):
        if not 1 <= p <= 100:
            ap.error("priorities must be between 1 and 100")
    if bool(args.client_id) != bool(args.client_secret):
        ap.error("rich mode needs both --client-id and --client-secret")

    if args.install:
        return install(args)
    if args.uninstall:
        return service.uninstall(SERVICE)

    bar = BusyBar(args.host, APP, args.token)
    app = Bar(bar, ds.Voice(), args.show, args.private, args.priority_voice, args.priority_message, args.fps)
    if args.demo:
        mode = "demo"
    elif args.client_id and not args.basic:
        mode = "rich mode (Discord RPC), with basic mode as a backup"
    else:
        mode = "basic mode (mic + desktop notifications). Add --client-id/--client-secret for rich mode"
    print(f"💬 Luca Discord: {mode}")
    print(f"🐺 Showing on the BUSY Bar at {args.host} when you're in a call or get a message.")
    print("   In a call: OK = mute/unmute, Start/Back = page. Message: OK = dismiss, Start = next.")

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(run(app, args))
    except KeyboardInterrupt:
        pass
    finally:
        stop_running(APP)
        if app.on_bar:
            try:
                bar.clear()
            except BarOffline:
                pass
        print("\n🌙 Luca hangs up.")


if __name__ == "__main__":
    main()
