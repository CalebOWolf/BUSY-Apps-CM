"""
Audio visualizer: little equalizer bars that bounce behind the title.

Runs `cava` (https://github.com/karlstav/cava) in raw mode and keeps the
latest bar heights. cava listens to your sound output (PipeWire, PulseAudio…)
by itself, so nothing else needs setting up.

    sudo pacman -S cava
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

BARS = 13         # 13 bars x (3 px + 1 gap) fill the 52 px title area
MAX_HEIGHT = 8    # bar heights run 0..8 pixels

CONFIG = f"""
[general]
bars = {BARS}
framerate = 30

[output]
method = raw
raw_target = /dev/stdout
data_format = ascii
ascii_max_range = {MAX_HEIGHT}
bar_delimiter = 59
frame_delimiter = 10
"""


class Visualizer:
    def __init__(self, mode: str = "auto"):
        self.levels = [0] * BARS
        self.enabled = mode != "off" and shutil.which("cava") is not None
        if mode == "on" and not self.enabled:
            raise SystemExit("--visualizer on needs cava:  sudo pacman -S cava")
        self._config = Path(tempfile.gettempdir()) / "luca-now-playing-cava.conf"

    async def run(self) -> None:
        if not self.enabled:
            return
        self._config.write_text(CONFIG)
        complained = False
        while True:
            proc = await asyncio.create_subprocess_exec(
                "cava", "-p", str(self._config),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            try:
                assert proc.stdout
                async for raw in proc.stdout:
                    values = [v for v in raw.decode(errors="replace").strip().split(";") if v]
                    try:
                        levels = [max(0, min(MAX_HEIGHT, int(v))) for v in values[:BARS]]
                    except ValueError:
                        continue
                    self.levels = levels + [0] * (BARS - len(levels))
                    complained = False
            finally:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
            self.levels = [0] * BARS
            if not complained:
                print("⚠️  The visualizer (cava) stopped; I'll try it again in a bit.")
                complained = True
            await asyncio.sleep(10)
