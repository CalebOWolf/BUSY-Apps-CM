<div align="center">

# 🎵 Luca Now Playing 🐺

### *Your music on the BUSY Bar, with Luca bopping along in glossy Frutiger Aero style*

<img src="preview/front.gif" alt="Front LED strip: Luca in mint headphones on a glass tile, BUBBLE SKIES - LUCA WOOD scrolling across an Aero sky, with a progress bar" width="720">

<img src="preview/back.png" alt="Back screen: a Windows 7 Aero 'Luca Player' window showing the song, artist, album, progress and play controls" width="480">

</div>

---

## ✨ What it does

| Screen | What you see |
| :-- | :-- |
| **Front** (72×16 RGB LEDs) | Luca in mint headphones on a glossy glass tile, bopping to the beat. The **title and artist** scroll across an Aero sky with drifting bubbles, and a mint **progress bar** fills up as the song plays |
| **Back** (160×80, 16 greys) | **Luca Player**, a Windows 7-style media player window with the **album art** (or Luca's portrait when there's none), the song, artist and album, a progress bar with the time, and the classic glossy play/pause orb |

Luca only shows up while music plays. When you pause, the text dims and stops scrolling, and he
waits **2 minutes** in case you come back. Then he steps aside and the bar goes back to its
usual screens, until you press play again.

## 🎮 Control your music from the bar

| Press | Does |
| :-- | :-- |
| **OK** | Play / pause |
| **Start** | Next song (Luca does a happy hop) |
| **Back** | Previous song |
| **Wheel** | Volume up / down. A glossy volume bar pops up over the title for a moment |

The wheel turns your computer's main volume (through PipeWire's `wpctl`, or `pactl`) in 2%
steps. If it turns the wrong way for you, add `--reverse-wheel`.

The buttons only control your music while Luca is on the bar. When he's away they do the
bar's normal things.

## 💻 Where it gets the music from

| Computer | Works with | Extra setup |
| :-- | :-- | :-- |
| **macOS** | Spotify and Apple Music | None. The first time, macOS asks to let your terminal control the app; click **OK** |
| **Windows** | Anything in the Windows media overlay: Spotify, browsers, Media Player… | `pip install winsdk` |
| **Linux** | Any MPRIS player (Spotify, VLC, browsers…) | Install `playerctl` from your package manager |

On Linux, Luca hears about changes the moment they happen and follows **every** player at once.
He shows whichever one started playing most recently. If nothing is playing, he shows the one
paused most recently. So a paused YouTube tab won't steal the screen from Spotify. To only ever
show one app, pin it:

```bash
python now_playing.py --player spotify
```

Names are as `playerctl --list-all` shows them: `spotify`, `firefox`, `chromium`, `vlc`…

## 🚀 Run it

You need Python 3.10+, [Pillow](https://pypi.org/project/pillow/) to draw the screens, and the
official [busylib](https://pypi.org/project/busylib/) for the buttons.

```bash
pip install pillow busylib
```

Plug in your BUSY Bar over USB, start some music, then:

```bash
python now_playing.py
```

Over Wi-Fi, use the bar's IP address (and its API key, if HTTP access is set to *key* mode):

```bash
python now_playing.py --host 192.168.1.42 --token YOUR_KEY
```

No music handy? Try it with a pretend playlist:

```bash
python now_playing.py --demo
```

Press **Ctrl+C** to stop. Luca takes his headphones off and the screens are cleared. 🌙

## 🐧 Start automatically at login (Linux)

Set it up once and Luca appears whenever you play music: no terminal, nothing to remember.
It runs as a **systemd user service**.

On Arch (btw), install the system bits first:

```bash
sudo pacman -S python playerctl
```

Arch doesn't let `pip` install into the system Python, so give Luca a little virtual environment:

```bash
python -m venv ~/.venvs/luca
```

```bash
~/.venvs/luca/bin/pip install pillow busylib
```

Then install the service, using that Python. Add `--host`, `--token`, `--linger`, `--player`
or `--reverse-wheel` here if you use them; they're saved into the service:

```bash
~/.venvs/luca/bin/python now_playing.py --install
```

That's it. Useful extras:

| To… | Run |
| :-- | :-- |
| See what Luca is doing | `journalctl --user -u luca-now-playing -f` |
| Restart him (after changing the code) | `systemctl --user restart luca-now-playing` |
| Stop him for now | `systemctl --user stop luca-now-playing` |
| Stop starting at login | `~/.venvs/luca/bin/python now_playing.py --uninstall` |

If the bar is unplugged or off Wi-Fi, Luca waits quietly and comes back when it does. The
service file lives in `~/.config/systemd/user/luca-now-playing.service`, and only you can
read it, since it may hold your API key. Keep this folder where it is: the service runs the
app from here.

### ⏳ How long Luca stays after the music stops

| Linger | Command |
| :-- | :-- |
| Leave right away | `--linger 0` |
| 30 seconds | `--linger 30s` |
| **2 minutes** (default) | *(nothing to add)* |
| 5 minutes | `--linger 5m` |

## 🎨 Make it yours

- `art.py` has everything you see: `LUCA` (the pixel Luca with headphones), `PALETTE`, the
  5×7 pixel font in `_FONT_SRC`, the bubbles and the *Luca Player* window in `back_screen()`
- `BUTTON_ACTIONS` in `now_playing.py`: which button does what
- `--fps`: how fast the title scrolls (default 10)
- `--linger`: how long Luca stays after the music stops (default 2m)
- `--player`: only show one app (Linux)
- `--reverse-wheel`: flip the volume wheel
- `python art.py` redraws the previews in `preview/`

Song titles are shown in capital pixel letters. Accents are simplified (*Café* shows as
*CAFE*), and characters the font doesn't have (like Japanese) show as `?`.

## 🔧 How it works

`media.py` finds out what's playing: on Linux it keeps `playerctl --follow` running for live
updates (and double-checks every few seconds), and elsewhere it asks about once a second. Luca is drawn only while
music plays (plus the linger time), and the app clears its screens when he steps aside. When
the song or the play state changes, `now_playing.py` draws a new title strip and back screen with Pillow and
uploads them through the BUSY Bar's local HTTP API (`/api/assets/upload`). About ten times a
second it redraws the screen with `/api/display/draw`: the sky, the title strip slid
sideways to scroll it, Luca's tile on top, and the progress bars and time as live
rectangles and text. Album art comes from the player (a file or a web address), and it's
converted to the back screen's 16 greys. Button presses and wheel turns come from the bar's status stream (`/api/status/ws`,
via `busylib`).

## 💖 Credits

Luca Wood portrait art by **KiroHusky**.
