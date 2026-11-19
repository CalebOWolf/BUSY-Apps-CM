"""
Talking to the BUSY Bar, shared by every app in this repo.

  BusyBar        upload images, draw elements, clear the screens (local HTTP API)
  BarOffline     raised when the bar doesn't answer, so apps can wait and retry
  Scroller       long text that scrolls, sent a screen-sized piece at a time
  image(), rect(), text()   build display elements
  input_events() follow the bar's buttons and wheel (needs busylib)
  Presence       which of our apps is on top, so only that one answers the buttons

Each app puts this folder on its import path with:

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

USB_HOST = "10.0.4.20"
FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80


class BarOffline(Exception):
    """Something went wrong talking to the BUSY Bar: apps wait, then upload
    their pictures again and retry."""


class BarRefused(BarOffline):
    """The bar answered, but said no to a request (and said why)."""


class NotOnTop(Exception):
    """The bar is showing something with a higher priority. Not an error."""


REFUSALS_BEFORE_RESET = 3   # refused drawings in a row before the app starts over
LOG_AGAIN_AFTER = 300       # seconds before the same complaint is printed again
BLANK = "blank.png"         # a transparent pixel, standing in for pieces that went away


def _reason(detail: str) -> str:
    """The bar's error message, on one line."""
    try:
        detail = json.loads(detail).get("error", detail)
    except (ValueError, AttributeError):
        pass
    return " ".join(str(detail).split()) or "no reason given"


