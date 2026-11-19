"""
The speed test itself: ping, download and upload against Cloudflare's speed
test servers (speed.cloudflare.com), using only Python's standard library.

    test = SpeedTest()
    result = test.run()          # blocks for about 20 seconds
    print(result.down_mbps, result.up_mbps, result.ping_ms)

While it runs, `test.phase`, `test.live_mbps` and `test.progress` say how
it's going, so the screen can follow along.
"""

from __future__ import annotations

import http.client
import statistics
import threading
import time
import urllib.parse
from dataclasses import dataclass, field

DEFAULT_SERVER = "https://speed.cloudflare.com"
USER_AGENT = "busy-speedtest/1.0"
PINGS = 12
STREAMS = 4                  # parallel connections, so one slow stream doesn't decide the result
DOWN_CHUNK = 25_000_000      # bytes asked for per download request
UP_CHUNK = 8_000_000         # bytes sent per upload request
PIECE = 64 * 1024
TIMEOUT = 15


@dataclass
class Result:
    ping_ms: float = 0.0
    jitter_ms: float = 0.0
    down_mbps: float = 0.0
    up_mbps: float = 0.0
    server: str = ""          # where the test server is, if it said
    finished: float = field(default_factory=time.time)


class TestFailed(Exception):
    pass


class SpeedTest:
    def __init__(self, server: str = DEFAULT_SERVER, seconds: float = 8.0):
        url = urllib.parse.urlsplit(server)
        if url.scheme not in ("http", "https") or not url.hostname:
            raise ValueError(f"not a server address: {server}")
        self.https = url.scheme == "https"
        self.host = url.hostname
        self.port = url.port
        self.base = url.path.rstrip("/")
        self.seconds = seconds
        self.phase = "idle"       # idle, ping, download, upload
        self.live_mbps = 0.0
        self.live_ping = 0.0
        self.progress = 0.0       # 0..1 through the current phase
        self._bytes = 0
        self._lock = threading.Lock()
        self._stop_at = 0.0

    # -- connections -------------------------------------------------------
    def _connect(self) -> http.client.HTTPConnection:
        cls = http.client.HTTPSConnection if self.https else http.client.HTTPConnection
        return cls(self.host, self.port, timeout=TIMEOUT)

    def _headers(self, extra: dict | None = None) -> dict:
        return {"User-Agent": USER_AGENT, "Accept": "*/*", **(extra or {})}

    # -- ping --------------------------------------------------------------
    def ping(self) -> tuple[float, float, str]:
        """Median and jitter (ms) of tiny requests over one kept-open connection."""
        self.phase, self.progress = "ping", 0.0
        conn = self._connect()
        times, server = [], ""
        try:
            for i in range(PINGS + 1):
                start = time.perf_counter()
                conn.request("GET", f"{self.base}/__down?bytes=0", headers=self._headers())
                resp = conn.getresponse()
                resp.read()
                took = (time.perf_counter() - start) * 1000
                if resp.status >= 400:
                    raise TestFailed(f"the server said {resp.status} {resp.reason}")
                took -= _server_time(resp.getheader("Server-Timing"))
                if i == 0:  # the first one includes setting up the connection
                    server = _place(resp)
                    continue
                times.append(max(took, 0.1))
                self.live_ping = statistics.median(times)
                self.progress = i / PINGS
        finally:
            conn.close()
        jitter = statistics.mean(abs(a - b) for a, b in zip(times, times[1:])) if len(times) > 1 else 0
        return statistics.median(times), jitter, server

    # -- download / upload -------------------------------------------------
    def _count(self, n: int) -> None:
        with self._lock:
            self._bytes += n

    def _download_stream(self, errors: list) -> None:
        conn = self._connect()
        try:
            while time.monotonic() < self._stop_at:
                conn.request("GET", f"{self.base}/__down?bytes={DOWN_CHUNK}", headers=self._headers())
                resp = conn.getresponse()
                if resp.status >= 400:
                    raise TestFailed(f"the server said {resp.status} {resp.reason}")
                while time.monotonic() < self._stop_at:
                    piece = resp.read(PIECE)
                    if not piece:
                        break
                    self._count(len(piece))
                else:
                    return  # time's up mid-download: just drop the connection
        except (OSError, http.client.HTTPException, TestFailed) as err:
            errors.append(err)
        finally:
            conn.close()

    def _upload_stream(self, errors: list) -> None:
        piece = b"0" * PIECE
        conn = self._connect()
        try:
            while time.monotonic() < self._stop_at:
                conn.putrequest("POST", f"{self.base}/__up")
                for k, v in self._headers({"Content-Type": "application/octet-stream",
                                           "Content-Length": str(UP_CHUNK)}).items():
                    conn.putheader(k, v)
                conn.endheaders()
                sent = 0
                while sent < UP_CHUNK:
                    if time.monotonic() >= self._stop_at:
                        return  # time's up mid-upload: just drop the connection
                    chunk = piece[:min(PIECE, UP_CHUNK - sent)]
                    conn.send(chunk)
                    sent += len(chunk)
                    self._count(len(chunk))
                resp = conn.getresponse()
                resp.read()
                if resp.status >= 400:
                    raise TestFailed(f"the server said {resp.status} {resp.reason}")
        except (OSError, http.client.HTTPException, TestFailed) as err:
            errors.append(err)
        finally:
            conn.close()

    def _measure(self, phase: str, worker) -> float:
        """Run STREAMS workers for `seconds`; returns Mbps. The first second
        is left out of the result, while the connections speed up."""
        self.phase, self.progress, self.live_mbps = phase, 0.0, 0.0
        self._bytes = 0
        start = time.monotonic()
        self._stop_at = start + self.seconds
        errors: list = []
        threads = [threading.Thread(target=worker, args=(errors,), daemon=True)
                   for _ in range(STREAMS)]
        for t in threads:
            t.start()
        warm_bytes, warm_at = None, None
        last_bytes, last_at = 0, start
        while any(t.is_alive() for t in threads):
            time.sleep(0.25)
            now = time.monotonic()
            got = self._bytes
            if warm_at is None and now - start >= 1.0:
                warm_bytes, warm_at = got, now
            # a smoothed live reading for the screen
            if now > last_at:
                instant = (got - last_bytes) * 8 / (now - last_at) / 1e6
                self.live_mbps = instant if self.live_mbps == 0 else self.live_mbps * 0.6 + instant * 0.4
                last_bytes, last_at = got, now
            self.progress = min((now - start) / self.seconds, 1.0)
        end = time.monotonic()
        if self._bytes == 0:
            raise TestFailed(str(errors[0]) if errors else "nothing came through")
        if warm_at is None or end - warm_at < 0.5:
            return self._bytes * 8 / (end - start) / 1e6
        return (self._bytes - warm_bytes) * 8 / (end - warm_at) / 1e6

    # -- all of it ---------------------------------------------------------
    def run(self) -> Result:
        try:
            ping, jitter, server = self.ping()
            down = self._measure("download", self._download_stream)
            self.live_mbps = down
            up = self._measure("upload", self._upload_stream)
            self.live_mbps = up
            return Result(round(ping, 1), round(jitter, 1), down, up, server)
        except (OSError, http.client.HTTPException) as err:
            raise TestFailed(str(getattr(err, "reason", err)) or type(err).__name__) from err
        finally:
            self.phase, self.progress = "idle", 0.0


def _server_time(header: str | None) -> float:
    """How long the server says it spent (ms), from `Server-Timing: x;dur=1.2`."""
    if not header:
        return 0.0
    for part in header.split(";"):
        part = part.strip()
        if part.startswith("dur="):
            try:
                return float(part[4:])
            except ValueError:
                return 0.0
    return 0.0


def _place(resp: http.client.HTTPResponse) -> str:
    """Cloudflare says which of its data centers answered (e.g. "FRA")."""
    colo = resp.getheader("cf-meta-colo") or ""
    city = resp.getheader("cf-meta-city") or ""
    return " ".join(p for p in (colo, city and f"({city})") if p)


def format_speed(mbps: float) -> tuple[str, str]:
    """(number, unit) for a speed: "245", "MBPS" / "12.4", "MBPS" / "1.23", "GBPS"."""
    if mbps >= 1000:
        return f"{mbps / 1000:.2f}", "GBPS"
    if mbps >= 100:
        return f"{mbps:.0f}", "MBPS"
    if mbps >= 10:
        return f"{mbps:.1f}", "MBPS"
    return f"{mbps:.2f}", "MBPS"
