"""
Talking to the BUSY Bar, shared by every app in this repo.

  BusyBar        upload images, draw elements, clear the screens (local HTTP API)
  BarOffline     raised when the bar doesn't answer, so apps can wait and retry
  image(), rect(), text()   build display elements
  input_events() follow the bar's buttons and wheel (needs busylib)

Each app puts this folder on its import path with:

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
"""

from __future__ import annotations

import asyncio
import io
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import AsyncIterator
from typing import Any

USB_HOST = "10.0.4.20"
FRONT_W, FRONT_H = 72, 16
BACK_W, BACK_H = 160, 80


class BarOffline(Exception):
    """The BUSY Bar didn't answer (unplugged, asleep, off Wi-Fi…) or said no."""


class BusyBar:
    def __init__(self, host: str, app: str, token: str | None = None):
        self.host = host
        self.app = app
        self.base = f"http://{host}/api"
        self.token = token

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
            raise BarOffline(f"it said {err.code} for {method} {path}: {detail}") from err
        except (urllib.error.URLError, OSError) as err:
            raise BarOffline(str(getattr(err, "reason", err))) from err
        return json.loads(raw) if raw else {}

    def upload(self, filename: str, data: bytes) -> None:
        self._call("POST", "/assets/upload",
                   params={"application_name": self.app, "file": filename},
                   body=data, content_type="application/octet-stream")

    def upload_image(self, filename: str, image) -> None:
        """Upload a Pillow image as PNG."""
        buf = io.BytesIO()
        image.save(buf, "PNG")
        self.upload(filename, buf.getvalue())

    def draw(self, elements: list[dict], priority: int = 50, led: str | None = None) -> None:
        """Show these elements. `led` ("#RRGGBBAA") also lights the bar's
        notification LED in that color."""
        payload = {"application_name": self.app, "priority": priority, "elements": elements}
        if led:
            payload["led_notification_color"] = led
        self._call("POST", "/display/draw", body=json.dumps(payload).encode(),
                   content_type="application/json")

    def clear(self) -> None:
        self._call("DELETE", "/display/draw", params={"application_name": self.app})


# --------------------------------------------------------------------------
# Display elements
# --------------------------------------------------------------------------
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
    "start"), `.action` and `.is_press`; a wheel event has `.delta`.
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
        yield await queue.get()


def is_press(event: Any) -> bool:
    return hasattr(event, "button") and getattr(event, "is_press", False)


def is_wheel(event: Any) -> bool:
    return hasattr(event, "delta") and bool(event.delta)


def is_selector(event: Any) -> bool:
    """The bar's selector moved; `.position` is "busy", "custom", "off"
    (do not disturb), "apps" or "settings"."""
    return hasattr(event, "position")
