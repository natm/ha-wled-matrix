"""Tide screen: high and low waters from any Home Assistant entity that lists them.

Two layouts:
- `list` (a tide table): the next four high (▲) and low (▼) waters, time in large digits and height, "IN 2H06" under
  the next one, and a line with the day's name before the first of tomorrow's.
- `curve`: today's tide from 00:00 to 24:00 with the sea filled in, a dotted line and a dot for now, the past half
  dimmed, and the next high and low below.

Heights are printed without a unit; a small `M` in the top-right corner gives it once for all of them.

The events come from an attribute of an entity (default `predictions`, as the UKHO Tides integration gives:
[["2026-11-08 05:27:00", 5.3], ...], times in UTC). Items can also be dicts (`time_key`, `height_key`, `type_key`).
When an item doesn't say whether it's a high or a low, it's worked out from its neighbours. Between events the curve
is a half-cosine, which is within a few centimetres of the real tide on most UK coasts.

Pure Python, no dependencies.
"""

import datetime
import math

from wm_render import Canvas
from wm_text import TEXT, TINY, draw_text, text_width

DAY_NAMES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

GREY = (120, 120, 120)
DIM = (80, 80, 80)
WHITE = (215, 215, 215)
HIGH = (0, 200, 255)    # high water: cyan
LOW = (0, 90, 200)      # low water: deep blue
WATER = (0, 45, 110)
COUNTDOWN = (0, 150, 200)
DIVIDER = (35, 35, 35)

HIGH_WORDS = {"h", "high", "highwater", "high_water", "high water", "hw"}


def parse_time(value, zone=datetime.timezone.utc):
    """A datetime from an ISO string or datetime; naive times are taken to be in `zone`."""
    if isinstance(value, datetime.datetime):
        when = value
    else:
        try:
            when = datetime.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return when if when.tzinfo else when.replace(tzinfo=zone)


def parse_events(raw, cfg=None, zone=datetime.timezone.utc):
    """Sorted [(aware datetime, "H" or "L", height m), ...] from a list of [time, height] pairs or dicts."""
    cfg = cfg or {}
    tk, hk, yk = cfg.get("time_key", "time"), cfg.get("height_key", "height"), cfg.get("type_key", "type")
    events = []
    for item in raw or []:
        kind = None
        if isinstance(item, dict):
            when, height, kind = item.get(tk), item.get(hk), item.get(yk)
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            when, height = item[0], item[1]
            kind = item[2] if len(item) > 2 else None
        else:
            continue
        when = parse_time(when, zone)
        try:
            height = float(str(height).rstrip("m ").strip())
        except (TypeError, ValueError):
            continue
        if when is None:
            continue
        if kind is not None:
            kind = "H" if str(kind).strip().lower() in HIGH_WORDS else "L"
        events.append([when, kind, height])
    events.sort(key=lambda e: e[0])
    for i, e in enumerate(events):  # infer high or low from the neighbours where the source doesn't say
        if e[1] is None:
            nbrs = [events[j][2] for j in (i - 1, i + 1) if 0 <= j < len(events)]
            e[1] = "H" if nbrs and all(e[2] > n for n in nbrs) else "L"
    return [tuple(e) for e in events]


def height_at(events, when):
    """Height (m) at `when`, a half-cosine between the events either side; None outside them."""
    for (t0, _, h0), (t1, _, h1) in zip(events, events[1:]):
        if t0 <= when <= t1:
            span = (t1 - t0).total_seconds()
            u = (when - t0).total_seconds() / span if span else 0
            return h0 + (h1 - h0) * (1 - math.cos(math.pi * u)) / 2
    return None


def upcoming(events, now, n):
    return [e for e in events if e[0] > now][:n]


def hhmm(when, zone):
    return when.astimezone(zone).strftime("%H:%M")


def countdown(delta):
    mins = max(0, int(round(delta.total_seconds() / 60)))
    return f"IN {mins // 60}H{mins % 60:02d}"


def scale(colour, k):
    return tuple(max(0, min(255, int(v * k))) for v in colour)


class TideCanvas(Canvas):
    def put(self, x, y, colour, a=1.0):
        x, y = int(math.floor(x)), int(math.floor(y))
        if 0 <= x < self.w and 0 <= y < self.h and a > 0:
            if a < 1:
                old = self.px[y * self.w + x]
                colour = tuple(int(old[i] * (1 - a) + colour[i] * a) for i in range(3))
            self.px[y * self.w + x] = tuple(int(v) for v in colour)

    def hline(self, x0, x1, y, c):
        for x in range(x0, x1 + 1):
            self.put(x, y, c)

    def text(self, s, x, y, colour, font=TINY):
        return draw_text(self, s, x, y, colour, font)

    def triangle(self, x, y, up, colour):
        rows = ["00100", "01110", "11111"] if up else ["11111", "01110", "00100"]
        for r, row in enumerate(rows):
            for k, b in enumerate(row):
                if b == "1":
                    self.put(x + k, y + r, colour)


