<div align="center">

# 🟥 BUSY-Apps-CM 🟥

### *A cozy little collection of apps I've made for the BUSY Bar*

![Made with love](https://img.shields.io/badge/made%20with-♥-ff4d6d?style=flat)
![Device](https://img.shields.io/badge/device-BUSY%20Bar-ff6b35?style=flat)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat&logo=python&logoColor=white)
![License](https://img.shields.io/github/license/CalebOWolf/BUSY-Apps-CM?style=flat&color=8a5cf6)

</div>

---

## ✨ What is this?

Welcome! 👋 This is my home for custom apps built for the **BUSY Bar**, the little
desk gadget that tells the world when you're in the zone (and when you're not).

Every app here started as a *"hey, wouldn't it be neat if…"* idea, and this repo
is where those ideas live.

## 📦 The Apps

| App | What it does | Status |
| :-- | :----------- | :----: |
| [🐺 Luca Wood Aero](luca-wood-aero/) | My fursona Luca Wood in glossy Frutiger Aero / Windows 7 style, with bubbles on the front and an Aero window on the back | ✅ |
| [🎵 Luca Now Playing](luca-now-playing/) | Shows the song playing on your computer in glossy Aero style, with Luca bopping along in headphones and the buttons controlling your music | ✅ |
| [📈 Luca PC Stats](luca-pc-stats/) | My PC's CPU, RAM, GPU and temperatures as glossy Aero gauges, with Luca sweating when things get hot and a Task Manager-style window on the back | ✅ |
| [🔔 Luca Notify Den](luca-notify-den/) | My PC's desktop notifications on the bar: Luca perks up, the message scrolls by, the LED glows in the app's color, and a Windows 7-style inbox sits on the back | ✅ |
| [⛅ Luca Weather Den](luca-weather-den/) | Live local weather with an animated Aero sky (sun, rain, snow, storms, stars) and Luca dressed for it, plus a Windows 7-style weather gadget on the back | ✅ |
| [🌕 Luca Pack Focus](luca-pack-focus/) | A Pomodoro-style focus timer: a moon waxes as you focus, Luca howls when it's full, sunset breaks, and notifications wait until your break | ✅ |
| [🕰️ Luca Aero Clock](luca-aero-clock/) | A glossy desk clock with big digits, a sky that follows the real sun and moon, Luca's mood through the day, and a Windows 7 clock gadget on the back | ✅ |
| [🔴 Luca On Air](luca-on-air/) | An ON AIR sign that lights up by itself when OBS is live or recording, you're in a call, or your camera is on, with Luca in a gaming headset | ✅ |
| [💬 Luca Discord](luca-discord/) | Discord on the bar: your voice call with who's talking, mute status (OK mutes you), and new messages, in glossy blurple Aero | ✅ |
| [💜 Luca Stream Chat](luca-stream-chat/) | Your Twitch (no login needed) or YouTube live chat scrolling by, with sparkling gold alerts for subs, raids, cheers and Super Chats | ✅ |
| [⛏️ Luca Blockland](luca-blockland/) | When your Minecraft instance starts, Luca grabs a pickaxe beside a blocky landscape that scrolls by, day or starry night, with your instance's name and how long you've played | ✅ |
| [📦 Luca Update Howl](luca-update-howl/) | Your Arch updates (official repos and the AUR through paru): Luca pops up when new ones arrive, howls for a kernel update, wears a hard hat when it's time to reboot, and takes a turn in the Den while updates wait | ✅ |
| [🏠 Luca's Den](luca-den/) | Home base: the always-on apps (stats, weather, clock) take turns with glossy channel-switch cards, and `--status` checks on every app | ✅ |
| [📶 BUSY Speedtest](busy-speedtest/) | A simple internet speed test: ping, download and upload, on the front strip and the back screen | ✅ |

> 💡 **Tip:** Each app lives in its own folder with its own notes on how to install
> and use it. The code they share for talking to the bar lives in [`shared/`](shared/).

## 🚀 Getting Started

**Clone** the repo:

```bash
git clone https://github.com/CalebOWolf/BUSY-Apps-CM.git
```

```bash
cd BUSY-Apps-CM
```

### ⚡ Install everything at once (Linux)

```bash
python install.py
```

It shows a menu of the apps. Pick some (`1 4 6`, or names like `now-playing clock`), or
press **Enter for all of them**. Then it:

1. Makes Luca's Python environment (`~/.venvs/luca`) and installs just the packages your
   apps need
2. Tells you about any Arch packages they need (like `playerctl` or `cava`) and offers to
   install them with `pacman`
3. Asks only what an app needs: your **city** for Weather Den, your **Twitch channel** for
   Stream Chat, and optional **OBS** and **Discord** details (Enter skips)
4. Sets each app to **start at login**

| Command | Does |
| :-- | :-- |
| `python install.py` | Pick from the menu |
| `python install.py --all` | Every app (still asks for your city and channel) |
| `python install.py now-playing pc-stats` | Just these apps |
| `python install.py --all --city "Berlin" --twitch yourchannel --yes` | Everything, no questions asked |
| `python install.py --list` | What's available, and what's installed |
| `python install.py --reconfigure` | Ask everything again instead of using your saved answers |
| `python install.py --forget` | Delete your saved answers (passwords and keys too) |
| `python install.py --check` | Try each app on the bar for a few seconds and report any trouble, installing nothing |
| `python install.py --uninstall clock` | Stop an app (or `--all`) starting at login |

Not sure everything works with your bar yet? Run `python install.py --check` first: each app
shows its demo on the bar for 12 seconds, one at a time, then you get a ✅ or ⚠️ for each.

🔒 Your answers (city, channel, OBS password, Discord keys, the bar's address and key) are
saved in `~/.config/luca-bar/settings.json`, which only you can read. Uninstalling keeps them,
so a reinstall doesn't ask again.

Run it again any time: it updates the apps you pick. Afterwards, check on everything with
`~/.venvs/luca/bin/python luca-den/luca_den.py --status`.

### 🧩 Or one at a time

Every app folder has its own README and its own `--install`, if you'd rather set them up
by hand or try one first. **Pick** a folder that looks fun, **follow** its instructions, and
**enjoy** your extra-busy (or extra-chill) desk. 😎

## 🤝 Contributing

Got an idea, found a bug, or just want to say hi? Feel free to
[open an issue](https://github.com/CalebOWolf/BUSY-Apps-CM/issues) or send a pull request.
Kind words and cool suggestions are always welcome. 🌱

## 📜 License

Released under the [MIT License](LICENSE), so share it, remix it, and have fun with it.

---

<div align="center">

**Stay focused. Stay busy. Take breaks.** 🌙

<sub>Crafted with care by CalebOWolf</sub>

</div>
