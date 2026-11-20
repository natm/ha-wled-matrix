"""Classic: a navy station-clock face, cream hands and a sweeping red second hand with a counterweight."""

from ...utils.text import TINY
from .common import date_text, disc, dot, hand, hand_fracs, line, polar

NAME = "Classic"
DATE = True


def render(c, now, t, date):
    cx = cy = 31.5
    disc(c, cx, cy, 29.5, (0, 4, 22))
    for i in range(60):
        x, y = polar(cx, cy, 29.5, i / 60)
        dot(c, x, y, (70, 80, 110), 0.5)
    for i in range(12):
        big = i % 3 == 0
        x0, y0 = polar(cx, cy, 24 if big else 26, i / 12)
        x1, y1 = polar(cx, cy, 29, i / 12)
        line(c, x0, y0, x1, y1, (230, 210, 160) if big else (130, 130, 150))
    if date:
        c.text(date_text(now), 32, 40, (200, 140, 40), font=TINY, align="center")
    h, m, s = hand_fracs(now)
    hand(c, cx, cy, h, 14, (230, 210, 170), width=3)
    hand(c, cx, cy, m, 22, (230, 220, 200), width=2)
    hand(c, cx, cy, s, 26, (255, 30, 20), tail=6)
    ox, oy = polar(cx, cy, -5, s)
    disc(c, ox, oy, 1.2, (255, 30, 20))
    disc(c, cx, cy, 1.5, (255, 40, 30))
