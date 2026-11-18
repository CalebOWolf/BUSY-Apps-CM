"""
When should notification-style apps keep quiet?

Luca Pack Focus writes a small file while a focus round runs, and Luca On Air
while you're live or recording. Luca Notify Den and Luca Discord read them and
hold new messages until you're done.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

_SHARED_DIR = Path(os.environ.get("XDG_RUNTIME_DIR")
                   or Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"))
QUIET_FILES = {"focus": (_SHARED_DIR / "luca-focus.json", "focusing"),
               "onair": (_SHARED_DIR / "luca-onair.json", "on_air")}


def quiet_reason() -> str | None:
    """"focus" during a focus round, "onair" while live or recording, else None.
    A file that hasn't been refreshed for 5 seconds (its app crashed) is ignored."""
    for reason, (path, flag) in QUIET_FILES.items():
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if data.get(flag) and time.time() - data.get("updated", 0) < 5:
            return reason
    return None
