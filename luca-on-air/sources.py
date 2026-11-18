"""
Finds out whether you're on air, all on this PC (no accounts, no internet).

  OBS        live or recording, through OBS Studio's built-in WebSocket
             (Tools → WebSocket Server Settings, OBS 28 and newer)
  Mic        which apps are using your microphone right now (PipeWire or
             PulseAudio, through `pactl`), so a Discord call shows as a call
  Camera     which apps have your webcam open (/dev/video*)
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from devices import CALL_APPS, IGNORE_MIC, camera_users, mic_users, nice_name  # noqa: E402,F401

@dataclass
class Status:
    streaming: bool = False
    stream_since: float | None = None   # time.time() when the stream started
    recording: bool = False
    record_since: float | None = None
    recording_paused: bool = False
    mic_apps: list[str] = field(default_factory=list)
    call_app: str | None = None
    cam_apps: list[str] = field(default_factory=list)
    obs_connected: bool = False

    @property
    def mode(self) -> str | None:
        """What to show, most important first; None means nothing's on air."""
        if self.streaming:
            return "live"
        if self.recording:
            return "rec"
        if self.call_app:
            return "call"
        if self.cam_apps:
            return "cam"
        return None


# --------------------------------------------------------------------------
# OBS Studio (obs-websocket 5)
# --------------------------------------------------------------------------
OUTPUTS_EVENTS = 1 << 6   # the "Outputs" event group: stream and record state


def obs_auth(password: str, salt: str, challenge: str) -> str:
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


def _timecode(tc: str | None) -> float | None:
    """'01:23:45.678' → seconds."""
    try:
        h, m, s = tc.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except (AttributeError, ValueError):
        return None


class OBS:
    """Keeps a connection to OBS and updates `status` as streams and recordings
    start and stop. Reconnects quietly whenever OBS isn't running."""

    def __init__(self, status: Status, host: str = "localhost:4455", password: str | None = None,
                 on_change=None):
        self.status, self.host, self.password = status, host, password
        self.on_change = on_change or (lambda: None)
        self.warned = False

    async def _request(self, ws, kind: str) -> dict:
        rid = str(uuid.uuid4())
        await ws.send(json.dumps({"op": 6, "d": {"requestType": kind, "requestId": rid}}))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("op") == 7 and msg["d"].get("requestId") == rid:
                return msg["d"].get("responseData") or {}
            if msg.get("op") == 5:
                self._event(msg["d"])

    def _event(self, d: dict) -> None:
        kind, data = d.get("eventType"), d.get("eventData") or {}
        s = self.status
        if kind == "StreamStateChanged":
            s.streaming = bool(data.get("outputActive"))
            s.stream_since = time.time() if s.streaming else None
        elif kind == "RecordStateChanged":
            state = data.get("outputState", "")
            s.recording = bool(data.get("outputActive")) or state == "OBS_WEBSOCKET_OUTPUT_PAUSED"
            s.recording_paused = state == "OBS_WEBSOCKET_OUTPUT_PAUSED"
            if state == "OBS_WEBSOCKET_OUTPUT_STARTED":
                s.record_since = time.time()
            elif not s.recording:
                s.record_since = None
        else:
            return
        self.on_change()

    async def run(self) -> None:
        import websockets
        import websockets.exceptions
        delay = 5
        while True:
            try:
                async with websockets.connect(f"ws://{self.host}", open_timeout=5,
                                              subprotocols=["obswebsocket.json"]) as ws:
                    hello = json.loads(await ws.recv())["d"]
                    ident = {"rpcVersion": 1, "eventSubscriptions": OUTPUTS_EVENTS}
                    auth = hello.get("authentication")
                    if auth:
                        if not self.password:
                            raise PermissionError("OBS wants a password: pass --obs-password "
                                                  "(or set OBS_PASSWORD)")
                        ident["authentication"] = obs_auth(self.password, auth["salt"], auth["challenge"])
                    await ws.send(json.dumps({"op": 1, "d": ident}))
                    try:
                        reply = json.loads(await ws.recv())
                    except websockets.exceptions.ConnectionClosed as closed:
                        code = closed.rcvd.code if closed.rcvd else None
                        raise PermissionError(
                            "OBS turned us away: the password is wrong (check --obs-password)"
                            if code == 4009 else f"OBS closed the connection (code {code})")
                    if reply.get("op") != 2:
                        raise PermissionError("OBS didn't accept us (wrong password?)")
                    s = self.status
                    stream = await self._request(ws, "GetStreamStatus")
                    s.streaming = bool(stream.get("outputActive"))
                    up = _timecode(stream.get("outputTimecode"))
                    s.stream_since = time.time() - up if s.streaming and up is not None else (
                        time.time() if s.streaming else None)
                    rec = await self._request(ws, "GetRecordStatus")
                    s.recording = bool(rec.get("outputActive"))
                    s.recording_paused = bool(rec.get("outputPaused"))
                    up = _timecode(rec.get("outputTimecode"))
                    s.record_since = time.time() - up if s.recording and up is not None else (
                        time.time() if s.recording else None)
                    s.obs_connected, self.warned, delay = True, False, 5
                    print("🎥 Connected to OBS")
                    self.on_change()
                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("op") == 5:
                            self._event(msg["d"])
            except asyncio.CancelledError:
                raise
            except PermissionError as err:
                if not self.warned:
                    print(f"⚠️  {err}")
                    self.warned = True
                delay = 30
            except Exception:
                pass  # OBS isn't running (yet); that's fine
            s = self.status
            if s.obs_connected:
                print("🎥 OBS closed")
            s.obs_connected = s.streaming = s.recording = s.recording_paused = False
            s.stream_since = s.record_since = None
            self.on_change()
            await asyncio.sleep(delay)
