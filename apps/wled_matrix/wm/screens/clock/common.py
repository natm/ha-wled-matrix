"""Drawing helpers the clock styles share: anti-aliased dots and lines, hands, discs and the date text."""

import math

from ...utils.glyphs import BIG
from ...utils.text import DAY_NAMES

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
TAU = 2 * math.pi


def secs(now):
    """Seconds into the minute, fractional."""
    return now.second + now.microsecond / 1e6


def hand_fracs(now):
    """(hour, minute, second) hand positions as fractions of a turn."""
    s = secs(now)
    m = (now.minute + s / 60) / 60
    h = ((now.hour % 12) + m) / 12
    return h, m, s / 60


def date_text(now, style="day"):
    """The date as text: `day` FRI 20, `full` FRI 20 NOV, `num` 20/11."""
    if style == "day":
        return "%s %d" % (DAY_NAMES[now.weekday()], now.day)
    if style == "full":
        return "%s %d %s" % (DAY_NAMES[now.weekday()], now.day, MONTHS[now.month - 1])
    return "%02d/%02d" % (now.day, now.month)


def add(c, x, y, col, a=1.0):
    """Light (x, y) with `col` at strength `a`, keeping the brighter of old and new per channel."""
    if 0 <= x < c.w and 0 <= y < c.h and a > 0.02:
        i = y * c.w + x
        o = c.px[i]
        c.px[i] = tuple(max(o[k], min(255, int(col[k] * a))) for k in range(3))


def dot(c, x, y, col, a=1.0):
    """An anti-aliased point at fractional (x, y)."""
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    for dx, dy, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        add(c, x0 + dx, y0 + dy, col, a * min(1.0, w * 1.7))


def line(c, x0, y0, x1, y1, col, a=1.0):
    n = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
    for i in range(n + 1):
        f = i / n
        dot(c, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, col, a)


def polar(cx, cy, r, frac):
    """The point at radius r and fraction `frac` of a turn clockwise from 12 o'clock."""
    a = frac * TAU
    return cx + r * math.sin(a), cy - r * math.cos(a)


def hand(c, cx, cy, frac, length, col, width=1, tail=0.0):
    """A clock hand; width 2 or 3 adds parallel strokes; `tail` extends it past the hub."""
    ex, ey = polar(cx, cy, length, frac)
    sx, sy = polar(cx, cy, -tail, frac)
    px, py = math.cos(frac * TAU), math.sin(frac * TAU)
    offsets = {1: [0.0], 2: [-0.4, 0.4], 3: [-0.8, 0.0, 0.8]}[width]
    for o in offsets:
        line(c, sx + px * o, sy + py * o, ex + px * o * 0.5, ey + py * o * 0.5, col)


def disc(c, cx, cy, r, col, a=1.0):
    for y in range(int(cy - r - 1), int(cy + r + 2)):
        for x in range(int(cx - r - 1), int(cx + r + 2)):
            d = math.hypot(x - cx, y - cy)
            if d <= r + 0.5:
                add(c, x, y, col, a * min(1.0, r + 0.5 - d + 0.3))


def big_width(text):
    """Width of `text` in the 10x14 number font."""
    return sum((len(BIG[ch][0]) + 1) * 2 for ch in text) - 2