def header(c, label, width):
    """Place name top left, and the height unit once, top right."""
    if label:
        c.text(label, 0, 1, GREY)
    c.text("M", width - text_width("M") - 1, 1, DIM)


def no_data(c, label, width, height):
    header(c, label, width)
    for x in range(width):  # a flat, dim sea
        c.put(x, height // 2 + 6, scale(WATER, 0.8))
    msg = "NO DATA"
    c.text(msg, (width - text_width(msg)) // 2, height // 2 - 4, GREY)


def render_list(c, events, now, zone, label, width):
    header(c, label, width)
    y, divided = 9, False
    for i, (when, kind, h) in enumerate(upcoming(events, now, 4)):
        later_day = when.astimezone(zone).date() != now.astimezone(zone).date()
        if later_day and not divided:  # a line and the day's name before the first tide of another day
            day = DAY_NAMES[when.astimezone(zone).weekday()]
            c.hline(0, width - text_width(day) - 6, y + 1, DIVIDER)
            c.text(day, width - text_width(day) - 1, y - 1, (90, 90, 90))
            y, divided = y + 5, True
        colour = HIGH if kind == "H" else LOW
        c.triangle(1, y + 2, kind == "H", colour)
        c.text(hhmm(when, zone), 9, y, WHITE if not later_day else (170, 170, 170), TEXT)
        hs = f"{h:.1f}"
        c.text(hs, width - text_width(hs) - 1, y + 2, colour if not later_day else scale(colour, 0.75))
        if i == 0:
            c.text(countdown(when - now), 9, y + 9, COUNTDOWN)
        y += 16 if i == 0 else 13


def render_curve(c, events, now, zone, label, width, height, hmax=None):
    local_now = now.astimezone(zone)
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + datetime.timedelta(days=1)
    if label:
        c.text(label, (width - text_width(label)) // 2, 1, GREY)
    c.text("M", width - text_width("M") - 1, 1, DIM)
    y_top, y_bot = 9, 46
    if hmax is None:
        hmax = max([e[2] for e in events] + [1.0]) * 1.1

    def y_of(h):
        return y_bot - h / hmax * (y_bot - y_top)
    span = (end - start).total_seconds()
    for x in range(width):
        when = start + datetime.timedelta(seconds=(x + .5) / width * span)
        h = height_at(events, when)
        if h is None:
            continue
        y = y_of(h)
        past = when < now
        for yy in range(int(math.ceil(y)), y_bot + 1):  # water, deeper = darker
            k = 1 - (yy - y) / (y_bot - y_top) * .6
            c.put(x, yy, scale(WATER, k * (.55 if past else 1)))
        frac = y - math.floor(y)
        line = scale(HIGH, .5 if past else 1)
        c.put(x, math.floor(y), line, 1 - frac * .5)
        if frac > .3:
            c.put(x, math.floor(y) + 1, line, frac)
    h_now = height_at(events, now)
    if h_now is not None:
        xn = (now - start).total_seconds() / span * width
        for yy in range(y_top, y_bot + 1, 2):
            c.put(xn, yy, (90, 90, 90))
        yn = y_of(h_now)
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
            c.put(xn - .5 + dx, yn - .5 + dy, WHITE)
    for i, (when, kind, h) in enumerate(upcoming(events, now, 2)):
        y = 50 + i * 7
        c.triangle(1, y + 1, kind == "H", HIGH if kind == "H" else LOW)
        c.text(hhmm(when, zone), 9, y, WHITE)
        hs = f"{h:.1f}"
        c.text(hs, width - text_width(hs) - 1, y, GREY)


def render_tides(cfg, events, now, zone, width=64, height=64):
    """`cfg` is the screen's `tides:` block, `events` from parse_events, `now` an aware datetime, `zone` the local
    time zone for the times shown."""
    c = TideCanvas(width, height)
    label = cfg.get("label", "")
    if not upcoming(events, now, 1):
        no_data(c, label, width, height)
    elif cfg.get("layout", "list") == "curve":
        render_curve(c, events, now, zone, label, width, height, cfg.get("max_height"))
    else:
        render_list(c, events, now, zone, label, width)
    return c.px