class BusyBar:
    def __init__(self, host: str, app: str, token: str | None = None):
        self.host = host
        self.app = app
        self.base = f"http://{host}/api"
        self.token = token
        self.presence = Presence(app, 50)
        self._shown: dict[str, str] = {}   # element id -> display, from the last draw
        self._sent: dict[str, int] = {}    # file name -> hash of what we last uploaded
        self._refused = 0
        self._logged: dict[str, float] = {}
        self._blanks_ok = True

    # -- talking to the bar ----------------------------------------------------
    def _call(self, method: str, path: str, params: dict | None = None,
              body: bytes | None = None, content_type: str | None = None) -> dict:
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, data=body, method=method)
        if content_type:
            req.add_header("Content-Type", content_type)
        if self.token:
            req.add_header("X-API-Token", self.token)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as err:
            detail = err.read().decode(errors="replace")
            if err.code == 409 and "priority" in detail.lower():
                raise NotOnTop(detail) from err
            what = {"/display/draw": "a drawing", "/assets/upload": "a picture"}.get(path, path)
            raise BarRefused(f"it refused {what} ({err.code}: {_reason(detail)})") from err
        except (urllib.error.URLError, OSError) as err:
            self._sent.clear()  # it may have restarted: upload everything again
            raise BarOffline(f"can't reach it ({getattr(err, 'reason', err)})") from err
        return json.loads(raw) if raw else {}

    def _log_once(self, message: str) -> None:
        now = time.monotonic()
        if now - self._logged.get(message, -LOG_AGAIN_AFTER) >= LOG_AGAIN_AFTER:
            self._logged[message] = now
            print(f"⚠️  BUSY Bar: {message}", flush=True)

    # -- pictures --------------------------------------------------------------
    def upload(self, filename: str, data: bytes) -> None:
        """Upload a file, unless the bar already has exactly this under that name."""
        digest = hash(data)
        if self._sent.get(filename) == digest:
            return
        self._sent.pop(filename, None)
        self._call("POST", "/assets/upload",
                   params={"application_name": self.app, "file": filename},
                   body=data, content_type="application/octet-stream")
        self._sent[filename] = digest

    def upload_image(self, filename: str, image) -> None:
        """Upload a Pillow image as PNG."""
        buf = io.BytesIO()
        image.save(buf, "PNG")
        self.upload(filename, buf.getvalue())

    def forget_uploads(self) -> None:
        """Upload everything again next time (e.g. after the bar lost its files)."""
        self._sent.clear()

    # -- drawing ---------------------------------------------------------------
    def draw(self, elements: list[dict], priority: int = 50, led: str | None = None) -> bool:
        """Show these elements. `led` ("#RRGGBBAA") also lights the bar's
        notification LED in that color.

        Returns False (after a short pause, so we don't hammer the bar) when
        the bar is showing something more important, or turned this one
        drawing down. Both are fine: just carry on with the next frame. Only
        when it keeps refusing does this raise, so the app starts over."""
        payload = {"application_name": self.app, "priority": priority,
                   "elements": self._with_blanks(elements)}
        if led:
            payload["led_notification_color"] = led
        try:
            self._call("POST", "/display/draw", body=json.dumps(payload).encode(),
                       content_type="application/json")
        except NotOnTop:
            self.presence.leave()
            time.sleep(1)
            return False
        except BarRefused as err:
            if self._blanks_ok and len(payload["elements"]) > len(elements):
                self._blanks_ok = False  # this bar won't take our blanks: clear instead
                return self.draw(elements, priority, led)
            self._refused += 1
            self._log_once(str(err))
            self._sent.clear()  # maybe a picture went missing: send them again
            if self._refused >= REFUSALS_BEFORE_RESET:
                self._refused = 0
                raise
            time.sleep(0.5)
            return False
        self._refused = 0
        self._shown = {el["id"]: el.get("display", "front") for el in elements}
        self.presence.priority = priority
        self.presence.beat()
        return True

    def _with_blanks(self, elements: list[dict]) -> list[dict]:
        """The bar keeps pieces from earlier drawings (matched by id), so a page
        with fewer pieces would leave old ones showing underneath. Swap each
        piece that went away for a transparent pixel."""
        ids = {el["id"] for el in elements}
        gone = [(i, d) for i, d in self._shown.items() if i not in ids]
        if not gone:
            return elements
        if not self._blanks_ok:
            self._delete()  # start afresh instead (may blink for a moment)
            return elements
        from PIL import Image
        self.upload_image(BLANK, Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
        return [image(i, BLANK, 0, 0, display=d) for i, d in gone] + elements

    def clear(self) -> None:
        self.presence.leave()
        self._delete()

    def _delete(self) -> None:
        self._shown = {}
        try:
            self._call("DELETE", "/display/draw", params={"application_name": self.app})
        except BarRefused as err:
            if "not displaying anything" not in str(err):
                raise  # already off the bar (another app was on top) is fine

    def answers_buttons(self) -> bool:
        """True while this app is on the bar and no higher-priority app of ours is."""
        return self.presence.showing() and self.presence.on_top()


# --------------------------------------------------------------------------
# Display elements
# --------------------------------------------------------------------------
class Scroller:
    """
    A long line of text in a window on the front screen. The bar won't take a
    picture wider than its 72-pixel screen, so instead of sliding one long
    strip along, we show just the part you can see. Each position gets its
    own little file, so text that loops is only uploaded the first time round.

        line = Scroller(bar, "msg", x=20, y=4, width=52)
        line.set(strip_image)
        elements.append(line.element(20 - offset))  # strip's left edge on screen
    """

    def __init__(self, bar: "BusyBar", name: str, x: int, y: int, width: int):
        self.bar, self.name, self.x, self.y, self.width = bar, name, x, y, width
        self.strip = None

    def set(self, strip) -> None:
        self.strip = strip

    def element(self, x: int) -> dict:
        """Uploads this position if the bar doesn't have it yet (call this off
        the event loop)."""
        left = self.x - x
        file = f"{self.name}_{left + 1000}.png"
        self.bar.upload_image(file, self.strip.crop((left, 0, left + self.width, self.strip.height)))
        return image(self.name, file, self.x, self.y)


def image(id_: str, path: str, x: int, y: int, display: str = "front") -> dict:
    return {"id": id_, "type": "image", "path": path, "display": display, "x": x, "y": y}


def rect(id_: str, x: int, y: int, w: int, h: int, color: str | list[str],
         display: str = "front", gradient: str | None = None) -> dict:
    """A filled rectangle. `color` is "#RRGGBBAA"; pass two colors and
    gradient="h" or "v" for a gradient."""
    colors = color if isinstance(color, list) else [color]
    fill = f"gradient_{gradient}" if gradient else "solid"
    return {"id": id_, "type": "rectangle", "display": display, "x": x, "y": y,
            "width": w, "height": h, "fill": fill, "fill_colors": colors,
            "border_width": 0}


def text(id_: str, value: str, x: int, y: int, color: str = "#FFFFFFFF",
         font: str = "small", display: str = "front", align: str | None = None) -> dict:
    """Text in one of the bar's built-in fonts."""
    el = {"id": id_, "type": "text", "display": display, "font": font,
          "text": value, "color": color, "x": x, "y": y}
    if align:
        el["align"] = align
    return el


# --------------------------------------------------------------------------
# Buttons and wheel
# --------------------------------------------------------------------------
async def input_events(bar: BusyBar) -> AsyncIterator[Any]:
    """
    Yield button presses and wheel turns from the bar's live status stream,
    reconnecting quietly whenever the bar goes away.

    Events are busylib's: a button event has `.button` ("ok", "back",
    "start"), `.action` and `.is_press`; a wheel event has `.delta`; a
    selector event has `.position`.

    Buttons and wheel turns only come through while this app is on the bar
    and on top (see Presence), so two apps never both act on one press.
    Selector moves always come through.

    Without busylib installed this prints a hint and yields nothing.
    """
    try:
        from busylib import AsyncBusyBar
        from busylib.features import input_events as decode
    except ImportError:
        print("ℹ️  Install busylib (pip install busylib) to use the bar's buttons.")
        return

    # The stream runs on its own background thread. Closing a WebSocket
    # politely can take up to 10 seconds, and this way the app can still quit
    # (or systemd can restart it) instantly.
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def hand_over(event: Any) -> bool:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
            return True
        except RuntimeError:  # the app has finished
            return False

    async def pump() -> None:
        client = AsyncBusyBar(bar.host, token=bar.token)
        delay = 2
        while True:
            try:
                async for message in client.stream_status_ws():
                    delay = 2
                    if isinstance(message, dict):
                        for event in decode(message):
                            if not hand_over(event):
                                return
            except Exception:  # the bar went away; try again, gently
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    threading.Thread(target=lambda: asyncio.run(pump()), daemon=True,
                     name="busybar-input").start()
    while True:
        event = await queue.get()
        if is_selector(event) or bar.answers_buttons():
            yield event


def is_press(event: Any) -> bool:
    return hasattr(event, "button") and getattr(event, "is_press", False)


def is_wheel(event: Any) -> bool:
    return hasattr(event, "delta") and bool(event.delta)


def is_selector(event: Any) -> bool:
    """The bar's selector moved; `.position` is "busy", "custom", "off"
    (do not disturb), "apps" or "settings"."""
    return hasattr(event, "position")


# --------------------------------------------------------------------------
# Who's on top
# --------------------------------------------------------------------------
PRESENCE_DIR = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()) / "luca-bar"
FRESH = 2.5  # seconds: an app that hasn't drawn for this long is no longer on screen


