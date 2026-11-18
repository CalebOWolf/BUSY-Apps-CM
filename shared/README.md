# 🧰 shared

Code every app in this repo uses, so a fix here helps them all.

| File | What's in it |
| :-- | :-- |
| `busybar.py` | `BusyBar` (upload images, draw with a priority and an optional notification LED color, clear), `BarOffline`, display element helpers (`image`, `rect`, `text`), and `input_events()` with `is_press` / `is_wheel` / `is_selector` for the buttons, wheel and selector |
| `pixelart.py` | The 5×7 pixel font (`draw_text`, `text_width`), `aero_sky()`, `lerp()`, `ui_font()` and `led_preview()` |
| `service.py` | `--install` / `--uninstall` support: a systemd user service so an app starts at login |

Apps add this folder to their import path at the top:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from busybar import BusyBar, image, rect
```

So keep the apps next to this folder: they find it as `../shared`.
