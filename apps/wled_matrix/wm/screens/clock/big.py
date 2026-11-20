"""Big: large cyan digits, a magenta colon that fades each second, the seconds, and a bar that fills across the
minute with a travelling sheen."""

import math

from ...utils.canvas import scale
from ...utils.text import TINY
from .common import TAU, add, date_text, secs

NAME = "Big"
DATE = True


def render(c, now, t, date):
    col = (60, 190, 255)
    if date:
        c.text(date_text(now, "full"), 32, 5, (150, 150, 170), font=TINY, align="center")
    y = 16
    c.big("%02d" % now.hour, 7, y, col)
    c.big("%02d" % now.minute, 35, y, col)
    k = 0.25 + 0.75 * (0.5 + 0.5 * math.cos(secs(now) * TAU))
    for cy in (y + 3, y + 9):
        c.rect(30, cy, 31, cy + 1, scale((255, 80, 200), k))
    s = secs(now)
    c.text("%02d" % now.second, 32, 37, (255, 80, 200), align="center")
    x0, x1, by = 4, 59, 49
    fill = x0 + (x1 - x0 + 1) * s / 60
    for x in range(x0, x1 + 1):
        if x < fill:
            f = (x - x0) / (x1 - x0)
            base = (int(60 + 195 * f), int(190 - 110 * f), int(255 - 55 * f))
            sheen = max(0.0, 1 - abs(((t * 20) % 70) - (x - x0)) / 4)
            c.rect(x, by, x, by + 3, tuple(min(255, int(v * (0.55 + 0.45 * sheen))) for v in base))
        else:
            c.rect(x, by, x, by + 3, (12, 14, 24))
        if (x - x0) % 11 == 0 or x == x1:
            add(c, x, by + 5, (80, 80, 100))
    head = int(fill)
    if x0 <= head <= x1:
        c.rect(head, by - 1, head, by + 4, (255, 255, 255))
