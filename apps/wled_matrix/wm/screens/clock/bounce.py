"""Bounce: each digit hops in turn, its shadow shrinking as it leaves the ground, in colours that cycle."""

import math

from ...utils.canvas import scale
from ...utils.glyphs import BIG
from ...utils.text import TINY
from .common import big_width, date_text

NAME = "Bounce"
DATE = True
PALETTE = [(255, 80, 80), (255, 180, 40), (80, 220, 100), (60, 160, 255), (210, 90, 255)]


def render(c, now, t, date):
    text = "%02d:%02d" % (now.hour, now.minute)
    x, base = (64 - big_width(text)) // 2, 22 if date else 26
    for i, ch in enumerate(text):
        lift = int(5 * abs(math.sin(t * 3 + i * 0.7)))
        colour = PALETTE[(i + int(t / 4)) % len(PALETTE)]
        for gy, row in enumerate(BIG[ch]):
            for gx, bit in enumerate(row):
                if bit == "1":
                    c.rect(x + gx * 2, base - lift + gy * 2, x + gx * 2 + 1, base - lift + gy * 2 + 1, colour)
        w = len(BIG[ch][0]) * 2
        shade = scale(colour, 0.25 + 0.1 * (5 - lift) / 5)
        c.rect(x + lift // 2, base + 16, x + w - 1 - lift // 2, base + 16, shade)  # the shadow shrinks as it jumps
        x += w + 2
    c.text("%02d" % now.second, 32, base + 19, (200, 200, 200), font=TINY, align="center")
    if date:
        c.text(date_text(now, "full"), 32, base + 27, (160, 160, 180), font=TINY, align="center")
