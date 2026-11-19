# Contributing

Plain Python, no dependencies beyond AppDaemon at run time (and Pillow for camera screens). From the repo root:

```bash
python3 -m unittest discover tests     # the tests need neither AppDaemon nor Home Assistant
black apps tests && ruff check apps tests   # the profile is in pyproject.toml; CI runs both
```

## Layout

```
apps/wled_matrix/
  wled_matrix.py        the AppDaemon app: rotation, timers, night dimming, the live view's routes
  wm/screens/           one module per screen type; base.py says what a screen is
  wm/screens/fun/       the animated screens that read no entities
  wm/utils/             canvas and fonts, icons, value formatting, DDP, config placeholders
  wm/web.py             the live-view page
tests/                  mirrors the package: tests/screens/, tests/screens/fun/, tests/utils/
docs/screens/           one page per screen type: screenshot, YAML and every option
```

## Adding a screen

A screen type is one module with one `Screen` subclass. The class names the config key that selects it and draws a
frame; the base class (`wm/screens/base.py`) handles everything else: the generic options (`dwell`, `frame_rate`,
`show_if`, `priority`, …), `{random: [low, high]}` config values, and access to Home Assistant through `host`.

1. **Create `apps/wled_matrix/wm/screens/moon.py`** (or `wm/screens/fun/moon.py` for an animation needing no
   entities). Keep the drawing in a plain function so the tests can call it without a host:

   ```python
   """Moon screen: tonight's phase. The config key is `moon:`."""

   from ..utils.canvas import TextCanvas
   from ..utils.values import to_number
   from .base import Screen


   def render_moon(cfg, phase, width=64, height=64, mdi=None, t=0.0, night=False):
       c = TextCanvas(width, height)
       ...
       return c.px


   class MoonScreen(Screen):
       key = "moon"

       def entities(self):
           return [self.cfg["entity"]]

       def render(self, width, height, *, night, t, now):
           phase = to_number(self.state(self.cfg["entity"]))
           return render_moon(self.cfg, phase, width, height, self.mdi, t=t, night=night)
   ```

   `self.cfg` is the screen's `moon:` block with any `{random: ...}` values already drawn; `self.screen` is the
   whole entry. `self.state()`, `self.states()`, `self.call_service()`, `self.log()`, `self.mdi` and
   `self.shared()` (one fetcher per app, for a source several screens read) are the host services. Return `None`
   for "nothing to show yet". For background work, override `start()` and use `self.host.run_every` or
   `self.host.listen_state`. Keep per-screen caches on the instance; a screen named once in `screens:` is one object.

2. **Register it** with one line in `wm/screens/__init__.py` (or `wm/screens/fun/__init__.py`): add `moon` to the
   `from . import …` line and to `__all__`. The explicit import is what AppDaemon's reload tracking follows, so an
   edited screen reloads the app while you work.

3. **Test it** in `tests/screens/test_moon.py` (same folder structure as the package): call `render_moon()` with a
   config and canned data and check pixels; `tests/screens/test_base.py` already checks that every registered type
   builds and renders a full frame, so add your key and a minimal config to its `CONFIGS` table.

4. **Document it**: a short section in the README with a screenshot and the YAML example plus a "Config docs" link,
   and `docs/screens/moon.md` with the same screenshot and YAML at the top followed by every option. The live view
   (`web: true`, the Preview tab) is the quickest way to design a screen and grab the screenshot.

Nothing in `wled_matrix.py` changes.
