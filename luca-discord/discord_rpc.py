"""
Talks to the Discord desktop app on this PC over its local RPC socket.

This is Discord's own supported way for apps on your computer to read your
voice state and notifications. It needs a (free) Discord application of your
own, which you make once at https://discord.com/developers/applications: its
Client ID and Client Secret go to --client-id / --client-secret. The first
time, Discord pops up an "Authorize" window; after that the login is kept in
~/.config/luca-discord/token.json (only you can read it) and refreshed by
itself.

No user tokens, no self-botting: only what Discord's RPC API hands out.
"""

from __future__ import annotations

import asyncio
import json
import os
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

API = "https://discord.com/api"
SCOPES = ["rpc", "rpc.voice.read", "rpc.voice.write", "rpc.notifications.read", "identify"]
TOKEN_FILE = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "luca-discord" / "token.json"

OP_HANDSHAKE, OP_FRAME, OP_CLOSE, OP_PING, OP_PONG = 0, 1, 2, 3, 4


class NeedsAuthorize(Exception):
    """No saved login, and we've already asked once this run."""


class RPCError(Exception):
    def __init__(self, code, message):
        super().__init__(f"{message} (code {code})")
        self.code = code


def socket_paths() -> list[Path]:
    """Where Discord (regular, Flatpak or Snap) puts its socket."""
    base = Path(os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("TMPDIR") or "/tmp")
    dirs = [base, base / "app" / "com.discordapp.Discord", base / "snap.discord",
            base / ".flatpak" / "com.discordapp.Discord" / "xdg-run"]
    return [d / f"discord-ipc-{i}" for d in dirs for i in range(10)]


class DiscordRPC:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str = "http://localhost",
                 on_event=None, api: str = API, token_file: Path = TOKEN_FILE):
        self.client_id, self.client_secret, self.redirect_uri = client_id, client_secret, redirect_uri
        self.on_event = on_event or (lambda evt, data: None)
        self.api, self.token_file = api, token_file
        self.reader = self.writer = None
        self.pending: dict[str, asyncio.Future] = {}
        self.user: dict = {}
        self._reader_task: asyncio.Task | None = None

    # -- framing ----------------------------------------------------------------
    def _send(self, op: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.writer.write(struct.pack("<II", op, len(data)) + data)

    async def _recv(self) -> tuple[int, dict]:
        header = await self.reader.readexactly(8)
        op, length = struct.unpack("<II", header)
        return op, json.loads(await self.reader.readexactly(length) or b"{}")

    async def _read_loop(self) -> None:
        try:
            while True:
                op, msg = await self._recv()
                if op == OP_PING:
                    self._send(OP_PONG, msg)
                elif op == OP_CLOSE:
                    raise ConnectionError(f"Discord closed the connection: {msg.get('message', '')}")
                elif msg.get("nonce") in self.pending:
                    self.pending.pop(msg["nonce"]).set_result(msg)
                elif msg.get("cmd") == "DISPATCH":
                    self.on_event(msg.get("evt"), msg.get("data") or {})
        except Exception as err:
            for fut in self.pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError(str(err)))
            self.pending.clear()
            raise

    async def command(self, cmd: str, args: dict | None = None, evt: str | None = None,
                      timeout: float = 15) -> dict:
        nonce = str(uuid.uuid4())
        fut = asyncio.get_running_loop().create_future()
        self.pending[nonce] = fut
        payload = {"cmd": cmd, "args": args or {}, "nonce": nonce}
        if evt:
            payload["evt"] = evt
        self._send(OP_FRAME, payload)
        msg = await asyncio.wait_for(fut, timeout)
        if msg.get("evt") == "ERROR":
            d = msg.get("data") or {}
            raise RPCError(d.get("code"), d.get("message", "error"))
        return msg.get("data") or {}

    async def subscribe(self, evt: str, args: dict | None = None) -> None:
        await self.command("SUBSCRIBE", args, evt)

    async def unsubscribe(self, evt: str, args: dict | None = None) -> None:
        try:
            await self.command("UNSUBSCRIBE", args, evt)
        except (RPCError, ConnectionError, asyncio.TimeoutError):
            pass

    # -- connecting --------------------------------------------------------------
    async def connect(self, ask: bool = True) -> dict:
        """Open the socket, shake hands and log in. Returns your user. With
        ask=False it only uses the saved login and never pops up Authorize."""
        self.asked = False
        last = None
        for path in socket_paths():
            if path.exists():
                try:
                    self.reader, self.writer = await asyncio.open_unix_connection(str(path))
                    break
                except OSError as err:
                    last = err
        else:
            raise ConnectionError(f"Discord isn't running (no RPC socket found){f': {last}' if last else ''}")
        self._send(OP_HANDSHAKE, {"v": 1, "client_id": self.client_id})
        op, ready = await self._recv()
        if op == OP_CLOSE or ready.get("evt") != "READY":
            raise ConnectionError(f"Discord said no: {ready.get('message', ready)}")
        self._reader_task = asyncio.create_task(self._read_loop())
        self.user = await self._login(ask)
        return self.user

    def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self.writer:
            self.writer.close()

    async def wait_closed(self) -> None:
        if self._reader_task:
            await self._reader_task

    # -- logging in ----------------------------------------------------------------
    def _load_token(self) -> dict:
        try:
            return json.loads(self.token_file.read_text())
        except (OSError, ValueError):
            return {}

    def _save_token(self, tok: dict) -> None:
        tok = dict(tok, saved_at=time.time())
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.token_file.with_suffix(".tmp")
        tmp.touch(mode=0o600)
        tmp.write_text(json.dumps(tok))
        tmp.chmod(0o600)
        tmp.replace(self.token_file)

    def _token_request(self, form: dict) -> dict:
        body = urllib.parse.urlencode(dict(form, client_id=self.client_id,
                                           client_secret=self.client_secret)).encode()
        req = urllib.request.Request(f"{self.api}/oauth2/token", data=body, headers={
            "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "luca-discord/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as err:
            detail = err.read().decode(errors="replace")
            hint = ""
            if "redirect" in detail.lower():
                hint = (f" The Redirect in your Discord application (Developer Portal, OAuth2, "
                        f"Redirects) must be exactly {self.redirect_uri}")
            elif "invalid_client" in detail:
                hint = " Check the Client ID and Client Secret (Reset Secret makes the old one stop working)."
            raise RPCError(err.code, f"Discord refused the login: {detail}.{hint}")

    async def _login(self, ask: bool = True) -> dict:
        tok = self._load_token()
        if tok.get("access_token"):
            try:
                return (await self.command("AUTHENTICATE", {"access_token": tok["access_token"]}))["user"]
            except RPCError:
                pass  # expired: try the refresh token
            if tok.get("refresh_token"):
                try:
                    new = await asyncio.to_thread(self._token_request, {
                        "grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
                    self._save_token(new)
                    return (await self.command("AUTHENTICATE", {"access_token": new["access_token"]}))["user"]
                except (RPCError, OSError, KeyError):
                    pass
        if not ask:
            raise NeedsAuthorize("Luca isn't authorized in Discord yet")
        self.asked = True
        print("🔑 Discord will ask you to authorize Luca. Click **Authorize** in the Discord window.")
        code = (await self.command("AUTHORIZE", {"client_id": self.client_id, "scopes": SCOPES},
                                   timeout=300))["code"]
        new = await asyncio.to_thread(self._token_request, {
            "grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri})
        self._save_token(new)
        print(f"🔑 Authorized! Saved to {self.token_file}")
        return (await self.command("AUTHENTICATE", {"access_token": new["access_token"]}))["user"]
