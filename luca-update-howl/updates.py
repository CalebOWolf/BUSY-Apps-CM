"""
What's waiting to be updated on your Arch system, and whether to reboot.

  official repos   `checkupdates` (from pacman-contrib) checks against a
                   fresh copy of the package lists in a temporary folder, so
                   your real database is never touched and no root is needed.
                   Without it, `paru -Qu --repo` uses your last sync instead.
  the AUR          `paru -Qua` asks the AUR for newer versions.
  reboot           after a kernel update, the running kernel's modules
                   (/usr/lib/modules/<uname -r>) are gone until you reboot.

Nothing here installs anything: updating is still up to you (`paru`).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

PACMAN_LOCAL = Path("/var/lib/pacman/local")   # changes whenever packages are installed
BIG = ("linux", "nvidia", "mesa", "systemd", "glibc", "pacman", "paru", "plasma-desktop",
       "kwin", "gnome-shell", "xorg-server", "wayland", "pipewire", "grub", "amd-ucode", "intel-ucode")


@dataclass
class Update:
    name: str
    old: str
    new: str
    aur: bool = False

    @property
    def big(self) -> bool:
        """Kernels, drivers and the core of the system."""
        return any(self.name == b or self.name.startswith(b + "-") for b in BIG)

    @property
    def kernel(self) -> bool:
        return self.name == "linux" or (self.name.startswith("linux-") and
                                        not self.name.startswith(("linux-firmware", "linux-api")))


@dataclass
class Status:
    updates: list[Update] = field(default_factory=list)
    reboot: bool = False
    running_kernel: str = ""
    checked: float = 0.0
    error: str = ""          # why the last check failed (the list is from before)
    aur_checked: bool = True

    @property
    def repo(self) -> list[Update]:
        return [u for u in self.updates if not u.aur]

    @property
    def aur(self) -> list[Update]:
        return [u for u in self.updates if u.aur]

    @property
    def big(self) -> list[Update]:
        return [u for u in self.updates if u.big]

    @property
    def kernel(self) -> bool:
        return any(u.kernel for u in self.updates)


def _parse(text: str, aur: bool) -> list[Update]:
    out = []
    for line in text.splitlines():
        parts = line.split()
        # "name old -> new", sometimes followed by "[ignored]"
        if len(parts) >= 4 and parts[2] == "->":
            out.append(Update(parts[0], parts[1], parts[3], aur))
    return out


def _run(cmd: list[str], ok_codes: tuple[int, ...]) -> tuple[str, str]:
    """(output, error message). A code in ok_codes with no output means "none"."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                           env=dict(os.environ, LC_ALL="C"))
    except (OSError, subprocess.TimeoutExpired) as err:
        return "", f"{cmd[0]}: {err}"
    if r.returncode == 0 or r.returncode in ok_codes:
        return r.stdout, ""
    msg = (r.stderr or r.stdout).strip().splitlines()
    return "", f"{cmd[0]} said: {msg[-1] if msg else f'exit code {r.returncode}'}"


def reboot_needed() -> tuple[bool, str]:
    release = os.uname().release
    modules = Path("/usr/lib/modules")
    # only when kernels are installed there at all (not in a container) but not this one
    installed = modules.is_dir() and any(modules.iterdir())
    return installed and not (modules / release).exists(), release


def check(aur: bool = True) -> Status:
    """Look for updates (takes a few seconds: it goes online)."""
    status = Status(checked=time.time())
    status.reboot, status.running_kernel = reboot_needed()
    errors = []
    if shutil.which("checkupdates"):
        out, err = _run(["checkupdates", "--nocolor"], ok_codes=(2,))  # 2 = nothing to update
    elif shutil.which("paru"):
        out, err = _run(["paru", "-Qu", "--repo", "--color", "never"], ok_codes=(1,))
    else:
        out, err = "", "neither checkupdates (pacman-contrib) nor paru is installed"
    status.updates += _parse(out, aur=False)
    if err:
        errors.append(err)
    if aur and shutil.which("paru"):
        out, err = _run(["paru", "-Qua", "--color", "never"], ok_codes=(1,))
        status.updates += _parse(out, aur=True)
        if err:
            errors.append(err)
    else:
        status.aur_checked = False
    status.error = "; ".join(errors)
    status.updates.sort(key=lambda u: (not u.big, u.aur, u.name))
    return status


def packages_changed_since(when: float) -> bool:
    """Did something install or update packages since `when`? (e.g. you ran paru)"""
    try:
        return PACMAN_LOCAL.stat().st_mtime > when
    except OSError:
        return False


if __name__ == "__main__":
    s = check()
    print(f"{len(s.repo)} from the repos, {len(s.aur)} from the AUR"
          + (", reboot needed" if s.reboot else "") + (f" ({s.error})" if s.error else ""))
    for u in s.updates:
        print(f"  {'⭐' if u.big else ' '} {u.name} {u.old} -> {u.new}" + ("  (AUR)" if u.aur else ""))
