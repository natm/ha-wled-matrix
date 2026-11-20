"""Clock screen: the time in one of several animated styles, analog and digital, some with the date. No entities.

    clock:
      clock:
        style: classic   # classic, minimal, big, flip, sun, polar, rain, bounce, bars
        date: false      # show the date too (the styles with room for it)

Each style is a module here with a `render(canvas, now, t, date)` drawing one 64x64 frame: `now` is the local
time, `t` a monotonic clock for the animation. The frame rate defaults to 10 so the second hands sweep.
"""

import datetime

from ...utils.canvas import TextCanvas
from ..base import Screen
from . import bars, big, bounce, classic, flip, minimal, polar, rain, sun

STYLES = {m.__name__.rsplit(".", 1)[1]: m for m in (classic, minimal, big, flip, sun, polar, rain, bounce, bars)}
SIZE = 64  # the styles are drawn for a 64x64 matrix; other sizes get the face centred


def render_clock(cfg, width=SIZE, height=SIZE, *, now, t=0.0):
    """Pixels for a clock frame from the config block: `style` and `date`."""
    cfg = cfg or {}
    style = STYLES[cfg.get("style", "classic")]
    c = TextCanvas(SIZE, SIZE)
    style.render(c, now, t, bool(cfg.get("date", False)))
    if (width, height) == (SIZE, SIZE):
        return c.px
    out = TextCanvas(width, height)
    ox, oy = (width - SIZE) // 2, (height - SIZE) // 2
    for y in range(SIZE):
        for x in range(SIZE):
            out.put(ox + x, oy + y, c.px[y * SIZE + x])
    return out.px


class ClockScreen(Screen):
    key = "clock"

    def on_show(self):
        super().on_show()
        style = self.cfg.get("style", "classic")
        if style not in STYLES:
            raise ValueError(f"{self.name}: unknown clock style {style!r}; one of {', '.join(STYLES)}")

    @property
    def frame_rate(self):
        return float(self.screen.get("frame_rate", 10))

    def render(self, width, height, *, night, t, now):
        return render_clock(self.cfg, width, height, now=now or datetime.datetime.now().astimezone(), t=t)
