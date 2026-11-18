# 🧰 shared

Code every app in this repo uses, so a fix here helps them all.

| File | What's in it |
| :-- | :-- |
| `busybar.py` | `BusyBar` (upload images, draw with a priority and an optional notification LED color, clear), `BarOffline`, display element helpers (`image`, `rect`, `text`), and `input_events()` with `is_press` / `is_wheel` / `is_selector` for the buttons, wheel and selector. `Presence` makes sure only the app on top answers a button press (built into `BusyBar` and `input_events()`), and `mark_running()` / `is_running()` let apps hand things over to each other |
| `pixelart.py` | The 5×7 pixel font (`draw_text`, `text_width`), `aero_sky()`, `lerp()`, `ui_font()` and `led_preview()` |
| `notifications.py` | The D-Bus desktop-notification watcher (used by Notify Den and Discord) |
| `devices.py` | Which apps are using the mic and webcam (used by On Air and Discord) |
| `quiet.py` | `quiet_reason()`: should notification apps hold messages (focus round / on air)? |
| `service.py` | `--install` / `--uninstall` support: a systemd user service so an app starts at login |

Apps add this folder to their import path at the top:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from busybar import BusyBar, image, rect
```

So keep the apps next to this folder: they find it as `../shared`.
