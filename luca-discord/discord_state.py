"""
What's going on in Discord right now: your voice call and new messages.

  Rich mode   (Discord RPC, see discord_rpc.py) the channel and server, who's
              in it, who's talking, and whether you're muted or deafened;
              messages arrive straight from Discord
  Basic mode  (no setup) you're "in voice" while Discord uses your mic, and
              messages come from your desktop notifications
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from devices import mic_users  # noqa: E402
from notifications import Notification  # noqa: E402

DISCORD_APPS = {"discord", "vesktop", "webcord", "armcord", "legcord", "discord canary", "discord ptb"}
SPEAK_HOLD = 0.6   # keep showing someone as talking for a moment after they pause


@dataclass
class Member:
    id: str
    name: str
    speaking: bool = False
    muted: bool = False
    deafened: bool = False
    spoke_at: float = 0.0

    @property
    def talking(self) -> bool:
        return self.speaking or time.monotonic() - self.spoke_at < SPEAK_HOLD


@dataclass
class Voice:
    active: bool = False
    channel: str | None = None        # "general"
    guild: str | None = None          # "Pack Den" (None in a direct call)
    members: dict[str, Member] = field(default_factory=dict)
    since: float | None = None        # time.time() you joined
    self_id: str | None = None
    self_mute: bool = False
    self_deaf: bool = False
    rich: bool = False                # do we know the details?

    def leave(self) -> None:
        self.active, self.channel, self.guild, self.since = False, None, None, None
        self.members.clear()

    @property
    def me(self) -> Member | None:
        return self.members.get(self.self_id) if self.self_id else None

    @property
    def talker(self) -> Member | None:
        """Whoever else is talking (the most recent one)."""
        others = [m for m in self.members.values() if m.id != self.self_id and m.talking]
        return max(others, key=lambda m: m.spoke_at) if others else None

    @property
    def i_am_talking(self) -> bool:
        return bool(self.me and self.me.talking)


@dataclass
class Message:
    author: str
    text: str
    where: str = ""        # "#general · Pack Den", or "" for a DM
    at: float = field(default_factory=time.time)


SUMMARY = re.compile(r"^(?P<author>.*?) \((?P<channel>#[^,]+), (?P<guild>.+)\)$")


def message_from_desktop(note: Notification) -> Message:
    """Discord's desktop notifications look like "Kiro (#general, Pack Den)" / "hi!"."""
    m = SUMMARY.match(note.summary)
    if m:
        return Message(m["author"], note.body, f"{m['channel']} · {m['guild']}", note.at)
    return Message(note.summary or "Discord", note.body, "", note.at)


def name_of(entry: dict) -> str:
    user = entry.get("user") or {}
    return entry.get("nick") or user.get("global_name") or user.get("username") or "someone"


# --------------------------------------------------------------------------
# Rich mode: Discord RPC
# --------------------------------------------------------------------------
CHANNEL_EVENTS = ["VOICE_STATE_CREATE", "VOICE_STATE_UPDATE", "VOICE_STATE_DELETE",
                  "SPEAKING_START", "SPEAKING_STOP"]


