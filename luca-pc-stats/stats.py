"""
Reads this PC's vitals: CPU, RAM, temperatures, GPU and network.

  CPU, RAM, network, CPU temperature   psutil
  NVIDIA GPU                           nvidia-smi
  AMD GPU                              the amdgpu driver's files in /sys
  --demo                               made-up numbers that drift around

Anything the PC can't report comes back as None and shows as "--".
"""

from __future__ import annotations

import glob
import math
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field

DRM_ROOT = "/sys/class/drm"

# Sensor names psutil uses for the CPU package temperature, best first.
CPU_SENSORS = [("k10temp", ("Tctl", "Tdie")), ("zenpower", ("Tdie", "Tctl")),
               ("coretemp", ("Package id 0",)), ("cpu_thermal", ()), ("acpitz", ())]


@dataclass
class Snapshot:
    cpu: float | None = None          # % busy
    ram: float | None = None          # % used
    ram_used: float | None = None     # GB
    ram_total: float | None = None    # GB
    cpu_temp: float | None = None     # °C
    gpu: float | None = None          # % busy
    gpu_temp: float | None = None     # °C
    gpu_name: str = ""
    net_down: float | None = None     # bytes per second
    net_up: float | None = None
    history: list[float] = field(default_factory=list)  # recent CPU %, oldest first

    @property
    def hottest(self) -> float | None:
        temps = [t for t in (self.cpu_temp, self.gpu_temp) if t is not None]
        return max(temps) if temps else None


def _read(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _num(text: str | None) -> float | None:
    try:
        return float(text) if text not in (None, "", "[N/A]") else None
    except ValueError:
        return None


# --------------------------------------------------------------------------
# GPUs
# --------------------------------------------------------------------------
def nvidia() -> tuple[float | None, float | None, str] | None:
    if not shutil.which("nvidia-smi"):
        return None
    out = _run(["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu,name",
                "--format=csv,noheader,nounits"])
    if not out:
        return None
    first = out.splitlines()[0].split(",")
    if len(first) < 3:
        return None
    return _num(first[0].strip()), _num(first[1].strip()), first[2].strip()


def amd() -> tuple[float | None, float | None, str] | None:
    """The busiest AMD GPU (a desktop with an iGPU has two)."""
    best = None
    for busy_file in glob.glob(os.path.join(DRM_ROOT, "card*", "device", "gpu_busy_percent")):
        device = os.path.dirname(busy_file)
        busy = _num(_read(busy_file))
        temp = None
        for hwmon in glob.glob(os.path.join(device, "hwmon", "hwmon*")):
            # temp1 is "edge"; temp2 "junction" is hotter and what fans react to
            for name in ("temp2_input", "temp1_input"):
                raw = _num(_read(os.path.join(hwmon, name)))
                if raw is not None:
                    temp = raw / 1000
                    break
            if temp is not None:
                break
        name = "AMD GPU"
        if busy is not None and (best is None or busy > (best[0] or 0)):
            best = (busy, temp, name)
    return best


# --------------------------------------------------------------------------
# The reader
# --------------------------------------------------------------------------
class Stats:
    HISTORY = 60

    def __init__(self):
        try:
            import psutil
        except ImportError:
            raise SystemExit("Luca PC Stats needs psutil:  pip install psutil")
        self.psutil = psutil
        psutil.cpu_percent(interval=None)  # the first reading is always 0; prime it
        self.history: list[float] = []
        self._net = (psutil.net_io_counters(), time.monotonic())
        self.gpu_source = "nvidia" if nvidia() else "amd" if amd() else None

    def cpu_temp(self) -> float | None:
        read = getattr(self.psutil, "sensors_temperatures", None)
        sensors = read() if read else {}
        for chip, labels in CPU_SENSORS:
            for entry in sensors.get(chip, []):
                if not labels or entry.label in labels:
                    return entry.current
        for chip, labels in CPU_SENSORS:  # a known chip with unexpected labels
            if sensors.get(chip):
                return max(e.current for e in sensors[chip])
        return None

    def read(self) -> Snapshot:
        ps = self.psutil
        s = Snapshot()
        s.cpu = ps.cpu_percent(interval=None)
        mem = ps.virtual_memory()
        s.ram, s.ram_used, s.ram_total = mem.percent, mem.used / 1e9, mem.total / 1e9
        s.cpu_temp = self.cpu_temp()
        gpu = nvidia() if self.gpu_source == "nvidia" else amd() if self.gpu_source == "amd" else None
        if gpu:
            s.gpu, s.gpu_temp, s.gpu_name = gpu
        net, at = ps.net_io_counters(), time.monotonic()
        (old, old_at) = self._net
        if at > old_at:
            s.net_down = max(0.0, (net.bytes_recv - old.bytes_recv) / (at - old_at))
            s.net_up = max(0.0, (net.bytes_sent - old.bytes_sent) / (at - old_at))
        self._net = (net, at)
        self.history = (self.history + [s.cpu])[-self.HISTORY:]
        s.history = list(self.history)
        return s


class DemoStats:
    """Smoothly drifting pretend numbers, including a hot spell now and then."""

    gpu_source = "demo"

    def __init__(self):
        self.t0 = time.monotonic()
        self.history: list[float] = []

    def read(self) -> Snapshot:
        t = time.monotonic() - self.t0
        heat = (math.sin(t / 9) + 1) / 2  # 0..1, a slow wave from cool to hot
        cpu = max(0.0, min(100.0, 15 + 70 * heat + 10 * math.sin(t * 1.7)))
        s = Snapshot(cpu=round(cpu, 1), ram=round(42 + 6 * math.sin(t / 20), 1),
                     ram_used=6.8, ram_total=16.0,
                     cpu_temp=round(42 + 48 * heat, 1), gpu=round(max(0, 60 * heat - 5), 1),
                     gpu_temp=round(38 + 40 * heat, 1), gpu_name="Demo GPU",
                     net_down=abs(math.sin(t / 3)) * 2.4e6, net_up=abs(math.cos(t / 4)) * 3e5)
        self.history = (self.history + [s.cpu])[-Stats.HISTORY:]
        s.history = list(self.history)
        return s
