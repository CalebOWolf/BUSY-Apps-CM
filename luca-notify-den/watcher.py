"""
Desktop notifications for Luca Notify Den: the real ones come from the shared
D-Bus watcher (../shared/notifications.py); demo() makes up a few.
"""

from __future__ import annotations

import asyncio
import random
import sys
from collections.abc import AsyncIterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from notifications import Notification, watch  # noqa: E402,F401

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
