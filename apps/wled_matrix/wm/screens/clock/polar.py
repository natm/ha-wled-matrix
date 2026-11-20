"""Polar: concentric arcs for the hours (of 24), minutes and seconds, the seconds arc sweeping with a fading tail
and a pulsing head on each ring; the hour and minute in the middle."""

import math

from .common import TAU, add, disc, polar, secs

NAME = "Polar"
DATE = False


def render(c, now, t, date):
    cx = cy = 31.5
    s = secs(now)
    m = (now.minute + s / 60) / 60
    h = (now.hour + m) / 24
    rings = ((27.2, 30.6, s / 60, (40, 200, 255)), (21.8, 25.2, m, (255, 170, 40)), (16.4, 19.8, h, (255, 50, 140)))
    for y in range(64):
        for x in range(64):
            dx, dy = x - cx, y - cy
            d = math.hypot(dx, dy)
            if d < 16 or d > 31:
                continue
            ang = (math.atan2(dx, -dy) / TAU) % 1.0
            for r0, r1, frac, col in rings:
                if r0 <= d <= r1:
                    if ang <= frac:
                        lag = frac - ang
                        k = 1.0 if lag < 0.01 else 0.45 + 0.4 * max(0.0, 1 - lag * 4)
                        if col[0] == 40:  # the seconds ring fades along its tail
                            k = 0.35 + 0.65 * max(0.0, 1 - lag * 3)
                        add(c, x, y, col, k)
                    else:
                        add(c, x, y, col, 0.1)
    for r0, r1, frac, col in rings:
        hx, hy = polar(cx, cy, (r0 + r1) / 2, frac)
        disc(c, hx, hy, 1.6, (255, 255, 255), 0.6 + 0.4 * math.sin(t * 6))
    c.text("%02d" % now.hour, 32, 24, (255, 50, 140), align="center")
    c.text("%02d" % now.minute, 32, 33, (255, 170, 40), align="center")