class Rich:
    def __init__(self, voice: Voice, messages: asyncio.Queue, make_rpc, on_change):
        self.voice, self.messages, self.make_rpc = voice, messages, make_rpc
        self.on_change = on_change
        self.rpc = None
        self.channel_id: str | None = None
        self.connected = False
        self.warned = False
        self.may_ask = True  # pop up Discord's Authorize at most once per run

    def event(self, evt: str, data: dict) -> None:
        v = self.voice
        if evt == "VOICE_CHANNEL_SELECT":
            asyncio.get_running_loop().create_task(self.refresh_channel())
            return
        if evt in ("VOICE_STATE_CREATE", "VOICE_STATE_UPDATE"):
            self._upsert(data)
        elif evt == "VOICE_STATE_DELETE":
            v.members.pop((data.get("user") or {}).get("id", ""), None)
        elif evt in ("SPEAKING_START", "SPEAKING_STOP"):
            m = v.members.get(str(data.get("user_id")))
            if m:
                m.speaking = evt == "SPEAKING_START"
                m.spoke_at = time.monotonic()
        elif evt == "VOICE_SETTINGS_UPDATE":
            v.self_mute, v.self_deaf = bool(data.get("mute")), bool(data.get("deaf"))
        elif evt == "NOTIFICATION_CREATE":
            msg = data.get("message") or {}
            author = msg.get("author") or {}
            title = data.get("title") or author.get("global_name") or author.get("username") or "Discord"
            parsed = message_from_desktop(Notification("Discord", title, data.get("body") or msg.get("content", "")))
            self.messages.put_nowait(parsed)
        else:
            return
        self.on_change()

    def _upsert(self, entry: dict) -> None:
        user = entry.get("user") or {}
        uid = str(user.get("id", ""))
        if not uid:
            return
        vs = entry.get("voice_state") or {}
        m = self.voice.members.get(uid) or Member(uid, name_of(entry))
        m.name = name_of(entry)
        m.muted = bool(vs.get("self_mute") or vs.get("mute") or entry.get("mute"))
        m.deafened = bool(vs.get("self_deaf") or vs.get("deaf"))
        self.voice.members[uid] = m

    async def refresh_channel(self) -> None:
        v, rpc = self.voice, self.rpc
        if self.channel_id:
            for evt in CHANNEL_EVENTS:
                await rpc.unsubscribe(evt, {"channel_id": self.channel_id})
        data = await rpc.command("GET_SELECTED_VOICE_CHANNEL")
        if not data or not data.get("id"):
            if v.active:
                print("  📴 Left voice")
            v.leave()
            self.channel_id = None
            self.on_change()
            return
        new = data["id"] != self.channel_id
        self.channel_id = data["id"]
        v.active, v.rich = True, True
        v.channel = data.get("name") or "voice"
        v.guild = None
        if data.get("guild_id"):
            try:
                v.guild = (await rpc.command("GET_GUILD", {"guild_id": data["guild_id"]})).get("name")
            except Exception:
                pass
        if new or v.since is None:
            v.since = time.time()
        v.members.clear()
        for entry in data.get("voice_states") or []:
            self._upsert(entry)
        for evt in CHANNEL_EVENTS:
            await rpc.subscribe(evt, {"channel_id": self.channel_id})
        where = f"#{v.channel}" + (f" in {v.guild}" if v.guild else "")
        print(f"  🎧 In voice: {where} ({len(v.members)} here)")
        self.on_change()

    async def toggle_mute(self) -> None:
        if self.rpc and self.connected:
            await self.rpc.command("SET_VOICE_SETTINGS", {"mute": not self.voice.self_mute})

    async def run(self) -> None:
        delay = 5
        while True:
            self.rpc = self.make_rpc(self.event)
            try:
                user = await self.rpc.connect(ask=self.may_ask)
                self.voice.self_id = str(user.get("id"))
                for evt in ("VOICE_CHANNEL_SELECT", "VOICE_SETTINGS_UPDATE", "NOTIFICATION_CREATE"):
                    await self.rpc.subscribe(evt)
                settings = await self.rpc.command("GET_VOICE_SETTINGS")
                self.voice.self_mute, self.voice.self_deaf = bool(settings.get("mute")), bool(settings.get("deaf"))
                self.connected, self.warned, delay = True, False, 5
                name = user.get("global_name") or user.get("username") or "you"
                print(f"💬 Connected to Discord as {name} (rich mode)")
                await self.refresh_channel()
                await self.rpc.wait_closed()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                if getattr(self.rpc, "asked", False):
                    # we popped up Authorize and it didn't work out: don't keep asking
                    self.may_ask, self.warned = False, True
                    print(f"⚠️  Discord login didn't work: {err}")
                    print("   Using basic mode. I won't ask again until Luca restarts: fix it, then run "
                          "`systemctl --user restart luca-discord` (or run it by hand) to try once more.")
                elif not self.warned:
                    print(f"⚠️  Discord RPC: {err}. Using basic mode until it works.")
                    self.warned = True
            finally:
                self.rpc.close()
            if self.connected:
                print("💬 Lost Discord; using basic mode until it's back")
            self.connected = False
            self.voice.rich = False
            self.channel_id = None
            self.voice.leave()
            self.on_change()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


# --------------------------------------------------------------------------
# Basic mode: the mic and desktop notifications
# --------------------------------------------------------------------------
async def basic_voice(voice: Voice, rich: Rich | None, on_change, every: float = 2) -> None:
    """In voice while Discord is using your microphone (when RPC isn't connected)."""
    while True:
        if not (rich and rich.connected):
            using = any(app in DISCORD_APPS for app in await asyncio.to_thread(mic_users))
            if using and not voice.active:
                voice.active, voice.rich, voice.since = True, False, time.time()
                print("  🎧 In a Discord call")
                on_change()
            elif not using and voice.active and not voice.rich:
                voice.leave()
                print("  📴 Call ended")
                on_change()
        await asyncio.sleep(every)


async def desktop_messages(messages: asyncio.Queue, rich: Rich | None, source) -> None:
    """Discord's desktop notifications, while RPC isn't delivering them itself."""
    async for note in source:
        if note.app.strip().lower() in DISCORD_APPS and not (rich and rich.connected):
            messages.put_nowait(message_from_desktop(note))
