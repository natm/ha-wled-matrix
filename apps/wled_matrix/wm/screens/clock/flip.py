"""Flip: split-flap cards for the hours and minutes, a small card flipping every second, and a line that fills
across the minute."""

from ...utils.canvas import TextCanvas, scale
from ...utils.text import DAY_NAMES, TINY
from .common import add, date_text, secs

NAME = "Flip"
DATE = True


def card(w, h, text, big):
    cv = TextCanvas(w, h)
    cv.rect(0, 0, w - 1, h - 1, (30, 30, 36))
    for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        cv.put(x, y, (0, 0, 0))
    col = (235, 225, 205)
    if big:
        cv.big(text, 2, 4, col)
    else:
        cv.text(text, w // 2, 2, col, align="center")
    return cv


def flip_card(c, x0, y0, w, h, old, new, p, big=True):
    """A split-flap card turning from `old` to `new`; p in 0..1 is the flap's progress (1 = settled)."""
    a, b = card(w, h, old, big), card(w, h, new, big)
    half = h // 2
    for y in range(h):
        src = b if (y < half or p >= 1) else a
        for x in range(w):
            c.put(x0 + x, y0 + y, src.px[y * w + x])
    if p < 0.5:
        fh = max(1, round(half * (1 - 2 * p)))
        for r in range(fh):
            sy = int(r / fh * half)
            for x in range(w):
                c.put(x0 + x, y0 + half - fh + r, scale(a.px[sy * w + x], 0.6 + 0.4 * (1 - 2 * p)))
    elif p < 1:
        fh = max(1, round((h - half) * (2 * p - 1)))
        for r in range(fh):
            sy = half + int(r / fh * (h - half))
            for x in range(w):
                c.put(x0 + x, y0 + half + r, scale(b.px[sy * w + x], 0.6 + 0.4 * (2 * p - 1)))
    for x in range(w):
        i = (y0 + half) * c.w + x0 + x
        c.px[i] = scale(c.px[i], 0.35)


def render(c, now, t, date):
    s, us = now.second, now.microsecond / 1e6
    p_min = us / 0.6 if s == 0 and us < 0.6 else 1.0
    p_hour = p_min if now.minute == 0 else 1.0
    flip_card(c, 4, 6, 26, 22, "%02d" % ((now.hour - 1) % 24), "%02d" % now.hour, p_hour)
    flip_card(c, 34, 6, 26, 22, "%02d" % ((now.minute - 1) % 60), "%02d" % now.minute, p_min)
    flip_card(c, 23, 33, 18, 12, "%02d" % ((s - 1) % 60), "%02d" % s, min(1.0, us / 0.35), big=False)
    for y in (13, 20):
        c.rect(31, y, 32, y + 1, scale((235, 225, 205), 0.5))
    fill = secs(now) / 60 * 40
    for i in range(40):
        add(c, 12 + i, 48, (200, 150, 70), 0.9 if i <= fill < i + 1 else (0.35 if i < fill else 0.08))
    if date:
        c.text(date_text(now, "full"), 32, 52, (200, 150, 70), font=TINY, align="center")
    else:
        c.text(DAY_NAMES[now.weekday()], 32, 52, (90, 90, 100), font=TINY, align="center")
