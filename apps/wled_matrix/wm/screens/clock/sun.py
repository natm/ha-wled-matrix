"""Sun: the sun travels a 6am-6pm arc over the horizon as the hour, the sky colour following the time of day; at
night a crescent moon takes the arc among twinkling stars. The time is written on the ground."""

import math

from ...utils.canvas import scale
from ...utils.noise import rand
from ...utils.text import TINY
from .common import TAU, add, date_text, disc, dot, secs

NAME = "Sun"
DATE = True


def render(c, now, t, date):
    hrs = now.hour + now.minute / 60 + secs(now) / 3600
    day = 6 <= hrs < 18
    lift = math.sin((hrs - 6) / 12 * math.pi) if day else 0.0
    for y in range(41):
        g = y / 40
        top = (0, 10 + 30 * lift, 40 + 40 * lift) if day else (0, 0, 10)
        bot = (30 + 40 * (1 - lift), 20 + 20 * lift, 50) if day else (8, 6, 26)
        c.rect(0, y, 63, y, tuple(int(top[k] + (bot[k] - top[k]) * g) for k in range(3)))
    if not day:
        for i in range(24):
            sx, sy = int(rand("star", i) * 64), int(rand("sy", i) * 36)
            tw = 0.5 + 0.5 * math.sin(t * (1.5 + rand("tw", i) * 2) + i)
            add(c, sx, sy, (200, 200, 255), 0.2 + 0.6 * tw)
    cx, cy, r = 31.5, 40, 26
    for i in range(13):
        x, y = cx - r * math.cos(i / 12 * math.pi), cy - r * math.sin(i / 12 * math.pi)
        dot(c, x, y, (120, 100, 70) if i % 3 else (220, 180, 100), 0.7)
    f = ((hrs - 6) % 12) / 12
    bx, by = cx - r * math.cos(f * math.pi), cy - r * math.sin(f * math.pi)
    if day:
        for k in range(8):
            a = k / 8 * TAU + t * 0.8
            ln = 5.5 + 0.8 * math.sin(t * 4 + k)
            dot(c, bx + ln * math.cos(a), by + ln * math.sin(a), (255, 200, 40), 0.8)
        disc(c, bx, by, 3.2, (255, 210, 60))
    else:
        for y in range(int(by) - 4, int(by) + 5):
            for x in range(int(bx) - 4, int(bx) + 5):
                if math.hypot(x - bx, y - by) <= 3.6 and math.hypot(x - bx - 1.8, y - by + 1.2) > 3.0:
                    c.put(x, y, (230, 225, 190))
    c.rect(0, 41, 63, 63, (6, 18, 8))
    c.rect(0, 41, 63, 41, (40, 90, 40))
    tcol = (255, 220, 140)
    blink = 0.25 + 0.75 * (0.5 + 0.5 * math.cos(secs(now) * TAU))
    c.text("%02d" % now.hour, 31, 45, tcol, align="right")
    c.text(":", 32, 45, scale(tcol, blink))
    c.text("%02d" % now.minute, 34, 45, tcol)
    if date:
        c.text(date_text(now, "full"), 32, 56, (130, 170, 120), font=TINY, align="center")
