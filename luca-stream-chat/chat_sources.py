"""
Live stream chat and alerts, read-only.

  Twitch   Twitch chat (IRC over TLS), joined anonymously: no login, no key.
           Chat messages, plus subs, resubs, gift subs, raids, cheers (bits)
           and first-time chatters
  YouTube  the YouTube Data API with your own (free) API key: chat messages,
           Super Chats, Super Stickers, new members and gifted memberships

Everything comes out as Chat items on one asyncio queue.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

TWITCH_HOST, TWITCH_PORT = "irc.chat.twitch.tv", 6697
YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
IGNORE_BOTS = {"nightbot", "streamelements", "streamlabs", "moobot", "fossabot", "wizebot",
               "soundalerts", "sery_bot", "kofistreambot"}
URL = re.compile(r"(https?://\S+|www\.\S+)", re.I)


@dataclass
class Chat:
    platform: str                 # "twitch" or "youtube"
    name: str
    text: str = ""
    color: tuple[int, int, int] | None = None
    alert: str | None = None      # "sub", "resub", "gift", "raid", "bits", "superchat", "member", "first"
    detail: str = ""              # "x3 months", "42 viewers", "500 bits", "$5.00"…
    role: str = ""                # "owner", "mod", "member", ""
    at: float = field(default_factory=time.time)


def clean(text: str, hide_links: bool = True) -> str:
    text = text.replace("\x01ACTION ", "").replace("\x01", "")
    if hide_links:
        text = URL.sub("[link]", text)
    return " ".join(text.split())


# --------------------------------------------------------------------------
# Twitch
# --------------------------------------------------------------------------
def _unescape(v: str) -> str:
    out, i = [], 0
    while i < len(v):
        if v[i] == "\\" and i + 1 < len(v):
            out.append({"s": " ", ":": ";", "\\": "\\", "r": "", "n": " "}.get(v[i + 1], v[i + 1]))
            i += 2
        else:
            out.append(v[i])
            i += 1
    return "".join(out)


def parse_irc(line: str) -> tuple[dict, str, str, list[str], str]:
    """'@tags :prefix COMMAND params :trailing' → (tags, prefix, command, params, trailing)."""
    tags, prefix = {}, ""
    if line.startswith("@"):
        raw, line = line[1:].split(" ", 1)
        for part in raw.split(";"):
            k, _, v = part.partition("=")
            tags[k] = _unescape(v)
    if line.startswith(":"):
        prefix, line = line[1:].split(" ", 1)
    trailing = ""
    if " :" in line:
        line, trailing = line.split(" :", 1)
    parts = line.split()
    return tags, prefix, (parts[0] if parts else ""), parts[1:], trailing


def _color(hex_: str) -> tuple[int, int, int] | None:
    try:
        return tuple(int(hex_[i:i + 2], 16) for i in (1, 3, 5)) if hex_.startswith("#") else None
    except ValueError:
        return None


def twitch_item(line: str, hide_links: bool = True) -> Chat | None:
    tags, prefix, cmd, _params, text = parse_irc(line)
    name = tags.get("display-name") or prefix.split("!")[0]
    color = _color(tags.get("color", ""))
    badges = tags.get("badges", "")
    role = "owner" if "broadcaster" in badges else "mod" if "moderator" in badges else \
        "member" if "subscriber" in badges else ""
    if cmd == "PRIVMSG":
        if name.lower() in IGNORE_BOTS:
            return None
        item = Chat("twitch", name, clean(text, hide_links), color, role=role)
        if tags.get("bits"):
            item.alert, item.detail = "bits", f"{tags['bits']} bits"
        elif tags.get("first-msg") == "1":
            item.alert = "first"
        return item
    if cmd == "USERNOTICE":
        kind = tags.get("msg-id", "")
        months = tags.get("msg-param-cumulative-months")
        if kind in ("sub", "resub"):
            return Chat("twitch", name, clean(text, hide_links), color, "resub" if kind == "resub" else "sub",
                        f"{months} months" if months and months != "1" else "", role)
        if kind in ("subgift", "submysterygift", "anonsubgift"):
            count = tags.get("msg-param-mass-gift-count") or "1"
            return Chat("twitch", name or "Someone", "", color, "gift", f"x{count}", role)
        if kind == "raid":
            raider = tags.get("msg-param-displayName") or name
            return Chat("twitch", raider, "", color, "raid", f"{tags.get('msg-param-viewerCount', '?')} viewers")
    return None


async def twitch(channel: str, queue: asyncio.Queue, hide_links: bool = True) -> None:
    channel = channel.lower().lstrip("#")
    delay = 2
    while True:
        try:
            reader, writer = await asyncio.open_connection(TWITCH_HOST, TWITCH_PORT, ssl=ssl.create_default_context())
            nick = f"justinfan{random.randint(10000, 99999)}"  # Twitch's anonymous, read-only login
            for msg in ("CAP REQ :twitch.tv/tags twitch.tv/commands", "PASS SCHMOOPIIE", f"NICK {nick}",
                        f"JOIN #{channel}"):
                writer.write((msg + "\r\n").encode())
            await writer.drain()
            joined = False
            while True:
                raw = await reader.readline()
                if not raw:
                    raise ConnectionError("Twitch closed the connection")
                line = raw.decode(errors="replace").rstrip("\r\n")
                if line.startswith("PING"):
                    writer.write(("PONG" + line[4:] + "\r\n").encode())
                    await writer.drain()
                    continue
                if not joined and f" JOIN #{channel}" in line:
                    joined, delay = True, 2
                    print(f"💜 Watching Twitch chat for #{channel}")
                item = twitch_item(line, hide_links)
                if item:
                    queue.put_nowait(item)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            print(f"⚠️  Twitch chat: {err}; reconnecting in {delay}s")
        await asyncio.sleep(delay)
        delay = min(delay * 2, 60)


# --------------------------------------------------------------------------
# YouTube
# --------------------------------------------------------------------------
def _yt(api: str, path: str, params: dict) -> dict:
    url = f"{api}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "luca-stream-chat/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        body = err.read().decode(errors="replace")
        try:
            reason = json.loads(body)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            reason = body[:200]
        raise PermissionError(f"YouTube said {err.code}: {reason}") from err


def youtube_item(entry: dict, hide_links: bool = True) -> Chat | None:
    sn, who = entry.get("snippet", {}), entry.get("authorDetails", {})
    name = who.get("displayName", "someone")
    role = "owner" if who.get("isChatOwner") else "mod" if who.get("isChatModerator") else \
        "member" if who.get("isChatSponsor") else ""
    kind = sn.get("type")
    text = clean(sn.get("displayMessage", ""), hide_links)
    if kind == "textMessageEvent":
        return Chat("youtube", name, text, role=role)
    if kind in ("superChatEvent", "superStickerEvent"):
        details = sn.get("superChatDetails") or sn.get("superStickerDetails") or {}
        return Chat("youtube", name, clean(details.get("userComment", ""), hide_links), alert="superchat",
                    detail=details.get("amountDisplayString", ""), role=role)
    if kind in ("newSponsorEvent", "memberMilestoneChatEvent"):
        months = (sn.get("memberMilestoneChatDetails") or {}).get("memberMonth")
        return Chat("youtube", name, text if kind == "memberMilestoneChatEvent" else "", alert="member",
                    detail=f"{months} months" if months else "", role=role)
    if kind == "membershipGiftingEvent":
        count = (sn.get("membershipGiftingDetails") or {}).get("giftMembershipsCount", 1)
        return Chat("youtube", name, "", alert="gift", detail=f"x{count}", role=role)
    return None


async def youtube(video_id: str, key: str, queue: asyncio.Queue, hide_links: bool = True,
                  api: str = YOUTUBE_API) -> None:
    delay = 10
    while True:
        try:
            info = await asyncio.to_thread(_yt, api, "videos", {"part": "liveStreamingDetails",
                                                               "id": video_id, "key": key})
            items = info.get("items") or []
            chat_id = (items[0].get("liveStreamingDetails") or {}).get("activeLiveChatId") if items else None
            if not chat_id:
                raise LookupError("that video has no live chat right now (is the stream live?)")
            print("❤️  Watching YouTube live chat")
            token, first, delay = None, True, 10
            while True:
                params = {"liveChatId": chat_id, "part": "snippet,authorDetails", "key": key}
                if token:
                    params["pageToken"] = token
                page = await asyncio.to_thread(_yt, api, "liveChat/messages", params)
                if not first:  # the first page is the backlog: start from "now"
                    for entry in page.get("items", []):
                        item = youtube_item(entry, hide_links)
                        if item and item.name.lower() not in IGNORE_BOTS:
                            queue.put_nowait(item)
                first, token = False, page.get("nextPageToken")
                await asyncio.sleep(max(2.0, page.get("pollingIntervalMillis", 5000) / 1000))
        except asyncio.CancelledError:
            raise
        except PermissionError as err:
            print(f"⚠️  {err}")
            delay = 120  # a bad key or quota: don't burn through the daily quota retrying
        except Exception as err:
            print(f"⚠️  YouTube chat: {err}; trying again in {delay}s")
        await asyncio.sleep(delay)
        delay = min(delay * 2, 300)
