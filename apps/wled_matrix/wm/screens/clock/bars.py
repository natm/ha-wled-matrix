"""Bars: the hour, minute and second as three filling bars with the number at the end; the seconds bar creeps
smoothly and its leading edge glows."""

from ...utils.canvas import scale
from ...utils.text import TEXT, TINY
from .common import date_text, secs

NAME = "Bars"
DATE = True


def render(c, now, t, date):
    s = secs(now)
    rows = (
        ("H", now.hour, 24, (255, 150, 40), "%02d" % now.hour),
        ("M", now.minute + s / 60, 60, (80, 220, 110), "%02d" % now.minute),
        ("S", s, 60, (70, 150, 255), "%02d" % now.second),
    )
    top, gap = (3, 16) if date else (6, 18)
    x0, x1 = 7, 46
    for i, (label, value, top_value, colour, number) in enumerate(rows):
        y = top + i * gap
        c.text(label, 1, y + 2, scale(colour, 0.7), font=TINY)
        c.rect(x0, y, x1, y + 6, (16, 16, 24))
        fill = x0 + (x1 - x0 + 1) * value / top_value
        for x in range(x0, int(fill)):
            k = 0.55 + 0.45 * (x - x0) / (x1 - x0)
            c.rect(x, y + 1, x, y + 5, scale(colour, k))
        head = int(fill)
        if head <= x1:
            c.rect(head, y, head, y + 6, scale(colour, 0.5 + 0.5 * (fill - head)))  # the moving edge
        c.text(number, 63, y, (230, 230, 230), font=TEXT, align="right")
    if date:
        c.text(date_text(now, "full"), 32, 55, (170, 170, 200), font=TINY, align="center")
