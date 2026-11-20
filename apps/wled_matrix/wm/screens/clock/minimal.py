"""Minimal: two floating hands in a ring of sixty dots that fills through the minute; the hub breathes."""

import math

from ...utils.canvas import scale
from .common import TAU, add, disc, dot, hand_fracs, line, polar, secs

NAME = "Minimal"
DATE = False


def render(c, now, t, date):
    cx = cy = 31.5
    s = secs(now)
    for i in range(60):
        x, y = polar(cx, cy, 29, i / 60)
        x, y = int(round(x)), int(round(y))
        if i < int(s):
            age = (s - i) / 60
            col = scale((40, 220, 200), 0.95 - age * 0.6)
        elif i == int(s):
            col = scale((255, 255, 255), 0.5 + 0.5 * math.cos((s % 1) * math.pi))
        else:
            col = (14, 28, 30) if i % 5 else (40, 60, 60)
        add(c, x, y, col)
        if i % 15 == 0:
            ix, iy = polar(cx, cy, 25, i / 60)
            dot(c, ix, iy, (90, 90, 90))
    h, m, _ = hand_fracs(now)
    for frac, length, col, w in ((h, 13, (255, 120, 30), 3), (m, 21, (230, 230, 220), 2)):
        x0, y0 = polar(cx, cy, 3, frac)
        x1, y1 = polar(cx, cy, length, frac)
        px, py = math.cos(frac * TAU), math.sin(frac * TAU)
        for o in {2: (-0.4, 0.4), 3: (-0.7, 0, 0.7)}[w]:
            line(c, x0 + px * o, y0 + py * o, x1 + px * o, y1 + py * o, col)
    breath = 0.5 + 0.5 * math.sin(t * 2)
    disc(c, cx, cy, 1.0, (255, 120, 30), 0.4 + 0.6 * breath)
