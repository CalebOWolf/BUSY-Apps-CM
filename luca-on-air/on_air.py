"""
Luca On Air 🔴🐺, an ON AIR sign for the BUSY Bar, so people around you know.

Lights up by itself when you're busy, and steps aside when you're not:

    LIVE      OBS is streaming       a glowing red ON AIR sign and the time live
    REC       OBS is recording       a blinking red dot and the time recording
    IN CALL   Discord, Zoom, Teams, a browser call… is using your mic
    CAM ON    an app has your webcam open

Luca wears a gaming headset (his mic light flickers when you're live). The
back screen becomes "Luca On Air", a Windows 7-style window showing what
OBS, your mic and your camera are up to. While you're live or recording,
Luca Notify Den holds notifications, in case the bar is on camera.

    Start / Back   next / previous page
    OK             hide the sign until something changes

    python on_air.py
    python on_air.py --obs-password YOUR_OBS_PASSWORD
    python on_air.py --no-mic --no-camera        # OBS only
    python on_air.py --demo                       # cycle through every sign
    python on_air.py --install / --uninstall      # Linux: start at login

Linux. Needs Pillow; OBS needs its WebSocket server on (Tools → WebSocket
Server Settings); buttons need busylib (pip install pillow busylib).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import art  # noqa: E402
import service  # noqa: E402
import sources  # noqa: E402
from busybar import BarOffline, BusyBar, image, input_events, is_press, is_running, is_wheel  # noqa: E402

APP = "luca_on_air"
SERVICE = "luca-on-air"
PAGE_SECONDS = 4
POLL_SECONDS = 2
DISCORD_APPS = {"discord", "vesktop", "webcord", "armcord", "legcord"}
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
# Luca Notify Den reads this to hold notifications while you're live or recording.
HUSH_FILE = Path(os.environ.get("XDG_RUNTIME_DIR") or CACHE_DIR) / "luca-onair.json"


class Sign:
    def __init__(self, bar: BusyBar, status: sources.Status, priority: int, fps: float):
        self.bar, self.status, self.priority, self.fps = bar, status, priority, fps
        self.online = False
        self.on_bar = False
        self.page = 0
        self.flipped_at = time.monotonic()
        self.hidden_for = None       # the state OK hid; shows again when it changes
        self.last_key = None
        self.app_slot = 0
        self.app_name = None
        self.back_due = 0.0
        self.back_slot = 0
        self.frame = 0
        self.light = False
        self.changed = asyncio.Event()

    def key(self):
        s = self.status
        return (s.mode, s.call_app, tuple(s.cam_apps), s.recording_paused)

    @property
    def wanted(self) -> bool:
        return self.status.mode is not None and self.key() != self.hidden_for

    def upload_static(self) -> None:
        for mode in art.MODES:
            for i in range(art.SIGN_FRAMES):
                self.bar.upload_image(f"sign_{mode}_{i}.png", art.sign(mode, i))
        for pose, n in art.POSES.items():
            for i in range(n):
                self.bar.upload_image(f"tile_{pose}_{i}.png", art.tile(pose, i))
        for name in art.WORDS:
            self.bar.upload_image(f"word_{name}.png", art.word(name))
        for ch in art.CLOCK_CHARS:
            self.bar.upload_image(f"char_{art.char_name(ch)}.png", art.char(ch))
        self.app_name = None

    def upload_dynamic(self) -> None:
        s = self.status
        app = s.call_app if s.mode == "call" else (s.cam_apps[0] if s.mode == "cam" and s.cam_apps else None)
        if app and app != self.app_name:
            slot = 1 - self.app_slot
            self.bar.upload_image(f"app_{slot}.png", art.text_image(art.display_name(app)))
            self.app_slot, self.app_name = slot, app
        if time.monotonic() >= self.back_due:
            slot = 1 - self.back_slot
            self.bar.upload_image(f"back_{slot}.png", art.back_screen(s, time.time()))
            self.back_slot, self.back_due = slot, time.monotonic() + 1

    def pages(self) -> list[list[tuple[str, str]]]:
        s, now = self.status, time.time()
        if s.mode == "live":
            return [[("word", "onair")], art.live_pieces(now - (s.stream_since or now))]
        if s.mode == "rec":
            if s.recording_paused:
                return [[("word", "paused")]]
            return [[("time", art.uptime(now - (s.record_since or now)))]]
        if s.mode == "call":
            return [[("word", "call")], [("app", "")]]
        return [[("word", "cam")], [("app", "")]] if s.cam_apps else [[("word", "cam")]]

    def elements(self) -> list[dict]:
        s = self.status
        pages = self.pages()
        if time.monotonic() - self.flipped_at >= PAGE_SECONDS:
            self.page, self.flipped_at = self.page + 1, time.monotonic()
        pieces = pages[self.page % len(pages)]

        widths = []
        for kind, val in pieces:
            if kind == "word":
                widths.append(art.word_width(val))
            elif kind == "app":
                widths.append(art.text_width(art.to_font_text(art.display_name(self.app_name or ""))))
            else:
                widths.append(sum(art.char_width(c) for c in val) - 1)
        gap = 4 if len(pieces) > 1 else 0
        x = art.AREA_X + (art.AREA_W - (sum(widths) + gap)) // 2 + (4 if s.mode == "rec" else 0)

        els = [image("sign", f"sign_{s.mode}_{self.frame % art.SIGN_FRAMES}.png", 0, 0)]
        for k, ((kind, val), w) in enumerate(zip(pieces, widths)):
            if kind == "word":
                els.append(image(f"p{k}", f"word_{val}.png", x, art.TEXT_Y))
            elif kind == "app":
                els.append(image(f"p{k}", f"app_{self.app_slot}.png", x, art.TEXT_Y))
            else:
                cx = x
                for i, ch in enumerate(val):
                    els.append(image(f"t{i}", f"char_{art.char_name(ch)}.png", cx, art.TEXT_Y))
                    cx += art.char_width(ch)
            x += w + gap + 1
        pose = {"live": "live", "call": "talk"}.get(s.mode, "smile")
        els.append(image("luca", f"tile_{pose}_{(self.frame // 3) % 2}.png", 0, 0))
        els.append(image("status", f"back_{self.back_slot}.png", 0, 0, display="back"))
        return els


def write_hush(on: bool) -> None:
    try:
        HUSH_FILE.parent.mkdir(parents=True, exist_ok=True)
        HUSH_FILE.write_text(json.dumps({"on_air": on, "updated": time.time()}))
    except OSError:
        pass


async def watch_devices(sign: Sign, mic: bool, camera: bool, extra_call_apps: set[str]) -> None:
    calls = sources.CALL_APPS | extra_call_apps
    while True:
        s = sign.status
        s.mic_apps = await asyncio.to_thread(sources.mic_users) if mic else []
        if is_running("luca_discord"):  # Luca Discord shows Discord calls, with more detail
            calls_now = calls - DISCORD_APPS
        else:
            calls_now = calls
        s.call_app = next((a for a in s.mic_apps if a in calls_now), None)
        s.cam_apps = await asyncio.to_thread(sources.camera_users) if camera else []
        sign.changed.set()
        await asyncio.sleep(POLL_SECONDS)


async def animate(sign: Sign) -> None:
    retry, last_hush = 2, 0.0
    while True:
        s = sign.status
        key = sign.key()
        if key != sign.last_key:
            if s.mode:
                label = {"live": "🔴 LIVE", "rec": "⏺️  Recording", "call": f"🎧 In a call ({s.call_app})",
                         "cam": f"📷 Camera on ({', '.join(s.cam_apps)})"}[s.mode]
                print(f"  {label}" + (" (paused)" if s.recording_paused else ""))
                sign.light, sign.page, sign.flipped_at = True, 0, time.monotonic()
            elif sign.last_key and sign.last_key[0]:
                print("  ⚪ Off air")
            sign.last_key = key
        if time.monotonic() - last_hush >= 1:
            await asyncio.to_thread(write_hush, s.mode in ("live", "rec"))
            last_hush = time.monotonic()
        try:
            if sign.wanted:
                if not sign.online:
                    await asyncio.to_thread(sign.upload_static)
                    sign.online, retry = True, 2
                await asyncio.to_thread(sign.upload_dynamic)
                led = art.LED.get(s.mode) if sign.light else None
                await asyncio.to_thread(sign.bar.draw, sign.elements(), sign.priority, led)
                sign.light, sign.on_bar = False, True
                sign.frame += 1
                await asyncio.sleep(1 / sign.fps)
            else:
                if sign.on_bar:
                    await asyncio.to_thread(sign.bar.clear)
                    sign.on_bar = False
                sign.changed.clear()
                try:
                    await asyncio.wait_for(sign.changed.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
        except BarOffline as err:
            if sign.online or retry == 2:
                print(f"🔌 Can't reach the BUSY Bar ({err}); I'll keep trying quietly")
            sign.online = sign.on_bar = False
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def listen(sign: Sign) -> None:
    async for event in input_events(sign.bar):
        if is_wheel(event):
            sign.page += 1 if event.delta > 0 else -1
            sign.flipped_at = time.monotonic()
        elif is_press(event):
            if event.button == "start":
                sign.page, sign.flipped_at = sign.page + 1, time.monotonic()
            elif event.button == "back":
                sign.page, sign.flipped_at = sign.page - 1, time.monotonic()
            elif event.button == "ok":
                sign.hidden_for = sign.key()
                print("  🙈 Hidden until something changes")


async def demo(sign: Sign) -> None:
    """Cycle through every kind of sign."""
    s = sign.status
    s.obs_connected = True
    steps = [dict(streaming=True, stream_since=time.time() - 754), dict(streaming=True, stream_since=time.time() - 3725),
             dict(recording=True, record_since=time.time() - 75), dict(recording=True, recording_paused=True,
                                                                     record_since=time.time() - 80),
             dict(mic_apps=["discord"], call_app="discord"), dict(cam_apps=["zoom"]), dict()]
    while True:
        for step in steps:
            for k in ("streaming", "recording", "recording_paused"):
                setattr(s, k, False)
            s.stream_since = s.record_since = s.call_app = None
            s.mic_apps, s.cam_apps = [], []
            for k, v in step.items():
                setattr(s, k, v)
            sign.changed.set()
            await asyncio.sleep(8)


async def run(sign: Sign, args) -> None:
    if args.demo:
        tasks = [demo(sign)]
    else:
        obs = sources.OBS(sign.status, args.obs_host, args.obs_password, sign.changed.set)
        extra = {a.strip().lower() for a in args.call_apps.split(",") if a.strip()}
        tasks = [watch_devices(sign, not args.no_mic, not args.no_camera, extra)]
        if not args.no_obs:
            tasks.append(obs.run())
    await asyncio.gather(animate(sign), listen(sign), *tasks)


def install(args) -> None:
    if args.demo:
        raise SystemExit("--install starts the real thing; leave out --demo.")
    service.check([
        ("Pillow (pip install pillow)", service.importable("PIL")),
        ("busylib (pip install busylib)", service.importable("busylib")),
        ("websockets (comes with busylib)", service.importable("websockets")),
    ], required={"Pillow (pip install pillow)"})
    command = [sys.executable, str(Path(__file__).resolve()), "--host", args.host,
               "--priority", str(args.priority), "--obs-host", args.obs_host]
    for flag in ("no_mic", "no_camera", "no_obs"):
        if getattr(args, flag):
            command.append("--" + flag.replace("_", "-"))
    if args.call_apps:
        command += ["--call-apps", args.call_apps]
    service.install(SERVICE, "Luca On Air for the BUSY Bar", command, args.token,
                    "Luca's ON AIR sign now lights up by itself from login.",
                    env={"OBS_PASSWORD": args.obs_password or ""})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--obs-host", default="localhost:4455", help="OBS WebSocket address")
    ap.add_argument("--obs-password", default=os.environ.get("OBS_PASSWORD"),
                    help="OBS WebSocket password (or set OBS_PASSWORD)")
    ap.add_argument("--no-obs", action="store_true", help="don't watch OBS")
    ap.add_argument("--no-mic", action="store_true", help="don't watch the microphone")
    ap.add_argument("--no-camera", action="store_true", help="don't watch the camera")
    ap.add_argument("--call-apps", default="", metavar="APPS",
                    help="more apps whose mic use means a call, e.g. jami,linphone")
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", default=os.environ.get("BUSYBAR_TOKEN"),
                    help="API key, if HTTP access is set to 'key' mode (or set BUSYBAR_TOKEN)")
    ap.add_argument("--priority", type=int, default=65,
                    help="draw priority 1-100 (default 65: over everything but notifications)")
    ap.add_argument("--fps", type=float, default=6, help="animation speed (default 6)")
    ap.add_argument("--demo", action="store_true", help="cycle through every sign")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true",
                       help="Linux: start automatically at login (systemd user service)")
    group.add_argument("--uninstall", action="store_true", help="Linux: stop starting at login")
    args = ap.parse_args()
    if not 1 <= args.priority <= 100:
        ap.error("--priority must be between 1 and 100")

    if args.install:
        return install(args)
    if args.uninstall:
        return service.uninstall(SERVICE)

    bar = BusyBar(args.host, APP, args.token)
    sign = Sign(bar, sources.Status(), args.priority, args.fps)
    watching = [] if args.demo else [w for w, off in (("OBS", args.no_obs), ("mic", args.no_mic),
                                                       ("camera", args.no_camera)) if not off]
    print("🔴 Luca On Air: " + ("demo, cycling through every sign" if args.demo
                                 else "watching " + ", ".join(watching)))
    print(f"🐺 The sign lights up on the BUSY Bar at {args.host} when you're on air.")
    print("   Start/Back = page, OK = hide until something changes. Ctrl+C to stop.")

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(run(sign, args))
    except KeyboardInterrupt:
        pass
    finally:
        try:
            HUSH_FILE.unlink()
        except OSError:
            pass
        if sign.on_bar:
            try:
                bar.clear()
            except BarOffline:
                pass
        print("\n🌙 Off air. Luca hangs up his headset.")


if __name__ == "__main__":
    main()
