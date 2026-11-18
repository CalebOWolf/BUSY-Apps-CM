"""
Which apps are using your microphone and webcam right now, found locally
(shared by Luca On Air and Luca Discord).

  mic_users()     apps recording from a real microphone (PipeWire or
                  PulseAudio, through `pactl`), not paused, not a monitor
  camera_users()  apps with a /dev/video* webcam open
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

# Apps whose use of the mic means "in a call".
CALL_APPS = {
    "discord", "vesktop", "webcord", "armcord", "legcord", "zoom", "teams", "teams-for-linux",
    "slack", "skype", "skypeforlinux", "signal", "signal-desktop", "telegram", "telegram-desktop",
    "element", "mumble", "teamspeak", "ts3client", "jitsi", "whatsapp",
    # browsers: almost always Meet, Jitsi, Discord in the browser…
    "firefox", "chromium", "chrome", "google-chrome", "brave", "vivaldi", "opera", "librewolf",
}
# Apps that hold the mic open without it meaning anything (OBS is followed directly).
IGNORE_MIC = {"obs", "cava", "pavucontrol", "easyeffects", "pulseeffects", "noisetorch",
              "pw-cat", "pw-record", "parec", "qpwgraph", "helvum"}


def nice_name(raw: str) -> str:
    base = os.path.basename(raw or "").lower()
    for suffix in (".exe", "-bin", "-desktop", ".bin"):
        base = base.removesuffix(suffix)
    return {"webrtc voiceengine": "discord", "google-chrome": "chrome",
            "skypeforlinux": "skype", "ts3client": "teamspeak"}.get(base, base)


# --------------------------------------------------------------------------
# Microphone
# --------------------------------------------------------------------------
def mic_users() -> list[str]:
    """Apps recording from a real microphone right now (not paused, not a monitor)."""
    if not shutil.which("pactl"):
        return []
    try:
        sources = json.loads(subprocess.run(["pactl", "-f", "json", "list", "sources"],
                                            capture_output=True, text=True, timeout=3).stdout or "[]")
        outputs = json.loads(subprocess.run(["pactl", "-f", "json", "list", "source-outputs"],
                                            capture_output=True, text=True, timeout=3).stdout or "[]")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    monitors = {s.get("index") for s in sources
                if s.get("name", "").endswith(".monitor") or s.get("monitor_of_sink") not in (None, "n/a")}
    apps = []
    for o in outputs:
        if o.get("corked") or o.get("source") in monitors:
            continue
        props = o.get("properties", {})
        name = nice_name(props.get("application.process.binary") or props.get("application.name", ""))
        if name and name not in IGNORE_MIC and name not in apps:
            apps.append(name)
    return apps


# --------------------------------------------------------------------------
# Camera
# --------------------------------------------------------------------------
def camera_users(prefix: str = "/dev/video", proc: str = "/proc") -> list[str]:
    """Apps with a webcam open, found by looking at our own processes' open files."""
    apps = []
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return []
    me = os.getpid()
    for pid in pids:
        if int(pid) == me:
            continue
        fd_dir = os.path.join(proc, pid, "fd")
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue  # someone else's process, or it just exited
        for fd in fds:
            try:
                target = os.readlink(os.path.join(fd_dir, fd))
            except OSError:
                continue
            if target.startswith(prefix):
                try:
                    with open(os.path.join(proc, pid, "comm")) as f:
                        name = nice_name(f.read().strip())
                except OSError:
                    name = "app"
                if name not in apps:
                    apps.append(name)
                break
    return apps
