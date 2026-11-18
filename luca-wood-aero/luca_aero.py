"""
Luca Wood Aero 🐺, a Frutiger Aero / Windows 7 style app for the BUSY Bar.

Uploads the artwork from build/ to the bar, then animates the front strip
(drifting bubbles, bouncing Luca) and shows the Aero window on the back.

    python render.py                      # once, to build the artwork
    python luca_aero.py                   # BUSY Bar on USB (10.0.4.20)
    python luca_aero.py --host 192.168.1.42 --token YOUR_KEY   # over Wi-Fi

Press Ctrl+C to stop; the app clears its screens on the way out.
Needs only the Python standard library at runtime.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

APP = "luca_wood_aero"
BUILD = Path(__file__).parent / "build"


class BusyBar:
    def __init__(self, host: str, token: str | None = None):
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
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as err:
            detail = err.read().decode(errors="replace")
            raise SystemExit(f"BUSY Bar said {err.code} for {method} {path}: {detail}")
        return json.loads(raw) if raw else {}

    def upload(self, filename: str, data: bytes) -> None:
        self._call("POST", "/assets/upload",
                   params={"application_name": APP, "file": filename},
                   body=data, content_type="application/octet-stream")

    def draw(self, elements: list[dict], priority: int = 50) -> None:
        payload = {"application_name": APP, "priority": priority, "elements": elements}
        self._call("POST", "/display/draw", body=json.dumps(payload).encode(),
                   content_type="application/json")

    def clear(self) -> None:
        self._call("DELETE", "/display/draw", params={"application_name": APP})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="10.0.4.20",
                    help="BUSY Bar address (default: 10.0.4.20, the USB address)")
    ap.add_argument("--token", help="API key, if HTTP access is set to 'key' mode")
    ap.add_argument("--fps", type=float, default=7, help="bubble animation speed")
    args = ap.parse_args()

    frames = sorted(BUILD.glob("front_*.png"))
    back = BUILD / "back.png"
    if not frames or not back.exists():
        raise SystemExit("No artwork yet. Run `python render.py` first.")

    bar = BusyBar(args.host, args.token)
    print(f"🐺 Uploading {len(frames) + 1} images to the BUSY Bar at {args.host}…")
    for f in [*frames, back]:
        bar.upload(f.name, f.read_bytes())

    back_el = {"id": "window", "type": "image", "path": back.name,
               "display": "back", "x": 0, "y": 0}
    print("✨ Luca is live! Press Ctrl+C to stop.")
    try:
        i = 0
        while True:
            front_el = {"id": "sky", "type": "image", "path": frames[i].name,
                        "display": "front", "x": 0, "y": 0}
            bar.draw([front_el, back_el])
            i = (i + 1) % len(frames)
            time.sleep(1 / args.fps)
    except KeyboardInterrupt:
        pass
    finally:
        bar.clear()
        print("\n🌙 Luca says goodnight. Screens cleared.")


if __name__ == "__main__":
    main()
