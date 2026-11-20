"""Rain: columns of green digits fall at different speeds behind the time, which sits in a black box."""

from ...utils.canvas import scale
from ...utils.noise import rand
from ...utils.text import TEXT, TINY
from .common import date_text

NAME = "Rain"
DATE = True


def render(c, now, t, date):
    for col in range(16):
        x = col * 4
        speed = 6 + 10 * rand("rain", col)
        head = (t * speed + rand("rain-off", col) * 64) % 90 - 12
        for i in range(10):
            y = int(head) - i * 6
            if 0 <= y < 64:
                ch = str(int(rand("rain-ch", col, y // 6, int(t * 2)) * 10) % 10)
                colour = (190, 255, 190) if i == 0 else scale((0, 200, 60), (1 - i / 10) * 0.8)
                c.text(ch, x, y, colour, font=TINY)
    y = 24 if date else 28
    c.rect(10, y - 2, 53, y + 8, (0, 0, 0))
    c.text("%02d:%02d:%02d" % (now.hour, now.minute, now.second), 32, y, (220, 255, 220), font=TEXT, align="center")
    if date:
        c.rect(16, 38, 47, 44, (0, 0, 0))
        c.text(date_text(now, "full"), 32, 39, (120, 230, 140), font=TINY, align="center")