class Presence:
    """
    Every app hears every button press, but only the one you can see should
    answer. While an app is on the bar it calls beat() after each draw; before
    acting on a press it asks on_top(), which is False while another of our
    apps with a higher priority is showing.
    """

    def __init__(self, app: str, priority: int):
        self.app, self.priority = app, priority
        self.path = PRESENCE_DIR / f"{app}.json"
        self._last = 0.0
        self._drawn = 0.0

    def beat(self) -> None:
        now = time.time()
        self._drawn = now
        if now - self._last < 0.5:
            return
        self._last = now
        try:
            PRESENCE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"priority": self.priority, "updated": now}))
            tmp.replace(self.path)
        except OSError:
            pass

    def showing(self) -> bool:
        """Has this app drawn on the bar in the last few seconds?"""
        return time.time() - self._drawn < FRESH

    def leave(self) -> None:
        self._last = self._drawn = 0.0
        try:
            self.path.unlink()
        except OSError:
            pass

    def on_top(self) -> bool:
        now = time.time()
        try:
            others = [p for p in PRESENCE_DIR.glob("*.json") if p != self.path]
        except OSError:
            return True
        for p in others:
            try:
                data = json.loads(p.read_text())
            except (OSError, ValueError):
                continue
            if now - data.get("updated", 0) < FRESH and data.get("priority", 0) > self.priority:
                return False
        return True


# --------------------------------------------------------------------------
# Which of our apps are running
# --------------------------------------------------------------------------
RUNNING_DIR = PRESENCE_DIR / "running"


def mark_running(app: str) -> None:
    """Say "I'm running" (call every few seconds), so other apps can hand
    things over: e.g. Notify Den leaves Discord to Luca Discord."""
    try:
        RUNNING_DIR.mkdir(parents=True, exist_ok=True)
        (RUNNING_DIR / f"{app}.json").write_text(json.dumps({"updated": time.time()}))
    except OSError:
        pass


def stop_running(app: str) -> None:
    try:
        (RUNNING_DIR / f"{app}.json").unlink()
    except OSError:
        pass


def is_running(app: str, fresh: float = 10) -> bool:
    try:
        data = json.loads((RUNNING_DIR / f"{app}.json").read_text())
    except (OSError, ValueError):
        return False
    return time.time() - data.get("updated", 0) < fresh
