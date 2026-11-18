"""
Listens for desktop notifications on Linux.

Apps send notifications to your notification daemon (dunst, mako, KDE,
GNOME…) over D-Bus. This quietly *watches* those messages as a D-Bus monitor,
so your normal pop-ups keep working exactly as before. Nothing is replaced
or intercepted.

Needs the `dbus-fast` package (pip install dbus-fast). The older `dbus-next`
works too.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

RULE = "type='method_call',interface='org.freedesktop.Notifications',member='Notify'"


@dataclass
class Notification:
    app: str
    summary: str
    body: str = ""
    urgency: int = 1                 # 0 low, 1 normal, 2 critical
    at: float = field(default_factory=time.time)


def _clean(text: str) -> str:
    """Notification bodies may carry a little markup; keep plain text."""
    import html
    import re
    text = re.sub(r"<[^>]+>", "", text or "")
    return " ".join(html.unescape(text).split())


def _load_dbus():
    try:
        from dbus_fast import BusType, Message, MessageType
        from dbus_fast.aio import MessageBus
    except ImportError:
        try:
            from dbus_next import BusType, Message, MessageType
            from dbus_next.aio import MessageBus
        except ImportError:
            raise SystemExit("Luca Notify Den needs dbus-fast:  pip install dbus-fast")
    return BusType, Message, MessageType, MessageBus


async def watch() -> AsyncIterator[Notification]:
    """Yield every desktop notification sent on this session, forever."""
    BusType, Message, MessageType, MessageBus = _load_dbus()
    delay = 2
    while True:
        queue: asyncio.Queue = asyncio.Queue()
        try:
            bus = await MessageBus(bus_type=BusType.SESSION).connect()
            reply = await bus.call(Message(
                destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus.Monitoring", member="BecomeMonitor",
                signature="asu", body=[[RULE], 0]))
            if reply.message_type == MessageType.ERROR:
                raise RuntimeError(f"D-Bus said no: {reply.error_name} {reply.body}")

            def handler(msg):
                if (msg.message_type == MessageType.METHOD_CALL and msg.member == "Notify"
                        and len(msg.body) >= 8):
                    app, _replaces, _icon, summary, body, _actions, hints, _timeout = msg.body[:8]
                    urgency = hints.get("urgency")
                    urgency = int(urgency.value) if urgency is not None else 1
                    queue.put_nowait(Notification(_clean(app) or "App", _clean(summary),
                                                  _clean(body), urgency))
                return True  # a monitor must never answer anything

            bus.add_message_handler(handler)
            delay = 2
            waiter = asyncio.ensure_future(bus.wait_for_disconnect())
            try:
                while True:
                    getter = asyncio.ensure_future(queue.get())
                    done, _ = await asyncio.wait({getter, waiter},
                                                 return_when=asyncio.FIRST_COMPLETED)
                    if getter in done:
                        yield getter.result()
                    else:
                        getter.cancel()
                        break  # the bus went away
            finally:
                waiter.cancel()
                bus.disconnect()
        except asyncio.CancelledError:
            raise
        except SystemExit:
            raise
        except Exception as err:
            print(f"⚠️  Lost the notification feed ({err}); retrying in {delay}s")
        await asyncio.sleep(delay)
        delay = min(delay * 2, 60)


DEMO = [
    ("Discord", "Kiro", "omg Luca looks so good on the bar!! 🐺"),
    ("Thunderbird", "Your order has shipped", "Frutiger Dreams vinyl is on its way"),
    ("Steam", "Your friend is now playing", "Aero Racing Deluxe"),
    ("Telegram", "Pack chat", "Howl at the moon tonight? 🌕"),
    ("Firefox", "Download complete", "luca_wallpaper_4k.png"),
    ("notify-send", "Backup finished", "1,204 files saved to /mnt/den"),
]


async def demo(every: float = 9) -> AsyncIterator[Notification]:
    """Made-up notifications, now and then."""
    await asyncio.sleep(1)
    for i in range(10**9):
        app, summary, body = DEMO[i % len(DEMO)]
        yield Notification(app, summary, body, 2 if i % 5 == 4 else 1)
        await asyncio.sleep(every + random.uniform(-2, 2))
